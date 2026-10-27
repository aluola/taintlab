param([ValidateSet('baseline','external','both')][string]$Campaign='both',[switch]$Ablation,[int]$Workers=4)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if ($Workers -ne 4) { throw 'Version 2.0 freezes four workers. Use a separately versioned campaign to change this.' }
if ($Ablation) { Write-Output 'Version 2.0 runs policy_only alongside the three main modes with paired scenarios; all four modes are resumed together.' }
& .venv/Scripts/python.exe scripts/run_v2_experiments.py --campaign $Campaign
exit $LASTEXITCODE
