# backend/api.py
import asyncio
import json
import os
import re
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

# 将项目根目录添加到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.agent import AgentService
from backend import auth
from backend.database import User
from backend.auth import get_current_user

from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk
import logging

from agent.checkpoint_parser import (
    parse_messages_from_checkpoint,
    parse_first_message,
    parse_checkpoint_ts,
)

logger = logging.getLogger("backend.api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(_handler)

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

# 有界线程池：所有 agent.stream() 的同步迭代都在这个池子里执行
# 不能再用默认无界池（run_in_executor(None)）——并发请求会无限创建线程，
# 且所有请求共享同一个 SQLite 连接，线程爆炸会放大锁竞争。
# 容量通过环境变量 AGENT_THREAD_POOL_SIZE 配置，默认 8。
_AGENT_POOL_SIZE = int(os.getenv("AGENT_THREAD_POOL_SIZE", "8"))
_agent_executor = ThreadPoolExecutor(
    max_workers=_AGENT_POOL_SIZE,
    thread_name_prefix="agent-worker",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时无需预热，关闭时释放 Agent 持有的 SQLite 连接与线程池"""
    yield
    global _agent_service
    if _agent_service is not None:
        _agent_service.close()
        _agent_service = None
    # 优雅关闭线程池：等待在跑的任务结束，不再接收新任务
    _agent_executor.shutdown(wait=True)


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
# 注意：地图由 agent/route_map_generator.py 生成，这里必须挂载同一目录，
# 否则生成的地图无法通过 /maps 访问。
#   - Docker 部署时由 docker-compose.yml 注入 maps_output_dir=/app/shared/maps
#   - 本地开发时回退到 data/maps
from fastapi.staticfiles import StaticFiles
import os
_maps_dir = os.getenv(
    "maps_output_dir",
    os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'maps')),
)
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



# session_id 会被拼进 thread_id 并作为目录/DB 查询条件，必须限制为安全字符
# 允许：字母数字、下划线、连字符（覆盖 UUID 与前端生成的自定义 ID）
# 注意：不能定义为类属性（_ 前缀会被 Pydantic 当作私有属性，无法通过 cls.xxx 访问）
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{0,64}$")


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, v: str) -> str:
        if not _SESSION_ID_RE.match(v):
            raise ValueError(
                "session_id 只能包含字母、数字、下划线或连字符，且长度不超过 64"
            )
        return v

    @field_validator("message")
    @classmethod
    def _validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("消息内容不能为空")
        if len(v) > 8000:
            raise ValueError("消息内容过长（上限 8000 字符）")
        return v


def _get_checkpointer_db() -> str:
    """返回 SqliteSaver 检查点数据库的完整路径"""
    from settings import settings as config_data
    return os.path.join(
        config_data.chat_history_storage_path,
        config_data.history_database_name,
    )


def _ensure_session_meta_table(conn: sqlite3.Connection):
    """确保 session_meta 表存在（存自定义会话标题，与 checkpointer 同库）

    LangGraph 的 SqliteSaver 只管理 checkpoints/writes 表，
    自定义表放在同一个库里是安全的，互不干扰。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_meta (
            thread_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


class RenameRequest(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("标题不能为空")
        if len(v) > 100:
            raise ValueError("标题过长（上限 100 字符）")
        return v


@app.get("/chat/sessions")
def list_sessions(current_user: User = Depends(get_current_user)):
    """返回当前用户的所有历史会话，按日期分组"""
    db_path = _get_checkpointer_db()
    if not os.path.exists(db_path):
        return {"groups": []}

    prefix = f"user_{current_user.id}_" if current_user else ""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_session_meta_table(conn)
    cur = conn.execute(
        "SELECT thread_id, checkpoint, metadata FROM checkpoints WHERE thread_id LIKE ? ORDER BY rowid",
        (f"{prefix}%",)
    )

    threads = {}
    for row in cur:
        tid = row["thread_id"]
        meta = json.loads(row["metadata"])
        if meta.get("source") == "input" and tid not in threads:
            ts = parse_checkpoint_ts(row["checkpoint"])
            preview = parse_first_message(row["checkpoint"])
            threads[tid] = {"thread_id": tid, "created_at": ts, "preview": preview or "新对话"}

    # 自定义标题优先于自动预览
    custom_titles = {
        r["thread_id"]: r["title"]
        for r in conn.execute(
            "SELECT thread_id, title FROM session_meta WHERE thread_id LIKE ?",
            (f"{prefix}%",)
        )
    }
    for tid, title in custom_titles.items():
        if tid in threads:
            threads[tid]["preview"] = title

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
    messages = parse_messages_from_checkpoint(row[0])
    return {"messages": messages}


@app.put("/chat/sessions/{thread_id:path}")
def rename_session(thread_id: str, request: RenameRequest, current_user: User = Depends(get_current_user)):
    """重命名指定会话（自定义标题，优先于自动预览显示）"""
    # 安全校验：只允许当前用户的会话
    expected_prefix = f"user_{current_user.id}"
    if not thread_id.startswith(expected_prefix):
        return {"ok": False, "error": "无权限"}
    db_path = _get_checkpointer_db()
    if not os.path.exists(db_path):
        return {"ok": False, "error": "会话不存在"}
    conn = sqlite3.connect(db_path)
    try:
        _ensure_session_meta_table(conn)
        # 会话必须真实存在（checkpoints 里有记录）
        exists = conn.execute(
            "SELECT 1 FROM checkpoints WHERE thread_id=? LIMIT 1",
            (thread_id,),
        ).fetchone()
        if not exists:
            return {"ok": False, "error": "会话不存在"}
        conn.execute(
            """
            INSERT INTO session_meta (thread_id, title, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET title=excluded.title, updated_at=excluded.updated_at
            """,
            (thread_id, request.title, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "title": request.title}


@app.delete("/chat/sessions/{thread_id:path}")
def delete_session(thread_id: str, current_user: User = Depends(get_current_user)):
    """删除指定会话（含所有 checkpoints 与 writes 记录）"""
    # 安全校验：只允许当前用户的会话
    expected_prefix = f"user_{current_user.id}"
    if not thread_id.startswith(expected_prefix):
        return {"ok": False, "error": "无权限"}
    db_path = _get_checkpointer_db()
    if not os.path.exists(db_path):
        return {"ok": False, "error": "会话不存在"}
    conn = sqlite3.connect(db_path)
    try:
        _ensure_session_meta_table(conn)
        cur = conn.execute(
            "DELETE FROM checkpoints WHERE thread_id=?",
            (thread_id,),
        )
        deleted = cur.rowcount
        conn.execute(
            "DELETE FROM writes WHERE thread_id=?",
            (thread_id,),
        )
        # 同步清理自定义标题，避免残留
        conn.execute(
            "DELETE FROM session_meta WHERE thread_id=?",
            (thread_id,),
        )
        conn.commit()
    finally:
        conn.close()
    if deleted == 0:
        return {"ok": False, "error": "会话不存在"}
    return {"ok": True, "deleted": deleted}


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
        except Exception as e:
            logger.warning("修复未完成 tool_calls 失败: %s", e)


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
            # 在独立线程（有界线程池）中运行同步的 agent.stream()，避免阻塞事件循环
            stream_iter = iter(
                await asyncio.wait_for(
                    loop.run_in_executor(
                        _agent_executor,
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
                    loop.run_in_executor(_agent_executor, _next_chunk),
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