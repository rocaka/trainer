$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'This smoke test requires Windows.' }
$repository = Split-Path -Parent $PSScriptRoot
$installers = @(Get-ChildItem "$repository/desktop/src-tauri/target/release/bundle/nsis/*.exe")
if ($installers.Count -ne 1) { throw 'Expected exactly one test installer.' }
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('trainer-install-' + [guid]::NewGuid())
$installRoot = Join-Path $testRoot 'Trainer Preview'
New-Item -ItemType Directory -Path $testRoot | Out-Null
$previousAppData = $env:LOCALAPPDATA
$desktopProcess = $null
try {
    $env:LOCALAPPDATA = Join-Path $testRoot 'AppData'
    New-Item -ItemType Directory -Path $env:LOCALAPPDATA | Out-Null
    # NSIS requires /D to be last and not quoted, including paths with spaces.
    $installerProcess = Start-Process -FilePath $installers[0].FullName -ArgumentList "/S /D=$installRoot" -PassThru
    if (-not $installerProcess.WaitForExit(120000) -or $installerProcess.ExitCode -ne 0) {
        throw 'Silent installation failed.'
    }
    $desktop = Join-Path $installRoot 'trainer-desktop.exe'
    if (-not (Test-Path $desktop)) { throw 'Installed desktop executable missing.' }
    if (-not (Test-Path (Join-Path $installRoot 'gateway/trainer-gateway.exe'))) {
        throw 'Bundled backend resource missing.'
    }
    $desktopProcess = Start-Process -FilePath $desktop -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($desktopProcess.HasExited) { throw 'Installed desktop exited before readiness.' }
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:18787/health' -TimeoutSec 2 -NoProxy
            if ($health.ok -and -not $health.submissionReady) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Installed application backend did not become ready.' }
    $windowReady = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $desktopProcess.Refresh()
        if ($desktopProcess.MainWindowHandle -ne 0) { $windowReady = $true; break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $windowReady) { throw 'Desktop window was not created.' }
    if (-not $desktopProcess.CloseMainWindow()) { throw 'Could not close own desktop window.' }
    if (-not $desktopProcess.WaitForExit(20000)) { throw 'Desktop did not exit after window close.' }
    $stopped = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try { Invoke-RestMethod 'http://127.0.0.1:18787/health' -TimeoutSec 1 -NoProxy | Out-Null }
        catch { $stopped = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $stopped) { throw 'Owned backend remained after closing the desktop.' }
    Write-Output 'PASS: silent installation, bundled backend, desktop window, health, normal close and backend cleanup.'
} finally {
    if ($desktopProcess -and -not $desktopProcess.HasExited) { $desktopProcess.Kill(); $desktopProcess.WaitForExit() }
    $env:LOCALAPPDATA = $previousAppData
    # Disposable runner owns installation and registry changes. No user data is deleted.
}
