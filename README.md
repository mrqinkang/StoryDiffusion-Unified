# StoryDiffusion 小说漫画工作室

> AI 驱动的全栈内容创作平台，实现「AI 写小说 → 自动转漫画 → 小红书发布」的完整商业闭环。

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-green)
![Tests](https://img.shields.io/badge/Tests-21%20passed-brightgreen)

## 功能特性

### 小说创作
- **多模型适配** — 工厂模式接入 OpenAI / DeepSeek / Gemini / 通义千问等 10+ LLM，零 LangChain 依赖
- **流式输出** — SSE + asyncio Queue 实时逐字推送，前端 ReadableStream 渲染
- **智能引擎** — 架构→蓝图→逐章生成→定稿，支持任意位置续写/插入章节
- **知识库检索** — Embedding 适配器工厂支持 7 种向量后端（OpenAI / Ollama / Gemini / BGE / ChromaDB）
- **自定义模板** — 用户可保存常用参数为模板，一键复用

### 漫画生成
- **多格漫画** — 阿里云万相 DashScope API，支持文生图 / 图生图 / 多格排版
- **风格管理** — 预置多种漫画风格，支持自定义风格切换
- **智能排版** — 自动分镜布局，支持 2×2 / 3×3 等多种排版模式

### 小说→漫画流水线
- **自动提取** — LLM 从章节中提取关键场景，生成分镜描述
- **批量生成** — 场景描述 → 图像 API 批量生成，支持经济模式合并提示词
- **一致性检查** — 角色状态追踪，确保跨章节人物形象一致

### 小红书发布
- **MCP 协议集成** — JSON-RPC over stdio，实现内容自动发布
- **Cookie 管理** — Windows DPAPI 解密 Chrome/Edge 登录态，免扫码登录
- **内容生成** — AI 自动分析商品图片，生成小红书风格文案

### 技术亮点
- **零框架依赖前端** — 原生 JS 开发完整 SPA，深色毛玻璃 UI，响应式布局
- **三层架构** — API 路由层 → 业务服务层 → 核心引擎层，职责清晰
- **Docker 部署** — 一键容器化，支持环境变量动态配置
- **自动化测试** — 21 个 API 测试用例，覆盖 5 个业务模块，通过率 100%

## 快速开始

### 环境要求

- Python 3.10+
- Node.js（可选，用于 xhs-mcp）

### 安装与运行

```bash
# 1. 克隆项目
git clone https://github.com/your-username/StoryDiffusion-Unified.git
cd StoryDiffusion-Unified

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python main.py
```

浏览器访问 http://localhost:8000

### Docker 部署

```bash
docker build -t storydiffusion .
docker run -d -p 8000:8000 storydiffusion
```

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PORT` | `8000` | 服务端口 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `OPENAI_API_KEY` | - | OpenAI API Key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容接口地址 |
| `DEEPSEEK_API_KEY` | - | DeepSeek API Key |
| `GEMINI_API_KEY` | - | Gemini API Key |
| `DASHSCOPE_API_KEY` | - | 阿里云 DashScope Key |

## API 端点

### 小说模块 `/api/novel/`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/generate` | 生成小说（流式） |
| POST | `/guided-chat` | 引导式创作 |
| POST | `/continue` | 续写小说 |
| GET | `/templates` | 获取预置模板 |
| GET | `/templates/custom` | 获取自定义模板 |
| POST | `/templates/custom/save` | 保存自定义模板 |
| GET | `/drafts` | 获取草稿列表 |
| GET | `/chat/list` | 获取对话列表 |
| POST | `/chat/save` | 保存对话 |
| POST | `/chat/load` | 加载对话 |
| POST | `/chat/delete` | 删除对话 |

### 漫画模块 `/api/comic/`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/test-connection` | 测试图像 API 连接 |
| GET | `/styles` | 获取漫画风格列表 |
| GET | `/layouts` | 获取排版布局列表 |
| GET | `/models` | 获取可用模型列表 |

### 流水线模块 `/api/pipeline/`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/extract-scenes` | 从章节提取场景 |
| POST | `/generate-from-scenes` | 从场景生成漫画 |

### 小红书模块 `/api/xhs/`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/publish/check` | 检查发布状态 |
| POST | `/publish/check-login` | 检查登录状态 |
| GET | `/publish/extract-cookies` | 提取浏览器 Cookie |
| POST | `/publish/cookies` | 保存 Cookie |
| POST | `/analyze` | 分析商品图片 |
| POST | `/generate-content` | 生成小红书文案 |
| POST | `/publish` | 发布内容 |

## 项目结构

```
StoryDiffusion-Unified/
├── main.py                 # 应用入口，路由注册
├── database.py             # SQLite 持久化层
├── llm_adapters.py         # LLM 适配器工厂（10+ 后端）
├── embedding_adapters.py   # Embedding 适配器工厂（7 种后端）
├── config_manager.py       # 配置管理
├── consistency_checker.py  # 角色一致性检查
├── wanxiang_api.py         # 阿里云万相图像 API
│
├── novel_generator/        # 小说生成引擎
│   ├── architecture.py     # 架构阶段
│   ├── blueprint.py        # 蓝图阶段
│   ├── chapter.py          # 章节生成
│   ├── finalization.py     # 定稿阶段
│   ├── knowledge.py        # 知识库检索
│   └── vectorstore_utils.py # 向量存储工具
│
├── routers/                # API 路由层
│   ├── novel.py            # 小说相关接口
│   ├── comic.py            # 漫画相关接口
│   ├── pipeline.py         # 流水线接口
│   └── xhs.py              # 小红书发布接口
│
├── services/               # 业务服务层
│   ├── novel_service.py    # 小说业务逻辑
│   ├── comic_service.py    # 漫画业务逻辑
│   ├── pipeline_service.py # 流水线业务逻辑
│   ├── xhs_service.py      # 小红书业务逻辑
│   ├── xhs_mcp_client.py   # MCP 协议客户端
│   ├── xhs_publisher.py    # 小红书发布器
│   └── cookie_reader.py    # 浏览器 Cookie 提取
│
├── utils/                  # 工具函数
│   ├── utils.py            # 通用工具
│   └── style_template.py   # 风格模板
│
├── static/                 # 前端静态文件
│   ├── index.html          # 主页面（SPA）
│   ├── css/style.css       # 全局样式（深色毛玻璃主题）
│   └── js/                 # 前端逻辑
│       ├── app.js          # 核心应用逻辑
│       ├── novel.js        # 小说模块
│       ├── comic.js        # 漫画模块
│       ├── pipeline.js     # 流水线模块
│       ├── xhs.js          # 小红书模块
│       └── settings.js     # 设置模块
│
├── tests/                  # 自动化测试
│   ├── conftest.py         # pytest 配置
│   ├── test_api.py         # API 集成测试
│   └── test_database.py    # 数据库单元测试
│
├── requirements.txt        # Python 依赖
├── Dockerfile              # Docker 部署配置
├── .gitignore              # Git 忽略规则
└── README.md               # 项目说明
```

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 运行数据库测试
pytest tests/test_database.py -v

# 运行 API 测试
pytest tests/test_api.py -v

# 生成测试报告
pytest tests/ -v --html=report.html
```

### API 自动化测试（Apifox）

项目支持通过 Apifox 进行 API 自动化测试：

1. 访问 `http://localhost:8000/docs` 导出 OpenAPI JSON
2. 在 Apifox 中导入 API 文档
3. 创建测试用例并运行回归测试

测试覆盖：21 个用例，5 个模块，通过率 100%。

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端（原生 JS SPA）                     │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │
│  │ 小说 │ │ 漫画 │ │ 流水线│ │ 小红书│ │ 设置 │         │
│  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘         │
│     └────────┴────────┴────────┴────────┘              │
│                    SSE / REST API                       │
├─────────────────────────────────────────────────────────┤
│                  API 路由层（FastAPI）                    │
│  routers/novel.py  comic.py  pipeline.py  xhs.py       │
├─────────────────────────────────────────────────────────┤
│                  业务服务层                               │
│  services/novel_service.py  comic_service.py  ...      │
├─────────────────────────────────────────────────────────┤
│                  核心引擎层                               │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐    │
│  │ 小说生成引擎 │ │ 图像生成引擎 │ │ 小红书发布器 │    │
│  │ (7 阶段流程) │ │ (万相 API)   │ │ (MCP 协议)   │    │
│  └──────┬──────┘ └──────┬───────┘ └──────┬───────┘    │
│         └───────────────┴────────────────┘             │
├─────────────────────────────────────────────────────────┤
│                  基础设施                                 │
│  ┌──────────┐ ┌───────────┐ ┌────────────────────┐    │
│  │ SQLite   │ │ LLM 工厂  │ │ Embedding 工厂     │    │
│  │ (WAL)    │ │ (10+ 后端)│ │ (7 种向量后端)     │    │
│  └──────────┘ └───────────┘ └────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## 许可证

MIT License

## 致谢

- [FastAPI](https://fastapi.tiangolo.com/)
- [OpenAI](https://openai.com/)
- [阿里云 DashScope](https://dashscope.aliyun.com/)
- [小红书 MCP](https://github.com/xhs-mcp)

