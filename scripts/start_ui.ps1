param([int]$Port = 8501)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project .venv is missing; run scripts/install.ps1 first.' }
$serverPath = Join-Path $projectRoot 'scripts/serve_app.py'
$frontendEntry = Join-Path $projectRoot 'frontend/dist/index.html'
if (-not (Test-Path -LiteralPath $serverPath)) { throw 'scripts/serve_app.py is missing.' }
if (-not (Test-Path -LiteralPath $frontendEntry)) { throw 'frontend/dist is missing. In frontend run npm ci and npm run build first.' }
& $pythonPath $serverPath --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
