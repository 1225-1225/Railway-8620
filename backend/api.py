# backend/api.py
import asyncio
import json
import os
import sqlite3
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 将项目根目录添加到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.agent import AgentService
from backend import auth
from backend.database import User
from backend.auth import get_current_user

from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk
import msgpack

# CORS 允许的前端来源，逗号分隔；默认仅放行 Vite 开发服务器
# 生产环境下前端走 Nginx 反代到后端，同源不需要 CORS
_DEFAULT_CORS_ORIGINS = "http://localhost:8620"
_cors_origins = [
    o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",") if o.strip()
]

# 智能体对象（懒加载：首次请求或配置保存时才创建，避免空 key 导致启动崩溃）
# _agent 是 LangGraph agent 实例（供路由直接使用 / 测试 mock 直接替换）
# _agent_service 持有 SQLite 连接等资源，用于生命周期管理
_agent = None
_agent_service = None
_agent_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时无需预热，关闭时释放 Agent 持有的 SQLite 连接"""
    yield
    global _agent_service
    if _agent_service is not None:
        _agent_service.close()
        _agent_service = None


app = FastAPI(lifespan=lifespan)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册认证路由
app.include_router(auth.router)

# 静态文件：提供地图文件访问
from fastapi.staticfiles import StaticFiles
import os
_maps_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'maps'))
os.makedirs(_maps_dir, exist_ok=True)
app.mount("/maps", StaticFiles(directory=_maps_dir), name="maps")


def _get_agent():
    """获取当前智能体实例（懒初始化 + 双检锁，并发安全）"""
    global _agent, _agent_service
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent_service = AgentService()
                _agent = _agent_service.agent
    return _agent


def reload_agent():
    """重建智能体实例（配置变更后调用），并安全释放旧实例的 SQLite 连接"""
    global _agent, _agent_service
    with _agent_lock:
        old_service = _agent_service
        new_service = AgentService()
        # 先把新实例赋值，再关闭旧连接，避免中间态对外不可用
        _agent_service = new_service
        _agent = new_service.agent
        if old_service is not None:
            old_service.close()



class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


def _get_checkpointer_db() -> str:
    """返回 SqliteSaver 检查点数据库的完整路径"""
    from settings import settings as config_data
    return os.path.join(
        config_data.chat_history_storage_path,
        config_data.history_database_name,
    )


def _parse_first_message(blob: bytes) -> str:
    """从 msgpack 编码的 checkpoint 中提取第一条用户消息"""
    try:
        data = msgpack.unpackb(blob)
        cv = data.get(b'channel_values', data.get('channel_values', {}))
        if isinstance(cv, bytes):
            cv = msgpack.unpackb(cv)
        for key in (b'messages', 'messages', b'__start__', '__start__'):
            msgs = cv.get(key, {})
            if isinstance(msgs, dict):
                msgs = msgs.get(b'messages', msgs.get('messages', []))
            if isinstance(msgs, (list, tuple)) and len(msgs) > 0:
                first = msgs[0]
                # ExtType(5) 格式
                if hasattr(first, 'code') and first.code == 5:
                    inner = msgpack.unpackb(first.data)
                    if isinstance(inner, (list, tuple)) and len(inner) >= 3:
                        kw = inner[2]
                        if isinstance(kw, bytes):
                            kw = msgpack.unpackb(kw)
                        if isinstance(kw, dict):
                            content = kw.get('content', '')
                            if content:
                                return content[:100]
                elif isinstance(first, dict):
                    content = first.get(b'content', first.get('content', ''))
                    if content:
                        return content[:100]
    except Exception:
        pass
    return ""


def _parse_checkpoint_ts(blob: bytes) -> str:
    """从 msgpack 编码的 checkpoint 中提取 ISO 时间戳"""
    try:
        data = msgpack.unpackb(blob)
        ts = data.get(b'ts', data.get('ts', b'')).decode() if isinstance(data.get(b'ts', data.get('ts', b'')), bytes) else data.get('ts', '')
        return ts
    except Exception:
        return ""


@app.get("/chat/sessions")
def list_sessions(current_user: User = Depends(get_current_user)):
    """返回当前用户的所有历史会话，按日期分组"""
    db_path = _get_checkpointer_db()
    if not os.path.exists(db_path):
        return {"groups": []}

    prefix = f"user_{current_user.id}_" if current_user else ""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT thread_id, checkpoint, metadata FROM checkpoints WHERE thread_id LIKE ? ORDER BY rowid",
        (f"{prefix}%",)
    )

    threads = {}
    for row in cur:
        tid = row["thread_id"]
        meta = json.loads(row["metadata"])
        if meta.get("source") == "input" and tid not in threads:
            ts = _parse_checkpoint_ts(row["checkpoint"])
            preview = _parse_first_message(row["checkpoint"])
            threads[tid] = {"thread_id": tid, "created_at": ts, "preview": preview or "新对话"}

    conn.close()

    # 按日期分组
    groups = {}
    for s in threads.values():
        try:
            dt = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            date_key = dt.strftime("%Y-%m-%d")
            time_label = dt.strftime("%H:%M")
        except Exception:
            date_key = "未知日期"
            time_label = ""
        group = groups.setdefault(date_key, {"date": date_key, "sessions": []})
        group["sessions"].append({
            "thread_id": s["thread_id"],
            "preview": s["preview"],
            "time": time_label,
            "created_at": s["created_at"],
        })

    # 每组内按时间降序，组间按日期降序
    for g in groups.values():
        g["sessions"].sort(key=lambda x: x["created_at"], reverse=True)

    sorted_groups = sorted(groups.values(), key=lambda g: g["date"], reverse=True)
    return {"groups": sorted_groups}


def _parse_messages_from_checkpoint(blob: bytes) -> list:
    """从最新的 checkpoint msgpack blob 中提取所有人类可读的消息

    LangGraph SqliteSaver 使用 msgpack ExtType(5) 序列化 LangChain 消息。
    格式: ExtType(5, msgpack(['module', 'ClassName', {kwargs}]))
    """
    try:
        data = msgpack.unpackb(blob)
        cv = data.get(b'channel_values', data.get('channel_values', {}))
        if isinstance(cv, bytes):
            cv = msgpack.unpackb(cv)

        # 统一提取 messages 列表（旧版直接是列表，新版可能是 dict 包装）
        raw_messages = []
        for key in (b'messages', 'messages'):
            val = cv.get(key)
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                raw_messages = val
                break
            if isinstance(val, dict):
                # 新版 LangGraph 可能把 messages 包装在 dict 中
                inner = val.get(b'messages', val.get('messages', []))
                if isinstance(inner, (list, tuple)):
                    raw_messages = inner
                    break

        # 兜底：从 __start__ 中提取
        if not raw_messages:
            start = cv.get(b'__start__', cv.get('__start__', {}))
            raw_messages = start.get(b'messages', start.get('messages', []))
            if isinstance(raw_messages, dict):
                raw_messages = raw_messages.get(b'messages', raw_messages.get('messages', []))

        result = []
        for msg in raw_messages:
            # ── 主线：LangGraph msgpack ExtType(code=5) ──
            if hasattr(msg, 'code') and msg.code == 5 and hasattr(msg, 'data'):
                inner = msgpack.unpackb(msg.data)
                if isinstance(inner, (list, tuple)) and len(inner) >= 3:
                    class_name = inner[1]
                    kw = inner[2]
                    if isinstance(kw, bytes):
                        kw = msgpack.unpackb(kw)
                    if isinstance(kw, dict):
                        content = kw.get('content', '')
                        if isinstance(content, bytes):
                            content = content.decode()
                        if isinstance(class_name, bytes):
                            class_name = class_name.decode()
                        if class_name == 'HumanMessage':
                            role = 'user'
                        elif class_name in ('AIMessage', 'AIMessageChunk'):
                            role = 'assistant'
                        else:
                            role = ''
                        if role and content:
                            result.append({'role': role, 'content': content})
                continue

            # ── 兼容旧格式：元组 (code, data) ──
            if isinstance(msg, (list, tuple)) and len(msg) >= 2:
                data = msg[1]
                if isinstance(data, bytes):
                    data = msgpack.unpackb(data)
                if isinstance(data, dict):
                    role = data.get('role', data.get(b'role', ''))
                    content = data.get('content', data.get(b'content', ''))
                    if isinstance(role, bytes): role = role.decode()
                    if isinstance(content, bytes): content = content.decode()
                    if role in ('user', 'assistant') and content:
                        result.append({'role': role, 'content': content})
                continue

            # ── 兼容旧格式：纯 dict ──
            if isinstance(msg, dict):
                role = msg.get('role', msg.get(b'role', ''))
                content = msg.get('content', msg.get(b'content', ''))
                if isinstance(role, bytes): role = role.decode()
                if isinstance(content, bytes): content = content.decode()
                if role in ('user', 'assistant') and content:
                    result.append({'role': role, 'content': content})

        return result
    except Exception:
        return []


@app.get("/chat/sessions/{thread_id:path}")
def get_session_messages(thread_id: str, current_user: User = Depends(get_current_user)):
    """返回指定会话的全部历史消息"""
    # 安全校验：只允许当前用户的会话
    expected_prefix = f"user_{current_user.id}"
    if not thread_id.startswith(expected_prefix):
        return {"messages": []}
    db_path = _get_checkpointer_db()
    if not os.path.exists(db_path):
        return {"messages": []}
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT checkpoint FROM checkpoints WHERE thread_id=? ORDER BY rowid DESC LIMIT 1",
        (thread_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"messages": []}
    messages = _parse_messages_from_checkpoint(row[0])
    return {"messages": messages}


def _repair_incomplete_tool_calls(agent, config: dict):
    """检测上一次请求是否留下了未完成的 tool_calls，如有则补完。

    当流式请求因工具执行超时而中断时，checkpoint 中最后一条消息可能是
    带 tool_calls 的 AIMessage，但缺少对应的 ToolMessage。
    再次用同一 thread_id 发送消息时，LLM 会拒绝这种不完整的消息序列。
    此函数检测到这种情况时，先调用 invoke() 完成工具执行，使状态恢复完整。
    """
    state = agent.get_state(config)
    if state is None or not state.values:
        return
    messages = state.values.get('messages', [])
    if not messages:
        return
    last = messages[-1]
    # 检查最后一条消息是否是 AIMessage 且带有未完成的 tool_calls
    if hasattr(last, 'tool_calls') and last.tool_calls:
        try:
            agent.invoke(input=None, config=config)
        except Exception:
            pass


@app.post("/chat")
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    session_suffix = f"_{request.session_id}" if request.session_id else ""
    thread_id = f"user_{current_user.id}{session_suffix}"
    config = {"configurable": {"thread_id": thread_id}}
    agent = _get_agent()
    _repair_incomplete_tool_calls(agent, config)
    
    input_data = {"messages": [{"role": "user", "content": request.message}]}
    result = agent.invoke(input=input_data, config=config)
    all_messages = result["messages"]
    
    answer = all_messages[-1].content
    return {"answer": answer}

@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    session_suffix = f"_{request.session_id}" if request.session_id else ""
    thread_id = f"user_{current_user.id}{session_suffix}"
    config = {"configurable": {"thread_id": thread_id}}
    agent = _get_agent()
    _repair_incomplete_tool_calls(agent, config)
    input_data = {"messages": [{"role": "user", "content": request.message}]}

    # 用哨兵值标记迭代结束，避免 StopIteration 通过 asyncio Future 传播
    _SENTINEL = object()

    async def generate():
        loop = asyncio.get_event_loop()
        try:
            # 在独立线程中运行同步的 agent.stream()，避免阻塞事件循环
            stream_iter = iter(
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: agent.stream(
                            input_data, config=config, stream_mode="messages"
                        ),
                    ),
                    timeout=60.0,
                )
            )

            def _next_chunk():
                """线程安全的 next() 包装，用哨兵代替 StopIteration"""
                try:
                    return next(stream_iter)
                except StopIteration:
                    return _SENTINEL

            while True:
                chunk = await asyncio.wait_for(
                    loop.run_in_executor(None, _next_chunk),
                    timeout=300.0,
                )
                if chunk is _SENTINEL:
                    break

                if isinstance(chunk, tuple):
                    msg = chunk[0]
                else:
                    msg = chunk
                if isinstance(msg, (AIMessage, AIMessageChunk)) and msg.content:
                    yield f"data: {json.dumps({'content': msg.content}, ensure_ascii=False)}\n\n"

        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'error': '操作超时（工具执行耗时较长，请稍后重试）'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            # 推送一条错误事件后正常结束流，避免前端一直转圈
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")