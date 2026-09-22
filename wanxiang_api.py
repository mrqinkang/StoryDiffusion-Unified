# wanxiang_api.py
# -*- coding: utf-8 -*-
"""
阿里云百炼·万相 2.7 图像生成 API 封装
- 支持文生图、图生图、批量生成
- 支持标准 DashScope 地址和工作空间专用地址
"""

import os
import json
import time
import base64
import logging
from io import BytesIO
from typing import Optional, List
import requests
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WanxiangAPI")

# 默认的万相 API 地址（标准 DashScope 端点）
DEFAULT_BASE_URL = (
    "https://dashscope.aliyuncs.com"
    "/api/v1/services/aigc/multimodal-generation/generation"
)


class WanxiangAPI:
    """万相 2.7 图像生成 API 封装"""

    def __init__(
        self,
        api_key: str,
        model: str = "wan2.7-image-pro",
        base_url: Optional[str] = None,
    ):
        """
        :param api_key: 阿里云百炼 API Key
                        (sk-xxx 或 sk-ws-H.xxx 格式均可)
        :param model: 模型名 (wan2.7-image-pro / wan2.7-image)
        :param base_url: API 地址，默认使用标准 DashScope 地址
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or DEFAULT_BASE_URL

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            f"万相 API 初始化 | 模型: {model} | "
            f"地址: {self.base_url}"
        )

    # ------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------

    def text_to_image(
        self,
        prompt: str,
        size: str = "2K",
        seed: Optional[int] = None,
        n: int = 1,
        thinking_mode: bool = True,
        watermark: bool = False,
        negative_prompt: Optional[str] = None,
    ) -> List[str]:
        """
        文生图

        :param prompt: 图片描述（建议使用简洁的中文自然语言）
        :param size: 分辨率 (1K / 2K / 4K)
        :param seed: 随机种子
        :param n: 生成数量 (1-4)
        :param thinking_mode: 思考模式
        :param watermark: 水印
        :param negative_prompt: 负面提示词，描述不希望出现的内容
        :return: 图片 URL 列表
        """
        params = {"size": size, "n": n, "watermark": watermark}
        if thinking_mode:
            params["thinking_mode"] = True
        if seed is not None:
            params["seed"] = seed
        if negative_prompt:
            params["negative_prompt"] = negative_prompt

        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": params,
        }
        return self._call_api(payload)

    def image_to_image(
        self,
        prompt: str,
        ref_image: str,
        size: str = "2K",
        seed: Optional[int] = None,
        n: int = 1,
        thinking_mode: bool = True,
        watermark: bool = False,
        negative_prompt: Optional[str] = None,
    ) -> List[str]:
        """
        图生图：参考图片 + 文本生成新图

        :param prompt: 编辑描述（建议使用简洁的中文自然语言）
        :param ref_image: 参考图片路径 (本地路径 / URL)
        :param size: 分辨率
        :param seed: 随机种子
        :param n: 生成数量
        :param thinking_mode: 思考模式
        :param watermark: 水印
        :param negative_prompt: 负面提示词，描述不希望出现的内容
        :return: 图片 URL 列表
        """
        image_data = self._resolve_image(ref_image)

        params = {"size": size, "n": n, "watermark": watermark}
        if thinking_mode:
            params["thinking_mode"] = True
        if seed is not None:
            params["seed"] = seed
        if negative_prompt:
            params["negative_prompt"] = negative_prompt

        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"image": image_data},
                            {"text": prompt},
                        ],
                    }
                ]
            },
            "parameters": params,
        }
        return self._call_api(payload)

    # ------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------

    def _call_api(self, payload: dict, max_retries: int = 3) -> List[str]:
        """调用万相 API"""
        for attempt in range(max_retries):
            try:
                logger.debug(f"请求 payload (截断): model={payload['model']}")
                resp = requests.post(
                    self.base_url,
                    json=payload,
                    headers=self.headers,
                    timeout=180,
                )
                resp.raise_for_status()
                result = resp.json()

                image_urls = self._parse_response(result)
                if image_urls:
                    return image_urls

                logger.warning(
                    f"API 返回无图片数据 (尝试 {attempt + 1}/{max_retries})\n"
                    f"响应: {json.dumps(result, ensure_ascii=False)[:300]}"
                )
                if attempt < max_retries - 1:
                    time.sleep(2)

            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(3)
            except requests.exceptions.RequestException as e:
                logger.error(f"API 请求失败: {e}")
                if hasattr(e, "response") and e.response is not None:
                    logger.error(
                        f"Status: {e.response.status_code}, "
                        f"Body: {e.response.text[:500]}"
                    )
                if attempt < max_retries - 1:
                    time.sleep(3)
            except json.JSONDecodeError as e:
                logger.error(f"响应解析失败: {e}")
                break

        return []

    @staticmethod
    def _parse_response(result: dict) -> List[str]:
        """解析 API 响应，提取图片 URL"""
        try:
            output = result.get("output", {})
            choices = output.get("choices", [])
            urls = []
            for choice in choices:
                message = choice.get("message", {})
                content_items = message.get("content", [])
                for item in content_items:
                    if "image" in item:
                        urls.append(item["image"])
            return urls
        except Exception as e:
            logger.error(
                f"解析响应失败: {e}, "
                f"响应: {json.dumps(result, ensure_ascii=False)[:300]}"
            )
            return []

    @staticmethod
    def _resolve_image(image_path: str) -> str:
        """将本地图片或 URL 转换为 base64 data URI"""
        # 已经是 data URI，直接返回
        if image_path.startswith("data:"):
            return image_path

        if image_path.startswith(("http://", "https://")):
            return image_path

        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img_data = f.read()
            ext = os.path.splitext(image_path)[1].lower()
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".bmp": "image/bmp",
            }.get(ext, "image/jpeg")
            return f"data:{mime};base64,{base64.b64encode(img_data).decode()}"

        raise FileNotFoundError(f"参考图片不存在: {image_path}")

    @staticmethod
    def _download_image(url: str) -> Optional[Image.Image]:
        """从 URL 下载图片"""
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            logger.error(f"下载图片失败: {url[:50]}... 错误: {e}")
            return None
