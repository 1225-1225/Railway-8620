# 🎯 Railway-8620 · 面试一页纸项目介绍

> 用途：面试自我介绍、简历项目描述、GitHub 项目简介的速查卡。
> 建议打印或熟读，面试前 5 分钟过一遍。

---

## 一句话定位

> 基于 **LangGraph Agent + RAG 向量检索 + FastAPI + Vue 3** 的中国铁路知识智能问答系统，支持**流式对话、多轮记忆、车次查询、交互式路线地图**，并完成 **Docker 容器化部署**。

---

## 项目背景与动机

- 铁路知识分散在 200+ 篇技术文档中，传统搜索难以直接回答"前进型蒸汽机车有什么特点"这类问题
- 需要把 **LLM 的推理能力 + 知识库的检索能力 + 结构化数据的查询能力** 结合起来
- 最终做成一个可对话、可查车次、可看地图的**一站式铁路知识助手**

---

## 技术栈

| 层级 | 技术 |
|------|------|
| LLM/Agent | LangChain 1.3 + LangGraph 1.2（ReAct 循环 + SqliteSaver 记忆） |
| RAG | RAGFlow 知识库（237 篇文档）+ 阿里百炼 text-embedding-v4 |
| 后端 | FastAPI 0.137、SQLAlchemy 2.0、JWT、argon2 |
| 前端 | Vue 3.5 + TypeScript + Pinia + Vue Router + SSE 流式 |
| 可视化 | Folium 交互式地图 |
| 部署 | Docker Compose（backend + Nginx + RAGFlow） |
| 测试 | Pytest 82 个用例（Mock 外部依赖） |

---

## 核心功能

1. **🧠 铁路知识问答**：RAGFlow 检索 237 篇文档，回答机车/铁路历史问题
2. **🚄 车次信息查询**：输入车次号，返回起讫站、经停站、时刻表
3. **🔍 路线车次推荐**：输入起讫站，按 G/D/C/Z/T/K 优先级排序返回车次
4. **🗺️ 交互式路线地图**：输入车次，生成 Folium 地图（始发绿/终点红/中间蓝）
5. **💬 流式对话**：SSE 逐 token 输出，打字机效果
6. **🔄 多轮记忆**：LangGraph Checkpointer + SQLite，跨轮次上下文
7. **🔐 用户认证**：JWT 注册/登录，每用户独立会话

---

## 五大技术难点（面试核心）

### 1️⃣ 同步流式 × asyncio 事件循环阻塞
- **问题**：`agent.stream()` 是同步阻塞生成器，直接放进 FastAPI 异步生成器会卡死事件循环；`StopIteration` 穿越 `asyncio.Future` 会被包装成 `RuntimeError`
- **解法**：`run_in_executor` 扔进**有界线程池**（8 线程），事件循环只 `await`；用**哨兵对象**替代 `StopIteration`；双超时兜底（建流 60s + 取块 300s）

### 2️⃣ LangGraph checkpoint 二进制反解
- **问题**：多轮记忆用 msgpack **ExtType(5)** 序列化落盘，版本升级后格式会变，没有统一读取路径
- **解法**：三级降级解析（`bytes`/`dict`/`__start__`），每条消息按三种格式分别还原，全程 `try/except` 兜底

### 3️⃣ 给开源 RAGFlow v0.26.4 打容器补丁
- **问题**：上游两个 bug（DashScope batch_size 写死 16 超限、parser_config 类型错误）阻断部署
- **解法**：补丁定义为"旧→新"精确替换对，`docker exec` 容器内替换，**幂等可重入**，重启自动补打

### 4️⃣ 工具调用中断后的状态修复
- **问题**：流式请求超时中断后，checkpoint 留下"带 tool_calls 但无 ToolMessage"的未闭合序列，会话坏掉
- **解法**：每次请求前 `get_state` 检查，若有未闭合 tool_calls 则 `invoke(input=None)` 补完

### 5️⃣ Agent 单例生命周期 + 配置热更新
- **问题**：Agent 持有 SQLite 连接，每次重建会泄漏；LLM 配置变更需不重启生效
- **解法**：懒加载 + 双检锁；`reload_agent()` 先建新实例再关旧连接；`settings.py` 代理类支持 `.env` 运行时重载

---

## 工程化亮点

- ✅ **82 个 Pytest 用例**：端到端 API 测试（Mock 外部依赖）、并发安全测试（20 线程真实 SqliteSaver）、checkpoint 解析测试
- ✅ **SQLite 并发优化**：WAL 模式 + busy_timeout + check_same_thread=False + 有界线程池
- ✅ **CI/CD**：GitHub Actions（Python 多版本测试 + 覆盖率 + 前端构建 + Docker 构建）
- ✅ **性能压测**：`benchmarks/` 提供 QPS / P50/P95/P99 指标
- ✅ **Docker 一键部署**：backend + Nginx + RAGFlow 编排，共享卷挂载地图

---

## 面试话术（按岗位侧重）

| 岗位 | 重点讲 |
|------|--------|
| **AI/LLM 岗** | 难点 1、2、4（Agent 循环、流式、状态管理）+ RAG 检索链路 |
| **后端岗** | FastAPI 并发模型、JWT 认证、SQLite 并发优化（WAL/busy_timeout） |
| **全栈岗** | 完整链路 + 前端 SSE 打字机 + 地图可视化 |
| **DevOps 岗** | Docker Compose 编排 + RAGFlow 容器补丁 + CI |

---

## 电梯陈述（30 秒版）

> "我独立开发了一个基于 LangGraph 的铁路知识问答系统，用 RAGFlow 做向量检索、FastAPI 提供 SSE 流式接口、Vue 3 做前端，支持多轮记忆和交互式地图。过程中解决了同步 Agent 与异步框架的阻塞冲突、LangGraph 二进制检查点的反序列化、以及给开源组件打容器补丁等真实工程问题，并用 Docker Compose 完成了一键部署，配套 82 个自动化测试和 CI 流水线。"

---

## 常见追问与回答要点

**Q: 为什么用 RAGFlow 而不是 Chroma？**
A: RAGFlow 提供完整的文档解析、分块、向量化流水线，支持 237 篇文档的批量管理；且通过 REST API 解耦，便于独立部署和扩展。

**Q: 多轮记忆是怎么实现的？**
A: LangGraph 的 SqliteSaver 作为 Checkpointer，每步对话状态自动序列化到 SQLite；`thread_id = user_{id}_{session_id}` 实现用户+会话双重隔离。

**Q: 流式输出为什么不会阻塞？**
A: 同步的 `agent.stream()` 全部在独立线程池执行，事件循环只做 `await`；用哨兵对象避免 StopIteration 被 asyncio 包装成 RuntimeError。

**Q: 遇到最大的坑是什么？**
A: 给开源 RAGFlow 打容器补丁——上游 batch_size 写死 16 导致向量化失败，通过 docker exec 精确替换源码并幂等重入解决。

**Q: 如何保证并发安全？**
A: SQLite 开启 WAL（读写不互斥）+ busy_timeout（写锁重试）+ SqliteSaver 自带 threading.Lock + 有界线程池（8 线程）避免线程爆炸。
