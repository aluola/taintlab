param(
    [string]$Narration = 'demo/narration.json',
    [string]$OutputDirectory = 'demo/voice',
    [double]$Duration = 240,
    [string]$Voice = 'Microsoft Huihui Desktop',
    [ValidateRange(-2,4)][int]$InitialRate = 0
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$culture = [System.Globalization.CultureInfo]::InvariantCulture
function Number([double]$value) { return $value.ToString('0.000000', $culture) }
function Run-Native([string]$program, [string[]]$arguments, [string]$logPath) {
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $text = (& $program @arguments 2>&1 | Out-String)
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $oldPreference }
    [System.IO.File]::WriteAllText($logPath, $text, [System.Text.UTF8Encoding]::new($false))
    if ($code -ne 0) { throw "Native tool failed ($code). Inspect $logPath" }
    return $text
}
function Wav-Duration([string]$path) {
    $text = & $ffprobe -v error -show_entries format=duration -of json $path
    if ($LASTEXITCODE -ne 0) { throw "ffprobe failed for $path" }
    return [double]::Parse(($text | ConvertFrom-Json).format.duration, $culture)
}
$narrationPath = (Resolve-Path -LiteralPath $Narration).Path
$entries = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($narrationPath, [System.Text.Encoding]::UTF8))
if ($entries -isnot [System.Array]) { $entries = @($entries) }
if ($entries.Count -eq 0 -or $entries.Count -gt 80) { throw 'Narration must contain 1 to 80 segments.' }
if ($Duration -le 0 -or $Duration -gt 300) { throw 'Duration must be positive and at most 300 seconds.' }
$previousEnd = 0.0
foreach ($entry in $entries) {
    if ($null -eq $entry.start -or $null -eq $entry.end -or [string]::IsNullOrWhiteSpace($entry.text)) { throw 'Each narration item needs start, end and text.' }
    if ([double]$entry.start -lt $previousEnd -or [double]$entry.end -le [double]$entry.start -or [double]$entry.end -gt $Duration) { throw 'Narration intervals must be non-overlapping, ordered, and inside the full track.' }
    if ($entry.text.Length -gt 2500) { throw 'Narration segment exceeds the bounded text limit.' }
    $previousEnd = [double]$entry.end
}
$ffmpeg = (Resolve-Path -LiteralPath 'vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe').Path
$ffprobe = (Resolve-Path -LiteralPath 'vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe').Path
$outDir = [System.IO.Path]::GetFullPath((Join-Path $root $OutputDirectory))
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $root 'demo/voice'))
if ($outDir -ne $allowedRoot -and !$outDir.StartsWith($allowedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Voice outputs must stay inside demo/voice.' }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$segmentDir = Join-Path $outDir 'segments'
New-Item -ItemType Directory -Force -Path $segmentDir | Out-Null
Add-Type -AssemblyName System.Speech
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$installed = @($synth.GetInstalledVoices() | Where-Object Enabled | ForEach-Object { $_.VoiceInfo.Name })
if ($installed -notcontains $Voice) { throw "Requested offline voice unavailable. Installed: $($installed -join ', ')" }
$synth.SelectVoice($Voice)
$synth.Volume = 100
$format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$segments = @()
try {
    for ($index = 0; $index -lt $entries.Count; $index++) {
        $entry = $entries[$index]
        $slot = [double]$entry.end - [double]$entry.start
        $speechBudget = $slot - [Math]::Min(0.30, $slot * 0.05)
        if ($speechBudget -lt 0.5) { throw "Narration segment $index is too short." }
        $stem = 'segment_{0:D3}' -f $index
        $rawPath = Join-Path $segmentDir ($stem + '_raw.wav')
        $fittedPath = Join-Path $segmentDir ($stem + '.wav')
        $attempts = @()
        $rate = $InitialRate
        while ($true) {
            $synth.Rate = $rate
            $synth.SetOutputToWaveFile($rawPath, $format)
            $synth.Speak([string]$entry.text)
            $synth.SetOutputToNull()
            $rawDuration = Wav-Duration $rawPath
            $attempts += [ordered]@{ rate = $rate; raw_duration_seconds = $rawDuration }
            if ($rawDuration -le $speechBudget * 1.18) { break }
            if ($rate -ge 4) { throw "Narration segment $index cannot fit naturally. Shorten text or extend its interval; no speech was truncated." }
            $rate++
        }
        # Only a small tempo correction; shorter phrases retain natural pacing and a pause.
        $tempo = if ($rawDuration -gt $speechBudget) { $rawDuration / $speechBudget } else { 1.0 }
        if ($tempo -gt 1.180001) { throw 'Tempo correction exceeded the documented bound.' }
        $filter = 'atempo=' + (Number $tempo) + ',apad,atrim=duration=' + (Number $slot) + ',asetpts=PTS-STARTPTS'
        [void](Run-Native $ffmpeg @('-hide_banner','-y','-i',$rawPath,'-af',$filter,'-ar','24000','-ac','1','-c:a','pcm_s16le',$fittedPath) (Join-Path $segmentDir ($stem + '_ffmpeg.log')))
        $fittedDuration = Wav-Duration $fittedPath
        if ([Math]::Abs($fittedDuration - $slot) -gt 0.03) { throw "Segment $index timing verification failed." }
        $segments += [ordered]@{
            index = $index; start = [double]$entry.start; end = [double]$entry.end; text = [string]$entry.text
            synthesis_attempts = $attempts; selected_rate = $rate; atempo = $tempo
            raw_duration_seconds = $rawDuration; fitted_duration_seconds = $fittedDuration
            speech_duration_after_tempo = $rawDuration / $tempo
            raw_file = 'segments/' + $stem + '_raw.wav'; file = 'segments/' + $stem + '.wav'
            sha256 = (Get-FileHash -LiteralPath $fittedPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        Write-Output "Voice segment $index complete: rate=$rate tempo=$(Number $tempo), slot=$(Number $slot)s"
    }
} finally { $synth.Dispose() }

$ffArgs = @('-hide_banner','-y','-f','lavfi','-t',(Number $Duration),'-i','anullsrc=r=24000:cl=mono')
$filterParts = @()
$mixInputs = '[0:a]'
for ($i = 0; $i -lt $segments.Count; $i++) {
    $ffArgs += @('-i', (Join-Path $outDir $segments[$i].file))
    $inputIndex = $i + 1
    $delay = [long][Math]::Round([double]$segments[$i].start * 1000)
    $filterParts += "[$inputIndex`:a]adelay=$delay`:all=1[seg$i]"
    $mixInputs += "[seg$i]"
}
$filterParts += $mixInputs + 'amix=inputs=' + ($segments.Count + 1) + ':duration=first:dropout_transition=0:normalize=0,atrim=duration=' + (Number $Duration) + ',asetpts=PTS-STARTPTS[mix]'
$filterFile = Join-Path $outDir 'mix_filter.txt'
[System.IO.File]::WriteAllText($filterFile, ($filterParts -join ';'), [System.Text.Encoding]::ASCII)
$voicePath = Join-Path $outDir 'voice.wav'
$ffArgs += @('-filter_complex',($filterParts -join ';'),'-map','[mix]','-ar','24000','-ac','1','-c:a','pcm_s16le',$voicePath)
[void](Run-Native $ffmpeg $ffArgs (Join-Path $outDir 'mix_ffmpeg.log'))
$actualDuration = Wav-Duration $voicePath
if ([Math]::Abs($actualDuration - $Duration) -gt 0.03) { throw 'Full voice track timing verification failed.' }
$manifest = [ordered]@{
    created_at_utc = [DateTime]::UtcNow.ToString('o'); backend_type = 'windows_system_speech_offline'
    voice = $Voice; requested_duration_seconds = $Duration; actual_duration_seconds = $actualDuration
    sample_rate = 24000; channels = 1; codec = 'pcm_s16le'; atempo_range = @(1.0,1.18)
    narration_source = $narrationPath; narration_sha256 = (Get-FileHash -LiteralPath $narrationPath -Algorithm SHA256).Hash.ToLowerInvariant()
    voice_sha256 = (Get-FileHash -LiteralPath $voicePath -Algorithm SHA256).Hash.ToLowerInvariant()
    network_required = $false; segments = $segments
    limits = 'System.Speech installed desktop voice; local synthesis and FFmpeg only. Tempo changes and padding are recorded; speech is never intentionally truncated.'
}
[System.IO.File]::WriteAllText((Join-Path $outDir 'voice_manifest.json'), ($manifest | ConvertTo-Json -Depth 12), [System.Text.UTF8Encoding]::new($false))
Write-Output "Offline voice track saved: $voicePath ($actualDuration seconds)"
