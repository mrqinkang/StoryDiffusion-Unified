# -*- coding: utf-8 -*-
"""
StoryDiffusion 自动化 API 测试脚本
运行方式: python test_api.py
"""
import urllib.request
import urllib.error
import json
import time
import sys
import os

API_BASE = "http://localhost:8000"
passed = 0
failed = 0
total = 0
results = []


def request(method, path, body=None, timeout=10):
    """发送 HTTP 请求并返回 (status_code, response_body)"""
    url = API_BASE + path
    data = json.dumps(body).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    
    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        elapsed = int((time.time() - start) * 1000)
        content = resp.read().decode('utf-8')
        return (resp.status, content, elapsed)
    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        content = e.read().decode('utf-8')
        return (e.code, content, elapsed)
    except urllib.error.URLError as e:
        elapsed = int((time.time() - start) * 1000)
        return (0, str(e.reason), elapsed)
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return (0, f"{type(e).__name__}: {e}", elapsed)


def test(name, method, path, body=None, timeout=10):
    """执行一个测试用例"""
    global passed, failed, total
    total += 1
    code, content, elapsed = request(method, path, body, timeout=timeout)
    is_pass = 200 <= code < 300
    
    if is_pass:
        print(f"  ✅ {name}")
        print(f"     ({code} - {elapsed}ms)")
        passed += 1
    else:
        content_preview = content[:150] + "..." if len(content) > 150 else content
        print(f"  ❌ {name}")
        print(f"     ({code} - {elapsed}ms)")
        print(f"     响应: {content_preview}")
        failed += 1
    
    results.append({
        "name": name,
        "passed": is_pass,
        "code": code,
        "time_ms": elapsed
    })


def print_header(text):
    print()
    print("━" * 50)
    print(f"  {text}")
    print("━" * 50)


