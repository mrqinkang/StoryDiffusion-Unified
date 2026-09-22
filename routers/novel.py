# routers/novel.py
"""小说生成 API 路由"""

import os
import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.novel_service import NovelService, NOVEL_TEMPLATES, DRAFTS_DIR
from database import init_db, create_template, get_template, update_template
from database import list_templates as db_list_templates
from database import delete_template as db_delete_template
from database import create_chat, list_chats, get_chat, delete_chat as db_delete_chat

logger = logging.getLogger("router.novel")
router = APIRouter(prefix="/api/novel", tags=["小说"])

# 启动时初始化数据库
init_db()


class NovelGenerateParams(BaseModel):
    topic: str = Field("", description="小说主题")
    genre: str = Field("", description="小说类型/风格")
    num_chapters: int = Field(5, ge=1, le=200, description="章节数")
    word_number: int = Field(2000, ge=500, le=50000, description="每章字数")
    user_guidance: str = Field("", description="用户指导")
    characters_involved: str = Field("", description="涉及角色")
    key_items: str = Field("", description="关键道具")
    scene_location: str = Field("", description="场景地点")
    time_constraint: str = Field("", description="时间限制")
    language_style: str = Field("", description="语言风格：口语化/书面语/古风/默认")
    emotional_tone: str = Field("", description="情感基调：热血/悲情/轻松/悬疑/默认")
    content_taboos: str = Field("", description="内容禁忌（避免出现的元素）")
    llm_interface: str = Field("OpenAI", description="LLM 接口格式")
    llm_api_key: str = Field("", description="LLM API Key")
    llm_base_url: str = Field("", description="LLM API 地址")
    llm_model: str = Field("deepseek-v4-flash", description="LLM 模型名")
    llm_temperature: float = Field(0.7, ge=0, le=2)
    llm_max_tokens: int = Field(4096, ge=256, le=65536)
    llm_timeout: int = Field(600)
    embedding_interface: str = Field("OpenAI")
    embedding_api_key: str = Field("")
    embedding_base_url: str = Field("")
    embedding_model: str = Field("text-embedding-ada-002")
    output_dir: Optional[str] = Field(None, description="输出目录")
    continuation_path: Optional[str] = Field(None, description="续写模式：已有小说目录路径")


class NovelQueryParams(BaseModel):
    path: str = Field("", description="小说目录路径")


class NovelContinueParams(BaseModel):
    novel_path: str = Field("", description="已有小说目录路径")
    num_chapters: int = Field(3, ge=1, le=100, description="续写章节数")
    insert_after: int = Field(-1, description="插入位置（-1=追加末尾，0=开头，N=在第N章之后）")
    context_chapters: list = Field(default_factory=list, description="参考章节号列表（空=全部）")
    user_guidance: str = Field("", description="续写方向指导（可选）")
    language_style: str = Field("", desc="语言风格")
    emotional_tone: str = Field("", desc="情感基调")
    content_taboos: str = Field("", desc="内容禁忌")
    llm_interface: str = Field("OpenAI")
    llm_api_key: str = Field("")
    llm_base_url: str = Field("")
    llm_model: str = Field("deepseek-v4-flash")
    llm_temperature: float = Field(0.7, ge=0, le=2)
    llm_max_tokens: int = Field(4096, ge=256, le=65536)
    llm_timeout: int = Field(600)
    embedding_interface: str = Field("OpenAI")
    embedding_api_key: str = Field("")
    embedding_base_url: str = Field("")
    embedding_model: str = Field("text-embedding-ada-002")


class GuidedChatParams(BaseModel):
    messages: list = Field(default_factory=list, description="对话历史 [{'role':'user'/'assistant','content':'...'}]")
    llm_interface: str = Field("OpenAI")
    llm_api_key: str = Field("")
    llm_base_url: str = Field("")
    llm_model: str = Field("deepseek-v4-flash")
    llm_temperature: float = Field(0.7, ge=0, le=2)
    llm_max_tokens: int = Field(4096, ge=256, le=65536)


class SaveTemplateParams(BaseModel):
    name: str = Field("未命名模板", description="模板名称")
    params: dict = Field(default_factory=dict, description="小说设置参数")


class DeleteTemplateParams(BaseModel):
    template_id: str = Field("", description="模板 ID")


class UpdateTemplateParams(BaseModel):
    template_id: str = Field("", description="要更新的模板 ID")
    name: str = Field("未命名模板", description="新模板名称")
    params: dict = Field(default_factory=dict, description="小说设置参数")


class SaveChatParams(BaseModel):
    name: str = Field("未命名对话", description="对话名称")
    messages: list = Field(default_factory=list, description="对话消息列表")


class DeleteChatParams(BaseModel):
    chat_id: str = Field("", description="对话 ID")


