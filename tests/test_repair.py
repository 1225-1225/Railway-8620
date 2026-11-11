"""
测试 backend/api.py 的图状态修复机制：_repair_incomplete_tool_calls

背景（实测得出，详见 docs/interview-qa-code.md 第五章 Q7）：
ReAct 图是 `model ⇄ tools` 两节点循环，流式请求被超时切断时可能停在
两个不同的截断点：

    T1: AI[tool_calls]            —— 工具还没跑（下一次请求会因未配对而持续失败）
    T2: AI[tool_calls] → Tool     —— 工具跑完了，模型没输出最终回答（静默丢一轮）

T2 更隐蔽：消息序列本身合法、不报错，所以旧判定（看最后一条有没有
tool_calls）会漏掉它。本测试锁定"用 state.next 判定"能同时覆盖两者，
且不会重复执行工具、不会误伤正常完成的会话。

测试用真实 create_agent + SqliteSaver（内存/临时文件）+ 脚本化假模型，
只替换 LLM 这一层，其余（图结构、checkpoint 提交时机、恢复机制）都是真的。
"""
import sqlite3
from unittest import mock

import pytest
from langchain.agents import create_agent
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import Field

from backend.api import _repair_incomplete_tool_calls


# ── 假模型：按脚本回话，支持 bind_tools（create_agent 必需）────────────
class ScriptedToolModel(BaseChatModel):
    """最小可控的聊天模型。

    为什么要自己写而不是用 MagicMock：create_agent 需要 bind_tools 返回
    一个可调用的模型对象，且图执行过程中会多次调用它（每轮 ReAct 一次）。
    脚本用 `turns` 列表驱动，`hits` 记录被调用次数，便于断言"模型是否被补跑"。
    """

    turns: list[BaseMessage] = Field(default_factory=list)
    hits: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-model"

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self

    def _next_message(self) -> BaseMessage:
        self.hits += 1
        if self.turns:
            return self.turns.pop(0)
        return AIMessage(content="(脚本用尽)")

    def _generate(  # type: ignore[override]
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=self._next_message())]
        )

    def _stream(  # type: ignore[override]
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ):
        msg = self._next_message()
        text = msg.content if isinstance(msg.content, str) else ""
        for ch in (text or " "):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=ch))
            if run_manager:
                run_manager.on_llm_new_token(ch, chunk=chunk)
            yield chunk


# ── 工具：每次执行计数，用于断言"有没有被重复执行"──────────────
CALL_COUNT = {"echo": 0}


@tool
def echo(text: str) -> str:
    """回显文本（测试用工具）。"""
    CALL_COUNT["echo"] += 1
    return f"echo:{text}"


def _make_agent(turns: list[BaseMessage]):
    """构造 真 create_agent + 真 SqliteSaver + 假模型。"""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    model = ScriptedToolModel(turns=list(turns))
    agent = create_agent(
        model=model,
        tools=[echo],
        checkpointer=SqliteSaver(conn),
    )
    return agent, model, conn


def _standard_turns() -> list[BaseMessage]:
    """一轮完整对话：先调工具，再给最终回答。"""
    return [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "echo", "args": {"text": "hi"}, "id": "call_1"}
            ],
        ),
        AIMessage(content="最终回答"),
        AIMessage(content="第二问的回答"),
    ]


def _cut_stream(agent, config: dict, n_events: int) -> None:
    """模拟"客户端/进程在中途挂掉"：只消费 n 个事件就丢弃迭代器。"""
    gen = agent.stream(
        {"messages": [HumanMessage(content="问题一")]},
        config=config,
        stream_mode="updates",
    )
    try:
        for _ in range(n_events):
            try:
                next(gen)
            except StopIteration:
                break
    finally:
        gen.close()


def _dangling_tool_call_ids(messages) -> list[str]:
    """找出没有被任何 ToolMessage 应答的 tool_call id。"""
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    out: list[str] = []
    for m in messages:
        if isinstance(m, AIMessage):
            out += [
                tc["id"] for tc in (m.tool_calls or []) if tc["id"] not in answered
            ]
    return out


