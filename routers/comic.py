# routers/comic.py
"""漫画生成 API 路由"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.comic_service import ComicService

logger = logging.getLogger("router.comic")
router = APIRouter(prefix="/api/comic", tags=["漫画"])
comic_svc = ComicService()


class TestConnectionParams(BaseModel):
    api_key: str = Field("", description="万相 API Key")
    model: str = Field("wan2.7-image-pro", description="模型名称")
    api_url: str = Field("", description="API 地址")


class GenerateComicParams(BaseModel):
    api_key: str = Field("", description="万相 API Key")
    model: str = Field("wan2.7-image-pro")
    prompts: List[str] = Field(..., min_length=2, description="分镜描述列表")
    style_name: str = Field("Japanese Anime")
    size: str = Field("2K")
    seed: int = Field(-1)
    thinking_mode: bool = Field(True)
    ref_image: Optional[str] = Field(None)
    comic_layout: str = Field("Classic Comic Style")
    api_url: str = Field("")
    batch_size: int = Field(1, ge=1, le=6, description="分镜合并数：1=标准模式，>1=经济模式")


@router.post("/test")
async def test_connection(params: TestConnectionParams):
    """测试万相 API 连接"""
    if not params.api_key:
        raise HTTPException(status_code=422, detail="请填写 API Key")
    result = comic_svc.test_connection(params.api_key, params.model, params.api_url)
    return result


@router.post("/generate")
async def generate_comic(params: GenerateComicParams):
    """生成漫画"""
    if not params.api_key:
        raise HTTPException(status_code=422, detail="请填写 API Key")
    if len(params.prompts) < 2:
        raise HTTPException(status_code=422, detail="至少需要 2 个分镜描述")

    result = comic_svc.generate_comic(
        api_key=params.api_key,
        model=params.model,
        prompts=params.prompts,
        style_name=params.style_name,
        size=params.size,
        seed=params.seed,
        thinking_mode=params.thinking_mode,
        ref_image=params.ref_image,
        comic_layout=params.comic_layout,
        api_url=params.api_url,
        batch_size=params.batch_size,
    )
    return result


@router.get("/styles")
async def list_styles():
    """获取可用的风格列表"""
    return {"success": True, "styles": ComicService.get_styles()}


@router.get("/layouts")
async def list_layouts():
    """获取可用的排版列表"""
    return {"success": True, "layouts": ComicService.get_layouts()}


@router.get("/models")
async def list_models():
    """获取可用的模型列表"""
    return {"success": True, "models": ComicService.get_models()}
