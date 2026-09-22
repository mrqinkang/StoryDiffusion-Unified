# embedding_adapters.py
# -*- coding: utf-8 -*-
"""
Embedding 适配器工厂 - 统一接口
纯原生 SDK，零 langchain/pydantic v1 依赖
"""

import re
import logging
import traceback
from typing import List

import requests
from openai import OpenAI, AzureOpenAI
from google import genai

DEFAULT_REQUEST_TIMEOUT = (5, 60)


def ensure_openai_base_url_has_v1(url: str) -> str:
    """规范化 base_url，确保包含 /v1"""
    url = url.strip()
    if not url:
        return url
    if not re.search(r'/v\d+$', url):
        if '/v1' not in url:
            url = url.rstrip('/') + '/v1'
    return url


class BaseEmbeddingAdapter:
    """Embedding 接口统一基类"""
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_query(self, query: str) -> List[float]:
        raise NotImplementedError


class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """OpenAI 兼容接口"""
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.model_name = model_name
        self._client = OpenAI(
            api_key=api_key,
            base_url=ensure_openai_base_url_has_v1(base_url),
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            response = self._client.embeddings.create(
                input=texts,
                model=self.model_name,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logging.error(f"OpenAI embed_documents failed: {e}")
            return [[] for _ in texts]

    def embed_query(self, query: str) -> List[float]:
        try:
            response = self._client.embeddings.create(
                input=query,
                model=self.model_name,
            )
            if response and response.data:
                return response.data[0].embedding
            return []
        except Exception as e:
            logging.error(f"OpenAI embed_query failed: {e}")
            return []


class AzureOpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """Azure OpenAI"""
    def __init__(self, api_key: str, base_url: str, model_name: str):
        match = re.match(
            r'https://(.+?)/openai/deployments/(.+?)/embeddings\?api-version=(.+)',
            base_url,
        )
        if match:
            azure_endpoint = f"https://{match.group(1)}"
            azure_deployment = match.group(2)
            api_version = match.group(3)
        else:
            raise ValueError("Invalid Azure OpenAI base_url format")

        self.model_name = model_name
        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            azure_deployment=azure_deployment,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            response = self._client.embeddings.create(
                input=texts,
                model=self.model_name,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logging.error(f"AzureOpenAI embed_documents failed: {e}")
            return [[] for _ in texts]

    def embed_query(self, query: str) -> List[float]:
        try:
            response = self._client.embeddings.create(
                input=query,
                model=self.model_name,
            )
            if response and response.data:
                return response.data[0].embedding
            return []
        except Exception as e:
            logging.error(f"AzureOpenAI embed_query failed: {e}")
            return []


class OllamaEmbeddingAdapter(BaseEmbeddingAdapter):
    """Ollama 本地模型（/api/embeddings 接口）"""
    def __init__(self, model_name: str, base_url: str):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_single(t) for t in texts]

    def embed_query(self, query: str) -> List[float]:
        return self._embed_single(query)

    def _embed_single(self, text: str) -> List[float]:
        url = self.base_url.rstrip("/")
        if "/api/embeddings" not in url:
            if "/api" in url:
                url = f"{url}/embeddings"
            else:
                if "/v1" in url:
                    url = url[:url.index("/v1")]
                url = f"{url}/api/embeddings"
        try:
            resp = requests.post(
                url,
                json={"model": self.model_name, "prompt": text},
                timeout=DEFAULT_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            result = resp.json()
            if "embedding" not in result:
                raise ValueError("No 'embedding' field in Ollama response")
            return result["embedding"]
        except Exception as e:
            logging.error(f"Ollama embedding error: {e}")
            return []


class MLStudioEmbeddingAdapter(BaseEmbeddingAdapter):
    """LM Studio（OpenAI 兼容 /v1/embeddings）"""
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.url = ensure_openai_base_url_has_v1(base_url)
        if not self.url.endswith('/embeddings'):
            self.url = f"{self.url}/embeddings"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.model_name = model_name

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            resp = requests.post(
                self.url,
                json={"input": texts, "model": self.model_name},
                headers=self.headers,
                timeout=DEFAULT_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [item.get("embedding", []) for item in data]
        except Exception as e:
            logging.error(f"LM Studio embed_documents failed: {e}")
            return [[] for _ in texts]

    def embed_query(self, query: str) -> List[float]:
        try:
            resp = requests.post(
                self.url,
                json={"input": query, "model": self.model_name},
                headers=self.headers,
                timeout=DEFAULT_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                return data[0].get("embedding", [])
            return []
        except Exception as e:
            logging.error(f"LM Studio embed_query failed: {e}")
            return []


class GeminiEmbeddingAdapter(BaseEmbeddingAdapter):
    """Google Gemini（保持原生 google-genai SDK）"""
    def __init__(self, api_key: str, model_name: str, base_url: str):
        self.api_key = api_key
        self.model_name = model_name
        self._client = genai.Client(api_key=self.api_key)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            response = self._client.models.embed_content(
                model=self.model_name,
                contents=texts,
            )
            return [emb.values for emb in response.embeddings]
        except Exception as e:
            logging.error(f"Gemini embed_documents failed: {e}")
            return [[] for _ in texts]

    def embed_query(self, query: str) -> List[float]:
        return self._embed_single(query)

    def _embed_single(self, text: str) -> List[float]:
        try:
            response = self._client.models.embed_content(
                model=self.model_name,
                contents=text,
            )
            if response and response.embeddings:
                return response.embeddings[0].values
            return []
        except Exception as e:
            logging.error(f"Gemini embed_query failed: {e}")
            return []


class LocalBGEAdapter(BaseEmbeddingAdapter):
    """本地 BGE 模型（sentence-transformers，无需 API 服务）"""
    def __init__(self, model_name_or_path: str, _unused_url: str = "", _unused_key: str = ""):
        """
        :param model_name_or_path: HuggingFace 模型名 或 本地路径
        """
        self.model_path = model_name_or_path
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer
        logging.info(f"正在加载本地 BGE 模型: {self.model_path}")
        try:
            self._model = SentenceTransformer(
                self.model_path,
                device="cpu",
                trust_remote_code=True,
            )
            logging.info(f"BGE 模型加载成功: {self.model_path}")
        except Exception as e:
            logging.error(f"BGE 模型加载失败: {e}")
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            self._load_model()
            embeddings = self._model.encode(texts, show_progress_bar=False)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logging.error(f"BGE embed_documents failed: {e}")
            return [[] for _ in texts]

    def embed_query(self, query: str) -> List[float]:
        try:
            self._load_model()
            emb = self._model.encode(query, show_progress_bar=False)
            return emb.tolist()
        except Exception as e:
            logging.error(f"BGE embed_query failed: {e}")
            return []


class SiliconFlowEmbeddingAdapter(BaseEmbeddingAdapter):
    """硅基流动"""
    def __init__(self, api_key: str, base_url: str, model_name: str):
        if not base_url.startswith(("http://", "https://")):
            base_url = "https://" + base_url
        self.url = base_url if base_url else "https://api.siliconflow.cn/v1/embeddings"
        self.model_name = model_name
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        results = []
        for text in texts:
            try:
                resp = requests.post(
                    self.url,
                    json={
                        "model": self.model_name,
                        "input": text,
                        "encoding_format": "float",
                    },
                    headers=self.headers,
                    timeout=DEFAULT_REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                results.append(data[0].get("embedding", []) if data else [])
            except Exception as e:
                logging.error(f"SiliconFlow embedding error: {e}")
                results.append([])
        return results

    def embed_query(self, query: str) -> List[float]:
        try:
            resp = requests.post(
                self.url,
                json={
                    "model": self.model_name,
                    "input": query,
                    "encoding_format": "float",
                },
                headers=self.headers,
                timeout=DEFAULT_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                return data[0].get("embedding", [])
            return []
        except Exception as e:
            logging.error(f"SiliconFlow embed_query failed: {e}")
            return []


def create_embedding_adapter(
    interface_format: str,
    api_key: str,
    base_url: str,
    model_name: str,
) -> BaseEmbeddingAdapter:
    """工厂函数"""
    fmt = interface_format.strip().lower()
    mapping = {
        "openai": OpenAIEmbeddingAdapter,
        "azure openai": AzureOpenAIEmbeddingAdapter,
        "ollama": OllamaEmbeddingAdapter,
        "ml studio": MLStudioEmbeddingAdapter,
        "gemini": GeminiEmbeddingAdapter,
        "siliconflow": SiliconFlowEmbeddingAdapter,
        "local bge": LocalBGEAdapter,
    }
    cls = mapping.get(fmt)
    if cls is None:
        raise ValueError(f"Unknown embedding interface_format: {interface_format}")

    if fmt == "ollama":
        return cls(model_name, base_url)
    elif fmt == "gemini":
        return cls(api_key, model_name, base_url)
    elif fmt == "local bge":
        return cls(model_name)
    return cls(api_key, base_url, model_name)
