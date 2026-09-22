# llm_adapters.py
# -*- coding: utf-8 -*-
"""
LLM 适配器工厂 - 统一接口，支持多种后端
纯原生 SDK，零 langchain/pydantic v1 依赖
"""

import re
import json
import logging
from typing import Optional, Iterator

from openai import OpenAI, AzureOpenAI
from google import genai
from google.genai import types
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference.models import SystemMessage, UserMessage


def check_base_url(url: str) -> str:
    """规范化 base_url（处理 /v1 后缀规则）"""
    url = url.strip()
    if not url:
        return url
    if url.endswith('#'):
        return url.rstrip('#')
    if not re.search(r'/v\d+$', url):
        if '/v1' not in url:
            url = url.rstrip('/') + '/v1'
    return url


class BaseLLMAdapter:
    """统一的 LLM 接口基类"""
    def invoke(self, prompt: str) -> str:
        raise NotImplementedError

    def stream_invoke(self, prompt: str) -> Iterator[str]:
        """流式调用，逐个返回文本块"""
        raise NotImplementedError

    def invoke_multimodal(self, text: str, image_data_uri: str) -> str:
        """多模态调用（文本+图片），默认回退到仅文本"""
        logger = logging.getLogger(__name__)
        logger.warning(f"{type(self).__name__} 不支持多模态，回退到文本模式")
        return self.invoke(text)


class OpenAIAdapter(BaseLLMAdapter):
    """OpenAI / 兼容接口（DeepSeek、百炼等）"""
    def __init__(
        self, api_key: str, base_url: str, model_name: str,
        max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600,
    ):
        self.api_key = api_key
        self.base_url = check_base_url(base_url)
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            if response and response.choices:
                return response.choices[0].message.content or ""
            return ""
        except Exception as e:
            logging.error(f"OpenAIAdapter invoke failed: {e}")
            return ""

    def invoke_multimodal(self, text: str, image_data_uri: str) -> str:
        """多模态：文本 + 图片（支持 data URI 格式）"""
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": image_data_uri}},
                    ]
                }],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            if response and response.choices:
                return response.choices[0].message.content or ""
            return ""
        except Exception as e:
            logging.error(f"OpenAIAdapter invoke_multimodal failed: {e}")
            return ""

    def stream_invoke(self, prompt: str) -> Iterator[str]:
        """流式调用 OpenAI 兼容接口"""
        try:
            stream = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logging.error(f"OpenAIAdapter stream_invoke failed: {e}")
            yield f"\n【错误】{e}"


class DeepSeekAdapter(OpenAIAdapter):
    """DeepSeek（与 OpenAI 接口完全兼容，直接复用）"""
    pass


class OllamaAdapter(OpenAIAdapter):
    """Ollama 本地模型（OpenAI 兼容接口）"""
    def __init__(
        self, api_key: str, base_url: str, model_name: str,
        max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600,
    ):
        if not api_key:
            api_key = "ollama"
        super().__init__(api_key, base_url, model_name, max_tokens, temperature, timeout)


class MLStudioAdapter(OpenAIAdapter):
    """LM Studio（OpenAI 兼容接口）"""
    pass


class AzureOpenAIAdapter(BaseLLMAdapter):
    """Azure OpenAI"""
    def __init__(
        self, api_key: str, base_url: str, model_name: str,
        max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature

        match = re.match(
            r'https://(.+?)/openai/deployments/(.+?)/chat/completions\?api-version=(.+)',
            base_url
        )
        if match:
            azure_endpoint = f"https://{match.group(1)}"
            azure_deployment = match.group(2)
            api_version = match.group(3)
        else:
            raise ValueError("Invalid Azure OpenAI base_url format")

        self._client = AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            azure_deployment=azure_deployment,
            timeout=timeout,
        )

    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            if response and response.choices:
                return response.choices[0].message.content or ""
            return ""
        except Exception as e:
            logging.error(f"AzureOpenAIAdapter invoke failed: {e}")
            return ""


