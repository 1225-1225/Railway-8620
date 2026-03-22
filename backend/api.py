# backend/api.py
import os
import sys
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
import json
from langchain_core.messages import AIMessage, AIMessageChunk

app = FastAPI()

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vue 开发服务器地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册认证路由
app.include_router(auth.router)

# 创建唯一的智能体对象
agent = AgentService().agent

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    # 使用用户 ID 作为 thread_id，确保每个用户有独立的对话历史
    thread_id = f"user_{current_user.id}"
    config = {"configurable": {"thread_id": thread_id}}
    input_data = {"messages": [{"role": "user", "content": request.message}]}
    result = agent.invoke(input=input_data, config=config)
    answer = result["messages"][-1].content
    return {"answer": answer}

@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    thread_id = f"user_{current_user.id}"
    config = {"configurable": {"thread_id": thread_id}}
    input_data = {"messages": [{"role": "user", "content": request.message}]}

    async def generate():
        for chunk in agent.stream(
            input_data,
            config=config,
            stream_mode="messages"
        ):
            # agent.stream 是同步的，但 StreamingResponse 的生成器可以是异步的
            # 为了简单，我们直接在异步生成器中调用同步方法，可能会轻微阻塞，但通常可接受
            if isinstance(chunk, tuple):
                msg = chunk[0]
            else:
                msg = chunk
            if isinstance(msg, (AIMessage, AIMessageChunk)) and msg.content:
                yield f"data: {json.dumps({'content': msg.content})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")