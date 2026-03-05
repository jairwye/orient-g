# Orient-G（财务信息内网）- 本地一键安装（Windows PowerShell）
# 在项目根目录执行: .\scripts\setup.ps1
# 策略：适合项目内的仅项目内（Python .venv、frontend/node_modules）；Node 不适合限制在项目目录，采用全局安装（winget）。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Refresh-EnvPath {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host "项目根目录: $root"
Write-Host "一键安装将配置：Python 虚拟环境（项目内）、后端依赖、Node.js（全局）、前端依赖、.env、uploads；PostgreSQL 需本机单独安装。"
Write-Host ""

# ---------- 1. Python 虚拟环境（项目内 .venv）----------
$pythonOk = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonOk) {
    Write-Host "[1/6] 未检测到 Python，尝试通过 winget 全局安装..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        Refresh-EnvPath
        $pythonOk = Get-Command python -ErrorAction SilentlyContinue
    }
    if (-not $pythonOk) {
        Write-Host "  -> 安装后仍无法找到 python。请关闭本窗口、新开终端后重新运行本脚本，或从 https://www.python.org/ 手动安装。"
        Read-Host "按 Enter 键退出"
        exit 1
    }
    Write-Host "  -> Python 已就绪（全局），继续创建项目内 .venv。"
}
if (-not (Test-Path ".venv")) {
    Write-Host "[1/6] 创建 Python .venv（项目内）..."
    python -m venv .venv
    Write-Host "  -> 完成"
} else {
    Write-Host "[1/6] .venv 已存在，跳过。"
}
Write-Host "[2/6] 安装后端依赖（venv 内）..."
& .\.venv\Scripts\pip.exe install -r backend\requirements.txt --quiet
Write-Host "  -> 完成"

# ---------- 2. Node.js（不适合项目内限制，采用全局安装）----------
$nodeDir = $null
$nodeSubdirs = Get-ChildItem -Path ".node" -Directory -ErrorAction SilentlyContinue
if ($nodeSubdirs) {
    foreach ($d in $nodeSubdirs) {
        if (Test-Path (Join-Path $d.FullName "node.exe")) {
            $nodeDir = $d.FullName
            break
        }
    }
}
if ($nodeDir) {
    $env:Path = "$nodeDir;$env:Path"
    Write-Host "[3/6] 使用已有项目内 Node.js (.node) ..."
} elseif (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "[3/6] 使用系统已安装的 Node.js（全局）..."
} else {
    Write-Host "[3/6] 未检测到 Node.js，通过 winget 全局安装..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
        Refresh-EnvPath
        $nodeDir = "C:\Program Files\nodejs"
        if (Test-Path (Join-Path $nodeDir "node.exe")) {
            $env:Path = "$nodeDir;$env:Path"
        }
    }
    $nodeOk = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeOk) {
        Write-Host "  -> 安装后仍无法找到 node。请关闭本窗口、新开终端后重新运行本脚本，或从 https://nodejs.org/ 手动安装 LTS。"
        Read-Host "按 Enter 键退出"
        exit 1
    }
    Write-Host "  -> 已通过 winget 安装 Node.js（全局）"
}

# ---------- 3. 前端依赖（项目内 frontend/node_modules）----------
Write-Host "[4/6] 安装前端依赖（frontend/node_modules）..."
Set-Location frontend
& npm install --no-audit --no-fund
if ($LASTEXITCODE -eq 0) {
    Write-Host "  -> 安装完成，正在执行 npm audit fix（修复可安全升级的漏洞）..."
    & npm audit fix
    if ($LASTEXITCODE -ne 0) { Write-Host "  -> audit fix 有未修复项，可稍后手动运行 npm audit 查看。" }
}
Set-Location $root
Write-Host "  -> 完成"

# ---------- 4. .env ----------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[5/6] 已复制 .env.example -> .env（请编辑 .env 填写数据库连接等）"
} else {
    Write-Host "[5/6] .env 已存在，未覆盖。"
}

# ---------- 5. uploads 目录 ----------
if (-not (Test-Path "uploads")) {
    New-Item -ItemType Directory -Path "uploads" | Out-Null
    Write-Host "[6/6] 已创建 uploads 目录。"
} else {
    Write-Host "[6/6] uploads 目录已存在。"
}

# ---------- PostgreSQL 检测（仅提示，无法项目内安装）----------
$pgOk = $false
if (Get-Command psql -ErrorAction SilentlyContinue) { $pgOk = $true }
if (-not $pgOk) {
    $pgPaths = Get-ChildItem -Path "C:\Program Files\PostgreSQL" -Recurse -Filter "psql.exe" -ErrorAction SilentlyContinue
    if ($pgPaths) { $pgOk = $true }
}
if (-not $pgOk) {
    Write-Host ""
    Write-Host "未检测到 PostgreSQL。请本机安装并创建数据库 mgmt_web，详见参考/PostgreSQL安装与连接说明.md"
}

# ---------- Git 检测（可选）----------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "未检测到 Git，提交代码需安装 Git for Windows。"
}

# ---------- 执行结果检查 ----------
Write-Host ""
Write-Host "========== 执行结果检查 =========="
$checks = @(
    @{ Name = ".venv"; Path = ".venv"; Desc = "Python 虚拟环境（项目内）" },
    @{ Name = "backend 依赖"; Path = ".venv\Scripts\pip.exe"; Desc = "后端 pip" },
    @{ Name = "Node"; Path = "node"; Desc = "node 命令" },
    @{ Name = "frontend 依赖"; Path = "frontend\node_modules"; Desc = "前端 node_modules（项目内）" },
    @{ Name = ".env"; Path = ".env"; Desc = "环境配置" },
    @{ Name = "uploads"; Path = "uploads"; Desc = "上传目录" }
)
foreach ($c in $checks) {
    if ($c.Name -eq "Node") {
        $ok = Get-Command node -ErrorAction SilentlyContinue
    } else {
        $ok = Test-Path $c.Path
    }
    $status = if ($ok) { "OK" } else { "缺失" }
    Write-Host ("  {0}: {1} ({2})" -f $c.Name, $status, $c.Desc)
}
Write-Host "  PostgreSQL: $(if ($pgOk) { '已检测到' } else { '请本机安装' })（无法项目内安装）"
Write-Host "=================================="
Write-Host ""
Write-Host "若上述依赖均为 OK，说明一键安装已执行完毕。请确保 PostgreSQL 已安装并创建数据库，然后："
Write-Host "  1. .\.venv\Scripts\Activate.ps1"
Write-Host "  2. uvicorn backend.main:app --reload"
Write-Host "  3. 新终端启动前端: cd frontend; npm run dev"
Write-Host ""
Write-Host "若新终端仍提示找不到 npm，请先执行以下一行再运行 npm："
Write-Host '  $env:Path = "C:\Program Files\nodejs;" + $env:Path'
Write-Host ""
Read-Host "按 Enter 键关闭此窗口"
