"""测试 agent/chat_history.py —— 对话历史的增删读写"""
import os
import json
import tempfile
from unittest import mock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from agent.chat_history import ChatHistory

class TestChatHistoryBasic:
    """基本读写测试"""
    def test_new_session_has_no_messages(self, temp_dir):
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            history = ChatHistory("user_001")
            assert history.messages == []

    def test_add_one_message_then_read_back(self, temp_dir):
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            history = ChatHistory("user_001")
            history.add_messages([HumanMessage(content="你好")])
            msgs = history.messages
            assert len(msgs) == 1
            assert msgs[0].content == '你好'
            assert isinstance(msgs[0], HumanMessage)

    def test_multiple_messages_ordered(self, temp_dir):
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            history = ChatHistory("user_002")
            history.add_messages([HumanMessage(content="第1句")])
            history.add_messages([AIMessage(content="回复1")])
            history.add_messages([HumanMessage(content="第2句")])
            msgs = history.messages
            assert len(msgs) == 3
            assert msgs[0].content == "第1句"
            assert msgs[1].content == "回复1"
            assert msgs[2].content == "第2句"
            

    def test_add_multiple_at_once(self, temp_dir):
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            history = ChatHistory("user_003")
            history.add_messages([
                HumanMessage(content="A"),
                AIMessage(content="B"),
            ])
            assert len(history.messages) == 2
    
    def test_clear_empties_history(self, temp_dir):
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            history = ChatHistory("user_004")
            history.add_messages([HumanMessage(content="会被删掉")])
            assert len(history.messages) == 1

            history.clear()
            assert history.messages == []

    def test_corrupt_json_file_handle_gracefully(self, temp_dir):
        """文件内容是烂json -> 返回空列表, 不崩溃"""
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            # 手动写垃圾
            filepath = os.path.join(temp_dir, "corrupt_user") 
            with open(filepath, "w", encoding="UTF-8") as f:
                f.write("这不是json {{{")
            history = ChatHistory("corrupt_user")
            assert history.messages == []
    
    def test_nonexistent_file_returns_empty(self, temp_dir):
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            history = ChatHistory("nobody")
            assert history.messages == []

class TestChatHistoryPersistance:
    """持久化到文件测试"""

    def test_message_written_to_disk(self, temp_dir):
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            history = ChatHistory("disk_test")
            history.add_messages([HumanMessage(content="持久化测试")])
            filepath = os.path.join(temp_dir, "disk_test")
            assert os.path.exists(filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data[0]["data"]["content"] == "持久化测试"

    def test_different_sessions_isolated(self, temp_dir):
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            h1 = ChatHistory("u1")
            h2 = ChatHistory("u2")

            h1.add_messages([HumanMessage(content="用户1")])
            h2.add_messages([HumanMessage(content="用户2")])

            assert h1.messages[0].content == "用户1"
            assert h2.messages[0].content == "用户2"

    def test_system_message_roundtrip(self, temp_dir):
        """SystemMessage 也能正确的序列化和反序列化"""
        with mock.patch("agent.chat_history.config_data") as cfg:
            cfg.chat_history_storage_path = temp_dir
            history = ChatHistory("sys_test")
            history.add_messages([SystemMessage(content="系统提示")])

            msgs = history.messages
            assert len(msgs) == 1
            assert isinstance(msgs[0], SystemMessage)
            assert msgs[0].content == "系统提示"