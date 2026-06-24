import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field

#项目根目录：settings.py所在目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class Settings(BaseSettings):
    # 向量库和RAG
    collection_name: str = "langchain-8620"
    persist_directory: str = ""
    chunk_size: int = 500
    chunk_overlap: int = 77
    separators: list = ["\n\n", "\n", "。", "？", "！", "，", ".", "?", "!", ","]
    data_path: str = ""
    md5_path: str = ""
    split_starting_point: int = 1000

    # 检索
    kwargs: int = 5

    # LLM
    chat_model_name: str = "deepseek-v4-flash"

    # LLM 供应商（openai / anthropic）
    llm_provider: str = "openai"
    OPENCODE_GO_API_KEY: str = Field("", validation_alias=AliasChoices("OPENCODE_GO_API_KEY", "llm_api_key"))
    llm_model_name: str = "qwen3-max-2025-09-23"
    llm_base_url: str = ""

    # Embedding 供应商（阿里百炼等兼容 OpenAI 格式的服务）
    embedding_provider: str = "openai"
    DASHSCOPE_API_KEY: str = Field("", validation_alias=AliasChoices("DASHSCOPE_API_KEY", "embedding_api_key"))
    embedding_model_name: str = "text-embedding-v4"
    embedding_base_url: str = ""

    # 对话历史
    session_config: dict = {"configurable": {"session_id": "001"}}
    chat_history_storage_path: str = ""
    history_database_name: str = "chat_history_check_pointer"

    # 铁路图数据
    station_geojson_path: str = ""
    railway_geojson_path: str = ""
    train_data_path: str = ""
    maps_output_dir: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# 自动补全相对路径（基于PROJECT_ROOT）
settings = Settings()

# 只有没在.env里指定的路径，才使用默认的相对路径
if not settings.persist_directory:
    settings.persist_directory = os.path.join(PROJECT_ROOT, "data", "vector_database")
if not settings.data_path:
    settings.data_path = os.path.join(PROJECT_ROOT, "data", "cleaned_txts")
if not settings.md5_path:
    settings.md5_path = os.path.join(PROJECT_ROOT, "MD5")
if not settings.chat_history_storage_path:
    settings.chat_history_storage_path = os.path.join(PROJECT_ROOT, "chat_history")
if not settings.station_geojson_path:
    settings.station_geojson_path = os.path.join(PROJECT_ROOT, "data", "city_to_node.pkl")
if not settings.railway_geojson_path:
    settings.railway_geojson_path = os.path.join(PROJECT_ROOT, "data", "china_railway.pkl")
if not settings.train_data_path:
    settings.train_data_path = os.path.join(PROJECT_ROOT, "data", "train_data.json")
if not settings.maps_output_dir:
    settings.maps_output_dir = os.path.join(PROJECT_ROOT, "frontend", "public", "maps")