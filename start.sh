#!/bin/bash
# Railway-8620 一键启动脚本
# 用法: ./start.sh [ragflow]
#   ragflow - 可选，同时启动 RAGFlow 知识库并自动初始化

echo "🚂 Railway-8620 启动中..."

# 启动前后端
echo "→ 启动 backend + frontend ..."
docker compose up -d

if [ "$1" = "ragflow" ]; then
    echo "→ 启动 RAGFlow 知识库服务 ..."
    docker compose -f docker-compose.ragflow.yml up -d

    echo "→ 等待 RAGFlow 就绪并自动初始化 ..."
    echo "  （将自动注册账号、创建知识库、上传 150+ 篇铁路文档）"

    # 运行初始化脚本
    python agent/ragflow_init.py

    echo "✅ RAGFlow 初始化完成，知识库已可用"
fi

echo ""
echo "📋 服务状态:"
docker compose ps

echo ""
echo "🌐 访问地址:"
echo "  前端:          http://localhost:8620"
echo "  后端 API:      http://localhost:8000/docs"
if [ "$1" = "ragflow" ]; then
    echo "  RAGFlow:       http://localhost:9380"
    echo "  管理员账号:     admin / admin123"
fi
