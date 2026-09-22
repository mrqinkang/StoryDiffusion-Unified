# routers/xhs.py
"""小红书图文带货 API 路由"""

import json
import webbrowser
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.xhs_service import XHSService
from services.xhs_mcp_client import XHSMCPClient
from services.cookie_reader import (
    extract_xhs_cookies,
    save_cookies_to_xhs_mcp,
    verify_cookies,
)

logger = logging.getLogger("router.xhs")
router = APIRouter(prefix="/api/xhs", tags=["小红书带货"])
xhs_svc = XHSService()
xhs_mcp = XHSMCPClient()


class LLMConfig(BaseModel):
    llm_interface: str = Field("OpenAI")
    llm_api_key: str = Field("")
    llm_base_url: str = Field("")
    llm_model: str = Field("gpt-4o")


class WanxiangConfig(BaseModel):
    api_key: str = Field("")
    model: str = Field("wan2.7-image-pro")
    api_url: str = Field("")
    style_name: str = Field("Japanese Anime")
    size: str = Field("2K")
    seed: int = Field(-1)
    thinking_mode: bool = Field(True)
    ref_image: Optional[str] = Field(None)
    comic_layout: str = Field("Classic Comic Style")
    batch_size: int = Field(3, ge=1, le=6)


class AnalyzeProductParams(BaseModel):
    image_data_uri: str = Field(..., description="商品图片 base64 data URI")
    llm: LLMConfig = Field(default_factory=LLMConfig)


class AnalyzeProductTextParams(BaseModel):
    product_description: str = Field(..., description="商品文字描述")
    llm: LLMConfig = Field(default_factory=LLMConfig)


class GenerateContentParams(BaseModel):
    product_info: dict = Field(..., description="商品分析结果")
    llm: LLMConfig = Field(default_factory=LLMConfig)


class GenerateComicParams(BaseModel):
    scenes: List[dict] = Field(..., description="场景分镜列表")
    wanxiang: WanxiangConfig = Field(default_factory=WanxiangConfig)


class PublishParams(BaseModel):
    title: str = Field("", description="标题")
    content: str = Field("", description="正文")
    images: List[str] = Field(default_factory=list, description="图片 base64 列表")
    tags: List[str] = Field(default_factory=list, description="标签")
    headless: bool = Field(False, description="是否无头模式")


@router.post("/analyze")
async def analyze_product(params: AnalyzeProductParams):
    """分析商品原型图（多模态，需图片）"""
    if not params.image_data_uri:
        raise HTTPException(status_code=400, detail="请上传商品图片")
    if not params.llm.llm_api_key:
        raise HTTPException(status_code=400, detail="请填写 LLM API Key")

    result = xhs_svc.analyze_product(
        image_data_uri=params.image_data_uri,
        llm_interface=params.llm.llm_interface,
        llm_api_key=params.llm.llm_api_key,
        llm_base_url=params.llm.llm_base_url,
        llm_model=params.llm.llm_model,
    )
    return result


@router.post("/analyze-text")
async def analyze_product_text(params: AnalyzeProductTextParams):
    """分析商品信息（通过文字描述，适合不支持多模态的 LLM）"""
    if not params.product_description.strip():
        raise HTTPException(status_code=400, detail="请填写商品描述")
    if not params.llm.llm_api_key:
        raise HTTPException(status_code=400, detail="请填写 LLM API Key")

    result = xhs_svc.analyze_product_text(
        product_description=params.product_description,
        llm_interface=params.llm.llm_interface,
        llm_api_key=params.llm.llm_api_key,
        llm_base_url=params.llm.llm_base_url,
        llm_model=params.llm.llm_model,
    )
    return result


@router.post("/generate-content")
async def generate_content(params: GenerateContentParams):
    """生成小红书带货文案 + 漫画分镜"""
    if not params.llm.llm_api_key:
        raise HTTPException(status_code=400, detail="请填写 LLM API Key")
    if not params.product_info:
        raise HTTPException(status_code=400, detail="请先分析商品")

    result = xhs_svc.generate_content(
        product_info=params.product_info,
        llm_interface=params.llm.llm_interface,
        llm_api_key=params.llm.llm_api_key,
        llm_base_url=params.llm.llm_base_url,
        llm_model=params.llm.llm_model,
    )
    return result


