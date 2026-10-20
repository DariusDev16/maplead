<#
.SYNOPSIS
    Install (or upgrade) MAPLEAD on Windows.

.DESCRIPTION
    Copies this portable folder into %LOCALAPPDATA%\Programs\MAPLEAD, adds a
    Start Menu shortcut, makes `maplead` available in new terminals and registers
    the app in "Apps & features" so it can be uninstalled again.

    Run it from the unpacked ZIP:

        powershell -ExecutionPolicy Bypass -File .\install.ps1

.PARAMETER Source
    Folder that holds MAPLEAD.exe. Defaults to the folder this script is in.

.PARAMETER InstallDir
    Destination. Defaults to %LOCALAPPDATA%\Programs\MAPLEAD.

.PARAMETER NoPath
    Do not touch the user PATH (the Start Menu shortcut still works).

.PARAMETER DesktopShortcut
    Also put an icon on the desktop.
#>
[CmdletBinding()]
param(
    [string]$Source = "",
    [string]$InstallDir = "",
    [switch]$NoPath,
    [switch]$DesktopShortcut
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

# $PSScriptRoot is not available inside param() defaults on Windows PowerShell 5.1
if (-not $Source) { $Source = $PSScriptRoot }
if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\MAPLEAD" }
if (-not $Source) { throw "run this script from the unpacked ZIP, or pass -Source <folder>." }

$exe = Join-Path $Source "MAPLEAD.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "MAPLEAD.exe not found in '$Source'. Run this script from the unpacked ZIP."
}

$sourceFull = (Resolve-Path -LiteralPath $Source).Path.TrimEnd('\')
$installFull = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$sameFolder = $sourceFull -ieq $installFull

# --------------------------------------------------------------------------- #
Write-Step "copying the app to $installFull"
# --------------------------------------------------------------------------- #
if (-not $sameFolder) {
    $running = Get-Process -Name "MAPLEAD" -ErrorAction SilentlyContinue
    if ($running) {
        throw "MAPLEAD is running - close it and run the installer again."
    }
    New-Item -ItemType Directory -Force -Path $installFull | Out-Null
    Copy-Item -Path (Join-Path $sourceFull "*") -Destination $installFull -Recurse -Force
}
$exe = Join-Path $installFull "MAPLEAD.exe"

# a `maplead` command for cmd/PowerShell users
$cmdShim = Join-Path $installFull "maplead.cmd"
@'
@echo off
"%~dp0maplead-cli.exe" %*
'@ | Set-Content -LiteralPath $cmdShim -Encoding ASCII

# --------------------------------------------------------------------------- #
Write-Step "Start Menu shortcut"
# --------------------------------------------------------------------------- #
$shell = New-Object -ComObject WScript.Shell
$startMenu = [Environment]::GetFolderPath("Programs")
$shortcutPath = Join-Path $startMenu "MAPLEAD.lnk"
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $installFull
$shortcut.IconLocation = "$exe,0"
$shortcut.Description = "MAPLEAD - Google Maps lead extractor"
$shortcut.Save()
Write-Host "    $shortcutPath"

if ($DesktopShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $desktopLink = Join-Path $desktop "MAPLEAD.lnk"
    $shortcut = $shell.CreateShortcut($desktopLink)
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = $installFull
    $shortcut.IconLocation = "$exe,0"
    $shortcut.Save()
    Write-Host "    $desktopLink"
}

# --------------------------------------------------------------------------- #
Write-Step "PATH"
# --------------------------------------------------------------------------- #
if ($NoPath) {
    Write-Host "    skipped (-NoPath)"
}
else {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if ($userPath) { $parts = @($userPath -split ";" | Where-Object { $_ -ne "" }) }
    if ($parts -notcontains $installFull) {
        $parts += $installFull
        [Environment]::SetEnvironmentVariable("Path", ($parts -join ";"), "User")
        Write-Host "    added $installFull to the user PATH"
        Write-Host "    (open a new terminal for 'maplead' to work)"
    }
    else {
        Write-Host "    already on the user PATH"
    }

    # tell Explorer that the environment changed
    try {
        Add-Type -Namespace Maplead -Name Native -MemberDefinition @'
[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam,
    string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@ -ErrorAction Stop
        $result = [UIntPtr]::Zero
        [Maplead.Native]::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero,
            "Environment", 2, 5000, [ref]$result) | Out-Null
    }
    catch {
        # cosmetic only: new terminals still pick the PATH up
    }
}

# --------------------------------------------------------------------------- #
Write-Step "Apps & features entry"
# --------------------------------------------------------------------------- #
$version = (Get-Item -LiteralPath $exe).VersionInfo.ProductVersion
if (-not $version) { $version = "1.0.0" }

$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MAPLEAD"
New-Item -Path $uninstallKey -Force | Out-Null
Set-ItemProperty -Path $uninstallKey -Name "DisplayName"     -Value "MAPLEAD"
Set-ItemProperty -Path $uninstallKey -Name "DisplayVersion"  -Value $version
Set-ItemProperty -Path $uninstallKey -Name "Publisher"       -Value "MAPLEAD contributors"
Set-ItemProperty -Path $uninstallKey -Name "InstallLocation" -Value $installFull
Set-ItemProperty -Path $uninstallKey -Name "DisplayIcon"     -Value "$exe,0"
Set-ItemProperty -Path $uninstallKey -Name "NoModify"        -Value 1 -Type DWord
Set-ItemProperty -Path $uninstallKey -Name "NoRepair"        -Value 1 -Type DWord
Set-ItemProperty -Path $uninstallKey -Name "UninstallString" `
    -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$installFull\uninstall.ps1`""

# --------------------------------------------------------------------------- #
Write-Host ""
Write-Host "MAPLEAD $version installed" -ForegroundColor Green
Write-Host "  desktop app : $exe"
Write-Host "  terminal    : $cmdShim  (or: maplead --demo)"
Write-Host "  exports     : $([Environment]::GetFolderPath('MyDocuments'))\maplead"
Write-Host "  keys        : $env:APPDATA\maplead\.env"
Write-Host ""
