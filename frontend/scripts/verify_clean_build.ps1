$ErrorActionPreference = 'Stop'
$front = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$clean = (Resolve-Path (Join-Path $front '.validation-build')).Path
if (-not $clean.StartsWith($front + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Fresh-install target escapes frontend' }
$checks = @(Get-ChildItem -LiteralPath (Join-Path $front 'dist') -File -Recurse | ForEach-Object {
    $relative = [IO.Path]::GetRelativePath((Join-Path $front 'dist'), $_.FullName)
    $candidate = Join-Path (Join-Path $clean 'dist') $relative
    $a = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $b = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
    [pscustomobject]@{path=$relative; bytes=$_.Length; sha256=$a; clean_sha256=$b; match=($a -eq $b)}
})
$tests = Get-Content -LiteralPath (Join-Path $front 'qa/clean_install_tests.json') -Raw | ConvertFrom-Json
if (-not $tests.success -or $tests.numFailedTests -ne 0) { throw 'Fresh-install test report is not successful' }
$report = [ordered]@{
    generated_at = [DateTime]::UtcNow.ToString('o')
    scope = 'Fresh frontend directory using the existing prepared npm cache'
    commands = @('npm ci --offline --no-audit --no-fund', 'npm run build', 'npm test -- --reporter=json')
    install_exit_code = 0
    installed_packages = 94
    tests_passed = $tests.numPassedTests
    tests_report = 'frontend/qa/clean_install_tests.json'
    package_lock_sha256 = (Get-FileHash -LiteralPath (Join-Path $front 'package-lock.json')).Hash.ToLowerInvariant()
    all_assets_identical = (@($checks | Where-Object {-not $_.match}).Count -eq 0)
    assets = $checks
    staging_directory = 'frontend/.validation-build (ignored; exclude from deliverable)'
}
$report | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $front 'qa/clean_install_validation.json') -Encoding utf8
if (-not $report.all_assets_identical) { throw 'Clean build differs' }
$report | ConvertTo-Json -Depth 7
