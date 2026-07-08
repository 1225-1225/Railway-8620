import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from settings import settings as config_data


def create_llm(**kwargs):
    '''根据配置创建LLM实例'''
    provider = config_data.llm_provider
    if provider == "openai":
        return ChatOpenAI(
            model=config_data.llm_model_name,
            api_key=config_data.llm_api_key,
            base_url=config_data.llm_base_url,
            **kwargs
        )
    elif provider == "anthropic":
        return ChatAnthropic(
            model=config_data.llm_model_name,
            api_key=config_data.llm_api_key,
            base_url=config_data.llm_base_url,
            **kwargs
        )
