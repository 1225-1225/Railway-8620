# 🚂 Railway-8620 · 中国铁路知识智能问答系统

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.137%2B-009688)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2%2B-orange)](https://langchain-ai.github.io/langgraph/)
[![Vue 3](https://img.shields.io/badge/Vue-3.5%2B-4FC08D)](https://vuejs.org/)
[![License](https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey)](LICENSE)

基于 **LangChain + LangGraph + FastAPI + Vue 3** 的中文铁路知识智能问答系统。支持 **RAG 向量检索问答**、**铁路线路图绘制**、**多轮对话**与**流式输出**。

> ⚠️ **注意**：本仓库包含大体积地理数据文件（GPKG、PKL、JSON），使用 **Git LFS** 管理。克隆前请确保已安装 Git LFS。

---

## 📸 功能演示

| 对话界面 | 铁路线路图 |
|:---:|:---:|
| ![对话界面](docs/screenshots/chat.png) | ![线路图](docs/screenshots/map.png) |

<details>
<summary>🎬 点击展开操作示例</summary>

**用户输入：** `合肥到北京丰台`

**系统返回：**
- 7 趟列车信息（含直达/途经），按发车时间排列
- 每趟车对应的交互式铁路线路图（基于 OSM 真实轨道几何，支持点击/缩放/平移）
- 自动推荐最佳车次

</details>

---

## ✨ 功能概览

| 功能 | 说明 |
|------|------|
| 🧠 **铁路知识问答** | 基于 Chroma 向量库 + RAG，检索 150+ 篇中国铁路机车知识文档 |
| 🗺️ **铁路线路图绘制** | 输入起止城市，自动匹配车次，在**真实铁路轨道网络**上绘制交互式地图 (Folium) |
| 💬 **流式对话** | 前端 SSE 实时流式输出，打字机效果 |
| 🔄 **多轮对话** | LangGraph Agent + SQLite Checkpointer，支持跨轮次记忆 |
| 🔐 **用户认证** | JWT 注册/登录，每个用户独立对话历史 |
| 🐳 **Docker 部署** | Dockerfile + docker-compose 一键启动前后端 |

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **LLM 框架** | LangChain、LangGraph |
| **向量检索** | Chroma + OpenAI 兼容 Embedding（阿里百炼 text-embedding-v4） |
| **LLM 提供商** | OpenAI 兼容 API / Anthropic（支持 OpenCode、DeepSeek 等） |
| **后端** | FastAPI、SQLAlchemy、python-jose (JWT) |
| **前端** | Vue 3 + TypeScript + Vite + Pinia + Vue Router |
| **地图** | Folium + NetworkX（A\* 路径搜索，真实铁路网络） |
| **数据库** | SQLite（用户库 + 对话检查点） |
| **部署** | Docker Compose（Python 3.10 + Nginx） |

---

## 📁 项目结构

```
Railway-8620/
├── agent/                          # Agent 核心模块
│   ├── agent.py                    # LangGraph Agent（工具调用 + 多轮记忆）
│   ├── llm.py                      # LLM 工厂函数（支持 OpenAI / Anthropic）
│   ├── tools.py                    # 工具定义：retriever_tool / route_map_drawing_tool
│   ├── vector_store.py             # Chroma 向量库服务
│   ├── build_vector_store.py       # 向量库构建（文本分块 + MD5去重）
│   ├── route_map_service.py        # 铁路绘图：车次匹配 + A* 最短路径 + Folium 地图
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
│   ├── nginx.conf                  # Nginx 配置（反向代理 /auth、/chat）
│   ├── Dockerfile                  # 多阶段构建
│   └── vite.config.ts              # Vite 配置（开发代理）
├── data/
│   ├── cleaned_txts/               # 150+ 篇清洗后的铁路知识文本
│   ├── vector_database/            # Chroma 向量库持久化目录
│   ├── railway_route/              # ⚠️ 大文件（Git LFS）
│   │   ├── china_railway_filtered.gpkg  # 全国铁路 OSM 地理数据（~222MB）
│   │   ├── line_graph.json              # 铁路线路图结构数据（~19MB）
│   │   └── timetable.json               # 列车时刻表（~56MB）
│   ├── china_railway.pkl           # 全国铁路 NetworkX 图（Git LFS）
│   ├── city_to_node.pkl            # 站点坐标映射（Git LFS）
│   ├── train_data.json             # 列车车次与经停站数据（Git LFS）
│   └── stations.json               # 城市→站点映射（模糊匹配兜底）
├── tests/                          # Pytest 测试
│   ├── test_api.py                 # 端到端 API 测试
│   ├── test_auth.py                # JWT 认证测试
│   └── ...
├── mytools/                        # 数据采集/清洗工具脚本
├── chat_history/                   # 对话历史持久化目录（运行时生成）
├── .env.example                    # 环境变量模板
├── .gitattributes                  # Git LFS 配置
├── settings.py                     # 配置管理层（支持 .env 热重载）
├── Dockerfile                      # 后端 Dockerfile
├── docker-compose.yml              # 一键启动前后端
└── requirements.txt                # Python 依赖
```

---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Node.js 18+ / npm
- Docker Desktop（可选，容器化部署）
- Git LFS（克隆大文件用）

### 1️⃣ 克隆仓库并拉取 LFS 文件

```bash
git clone https://github.com/1225-1225/Railway-8620.git
cd Railway-8620
git lfs pull
```

> 如果未安装 Git LFS，可先 `git lfs install` 再 `git lfs pull`。

### 2️⃣ 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```env
# LLM 配置（支持 OpenAI 兼容接口）
llm_provider=openai
llm_model_name=deepseek-v4-flash
llm_base_url=https://opencode.ai/zen/go/v1
llm_api_key="your-api-key-here"

# Embedding 配置（阿里百炼，兼容 OpenAI 格式）
embedding_provider=openai
embedding_model_name=text-embedding-v4
embedding_base_url=https://dashscope.aliyuncs.com/compatible-mode/v1
embedding_api_key="your-api-key-here"

# JWT 签名密钥（生产环境务必更换为高熵随机串）
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

### `retriever_tool` — 知识检索

- 查询 Chroma 向量数据库，检索相关铁路知识文档
- 数据源：`data/cleaned_txts/` 下 150+ 篇清洗文本（蒸汽机车、电力机车、内燃机车等）

### `route_map_drawing_tool` — 按车次绘制路线图

- 输入车次代码（如 `G1`、`Z227`）
- 在 OSM 真实轨道网络上用 **per-line A\*** 算法（按线路隔离的图搜索）计算路径
- 回退策略：per-line 失败 → 全图 A\* → 直线连接
- 区间匹配三级策略：Tier 1 segments 直查 → Tier 2 line_stations 评分 → Tier 3 空间兜底
- 生成带线路颜色区分、车站标注的 Folium 交互式地图

### `station_route_drawing_tool` — 按起止站查找并绘图

- 输入："合肥" → "北京丰台"
- 从时刻表匹配所有经过这两站的车次（按发车时间排序）
- 每趟车分别绘制路线图
- 支持站名模糊匹配和归一化

---

## 🔧 构建向量库

如有新的文本数据，重新构建向量库：

```bash
python -m agent.build_vector_store
```

该脚本会：
1. 扫描 `data/cleaned_txts/` 下所有 `.txt` 文件
2. 使用 `RecursiveCharacterTextSplitter` 分块（chunk_size=500, overlap=77）
3. 计算 MD5 去重，避免重复入库
4. 存入 Chroma 向量数据库

---

## 🧪 运行测试

```bash
pytest tests/ -v
```

测试覆盖：

| 文件 | 测试内容 |
|------|----------|
| `test_api.py` | 端到端：注册、登录、聊天接口 |
| `test_auth.py` | JWT 签发/验证、用户认证逻辑 |
| `test_database.py` | 用户模型 CRUD |
| `test_schemas.py` | Pydantic 数据校验 |
| `test_llm.py` | LLM 服务创建与链调用 |
| `test_chat_history.py` | 对话历史读写 |
| `test_tools.py` | 工具函数调用 |
| `test_build_vector_store.py` | 向量库构建 |

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
    │                    ├── retriever_tool          → Chroma 向量检索
    │                    └── route_map_drawing_tool  → RouteMapService
    │                        或 station_route_drawing_tool
    │                        ├── 车次匹配 (timetable.json)
    │                        ├── 站点定位 (city_to_node.pkl / GPKG)
    │                        ├── per-line A* 路径搜索 (line_graph.json)
    │                        ├── 全图 A* 兜底 (china_railway_filtered.gpkg)
    │                        └── Folium 地图生成 (frontend/public/maps/*.html)
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
A: 检查 `.env` 中的 `llm_api_key` 和 `embedding_api_key` 是否正确填写。

**Q: 如何切换 LLM 提供商？**
A: 修改 `.env` 中 `llm_provider` 为 `openai` 或 `anthropic`，调整对应的 `llm_model_name`、`llm_base_url`、`llm_api_key`，重启后端即可生效。

**Q: 生成的铁路地图在哪？**
A: 地图 HTML 保存在 `frontend/public/maps/` 目录，通过前端聊天消息中的链接即可打开。

**Q: 克隆后文件不完整？（GPKG / JSON 为空）**
A: 运行 `git lfs install && git lfs pull` 拉取大文件。

**Q: 如何重置对话历史？**
A: 删除 `chat_history/` 目录下的 SQLite 文件，重启后端即可。

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