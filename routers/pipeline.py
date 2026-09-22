# routers/pipeline.py
"""流水线 API 路由 - 小说→漫画"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.pipeline_service import PipelineService

logger = logging.getLogger("router.pipeline")
router = APIRouter(prefix="/api/pipeline", tags=["流水线"])


class ExtractScenesParams(BaseModel):
    chapter_text: str = Field("", description="小说章节文本")
    llm_interface: str = Field("OpenAI")
    llm_api_key: str = Field("")
    llm_base_url: str = Field("")
    llm_model: str = Field("deepseek-v4-flash")
    max_scenes: int = Field(6, ge=2, le=12)


class GenerateFromScenesParams(BaseModel):
    scenes: List[dict] = Field(..., description="场景列表")
    api_key: str = Field("", description="万相 API Key")
    model: str = Field("wan2.7-image-pro")
    style_name: str = Field("Japanese Anime")
    size: str = Field("2K")
    seed: int = Field(-1)
    thinking_mode: bool = Field(True)
    ref_image: Optional[str] = Field(None)
    comic_layout: str = Field("Classic Comic Style")
    api_url: str = Field("")


@router.post("/extract")
async def extract_scenes(params: ExtractScenesParams):
    """从小说章节提取漫画分镜场景"""
    if not params.chapter_text:
        raise HTTPException(status_code=422, detail="请提供小说文本")
    if not params.llm_api_key:
        raise HTTPException(status_code=422, detail="请填写 LLM API Key")

    result = PipelineService.extract_scenes(
        chapter_text=params.chapter_text,
        llm_interface=params.llm_interface,
        llm_api_key=params.llm_api_key,
        llm_base_url=params.llm_base_url,
        llm_model=params.llm_model,
        max_scenes=params.max_scenes,
    )
    return result


@router.post("/generate")
async def generate_from_scenes(params: GenerateFromScenesParams):
    """从提取的场景列表生成漫画"""
    if not params.api_key:
        raise HTTPException(status_code=422, detail="请填写万相 API Key")
    if not params.scenes or len(params.scenes) < 2:
        raise HTTPException(status_code=422, detail="至少需要 2 个场景")

    result = PipelineService.generate_comic_from_scenes(
        scenes=params.scenes,
        api_key=params.api_key,
        model=params.model,
        style_name=params.style_name,
        size=params.size,
        seed=params.seed,
        thinking_mode=params.thinking_mode,
        ref_image=params.ref_image,
        comic_layout=params.comic_layout,
        api_url=params.api_url,
    )
    return result
