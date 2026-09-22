"""pytest  fixtures — 测试用内存数据库 + FastAPI TestClient"""

import os
import sys
import tempfile

# 把项目根目录加入 path，确保 import 能工作
_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

# 在 import database 之前把 DB_PATH 改为临时文件，防止污染开发库
import database as db_mod

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
db_mod.DB_PATH = _db_path

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(autouse=True)
def _setup_db():
    """每个测试前重置数据库表"""
    db_mod.init_db()
    yield
    # 清空所有表
    from database import _get_conn
    with _get_conn() as conn:
        conn.execute("DELETE FROM templates")
        conn.execute("DELETE FROM chats")


@pytest.fixture
def client():
    """FastAPI 测试客户端"""
    return TestClient(app)


@pytest.fixture
def sample_template():
    """创建一个示例模板并返回其 id"""
    from database import create_template
    tpl = create_template(
        name="测试模板",
        params={"topic": "修仙", "genre": "玄幻", "word_number": 2000, "num_chapters": 5},
    )
    return tpl


@pytest.fixture
def sample_chat():
    """创建一个示例对话并返回其 id"""
    from database import create_chat
    chat = create_chat(
        name="测试对话",
        messages=[
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你的？"},
        ],
    )
    return chat
