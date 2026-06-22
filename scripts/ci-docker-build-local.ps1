# 本地模拟 .github/workflows/docker-publish.yml 的镜像构建（不 push 到 ghcr.io）
# 在项目根目录执行: .\scripts\ci-docker-build-local.ps1
#
# 与 CI 对齐：backend 普通 build；frontend 使用 --no-cache（与 workflow 一致）。
# 日常改 frontend 可先跑 cd frontend && npm run lint && npm run build（更快）。

param(
    [switch]$CacheFrontend
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 docker 命令。请先安装 Docker 并确保其在 PATH 中。"
}

function Invoke-DockerBuild {
    param(
        [string[]]$Args,
        [string]$Label
    )
    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    & docker @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker build 失败: $Label"
    }
}

Write-Host "Orient-G 本地 Docker 构建（模拟 CI，不 push）" -ForegroundColor Green
Write-Host "仓库根: $root"

Invoke-DockerBuild @(
    "build",
    "-f", "backend/Dockerfile",
    "-t", "orient-g-backend:local",
    "."
) "backend"

$frontendArgs = @(
    "build",
    "-f", "frontend/Dockerfile",
    "-t", "orient-g-frontend:local",
    "."
)
if (-not $CacheFrontend) {
    $frontendArgs = @("build", "--no-cache") + $frontendArgs[1..($frontendArgs.Length - 1)]
}
Invoke-DockerBuild $frontendArgs "frontend$(if ($CacheFrontend) { ' (cache enabled)' } else { ' (--no-cache)' })"

Write-Host ""
Write-Host "构建成功。本地镜像:" -ForegroundColor Green
Write-Host "  orient-g-backend:local"
Write-Host "  orient-g-frontend:local"
Write-Host "未推送到 ghcr.io；push 到 main 后由 GitHub Actions 发布。"
