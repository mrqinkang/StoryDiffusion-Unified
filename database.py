# database.py
"""SQLite 持久化层 — 替换 JSON 文件存储"""

import sqlite3
import json
import os
import uuid
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "storydiffusion.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """创建表结构（幂等）"""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS templates (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                params     TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chats (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                messages   TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
        """)


# ======================== 模板 ========================

def create_template(name: str, params: dict) -> dict:
    tid = f"tpl_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO templates (id, name, params, created_at) VALUES (?, ?, ?, ?)",
            (tid, name[:50], json.dumps(params, ensure_ascii=False), now),
        )
    return {"id": tid, "name": name[:50], "params": params, "created_at": now}


def list_templates() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, params, created_at FROM templates ORDER BY created_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "name": r["name"],
            "params": json.loads(r["params"]),
            "created_at": r["created_at"],
        })
    return result


def get_template(template_id: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, params, created_at FROM templates WHERE id = ?",
            (template_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "params": json.loads(row["params"]),
        "created_at": row["created_at"],
    }


def update_template(template_id: str, name: str, params: dict) -> bool:
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE templates SET name = ?, params = ?, created_at = ? WHERE id = ?",
            (name[:50], json.dumps(params, ensure_ascii=False), now, template_id),
        )
        return cur.rowcount > 0


def delete_template(template_id: str) -> bool:
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        return cur.rowcount > 0


# ======================== 聊天记录 ========================

def create_chat(name: str, messages: list) -> dict:
    cid = f"chat_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO chats (id, name, messages, created_at) VALUES (?, ?, ?, ?)",
            (cid, name[:50], json.dumps(messages[-100:], ensure_ascii=False), now),
        )
    return {"id": cid, "name": name[:50], "messages": messages[-100:], "created_at": now}


def list_chats() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, messages, created_at FROM chats ORDER BY created_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        msgs = json.loads(r["messages"])
        result.append({
            "id": r["id"],
            "name": r["name"],
            "created_at": r["created_at"],
            "message_count": len(msgs),
        })
    return result


def get_chat(chat_id: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, messages, created_at FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "messages": json.loads(row["messages"]),
        "created_at": row["created_at"],
    }


def delete_chat(chat_id: str) -> bool:
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cur.rowcount > 0
