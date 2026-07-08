# 个人简历

## 基本信息

| 项目 | 内容 |
|------|------|
| 姓名 | （请填写） |
| 电话 | （请填写） |
| 邮箱 | （请填写） |
| 学校/学历 | （请填写） |
| 求职意向 | 后端开发 / AI 应用开发 实习 |

---

## 技术能力

- **语言**：Python（熟练），TypeScript / JavaScript（了解），SQL
- **后端框架**：FastAPI，LangChain，LangGraph
- **AI / LLM**：RAG 检索增强生成，Agent + Tool Use 编排，Prompt Engineering，Embedding 向量化
- **数据存储**：Chroma 向量数据库，SQLite（SQLAlchemy ORM），JSON 文件存储
- **前端**：Vue 3，Vite，Pinia，Nginx 反向代理
- **算法与工具**：NetworkX 图算法（A* 最短路径），Folium 地理可视化，Geopy 地理编码
- **认证与安全**：JWT 令牌签发与校验，Argon2 密码哈希，OAuth2 协议
- **工程化**：Docker + docker-compose 容器化部署，pytest 单元测试（103 用例覆盖），Git 版本管理
- **环境**：Python 虚拟环境管理（conda），环境变量配置驱动（.env）

---

## 项目经历

### Railway-8620 — 铁路知识智能问答与线路图绘制系统

**时间**：2025 年 | **角色**：独立开发

基于 LangChain + LangGraph 的多工具智能 Agent 系统，整合 RAG 向量检索与路径规划算法，提供铁路知识问答和交互式线路图生成服务。

**技术栈**：Python · FastAPI · LangChain 1.x · LangGraph · Vue 3 · Chroma · NetworkX · Folium · SQLite · Docker · Nginx · pytest

**核心功能**：

1. **RAG 智能问答** — 基于 Chroma 向量库，对 150+ 篇中国铁路机车知识文档建立索引，支持语义检索，LLM 结合检索结果生成专业回答
2. **铁路线路图自动绘制** — 输入"北京到合肥"等自然语言，LLM 自动提取城市 → 匹配真实车次（train_data.json）→ 在 NetworkX 全国铁路图上运行 A* 算法搜索最短路径 → Folium 生成交互式 HTML 地图
3. **流式对话（SSE）** — 后端 StreamingResponse 实时推送 SSE 事件，前端 ReadableStream 解析实现打字机效果，异常时推送 error 事件优雅降级
4. **多轮对话记忆** — LangGraph Agent + SqliteSaver Checkpointer，按 `thread_id = user_{id}` 实现用户隔离，对话历史自动持久化
5. **JWT 用户认证** — 注册 / 登录接口，Argon2 密码哈希，OAuth2PasswordBearer 依赖注入保护 API
6. **容器化部署** — 前后端独立 Dockerfile（多阶段构建），docker-compose 一键启动，Nginx 反向代理 + SSE 流式缓冲关闭，共享 volume 传递地图文件

**架构设计亮点**：

- **Agent 编排**：LangGraph 协调 LLM 自主决策调用工具（retriever_tool / railway_drawing_tool），无需硬编码路由
- **服务单例化**：VectorStoreService 与 RailwayDrawingService 模块级懒加载 + 双检锁，避免重复加载向量库和全国铁路图，A* 路径缓存跨请求复用
- **配置驱动**：CORS 来源、数据库路径、LLM Provider 全走 `.env` 环境变量，无硬编码
- **测试驱动**：pytest 覆盖 103 个用例，Mock 隔离所有外部依赖（数据库、Agent、LLM），覆盖认证、流式响应、SSE 异常恢复、服务单例行为、站名归一化等回归场景

**项目量化**：
- 知识库：150+ 篇文档，Chroma 向量索引
- 铁路网络：覆盖全国主要铁路线路的 NetworkX 图
- 测试：103 个 pytest 用例，覆盖 API / 认证 / 工具层 / 配置 / ORM / 路径算法
- 部署：3 个 Docker 镜像，docker-compose 一键编排

---

## 自我评价

- 具备完整的 AI 应用从 0 到 1 开发能力，覆盖数据采集、模型选型、后端开发、前端对接、容器化部署全流程
- 熟悉 LangChain / LangGraph 生态，能独立设计 Agent + Tool 架构
- 注重工程化实践：环境变量配置管理、单元测试、Docker 容器化、文档与代码一致
- 善于从面试官视角审视项目质量，主动发现并修复文档不一致、硬编码、安全漏洞等问题

---

> 简历中的个人信息（姓名、电话、邮箱、学校）请自行填写。