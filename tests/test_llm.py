"""测试 agent/llm.py —— create_llm 工厂函数"""
from unittest import mock

class TestCreateLlmOpenAI:
    """provider=openai"""
    def test_returns_chat_openai(self):
        with mock.patch("agent.llm.config_data") as cfg:
            cfg.llm_provider = "openai"
            cfg.llm_model_name = "deepseek-v4-pro"
            cfg.llm_api_key = "sk-test"
            cfg.llm_base_url = "https://opencode.ai/zen/go/v1"

            from langchain_openai import ChatOpenAI
            from agent.llm import create_llm

            llm = create_llm()
            assert isinstance(llm, ChatOpenAI)
    
    def test_passes_all_parameters(self):
        with mock.patch("agent.llm.config_data") as cfg:
            cfg.llm_provider = "openai"
            cfg.llm_model_name = "my-model"
            cfg.llm_api_key = "sk-test"
            cfg.llm_base_url = "https://proxy.com/v1"

            from agent.llm import create_llm
            llm = create_llm(temperature=0.5, max_tokens = 1000, streaming=True)

            assert llm.model_name == "my-model"
            assert llm.openai_api_base == "https://proxy.com/v1"
            assert llm.temperature == 0.5
            assert llm.max_tokens == 1000

class TestCreateLlmAnthropic:
    """provider=anthropic"""
    def test_create_chat_anthropic(self):
        with mock.patch("agent.llm.config_data") as cfg:
            cfg.llm_provider = "anthropic"
            cfg.llm_model_name = "claude-sonnet-4-20250514"
            cfg.llm_api_key = "sk-ant-test"
            cfg.llm_base_url = "https://api.anthropic.com"

            from agent.llm import create_llm
            from langchain_anthropic import ChatAnthropic
            llm = create_llm()

            assert isinstance(llm, ChatAnthropic)