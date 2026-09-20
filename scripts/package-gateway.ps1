$ErrorActionPreference = "Stop"
if (-not $IsWindows -and $env:OS -ne "Windows_NT") {
    throw "This script must run on Windows."
}
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    # Build dependency only. End users will not need Python installed.
    python -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) { throw "Install scripts/requirements-build.txt in an isolated build environment first." }
    python -m PyInstaller --distpath dist/windows-gateway --workpath dist/windows-gateway-build scripts/gateway-bundle.spec
    if ($LASTEXITCODE -ne 0) { throw "Gateway packaging failed." }
    Write-Host "Created backend folder: dist/windows-gateway/trainer-gateway"
    Write-Host "Preview only: Windows secure submission is disabled pending ACL/handle validation."
} finally {
    Pop-Location
}
