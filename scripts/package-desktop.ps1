$ErrorActionPreference = "Stop"
if (-not $IsWindows -and $env:OS -ne "Windows_NT") { throw "Build this preview on Windows." }
$repoRoot = Split-Path $PSScriptRoot -Parent
& "$PSScriptRoot/package-gateway.ps1"
Push-Location "$repoRoot/desktop"
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    npm run tauri build -- --config src-tauri/windows-preview.conf.json
    if ($LASTEXITCODE -ne 0) { throw "Desktop build failed." }
    Write-Host "Unsigned preview installer: desktop/src-tauri/target/release/bundle/nsis"
    Write-Host "Do not distribute as production: submission ACL/handle validation is pending."
} finally { Pop-Location }
