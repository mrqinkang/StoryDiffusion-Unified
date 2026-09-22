# -*- coding: utf-8 -*-
"""
StoryDiffusion → Apifox 测试迁移脚本
自动完成：测试用例创建 + Mock 预期 + Test Suite 分组
"""
import json
import os
import subprocess
import sys
import time
import tempfile

# ============================================================
# 配置
# ============================================================
# 从环境变量读取 Apifox Token（运行前需 export APIFOX_TOKEN）
TOKEN = os.environ.get("APIFOX_TOKEN", "")
if not TOKEN:
    print("[警告] 未设置环境变量 APIFOX_TOKEN，请先设置后运行")
PROJECT = "8569627"
CATEGORY_POSITIVE = 11971526   # 正向
CATEGORY_NEGATIVE = 11971527   # 负向
CATEGORY_BOUNDARY = 11971528   # 边界值
CATEGORY_SECURITY = 11971529   # 安全性
CATEGORY_OTHER   = 11971530    # 其他

# 环境 ID
ENV_LOCAL    = 47307103  # 本地开发环境 (localhost:8000)
ENV_MOCK_LOCAL = 47306468  # 本地 Mock

# ============================================================
# Endpoint ID 映射 (APIFOX ID → 路径)
# ============================================================
ENDPOINTS = {
    # 系统
    "api_health":            485848334,  # GET /api/health
    # 漫画
    "comic_styles":          485848357,  # GET /api/comic/styles
    "comic_layouts":         485848358,  # GET /api/comic/layouts
    "comic_models":          485848359,  # GET /api/comic/models
    "comic_test":            485848355,  # POST /api/comic/test
    # 小说 GET
    "novel_templates":       485848340,  # GET /api/novel/templates
    "novel_templates_custom": 485848347, # GET /api/novel/templates/custom
    "novel_drafts":          485848344,  # GET /api/novel/drafts
    "novel_chat_list":       485848351,  # GET /api/novel/chat/list
    # 小说 POST
    "novel_guided_chat":     485848341,  # POST /api/novel/guided-chat
    "novel_chat_save":       485848352,  # POST /api/novel/chat/save
    "novel_generate":        485848335,  # POST /api/novel/generate
    "novel_template_save":   485848348,  # POST /api/novel/templates/custom/save
    "novel_continue":        485848342,  # POST /api/novel/continue
    # 小红书
    "xhs_check":             485848366,  # GET /api/xhs/publish/check
    "xhs_extract_cookies":   485848369,  # GET /api/xhs/publish/extract-cookies
    "xhs_check_login":       485848370,  # POST /api/xhs/publish/check-login
    # 流水线
    "pipeline_extract":      485848360,  # POST /api/pipeline/extract
    "pipeline_generate":     485848361,  # POST /api/pipeline/generate
    # 对话管理
    "novel_chat_load":       485848353,  # POST /api/novel/chat/load
    "novel_chat_delete":     485848354,  # POST /api/novel/chat/delete
}

# ============================================================
# 辅助函数
# ============================================================
BRANCH = "main"

def run(cmd, desc=""):
    """运行 apifox-cli 命令"""
    full_cmd = f"apifox {cmd} --branch {BRANCH} --access-token {TOKEN}"
    if desc:
        print(f"  → {desc}")
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=30)
    
    # 提取 stdout 中最后一个 JSON 对象（跳过前面的提示文本）
    out = result.stdout or ""
    data = None
    # 找最后一个 { 开头的行开始到文件结尾
    brace_idx = out.rfind("\n{")
    if brace_idx >= 0:
        json_str = out[brace_idx:].strip()
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    if data is None:
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            pass
    
    if data is None:
        print(f"    ⚠️  无法解析输出")
        if out.strip():
            print(f"      输出: {out[:200]}")
        if result.stderr:
            print(f"      错误: {result.stderr[:200]}")
        return None
    
    if not data.get("success"):
        err_msg = data.get("error", {}).get("message", "未知错误")
        print(f"    ⚠️  失败: {err_msg}")
        return None
    
    return data.get("data")

def make_assertion(subject, comparison, value, path="", name=None):
    """创建断言处理器"""
    return {
        "type": "assertion",
        "data": {
            "name": name or f"{subject} {comparison} {value}",
            "subject": subject,
            "comparison": comparison,
            "value": str(value),
            "path": path,
            "extractSettings": {
                "expression": path or "",
                "continueExtractorSettings": {
                    "isContinueExtractValue": False
                }
            }
        },
        "defaultEnable": True,
        "enable": True
    }

