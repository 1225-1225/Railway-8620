# 🏗️ Railway-8620 架构设计

> 本文档基于真实代码整理，配合 README 的「技术深度」章节阅读。
> 图示为 Mermaid 语法，可在 GitHub / VS Code / Typora 中直接渲染。

---

## 1. 系统整体架构

```mermaid
flowchart TB
    subgraph 用户端
        Browser["🌐 浏览器 (Vue 3 SPA)"]
    end

    subgraph 前端层
        Vite["Vite Dev Server (:8620)<br/>/auth /chat /maps 代理"]
        Nginx["Nginx 生产 (:8620)<br/>反向代理 + 静态资源"]
    end

    subgraph 后端 FastAPI (:8000)
        Auth["🔐 /auth/*<br/>JWT 注册/登录"]
        Chat["💬 /chat /chat/stream<br/>SSE 流式输出"]
        Sessions["📜 /chat/sessions*<br/>历史会话列表"]
        AgentCore["🧠 Agent (LangGraph)"]
    end

    subgraph LangGraph Agent 核心
        LLMNode["LLM 节点<br/>ChatOpenAI / ChatAnthropic"]
        ToolsNode["工具执行节点"]
        Checkpointer["SqliteSaver<br/>checkpointer"]
    end

    subgraph 工具集 Tools
        T1["retriever_tool"]
        T2["query_train_info"]
        T3["query_trains_by_route"]
        T4["generate_route_map"]
    end

    subgraph 外部依赖
        RAGFlow["RAGFlow 知识库<br/>(:9380, 237 篇文档)"]
        DataJSON["data/*.json<br/>车次/站点/坐标"]
        Folium["Folium → HTML 地图<br/>data/maps/*.html"]
        SQLite2["users.db<br/>用户账号"]
        SQLite3["chat_history/checkpointer.db<br/>对话检查点"]
    end

    Browser -->|SSE/REST| Vite
    Browser -->|生产| Nginx
    Vite -->|代理| Auth & Chat & Sessions
    Nginx -->|代理| Auth & Chat & Sessions

    Auth --> SQLite2
    Sessions -->|msgpack 反解| SQLite3
    Chat -->|invoke/stream| AgentCore
    AgentCore --> LLMNode
    AgentCore --> Checkpointer
    LLMNode -->|tool_calls| ToolsNode
    ToolsNode -->|AIMessage + ToolMessage 循环| LLMNode
    ToolsNode --> T1 & T2 & T3 & T4
    Checkpointer --> SQLite3
    T1 --> RAGFlow
    T2 --> DataJSON
    T3 --> DataJSON
    T4 --> Folium
    Folium -->|静态挂载 /maps| Browser
```

**关键数据流：**

- 前端把用户消息 POST 到 `/chat/stream`，后端用 SSE（`text/event-stream`）逐 token 推送回答
- 后端在独立线程里跑 `agent.stream(stream_mode="messages")`，避免阻塞 asyncio 事件循环
- 每次对话状态自动写入 SQLite checkpointer，实现跨轮记忆
- 工具结果直接查本地 JSON 或调 RAGFlow，地图生成后通过 `/maps` 静态路径返回给前端

---

## 2. LangGraph ReAct 循环（核心）

```mermaid
flowchart LR
    START(["输入<br/>HumanMessage"]) --> LLM["LLM 节点<br/>绑定 4 个工具 schema"]

    LLM --> 判断{"模型输出?<br/>是否带 tool_calls"}
    判断 -->|"✅ 要调用工具"| TOOLS["工具执行节点<br/>执行对应 @tool 函数<br/>生成 ToolMessage 写回"]
    TOOLS -->|"ToolMessage 追加到<br/>消息列表（状态更新）"| LLM
    判断 -->|"❌ 直接回答"| END["输出 AIMessage<br/>最终回答"]

    LLM -. "每步后自动保存检查点" .-> CP["SqliteSaver<br/>(msgpack ExtType 序列化)"]
    TOOLS -. "每步后自动保存检查点" .-> CP

    TOOLS --> T1["retriever_tool<br/>→ RAGFlow 检索"]
    TOOLS --> T2["query_train_info<br/>→ train_details.json"]
    TOOLS --> T3["query_trains_by_route<br/>→ train_stations.json"]
    TOOLS --> T4["generate_route_map<br/>→ Folium 地图"]
```

### 循环环节与代码映射

| 循环环节 | 对应代码 | 说明 |
|---------|---------|------|
| LLM 节点 | `agent/llm.py` 的 `create_llm(streaming=True)` | 绑定工具 schema，决定下一步 |
| 工具执行节点 | `agent/tools.py` + `agent/railway_tools.py` | `@tool` + `@log_tool_call` |
| 循环控制 | `create_agent(...)` 内部 `StateGraph` | LLM → 工具 → LLM 直到不再要调工具 |
| 状态持久化 | `SqliteSaver` + `checkpointer` 参数 | 每一步写入 SQLite |
| 流式读取 | `agent.stream(stream_mode="messages")` | 拿 `AIMessageChunk` 级 token |
| 中断修复 | `backend/api.py` 的 `_repair_incomplete_tool_calls` | 补完未闭合的 `tool_calls` |
| 多轮隔离 | `thread_id = user_{id}_{session_id}` | 用户 + 会话双重隔离 |

