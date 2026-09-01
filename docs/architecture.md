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
