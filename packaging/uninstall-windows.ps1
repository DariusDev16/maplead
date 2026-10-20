<#
.SYNOPSIS
    Remove MAPLEAD from this Windows account.

.DESCRIPTION
    Deletes the Start Menu shortcut, the user-PATH entry and the Apps & features
    registration, then removes the program folder. Lead exports and saved API
    keys are left untouched.

        powershell -ExecutionPolicy Bypass -File .\uninstall.ps1

.PARAMETER InstallDir
    Folder to remove. Defaults to the folder this script is in.

.PARAMETER Force
    Do not ask for confirmation.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot is not available inside param() defaults on Windows PowerShell 5.1
if (-not $InstallDir) { $InstallDir = $PSScriptRoot }
if (-not $InstallDir) { throw "pass -InstallDir <folder> (the script could not locate itself)." }

$installFull = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')

if (-not $Force) {
    Write-Host "This removes MAPLEAD from:"
    Write-Host "    $installFull"
    Write-Host "Lead exports and saved API keys are kept."
    $answer = Read-Host "Continue? [y/N]"
    if ($answer -notmatch '^(y|yes|s|sim)$') {
        Write-Host "cancelled"
        exit 1
    }
}

Write-Host ""
Write-Host "==> stopping MAPLEAD" -ForegroundColor Cyan
Get-Process -Name "MAPLEAD", "maplead-cli" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "==> removing shortcuts" -ForegroundColor Cyan
$startMenu = [Environment]::GetFolderPath("Programs")
foreach ($link in @(
        (Join-Path $startMenu "MAPLEAD.lnk"),
        (Join-Path ([Environment]::GetFolderPath("Desktop")) "MAPLEAD.lnk"))) {
    if (Test-Path -LiteralPath $link) {
        Remove-Item -LiteralPath $link -Force
        Write-Host "    $link"
    }
}

Write-Host "==> removing the PATH entry" -ForegroundColor Cyan
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $parts = @($userPath -split ";" | Where-Object { $_ -ne "" -and $_ -ine $installFull })
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ";"), "User")
}

Write-Host "==> removing the Apps & features entry" -ForegroundColor Cyan
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MAPLEAD"
if (Test-Path $uninstallKey) {
    Remove-Item -Path $uninstallKey -Recurse -Force
}

Write-Host "==> deleting $installFull" -ForegroundColor Cyan
Set-Location -Path $env:TEMP
Start-Sleep -Milliseconds 300
try {
    Remove-Item -LiteralPath $installFull -Recurse -Force
}
catch {
    # a still-mapped .exe or an open Explorer window can hold the folder
    & cmd.exe /c "rmdir /s /q `"$installFull`"" 2>$null
}

Write-Host ""
Write-Host "MAPLEAD removed." -ForegroundColor Green
Write-Host "Exports in $([Environment]::GetFolderPath('MyDocuments'))\maplead and keys in $env:APPDATA\maplead were kept."
