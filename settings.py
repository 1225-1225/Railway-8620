import os
from pydantic_settings import BaseSettings, SettingsConfigDict

#项目根目录：settings.py所在目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class Settings(BaseSettings):
    # RAGFlow 配置
    ragflow_host: str = "http://localhost:9380"
    ragflow_api_key: str = ""
    ragflow_dataset_id: str = ""

    # 检索
    kwargs: int = 5
    ragflow_similarity_threshold: float = 0.0

    # LLM 供应商（openai / anthropic）
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model_name: str = "deepseek-v4-flash"
    llm_base_url: str = ""

    # Embedding 供应商（阿里百炼等兼容 OpenAI 格式的服务）
    embedding_provider: str = "openai"
    embedding_api_key: str = ""
    embedding_model_name: str = "text-embedding-v4"
    embedding_base_url: str = ""

    # 对话历史
    session_config: dict = {"configurable": {"session_id": "001"}}
    chat_history_storage_path: str = ""
    history_database_name: str = "chat_history_check_pointer"

    # 数据路径（用于迁移脚本等）
    data_path: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def _apply_path_defaults(s: Settings):
    """补全未在.env中指定的相对路径"""
    if not s.data_path:
        s.data_path = os.path.join(PROJECT_ROOT, "data", "cleaned_txts")
    if not s.chat_history_storage_path:
        s.chat_history_storage_path = os.path.join(PROJECT_ROOT, "chat_history")


def _resolve_env_var_refs(s: Settings):
    """将 API Key 字段中的环境变量名引用替换为实际值

    `.env` 中两种写法都支持：
        llm_api_key=sk-xxx        → 直接用
        llm_api_key=DEEPSEEK_API_KEY  → 视为环境变量名，取 os.environ["DEEPSEEK_API_KEY"]
    """
    for field in ("llm_api_key", "embedding_api_key", "ragflow_api_key"):
        raw = getattr(s, field)
        if raw and raw in os.environ and os.environ[raw]:
            setattr(s, field, os.environ[raw])


class _SettingsProxy:
    """代理类：支持运行时从 .env 重新加载配置，无需重启进程"""

    def __init__(self):
        object.__setattr__(self, "_settings", None)
        self._load()

    def _load(self):
        s = Settings()
        _apply_path_defaults(s)
        _resolve_env_var_refs(s)
        object.__setattr__(self, "_settings", s)

    def reload(self):
        """从 .env 重新加载所有配置"""
        self._load()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._settings, name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._settings, name, value)


settings = _SettingsProxy()