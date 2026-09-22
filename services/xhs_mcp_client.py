# services/xhs_mcp_client.py
"""小红书 MCP 客户端 - 通过 xhs-mcp 服务发布内容到小红书

使用原始 JSON-RPC over stdio 协议与 xhs-mcp 通信，避免依赖 anyio/MCP SDK 的复杂上下文管理。
"""

import os
import re
import json
import base64
import tempfile
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("xhs_mcp_client")

MCP_AVAILABLE = False
MCP_SERVER_PATH = ""

# 查找 xhs-mcp 入口文件（npx 在 Windows 上是 .ps1 文件，create_subprocess_exec 无法直接运行）
_potential_paths = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "node_modules", "xhs-mcp", "dist", "xhs-mcp.cjs"),
    "D:\\nodejs\\npm_global\\node_modules\\xhs-mcp\\dist\\xhs-mcp.cjs",
    "C:\\Users\\Administrator\\AppData\\Roaming\\npm\\node_modules\\xhs-mcp\\dist\\xhs-mcp.cjs",
    "C:\\Users\\Administrator\\AppData\\Local\\npm\\node_modules\\xhs-mcp\\dist\\xhs-mcp.cjs",
]
for _p in _potential_paths:
    _abs = os.path.abspath(_p)
    if os.path.exists(_abs):
        MCP_SERVER_PATH = _abs
        break

if not MCP_SERVER_PATH:
    import shutil
    _npx = shutil.which("npx")
    if _npx:
        _npx_dir = os.path.dirname(os.path.abspath(_npx))
        _candidate = os.path.join(_npx_dir, "node_modules", "xhs-mcp", "dist", "xhs-mcp.cjs")
        if os.path.exists(_candidate):
            MCP_SERVER_PATH = _candidate

if MCP_SERVER_PATH:
    MCP_AVAILABLE = True
    logger.info("xhs-mcp 路径: %s", MCP_SERVER_PATH)
else:
    logger.warning("未找到 xhs-mcp 入口文件，发布功能不可用")


