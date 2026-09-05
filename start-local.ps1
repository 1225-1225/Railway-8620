# Railway-8620 本地开发一键启动脚本（不依赖 Docker）
# 用法: .\start-local.ps1
#   启动后端 (uvicorn :8000) + 前端 (vite :8620)
#
# 前置要求:
#   - Python 环境已激活（conda activate railway-8620）
#   - 前端依赖已安装（cd frontend && npm install）

param(
    [switch]$NoFrontend   # 只启动后端，不启动前端
)

# 确保 PowerShell 正确输出中文
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "🚂 Railway-8620 本地启动中..." -ForegroundColor Cyan

# 检查 Python
$PythonCmd = "python"
if (Test-Path "C:/Users/1225/.conda/envs/railway-8620/python.exe") {
    $PythonCmd = "C:/Users/1225/.conda/envs/railway-8620/python.exe"
}
Write-Host "→ 使用 Python: $PythonCmd" -ForegroundColor DarkGray

# 检查 .env 是否存在
if (-not (Test-Path ".env")) {
    Write-Host "⚠️ 未找到 .env，请先复制 .env.example 并配置 API Key" -ForegroundColor Yellow
    exit 1
}

# 启动后端（后台）
Write-Host "→ 启动后端 (uvicorn :8000) ..." -ForegroundColor Yellow
$backend = Start-Process -FilePath $PythonCmd -ArgumentList "-m", "uvicorn", "backend.api:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden
Write-Host "  后端 PID: $($backend.Id)" -ForegroundColor DarkGray

# 等待后端就绪
Write-Host "→ 等待后端就绪 ..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}
if ($ready) {
    Write-Host "  ✅ 后端已就绪" -ForegroundColor Green
} else {
    Write-Host "  ⚠️ 后端未在 15 秒内就绪，请检查日志" -ForegroundColor Yellow
}

# 启动前端（后台）
if (-not $NoFrontend) {
    Write-Host "→ 启动前端 (vite :8620) ..." -ForegroundColor Yellow
    # Windows 上 npm 是 npm.cmd，Start-Process 需要完整可执行文件名
    $npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npmCmd) { $npmCmd = "npm.cmd" }
    $frontend = Start-Process -FilePath $npmCmd -ArgumentList "run", "dev" -WorkingDirectory (Join-Path $ProjectRoot "frontend") -PassThru -WindowStyle Hidden
    Write-Host "  前端 PID: $($frontend.Id)" -ForegroundColor DarkGray
}

Write-Host "`n🌐 访问地址:" -ForegroundColor Cyan
Write-Host "  前端:          http://localhost:8620" -ForegroundColor White
Write-Host "  后端 API:      http://localhost:8000/docs" -ForegroundColor White
Write-Host "`n📌 提示:" -ForegroundColor Cyan
Write-Host "  - 停止服务: 在任务管理器结束对应 PID，或重启终端" -ForegroundColor DarkGray
Write-Host "  - 知识类问题需先启动 RAGFlow: .\start.ps1 ragflow" -ForegroundColor DarkGray
Write-Host "  - 车次/地图类问题无需 RAGFlow，可直接使用" -ForegroundColor DarkGray