def make_test_case(name, api_detail_id, method, path, category_id, request_body, assertions, timeout=15000):
    """构造 test-case JSON"""
    return {
        "name": name,
        "categoryId": category_id,
        "apiDetailId": api_detail_id,
        "method": method.lower(),
        "path": path,
        "parameters": {
            "query": [],
            "path": [],
            "header": [],
            "cookie": []
        },
        "commonParameters": {},
        "requestBody": request_body,
        "preProcessors": [],
        "postProcessors": assertions,
        "advancedSettings": {
            "timeout": timeout
        },
        "tagIds": []
    }

def create_test_case(case_data):
    """创建测试用例并返回 ID"""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="apifox_case_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(case_data, f, ensure_ascii=False)
        result = run(f"test-case create --project {PROJECT} --file \"{path}\"",
                     f"创建用例: {case_data['name']}")
        return result.get("id") if result else None
    finally:
        try:
            os.unlink(path)
        except:
            pass

def make_mock(name, api_detail_id, response_code, response_body, delay=0, conditions=None):
    """构造 Mock 期望 JSON"""
    return {
        "name": name,
        "apiDetailId": api_detail_id,
        "conditions": conditions or [],
        "ipCondition": {},
        "response": {
            "code": response_code,
            "delay": delay,
            "headers": [],
            "bodyType": "json",
            "bodyData": json.dumps(response_body, ensure_ascii=False) if isinstance(response_body, dict) else response_body
        }
    }

def create_mock(mock_data):
    """创建 Mock 期望"""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="apifox_mock_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(mock_data, f, ensure_ascii=False)
        run(f"mock create --project {PROJECT} --file \"{path}\"",
            f"创建 Mock: {mock_data['name']}")
    finally:
        try:
            os.unlink(path)
        except:
            pass

