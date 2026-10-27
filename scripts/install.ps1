param([string]$Venv='.venv')
$ErrorActionPreference='Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if ([string]::IsNullOrWhiteSpace($Venv)) {throw 'Venv path must not be empty'}
$venvPath = if ([IO.Path]::IsPathRooted($Venv)) {
    [IO.Path]::GetFullPath($Venv)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $Venv))
}
$venvPython = Join-Path $venvPath 'Scripts/python.exe'
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue

function Test-Python312([string]$Executable, [string[]]$PrefixArguments=@(), [switch]$VirtualEnvironment) {
    # Do not accept a 32-bit interpreter or silently use a different minor version.
    $code = "import struct,sys; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8"
    if ($VirtualEnvironment) {$code += '; assert sys.prefix != sys.base_prefix'}
    try {
        & $Executable @PrefixArguments -c $code 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {return $false}
}

if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    if (-not (Test-Path -LiteralPath (Join-Path $venvPath 'pyvenv.cfg') -PathType Leaf) -or
        -not (Test-Python312 $venvPython -VirtualEnvironment)) {
        throw 'Existing environment is not a usable Python 3.12 x64 venv. Select a new -Venv path; no existing files were removed.'
    }
    Write-Host "Reusing verified Python 3.12 x64 environment: $venvPath"
} else {
    if (Test-Path -LiteralPath $venvPath) {
        # Reject arbitrary/partial directories rather than clearing user files.
        throw 'Environment target already exists but has no usable Python. Select a new -Venv path; no existing files were removed.'
    }
    if ($uvCommand) {
        & $uvCommand venv --python '3.12' $venvPath
    } else {
        $pyCommand = Get-Command py -ErrorAction SilentlyContinue
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pyCommand -and (Test-Python312 $pyCommand.Name @('-3.12'))) {
            & $pyCommand -3.12 -m venv $venvPath
        } elseif ($pythonCommand -and (Test-Python312 $pythonCommand.Name)) {
            & $pythonCommand -m venv $venvPath
        } else {
            throw 'Python 3.12 x64 was not found. Install uv, or Python 3.12 x64 with the Windows py launcher or python on PATH, then rerun this script.'
        }
    }
    if ($LASTEXITCODE -ne 0) {throw 'Virtual environment creation failed'}
    if (-not (Test-Python312 $venvPython -VirtualEnvironment)) {
        throw 'Created environment is not Python 3.12 x64. Installation stopped without removing files.'
    }
}

if ($uvCommand) {
    & $uvCommand pip install --python $venvPython -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) {throw 'Locked dependency installation failed'}
    & $uvCommand pip install --python $venvPython --no-deps --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) {throw 'Project installation failed'}
    & $uvCommand pip check --python $venvPython
} else {
    # A previously uv-created environment may not have pip yet. ensurepip is local.
    & $venvPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) {throw 'Local pip preparation failed'}
    & $venvPython -m pip install -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) {throw 'Locked dependency installation failed'}
    & $venvPython -m pip install --no-deps --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) {throw 'Project installation failed'}
    & $venvPython -m pip check
}
if ($LASTEXITCODE -ne 0) {throw 'Installed dependency consistency check failed'}
Write-Host "Installation complete: $venvPython"
Write-Host 'Next: .venv\Scripts\python.exe scripts/model_prepare.py'
Write-Host 'Daily CMD launchers use the default .venv directory.'
