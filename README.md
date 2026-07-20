# 🚂 Railway-8620 · 中国铁路知识智能问答系统

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.137%2B-009688)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2%2B-orange)](https://langchain-ai.github.io/langgraph/)
[![Vue 3](https://img.shields.io/badge/Vue-3.5%2B-4FC08D)](https://vuejs.org/)
[![License](https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey)](LICENSE)

基于 **LangChain + LangGraph + FastAPI + Vue 3** 的中文铁路知识智能问答系统。支持 **RAG 向量检索问答**（RAGFlow）、**交互式路线地图生成**、**多轮对话**与**流式输出**。

---

## ✨ 功能概览

| 功能 | 说明 |
|------|------|
| 🧠 **铁路知识问答** | 基于 RAGFlow 知识库 + RAG，检索 150+ 篇中国铁路机车知识文档 |
| 🗺️ **交互式路线地图** | 输入车次，自动生成途经站点路线图 (Folium)，支持缩放/悬停 |
| 🚄 **车次信息查询** | 查询指定车次的详细信息（起讫站、经停站、时刻表） |
| 🔍 **路线车次推荐** | 根据起讫站查询车次列表，按 G/D/C/Z/T/K 优先级排序 |
| 💬 **流式对话** | 前端 SSE 实时流式输出，打字机效果 |
| 🔄 **多轮对话** | LangGraph Agent + SQLite Checkpointer，支持跨轮次记忆 |
| 🔐 **用户认证** | JWT 注册/登录，每个用户独立对话历史 |
| 🐳 **Docker 部署** | Dockerfile + docker-compose 一键启动前后端 |

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **LLM 框架** | LangChain 1.3 + LangGraph 1.2 |
| **向量检索** | RAGFlow（REST API 对接，阿里百炼 text-embedding-v4） |
| **LLM 提供商** | OpenAI 兼容 API / Anthropic（支持 OpenCode、DeepSeek 等） |
| **后端** | FastAPI 0.137、SQLAlchemy 2.0、python-jose (JWT)、argon2-cffi |
| **前端** | Vue 3.5 + TypeScript + Vite 7 + Pinia 3 + Vue Router 5 |
| **地图** | Folium 0.20（相邻站点直线连接） |
| **数据库** | SQLite（用户库 `users.db` + LangGraph 对话检查点） |
| **部署** | Docker Compose（Python 3.10-slim + Nginx alpine） |

---

## 📁 项目结构

```
Railway-8620/
├── agent/                          # Agent 核心模块
│   ├── agent.py                    # LangGraph Agent（工具调用 + SqliteSaver 多轮记忆）
│   ├── llm.py                      # LLM 工厂函数（支持 OpenAI / Anthropic）
│   ├── tools.py                    # 工具工厂 + retriever_tool（RAGFlow 知识库检索）
│   ├── railway_tools.py            # 铁路工具：query_train_info / query_trains_by_route
│   ├── route_map_generator.py      # Folium 路线地图生成器（相邻站点直线连接）
│   ├── route_map_service.py        # （保留，暂为空）
│   ├── ragflow_client.py           # RAGFlow REST API 客户端封装
│   ├── ragflow_migrate.py          # 批量上传文档到 RAGFlow
│   └── chat_history.py             # JSON 文件对话历史（独立存储实现）
├── backend/                        # FastAPI 后端
│   ├── api.py                      # 主入口：流式/非流式聊天接口、CORS 配置
│   ├── auth.py                     # JWT 认证：注册、登录、令牌验证
│   ├── database.py                 # SQLite 用户模型 (SQLAlchemy)
│   └── schemas.py                  # Pydantic 数据模型
├── frontend/                       # Vue 3 前端
│   ├── src/
│   │   ├── views/
│   │   │   ├── ChatView.vue        # 流式聊天页（主页，带历史侧边栏）
│   │   │   ├── ChatLegacyView.vue  # 非流式聊天页
│   │   │   ├── LoginView.vue       # 登录页
│   │   │   └── RegisterView.vue    # 注册页
│   │   ├── components/
│   │   │   └── HistorySidebar.vue  # 历史对话侧边栏
│   │   ├── stores/auth.ts          # Pinia 认证状态管理
│   │   ├── services/api.ts         # Axios 封装 + JWT 拦截器
│   │   ├── router/index.ts         # 路由 + 守卫
│   │   ├── App.vue                 # 根组件
│   │   └── main.ts                 # 入口
│   ├── nginx.conf                  # Nginx 配置（反向代理 /auth、/chat、/maps）
│   ├── Dockerfile                  # 多阶段构建
│   └── vite.config.ts              # Vite 配置（开发代理 :8620 → :8000）
├── data/
│   ├── cleaned_txts/               # 150+ 篇清洗后的铁路知识文本（RAGFlow 语料源）
│   ├── station_coords.json         # 车站经纬度坐标（地图绘制用）
│   ├── stations.json               # 车站基础信息
│   ├── train_details.json          # 车次详细信息（含经停站时刻表）
│   ├── train_stations.json         # 车次-站点映射
│   ├── railway_graph.json          # 铁路线路图结构数据
│   ├── maps/                       # 运行时生成的 Folium 地图 HTML
│   ├── vector_database/            # （旧版 Chroma 遗留目录）
│   └── railway_route/
│       ├── line_graph.json         # 铁路线路图结构
│       └── timetable.json          # 列车时刻表
├── tests/                          # Pytest 测试
│   ├── test_api.py                 # 端到端 API 测试（Mock 数据库 + Agent）
│   ├── test_auth.py                # JWT 认证测试
│   ├── test_settings.py            # 配置管理测试
│   ├── test_tools.py               # 工具函数 + 单例测试
│   ├── test_database.py            # 用户模型 CRUD
│   ├── test_schemas.py             # Pydantic 校验
│   ├── test_chat_history.py        # 对话历史读写
│   ├── test_llm.py                 # LLM 工厂函数
│   └── conftest.py                 # 全局夹具 + 环境变量注入
├── mytools/                        # 数据采集/清洗/处理工具脚本
├── chat_history/                   # 对话检查点 SQLite 存储（运行时生成）
├── logs/                           # 运行日志（tool_calls.log）
├── .env.example                    # 环境变量模板
├── settings.py                     # Pydantic 配置管理（支持 .env 热重载）
├── Dockerfile                      # 后端 Dockerfile（Python 3.10-slim）
├── docker-compose.yml              # 一键启动 backend + frontend
└── requirements.txt                # Python 依赖
```

---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Node.js 18+ / npm
- Docker Desktop（可选，容器化部署）
- RAGFlow 服务（可选，可外部部署，参见 `docker-compose.ragflow.yml`）

### 1️⃣ 克隆仓库

```bash
git clone https://github.com/1225-1225/Railway-8620.git
cd Railway-8620
```

### 2️⃣ 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```env
# LLM 配置（支持 OpenAI 兼容接口）
llm_provider=openai
llm_model_name=deepseek-v4-flash
llm_base_url=your-url
llm_api_key="your-api-key-here"

# Embedding 配置
embedding_provider=openai
embedding_model_name=text-embedding-v4
embedding_base_url=your-embedding-url
embedding_api_key="your-api-key-here"

# JWT 签名密钥（请更换为高熵随机串）
JWT_SECRET_KEY="your-secret-key-change-in-production"
```

### 3️⃣ 安装依赖

**后端：**
```bash
pip install -r requirements.txt
```

**前端：**
```bash
cd frontend
npm install
cd ..
```

### 4️⃣ 启动后端

```bash
uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000/docs 查看 Swagger API 文档。

### 5️⃣ 启动前端（另一个终端）

```bash
cd frontend
npm run dev
```

前端运行在 http://localhost:8620，已配置代理将 `/auth`、`/chat` 转发到后端。

### 🐳 Docker Compose 一键启动

```bash
docker compose up -d
```

| 服务 | 地址 |
|------|------|
| 前端 (Nginx) | http://localhost:8620 |
| 后端 (FastAPI) | http://localhost:8000 |

---

## 📡 API 接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/auth/register` | 注册新用户 | 否 |
| POST | `/auth/login` | 登录，返回 JWT（Form 格式） | 否 |
| POST | `/chat` | 非流式对话（完整响应） | 是 |
| POST | `/chat/stream` | 流式对话（SSE，打字机效果） | 是 |
| GET | `/chat/sessions` | 获取历史会话列表 | 是 |
| GET | `/chat/sessions/{thread_id}` | 获取指定会话的全部消息 | 是 |

### 流式响应格式

```
data: {"content": "前进型蒸汽机车"}
data: {"content": "是中国铁路"}
data: {"content": "..."}
data: [DONE]
```

异常情况：
```
data: {"error": "操作超时（工具执行耗时较长，请稍后重试）"}
data: [DONE]
```

---

## 🧩 Agent 工具说明

Agent（`agent/agent.py`）基于 LangGraph 的 `create_agent` 构建，使用 `SqliteSaver` 持久化对话检查点，共注册 4 个工具：

### `retriever_tool` — 知识库检索

- 调用 RAGFlow 的 `/api/v1/retrieval` 接口，检索相关铁路知识文档
- 数据源：`data/cleaned_txts/` 下 150+ 篇清洗文本（蒸汽机车、电力机车、内燃机车、铁路历史等）
- 支持配置 `top_k` 和相似度阈值

### `query_train_info` — 车次信息查询

- 输入车次代码（如 `G1`、`Z227`）
- 从 `train_details.json` 查询详细信息：起讫站、发车/到达时间、经停站列表及时刻
- 支持同时查询多个车次

### `query_trains_by_route` — 路线车次查询

- 输入起讫站："合肥" → "北京丰台"
- 从时刻表匹配所有经过这两站的车次
- 按 G（高铁）→ D（动车）→ C（城际）→ Z（直达）→ T（特快）→ K（快速）优先级排序

### `generate_route_map` — 生成路线地图

- 输入车次代码
- 读取 `station_coords.json` 站点经纬度坐标
- 将相邻经停站用直线连接，生成 Folium 交互式 HTML 地图
- 始发站绿色图标、终点站红色方格旗、中间站蓝色圆点，支持悬停查看站名
- 地图文件保存到 `data/maps/`，通过 `/maps/` 路径访问

---

## 🔧 知识库管理

项目使用 RAGFlow 作为知识库引擎。如有新的文本数据需要导入：

```bash
python -m agent.ragflow_migrate
```

该脚本会：
1. 扫描 `data/cleaned_txts/` 下所有 `.txt` 文件
2. 通过 RAGFlow REST API 批量上传文档
3. 由 RAGFlow 内部完成解析、分块和向量化（使用阿里百炼 text-embedding-v4 模型）

> RAGFlow 服务需独立部署（参考 `docker-compose.ragflow.yml`），或在 `settings.py` 中配置外部 RAGFlow 地址。

---

## 🧪 运行测试

```bash
pytest tests/ -v
```

测试覆盖：

| 文件 | 测试内容 |
|------|----------|
| `test_api.py` | 端到端：注册、登录、聊天接口（Mock 数据库 + Agent） |
| `test_auth.py` | JWT 签发/验证、用户认证逻辑 |
| `test_database.py` | 用户模型 CRUD |
| `test_schemas.py` | Pydantic 数据校验 |
| `test_llm.py` | LLM 服务创建与链调用 |
| `test_chat_history.py` | 对话历史读写 |
| `test_tools.py` | RAGFlow 检索工具 + 单例行为 |
| `test_settings.py` | 配置管理默认值与环境变量 |

---

## 🏗️ 架构说明

```
用户浏览器 (Vue 3)
    │  SSE 流式 / REST API
    ▼
Nginx (生产) / Vite Proxy (开发)
    │
    ▼
FastAPI 后端
    ├── /auth/*       → JWT 认证 (SQLite users.db)
    ├── /chat/*       → LangGraph Agent
    │                    ├── retriever_tool          → RAGFlow 知识库检索
    │                    ├── query_train_info        → train_details.json
    │                    ├── query_trains_by_route   → train_stations.json
    │                    └── generate_route_map      → Folium 直线地图
    └── /chat/sessions → 历史会话管理 (SQLite checkpoint)
```

### 多轮对话机制

- 使用 LangGraph 的 `SqliteSaver` 作为 Checkpointer，所有轮次自动持久化到 SQLite
- 每个用户的 `thread_id = f"user_{user_id}_{session_id}"`，实现用户+会话双重隔离
- 支持跨轮次记忆：Agent 能参考前几轮的上下文回答

### 地图自动补全机制

- LLM 生成回答时可能忘记在文字中嵌入 `[MAP]` 标记
- 后端 `_ensure_map_tags()` 自动检测并从工具返回值中提取 `[MAP]...[/MAP]` 块追加到回答末尾
- 前端 `renderContent()` 自动将 `[MAP]` 标记渲染为带 iframe 的地图容器

---

## 📦 数据来源

- **铁路网络数据**：OpenStreetMap 中国铁路数据（经筛选过滤）
- **列车时刻表**：公开列车运行时刻数据
- **铁路知识文档**：150+ 篇中国铁路机车相关技术文档

> ⚠️ 本仓库仅用于学习和研究目的。数据版权归各自所有者所有。

---

## ❓ 常见问题

**Q: Docker 启动报 "unable to get image"？**
A: 确保 Docker Desktop 已启动并运行，然后重试 `docker compose up -d`。

**Q: 启动后端报 API Key 错误？**
A: 检查 `.env` 中的 `llm_api_key` 和 `embedding_api_key` 是否正确填写。如果使用环境变量间接引用（如 `OPENCODE_GO_API_KEY`），确保该环境变量已设置。

**Q: 如何切换 LLM 提供商？**
A: 修改 `.env` 中 `llm_provider` 为 `openai` 或 `anthropic`，调整对应的 `llm_model_name`、`llm_base_url`、`llm_api_key`，调用 API 的 `/reload` 接口即可热生效，无需重启。

**Q: 生成的铁路地图在哪？**
A: 地图 HTML 保存在 `data/maps/` 目录，通过 `/maps/` 静态路径访问。

**Q: 如何重置对话历史？**
A: 删除 `chat_history/` 目录下的 SQLite 文件，重启后端即可。

**Q: 需要部署 RAGFlow 吗？**
A: RAGFlow 是可选的外部依赖。可以参考 `docker-compose.ragflow.yml` 部署，或在 `settings.py` 中配置已有服务的地址。不配置 RAGFlow 时，知识库检索功能不可用，但车次查询和地图生成功能不受影响。

---

## 📄 许可证

本仓库使用 **Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0)** 许可证。

您可以：
- ✅ **共享** — 在任何媒介以任何形式复制、发行本作品
- ✅ **演绎** — 修改、转换或以本作品为基础进行创作

**必须遵守：**
- **署名** — 您必须给出适当的署名，提供指向本许可证的链接
- **非商业性使用** — 您不得将本作品用于商业目的

完整的许可证文本请参见 [LICENSE](LICENSE) 文件或访问 https://creativecommons.org/licenses/by-nc/4.0/

---

## 📬 联系方式

如有问题或建议，欢迎提交 [Issue](https://github.com/1225-1225/Railway-8620/issues) 或 Pull Request。

---

<p align="center">🚂 <b>Railway-8620</b> — 让中国铁路知识触手可及</p>