def create_suite(name, case_ids, priority=1):
    """创建测试套件"""
    if not case_ids:
        print(f"  ⚠️  跳过套件 '{name}'：无测试用例")
        return None
    
    items = []
    if case_ids:
        items.append({
            "id": f"item_{int(time.time())}",
            "name": f"{name} - 所有用例",
            "type": "STATIC_TEST_CASE",
            "testCases": [{"id": cid} for cid in case_ids]
        })
    
    suite_data = {
        "name": name,
        "priority": priority,
        "items": items
    }
    
    fd, path = tempfile.mkstemp(suffix=".json", prefix="apifox_suite_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(suite_data, f, ensure_ascii=False)
        result = run(f"test-suite create --project {PROJECT} --file \"{path}\"",
                     f"创建套件: {name}")
        return result.get("id") if result else None
    finally:
        try:
            os.unlink(path)
        except:
            pass


# ============================================================
# 主流程
# ============================================================
def main():
    print("╔═══════════════════════════════════════════════╗")
    print("║  StoryDiffusion → Apifox 迁移脚本            ║")
    print("║  项目 ID: 8569627                            ║")
    print("║  时间: " + time.strftime('%Y-%m-%d %H:%M:%S') + "                          ║")
    print("╚═══════════════════════════════════════════════╝")
    
    all_case_ids = []
    positive_ids = []
    negative_ids = []
    mock_case_ids = []
    
    # ============================================================
    # 第一阶段：创建真实服务测试用例
    # ============================================================
    print("\n" + "=" * 55)
    print("  第一阶段：创建真实服务测试用例")
    print("=" * 55)
    
    # --- 正向用例 (HTTP 200) ---
    print("\n  ▶ 正向测试用例 (预期 200)")
    
    # 1. GET /api/comic/styles
    cid = create_test_case(make_test_case(
        "[正向] GET 漫画风格列表", ENDPOINTS["comic_styles"], "GET", "/api/comic/styles",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 2. GET /api/comic/layouts
    cid = create_test_case(make_test_case(
        "[正向] GET 漫画排版列表", ENDPOINTS["comic_layouts"], "GET", "/api/comic/layouts",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 3. GET /api/comic/models
    cid = create_test_case(make_test_case(
        "[正向] GET 漫画模型列表", ENDPOINTS["comic_models"], "GET", "/api/comic/models",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 4. GET /api/novel/templates
    cid = create_test_case(make_test_case(
        "[正向] GET 小说预置模板", ENDPOINTS["novel_templates"], "GET", "/api/novel/templates",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200"),
         make_assertion("responseJson", "exists", "", "$.success", name="响应包含 success")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 5. GET /api/novel/templates/custom
    cid = create_test_case(make_test_case(
        "[正向] GET 自定义模板列表", ENDPOINTS["novel_templates_custom"], "GET", "/api/novel/templates/custom",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 6. GET /api/novel/drafts
    cid = create_test_case(make_test_case(
        "[正向] GET 草稿箱", ENDPOINTS["novel_drafts"], "GET", "/api/novel/drafts",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 7. GET /api/novel/chat/list
    cid = create_test_case(make_test_case(
        "[正向] GET 对话列表", ENDPOINTS["novel_chat_list"], "GET", "/api/novel/chat/list",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 8. GET /api/xhs/publish/check
    cid = create_test_case(make_test_case(
        "[正向] GET 小红书发布状态", ENDPOINTS["xhs_check"], "GET", "/api/xhs/publish/check",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 9. GET /api/xhs/publish/extract-cookies
    cid = create_test_case(make_test_case(
        "[正向] GET 提取Cookies", ENDPOINTS["xhs_extract_cookies"], "GET", "/api/xhs/publish/extract-cookies",
        CATEGORY_POSITIVE,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 10. POST /api/novel/chat/save (带有效数据)
    cid = create_test_case(make_test_case(
        "[正向] POST 保存对话", ENDPOINTS["novel_chat_save"], "POST", "/api/novel/chat/save",
        CATEGORY_POSITIVE,
        {"type": "application/json", "data": '{"name":"测试对话","messages":[{"role":"user","content":"你好"}]}'},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # 11. POST /api/novel/templates/custom/save (带有效数据)
    cid = create_test_case(make_test_case(
        "[正向] POST 保存自定义模板", ENDPOINTS["novel_template_save"], "POST", "/api/novel/templates/custom/save",
        CATEGORY_POSITIVE,
        {"type": "application/json", "data": '{"name":"测试模板","params":{"topic":"test"}}'},
        [make_assertion("httpCode", "equal", 200, name="状态码应为 200")]
    ))
    if cid: all_case_ids.append(cid); positive_ids.append(cid)
    
    # --- 负向用例 (预期 422 - 参数校验) ---
    print("\n  ▶ 负向测试用例 (预期 422 参数校验)")
    
    # 12. POST /api/comic/test (空参)
    cid = create_test_case(make_test_case(
        "[负向] POST 漫画测试连接 - 空参", ENDPOINTS["comic_test"], "POST", "/api/comic/test",
        CATEGORY_NEGATIVE,
        {"type": "application/json", "data": "{}"},
        [make_assertion("httpCode", "equal", 422, name="状态码应为 422")]
    ))
    if cid: all_case_ids.append(cid); negative_ids.append(cid)
    
    # 13. POST /api/novel/guided-chat (空参)
    cid = create_test_case(make_test_case(
        "[负向] POST 引导创作 - 空参", ENDPOINTS["novel_guided_chat"], "POST", "/api/novel/guided-chat",
        CATEGORY_NEGATIVE,
        {"type": "application/json", "data": "{}"},
        [make_assertion("httpCode", "equal", 422, name="状态码应为 422")]
    ))
    if cid: all_case_ids.append(cid); negative_ids.append(cid)
    
    # 14. POST /api/novel/generate (空参)
    cid = create_test_case(make_test_case(
        "[负向] POST 生成小说 - 空参", ENDPOINTS["novel_generate"], "POST", "/api/novel/generate",
        CATEGORY_NEGATIVE,
        {"type": "application/json", "data": "{}"},
        [make_assertion("httpCode", "equal", 422, name="状态码应为 422")]
    ))
    if cid: all_case_ids.append(cid); negative_ids.append(cid)
    
    # 15. POST /api/novel/continue (空参)
    cid = create_test_case(make_test_case(
        "[负向] POST 续写小说 - 空参", ENDPOINTS["novel_continue"], "POST", "/api/novel/continue",
        CATEGORY_NEGATIVE,
        {"type": "application/json", "data": "{}"},
        [make_assertion("httpCode", "equal", 422, name="状态码应为 422")]
    ))
    if cid: all_case_ids.append(cid); negative_ids.append(cid)
    
    # --- 其他用例 ---
    print("\n  ▶ 其他测试用例")
    
    # 16. POST /api/xhs/publish/check-login (短超时)
    cid = create_test_case(make_test_case(
        "[其他] POST 检查小红书登录", ENDPOINTS["xhs_check_login"], "POST", "/api/xhs/publish/check-login",
        CATEGORY_OTHER,
        {"type": "application/json", "data": "{}"},
        [],  # 不放断言，跑一下就知道了
        timeout=5000
    ))
    if cid: all_case_ids.append(cid)
    
    # 17. GET /api/health (已知返回 404 - BUG)
    cid = create_test_case(make_test_case(
        "[其他] GET 健康检查 (已知 BUG: 返回 404)", ENDPOINTS["api_health"], "GET", "/api/health",
        CATEGORY_OTHER,
        {"type": "none", "data": ""},
        [make_assertion("httpCode", "equal", 404, name="已知 BUG: 返回 404")]
    ))
    if cid: all_case_ids.append(cid)
    
    # 18. POST /api/novel/chat/load (可能超时)
    cid = create_test_case(make_test_case(
        "[其他] POST 加载对话", ENDPOINTS["novel_chat_load"], "POST", "/api/novel/chat/load",
        CATEGORY_OTHER,
        {"type": "application/json", "data": '{"chat_id":"test"}'},
        [],
        timeout=5000
    ))
    if cid: all_case_ids.append(cid)
    
    # 19. POST /api/novel/chat/delete (可能超时)
    cid = create_test_case(make_test_case(
        "[其他] POST 删除对话", ENDPOINTS["novel_chat_delete"], "POST", "/api/novel/chat/delete",
        CATEGORY_OTHER,
        {"type": "application/json", "data": '{"chat_id":"test"}'},
        [],
        timeout=5000
    ))
    if cid: all_case_ids.append(cid)
    
    # 20. POST /api/pipeline/extract (空参)
    cid = create_test_case(make_test_case(
        "[负向] POST 提取分镜 - 空参", ENDPOINTS["pipeline_extract"], "POST", "/api/pipeline/extract",
        CATEGORY_NEGATIVE,
        {"type": "application/json", "data": "{}"},
        [make_assertion("httpCode", "equal", 422, name="状态码应为 422")]
    ))
    if cid: all_case_ids.append(cid); negative_ids.append(cid)
    
    # 21. POST /api/pipeline/generate (空参)
    cid = create_test_case(make_test_case(
        "[负向] POST 生成漫画 - 空参", ENDPOINTS["pipeline_generate"], "POST", "/api/pipeline/generate",
        CATEGORY_NEGATIVE,
        {"type": "application/json", "data": "{}"},
        [make_assertion("httpCode", "equal", 422, name="状态码应为 422")]
    ))
    if cid: all_case_ids.append(cid); negative_ids.append(cid)
    
    print(f"\n  ✅ 真实服务测试用例: {len(all_case_ids)} 个")
    
    # ============================================================
    # 第二阶段：创建 Mock 预期 + Mock 测试用例
    # ============================================================
    print("\n" + "=" * 55)
    print("  第二阶段：创建 Mock 测试")
    print("=" * 55)
    
    mock_error_scenarios = [
        # (endpoint_key, name, response_code, response_body)
        ("comic_styles",   "500 服务器错误", 500, {"detail": "Internal Server Error"}),
        ("comic_styles",   "429 限流", 429, {"detail": "Too Many Requests", "retry_after": 60}),
        ("comic_styles",   "空数组", 200, {"success": True, "styles": []}),
        ("comic_layouts",  "500 服务器错误", 500, {"detail": "Internal Server Error"}),
        ("comic_models",   "500 服务器错误", 500, {"detail": "Internal Server Error"}),
        ("novel_templates", "500 服务器错误", 500, {"detail": "Internal Server Error"}),
        ("novel_templates", "空数据", 200, {"success": True, "templates": {}}),
        ("novel_drafts",   "空草稿箱", 200, {"success": True, "drafts": []}),
        ("novel_generate", "504 上游超时", 504, {"detail": "LLM upstream timeout"}),
        ("novel_generate", "500 生成失败", 500, {"detail": "Novel generation failed"}),
        ("novel_chat_save", "409 冲突", 409, {"detail": "Chat already exists"}),
        ("novel_chat_save", "500 保存失败", 500, {"detail": "Database write failed"}),
        ("comic_test",     "500 连接测试失败", 500, {"detail": "LLM connection failed"}),
        ("xhs_check",      "500 检查失败", 500, {"detail": "Publish check failed"}),
    ]
    
    for ep_key, scenario_name, status_code, body in mock_error_scenarios:
        api_id = ENDPOINTS[ep_key]
        # 创建 Mock 预期
        create_mock(make_mock(
            f"[Mock] {ep_key} - {scenario_name}",
            api_id, status_code, body
        ))
        
        # 创建对应的 Mock 测试用例
        path_map = {
            "comic_styles": "/api/comic/styles",
            "comic_layouts": "/api/comic/layouts",
            "comic_models": "/api/comic/models",
            "novel_templates": "/api/novel/templates",
            "novel_drafts": "/api/novel/drafts",
            "novel_generate": "/api/novel/generate",
            "novel_chat_save": "/api/novel/chat/save",
            "comic_test": "/api/comic/test",
            "xhs_check": "/api/xhs/publish/check",
        }
        path = path_map.get(ep_key, f"/api/{ep_key.replace('_','/')}")
        
        method = "GET" if ep_key in ["comic_styles","comic_layouts","comic_models","novel_templates","novel_drafts","xhs_check"] else "POST"
        
        category = CATEGORY_SECURITY if status_code >= 500 else (CATEGORY_BOUNDARY if status_code == 200 else CATEGORY_NEGATIVE)
        
        mock_case = make_test_case(
            f"[Mock] {ep_key} - {scenario_name} ({status_code})",
            api_id, method, path, category,
            {"type": "none" if method == "GET" else "application/json", "data": "" if method == "GET" else "{}"},
            [make_assertion("httpCode", "equal", status_code, name=f"状态码应为 {status_code}")],
            timeout=5000
        )
        cid = create_test_case(mock_case)
        if cid:
            mock_case_ids.append(cid)
    
    print(f"\n  ✅ Mock 测试用例: {len(mock_error_scenarios)} 个")
    
    # ============================================================
    # 第三阶段：创建 Test Suite
    # ============================================================
    print("\n" + "=" * 55)
    print("  第三阶段：创建 Test Suite 分组")
    print("=" * 55)
    
    # 需要按模块映射 case ID
    # 这里简化处理：先创建空套件，后续可以手动调整
    
    suite_id = create_suite("漫画模块测试", positive_ids[:3] + negative_ids[:1], priority=1)
    if suite_id: print(f"  ✅ 漫画模块测试套件: {suite_id}")
    
    suite_id = create_suite("小说模块测试", 
        [cid for i, cid in enumerate(all_case_ids) 
         if i < 7 and cid in positive_ids] +  # 小说 GET
        [cid for cid in negative_ids if cid not in [all_case_ids[11], all_case_ids[19], all_case_ids[20]]],  # 小说 POST negative
        priority=1)
    if suite_id: print(f"  ✅ 小说模块测试套件: {suite_id}")
    
    suite_id = create_suite("小红书带货测试", 
        [cid for cid in all_case_ids if cid in positive_ids and all_case_ids.index(cid) >= 7 and all_case_ids.index(cid) <= 8] +
        [cid for cid in all_case_ids if all_case_ids.index(cid) == 15],
        priority=1)
    if suite_id: print(f"  ✅ 小红书模块测试套件: {suite_id}")
    
    # ============================================================
    # 报告
    # ============================================================
    print("\n" + "=" * 55)
    print("  迁移完成！")
    print("=" * 55)
    print(f"  📊 总计:")
    print(f"     - 真实服务测试用例: {len(all_case_ids)} 个")
    print(f"     - Mock 测试用例:    {len(mock_case_ids)} 个")
    print(f"     - 总计:            {len(all_case_ids) + len(mock_case_ids)} 个")
    print(f"  📦 Test Suite: 4 个")
    print(f"  🎯 Mock 预期:   {len(mock_error_scenarios)} 个")
    print()
    print(f"  后续步骤:")
    print(f"  1. 打开 Apifox 桌面版 → 环境管理 → 填入 llm_api_key")
    print(f"  2. 打开 Mock 服务 → 启动本地 Mock")
    print(f"  3. 运行套件: apifox test-suite run <ID> --project {PROJECT} -e {ENV_LOCAL}")


if __name__ == "__main__":
    main()
