"""数据库层单元测试"""

import pytest
from database import (
    create_template, list_templates, get_template, update_template, delete_template,
    create_chat, list_chats, get_chat, delete_chat,
)


class TestTemplates:
    def test_create_and_list(self):
        """创建模板后列表应包含该模板"""
        tpl = create_template("我的模板", {"topic": "科幻"})
        lst = list_templates()
        ids = [t["id"] for t in lst]
        assert tpl["id"] in ids

    def test_get_by_id(self):
        """按 ID 查询应返回正确模板"""
        tpl = create_template("查询测试", {"genre": "悬疑"})
        got = get_template(tpl["id"])
        assert got is not None
        assert got["name"] == "查询测试"
        assert got["params"]["genre"] == "悬疑"

    def test_get_not_found(self):
        """查询不存在的 ID 应返回 None"""
        assert get_template("nonexistent") is None

    def test_update(self):
        """更新模板名称和参数"""
        tpl = create_template("旧名", {"a": 1})
        ok = update_template(tpl["id"], name="新名", params={"b": 2})
        assert ok is True
        got = get_template(tpl["id"])
        assert got["name"] == "新名"
        assert got["params"]["b"] == 2

    def test_update_not_found(self):
        """更新不存在的模板应返回 False"""
        ok = update_template("nonexistent", name="x", params={})
        assert ok is False

    def test_delete(self):
        """删除后列表不应包含该模板"""
        tpl = create_template("待删除", {})
        assert delete_template(tpl["id"]) is True
        assert get_template(tpl["id"]) is None

    def test_delete_not_found(self):
        """删除不存在的模板应返回 False"""
        assert delete_template("nonexistent") is False

    def test_name_truncation(self):
        """名称超过 50 字符应截断"""
        long_name = "a" * 100
        tpl = create_template(long_name, {})
        assert len(tpl["name"]) == 50

    def test_list_empty(self):
        """空数据库时应返回空列表"""
        # fixture 已清空表
        assert list_templates() == []


class TestChats:
    def test_create_and_list(self):
        """创建对话后列表应包含"""
        chat = create_chat("闲聊", [{"role": "user", "content": "hi"}])
        lst = list_chats()
        ids = [c["id"] for c in lst]
        assert chat["id"] in ids

    def test_get_by_id(self):
        """按 ID 查询对话"""
        chat = create_chat("测试", [{"role": "user", "content": "msg"}])
        got = get_chat(chat["id"])
        assert got is not None
        assert got["name"] == "测试"
        assert len(got["messages"]) == 1

    def test_get_not_found(self):
        """查询不存在的对话应返回 None"""
        assert get_chat("nonexistent") is None

    def test_message_truncation(self):
        """超过 100 条消息应截断"""
        many = [{"role": "user", "content": f"msg{i}"} for i in range(150)]
        chat = create_chat("长对话", many)
        assert len(chat["messages"]) == 100

    def test_delete(self):
        """删除对话"""
        chat = create_chat("待删除", [])
        assert delete_chat(chat["id"]) is True
        assert get_chat(chat["id"]) is None

    def test_delete_not_found(self):
        """删除不存在的对话应返回 False"""
        assert delete_chat("nonexistent") is False

    def test_list_message_count(self):
        """列表应返回正确的消息数"""
        msgs = [{"role": "user", "content": f"m{i}"} for i in range(5)]
        create_chat("计数测试", msgs)
        lst = list_chats()
        assert lst[0]["message_count"] == 5
