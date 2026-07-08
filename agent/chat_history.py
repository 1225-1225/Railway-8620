"""
基于 JSON 文件的对话历史存储实现。

说明：当前 Agent (agent/agent.py) 默认使用 LangGraph 的 SqliteSaver 作为
Checkpointer，本类未接入主流程，仅作为可选的独立存储后端保留，便于未来
切换为基于文件的实现或做迁移/导出。如需启用，请在 AgentService 中通过
RunnableWithMessageHistory 之类的方式注入。
"""
import json
import os.path
from typing import Sequence

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, messages_from_dict, message_to_dict

from settings import settings as config_data


class ChatHistory(BaseChatMessageHistory):
    def __init__(self, session_id):
        self.session_id = session_id
        self.storage_path = config_data.chat_history_storage_path
        self.history_file_path = os.path.join(self.storage_path, self.session_id)

    @property
    def messages(self) -> list[BaseMessage]:
        try:
            with open(self.history_file_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)    #读取json格式的历史数据返回字典对象
            return messages_from_dict(history_data)    #将字典对象转化成message格式并返回
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            return []

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        all_messages = list(self.messages)
        all_messages.extend(messages)
        new_messages = [message_to_dict(message) for message in all_messages]
        with open(self.history_file_path, "w", encoding="utf-8") as f:
            json.dump(new_messages, f)

    def clear(self) -> None:
        with open(self.history_file_path, "w", encoding="utf-8") as f:
            json.dump([],f)    #将空数组以json格式写入文件
