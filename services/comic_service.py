# services/comic_service.py
"""漫画生成服务 - 封装万相 API 调用与漫画排版"""

import os
import json
import random
import logging
from io import BytesIO
from typing import Optional, List
import numpy as np
from PIL import Image, ImageFont

from wanxiang_api import WanxiangAPI
from utils.utils import get_comic

logger = logging.getLogger("comic_service")

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"  # 微软雅黑，完整中文支持
PAD_IMAGE_PATH = "./images/pad_images.png"

STYLE_NAMES = [
    "(No style)", "Japanese Anime", "Comic book", "Line art",
    "Watercolor", "Pixel Art", "Black and White", "Traditional Chinese",
    "CG", "Oil Painting", "Sketch", "Chibi", "Chinese ink",
    "Impasto",
]

MODEL_CHOICES = ["wan2.7-image-pro", "wan2.7-image"]
SIZE_MAP = {
    "1K (1024*1024)": "1K",
    "2K (2048*2048)": "2K",
    "4K (4096*4096)": "4K",
    "手机竖屏 720*1280": "720*1280",
    "手机竖屏 1080*1920": "1080*1920",
}

DEFAULT_API_URL = (
    "https://dashscope.aliyuncs.com"
    "/api/v1/services/aigc/multimodal-generation/generation"
)

MAX_SEED = 2147483647


