$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$result = [ordered]@{
    captured_at = (Get-Date -Format o)
    os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,TotalVisibleMemorySize,FreePhysicalMemory
    cpu = Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
    gpu = Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM
    disk = Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free
    commands = Get-Command python,py,uv,git,ffmpeg,ffprobe,node,pandoc,soffice -ErrorAction SilentlyContinue | Select-Object Name,Source
    nvidia = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1 | Out-String).Trim()
}
New-Item -ItemType Directory -Force -Path (Join-Path $root 'results/environment') | Out-Null
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $root 'results/environment/hardware.json') -Encoding utf8
$result | ConvertTo-Json -Depth 5
