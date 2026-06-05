# 无人值守财务矩阵浏览器实测
# 前置: :3000 :8000 Hermes + Chrome 调试端口 9222
# 用法: .\backend\scripts\finance_matrix_unattended.ps1

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root

Write-Host "== preflight ==" -ForegroundColor Cyan
try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/agent/status" -UseBasicParsing -TimeoutSec 8
} catch {
    Write-Error "backend :8000 未就绪"
}
try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:9222/json/version" -UseBasicParsing -TimeoutSec 5
} catch {
    Write-Host @"

Chrome 调试端口 9222 未监听。请先启动（与 Chrome DevTools MCP 可共用）:
  chrome.exe --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=$env:TEMP\orientg-cdp http://localhost:3000

"@ -ForegroundColor Yellow
    exit 1
}

py -3.10 backend/scripts/finance_matrix_browser_loop.py activate
Write-Host "== CDP runner 开始（失败即停，须修代码后重跑）==" -ForegroundColor Cyan
py -3.10 backend/scripts/finance_matrix_browser_cdp_runner.py @args
$code = $LASTEXITCODE
py -3.10 backend/scripts/finance_matrix_browser_loop.py status
exit $code