---

## 3. 部署拓扑（Docker Compose）

```mermaid
flowchart TB
    subgraph 宿主机
        subgraph Docker 网络 railway-8620_default
            subgraph 前端容器 frontend
                Nginx["Nginx (:80)<br/>静态资源 + 反向代理"]
            end
            subgraph 后端容器 backend
                FastAPI["uvicorn FastAPI (:8000)"]
                Agent["LangGraph Agent"]
            end
            subgraph RAGFlow 容器 ragflow
                RAGFlow["RAGFlow (:9380)<br/>知识库引擎"]
            end
        end

        subgraph 命名卷 Volumes
            V1["backend_data<br/>/app/data"]
            V2["maps_data<br/>/app/shared/maps"]
        end

        subgraph 绑定挂载 Bind Mounts
            B1["./chat_history<br/>→ /app/chat_history"]
        end

        subgraph 外部依赖
            LLM_API["LLM API<br/>(DeepSeek/OpenCode)"]
            EMB_API["Embedding API<br/>(阿里百炼 text-embedding-v4)"]
        end
    end

    Browser["🌐 浏览器"] -->|":8620"| Nginx
    Nginx -->|"/auth /chat 代理"| FastAPI
    Nginx -->|"/maps 静态"| V2
    FastAPI --> Agent
    Agent -->|"REST /api/v1/retrieval"| RAGFlow
    Agent -->|"REST /api/v1/retrieval"| LLM_API
    RAGFlow -->|"向量化"| EMB_API
    FastAPI -->|"SQLite 用户库"| V1
    Agent -->|"SqliteSaver 检查点"| B1
```

**端口映射：**

| 容器 | 内部端口 | 宿主机端口 | 说明 |
|------|---------|-----------|------|
| `frontend` | 80 | **8620** | Nginx 托管 Vue 静态资源 + 反代 API |
| `backend` | 8000 | **8000** | FastAPI 服务 |
| `ragflow` | 9380 | **9380** | RAGFlow 知识库（可选） |

**关键设计：**

- **共享卷 `maps_data`**：后端生成的地图 HTML 写入 `/app/shared/maps`，前端 Nginx 通过只读挂载 `/usr/share/nginx/maps:ro` 直接提供 `/maps/` 静态访问，无需经过后端
- **绑定挂载 `./chat_history`**：对话检查点 SQLite 持久化到宿主机，容器重建不丢失
- **SSE 反代**：Nginx 对 `/chat/` 关闭 `proxy_buffering`，保证流式输出实时到达浏览器
- **RAGFlow 可选**：不启动 RAGFlow 时，车次查询/地图生成/对话功能不受影响，仅知识库检索不可用

---

## 4. 一次完整请求的数据流（时序）

```mermaid
sequenceDiagram
    participant U as 用户
    participant F as Vue 前端
    participant N as Nginx/Vite
    participant A as FastAPI
    participant G as LangGraph Agent
    participant T as 工具集
    participant R as RAGFlow
    participant D as data/*.json
    participant S as SQLite

    U->>F: 输入问题
    F->>N: POST /chat/stream {message, session_id} + JWT
    N->>A: 转发请求
    A->>A: 校验 JWT → 解析用户
    A->>A: thread_id = user_{id}_{session_id}
    A->>G: 检查并修复未完成 tool_calls
    A->>G: agent.stream(messages, stream_mode="messages")

    loop ReAct 循环
        G->>G: LLM 判断是否需要工具
        alt 需要工具
            G->>T: 执行工具
            T->>R: retriever_tool → RAGFlow 检索
            T->>D: query_train_info / query_trains_by_route
            T->>D: generate_route_map → Folium HTML
            T-->>G: ToolMessage 写回
            G->>S: 保存 checkpoint
        else 直接回答
            G-->>A: AIMessageChunk（逐 token）
        end
    end

    A-->>N: SSE data: {content: "..."}
    N-->>F: 流式推送
    F-->>U: 打字机效果渲染
    F->>A: GET /chat/sessions（刷新历史侧边栏）
    A->>S: 反解 checkpoint 二进制
    A-->>F: 会话列表
```

---

## 3. 流式对话时序（SSE）

```mermaid
sequenceDiagram
    participant F as 前端 (Vue 3)
    participant A as FastAPI /chat/stream
    participant E as 线程池 executor
    participant G as LangGraph Agent

    F->>A: POST {message, session_id} + JWT
    A->>A: thread_id = user_{id}_{session_id}
    A->>G: 检查并修复未完成 tool_calls
    A->>E: run_in_executor(agent.stream, messages)
    E-->>A: stream_iter（同步生成器）
    loop 逐 token
        A->>E: run_in_executor(next)
        E-->>A: AIMessageChunk
        A-->>F: data: {"content": "..."}\n\n
    end
    A-->>F: data: [DONE]\n\n
```

> 注意：同步的 `agent.stream()` 全部在独立线程中执行，事件循环只做 `await`，
> 用哨兵对象替代 `StopIteration` 避免被 asyncio 包装成 RuntimeError。
