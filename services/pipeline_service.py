# services/pipeline_service.py
"""流水线服务 - 小说→场景→漫画"""

import logging
from typing import List, Optional

from llm_adapters import create_llm_adapter
from services.comic_service import ComicService

logger = logging.getLogger("pipeline_service")


class PipelineService:
    """小说→漫画流水线服务"""

    @staticmethod
    def extract_scenes(
        chapter_text: str,
        llm_interface: str = "OpenAI",
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_model: str = "gpt-4",
        max_scenes: int = 6,
    ) -> dict:
        """
        用 LLM 从小说章节中提取关键场景并生成分镜描述
        返回: { scenes: [{title, description, prompt}], success: bool, message: str }
        """
        if not chapter_text or not llm_api_key:
            return {"success": False, "message": "缺少小说文本或 API Key", "scenes": []}

        try:
            adapter = create_llm_adapter(
                interface_format=llm_interface,
                base_url=llm_base_url,
                model_name=llm_model,
                api_key=llm_api_key,
                temperature=0.3,
                max_tokens=4096,
                timeout=120,
            )

            prompt = f"""你是一个专业的漫画分镜师。请从以下小说章节中提取关键场景，将其转化为漫画分镜描述。

要求：
1. 提取 {max_scenes} 个最有画面感的关键场景
2. 每个场景包含：标题、画面描述（适合AI图像生成的英文 prompt）
3. 描述要包含角色外貌、动作、场景、光影、构图
4. 保持角色一致性（发型、服装、体型在多个场景中一致）

小说章节内容：
---
{chapter_text[:8000]}
---

请严格按以下 JSON 格式输出（不要包含其他文字）：
{{
  "scenes": [
    {{
      "title": "场景标题",
      "description": "中文场景描述",
      "prompt": "English prompt for AI image generation, detailed visual description"
    }}
  ]
}}
"""

            response = adapter.invoke(prompt)
            if not response:
                return {"success": False, "message": "LLM 返回为空", "scenes": []}

            # 提取 JSON
            import json as j
            # 尝试找到 JSON 部分
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = j.loads(json_str)
                scenes = data.get("scenes", [])
                return {
                    "success": True,
                    "message": f"成功提取 {len(scenes)} 个场景",
                    "scenes": scenes[:max_scenes],
                }

            return {"success": False, "message": "无法解析 LLM 输出", "scenes": []}

        except Exception as e:
            logger.exception("场景提取失败")
            return {"success": False, "message": str(e)[:200], "scenes": []}

    @staticmethod
    def generate_comic_from_scenes(
        scenes: List[dict],
        api_key: str,
        model: str = "wan2.7-image-pro",
        style_name: str = "Japanese Anime",
        size: str = "2K",
        seed: int = -1,
        thinking_mode: bool = True,
        ref_image: Optional[str] = None,
        comic_layout: str = "Classic Comic Style",
        api_url: str = "",
    ) -> dict:
        """
        从提取的场景列表生成漫画
        """
        prompts = [s.get("prompt", s.get("description", "")) for s in scenes]
        titles = [s.get("title", f"场景 {i+1}") for i, s in enumerate(scenes)]

        if len(prompts) < 2:
            return {"success": False, "message": "至少需要 2 个场景"}

        comic_svc = ComicService()
        result = comic_svc.generate_comic(
            api_key=api_key,
            model=model,
            prompts=prompts,
            style_name=style_name,
            size=size,
            seed=seed,
            thinking_mode=thinking_mode,
            ref_image=ref_image,
            comic_layout=comic_layout,
            api_url=api_url,
        )

        if result["success"]:
            result["titles"] = titles
        return result