@router.post("/generate-comic")
async def generate_comic(params: GenerateComicParams):
    """从场景分镜生成带货漫画"""
    if not params.wanxiang.api_key:
        raise HTTPException(status_code=400, detail="请填写万相 API Key")
    if not params.scenes or len(params.scenes) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 个场景")

    result = xhs_svc.generate_comic(
        scenes=params.scenes,
        api_key=params.wanxiang.api_key,
        model=params.wanxiang.model,
        style_name=params.wanxiang.style_name,
        size=params.wanxiang.size,
        seed=params.wanxiang.seed,
        thinking_mode=params.wanxiang.thinking_mode,
        ref_image=params.wanxiang.ref_image,
        comic_layout=params.wanxiang.comic_layout,
        api_url=params.wanxiang.api_url,
        batch_size=params.wanxiang.batch_size,
    )
    return result


@router.get("/publish/check")
async def check_publish():
    """检查发布功能状态"""
    logged_in = xhs_mcp.is_logged_in_cached()
    return {
        "success": True,
        "mcp_available": xhs_mcp.is_available(),
        "logged_in": logged_in,
        "hint": "发布前需要先登录小红书账号，点击「登录小红书」按钮扫码即可",
    }


@router.post("/publish/login")
async def publish_login():
    """登录小红书 - 在用户当前浏览器中打开小红书"""
    if not xhs_mcp.is_available():
        raise HTTPException(status_code=400, detail="MCP 未就绪")

    # 在用户默认浏览器中打开小红书登录页
    login_urls = [
        "https://creator.xiaohongshu.com/login",
        "https://www.xiaohongshu.com/login",
    ]
    opened = False
    for url in login_urls:
        try:
            webbrowser.open(url)
            opened = True
            break
        except Exception:
            continue

    return {
        "success": True,
        "opened_browser": opened,
        "message": "已在浏览器中打开小红书登录页，请登录后回到这里提取 Cookies",
        "login_url": login_urls[0],
        "hint": "方式一：点击「一键提取」自动提取浏览器 Cookies\n方式二：按 F12 → Application → Cookies → 右键导出 → 粘贴到文本框",
    }


@router.post("/publish/cookies")
async def save_cookies(cookies: list[dict]):
    """保存 cookies 到 xhs-mcp（接收从浏览器导出的 cookies JSON）"""
    if not cookies:
        raise HTTPException(status_code=400, detail="cookies 列表为空")

    saved = save_cookies_to_xhs_mcp(cookies)
    if not saved:
        raise HTTPException(status_code=500, detail="保存 cookies 失败")

    verify = verify_cookies(cookies)
    if verify["valid"]:
        return {
            "success": True,
            "message": verify["message"],
            "count": verify["count"],
            "has_session": True,
        }
    else:
        return {
            "success": True,
            "message": f"Ccookies 已保存（{verify['count']}个），但缺少关键 session cookie，可能未登录",
            "count": verify["count"],
            "has_session": False,
            "hint": "请确认已在浏览器中登录小红书账号后重新提取",
        }


@router.get("/publish/extract-cookies")
async def extract_cookies():
    """尝试从本机浏览器自动提取小红书 cookies"""
    cookies = extract_xhs_cookies()
    if not cookies:
        return {
            "success": False,
            "count": 0,
            "message": "未能从浏览器提取到小红书 cookies。请确保：\n"
                       "1. 已在浏览器中登录小红书\n"
                       "2. 暂时关闭浏览器重试（避免数据库锁定）",
        }

    saved = save_cookies_to_xhs_mcp(cookies)
    verify = verify_cookies(cookies)

    return {
        "success": saved,
        "count": len(cookies),
        "has_session": verify.get("has_session", False),
        "session_keys": verify.get("session_keys", []),
        "message": verify.get("message", f"已提取 {len(cookies)} 个 cookies"),
    }


@router.post("/publish/check-login")
async def publish_check_login():
    """检查登录状态"""
    if not xhs_mcp.is_available():
        return {"success": False, "logged_in": False, "status": "mcp_not_available"}

    result = await xhs_mcp.check_login()
    return result


@router.post("/publish")
async def publish(params: PublishParams):
    """发布到小红书（通过 xhs-mcp）"""
    if not params.images:
        raise HTTPException(status_code=400, detail="没有可发布的图片")
    if not xhs_mcp.is_available():
        raise HTTPException(
            status_code=400,
            detail="MCP 未就绪。请运行: pip install mcp",
        )

    result = await xhs_mcp.publish(
        title=params.title,
        content=params.content,
        image_base64_list=params.images,
        tags=params.tags,
    )
    return result
