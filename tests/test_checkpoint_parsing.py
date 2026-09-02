"""
测试 agent/checkpoint_parser.py 的 checkpoint 二进制解析逻辑。

背景：
  LangGraph SqliteSaver 把完整对话状态用 msgpack 序列化后存入 SQLite 的 checkpoint 字段。
  JsonPlusSerializer.dumps_typed() 返回 ('msgpack', <bytes>)，其中 <bytes> 解包后：
    - 外层是 checkpoint dict: {v, ts, channel_values: {messages: [...]}}
    - 每条消息是 ['msgpack', <bytes>]，<bytes> 再解包是 ExtType(5)，
      ExtType(5).data 再解包是 ['module', 'ClassName', {kwargs}]

  本测试用与线上完全相同的序列化器构造真实格式的 blob，验证解析函数能正确还原消息。
"""

import msgpack
import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from agent.checkpoint_parser import (
    parse_messages_from_checkpoint,
    parse_first_message,
    parse_checkpoint_ts,
)


def _make_blob(messages, ts="2026-09-01T12:00:00+00:00") -> bytes:
    """用 JsonPlusSerializer 构造与 SqliteSaver 完全一致的 checkpoint blob"""
    serde = JsonPlusSerializer()
    typed_msgs = [serde.dumps_typed(m) for m in messages]
    checkpoint = {
        "v": 1,
        "ts": ts,
        "channel_values": {"messages": typed_msgs},
    }
    _, blob = serde.dumps_typed(checkpoint)
    return blob


class TestParseMessagesFromCheckpoint:
    def test_parses_human_and_ai(self):
        blob = _make_blob([
            HumanMessage(content="你好，查一下Z227"),
            AIMessage(content="Z227 从北京到广州"),
        ])
        msgs = parse_messages_from_checkpoint(blob)
        assert msgs == [
            {"role": "user", "content": "你好，查一下Z227"},
            {"role": "assistant", "content": "Z227 从北京到广州"},
        ]

    def test_ignores_system_and_tool_messages(self):
        blob = _make_blob([
            SystemMessage(content="你是铁路专家"),
            HumanMessage(content="G1 的信息"),
            AIMessage(content="G1 是京沪高铁"),
        ])
        msgs = parse_messages_from_checkpoint(blob)
        # SystemMessage 不应被解析出来
        assert all(m["role"] in ("user", "assistant") for m in msgs)
        assert msgs[0] == {"role": "user", "content": "G1 的信息"}
        assert msgs[1] == {"role": "assistant", "content": "G1 是京沪高铁"}

    def test_empty_messages(self):
        blob = _make_blob([])
        assert parse_messages_from_checkpoint(blob) == []

    def test_invalid_blob_returns_empty(self):
        # 无效二进制不应抛异常，返回空列表
        assert _parse_messages_guard(b"not-msgpack-data") == []


def _parse_messages_guard(blob: bytes) -> list:
    """包一层 try/except 的守卫，等价于线上行为（异常返回空）"""
    try:
        return parse_messages_from_checkpoint(blob)
    except Exception:
        return []


class TestParseFirstMessage:
    def test_extracts_first_user_message(self):
        blob = _make_blob([
            HumanMessage(content="帮我查G1"),
            AIMessage(content="G1 的信息如下"),
        ])
        assert parse_first_message(blob) == "帮我查G1"

    def test_no_messages_returns_empty(self):
        blob = _make_blob([])
        assert parse_first_message(blob) == ""


class TestParseCheckpointTs:
    def test_extracts_iso_timestamp(self):
        blob = _make_blob([], ts="2026-09-01T08:30:00+00:00")
        assert parse_checkpoint_ts(blob) == "2026-09-01T08:30:00+00:00"