class GeminiAdapter(BaseLLMAdapter):
    """Google Gemini 接口（支持自定义 endpoint）"""
    def __init__(
        self, api_key: str, base_url: str, model_name: str,
        max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature

        # 构建 Client 参数
        client_kwargs = {"api_key": self.api_key}

        # 如果用户提供了自定义 API 地址，通过 http_options 传入
        if base_url and base_url != "https://generativelanguage.googleapis.com/v1beta":
            # 去掉末尾的 /models 如果存在
            url = base_url.rstrip("/")
            if url.endswith("/models"):
                url = url[:-7]
            if url.endswith("/v1beta"):
                url = url[:-7]
            client_kwargs["http_options"] = {"base_url": url}
            logging.info(f"Gemini 使用自定义 endpoint: {url}")

        self._client = genai.Client(**client_kwargs)

        # 模型名兼容：google-genai SDK 期望 "models/xxx" 或 "gemini-xxx"
        if not self.model_name.startswith("models/") and not self.model_name.startswith("gemini-"):
            self.model_name = f"models/{self.model_name}"

    def invoke(self, prompt: str) -> str:
        try:
            config = types.GenerateContentConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            text = response.text
            return text if text else ""
        except (ValueError, AttributeError) as e:
            logging.warning(f"Gemini response blocked or empty: {e}")
            return ""
        except Exception as e:
            logging.error(f"GeminiAdapter invoke failed: {e}")
            return ""

    def invoke_multimodal(self, text: str, image_data_uri: str) -> str:
        """Gemini 多模态：文本 + 图片"""
        import base64 as b64mod
        try:
            # 从 data URI 提取 mime type 和 base64 数据
            # data:image/png;base64,iVBOR...
            if ";" in image_data_uri and image_data_uri.startswith("data:"):
                header, b64data = image_data_uri.split(";base64,", 1)
                mime_type = header.split(":")[1] if ":" in header else "image/png"
            else:
                b64data = image_data_uri
                mime_type = "image/png"

            image_bytes = b64mod.b64decode(b64data)
            image = types.Image(image_bytes=image_bytes, mime_type=mime_type)

            config = types.GenerateContentConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[text, image],
                config=config,
            )
            result = response.text
            return result if result else ""
        except Exception as e:
            logging.error(f"GeminiAdapter invoke_multimodal failed: {e}")
            return ""

    def stream_invoke(self, prompt: str) -> Iterator[str]:
        """流式调用 Gemini"""
        try:
            config = types.GenerateContentConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            response = self._client.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logging.error(f"GeminiAdapter stream_invoke failed: {e}")
            yield f"\n【错误】{e}"


class AzureAIAdapter(BaseLLMAdapter):
    """Azure AI Inference（保持不变，已用原生 azure-ai-inference）"""
    def __init__(
        self, api_key: str, base_url: str, model_name: str,
        max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600,
    ):
        match = re.match(
            r'https://(.+?)\.services\.ai\.azure\.com(?:/models)?(?:/chat/completions)?(?:\?api-version=(.+))?',
            base_url,
        )
        if match:
            endpoint = f"https://{match.group(1)}.services.ai.azure.com/models"
            api_version = match.group(2) if match.group(2) else "2024-05-01-preview"
        else:
            raise ValueError("Invalid Azure AI base_url format")

        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature

        self._client = ChatCompletionsClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key),
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=timeout,
        )

    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.complete(
                messages=[
                    SystemMessage("You are a helpful assistant."),
                    UserMessage(prompt),
                ]
            )
            if response and response.choices:
                return response.choices[0].message.content or ""
            return ""
        except Exception as e:
            logging.error(f"AzureAIAdapter invoke failed: {e}")
            return ""


class VolcanoEngineAIAdapter(BaseLLMAdapter):
    """火山引擎（已用原生 openai SDK）"""
    def __init__(
        self, api_key: str, base_url: str, model_name: str,
        max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600,
    ):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=timeout)

    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是DeepSeek，是一个 AI 人工智能助手"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            if response and response.choices:
                return response.choices[0].message.content or ""
            return ""
        except Exception as e:
            logging.error(f"VolcanoEngineAdapter invoke failed: {e}")
            return ""


class SiliconFlowAdapter(BaseLLMAdapter):
    """硅基流动（已用原生 openai SDK）"""
    def __init__(
        self, api_key: str, base_url: str, model_name: str,
        max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600,
    ):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=timeout)

    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是DeepSeek，是一个 AI 人工智能助手"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            if response and response.choices:
                return response.choices[0].message.content or ""
            return ""
        except Exception as e:
            logging.error(f"SiliconFlowAdapter invoke failed: {e}")
            return ""


class GrokAdapter(BaseLLMAdapter):
    """xAI Grok（已用原生 openai SDK）"""
    def __init__(
        self, api_key: str, base_url: str, model_name: str,
        max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600,
    ):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=timeout)

    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are Grok, created by xAI."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            if response and response.choices:
                return response.choices[0].message.content or ""
            return ""
        except Exception as e:
            logging.error(f"GrokAdapter invoke failed: {e}")
            return ""


def create_llm_adapter(
    interface_format: str,
    base_url: str,
    model_name: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> BaseLLMAdapter:
    """工厂函数：根据 interface_format 返回对应适配器"""
    fmt = interface_format.strip().lower()
    mapping = {
        "openai": OpenAIAdapter,
        "deepseek": DeepSeekAdapter,
        "azure openai": AzureOpenAIAdapter,
        "azure ai": AzureAIAdapter,
        "ollama": OllamaAdapter,
        "ml studio": MLStudioAdapter,
        "gemini": GeminiAdapter,
        "阿里云百炼": OpenAIAdapter,
        "火山引擎": VolcanoEngineAIAdapter,
        "硅基流动": SiliconFlowAdapter,
        "grok": GrokAdapter,
    }
    cls = mapping.get(fmt)
    if cls is None:
        raise ValueError(f"Unknown interface_format: {interface_format}")
    return cls(api_key, base_url, model_name, max_tokens, temperature, timeout)
