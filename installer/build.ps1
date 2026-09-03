<#
.SYNOPSIS
    Builds the complete obsidian-sync installer: editable install ->
    PyInstaller (daemon + tray) -> Inno Setup.

.DESCRIPTION
    Run from anywhere; paths are resolved relative to this script's location.
    Requires Inno Setup's ISCC.exe to be discoverable -- either on PATH, or
    at one of the common install locations checked below.

.EXAMPLE
    .\installer\build.ps1
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "==> Installing package (editable, with build extras)" -ForegroundColor Cyan
pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "==> Cleaning previous build output" -ForegroundColor Cyan
Remove-Item -Recurse -Force "$RepoRoot\build\pyinstaller" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$RepoRoot\dist" -ErrorAction SilentlyContinue

Write-Host "==> Building obsidian-sync (daemon)" -ForegroundColor Cyan
pyinstaller --noconfirm --distpath "$RepoRoot\dist" --workpath "$RepoRoot\build\pyinstaller" "$PSScriptRoot\obsidian_sync_daemon.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed for the daemon" }

Write-Host "==> Building obsidian-sync-tray" -ForegroundColor Cyan
pyinstaller --noconfirm --distpath "$RepoRoot\dist" --workpath "$RepoRoot\build\pyinstaller" "$PSScriptRoot\obsidian_sync_tray.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed for the tray app" }

Write-Host "==> Locating ISCC.exe" -ForegroundColor Cyan
$iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidates = @(
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    )
    $found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $found) {
        throw "ISCC.exe not found on PATH or in common install locations. Install Inno Setup (https://jrsoftware.org/isinfo.php) and retry, or add it to PATH."
    }
    $iscc = $found
} else {
    $iscc = $iscc.Source
}

Write-Host "==> Compiling installer with $iscc" -ForegroundColor Cyan
& $iscc "$PSScriptRoot\obsidian_sync.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC compile failed" }

Write-Host "==> Done: $RepoRoot\dist-installer\obsidian-sync-setup.exe" -ForegroundColor Green
