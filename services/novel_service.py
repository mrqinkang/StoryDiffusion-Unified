# services/novel_service.py
"""小说生成服务 - 封装 AI_NovelGenerator 核心流水线"""

import os
import json
import uuid
import logging
import threading
import time
import asyncio
from datetime import datetime
from typing import Optional, Callable, AsyncIterator

from llm_adapters import create_llm_adapter
from novel_generator.architecture import Novel_architecture_generate
from novel_generator.blueprint import Chapter_blueprint_generate
from novel_generator.chapter import generate_chapter_draft
from novel_generator.finalization import finalize_chapter
from novel_utils import read_file

logger = logging.getLogger("novel_service")

# 存储后台任务状态
_tasks: dict = {}
# 存储流式队列 {task_id: asyncio.Queue}
_stream_queues: dict = {}

# ---------- 模板预设 ----------
NOVEL_TEMPLATES = {
    "玄幻修仙": {
        "topic": "一位平凡少年意外获得上古传承，踏上修仙之路，历经磨难终成大道至尊",
        "genre": "玄幻修仙",
        "characters_involved": "主角（废柴少年）、师尊（神秘高人）、宿敌（宗门天才）、红颜知己",
        "key_items": "上古玉佩、飞剑、灵丹妙药",
        "scene_location": "修真大陆、玄天宗、秘境、天劫台",
        "time_constraint": "古代架空，修真纪元",
        "user_guidance": "典型的废柴逆袭流，要有境界突破（练气→筑基→金丹→元婴→化神），每章结尾留悬念",
    },
    "科幻末世": {
        "topic": "公元2157年，人类文明在 AI 叛乱中濒临崩溃，一支幸存者小队寻找最后的希望",
        "genre": "科幻末世",
        "characters_involved": "主角（前军事情报官）、AI 科学家（制造了叛乱的 AI）、机械师、医疗兵",
        "key_items": "量子通讯器、生物装甲、能源核心",
        "scene_location": "废都、地下基地、AI 主脑核心",
        "time_constraint": "公元2157年，AI 叛乱后第3年",
        "user_guidance": "硬科幻风格，注重科技细节和生存紧张感，角色在道德困境中做选择",
    },
    "悬疑推理": {
        "topic": "深夜，一位私家侦探接到了一通神秘电话，从此卷入一起横跨十年的连环案件",
        "genre": "悬疑推理",
        "characters_involved": "主角（私家侦探）、委托人（神秘女子）、警长（老搭档）、真凶",
        "key_items": "旧照片、怀表、未署名的信",
        "scene_location": "雨夜的都市、废弃工厂、高档公寓",
        "time_constraint": "1990年代，连续十天",
        "user_guidance": "本格推理风格，所有线索必须公平地呈现给读者，注重逻辑严密性，结局要有反转",
    },
    "都市异能": {
        "topic": "一个普通上班族意外觉醒了能看见他人记忆的能力，平静的生活从此天翻地覆",
        "genre": "都市异能",
        "characters_involved": "主角（社畜程序员）、好友（话痨同事）、神秘组织成员、女主角",
        "key_items": "能力触发的怀表、日记本、加密U盘",
        "scene_location": "现代都市、写字楼、地铁站、天台酒吧",
        "time_constraint": "现代都市，2024年秋季",
        "user_guidance": "轻松幽默与紧张悬疑交替，能力成长为主线，都市日常为辅",
    },
}

# ---------- 草稿箱路径 ----------
DRAFTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generated_novels")
os.makedirs(DRAFTS_DIR, exist_ok=True)


def _get_task(task_id: str) -> Optional[dict]:
    return _tasks.get(task_id)


def _update_task(task_id: str, **kwargs):
    if task_id in _tasks:
        _tasks[task_id].update(kwargs)


# ---------- 章节摘要 ----------
SUMMARY_PROMPT = """请为以下小说章节写一段简洁的摘要（150字以内），
提取关键剧情发展、角色变化、重要伏笔。
不要评价，只客观总结：

{chapter_text}

摘要："""