def generate_html_report(results, total, passed, failed, rate):
    """生成 HTML 测试报告文件"""
    timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"测试报告_{timestamp}.html"
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    
    # 构建模块统计
    modules = {}
    for r in results:
        if "/api/comic" in r["name"]:
            mod = "漫画模块"
        elif "/api/novel" in r["name"]:
            mod = "小说模块"
        elif "/api/xhs" in r["name"]:
            mod = "小红书带货"
        elif "/api/pipeline" in r["name"]:
            mod = "流水线"
        elif "health" in r["name"]:
            mod = "系统健康"
        else:
            mod = "其他"
        modules.setdefault(mod, {"total": 0, "passed": 0, "failed": 0})
        modules[mod]["total"] += 1
        if r["passed"]:
            modules[mod]["passed"] += 1
        else:
            modules[mod]["failed"] += 1
    
    # 构建每行结果
    detail_rows = ""
    for r in results:
        status_icon = "✅" if r["passed"] else "❌"
        status_text = "通过" if r["passed"] else "失败"
        color = "#27ae60" if r["passed"] else "#e74c3c"
        time_color = "#27ae60" if r["time_ms"] < 200 else ("#f39c12" if r["time_ms"] < 1000 else "#e74c3c")
        detail_rows += f"""
        <tr>
            <td>{r['name']}</td>
            <td style="color:{color};font-weight:bold">{status_icon} {status_text}</td>
            <td>{r['code']}</td>
            <td style="color:{time_color}">{r['time_ms']}ms</td>
        </tr>"""
    
    # 构建模块统计行
    module_rows = ""
    for mod_name, mod_data in sorted(modules.items()):
        mod_pct = round(mod_data["passed"] / mod_data["total"] * 100, 1) if mod_data["total"] > 0 else 0
        module_rows += f"""
        <div class="module-card">
            <div class="module-name">{mod_name}</div>
            <div class="module-stat">
                <span class="stat-pass">✅ {mod_data['passed']}</span>
                <span class="stat-fail">❌ {mod_data['failed']}</span>
                <span class="stat-total">共 {mod_data['total']}</span>
                <span class="stat-rate">{mod_pct}%</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width:{mod_pct}%"></div>
            </div>
        </div>"""
    
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>StoryDiffusion 测试报告</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f5f7fa; color:#333; }}
.header {{ background:linear-gradient(135deg,#667eea,#764ba2); color:#fff; padding:40px; text-align:center; }}
.header h1 {{ font-size:28px; margin-bottom:8px; }}
.header p {{ opacity:0.9; font-size:14px; }}
.summary {{ display:flex; justify-content:center; gap:30px; margin:-25px auto 0; padding:20px; max-width:600px; background:#fff; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.1); }}
.summary-item {{ text-align:center; }}
.summary-item .number {{ font-size:32px; font-weight:bold; }}
.summary-item .label {{ font-size:13px; color:#888; margin-top:4px; }}
.total-num {{ color:#333; }}
.pass-num {{ color:#27ae60; }}
.fail-num {{ color:#e74c3c; }}
.rate-num {{ color:#667eea; }}
.container {{ max-width:900px; margin:30px auto; padding:0 20px; }}
.section-title {{ font-size:18px; font-weight:600; color:#444; margin:25px 0 15px; padding-bottom:8px; border-bottom:2px solid #667eea; }}
.module-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:15px; }}
.module-card {{ background:#fff; border-radius:10px; padding:16px; box-shadow:0 2px 8px rgba(0,0,0,0.06); }}
.module-name {{ font-weight:600; font-size:15px; color:#444; margin-bottom:10px; }}
.module-stat {{ display:flex; gap:12px; margin-bottom:10px; font-size:13px; }}
.stat-pass {{ color:#27ae60; }}
.stat-fail {{ color:#e74c3c; }}
.stat-total {{ color:#888; }}
.stat-rate {{ color:#667eea; font-weight:bold; }}
.progress-bar {{ height:6px; background:#eee; border-radius:3px; overflow:hidden; }}
.progress-fill {{ height:100%; background:linear-gradient(90deg,#27ae60,#2ecc71); border-radius:3px; transition:width 0.5s; }}
table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.06); }}
th {{ background:#667eea; color:#fff; padding:12px 16px; text-align:left; font-size:14px; font-weight:500; }}
td {{ padding:10px 16px; border-bottom:1px solid #f0f0f0; font-size:14px; }}
tr:hover {{ background:#f8f9ff; }}
.footer {{ text-align:center; padding:30px; color:#999; font-size:13px; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; background:#e8f0fe; color:#667eea; }}
</style>
</head>
<body>
<div class="header">
    <h1>📊 StoryDiffusion 测试报告</h1>
    <p>项目: StoryDiffusion 小说漫画工作室 | 生成时间: {now}</p>
    <p style="margin-top:8px"><span class="tag">API 测试</span> <span class="tag">自动化测试</span> <span class="tag">HTTP {API_BASE}</span></p>
</div>

<div class="summary">
    <div class="summary-item">
        <div class="number total-num">{total}</div>
        <div class="label">总用例数</div>
    </div>
    <div class="summary-item">
        <div class="number pass-num">{passed}</div>
        <div class="label">✅ 通过</div>
    </div>
    <div class="summary-item">
        <div class="number fail-num">{failed}</div>
        <div class="label">❌ 失败</div>
    </div>
    <div class="summary-item">
        <div class="number rate-num">{rate}%</div>
        <div class="label">通过率</div>
    </div>
</div>

<div class="container">
    <div class="section-title">📦 模块概览</div>
    <div class="module-grid">
        {module_rows}
    </div>

    <div class="section-title">📋 详细结果</div>
    <table>
        <thead>
            <tr><th>接口名称</th><th>结果</th><th>状态码</th><th>耗时</th></tr>
        </thead>
        <tbody>
            {detail_rows}
        </tbody>
    </table>

    <div class="section-title">📌 说明</div>
    <div style="background:#fff;border-radius:10px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06);font-size:14px;line-height:1.8;color:#555;">
        <p>• ✅ = 接口正常响应 (HTTP 2xx)</p>
        <p>• ❌ = 接口异常 (4xx=参数问题, 5xx=服务器问题)</p>
        <p>• POST 接口返回 422 是因为请求体为空，参数校验生效，属于正常行为</p>
        <p>• 加载/删除对话返回 404 是因为该对话确实不存在，接口逻辑正确</p>
        <p>• 配置好 LLM API Key 后，小说生成类接口即可返回真实数据</p>
    </div>
</div>

<div class="footer">
    <p>StoryDiffusion 小说漫画工作室 · 自动化测试报告</p>
    <p style="margin-top:4px">Powered by Python + urllib</p>
</div>
</body>
</html>"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return filename


# ============================================================
# 主测试流程
# ============================================================
print("╔════════════════════════════════════════════════════╗")
print("║  StoryDiffusion 自动化 API 测试                    ║")
print(f"║  {time.strftime('%Y-%m-%d %H:%M:%S')}                              ║")
print("╚════════════════════════════════════════════════════╝")

# ===== 模块一：系统 =====
print_header("模块一：系统健康检查")
test("GET /api/health", "GET", "/api/health")

# ===== 模块二：漫画 =====
print_header("模块二：漫画模块")
test("GET /api/comic/styles -> 风格列表", "GET", "/api/comic/styles")
test("GET /api/comic/layouts -> 排版列表", "GET", "/api/comic/layouts")
test("GET /api/comic/models  -> 模型列表", "GET", "/api/comic/models")
test("POST /api/comic/test -> 测试连接(空参)", "POST", "/api/comic/test", {})

# ===== 模块三：小说 GET =====
print_header("模块三：小说模块 - GET 接口")
test("GET /api/novel/templates -> 预置模板", "GET", "/api/novel/templates")
test("GET /api/novel/templates/custom -> 自定义模板", "GET", "/api/novel/templates/custom")
test("GET /api/novel/drafts -> 草稿箱", "GET", "/api/novel/drafts")
test("GET /api/novel/chat/list -> 对话列表", "GET", "/api/novel/chat/list")

# ===== 模块四：小说 POST =====
print_header("模块四：小说模块 - POST 接口")
test("POST /api/novel/guided-chat -> 引导创作", "POST", "/api/novel/guided-chat", {})
test("POST /api/novel/chat/save -> 保存对话", "POST", "/api/novel/chat/save",
     {"name": "测试对话", "messages": [{"role": "user", "content": "你好"}]})
test("POST /api/novel/generate -> 生成小说", "POST", "/api/novel/generate", {})
test("POST /api/novel/templates/custom/save -> 保存模板", "POST",
     "/api/novel/templates/custom/save",
     {"name": "测试模板", "params": {"topic": "test"}})
test("POST /api/novel/continue -> 续写", "POST", "/api/novel/continue", {})

# ===== 模块五：小红书 =====
print_header("模块五：小红书带货模块")
test("GET /api/xhs/publish/check -> 发布状态检查", "GET", "/api/xhs/publish/check")
test("GET /api/xhs/publish/extract-cookies -> 提取Cookies", "GET",
     "/api/xhs/publish/extract-cookies")
test("POST /api/xhs/publish/check-login -> 检查登录", "POST",
     "/api/xhs/publish/check-login", timeout=5)

# ===== 模块六：流水线 =====
print_header("模块六：小说→漫画流水线")
test("POST /api/pipeline/extract -> 提取分镜", "POST", "/api/pipeline/extract", {})
test("POST /api/pipeline/generate -> 生成漫画", "POST", "/api/pipeline/generate", {})

# ===== 模块七：对话管理 =====
print_header("模块七：对话与模板管理")
test("POST /api/novel/chat/load -> 加载对话", "POST", "/api/novel/chat/load",
     {"chat_id": "test"})
test("POST /api/novel/chat/delete -> 删除对话", "POST", "/api/novel/chat/delete",
     {"chat_id": "test"})

# ============================================================
# 测试报告
# ============================================================
print()
print("═" * 50)
print("  测试报告")
print(f"  总计: {total} 个用例")
print(f"  ✅ 通过: {passed}" if passed > 0 else f"  ❌ 通过: {passed}")
print(f"  ❌ 失败: {failed}" if failed > 0 else f"  ✅ 失败: {failed}")
rate = round(passed / total * 100, 1) if total > 0 else 0
print(f"  通过率: {rate}%")
print("═" * 50)

print()
print("📌 测试结果分析:")
print("  ✅ = 接口正常响应 (HTTP 2xx)")
print("  ❌ = 接口异常 (4xx=参数问题, 5xx=服务器问题, timeout=超时)")
print()
print("💡 提示:")
print("  · POST 接口如果返回 400/422 是参数校验生效，属于正常行为")
print("  · 配置好 LLM 后小说生成类接口就能返回真实数据")
print()
report_file = generate_html_report(results, total, passed, failed, rate)
print(f"📄 HTML 测试报告已生成: {report_file}")
print("📄 测试脚本保存在: test_api.py")
print("   下次运行: python test_api.py")
