param([switch]$Child, [string]$TakeDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$consoleTitle = 'TaintLab F06 - Synthetic detector self-check'
if ($Child) {
    $Host.UI.RawUI.WindowTitle = $consoleTitle
    $Host.UI.RawUI.BackgroundColor = 'Black'
    $Host.UI.RawUI.ForegroundColor = 'White'
    try {
        $taskBuffer = $Host.UI.RawUI.BufferSize
        $taskBuffer.Width = 145; $taskBuffer.Height = 300
        $Host.UI.RawUI.BufferSize = $taskBuffer
        $taskWindow = $Host.UI.RawUI.WindowSize
        $taskWindow.Width = [Math]::Min(145, $Host.UI.RawUI.MaxWindowSize.Width)
        $taskWindow.Height = [Math]::Min(40, $Host.UI.RawUI.MaxWindowSize.Height)
        $Host.UI.RawUI.WindowSize = $taskWindow
    } catch { }
    Clear-Host
    Write-Host 'F06 | Detector mechanism self-check | Synthetic inputs | NOT model experiments' -ForegroundColor Cyan
    Write-Host 'Actual command output will be shown in pages; presentation pauses are not inference timing.'
    Write-Host 'Command: .venv/Scripts/python.exe scripts/demo_canary_selfcheck.py --output <new evidence file>'
    $waitDeadline = [DateTime]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath (Join-Path $TakeDirectory 'start.signal'))) { if ([DateTime]::UtcNow -gt $waitDeadline) { exit 2 }; Start-Sleep -Milliseconds 100 }
    $evidenceFile = 'results/core_features/canary/demo_selfcheck_' + (Split-Path -Leaf $TakeDirectory) + '.json'
    if (Test-Path -LiteralPath $evidenceFile) { throw 'This evidence file already exists; choose a fresh evidence destination before re-recording.' }
    $actualLines = @(& .venv/Scripts/python.exe scripts/demo_canary_selfcheck.py --output $evidenceFile)
    $actualExit = $LASTEXITCODE
    [System.IO.File]::WriteAllLines((Join-Path $TakeDirectory 'actual_stdout.txt'), $actualLines, [System.Text.UTF8Encoding]::new($false))
    if ($actualExit -ne 0) { throw "Actual self-check failed: $actualExit" }
    $groups = @(
        @{Name='Positive and negative'; Start=0; Count=11},
        @{Name='Encoding and segmented observations'; Start=15; Count=12},
        @{Name='Coverage boundary and conclusion'; Start=27; Count=12}
    )
    $timing = @()
    foreach ($group in $groups) {
        Clear-Host
        Write-Host 'F06 | Detector mechanism self-check | Synthetic inputs | NOT model experiments' -ForegroundColor Cyan
        Write-Host ('Actual command: .venv/Scripts/python.exe scripts/demo_canary_selfcheck.py --output ' + $evidenceFile)
        Write-Host ('Actual stdout excerpt: ' + $group.Name) -ForegroundColor Yellow
        Write-Host ('-' * 100)
        $end = [Math]::Min($actualLines.Count - 1, $group.Start + $group.Count - 1)
        for ($line = $group.Start; $line -le $end; $line++) { Write-Host $actualLines[$line] }
        Write-Host ('-' * 100)
        Write-Host 'Synthetic mechanism validation only. This is not evidence of model exfiltration or ASR.' -ForegroundColor Cyan
        $timing += [ordered]@{group=$group.Name;displayed_at_utc=[DateTime]::UtcNow.ToString('o');stdout_start=$group.Start;stdout_end=$end}
        Start-Sleep -Seconds 12
    }
    [System.IO.File]::WriteAllText((Join-Path $TakeDirectory 'console_pages.json'), ($timing | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText((Join-Path $TakeDirectory 'command_exit.json'), (@{actual_cli_exit_code=$actualExit;completed_pages=$groups.Count;actual_output_file=$evidenceFile;finished_at_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
    Start-Sleep -Seconds 5
    exit 0
}
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$takePath = Join-Path $projectRoot ('demo/core_features/raw/console_' + $stamp)
New-Item -ItemType Directory -Path $takePath | Out-Null
$quotedScript = $PSCommandPath.Replace("'", "''")
$quotedTake = $takePath.Replace("'", "''")
$command = "& '$quotedScript' -Child -TakeDirectory '$quotedTake'"
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$shellPath = (Get-Command powershell.exe).Source
# The user explicitly requested an actual visible command-output demonstration.
# Commands run through the shell; no terminal input or UI automation is used.
$consoleHost = Join-Path $env:SystemRoot 'System32/conhost.exe'
$childProcess = Start-Process -FilePath $consoleHost -ArgumentList @($shellPath,'-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',$encoded) -WindowStyle Normal -PassThru
$ffmpeg = Join-Path $projectRoot 'vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe'
Start-Sleep -Seconds 3
$capture = Start-Process -FilePath $ffmpeg -ArgumentList @('-hide_banner','-y','-f','gdigrab','-framerate','25','-i',('title="' + $consoleTitle + '"'),'-t','39','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p',('"' + (Join-Path $takePath 'console.mp4') + '"')) -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $takePath 'ffmpeg.log') -RedirectStandardOutput (Join-Path $takePath 'ffmpeg.stdout.log')
Start-Sleep -Seconds 2
if ($capture.HasExited) { throw ('FFmpeg window capture failed; inspect ' + (Join-Path $takePath 'ffmpeg.log')) }
[System.IO.File]::WriteAllText((Join-Path $takePath 'start.signal'), [DateTime]::UtcNow.ToString('o'), [System.Text.Encoding]::ASCII)
$capture.WaitForExit()
$childProcess.WaitForExit()
$commandResult = Get-Content -LiteralPath (Join-Path $takePath 'command_exit.json') -Raw | ConvertFrom-Json
if ($commandResult.actual_cli_exit_code -ne 0 -or $commandResult.completed_pages -ne 3) { throw 'Actual detector command did not finish all output pages.' }
$ffprobe = Join-Path $projectRoot 'vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe'
$media = & $ffprobe -v error -show_entries format=duration -of json (Join-Path $takePath 'console.mp4') | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or [double]$media.format.duration -lt 38) { throw 'Recorded media is invalid or too short.' }
$items = @()
foreach ($file in @('console.mp4','actual_stdout.txt','console_pages.json','command_exit.json')) {
    $full = Join-Path $takePath $file
    $items += [ordered]@{path=$full.Substring($projectRoot.Length + 1).Replace('\','/');sha256=(Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant();bytes=(Get-Item -LiteralPath $full).Length}
}
$manifest = [ordered]@{project_version='2.0.0';runtime_version='2.0.0';release_version='2.0.1';created_at_utc=[DateTime]::UtcNow.ToString('o');kind='actual_console_recording';title=$consoleTitle;command=('.venv/Scripts/python.exe scripts/demo_canary_selfcheck.py --output results/core_features/canary/demo_selfcheck_' + (Split-Path -Leaf $takePath) + '.json');source_files=$items;boundaries='Actual PowerShell output pages, not reconstructed UI. All detector inputs synthetic. No model request, business action or formal metric changes. Presentation pauses are not runtime performance.'}
[System.IO.File]::WriteAllText((Join-Path $takePath 'capture_manifest.json'), ($manifest | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
Write-Output ($manifest | ConvertTo-Json -Depth 8)
