import os
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain.agents import create_agent
from agent.llm import create_llm

from settings import settings as config_data
from agent.tools import retriever_tool, railway_drawing_tool

tools = [retriever_tool, railway_drawing_tool]

class AgentService:
    def __init__(self):
        # 确保存储目录存在
        os.makedirs(config_data.chat_history_storage_path, exist_ok=True)
        # 构建数据库文件的完整路径
        db_path = os.path.join(config_data.chat_history_storage_path, config_data.history_database_name)
        # 直接创建 SQLite 连接并传入 SqliteSaver（需要设置 check_same_thread=False）
        self.checkpointer = SqliteSaver.from_conn_string(db_path)
        # 启用流式输出
        self.agent = create_agent(
            model=create_llm(streaming=True),
            tools=tools,
            system_prompt="你是一位知晓中国铁路和机车知识的专家。"
                          "请根据工具返回的资料，直接、专业地回答用户问题。"
                          "如果需要绘制铁路线路图，请调用 railway_drawing_tool 工具。",
            checkpointer=self.checkpointer
        )

if __name__ == '__main__':
    agent_service = AgentService()
    agent = agent_service.agent
    thread_id = "user_001"
    config = {"configurable": {"thread_id": thread_id}}

    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": "第四次呢"}]},
        config=config,
        stream_mode="messages"
    ):
        if isinstance(chunk, tuple):
            msg = chunk[0]
        else:
            msg = chunk
        if hasattr(msg, 'content') and msg.content:
            print(msg.content, end='', flush=True)