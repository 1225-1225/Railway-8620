# frontend/app_qa.py
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

import streamlit as st
from langchain_core.messages import AIMessage, AIMessageChunk  # 导入消息类型

import config_data
from agent.agent import AgentService

# 页面配置
st.set_page_config(
    page_title="中国铁路历史专家",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("🚂 中国铁路历史专家")
st.caption("基于 LangChain Agent + RAG 的铁路知识助手，支持多轮对话")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent" not in st.session_state:
    with st.spinner("正在加载智能体，请稍候..."):
        st.session_state.agent = AgentService().agent

thread_id = config_data.session_config["configurable"]["session_id"]
config = {"configurable": {"thread_id": thread_id}}

# 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("请输入您的问题..."):
    # 显示用户消息
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 调用 Agent 流式输出
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        for chunk in st.session_state.agent.stream(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config,
            stream_mode="messages",
        ):
            # 处理可能的元组（某些版本返回 (message, metadata)）
            if isinstance(chunk, tuple):
                msg = chunk[0]
            else:
                msg = chunk

            # 🚀 关键修改：只处理 AI 生成的消息，忽略工具消息
            if isinstance(msg, (AIMessage, AIMessageChunk)) and msg.content:
                full_response += msg.content
                response_placeholder.markdown(full_response + "▌")

        # 显示最终完整回答
        response_placeholder.markdown(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})