class ComicService:
    """漫画生成服务"""

    def __init__(self):
        self._api: Optional[WanxiangAPI] = None

    def _ensure_api(self, api_key: str, model: str, api_url: str = "") -> WanxiangAPI:
        """获取或创建 API 实例"""
        url = api_url if api_url else None
        if (self._api is None
                or self._api.api_key != api_key
                or self._api.model != model
                or self._api.base_url != (url or DEFAULT_API_URL)):
            self._api = WanxiangAPI(
                api_key=api_key,
                model=model,
                base_url=url,
            )
        return self._api

    def test_connection(self, api_key: str, model: str = "wan2.7-image-pro",
                        api_url: str = "") -> dict:
        """测试万相 API 连接"""
        if not api_key:
            return {"success": False, "message": "请填写 API Key"}
        try:
            api = self._ensure_api(api_key, model, api_url)
            urls = api.text_to_image(
                prompt="一只橘猫", size="1K", seed=42, n=1,
                thinking_mode=False,
            )
            if urls:
                return {"success": True, "message": "连接成功！万相模型可用"}
            return {"success": False, "message": "API 返回为空"}
        except Exception as e:
            return {"success": False, "message": str(e)[:200]}

    @staticmethod
    def _merge_prompts(prompts: List[str], batch_size: int) -> List[str]:
        """将连续的分镜 prompt 合并为复合提示词，减少 API 调用次数"""
        if batch_size <= 1:
            return prompts
        merged = []
        for i in range(0, len(prompts), batch_size):
            chunk = prompts[i:i+batch_size]
            if len(chunk) == 1:
                merged.append(chunk[0])
            else:
                # 纯中文自然描述：逐格说明画面内容，不要求模型理解"panel""triptych"等排版术语
                parts = [f"第{j+1}格：{p}" for j, p in enumerate(chunk)]
                merged.append(f"一张长图，从左到右平均分成{len(chunk)}个竖格，每格是一个独立完整的画面。{' '.join(parts)}")
        return merged

    @staticmethod
    def _trim_black_borders(img: Image.Image, threshold: int = 15) -> Image.Image:
        """裁剪图片四周的纯色/黑色空白边框"""
        arr = np.array(img)
        mask = np.any(arr > threshold, axis=2)
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if not rows.any() or not cols.any():
            return img
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]
        return img.crop((x_min, y_min, x_max + 1, y_max + 1))

    @staticmethod
    def _split_merged_image(img: Image.Image, num_panels: int) -> List[Image.Image]:
        """将合并生成的宽图按水平方向裁剪为独立格子

        先裁剪四周空白边框，再等分裁剪；添加微重叠避免画面切割。
        """
        if num_panels <= 1:
            return [img]
        # 先裁剪空白边框
        img = ComicService._trim_black_borders(img)
        w, h = img.size
        pw = w // num_panels
        panels = []
        for i in range(num_panels):
            left = max(0, i * pw - 4)
            right = min(w, (i + 1) * pw + 4)
            panel = img.crop((left, 0, right, h))
            # 缩放回标准宽度（消除重叠偏移）
            panel = panel.resize((pw, h), Image.LANCZOS)
            panels.append(panel)
        return panels

    def generate_comic(
        self,
        api_key: str,
        model: str,
        prompts: List[str],
        style_name: str,
        size: str,
        seed: int,
        thinking_mode: bool,
        ref_image: Optional[str] = None,
        comic_layout: str = "Classic Comic Style",
        api_url: str = "",
        batch_size: int = 1,
    ) -> dict:
        """生成漫画

        Args:
            batch_size: 分镜合并数。1=每格单独生成(标准)，>1=合并后生成(经济模式)
        """
        from utils.style_template import styles

        if not api_key:
            return {"success": False, "message": "请填写 API Key"}
        if len(prompts) < 2:
            return {"success": False, "message": "请至少输入 2 个分镜"}

        # 合并分镜 prompt
        merged_prompts = self._merge_prompts(prompts, batch_size)
        # 记录每个合并块包含的原分镜数量，用于后续裁剪
        orig_per_batch = []
        idx = 0
        for mp in merged_prompts:
            count = min(batch_size, len(prompts) - idx)
            orig_per_batch.append(count)
            idx += count

        api = self._ensure_api(api_key, model, api_url)
        size_val = SIZE_MAP.get(size, "2K")
        base_seed = seed if seed >= 0 else random.randint(0, MAX_SEED)

        # 应用风格模板 — 万相模型是中文自然语言模型，不适合 SD 关键词堆砌风格
        style_p, style_n = styles.get(style_name, styles.get("(No style)", ("{prompt}", "")))
        # 对 not-no-style 的风格，只取纯文字描述前缀（去掉 SD 特有语法）
        if style_name != "(No style)":
            # 只保留 {prompt} 前面的纯文字前缀，去掉 SD 关键字后缀
            prefix = style_p.split("{prompt}")[0] if "{prompt}" in style_p else ""
            suffix = style_p.split("{prompt}")[-1] if "{prompt}" in style_p else ""
            if prefix or suffix:
                # 仅保留风格说明的第一个短语作为自然语言前缀
                clean_style = prefix.strip().rstrip(",").strip()
                if clean_style:
                    styled = [f"{clean_style}，{p}" for p in merged_prompts]
                else:
                    styled = merged_prompts
            else:
                styled = merged_prompts
        else:
            styled = merged_prompts

        # 统一 negative_prompt（所有块使用同一个）
        final_negative = style_n if style_n else None

        # 生成图片（循环次数 = 合并后的块数，远小于分镜数）
        merged_images = []
        for i, prompt in enumerate(styled):
            current_seed = base_seed + i
            logger.info(f"生成合并块 {i+1}/{len(styled)} seed={current_seed} ({orig_per_batch[i]}个分镜)")
            try:
                # 所有场景如果有参考图都使用图生图，保持商品外观一致性
                if ref_image:
                    urls = api.image_to_image(
                        prompt=prompt, ref_image=ref_image,
                        size=size_val, seed=current_seed, n=1,
                        thinking_mode=thinking_mode,
                        negative_prompt=final_negative,
                    )
                else:
                    urls = api.text_to_image(
                        prompt=prompt, size=size_val, seed=current_seed, n=1,
                        thinking_mode=thinking_mode,
                        negative_prompt=final_negative,
                    )
                if urls:
                    img = api._download_image(urls[0])
                    if img:
                        merged_images.append((img, orig_per_batch[i]))
                        continue
                logger.error(f"合并块 {i+1} 生成失败")
            except Exception as e:
                logger.error(f"合并块 {i+1} 异常: {e}")
                # 尽量返回已生成的图片
                images_so_far = []
                for mi, cnt in merged_images:
                    images_so_far.extend(self._split_merged_image(mi, cnt))
                return {
                    "success": False,
                    "message": f"合并块 {i+1} 生成失败: {str(e)[:150]}",
                    "images": self._images_to_base64(images_so_far),
                }

        if not merged_images:
            return {"success": False, "message": "所有图片生成失败"}

        # 裁剪合并图 → 还原为独立分镜
        images = []
        for mi, cnt in merged_images:
            panels = self._split_merged_image(mi, cnt)
            # 对所有面板做空白边框裁剪，确保无黑边
            panels = [self._trim_black_borders(p) for p in panels]
            images.extend(panels)

        # 合成漫画排版
        try:
            font = ImageFont.truetype(FONT_PATH, 45) if os.path.exists(FONT_PATH) else None
            # 使用纯白填充图，避免 pad_images.png 中有文字/图案混入漫画
            pad = Image.new("RGB", (512, 512), (255, 255, 255))

            if comic_layout == "无排版（原始图片）":
                result = images
            elif comic_layout == "双图拼接（推荐）" and len(images) == 2:
                result = [self._combine_two_images(images[0], images[1])]
            elif comic_layout == "双图拼接（推荐）":
                # 多于2张时每2张拼一张，最后多的单独保留
                combined = []
                for i in range(0, len(images), 2):
                    if i + 1 < len(images):
                        combined.append(self._combine_two_images(images[i], images[i + 1]))
                    else:
                        combined.append(images[i])
                result = combined
            else:
                result = get_comic(images, comic_layout, captions=prompts, font=font, pad_image=pad)
        except Exception as e:
            logger.error(f"排版失败: {e}")
            result = images

        api_calls = len(styled)
        saved = len(prompts) - api_calls
        return {
            "success": True,
            "message": f"生成成功！共 {len(images)} 格（合并后调用 {api_calls} 次，节省 {saved} 次）",
            "images": self._images_to_base64(result),
            "seed": base_seed,
            "api_calls": api_calls,
            "panels": len(images),
        }

    def _images_to_base64(self, images: List[Image.Image]) -> List[str]:
        """将 PIL Image 列表转为 base64 data URI"""
        import base64 as b64
        data_uris = []
        for img in images:
            buf = BytesIO()
            img.save(buf, format="PNG")
            b = b64.b64encode(buf.getvalue()).decode()
            data_uris.append(f"data:image/png;base64,{b}")
        return data_uris

    @staticmethod
    def get_styles() -> List[str]:
        return STYLE_NAMES

    @staticmethod
    def get_models() -> List[str]:
        return MODEL_CHOICES

    @staticmethod
    def get_layouts() -> List[str]:
        return ["双图拼接（推荐）", "Classic Comic Style", "Four Pannel", "无排版（原始图片）"]

    @staticmethod
    def _combine_two_images(img1: Image.Image, img2: Image.Image) -> Image.Image:
        """将两张等高的图片左右拼接为一张宽图，中间留白边"""
        from utils.utils import add_white_border
        # 统一高度
        h = max(img1.height, img2.height)
        if img1.height != h:
            new_w = int(img1.width * h / img1.height)
            img1 = img1.resize((new_w, h), Image.LANCZOS)
        if img2.height != h:
            new_w = int(img2.width * h / img2.height)
            img2 = img2.resize((new_w, h), Image.LANCZOS)
        # 加白边
        img1 = add_white_border(img1, 8)
        img2 = add_white_border(img2, 8)
        # 中间留间隔
        gap = 16
        total_w = img1.width + gap + img2.width
        canvas = Image.new("RGB", (total_w, h + 16), (255, 255, 255))
        canvas.paste(img1, (8, 8))
        canvas.paste(img2, (8 + img1.width + gap, 8))
        return canvas
