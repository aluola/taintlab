$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& .venv/Scripts/python.exe -m pytest -q --junitxml=results/v2/validation/pytest.xml
exit $LASTEXITCODE
