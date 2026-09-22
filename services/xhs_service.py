# services/xhs_service.py
"""小红书图文带货服务 - 商品分析 → 文案生成 → 漫画分镜"""

import json
import logging
from typing import Optional

from llm_adapters import create_llm_adapter
from services.comic_service import ComicService

logger = logging.getLogger("xhs_service")

# 商品信息 JSON Schema（图片分析和文字分析共用）
PRODUCT_SCHEMA = """{
  "name": "商品名称",
  "category": "商品类别",
  "features": ["核心卖点1", "核心卖点2"],
  "usage_scenarios": ["使用场景1", "使用场景2", "使用场景3"],
  "style": "设计风格（如 ins风、极简、可爱、专业、复古等）",
  "colors": ["主色1", "主色2"],
  "target_audience": "目标人群描述",
  "keywords": ["关键词1", "关键词2", "关键词3"]
}"""


def _parse_json_response(resp: str) -> Optional[dict]:
    """从 LLM 返回文本中提取并解析 JSON"""
    start = resp.find("{")
    end = resp.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(resp[start:end])
    return None


class XHSService:
    """小红书带货一站式服务"""

    @staticmethod
    def analyze_product(
        image_data_uri: str,
        llm_interface: str = "OpenAI",
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_model: str = "gpt-4o",
    ) -> dict:
        """用多模态 LLM 分析商品原型图"""
        if not llm_api_key:
            return {"success": False, "message": "请填写 LLM API Key"}

        prompt = f"""请分析这张商品图片，返回以下 JSON 格式的信息（仅返回 JSON，不要包含其他文字）：

{PRODUCT_SCHEMA}"""

        try:
            adapter = create_llm_adapter(
                interface_format=llm_interface,
                base_url=llm_base_url,
                model_name=llm_model,
                api_key=llm_api_key,
                temperature=0.3,
                max_tokens=2048,
                timeout=120,
            )
            resp = adapter.invoke_multimodal(prompt, image_data_uri)
            if not resp:
                return {"success": False, "message": "LLM 返回为空", "product": {}}

            product = _parse_json_response(resp)
            if product:
                return {"success": True, "message": "商品分析成功", "product": product}
            return {"success": False, "message": "无法解析 LLM 输出", "product": {}}

        except Exception as e:
            logger.exception("商品分析失败")
            return {"success": False, "message": str(e)[:200], "product": {}}

    @staticmethod
    def analyze_product_text(
        product_description: str,
        llm_interface: str = "OpenAI",
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_model: str = "deepseek-v4-flash",
    ) -> dict:
        """通过文字描述分析商品（适合不支持多模态的 LLM）"""
        if not llm_api_key:
            return {"success": False, "message": "请填写 LLM API Key"}
        if not product_description.strip():
            return {"success": False, "message": "请填写商品描述"}

        prompt = f"""你是一个商品分析师。请根据以下商品描述，提取结构化信息。

商品描述：
{product_description.strip()[:3000]}

请严格按以下 JSON 格式输出（仅返回 JSON，不要包含其他文字）：

{PRODUCT_SCHEMA}"""

        try:
            adapter = create_llm_adapter(
                interface_format=llm_interface,
                base_url=llm_base_url,
                model_name=llm_model,
                api_key=llm_api_key,
                temperature=0.3,
                max_tokens=2048,
                timeout=120,
            )
            resp = adapter.invoke(prompt)
            if not resp:
                # invoke 可能因配置错误返回空（adapter 内部吞掉了异常）
                return {
                    "success": False,
                    "message": "LLM 返回为空，请检查：① API Key 是否正确 ② 模型名是否正确 ③ API 地址是否正确",
                    "product": {},
                }

            product = _parse_json_response(resp)
            if product:
                return {"success": True, "message": "商品分析成功", "product": product}
            return {"success": False, "message": "无法解析 LLM 输出", "product": {}}

        except Exception as e:
            logger.exception("商品文字分析失败")
            return {"success": False, "message": str(e)[:200], "product": {}}

    @staticmethod
    def _build_product_focus(product_info: dict) -> str:
        """构建商品焦点描述，用于强化每个场景的 prompt"""
        parts = []
        name = product_info.get("name", "")
        colors = product_info.get("colors", [])
        style = product_info.get("style", "")
        features = product_info.get("features", [])

        if name:
            parts.append(f"the product: {name}")
        if colors:
            parts.append(f"color scheme: {'/'.join(colors[:3])}")
        if style:
            parts.append(f"design style: {style}")
        if features:
            parts.append(f"key features: {'/'.join(features[:3])}")

        return ", ".join(parts) if parts else ""

    @staticmethod
    def generate_content(
        product_info: dict,
        llm_interface: str = "OpenAI",
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_model: str = "deepseek-v4-flash",
    ) -> dict:
        """根据商品信息生成小红书种草文案 + 漫画分镜"""
        if not llm_api_key:
            return {"success": False, "message": "请填写 LLM API Key"}

        product_json = json.dumps(product_info, ensure_ascii=False, indent=2)
        focus = XHSService._build_product_focus(product_info)

        prompt = f"""你是小红书带货文案专家 + 漫画分镜师。请根据以下商品信息，生成一套完整的种草内容。

商品信息：
{product_json}

要求：
1. 标题：20字以内，吸引眼球，带 emoji
2. 正文：300-500字，小红书种草风格，口语化，带 emoji，讲述使用体验故事
3. 标签：4-6个，如 #好物分享 #日常必备
4. 漫画分镜：2个高质量场景，左右各一，最后合并为一张对比/组合图

每个场景的 prompt 要求（重要）：
- **用中文自然描述场景画面**，控制在 60-100 个汉字
- **画面必须饱满充实**，元素丰富，忌空洞背景
- 包括：场景环境 + 人物动作 + 商品特写 + 画面构图说明
- 商品必须在场景中明显可见且居中/突出
- 2 个场景中商品外观保持一致
- 示例：✅ "年轻女性在明亮简约的厨房中，右手拿着白色保温杯靠近唇边，左手扶着料理台，身后橱柜台面上有水果和绿植，商品居中特写，画面饱满"
- 使用万相官网风格：直接描述画面，不要英文，不要艺术风格关键词

场景组合建议：
1. **商品展示**：商品 C 位呈现，展示外观/材质/设计特点，背景简洁突出商品
2. **使用场景**：人物正在使用商品，展示功能/效果，环境丰富自然

请严格按以下 JSON 格式输出（仅返回 JSON，不要包含其他文字）：
{{
  "title": "标题",
  "content": "正文内容",
  "tags": ["#tag1", "#tag2"],
  "scenes": [
    {{"title": "场景1标题", "description": "中文描述", "prompt": "中文画面描述，60-100字，画面饱满充实，商品突出"}},
    {{"title": "场景2标题", "description": "中文描述", "prompt": "中文画面描述，60-100字，画面饱满充实，商品突出"}}
  ]
}}"""

        try:
            adapter = create_llm_adapter(
                interface_format=llm_interface,
                base_url=llm_base_url,
                model_name=llm_model,
                api_key=llm_api_key,
                temperature=0.7,
                max_tokens=4096,
                timeout=180,
            )
            resp = adapter.invoke(prompt)
            if not resp:
                return {"success": False, "message": "LLM 返回为空"}

            # 解析 JSON
            start = resp.find("{")
            end = resp.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(resp[start:end])
                scenes = data.get("scenes", [])

                # 场景 prompt 已由 LLM 按模板要求包含商品细节，无需额外处理
                return {
                    "success": True,
                    "message": f"生成成功！{len(scenes)} 个场景",
                    "title": data.get("title", ""),
                    "content": data.get("content", ""),
                    "tags": data.get("tags", []),
                    "scenes": scenes,
                }
            return {"success": False, "message": "无法解析 LLM 输出"}

        except Exception as e:
            logger.exception("内容生成失败")
            return {"success": False, "message": str(e)[:200]}

    @staticmethod
    def generate_comic(
        scenes: list,
        api_key: str,
        model: str = "wan2.7-image-pro",
        style_name: str = "Japanese Anime",
        size: str = "2K",
        seed: int = -1,
        thinking_mode: bool = True,
        ref_image: Optional[str] = None,
        comic_layout: str = "双图拼接（推荐）",
        api_url: str = "",
        batch_size: int = 1,
    ) -> dict:
        """从带货分镜生成漫画"""
        if not scenes or len(scenes) < 2:
            return {"success": False, "message": "至少需要 2 个场景"}

        prompts = [s.get("prompt", s.get("description", "")) for s in scenes]
        titles = [s.get("title", f"场景 {i+1}") for i, s in enumerate(scenes)]

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
            batch_size=batch_size,
        )

        if result.get("success"):
            result["titles"] = titles
        return result
