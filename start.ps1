# Railway-8620 一键启动脚本
# 用法: .\start.ps1 [ragflow]
#   ragflow - 可选，同时启动 RAGFlow 知识库并自动初始化

param(
    [string]$Mode = ""
)

# 确保 PowerShell 正确输出中文
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "🚂 Railway-8620 启动中..." -ForegroundColor Cyan

# 启动前后端
Write-Host "→ 启动 backend + frontend ..." -ForegroundColor Yellow
docker compose up -d

if ($Mode -eq "ragflow") {
    Write-Host "→ 启动 RAGFlow 知识库服务 ..." -ForegroundColor Yellow
    docker compose -f docker-compose.ragflow.yml up -d

    Write-Host "→ 等待 RAGFlow 就绪并自动初始化 ..." -ForegroundColor Yellow
    Write-Host "  （将自动注册账号、创建知识库、上传 150+ 篇铁路文档）" -ForegroundColor DarkYellow

    # 运行初始化脚本（复用本地 Python 环境）
    python agent/ragflow_init.py

    Write-Host "✅ RAGFlow 初始化完成，知识库已可用" -ForegroundColor Green
}

Write-Host "`n📋 服务状态:" -ForegroundColor Cyan
docker compose ps

Write-Host "`n🌐 访问地址:" -ForegroundColor Cyan
Write-Host "  前端:          http://localhost:8620" -ForegroundColor White
Write-Host "  后端 API:      http://localhost:8000/docs" -ForegroundColor White
if ($Mode -eq "ragflow") {
    Write-Host "  RAGFlow:       http://localhost:9380" -ForegroundColor White
    Write-Host "  管理员账号:     admin / admin123" -ForegroundColor White
}
