from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from settings import settings as config_data

class VectorStoreService:
    def __init__(self):
        self.chroma = Chroma(
            collection_name=config_data.collection_name,
            embedding_function=OpenAIEmbeddings(
                model=config_data.embedding_model_name,
                api_key=config_data.DASHSCOPE_API_KEY,
                base_url=config_data.embedding_base_url,
                check_embedding_ctx_length=False,
            ),
            persist_directory=config_data.persist_directory
        )

    def get_retriever(self, kwargs=config_data.kwargs):
        return self.chroma.as_retriever(search_kwargs={"k":kwargs})
