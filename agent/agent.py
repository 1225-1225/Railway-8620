import os
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain.agents import create_agent
from agent.llm import create_llm

from settings import settings as config_data
from agent.tools import retriever_tool, query_train_info, query_trains_by_route, generate_route_map

tools = [retriever_tool, query_train_info, query_trains_by_route, generate_route_map]

class AgentService:
    def __init__(self):
        # 确保存储目录存在
        os.makedirs(config_data.chat_history_storage_path, exist_ok=True)
        # 构建数据库文件的完整路径
        db_path = os.path.join(config_data.chat_history_storage_path, config_data.history_database_name)
        # 直接创建 SQLite 连接并传入 SqliteSaver（需要设置 check_same_thread=False）
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self.conn)
        # 启用流式输出
        self.agent = create_agent(
            model=create_llm(streaming=True),
            tools=tools,
            system_prompt="你是一位知晓中国铁路和机车知识的专家。"
                          "请根据工具返回的资料，直接、专业地回答用户问题。\n\n"
                          "工具使用指南：\n"
                          "1. 当用户询问具体车次的信息时（如'Z227的信息'），请调用 query_train_info 工具，传入车次列表。\n"
                          "2. 当用户询问两地之间的车次时（如'北京到合肥的车'），请调用 query_trains_by_route 工具，传入起讫站和数量。\n"
                          "3. 当用户需要查看车次运行路线地图时，请调用 generate_route_map 工具，传入车次列表。\n"
                          "4. 如果用户同时要求查车次信息和画路线图，先调用 query_train_info 查信息，再调用 generate_route_map 画图。\n"
                          "5. 回答中请直接展示车次详细信息，包括发车/到达时间和经停站。",
            checkpointer=self.checkpointer
        )

    def close(self):
        """释放底层 SQLite 连接，避免 reload / 应用关闭时泄漏"""
        try:
            self.conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    agent_service = AgentService()
    agent = agent_service.agent
    thread_id = "user_001"
    config = {"configurable": {"thread_id": thread_id}}

    try:
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
    finally:
        agent_service.close()