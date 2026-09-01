"""
Agent 并发安全集成测试。

背景：
  生产环境中，api.py 会在有界线程池里并发跑 agent.stream()，所有请求共享
  同一个 SqliteSaver（同一个 SQLite 连接）。这要求：
    - SQLite 连接开启 WAL 模式（读写不互斥）
    - busy_timeout 兜底写锁竞争
    - SqliteSaver 自带 threading.Lock 保护写路径

  本测试用 真实的 SqliteSaver + 假 LLM（不联网）+ 多线程并发，验证：
    1. 并发执行不抛 database is locked 等异常
    2. 每个线程的对话状态正确持久化（thread_id 隔离）
    3. 状态能从 checkpoint 恢复
"""

import os
import sqlite3
import threading
import tempfile

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from agent.agent import AgentService


@pytest.fixture
def sqlite_agent():
    """构造一个使用真实 SqliteSaver（WAL + busy_timeout）的无工具 agent"""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test_checkpoint.db")
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    saver = SqliteSaver(conn)
    fake_llm = FakeMessagesListChatModel(responses=[AIMessage(content="ok")])
    agent = create_agent(model=fake_llm, tools=[], checkpointer=saver)
    yield agent
    conn.close()


def test_concurrent_invokes_no_locked_errors(sqlite_agent):
    """20 个线程并发 invoke，不应抛 database is locked 等异常"""
    errors = []
    results = []

    def worker(i):
        try:
            cfg = {"configurable": {"thread_id": f"thread_{i}"}}
            r = sqlite_agent.invoke(
                {"messages": [{"role": "user", "content": f"问题{i}"}]}, config=cfg
            )
            results.append(r["messages"][-1].content)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"并发执行出现错误: {errors}"
    assert len(results) == 20


def test_thread_id_isolation(sqlite_agent):
    """不同 thread_id 的对话状态应互相隔离"""
    # 线程 A 连续问两轮（同一 thread_id）
    cfg_a = {"configurable": {"thread_id": "user_a"}}
    sqlite_agent.invoke({"messages": [{"role": "user", "content": "第一问"}]}, config=cfg_a)
    sqlite_agent.invoke({"messages": [{"role": "user", "content": "第二问"}]}, config=cfg_a)

    # 线程 B 只问一轮（不同 thread_id）
    cfg_b = {"configurable": {"thread_id": "user_b"}}
    sqlite_agent.invoke({"messages": [{"role": "user", "content": "B 的问题"}]}, config=cfg_b)

    # 从 checkpoint 恢复
    state_a = sqlite_agent.get_state(cfg_a)
    state_b = sqlite_agent.get_state(cfg_b)

    msgs_a = state_a.values["messages"]
    msgs_b = state_b.values["messages"]

    # 隔离性核心断言：
    #   A 里包含 A 的两条问题，且不含 B 的问题
    contents_a = [m.content for m in msgs_a if getattr(m, "type", "") == "human"]
    contents_b = [m.content for m in msgs_b if getattr(m, "type", "") == "human"]

    assert "第一问" in contents_a
    assert "第二问" in contents_a
    assert "B 的问题" not in contents_a  # A 不应被 B 污染

    assert "B 的问题" in contents_b
    assert "第一问" not in contents_b  # B 不应被 A 污染


def test_agent_service_uses_wal_mode():
    """AgentService 创建的连接应开启 WAL + busy_timeout（并发安全的必要条件）"""
    service = AgentService()
    try:
        pragma = service.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert pragma.upper() == "WAL"
        busy = service.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy == 30000
    finally:
        service.close()
