param([int]$Port = 8080, [int]$GpuLayers = 99)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$lock = Get-Content -LiteralPath (Join-Path $root 'configs/model.lock.json') -Raw | ConvertFrom-Json
$server = Join-Path $root $lock.server_file
$model = Join-Path $root $lock.model_file
if (!(Test-Path -LiteralPath $server) -or !(Test-Path -LiteralPath $model)) {throw 'Run python scripts/model_prepare.py first.'}
$server = (Resolve-Path -LiteralPath $server).Path
$model = (Resolve-Path -LiteralPath $model).Path
$logDir = Join-Path $root 'results/environment'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$pidFile = Join-Path $logDir 'model.pid'
if (Test-Path -LiteralPath $pidFile) {
    $oldPid = [int](Get-Content -LiteralPath $pidFile)
    $existing = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
    if ($existing -and $existing.Path -eq $server) {Write-Output "llama-server already running with PID $oldPid"; exit 0}
}
$python = Join-Path $root '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) {throw 'Run scripts/install.ps1 first.'}
$startedPid = & $python (Join-Path $PSScriptRoot 'launch_model.py') --port $Port --gpu-layers $GpuLayers
if ($LASTEXITCODE -ne 0) {throw 'Detached model launch failed.'}
$process = Get-Process -Id ([int]$startedPid)
Write-Output "Started llama-server PID $($process.Id), loopback port $Port. Check python scripts/model_health.py."
for ($i = 0; $i -lt 55; $i++) {
    if ($process.HasExited) {throw "llama-server exited. See results/environment/llama.stderr.log"}
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 1
        if ($health.status -eq 'ok') {Write-Output 'Model is healthy.'; exit 0}
    } catch { }
    Start-Sleep -Milliseconds 500
}
throw 'Model startup health timeout. Inspect results/environment/llama.stderr.log.'
