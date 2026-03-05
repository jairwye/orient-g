# 启动前端（若 Node 在项目内 .node，会先加入 PATH）
# 在项目根目录执行: .\scripts\run-frontend.ps1

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$nodeDirs = Get-ChildItem -Path (Join-Path $root ".node") -Directory -ErrorAction SilentlyContinue
foreach ($d in $nodeDirs) {
    if (Test-Path (Join-Path $d.FullName "node.exe")) {
        $env:Path = "$($d.FullName);$env:Path"
        break
    }
}

Set-Location (Join-Path $root "frontend")
npm run dev
