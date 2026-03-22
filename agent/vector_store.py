from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings

import config_data

class VectorStoreService:
    def __init__(self):
        self.chroma = Chroma(
            collection_name=config_data.collection_name,
            embedding_function=DashScopeEmbeddings(model="text-embedding-v4"),
            persist_directory=config_data.persist_directory
        )

    def get_retriever(self, kwargs=config_data.kwargs):
        return self.chroma.as_retriever(search_kwargs={"k":kwargs})
