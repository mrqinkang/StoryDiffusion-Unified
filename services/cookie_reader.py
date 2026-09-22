# services/cookie_reader.py
"""从本地 Chrome/Edge 浏览器提取小红书 cookies

在 Windows 上，Chrome/Edge 的 cookies 储存在 SQLite 数据库中，
值使用 Windows DPAPI (CryptProtectData) 加密。
此模块尝试读取这些 cookies 并转换为 xhs-mcp 的 cookies.json 格式。
"""

import os
import json
import time
import logging
import sqlite3
import shutil
import tempfile

logger = logging.getLogger("cookie_reader")

# 浏览器 cookie 数据库路径
BROWSER_PATHS = [
    # Edge (Chromium-based) - 新路径
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Network\Cookies"),
    # Edge - 旧路径
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cookies"),
    # Chrome - 新路径
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies"),
    # Chrome - 旧路径
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cookies"),
]

# 360 极速浏览器
_360_PATH = os.path.expandvars(r"%LOCALAPPDATA%\360Chrome\Chrome\User Data\Default\Cookies")

# QQ 浏览器
QQ_PATH = os.path.expandvars(r"%LOCALAPPDATA%\Tencent\QQBrowser\User Data\Default\Cookies")


def _find_cookie_db() -> str | None:
    """查找存在且可读的浏览器 cookie 数据库"""
    for p in BROWSER_PATHS:
        if os.path.exists(p):
            logger.info("发现 cookie 数据库: %s", p)
            return p
    # 尝试 360 浏览器
    if os.path.exists(_360_PATH):
        logger.info("发现 360 浏览器 cookie 数据库")
        return _360_PATH
    return None


def extract_xhs_cookies() -> list[dict]:
    """从本机浏览器提取小红书 cookies

    Returns:
        xhs-mcp 格式的 cookies 列表（空列表表示提取失败）
    """
    db_path = _find_cookie_db()
    if not db_path:
        logger.warning("未找到浏览器 cookie 数据库")
        return []

    try:
        return _read_cookies_from_db(db_path)
    except Exception as e:
        logger.exception("读取 cookies 失败: %s", e)
        return []


def _read_cookies_from_db(db_path: str) -> list[dict]:
    """从 SQLite cookie 数据库读取 xiaohongshu.com 的 cookies"""
    import win32crypt  # pywin32

    # 复制数据库到临时文件（避免浏览器锁冲突）
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    try:
        shutil.copy2(db_path, tmp_path)

        conn = sqlite3.connect(tmp_path)
        conn.text_factory = bytes  # 避免编码问题
        cursor = conn.cursor()

        # Chrome/Edge cookies 表结构
        cursor.execute(
            "SELECT host_key, name, value, encrypted_value, path, "
            "expires_utc, is_httponly, is_secure "
            "FROM cookies WHERE host_key LIKE '%xiaohongshu%' "
            "OR host_key LIKE '%xhs%'"
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            logger.warning("未找到小红书 cookies")
            return []

        cookies = []
        for row in rows:
            host_key_raw, name_raw, value_raw, encrypted_value, path_raw, expires_utc, is_httponly, is_secure = row

            # 解码 bytes
            host_key = host_key_raw.decode("utf-8") if isinstance(host_key_raw, bytes) else host_key_raw
            name = name_raw.decode("utf-8") if isinstance(name_raw, bytes) else name_raw
            value = value_raw.decode("utf-8") if isinstance(value_raw, bytes) else value_raw
            path = path_raw.decode("utf-8") if isinstance(path_raw, bytes) else path_raw

            # 尝试解密 encrypted_value
            if encrypted_value and encrypted_value != b"":
                try:
                    decrypted = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)
                    if decrypted and len(decrypted) > 1 and decrypted[1]:
                        value = decrypted[1].decode("utf-8")
                except Exception:
                    pass  # 使用 value 字段

            # 转换过期时间（Chrome 使用 1601-01-01 起的微秒）
            # -1 表示会话 cookie
            expires = -1
            if expires_utc and expires_utc > 0:
                expires = int(expires_utc / 1_000_000 - 11644473600)  # 转换为 Unix 时间戳

            cookie = {
                "name": name,
                "value": value,
                "domain": _normalize_domain(host_key),
                "path": path or "/",
                "expires": expires,
                "httpOnly": bool(is_httponly),
                "secure": bool(is_secure),
            }
            cookies.append(cookie)

        # 去重（相同 name + domain 保留最后一个）
        seen = set()
        deduped = []
        for c in reversed(cookies):
            key = (c["name"], c["domain"])
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        deduped.reverse()

        logger.info("成功提取 %d 个小红书 cookies（去重前 %d）", len(deduped), len(cookies))
        return deduped

    except Exception as e:
        logger.exception("读取 cookie 数据库失败")
        return []
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _normalize_domain(host_key: str) -> str:
    """将 host_key 标准化为 xhs-mcp 使用的 domain 格式"""
    host_key = host_key.strip().lower()
    if host_key.startswith("."):
        return host_key
    # 如果是子域名，加前导点
    if host_key.count(".") >= 2:
        return "." + host_key
    return host_key


def save_cookies_to_xhs_mcp(cookies: list[dict]) -> bool:
    """保存 cookies 到 xhs-mcp 的 cookies.json 文件

    Args:
        cookies: 符合 xhs-mcp 格式的 cookie 列表

    Returns:
        是否保存成功
    """
    cookies_dir = os.path.expanduser("~/.xhs-mcp")
    os.makedirs(cookies_dir, exist_ok=True)
    cookies_path = os.path.join(cookies_dir, "cookies.json")

    try:
        with open(cookies_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)
        logger.info("cookies 已保存到 %s (%d 个)", cookies_path, len(cookies))
        return True
    except Exception as e:
        logger.exception("保存 cookies 失败")
        return False


def verify_cookies(cookies: list[dict]) -> dict:
    """验证 cookies 是否有效（简单检查必要字段）

    Returns:
        {"valid": bool, "count": int, "has_session": bool, "message": str}
    """
    if not cookies:
        return {"valid": False, "count": 0, "has_session": False, "message": "没有 cookies"}

    # 检查关键 session cookie
    session_keys = [
        "galaxy_creator_session_id",
        "access-token-creator.xiaohongshu.com",
        "web_session",
        "customer-sso-sid",
        "a1",
    ]
    found = [c["name"] for c in cookies if c.get("name") in session_keys]

    has_session = bool(found)
    domain_ok = any("xiaohongshu.com" in c.get("domain", "") for c in cookies)

    if has_session and domain_ok:
        return {
            "valid": True,
            "count": len(cookies),
            "has_session": True,
            "session_keys": found,
            "message": f"找到 {len(found)} 个关键 session cookie，登录态有效",
        }
    elif has_session:
        return {
            "valid": True,
            "count": len(cookies),
            "has_session": True,
            "session_keys": found,
            "message": "找到 session cookie 但域名可能不完整",
        }
    else:
        return {
            "valid": False,
            "count": len(cookies),
            "has_session": False,
            "message": "缺少关键 session cookie，请确认已登录小红书",
        }
