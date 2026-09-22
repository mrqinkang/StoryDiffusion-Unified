# novel_generator/vectorstore_utils.py
# -*- coding: utf-8 -*-
"""
向量库相关操作（初始化、更新、检索、清空、文本切分等）
纯原生 chromadb，零 langchain/pydantic v1 依赖
"""
import os
import re
import json
import shutil
import logging
import traceback
import warnings
from dataclasses import dataclass, field
from typing import List, Optional

import nltk
import numpy as np

import chromadb
from chromadb.config import Settings

from .common import call_with_retry

logging.basicConfig(
    filename='app.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
warnings.filterwarnings('ignore', message='.*Torch was not compiled with flash attention.*')
os.environ["TOKENIZERS_PARALLELISM"] = "false"


# ============================================================
# 极简 Document 类（替代 langchain_core.documents.Document）
# ============================================================

@dataclass
class Document:
    page_content: str
    metadata: dict = field(default_factory=dict)


# ============================================================
# ChromaDB Embedding 函数包装
# ============================================================

class _ChromaEmbeddingFunction:
    """将 embedding_adapter 包装成 ChromaDB 可用的 embedding 函数"""
    def __init__(self, embedding_adapter):
        self._adapter = embedding_adapter

    def __call__(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return call_with_retry(
            func=self._adapter.embed_documents,
            max_retries=3,
            fallback_return=[[0.0]],
            texts=texts,
        )


# ============================================================
# 路径 / 工具
# ============================================================

def get_vectorstore_dir(filepath: str) -> str:
    return os.path.join(filepath, "vectorstore")


def clear_vector_store(filepath: str) -> bool:
    store_dir = get_vectorstore_dir(filepath)
    if not os.path.exists(store_dir):
        logging.info("No vector store found to clear.")
        return False
    try:
        shutil.rmtree(store_dir)
        logging.info(f"Vector store directory '{store_dir}' removed.")
        return True
    except Exception as e:
        logging.error(f"Failed to remove vector store: {e}")
        traceback.print_exc()
        return False


def _get_or_create_collection(embedding_adapter, filepath: str):
    """获取或创建 ChromaDB collection"""
    store_dir = get_vectorstore_dir(filepath)
    os.makedirs(store_dir, exist_ok=True)
    client = chromadb.PersistentClient(
        path=store_dir,
        settings=Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name="novel_collection",
        embedding_function=_ChromaEmbeddingFunction(embedding_adapter),
    )


def _get_collection(embedding_adapter, filepath: str):
    """只获取已存在的 collection，不存在返回 None"""
    store_dir = get_vectorstore_dir(filepath)
    if not os.path.exists(store_dir):
        return None
    try:
        client = chromadb.PersistentClient(
            path=store_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        return client.get_collection(name="novel_collection")
    except Exception:
        return None


# ============================================================
# 核心操作
# ============================================================

def init_vector_store(embedding_adapter, texts, filepath: str):
    """初始化向量库并插入文本"""
    try:
        collection = _get_or_create_collection(embedding_adapter, filepath)
        # 清空已有数据再插入
        existing = collection.get()
        if existing and existing.get("ids"):
            collection.delete(existing["ids"])
        # 插入新文本
        doc_ids = [f"doc_{i}" for i in range(len(texts))]
        collection.add(
            documents=[str(t) for t in texts],
            ids=doc_ids,
        )
        logging.info(f"Vector store initialized with {len(texts)} documents.")
        return collection
    except Exception as e:
        logging.warning(f"Init vector store failed: {e}")
        traceback.print_exc()
        return None


def load_vector_store(embedding_adapter, filepath: str):
    """加载已存在的向量库"""
    try:
        collection = _get_collection(embedding_adapter, filepath)
        return collection
    except Exception as e:
        logging.warning(f"Load vector store failed: {e}")
        return None


def update_vector_store(embedding_adapter, new_chapter: str, filepath: str):
    """将新章节文本插入向量库"""
    from novel_utils import read_file, clear_file_content, save_string_to_txt

    splitted_texts = split_text_for_vectorstore(new_chapter)
    if not splitted_texts:
        logging.warning("No valid text to insert into vector store. Skipping.")
        return

    collection = _get_collection(embedding_adapter, filepath)
    if not collection:
        logging.info("Vector store not found. Initializing new one...")
        collection = init_vector_store(embedding_adapter, splitted_texts, filepath)
        return

    try:
        existing_ids = set(collection.get().get("ids", []))
        new_ids = []
        new_docs = []
        for i, t in enumerate(splitted_texts):
            doc_id = f"doc_{len(existing_ids) + i}"
            new_ids.append(doc_id)
            new_docs.append(str(t))
        if new_docs:
            collection.add(documents=new_docs, ids=new_ids)
            logging.info(f"Vector store updated with {len(new_docs)} new segments.")
    except Exception as e:
        logging.warning(f"Update vector store failed: {e}")
        traceback.print_exc()


def get_relevant_context_from_vector_store(
    embedding_adapter, query: str, filepath: str, k: int = 2
) -> str:
    """从向量库检索相关上下文"""
    collection = _get_collection(embedding_adapter, filepath)
    if not collection:
        logging.info("No vector store found. Returning empty context.")
        return ""

    try:
        results = collection.query(query_texts=[query], n_results=k)
        if not results or not results.get("documents") or not results["documents"][0]:
            return ""
        combined = "\n".join(results["documents"][0])
        return combined[:2000]
    except Exception as e:
        logging.warning(f"Similarity search failed: {e}")
        traceback.print_exc()
        return ""


# ============================================================
# 文本切分
# ============================================================

def split_by_length(text: str, max_length: int = 500) -> List[str]:
    """按长度切分文本"""
    segments = []
    start = 0
    while start < len(text):
        end = min(start + max_length, len(text))
        segments.append(text[start:end].strip())
        start = end
    return segments


def split_text_for_vectorstore(
    chapter_text: str, max_length: int = 500, similarity_threshold: float = 0.7
) -> List[str]:
    """将章节文本分段，用于存入向量库"""
    if not chapter_text.strip():
        return []

    sentences = nltk.sent_tokenize(chapter_text)
    if not sentences:
        return []

    final_segments = []
    current_segment = []
    current_length = 0

    for sentence in sentences:
        sentence_length = len(sentence)
        if current_length + sentence_length > max_length:
            if current_segment:
                final_segments.append(" ".join(current_segment))
            current_segment = [sentence]
            current_length = sentence_length
        else:
            current_segment.append(sentence)
            current_length += sentence_length

    if current_segment:
        final_segments.append(" ".join(current_segment))

    return final_segments


def _get_sentence_transformer(model_name: str = 'paraphrase-MiniLM-L6-v2'):
    """占位 - 无 torch 环境时不可用"""
    logging.warning("Sentence transformer is not available without torch.")
    return None
