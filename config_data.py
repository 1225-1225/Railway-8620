# config_data.py
# 项目配置文件，包含所有模块的配置参数
# 注意：所有路径使用绝对路径，请根据你的实际项目位置修改

# ================== build_vector_store 模块配置 ==================
collection_name = "langchain-8620"
persist_directory = r"E:\PyCharm\LangChain-8620\data\vector_database"
chunk_size = 500
chunk_overlap = 77
separators = ["\n\n", "\n", "。", "？", "！", "，", ".", "?", "!", ","]
data_path = r"E:\PyCharm\LangChain-8620\data\cleaned_txts"
md5_path = r"E:\PyCharm\LangChain-8620\MD5"
split_starting_point = 1000

# ================== vector_store 模块配置 ==================
kwargs = 5

# ================== llm 模块配置 ==================
chat_model_name = "qwen3-max-2025-09-23"
session_config = {
    "configurable": {
        "session_id": "001"
    }
}

# ================== chat_history 模块配置 ==================
chat_history_storage_path = r"E:\PyCharm\LangChain-8620\chat_history"

# ================== agent 模块配置 ==================
history_database_name = "chat_history_check_pointer"

station_geojson_path = r"E:\PyCharm\LangChain-8620\data\city_to_node.pkl"
railway_geojson_path = r"E:\PyCharm\LangChain-8620\data\china_railway.pkl"
# 兼容旧变量（如有遗留代码依赖）
china_railway_path = railway_geojson_path
city_to_node_path = station_geojson_path
train_data_path = r"E:\PyCharm\LangChain-8620\data\train_data.json"
maps_output_dir = r"E:\PyCharm\LangChain-8620\frontend\public\maps"