GUIDED_SYSTEM_PROMPT = """你是小说创作助手「灵感」。你的任务是通过对话了解用户需求，逐步收集信息，最后生成完整的小说大纲。

## 对话规则
- 每次只问 **一个问题**，等用户回答后再问下一个
- 问题要友好、有引导性，给出示例选项
- 不要一次问多个问题

## 需要收集的信息（按顺序）
1. 小说类型（玄幻/科幻/悬疑/言情/都市/历史等）
2. 核心主题或故事梗概（一句话）
3. 主角设定（性格、身份、特点）
4. 世界观/时代背景
5. 篇幅（短篇3-5章 / 中篇8-15章 / 长篇20+章）
6. 每章大致字数
7. 其他特殊要求

## 信息收齐后的输出格式
当用户提供了足够的信息后，请生成完整大纲，并用以下格式输出（注意：**必须**包含【大纲开始】标记）：

【大纲开始】
标题：<小说标题>

类型：<类型>

核心主题：<一句话梗概>

角色设定：
- 主角：<姓名，性格，背景>
- 其他角色：<角色名，关系>

世界观/背景：<设定描述>

章节规划：
第1章 <章节名>：<概要>
第2章 <章节名>：<概要>
...

写作建议：<特别提示>
【大纲结束】

在输出大纲之前，继续提问收集信息。只有在信息足够时才输出大纲。"""


@router.post("/generate")
async def generate_novel(params: NovelGenerateParams):
    """启动小说生成任务（非流式），返回 task_id"""
    if not params.llm_api_key:
        raise HTTPException(status_code=422, detail="请填写 LLM API Key")
    if not params.topic:
        raise HTTPException(status_code=422, detail="请填写小说主题")

    task_id = NovelService.start_generation(params.dict())
    return {
        "success": True,
        "task_id": task_id,
        "message": "小说生成任务已启动（非流式）",
    }


@router.post("/generate-stream")
async def generate_novel_stream(params: NovelGenerateParams):
    """SSE 流式小说生成 — 实时推送章节内容"""
    if not params.llm_api_key:
        raise HTTPException(status_code=422, detail="请填写 LLM API Key")
    if not params.topic:
        raise HTTPException(status_code=422, detail="请填写小说主题")

    task_id = NovelService.start_streaming_generation(params.dict())

    async def event_stream():
        queue = NovelService.get_stream_queue(task_id)
        if not queue:
            yield f"data: {json.dumps({'type': 'error', 'error': '队列创建失败'})}\n\n"
            return

        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=300)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

                if msg.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'error', 'error': '生成超时'})}\n\n"
                break

        NovelService.cleanup_stream(task_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/progress/{task_id}")
async def progress_stream(task_id: str):
    """SSE 进度推送（兼容旧版）"""

    async def event_stream():
        while True:
            task = NovelService.get_progress(task_id)
            if task is None:
                yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                break

            data = {
                "status": task.get("status"),
                "progress_pct": task.get("progress_pct", 0),
                "progress_msg": task.get("progress_msg", ""),
                "error": task.get("error"),
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            if task.get("status") in ("completed", "error"):
                if task.get("status") == "completed":
                    result = NovelService.get_result(task_id)
                    data["result"] = {
                        "total_chapters": result.get("total_chapters") if result else 0,
                        "filepath": result.get("filepath") if result else "",
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/progress/status/{task_id}")
async def get_progress(task_id: str):
    """获取任务进度（非流式）"""
    task = NovelService.get_progress(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, **task}


@router.get("/result/{task_id}")
async def get_result(task_id: str):
    """获取生成结果"""
    result = NovelService.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="结果不存在或任务未完成")
    return {"success": True, "data": result}


# ========== 模板 ==========

@router.get("/templates")
async def list_templates():
    """列出小说模板预设"""
    templates = {}
    for name, data in NOVEL_TEMPLATES.items():
        templates[name] = {k: v for k, v in data.items()}
    return {"success": True, "templates": templates}


# ========== 引导式创作 ==========

@router.post("/guided-chat")
async def guided_chat(params: GuidedChatParams):
    """引导式创作对话——AI 逐步提问收集需求，最终生成大纲"""
    if not params.llm_api_key:
        raise HTTPException(status_code=422, detail="请填写 LLM API Key")

    from llm_adapters import create_llm_adapter

    try:
        adapter = create_llm_adapter(
            interface_format=params.llm_interface,
            base_url=params.llm_base_url,
            model_name=params.llm_model,
            api_key=params.llm_api_key,
            temperature=params.llm_temperature,
            max_tokens=params.llm_max_tokens,
            timeout=120,
        )

        # 拼接完整对话作为 prompt
        # 格式：system 指令 + 历史对话
        dialog_lines = [f"系统指令：{GUIDED_SYSTEM_PROMPT}", ""]
        for m in params.messages:
            role = "用户" if m["role"] == "user" else "助手"
            dialog_lines.append(f"{role}：{m['content']}")
        dialog_lines.append("助手：")  # 提示 AI 继续回答

        full_prompt = "\n".join(dialog_lines)
        reply = adapter.invoke(full_prompt)

        # 检测是否包含大纲
        has_outline = "【大纲开始】" in reply

        return {
            "success": True,
            "reply": reply,
            "has_outline": has_outline,
        }

    except Exception as e:
        logger.exception("guided_chat 失败")
        raise HTTPException(status_code=500, detail=str(e)[:300])


# ========== 续写 ==========

@router.post("/continue")
async def continue_novel(params: NovelContinueParams):
    """在已有小说基础上续写新章节（SSE 流式返回）"""
    if not params.llm_api_key:
        raise HTTPException(status_code=422, detail="请填写 LLM API Key")
    if not params.novel_path or not os.path.exists(params.novel_path):
        raise HTTPException(status_code=422, detail="小说目录不存在")

    ch_dir = os.path.join(params.novel_path, "chapters")
    if not os.path.exists(ch_dir):
        raise HTTPException(status_code=422, detail="小说目录中没有章节")

    existing = len([f for f in os.listdir(ch_dir) if f.startswith("chapter_")])
    if existing == 0:
        raise HTTPException(status_code=422, detail="小说中没有已有章节")

    insert_after = params.insert_after
    # 校验 insert_after
    if insert_after < 0:
        insert_after = existing  # 追加末尾
    elif insert_after > existing:
        insert_after = existing
    # 计算插入后的总章数
    is_insert = insert_after < existing
    total_after = existing + params.num_chapters

    # 构建参数
    gen_params = params.dict()
    gen_params["topic"] = ""
    gen_params["num_chapters"] = params.num_chapters
    gen_params["insert_after"] = insert_after
    gen_params["output_dir"] = params.novel_path
    gen_params["_is_continuation"] = True
    gen_params["_is_insert"] = is_insert
    gen_params["_existing_chapters"] = existing
    gen_params["_total_chapters"] = total_after
    gen_params["filepath"] = params.novel_path

    task_id = NovelService.start_streaming_generation(gen_params)

    async def event_stream():
        queue = NovelService.get_stream_queue(task_id)
        if not queue:
            yield f"data: {json.dumps({'type': 'error', 'error': '队列创建失败'})}\n\n"
            return

        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=600)
                # 标记续写
                msg["is_continuation"] = True
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'error', 'error': '续写超时'})}\n\n"
                break

        NovelService.cleanup_stream(task_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/summaries/{task_id}")
async def get_summaries(task_id: str):
    """获取任务的摘要信息（用于前端展示）"""
    from services.novel_service import _get_task
    task = _get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    fp = task.get("result", {}).get("filepath", "")
    if fp and os.path.exists(fp):
        from services.novel_service import _load_summaries
        return {"success": True, "summaries": _load_summaries(fp)}
    return {"success": True, "summaries": {}}


# ========== 草稿箱 ==========

@router.get("/drafts")
async def list_drafts():
    """列出草稿箱"""
    novels = NovelService.list_saved_novels()
    return {"success": True, "novels": novels}


@router.post("/drafts/delete")
async def delete_draft(params: NovelQueryParams):
    """删除指定草稿"""
    if not params.path or not os.path.exists(params.path):
        raise HTTPException(status_code=404, detail="草稿不存在")
    ok = NovelService.delete_novel(params.path)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"success": True, "message": "草稿已删除"}


