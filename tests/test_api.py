"""API 路由集成测试"""

import pytest


class TestTemplatesAPI:
    """模板 API 测试"""

    def test_list_empty(self, client):
        """空数据库时列表应为空"""
        resp = client.get("/api/novel/templates/custom")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["templates"] == []

    def test_create(self, client):
        """POST 创建模板"""
        resp = client.post("/api/novel/templates/custom/save", json={
            "name": "测试模板",
            "params": {"topic": "修仙", "genre": "玄幻"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["name"] == "测试模板"
        assert data["template_id"].startswith("tpl_")

    def test_list_after_create(self, client):
        """创建后列表应有 1 条"""
        client.post("/api/novel/templates/custom/save", json={
            "name": "模板A",
            "params": {"topic": "科幻"},
        })
        resp = client.get("/api/novel/templates/custom")
        assert len(resp.json()["templates"]) == 1

    def test_update(self, client):
        """更新模板"""
        # 先创建
        create_resp = client.post("/api/novel/templates/custom/save", json={
            "name": "旧名称",
            "params": {"topic": "A"},
        })
        tid = create_resp.json()["template_id"]
        # 更新
        upd_resp = client.post("/api/novel/templates/custom/update", json={
            "template_id": tid,
            "name": "新名称",
            "params": {"topic": "B"},
        })
        assert upd_resp.status_code == 200
        assert upd_resp.json()["success"] is True
        # 验证
        lst = client.get("/api/novel/templates/custom").json()["templates"]
        tpl = next(t for t in lst if t["id"] == tid)
        assert tpl["name"] == "新名称"
        assert tpl["params"]["topic"] == "B"

    def test_update_not_found(self, client):
        """更新不存在的模板应 404"""
        resp = client.post("/api/novel/templates/custom/update", json={
            "template_id": "tpl_nonexistent",
            "name": "x",
            "params": {},
        })
        assert resp.status_code == 404

    def test_delete(self, client):
        """删除模板"""
        create_resp = client.post("/api/novel/templates/custom/save", json={
            "name": "待删除",
            "params": {},
        })
        tid = create_resp.json()["template_id"]
        del_resp = client.post("/api/novel/templates/custom/delete", json={
            "template_id": tid,
        })
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True
        # 验证已删除
        lst = client.get("/api/novel/templates/custom").json()["templates"]
        assert all(t["id"] != tid for t in lst)

    def test_delete_not_found(self, client):
        """删除不存在的模板应 404"""
        resp = client.post("/api/novel/templates/custom/delete", json={
            "template_id": "tpl_nonexistent",
        })
        assert resp.status_code == 404

    def test_builtin_templates(self, client):
        """内置模板接口应返回对象（键值对）"""
        resp = client.get("/api/novel/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["templates"], dict)


class TestChatsAPI:
    """对话 API 测试"""

    def test_list_empty(self, client):
        """空数据库时列表应为空"""
        resp = client.get("/api/novel/chat/list")
        assert resp.status_code == 200
        assert resp.json()["chats"] == []

    def test_create(self, client):
        """创建对话"""
        resp = client.post("/api/novel/chat/save", json={
            "name": "测试对话",
            "messages": [{"role": "user", "content": "你好"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["chat_id"].startswith("chat_")

    def test_load(self, client):
        """加载对话应返回完整消息"""
        create_resp = client.post("/api/novel/chat/save", json={
            "name": "对话",
            "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        })
        cid = create_resp.json()["chat_id"]
        load_resp = client.post("/api/novel/chat/load", json={"chat_id": cid})
        assert load_resp.status_code == 200
        data = load_resp.json()
        assert data["success"] is True
        assert len(data["data"]["messages"]) == 2

    def test_load_not_found(self, client):
        """加载不存在的对话应 404"""
        resp = client.post("/api/novel/chat/load", json={"chat_id": "chat_nonexistent"})
        assert resp.status_code == 404

    def test_delete(self, client):
        """删除对话"""
        create_resp = client.post("/api/novel/chat/save", json={
            "name": "待删除",
            "messages": [],
        })
        cid = create_resp.json()["chat_id"]
        del_resp = client.post("/api/novel/chat/delete", json={"chat_id": cid})
        assert del_resp.status_code == 200
        # 验证
        lst = client.get("/api/novel/chat/list").json()["chats"]
        assert all(c["id"] != cid for c in lst)

    def test_delete_not_found(self, client):
        """删除不存在的对话应 404"""
        resp = client.post("/api/novel/chat/delete", json={"chat_id": "chat_nonexistent"})
        assert resp.status_code == 404

    def test_message_limit(self, client):
        """超过 100 条消息应被截断"""
        many = [{"role": "user", "content": f"msg{i}"} for i in range(150)]
        create_resp = client.post("/api/novel/chat/save", json={
            "name": "长对话",
            "messages": many,
        })
        cid = create_resp.json()["chat_id"]
        load_resp = client.post("/api/novel/chat/load", json={"chat_id": cid})
        assert len(load_resp.json()["data"]["messages"]) == 100



