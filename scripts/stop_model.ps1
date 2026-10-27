$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root 'results/environment/model.pid'
if (!(Test-Path -LiteralPath $pidFile)) {Write-Output 'No managed model PID file.'; exit 0}
$serverPid = [int](Get-Content -LiteralPath $pidFile)
$server = (Resolve-Path -LiteralPath (Join-Path $root 'vendor/llama.cpp/llama-server.exe')).Path
$process = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
if ($process -and $process.Path -eq $server) {Stop-Process -Id $serverPid; Write-Output "Stopped managed llama-server PID $serverPid"}
Remove-Item -LiteralPath $pidFile