class XHSMCPClient:
    """小红书 MCP 客户端 - 通过 xhs-mcp 工具发布内容（原始 JSON-RPC over stdio）"""

    _instance = None
    _proc: asyncio.subprocess.Process = None
    _lock = asyncio.Lock()
    _msg_id = 0
    _pending_responses: dict[int, asyncio.Future] = {}
    _reader_task: asyncio.Task = None
    _buffer = b""

    @classmethod
    def is_available(cls) -> bool:
        """检查 xhs-mcp 是否可用"""
        return MCP_AVAILABLE

    @classmethod
    def is_logged_in_cached(cls) -> bool:
        """快速检查是否有缓存的登录态（不启动 MCP 服务）"""
        cookies_path = os.path.expanduser("~/.xhs-mcp/cookies.json")
        if os.path.exists(cookies_path):
            try:
                with open(cookies_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                return isinstance(cookies, list) and len(cookies) > 10
            except Exception:
                pass
        alt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "xhs_auth.json",
        )
        return os.path.exists(alt_path)

    async def _ensure_connected(self):
        """确保 xhs-mcp 进程已启动并完成握手"""
        mcp_proc = getattr(self, '_mcp_proc', None)
        if mcp_proc and mcp_proc.returncode is None:
            return  # 已在运行

        async with self._lock:
            mcp_proc = getattr(self, '_mcp_proc', None)
            if mcp_proc and mcp_proc.returncode is None:
                return

            logger.info("正在启动 xhs-mcp 服务...")
            # 【关键修复】Python 3.14 的 asyncio 子进程机制在 uvicorn 环境下有 Bug
            # （ProactorEventLoop._make_subprocess_transport 不生效）
            # 改用 threading + subprocess.Popen 完全绕过 asyncio 子进程
            import subprocess as _sp
            import threading as _th
            import queue as _q

            self._mcp_queue = _q.Queue()
            self._mcp_lock = _th.Lock()
            self._mcp_stop = False

            def _run_mcp():
                """在独立线程中运行 xhs-mcp 进程"""
                try:
                    # 设置 XHS_HEADLESS=false 让浏览器窗口可见，便于扫码登录
                    mcp_env = os.environ.copy()
                    mcp_env["XHS_HEADLESS"] = "false"
                    proc = _sp.Popen(
                        ["node", MCP_SERVER_PATH, "mcp"],
                        stdin=_sp.PIPE,
                        stdout=_sp.PIPE,
                        stderr=_sp.PIPE,
                        env=mcp_env,
                    )
                    self._mcp_proc = proc
                    self._mcp_ready.set()

                    # 持续读取 stdout 行并放入队列
                    for line in iter(proc.stdout.readline, b""):
                        if self._mcp_stop:
                            break
                        if line:
                            self._mcp_queue.put(("stdout", line))
                    
                    # 进程结束
                    proc.wait()
                    self._mcp_queue.put(("exit", proc.returncode))
                except Exception as e:
                    self._mcp_queue.put(("error", str(e)))

            self._mcp_ready = _th.Event()
            self._mcp_thread = _th.Thread(target=_run_mcp, daemon=True)
            self._mcp_thread.start()
            self._mcp_ready.wait(timeout=10)
            
            if not hasattr(self, '_mcp_proc') or self._mcp_proc is None:
                raise RuntimeError("xhs-mcp 进程启动失败")

            logger.info("xhs-mcp 进程已启动 (PID=%d)", self._mcp_proc.pid)

        # 在锁外执行握手
        result = await self._send_request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "xhs-publisher", "version": "1.0"},
        })
        logger.info("xhs-mcp 服务已就绪")
        return result

    async def _read_mcp_line(self, timeout: float = 10) -> bytes:
        """从 MCP 进程读取一行输出（通过线程队列桥接）"""
        import queue as _q
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("读取 MCP 输出超时")
            try:
                item = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._mcp_queue.get(timeout=min(remaining, 1))
                )
            except _q.Empty:
                continue
            
            kind, data = item
            if kind == "stdout":
                return data
            elif kind == "exit":
                raise ConnectionError(f"MCP 进程已退出，返回码: {data}")
            elif kind == "error":
                raise ConnectionError(f"MCP 进程错误: {data}")
            else:
                continue  # 忽略未知消息

    async def _send_request(self, method: str, params: dict = None, timeout: float = 120) -> dict:
        """发送 JSON-RPC 请求并等待响应（通过线程安全的方式）"""
        await self._ensure_connected()

        import queue as _q

        async with self._lock:
            self._msg_id += 1
            msg_id = self._msg_id

        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        data_str = json.dumps(request) + "\n"

        # 通过线程写入 stdin
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_stdin, data_str)

        # 从队列读取响应，直到找到匹配的 id
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"MCP 请求超时: {method}")

            try:
                item = await loop.run_in_executor(
                    None, lambda: self._mcp_queue.get(timeout=min(remaining, 1))
                )
            except _q.Empty:
                continue

            kind, data = item
            if kind == "exit":
                raise ConnectionError(f"MCP 进程已退出，返回码: {data}")
            elif kind == "error":
                raise ConnectionError(f"MCP 进程错误: {data}")
            elif kind != "stdout":
                continue

            # 解析 JSON-RPC 行
            try:
                msg = json.loads(data.decode("utf-8").strip())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            resp_id = msg.get("id")
            if resp_id == msg_id:
                if "error" in msg:
                    raise Exception(msg["error"].get("message", "RPC error"))
                return msg.get("result", {})
            # 其他 id 的响应忽略（可能是旧请求的响应）

    def _write_stdin(self, data: str):
        """向 MCP 进程写入数据（在独立线程中调用）"""
        proc = getattr(self, '_mcp_proc', None)
        if proc is None:
            raise ConnectionError("MCP 进程未启动")
        proc.stdin.write(data.encode("utf-8"))
        proc.stdin.flush()

    async def check_login(self) -> dict:
        """检查小红书登录状态"""
        if not MCP_AVAILABLE:
            return {"success": False, "logged_in": False, "status": "mcp_not_available"}

        try:
            result = await self._send_request("tools/call", {
                "name": "xhs_auth_status",
                "arguments": {},
            })
            # 解析返回的 content
            content_list = result.get("content", [])
            for item in content_list:
                text = item.get("text", "")
                if text:
                    data = json.loads(text)
                    return {
                        "success": data.get("success", False),
                        "logged_in": data.get("loggedIn", False),
                        "status": data.get("status", "unknown"),
                    }
            return {"success": True, "logged_in": False, "status": "no_data"}
        except Exception as e:
            logger.warning("检查登录状态失败: %s", e)
            return {"success": False, "logged_in": False, "status": f"error: {str(e)[:100]}"}

    async def login(self) -> dict:
        """打开浏览器进行小红书登录（扫码）"""
        if not MCP_AVAILABLE:
            return {"success": False, "message": "MCP 包未安装"}

        try:
            result = await self._send_request("tools/call", {
                "name": "xhs_auth_login",
                "arguments": {},
            })
            content_list = result.get("content", [])
            for item in content_list:
                text = item.get("text", "")
                if text:
                    data = json.loads(text)
                    return {
                        "success": data.get("success", False),
                        "message": data.get("message", "登录完成"),
                    }
            return {"success": True, "message": "登录流程已启动，请在打开的浏览器中扫码"}
        except Exception as e:
            logger.exception("登录失败")
            return {"success": False, "message": f"登录失败: {str(e)[:200]}"}

    async def publish(
        self,
        title: str,
        content: str,
        image_base64_list: list[str],
        tags: list[str] = None,
    ) -> dict:
        """发布到小红书（通过 xhs-mcp）

        Args:
            title: 标题（最多20字）
            content: 正文
            image_base64_list: 图片 base64 data URI 列表
            tags: 标签列表，如 ["#好物分享", "#日常必备"]

        Returns:
            {"success": bool, "message": str, "url": str}
        """
        if not MCP_AVAILABLE:
            return {"success": False, "message": "MCP 包未安装。请运行: pip install mcp"}

        if not image_base64_list:
            return {"success": False, "message": "没有可发布的图片"}

        tags = tags or []
        temp_files = []

        try:
            # 1. 将 base64 图片保存到临时文件
            for b64data in image_base64_list:
                if b64data.startswith("data:"):
                    header, data = b64data.split(";base64,", 1)
                    ext = "png"
                    mime_match = re.match(r"data:image/(\w+)", header)
                    if mime_match:
                        ext = mime_match.group(1)
                else:
                    data = b64data
                    ext = "png"

                f = tempfile.NamedTemporaryFile(
                    suffix=f".{ext}", delete=False,
                )
                f.write(base64.b64decode(data))
                f.close()
                temp_files.append(f.name)

            # 2. 确保与 MCP 服务已连接
            await self._ensure_connected()

            # 3. 检查登录状态
            login_check = await self.check_login()
            if not login_check.get("logged_in"):
                logger.warning("未登录小红书，请先登录")
                return {
                    "success": False,
                    "message": "未登录小红书账号。请先点击「登录小红书」按钮完成扫码登录后，再重新发布。",
                    "need_login": True,
                }

            # 4. 拼接标签到正文
            full_content = content.strip()
            if tags:
                full_content += "\n\n" + " ".join(tags)

            # 5. 发布内容
            logger.info(f"正在发布到小红书... ({len(temp_files)} 张图片)")
            publish_args = {
                "type": "image",
                "title": title[:20],
                "content": full_content[:1000],
                "media_paths": temp_files,
            }
            if tags:
                publish_args["tags"] = ",".join(tags)

            result = await self._send_request(
                "tools/call",
                {"name": "xhs_publish_content", "arguments": publish_args},
                timeout=300,  # 发布可能需要较长时间
            )

            # 6. 解析结果
            content_list = result.get("content", [])
            for item in content_list:
                text = item.get("text", "")
                if text:
                    try:
                        data = json.loads(text)
                        if data.get("success"):
                            return {
                                "success": True,
                                "message": "发布成功！内容已发布到小红书",
                                "url": data.get("url", "https://www.xiaohongshu.com"),
                                "note_id": data.get("note_id", ""),
                            }
                        else:
                            return {
                                "success": False,
                                "message": f"发布失败: {data.get('message', '未知错误')}",
                            }
                    except json.JSONDecodeError:
                        pass

            raw_text = content_list[0].get("text", "未知") if content_list else "未知"
            return {
                "success": True,
                "message": f"发布操作已完成: {raw_text[:200]}",
            }

        except TimeoutError:
            return {"success": False, "message": "发布超时，请稍后重试"}
        except Exception as e:
            logger.exception("MCP 发布过程异常")
            return {"success": False, "message": f"发布失败: {str(e)[:300]}"}

        finally:
            for f in temp_files:
                try:
                    os.unlink(f)
                except Exception:
                    pass
