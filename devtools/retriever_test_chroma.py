from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from settings import settings as config_data

vectordb = Chroma(
    collection_name=config_data.collection_name,
    embedding_function=DashScopeEmbeddings(model="text-embedding-v4"),
    persist_directory=config_data.persist_directory
)

# 检查文档总数
print(f"文档总数: {vectordb._collection.count()}")

# 尝试获取一些文档内容（不进行检索）
all_docs = vectordb.get(limit=5)  # 获取前5条文档
if all_docs and all_docs['documents']:
    print("文档样例：")
    for i, doc in enumerate(all_docs['documents']):
        print(f"{i+1}: {doc[:100]}...")  # 打印前100字符
else:
    print("向量库中没有文档！")

# 测试检索
query = "ND5机车的长度是多少？"
docs = vectordb.similarity_search(query, k=3)
print(f"检索到 {len(docs)} 个文档")
for i, doc in enumerate(docs):
    print(f"--- 结果 {i+1} ---")
    print(doc.page_content)
    print(f"元数据: {doc.metadata}\n")