@router.post("/load")
async def load_novel(params: NovelQueryParams):
    """加载指定小说"""
    if not params.path or not os.path.exists(params.path):
        raise HTTPException(status_code=404, detail="小说不存在")
    data = NovelService.load_novel(params.path)
    if data is None:
        raise HTTPException(status_code=404, detail="无法加载小说")
    return {"success": True, "data": data}


# ========== 自定义模板 ==========

@router.get("/templates/custom")
async def list_custom_templates():
    """列出所有自定义模板"""
    return {"success": True, "templates": db_list_templates()}


@router.post("/templates/custom/save")
async def save_template(params: SaveTemplateParams):
    """保存自定义模板"""
    tpl = create_template(name=params.name, params=params.params)
    return {"success": True, "template_id": tpl["id"], "name": tpl["name"]}


@router.post("/templates/custom/delete")
async def delete_template(params: DeleteTemplateParams):
    """删除自定义模板"""
    if not db_delete_template(params.template_id):
        raise HTTPException(status_code=404, detail="模板不存在")
    return {"success": True, "message": "模板已删除"}


@router.post("/templates/custom/update")
async def update_template_route(params: UpdateTemplateParams):
    """更新自定义模板"""
    if not update_template(params.template_id, name=params.name, params=params.params):
        raise HTTPException(status_code=404, detail="模板不存在")
    return {"success": True, "template_id": params.template_id, "name": params.name}


# ========== 聊天记录 ==========

@router.get("/chat/list")
async def list_chats_route():
    """列出所有保存的对话"""
    return {"success": True, "chats": list_chats()}


@router.post("/chat/save")
async def save_chat_route(params: SaveChatParams):
    """保存聊天记录"""
    chat = create_chat(name=params.name, messages=params.messages)
    return {"success": True, "chat_id": chat["id"], "name": chat["name"]}


@router.post("/chat/load")
async def load_chat_route(params: DeleteChatParams):
    """加载指定对话"""
    data = get_chat(params.chat_id)
    if data is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"success": True, "data": data}


@router.post("/chat/delete")
async def delete_chat_route(params: DeleteChatParams):
    """删除对话记录"""
    if not db_delete_chat(params.chat_id):
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"success": True, "message": "对话已删除"}
