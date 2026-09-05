# 📊 性能压测

本目录包含 Railway-8620 的性能压测脚本，用于量化系统的并发能力与延迟指标，为面试提供**可量化的数据支撑**。

## 脚本清单

| 脚本 | 说明 | 依赖 |
|------|------|------|
| `benchmark_api.py` | 纯 Python 并发压测（推荐，零额外依赖） | `httpx`（已在 requirements.txt） |
| `locustfile.py` | Locust 分布式压测（可选，更专业） | `pip install locust` |

---

## 快速开始

### 1. 启动后端

```bash
# 本地开发模式
uvicorn backend.api:app --host 0.0.0.0 --port 8000

# 或 Docker
docker compose up -d backend
```

> ⚠️ 压测前请确保 `.env` 中已配置 `llm_api_key`（否则 Agent 无法创建，接口会报错）。

### 2. 运行纯 Python 压测

```bash
# 默认：注册一个测试用户，并发 10，共 100 个请求
python benchmarks/benchmark_api.py

# 自定义参数
python benchmarks/benchmark_api.py --base-url http://localhost:8000 \
    --concurrency 20 --requests 200 --output results.json
```

### 3. 运行 Locust 压测（可选）

```bash
pip install locust
locust -f benchmarks/locustfile.py --host http://localhost:8000
# 打开 http://localhost:8080 配置并发数与速率
```

---

## 指标说明

脚本会输出以下指标：

| 指标 | 含义 |
|------|------|
| **QPS** | 每秒请求数（吞吐量） |
| **P50 / P95 / P99** | 延迟百分位（毫秒） |
| **成功率** | 非 5xx 响应占比 |
| **平均延迟** | 所有请求的平均耗时 |

> 💡 **面试建议**：压测结果受 LLM 提供商响应速度影响很大。建议：
> - 用**非流式 `/chat` 接口**压测（更稳定，便于对比）
> - 记录**环境信息**（机器配置、LLM 模型、并发数），保证数据可复现
> - 对比不同 `AGENT_THREAD_POOL_SIZE`（默认 8）下的吞吐差异，展示你对线程池调优的理解

---

## 📈 实测数据（2026-09-04）

**环境**：
- 后端：FastAPI + LangGraph Agent（本地 uvicorn，单进程）
- LLM：`deepseek-v4-flash`（火山方舟 coding 接口）
- 线程池：`AGENT_THREAD_POOL_SIZE=8`（默认）
- 压测接口：`POST /chat`（非流式）

**结果**（并发 5，共 10 请求，消息"你好"）：

| 指标 | 数值 |
|------|------|
| 成功率 | **100%**（10/10） |
| QPS | 0.4 req/s |
| 平均延迟 | 12.5 s |
| P50 延迟 | 15.5 s |
| P95 延迟 | 27.2 s |
| P99 延迟 | 27.2 s |

> 📌 **解读**：延迟主要来自 LLM 推理（`deepseek-v4-flash` 单次响应约 10-15s），而非系统瓶颈。系统本身（认证、路由、checkpoint 持久化）开销极小。若需提升吞吐，可：
> - 增大 `AGENT_THREAD_POOL_SIZE`（但受 LLM 并发配额限制）
> - 换用响应更快的 LLM 模型
> - 对纯工具查询（车次/地图）走独立快速通道，不经 LLM

> ⚠️ **注意**：本次压测时 RAGFlow 未启动，Agent 对知识类问题会反复调用 `retriever_tool`（每次超时约 4s 后返回"未找到"），进一步拉高延迟。**启动 RAGFlow 后**知识检索正常，延迟会显著下降。建议压测时：
> - 用**车次/地图类问题**（走本地 JSON，不经 RAGFlow）测系统吞吐
> - 用**知识类问题**（走 RAGFlow）测 RAG 链路延迟
