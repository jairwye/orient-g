# Install pgvector prebuilt binaries for PostgreSQL 18 on Windows
# Run from repo root (may need Administrator if PG dir is protected):
#   powershell -ExecutionPolicy Bypass -File .\scripts\install-pgvector-windows.ps1

$ErrorActionPreference = "Stop"
$PgRoot = $env:PGROOT
if (-not $PgRoot) {
    if (Test-Path "D:\Programs\PostgreSQL\18") { $PgRoot = "D:\Programs\PostgreSQL\18" }
    elseif (Test-Path "C:\Program Files\PostgreSQL\18") { $PgRoot = "C:\Program Files\PostgreSQL\18" }
}
if (-not $PgRoot -or -not (Test-Path $PgRoot)) {
    Write-Host "Set PGROOT to your PostgreSQL 18 install dir, e.g. D:\Programs\PostgreSQL\18" -ForegroundColor Red
    exit 1
}
Write-Host "PGROOT=$PgRoot"

$zipUrl = "https://github.com/andreiramani/pgvector_pgsql_windows/releases/download/0.8.2_18.0.2/vector.v0.8.2-pg18.zip"
$zip = Join-Path $env:TEMP "vector.v0.8.2-pg18.zip"
$extract = Join-Path $env:TEMP "vector-pg18-extract"

Write-Host "Downloading pgvector ..." -ForegroundColor Cyan
curl.exe -sL -o $zip $zipUrl
if (-not (Test-Path $zip)) { throw "Download failed" }

if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $extract -Force

function Copy-Merge($src, $dst) {
    if (-not (Test-Path $src)) { return }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Copy-Item -Path (Join-Path $src "*") -Destination $dst -Recurse -Force
}

Write-Host "Installing into $PgRoot ..." -ForegroundColor Cyan
Copy-Merge (Join-Path $extract "lib") (Join-Path $PgRoot "lib")
Copy-Merge (Join-Path $extract "share\extension") (Join-Path $PgRoot "share\extension")
Copy-Merge (Join-Path $extract "include\server\extension\vector") (Join-Path $PgRoot "include\server\extension\vector")

if (-not (Test-Path (Join-Path $PgRoot "lib\vector.dll"))) {
    throw "vector.dll not found after copy - run as Administrator?"
}

$svc = Get-Service -Name "postgresql-x64-18" -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "Restarting PostgreSQL service ..." -ForegroundColor Cyan
    Restart-Service "postgresql-x64-18"
    Start-Sleep -Seconds 2
}

$Root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $py) {
    Write-Host "Running init_kb_vector_local.py ..." -ForegroundColor Cyan
    & $py (Join-Path $Root "scripts\init_kb_vector_local.py")
    exit $LASTEXITCODE
}

Write-Host "Done. Run: .\.venv\Scripts\python.exe scripts\init_kb_vector_local.py" -ForegroundColor Green
exit 0
