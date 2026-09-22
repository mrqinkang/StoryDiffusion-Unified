# main.py
# -*- coding: utf-8 -*-
"""
StoryDiffusion 小说漫画工作室
FastAPI 后端 - 提供 REST API + 静态文件服务
"""

import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 添加当前目录到 Python 路径（确保可以导入同级模块）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- 确保日志目录存在 ---
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("main")

# ============================================================
# 创建 FastAPI 应用
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("  StoryDiffusion 小说漫画工作室 启动")
    logger.info("=" * 50)
    yield
    logger.info("应用关闭")

app = FastAPI(
    title="StoryDiffusion 小说漫画工作室",
    description="AI 小说生成 + 漫画生成 + 小说→漫画流水线",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - 允许前端开发时跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 注册路由
# ============================================================

from routers.novel import router as novel_router
from routers.comic import router as comic_router
from routers.pipeline import router as pipeline_router
from routers.xhs import router as xhs_router

app.include_router(novel_router)
app.include_router(comic_router)
app.include_router(pipeline_router)
app.include_router(xhs_router)

# ============================================================
# 挂载静态文件
# ============================================================

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
(static_dir / "css").mkdir(exist_ok=True)
(static_dir / "js").mkdir(exist_ok=True)
(static_dir / "assets").mkdir(exist_ok=True)

app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

# ============================================================
# 健康检查
# ============================================================

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    import uvicorn
    import socket

    def find_available_port(start_port: int) -> int:
        """从 start_port 开始找第一个可用端口"""
        port = start_port
        while port < start_port + 100:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    return port
            port += 1
        return start_port  # 实在找不到就用默认的

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    port = find_available_port(port)

    print("=" * 60)
    print("  StoryDiffusion 小说漫画工作室")
    print("=" * 60)
    print(f"  浏览器访问: http://localhost:{port}")
    print(f"  API 文档:   http://localhost:{port}/docs")
    print("=" * 60)

    uvicorn.run("main:app", host=host, port=port, reload=True)
