# services/xhs_publisher.py
"""小红书自动发布器 - 通过 Playwright 浏览器自动化发布到创作中心"""

import os
import re
import json
import base64
import tempfile
import logging
from typing import Optional

logger = logging.getLogger("xhs_publisher")

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning("playwright 未安装，发布功能不可用")


STORAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "xhs_auth.json",
)


class XHSPublisher:
    """小红书自动发布器"""

    def __init__(self):
        self._storage_path = STORAGE_PATH

    def is_playwright_available(self) -> bool:
        """检查 Playwright 是否已安装"""
        return PLAYWRIGHT_AVAILABLE

    def is_logged_in(self) -> bool:
        """检查是否有保存的登录态"""
        return os.path.exists(self._storage_path)

    def _ensure_storage_dir(self):
        """确保存储登录态的目录存在"""
        os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)

    async def _page_has_publish_form(self, page) -> bool:
        """判断页面是否已显示发布表单（而非登录页）"""
        try:
            # 查找发布页的关键元素：文件上传 input 或发布按钮
            await page.locator('input[type="file"]').first.wait_for(
                state="attached", timeout=5000
            )
            return True
        except (PlaywrightTimeout, Exception):
            pass
        try:
            # 也可能用其他方式检测：是否有"发布笔记"之类标题
            body_text = await page.locator("body").text_content(timeout=3000)
            if body_text and ("发布" in body_text or "上传" in body_text):
                return True
        except Exception:
            pass
        return False

    async def publish(
        self,
        title: str,
        content: str,
        image_base64_list: list[str],
        tags: list[str] = None,
        headless: bool = False,
    ) -> dict:
        """发布到小红书创作中心

        Args:
            title: 标题（最多20字）
            content: 正文
            image_base64_list: 图片 base64 data URI 列表
            tags: 标签列表，如 ["#好物分享", "#日常必备"]
            headless: 是否无头模式（默认 False，会看到浏览器窗口）

        Returns:
            {"success": bool, "message": str, "url": str}
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "success": False,
                "message": "Playwright 未安装。请运行: pip install playwright && playwright install chromium",
            }

        if not image_base64_list:
            return {"success": False, "message": "没有可发布的图片"}

        tags = tags or []
        self._ensure_storage_dir()

        # 将 base64 图片保存到临时文件
        temp_files = []
        try:
            for b64data in image_base64_list:
                # 处理 data URI 格式: data:image/png;base64,xxx
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

            # 拼接正文 + 标签
            full_content = content.strip()
            if tags:
                full_content += "\n\n" + " ".join(tags)

            # 启动浏览器并发布
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )

                # 加载之前保存的登录态
                auth_path = self._storage_path if os.path.exists(self._storage_path) else None
                context = await browser.new_context(
                    storage_state=auth_path,
                    locale="zh-CN",
                )

                page = await context.new_page()

                # 打开小红书创作中心（使用 domcontentloaded 避免等待所有资源）
                logger.info("正在打开小红书创作中心...")
                await page.goto(
                    "https://creator.xiaohongshu.com/publish/publish",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                # 等待 SPA 渲染完成
                await page.wait_for_timeout(5000)

                # ----- 检测登录状态 -----
                logged_in = await self._page_has_publish_form(page)
                if not logged_in:
                    logger.info("未检测到发布表单，需要登录小红书...")
                    # 页面可能显示登录界面（SPA 内嵌，URL 不变）
                    # 尝试找到登录二维码/方式，提示用户
                    await page.wait_for_timeout(2000)

                    # 轮询等待用户完成登录（最多5分钟）
                    login_successful = False
                    for _ in range(60):
                        await page.wait_for_timeout(5000)
                        if await self._page_has_publish_form(page):
                            login_successful = True
                            break
                        logger.info("等待用户扫码登录...")

                    if not login_successful:
                        return {
                            "success": False,
                            "message": "登录超时。请在打开的浏览器窗口中扫码登录小红书账号，然后重试发布。",
                        }

                    # 登录成功，保存登录态
                    await context.storage_state(path=self._storage_path)
                    logger.info("登录态已保存到 %s", self._storage_path)

                # ----- 发布表单已就绪，开始填写内容 -----
                # 等待页面完全渲染
                await page.wait_for_timeout(2000)

                # 上传图片
                upload_success = False
                try:
                    # 优先使用 file input
                    file_input = page.locator('input[type="file"]').first
                    if await file_input.is_visible(timeout=3000):
                        await file_input.set_input_files(temp_files)
                        logger.info(f"已上传 {len(temp_files)} 张图片")
                        upload_success = True
                    else:
                        # 尝试通过拖拽区域上传
                        await page.set_input_files('input[type="file"]', temp_files)
                        upload_success = True
                except Exception as e:
                    logger.warning(f"上传图片方式1失败: {e}")
                    try:
                        # 备用：通过 JavaScript 添加文件
                        await page.evaluate("""(files) => {
                            const input = document.querySelector('input[type="file"]');
                            if (!input) throw new Error('找不到文件上传控件');
                            const dt = new DataTransfer();
                            for (const f of files) dt.items.add(f);
                            input.files = dt.files;
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                        }""", temp_files)
                        upload_success = True
                    except Exception as e2:
                        logger.warning(f"上传图片方式2失败: {e2}")
                        # 不中断流程，让用户手动上传

                # 等待上传完成
                if upload_success:
                    await page.wait_for_timeout(3000)
                else:
                    logger.warning("所有上传方式均失败，请手动上传图片")

                # 填写标题
                try:
                    title_input = page.locator(
                        '[placeholder*="标题"], '
                        '[placeholder*="title"], '
                        '[class*="title"] input, '
                        'input[class*="title"]'
                    ).first
                    if await title_input.is_visible(timeout=3000):
                        await title_input.fill("")
                        await page.wait_for_timeout(300)
                        await title_input.fill(title[:20])
                        logger.info(f"已填写标题: {title[:20]}")
                except Exception as e:
                    logger.warning(f"填写标题失败: {e}")

                # 填写正文
                try:
                    content_editor = page.locator(
                        '[placeholder*="正文"], '
                        '[placeholder*="正文内容"], '
                        '[contenteditable="true"], '
                        '[class*="ql-editor"], '
                        '.ql-editor'
                    ).first
                    if await content_editor.is_visible(timeout=3000):
                        await content_editor.fill("")
                        await page.wait_for_timeout(300)
                        await content_editor.fill(full_content)
                        logger.info("已填写正文")
                except Exception as e:
                    logger.warning(f"填写正文失败: {e}")

                # 如果所有自动填充都失败，给出更明确的提示
                filled_something = upload_success
                msg = "内容已填充到小红书发布页面，请检查后手动点击「发布」按钮"
                note = "首次使用需要扫码登录，之后自动保持登录态"
                if not filled_something:
                    msg = (
                        "浏览器已打开到小红书发布页面，但自动填充未完全成功。"
                        "请手动上传图片、填写标题和正文，然后点击发布。"
                    )
                    note = "登录态已保存，下次可自动发布"

                return {
                    "success": True,
                    "message": msg,
                    "url": page.url,
                    "note": note,
                }

        except Exception as e:
            logger.exception("发布过程异常")
            err_msg = str(e)[:300]
            return {"success": False, "message": f"发布失败: {err_msg}"}

        finally:
            # 清理临时文件
            for f in temp_files:
                try:
                    os.unlink(f)
                except Exception:
                    pass
