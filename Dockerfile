# ===== 后端 FastAPI =====
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖（chromadb 需要 C++ 运行时）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 先装 Python 依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 挂载点声明（向量库、对话历史等持久化数据）
VOLUME ["/app/data/vector_database", "/app/chat_history"]

EXPOSE 8000

CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
