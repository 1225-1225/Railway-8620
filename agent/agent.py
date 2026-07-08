import os
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain.agents import create_agent
from agent.llm import create_llm

from settings import settings as config_data
from agent.tools import retriever_tool, route_map_drawing_tool, station_route_drawing_tool

tools = [retriever_tool, route_map_drawing_tool, station_route_drawing_tool]

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
                          "请根据工具返回的资料，直接、专业地回答用户问题。"
                          "绘图工具使用规则："
                          "1. 用户明确指定车次代码（如G1、K4174等）时，调用 route_map_drawing_tool 工具；"
                          "2. 用户给出起点和终点站名（如「合肥到北京西」、「从合肥去北京西」）时，"
                          "调用 station_route_drawing_tool 工具，会自动查找所有车次并按发车时间排序绘制。"
                          "【重要】当工具返回内容中包含 [MAP]...[/MAP] 标记时，"
                          "你必须原封不动地将这些 [MAP]...[/MAP] 标记复制到你的回答中，"
                          "不要删除、修改或省略它们，这些标记会自动渲染为路线图。",
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