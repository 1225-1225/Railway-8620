# ===== 后端 FastAPI =====
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖（部分 Python 包需要 C++ 运行时编译）
RUN apt-get update && apt-get install -y --no-install-recommends --no-install-suggests \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 先装 Python 依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 确保运行时目录存在且可写（共享地图、对话历史、知识库文件）
RUN mkdir -p /app/shared/maps /app/chat_history /app/data && chmod -R 777 /app/shared /app/chat_history /app/data

# 挂载点声明（地图、对话历史等持久化数据）
VOLUME ["/app/chat_history", "/app/shared/maps", "/app/data"]

EXPOSE 8000

CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
