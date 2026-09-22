# novel_generator/knowledge.py
# -*- coding: utf-8 -*-
"""
知识文件导入至向量库
零 langchain/pydantic v1 依赖
"""
import os
import logging
import re
import traceback
import warnings

import nltk

from novel_utils import read_file
from novel_generator.vectorstore_utils import load_vector_store, init_vector_store, Document

warnings.filterwarnings('ignore', message='.*Torch was not compiled with flash attention.*')
os.environ["TOKENIZERS_PARALLELISM"] = "false"

logging.basicConfig(
    filename='app.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def advanced_split_content(
    content: str, similarity_threshold: float = 0.7, max_length: int = 500
) -> list:
    """使用基本分段策略"""
    sentences = nltk.sent_tokenize(content)
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


def import_knowledge_file(
    embedding_api_key: str,
    embedding_url: str,
    embedding_interface_format: str,
    embedding_model_name: str,
    file_path: str,
    filepath: str,
):
    """将知识文件导入向量库"""
    logging.info(
        f"开始导入知识库文件: {file_path}, "
        f"接口: {embedding_interface_format}, 模型: {embedding_model_name}"
    )
    if not os.path.exists(file_path):
        logging.warning(f"知识库文件不存在: {file_path}")
        return

    content = read_file(file_path)
    if not content.strip():
        logging.warning("知识库文件内容为空。")
        return

    paragraphs = advanced_split_content(content)
    from embedding_adapters import create_embedding_adapter

    embedding_adapter = create_embedding_adapter(
        embedding_interface_format,
        embedding_api_key,
        embedding_url if embedding_url else "http://localhost:11434/api",
        embedding_model_name,
    )

    store = load_vector_store(embedding_adapter, filepath)
    if not store:
        logging.info("向量库不存在，创建新库并导入...")
        store = init_vector_store(embedding_adapter, paragraphs, filepath)
        if store:
            logging.info("知识库文件已成功导入至向量库(新初始化)。")
        else:
            logging.warning("知识库导入失败，跳过。")
    else:
        try:
            docs = [Document(page_content=str(p)) for p in paragraphs]
            # 直接用 chromadb collection 的 add 方法
            existing_ids = set(store.get().get("ids", []))
            new_ids = [f"knowledge_{len(existing_ids) + i}" for i in range(len(docs))]
            store.add(
                documents=[d.page_content for d in docs],
                ids=new_ids,
            )
            logging.info("知识库文件已成功导入至向量库(追加模式)。")
        except Exception as e:
            logging.warning(f"知识库导入失败: {e}")
            traceback.print_exc()