# ── 测试 ───────────────────────────────────────────────────────
class TestRepairIncompleteToolCalls:
    """修复机制的边界：T1 / T2 必须修，正常完成必须不修。"""

    def setup_method(self):
        CALL_COUNT["echo"] = 0

    def test_t1_missing_tool_execution_is_repaired(self):
        """T1：模型出了 tool_calls、工具没跑 → 修复后工具补跑、悬空消除。"""
        agent, model, conn = _make_agent(_standard_turns())
        config = {"configurable": {"thread_id": "t1"}}

        _cut_stream(agent, config, n_events=1)  # 只跑到 model 输出 tool_calls

        state = agent.get_state(config)
        assert state.next == ("tools",), "截断后应停在 tools 节点"
        assert _dangling_tool_call_ids(state.values["messages"]) == ["call_1"]
        assert CALL_COUNT["echo"] == 0, "工具不该跑过"

        _repair_incomplete_tool_calls(agent, config)

        repaired = agent.get_state(config)
        assert CALL_COUNT["echo"] == 1, "修复应补跑工具"
        assert _dangling_tool_call_ids(repaired.values["messages"]) == []
        assert repaired.next == (), "修复后不应再有待执行节点"
        conn.close()

    def test_t2_missing_final_answer_is_repaired(self):
        """T2：工具已回写、模型没出最终回答 → 旧判定会漏掉，新判定应补上。

        这是本测试的核心：T2 的序列是合法的（tool_calls 全配对），
        所以"能跑通"不等于"没丢东西"——丢的是上一个问题的回答。
        """
        agent, model, conn = _make_agent(_standard_turns())
        config = {"configurable": {"thread_id": "t2"}}

        _cut_stream(agent, config, n_events=2)  # model + tools 都跑完了

        state = agent.get_state(config)
        assert state.next == ("model",), "截断后应停在 model 节点（待收尾）"
        # 关键：旧判定看最后一条消息的 tool_calls，这里是 ToolMessage → 判定为 False
        last = state.values["messages"][-1]
        assert isinstance(last, ToolMessage)
        assert not getattr(last, "tool_calls", None), "旧判定在这里必然漏掉"
        assert _dangling_tool_call_ids(state.values["messages"]) == [], (
            "序列本身合法，所以不会报错——这正是 T2 隐蔽的原因"
        )

        _repair_incomplete_tool_calls(agent, config)

        repaired = agent.get_state(config)
        messages = repaired.values["messages"]
        assert repaired.next == ()
        assert messages[-1].content == "最终回答", "被丢掉的回答应被补出来"
        assert CALL_COUNT["echo"] == 1, (
            "工具不该被重复执行——ToolMessage 已在状态里，只补跑模型节点"
        )
        conn.close()

    def test_normal_completion_does_not_trigger_repair(self):
        """正常跑完（next 为空）→ 修复不应触发，模型也不该被多调一次。"""
        agent, model, conn = _make_agent(_standard_turns())
        config = {"configurable": {"thread_id": "normal"}}

        agent.invoke({"messages": [HumanMessage(content="问题一")]}, config=config)

        state = agent.get_state(config)
        assert state.next == ()
        hits_before = model.hits
        calls_before = CALL_COUNT["echo"]

        _repair_incomplete_tool_calls(agent, config)

        assert model.hits == hits_before, "修复不该在正常会话上多做一次模型调用"
        assert CALL_COUNT["echo"] == calls_before
        conn.close()

    def test_fresh_session_does_not_trigger_repair(self):
        """全新会话（还没有任何 checkpoint 状态）→ 安全返回，不抛异常。"""
        agent, model, conn = _make_agent(_standard_turns())
        config = {"configurable": {"thread_id": "brand-new"}}

        _repair_incomplete_tool_calls(agent, config)  # 不应抛任何异常

        assert model.hits == 0
        assert CALL_COUNT["echo"] == 0
        conn.close()

    def test_repair_failure_is_swallowed_and_logged(self):
        """修复过程中 invoke 抛异常 → 被吞掉并记日志，不向上传播。

        理由：修复是"尽力而为"的兜底，修不好也不该让请求整体 500——
        最坏情况只是这一轮丢掉，用户可以换会话继续。
        """
        agent, model, conn = _make_agent(_standard_turns())
        config = {"configurable": {"thread_id": "boom"}}
        _cut_stream(agent, config, n_events=1)

        with mock.patch.object(
            agent, "invoke", side_effect=RuntimeError("模拟修复失败")
        ), mock.patch("backend.api.logger") as mock_logger:
            _repair_incomplete_tool_calls(agent, config)  # 不应抛出

        mock_logger.warning.assert_called_once()
        assert "模拟修复失败" in str(mock_logger.warning.call_args)
        conn.close()

    def test_repair_enables_subsequent_conversation(self):
        """修复后能正常接续对话（不会因为畸形历史而持续失败）。"""
        agent, model, conn = _make_agent(_standard_turns())
        config = {"configurable": {"thread_id": "continue"}}

        _cut_stream(agent, config, n_events=1)
        _repair_incomplete_tool_calls(agent, config)

        out = agent.invoke(
            {"messages": [HumanMessage(content="问题二")]}, config=config
        )
        messages = out["messages"]
        assert _dangling_tool_call_ids(messages) == []
        assert messages[-1].content == "第二问的回答"
        conn.close()