def _generate_summary(adapter, chapter_text: str) -> str:
    """调用 LLM 生成章节摘要"""
    if not chapter_text or len(chapter_text) < 50:
        return chapter_text[:200] if chapter_text else ""
    try:
        prompt = SUMMARY_PROMPT.format(chapter_text=chapter_text[:3000])
        summary = adapter.invoke(prompt)
        # 清理和截断
        summary = summary.strip().replace("摘要：", "").replace("摘要:", "").strip()
        return summary[:300] if summary else chapter_text[:200]
    except Exception as e:
        logger.warning(f"生成摘要失败: {e}")
        return chapter_text[:200]


def _load_summaries(fp: str) -> dict:
    """加载已有的章节摘要"""
    path = os.path.join(fp, "chapter_summaries.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_summaries(fp: str, summaries: dict):
    """保存章节摘要"""
    path = os.path.join(fp, "chapter_summaries.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)


def _update_manifest_chapter_count(fp: str):
    """在插入续写后更新 manifest.json 的章节数"""
    mf_path = os.path.join(fp, "manifest.json")
    if os.path.exists(mf_path):
        try:
            with open(mf_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            ch_dir = os.path.join(fp, "chapters")
            actual = len([f for f in os.listdir(ch_dir) if f.startswith("chapter_")]) if os.path.exists(ch_dir) else 0
            manifest["num_chapters"] = actual
            with open(mf_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"更新 manifest 失败: {e}")


def _build_continuation_context(fp: str, next_chapter: int, summaries: dict) -> str:
    """
    构建续写上下文：
    - 前 N-2 章：摘要（历史脉络）
    - 第 N-1 章：全文（最近的细节）
    """
    parts = []

    # 前 N-2 章的摘要
    summary_lines = []
    for ch in range(1, next_chapter - 1):
        s = summaries.get(str(ch), "")
        if s:
            summary_lines.append(f"第{ch}章摘要：{s}")
    if summary_lines:
        parts.append("【前情提要】\n" + "\n".join(summary_lines))

    # 第 N-1 章全文
    prev_ch = next_chapter - 1
    prev_file = os.path.join(fp, "chapters", f"chapter_{prev_ch}.txt")
    if os.path.exists(prev_file):
        from novel_utils import read_file
        prev_text = read_file(prev_file)
        parts.append(f"\n【上一章原文（第{prev_ch}章）】\n{prev_text[:3000]}")

    return "\n\n".join(parts)


def _build_style_instruction(params: dict) -> str:
    """根据风格参数构建 prompt 指令"""
    parts = []
    lang = params.get("language_style", "").strip()
    if lang:
        parts.append(f"语言风格：{lang}")
    emotion = params.get("emotional_tone", "").strip()
    if emotion:
        parts.append(f"情感基调：{emotion}")
    taboo = params.get("content_taboos", "").strip()
    if taboo:
        parts.append(f"内容禁忌：避免出现{taboo}")
    return "；".join(parts) if parts else ""


def _save_draft_manifest(params: dict, fp: str, task_id: str):
    """保存草稿清单（元信息）"""
    manifest = {
        "task_id": task_id,
        "title": params.get("topic", "未命名小说")[:50],
        "genre": params.get("genre", ""),
        "created_at": datetime.now().isoformat(),
        "num_chapters": params.get("num_chapters", 5),
        "words_per_chapter": params.get("word_number", 2000),
    }
    mf_path = os.path.join(fp, "manifest.json")
    with open(mf_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def _run_novel_generation(
    task_id: str,
    params: dict,
    stream_queue: asyncio.Queue = None,
):
    """
    在后台线程中运行小说生成流水线
    如果 stream_queue 不为 None，则每完成一步就推送消息到队列（流式模式）
    """
    task = _get_task(task_id)
    if not task:
        return

    fp = params["filepath"]
    os.makedirs(fp, exist_ok=True)
    os.makedirs(os.path.join(fp, "chapters"), exist_ok=True)

    # 保存草稿清单
    _save_draft_manifest(params, fp, task_id)

    # 通用 LLM 参数
    llm_if = params.get("llm_interface", "OpenAI")
    llm_key = params.get("llm_api_key", "")
    llm_url = params.get("llm_base_url", "")
    llm_model = params.get("llm_model", "gpt-4")
    llm_temp = params.get("llm_temperature", 0.7)
    llm_tokens = params.get("llm_max_tokens", 4096)
    llm_timeout = params.get("llm_timeout", 600)

    embedding_if = params.get("embedding_interface", "OpenAI")
    embedding_key = params.get("embedding_api_key", "")
    embedding_url = params.get("embedding_base_url", "")
    embedding_model = params.get("embedding_model", "text-embedding-ada-002")

    num_chapters = int(params.get("num_chapters", 5))
    word_number = int(params.get("word_number", 2000))
    topic = params.get("topic", "")
    genre = params.get("genre", "")
    user_guidance = params.get("user_guidance", "")
    characters_involved = params.get("characters_involved", "")
    key_items = params.get("key_items", "")
    scene_location = params.get("scene_location", "")
    time_constraint = params.get("time_constraint", "")

    # 风格参数
    style_instruction = _build_style_instruction(params)
    if style_instruction:
        user_guidance = (user_guidance + "\n" + style_instruction).strip()

    # 用于构建最终结果
    all_architecture = ""
    all_directory = ""
    chapters_content = []

    def _push(event_type: str, data: dict):
        """推送到流式队列（自动带上 filepath）"""
        if stream_queue:
            try:
                data["filepath"] = fp
                loop = asyncio.new_event_loop()
                loop.run_until_complete(stream_queue.put({"type": event_type, **data}))
                loop.close()
            except Exception:
                pass

    def progress(msg: str, pct: float):
        _update_task(task_id, progress_msg=msg, progress_pct=pct)
        _push("progress", {"progress_msg": msg, "progress_pct": pct})

    # ------ 判断是否为续写模式 ------
    is_continuation = params.get("_is_continuation", False)
    is_insert = params.get("_is_insert", False)
    existing_chapters = int(params.get("_existing_chapters", 0))
    total_target = int(params.get("_total_chapters", num_chapters))

    try:
        if is_continuation:
            # ===== 续写模式：跳过架构和蓝图，加载已有内容 =====
            arch_file = os.path.join(fp, "Novel_architecture.txt")
            all_architecture = read_file(arch_file) if os.path.exists(arch_file) else ""
            dir_file = os.path.join(fp, "Novel_directory.txt")
            all_directory = read_file(dir_file) if os.path.exists(dir_file) else ""

            # 加载已有的章节内容
            for ec in range(1, existing_chapters + 1):
                cf = os.path.join(fp, "chapters", f"chapter_{ec}.txt")
                if os.path.exists(cf):
                    chapters_content.append(read_file(cf))

            insert_after = int(params.get("insert_after", existing_chapters))

            if is_insert:
                # ===== 插入模式：把 insert_after 之后的章节往后移 =====
                shift_by = num_chapters
                ch_dir = os.path.join(fp, "chapters")
                # 从后往前移动，避免覆盖
                for ec in range(existing_chapters, insert_after, -1):
                    src = os.path.join(ch_dir, f"chapter_{ec}.txt")
                    dst = os.path.join(ch_dir, f"chapter_{ec + shift_by}.txt")
                    if os.path.exists(src):
                        os.rename(src, dst)
                        logger.info(f"  移动章节: chapter_{ec}.txt → chapter_{ec + shift_by}.txt")

                # 摘要也要移动
                summaries = _load_summaries(fp)
                new_summaries = {}
                for k, v in summaries.items():
                    k_int = int(k)
                    if k_int > insert_after:
                        new_summaries[str(k_int + shift_by)] = v
                    else:
                        new_summaries[k] = v
                _save_summaries(fp, new_summaries)

                progress(f"插入模式：在第 {insert_after} 章后插入 {num_chapters} 章", 10)
                generation_start = insert_after + 1
                generation_total = insert_after + num_chapters

                # 后续上下文构建将从 insert_after 之前的内容生成
                cont_ctx = _build_continuation_context(fp, generation_start, _load_summaries(fp))
            else:
                # ===== 追加模式（默认） =====
                # 构建续写上下文（摘要 + 最近一章全文）
                summaries = _load_summaries(fp)
                cont_ctx = _build_continuation_context(fp, existing_chapters + 1, summaries)
                generation_start = existing_chapters + 1
                generation_total = total_target

            if cont_ctx:
                user_guidance = (user_guidance + "\n\n" + cont_ctx).strip()

            progress(f"续写模式：已有 {existing_chapters} 章，追加 {num_chapters} 章", 10)
            _push("continuation_info", {
                "existing": existing_chapters,
                "new": num_chapters,
                "total": total_target,
            })
        else:
            # ===== Step 1: 构造小说架构 =====
            progress("正在生成小说架构...", 5)
            logger.info(f"[{task_id}] Step 1: 生成小说架构")
            Novel_architecture_generate(
                interface_format=llm_if,
                api_key=llm_key,
                base_url=llm_url,
                llm_model=llm_model,
                topic=topic,
                genre=genre,
                number_of_chapters=num_chapters,
                word_number=word_number,
                filepath=fp,
                user_guidance=user_guidance,
                temperature=llm_temp,
                max_tokens=llm_tokens,
                timeout=llm_timeout,
            )

            arch_file = os.path.join(fp, "Novel_architecture.txt")
            if not os.path.exists(arch_file):
                _update_task(task_id, status="error", error="小说架构生成失败")
                _push("error", {"error": "小说架构生成失败"})
                return

            all_architecture = read_file(arch_file)

            # ===== Step 2: 生成章节目录 =====
            progress("正在生成章节目录...", 15)
            logger.info(f"[{task_id}] Step 2: 生成章节目录")
            Chapter_blueprint_generate(
                interface_format=llm_if,
                api_key=llm_key,
                base_url=llm_url,
                llm_model=llm_model,
                filepath=fp,
                number_of_chapters=num_chapters,
                user_guidance=user_guidance,
                temperature=llm_temp,
                max_tokens=llm_tokens,
                timeout=llm_timeout,
            )

            dir_file = os.path.join(fp, "Novel_directory.txt")
            all_directory = read_file(dir_file) if os.path.exists(dir_file) else ""

            # 推送架构信息
            _push("architecture", {
                "architecture": all_architecture,
                "directory": all_directory,
            })

            generation_total = num_chapters
            generation_start = 1

        # ===== 逐章生成 =====
        progress("开始逐章生成..." if not is_continuation else f"开始续写 ({num_chapters} 章)...", 25)
        logger.info(f"[{task_id}] 逐章生成 ({generation_start}~{generation_total})")

        for ch in range(generation_start, generation_total + 1):
            pct = 25 + ((ch - generation_start + 1) / (generation_total - generation_start + 1)) * 60
            msg = f"正在生成第 {ch}/{generation_total} 章..."
            if is_continuation:
                msg = f"续写：第 {ch}/{generation_total} 章..."
            progress(msg, int(pct))
            _push("chapter_start", {"chapter": ch, "total": generation_total})

            chapter_content = generate_chapter_draft(
                api_key=llm_key,
                base_url=llm_url,
                model_name=llm_model,
                filepath=fp,
                novel_number=ch,
                word_number=word_number,
                temperature=llm_temp,
                user_guidance=user_guidance,
                characters_involved=characters_involved,
                key_items=key_items,
                scene_location=scene_location,
                time_constraint=time_constraint,
                embedding_api_key=embedding_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_if,
                embedding_model_name=embedding_model,
                interface_format=llm_if,
                max_tokens=llm_tokens,
                timeout=llm_timeout,
            )

            if not chapter_content:
                logger.warning(f"[{task_id}] 第 {ch} 章生成为空，跳过定稿")
                continue

            chapters_content.append(chapter_content)

            # 推送章节内容
            _push("chapter_content", {
                "chapter": ch,
                "content": chapter_content,
            })

            # 定稿（更新摘要、角色状态、向量库）
            finalize_chapter(
                novel_number=ch,
                word_number=word_number,
                api_key=llm_key,
                base_url=llm_url,
                model_name=llm_model,
                temperature=llm_temp,
                filepath=fp,
                embedding_api_key=embedding_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_if,
                embedding_model_name=embedding_model,
                interface_format=llm_if,
                max_tokens=llm_tokens,
                timeout=llm_timeout,
            )

            # 生成并保存章节摘要（用于续写模式）
            try:
                summary_adapter = create_llm_adapter(
                    llm_if, llm_url, llm_model, llm_key, 0.3, 512, 60
                )
                summary = _generate_summary(summary_adapter, chapter_content)
                summaries = _load_summaries(fp)
                summaries[str(ch)] = summary
                _save_summaries(fp, summaries)
                logger.info(f"[{task_id}] 第{ch}章摘要已保存")
            except Exception as e:
                logger.warning(f"[{task_id}] 第{ch}章摘要生成失败: {e}")

        # ===== 读取生成结果 =====
        progress("正在整理结果...", 95)

        # 如果插入了章节，更新 manifest.json 的章数
        if is_insert:
            _update_manifest_chapter_count(fp)

        _update_task(
            task_id,
            status="completed",
            progress_pct=100,
            progress_msg="生成完成！",
            result={
                "architecture": all_architecture,
                "directory": all_directory,
                "chapters": chapters_content,
                "total_chapters": len(chapters_content),
                "filepath": fp,
            },
        )
        _push("done", {
            "total_chapters": len(chapters_content),
            "filepath": fp,
        })
        logger.info(f"[{task_id}] 小说生成完成，共 {len(chapters_content)} 章")

    except Exception as e:
        logger.exception(f"[{task_id}] 小说生成异常")
        _update_task(task_id, status="error", error=str(e)[:500])
        _push("error", {"error": str(e)[:500]})


class NovelService:
    """小说生成服务"""

    @staticmethod
    def start_generation(params: dict) -> str:
        """启动后台小说生成任务，返回 task_id"""
        task_id = uuid.uuid4().hex[:12]
        output_dir = params.get("output_dir", "")
        if not output_dir:
            output_dir = os.path.join(DRAFTS_DIR, f"novel_{task_id}")
        params["filepath"] = output_dir

        _tasks[task_id] = {
            "status": "running",
            "progress_pct": 0,
            "progress_msg": "初始化...",
            "result": None,
            "error": None,
        }

        thread = threading.Thread(
            target=_run_novel_generation,
            args=(task_id, params, None),
            daemon=True,
        )
        thread.start()
        return task_id

    @staticmethod
    def start_streaming_generation(params: dict) -> str:
        """启动流式小说生成（结果通过 asyncio.Queue 推送）"""
        task_id = uuid.uuid4().hex[:12]
        output_dir = params.get("output_dir", "")
        if not output_dir:
            output_dir = os.path.join(DRAFTS_DIR, f"novel_{task_id}")
        params["filepath"] = output_dir

        _tasks[task_id] = {
            "status": "running",
            "progress_pct": 0,
            "progress_msg": "初始化...",
            "result": None,
            "error": None,
        }

        # 创建流式队列
        queue = asyncio.Queue()
        _stream_queues[task_id] = queue

        thread = threading.Thread(
            target=_run_novel_generation,
            args=(task_id, params, queue),
            daemon=True,
        )
        thread.start()
        return task_id

    @staticmethod
    def get_stream_queue(task_id: str) -> Optional[asyncio.Queue]:
        return _stream_queues.get(task_id)

    @staticmethod
    def cleanup_stream(task_id: str):
        _stream_queues.pop(task_id, None)
        _tasks.pop(task_id, None)

    @staticmethod
    def get_progress(task_id: str) -> Optional[dict]:
        """获取任务进度"""
        task = _get_task(task_id)
        if not task:
            return None
        return {k: v for k, v in task.items() if k != "result"}

    @staticmethod
    def get_result(task_id: str) -> Optional[dict]:
        """获取任务结果"""
        task = _get_task(task_id)
        if not task:
            return None
        return task.get("result")

    @staticmethod
    def list_saved_novels() -> list:
        """列出草稿箱中的小说"""
        if not os.path.exists(DRAFTS_DIR):
            return []

        results = []
        for name in sorted(os.listdir(DRAFTS_DIR), reverse=True):
            novel_dir = os.path.join(DRAFTS_DIR, name)
            if not os.path.isdir(novel_dir):
                continue
            # 读取 manifest
            mf_path = os.path.join(novel_dir, "manifest.json")
            manifest = {}
            if os.path.exists(mf_path):
                try:
                    with open(mf_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception:
                    pass

            chapters_dir = os.path.join(novel_dir, "chapters")
            chapter_count = 0
            if os.path.exists(chapters_dir):
                chapter_count = len([f for f in os.listdir(chapters_dir) if f.startswith("chapter_")])

            results.append({
                "id": name,
                "name": manifest.get("title", name),
                "path": novel_dir,
                "chapter_count": chapter_count,
                "genre": manifest.get("genre", ""),
                "created_at": manifest.get("created_at", ""),
            })
        return results

    @staticmethod
    def load_novel(novel_path: str) -> Optional[dict]:
        """加载指定目录的小说"""
        arch_file = os.path.join(novel_path, "Novel_architecture.txt")
        dir_file = os.path.join(novel_path, "Novel_directory.txt")
        chapters_dir = os.path.join(novel_path, "chapters")

        if not os.path.exists(arch_file) and not os.path.exists(chapters_dir):
            return None

        chapters = []
        if os.path.exists(chapters_dir):
            files = sorted(
                [f for f in os.listdir(chapters_dir) if f.startswith("chapter_")],
                key=lambda x: int(x.replace("chapter_", "").replace(".txt", "")),
            )
            for fname in files:
                chapters.append({
                    "number": fname.replace("chapter_", "").replace(".txt", ""),
                    "content": read_file(os.path.join(chapters_dir, fname)),
                })

        return {
            "architecture": read_file(arch_file) if os.path.exists(arch_file) else "",
            "directory": read_file(dir_file) if os.path.exists(dir_file) else "",
            "chapters": chapters,
            "summaries": _load_summaries(novel_path),
            "path": novel_path,
        }

    @staticmethod
    def continue_novel(
        novel_path: str,
        params: dict,
        stream_queue: asyncio.Queue = None,
    ) -> str:
        """在已有小说基础上续写新章节，返回 task_id"""
        task_id = uuid.uuid4().hex[:12]

        # 统计已有章节数
        chapters_dir = os.path.join(novel_path, "chapters")
        existing = 0
        if os.path.exists(chapters_dir):
            existing = len([f for f in os.listdir(chapters_dir) if f.startswith("chapter_")])

        new_chapters = int(params.get("num_chapters", 3))
        total_chapters = existing + new_chapters
        params["filepath"] = novel_path
        params["_existing_chapters"] = existing
        params["_total_chapters"] = total_chapters
        params["_is_continuation"] = True

        _tasks[task_id] = {
            "status": "running",
            "progress_pct": 0,
            "progress_msg": "初始化续写...",
            "result": None,
            "error": None,
        }

        if stream_queue is not None:
            _stream_queues[task_id] = stream_queue

        thread = threading.Thread(
            target=_run_novel_generation,
            args=(task_id, params, stream_queue),
            daemon=True,
        )
        thread.start()
        return task_id

    @staticmethod
    def delete_novel(novel_path: str) -> bool:
        """删除指定目录的小说（包含所有文件）"""
        import shutil
        if not os.path.exists(novel_path):
            return False
        try:
            shutil.rmtree(novel_path)
            logger.info(f"已删除小说: {novel_path}")
            return True
        except Exception as e:
            logger.error(f"删除小说失败 {novel_path}: {e}")
            return False
