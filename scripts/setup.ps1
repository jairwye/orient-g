# Orient-G - PowerShell script encoding: UTF-8 with BOM
# Orient-G（财务信息内网）- 本地一键安装（Windows PowerShell）
# Orient-G project root install script
# Orient-G projekt mappa: egy kattintassal telepito PowerShell

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Refresh-EnvPath {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host "Project root: $root"
Write-Host "Setup will configure: Python venv, backend deps, Node.js (global), frontend deps, .env, uploads"
Write-Host ""

# ---------- 1. Python venv (project-local .venv) ----------
$pythonOk = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonOk) {
    Write-Host "[1/6] Python not found, installing via winget..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        Refresh-EnvPath
        $pythonOk = Get-Command python -ErrorAction SilentlyContinue
    }
    if (-not $pythonOk) {
        Write-Host "  -> Python still not found after install. Please restart this window or install manually from python.org."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "  -> Python ready (global), creating project-local .venv."
}
if (-not (Test-Path ".venv")) {
    Write-Host "[1/6] Creating Python .venv..."
    python -m venv .venv
    Write-Host "  -> Done"
} else {
    Write-Host "[1/6] .venv already exists, skipping."
}
Write-Host "[2/6] Installing backend deps..."
Write-Host "  -> Note: Docling 2.x (torch/transformers) may take 10-60+ minutes on first install, do not interrupt."
& .\.venv\Scripts\pip.exe install -r backend\requirements.txt --quiet
Write-Host "  -> pip install complete"
$pipShow = & .\.venv\Scripts\pip.exe show docling 2>$null
if ($LASTEXITCODE -eq 0 -and $pipShow -and ($pipShow -match '(?m)^Version:\s*(.+)$')) {
    Write-Host "  -> Docling version: $($Matches[1])"
} elseif ($LASTEXITCODE -eq 0 -and $pipShow) {
    Write-Host "  -> Docling installed (version parse skipped)"
} else {
    Write-Host "  -> Warning: docling package not detected. Run: .\.venv\Scripts\pip.exe install -r backend\requirements.txt"
}
if (Test-Path .\.venv\Scripts\docling.exe) {
    Write-Host "  -> Docling CLI: .venv\Scripts\docling.exe exists"
}
Write-Host "  -> Done"


# ---------- 2. Node.js (global install, not project-local) ----------
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
    Write-Host "[3/6] Using existing project-local Node.js (.node) ..."
} elseif (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "[3/6] Using system Node.js (global)..."
} else {
    Write-Host "[3/6] Node.js not found, installing via winget..."
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
        Write-Host "  -> Node.js still not found. Please restart this window or install from nodejs.org."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "  -> Node.js installed via winget (global)"
}

# ---------- 3. Frontend deps (project-local frontend/node_modules) ----------
Write-Host "[4/6] Installing frontend deps..."
Set-Location frontend
& npm install --no-audit --no-fund
if ($LASTEXITCODE -eq 0) {
    Write-Host "  -> npm install done, running audit fix..."
    & npm audit fix
    if ($LASTEXITCODE -ne 0) { Write-Host "  -> audit fix has unresolved items, run npm audit later." }
}
Set-Location $root
Write-Host "  -> Done"

# ---------- 4. .env ----------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[5/6] Copied .env.example -> .env (edit .env to configure DB connection)"
} else {
    Write-Host "[5/6] .env already exists, not overwritten."
}

# ---------- 5. uploads directory ----------
if (-not (Test-Path "uploads")) {
    New-Item -ItemType Directory -Path "uploads" | Out-Null
    Write-Host "[6/6] Created uploads directory."
} else {
    Write-Host "[6/6] uploads directory already exists."
}

# ---------- PostgreSQL check (hint only) ----------
$pgOk = $false
if (Get-Command psql -ErrorAction SilentlyContinue) { $pgOk = $true }
if (-not $pgOk) {
    $pgPaths = Get-ChildItem -Path "C:\Program Files\PostgreSQL" -Recurse -Filter "psql.exe" -ErrorAction SilentlyContinue
    if ($pgPaths) { $pgOk = $true }
}
if (-not $pgOk) {
    Write-Host ""
    Write-Host "PostgreSQL not detected. Please install PostgreSQL locally and create database mgmt_web."
    Write-Host "See docs/汇率-PostgreSQL排查.md for DB connection troubleshooting."
}

# ---------- Git check (optional) ----------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git not detected, code commits require Git for Windows."
}

# ---------- Execution summary ----------
Write-Host ""
Write-Host "========== Execution Summary =========="
$checks = @(
    @{ Name = ".venv"; Path = ".venv"; Desc = "Python venv" },
    @{ Name = "backend deps"; Path = ".venv\Scripts\pip.exe"; Desc = "backend pip" },
    @{ Name = "Node"; Path = "node"; Desc = "node command" },
    @{ Name = "frontend deps"; Path = "frontend\node_modules"; Desc = "frontend node_modules" },
    @{ Name = ".env"; Path = ".env"; Desc = "environment config" },
    @{ Name = "uploads"; Path = "uploads"; Desc = "upload directory" }
)
foreach ($c in $checks) {
    if ($c.Name -eq "Node") {
        $ok = Get-Command node -ErrorAction SilentlyContinue
    } else {
        $ok = Test-Path $c.Path
    }
    $status = if ($ok) { "OK" } else { "MISSING" }
    Write-Host ("  {0}: {1} ({2})" -f $c.Name, $status, $c.Desc)
}
Write-Host "  PostgreSQL: $(if ($pgOk) { 'detected' } else { 'not installed - please install' })"
Write-Host "=================================="
Write-Host ""
Write-Host "If all deps are OK, PostgreSQL is running, and DB mgmt_web exists:"
Write-Host "  1. .\.venv\Scripts\Activate.ps1"
Write-Host "  2. uvicorn backend.main:app --reload"
Write-Host "  3. New terminal, start frontend: cd frontend; npm run dev"
Write-Host ""
Write-Host "If npm not found after install, run this first:"
Write-Host '  $env:Path = "C:\Program Files\nodejs;" + $env:Path'
Write-Host ""
Read-Host "Press Enter to close this window"
