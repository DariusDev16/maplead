<#
.SYNOPSIS
    MAPLEAD Desktop - Windows build (x64).

.DESCRIPTION
    Produces a ready-to-run folder and a zip for Windows users:

        dist\maplead\maplead.exe      the application
        release\MAPLEAD-<ver>-win64.zip

    Nothing is installed system-wide: the build uses a project-local virtual
    environment, exactly like build-appimage.sh does on Linux.

        powershell -ExecutionPolicy Bypass -File .\build-windows.ps1
        powershell -ExecutionPolicy Bypass -File .\build-windows.ps1 -Install
        powershell -ExecutionPolicy Bypass -File .\build-windows.ps1 -NoTest

.NOTES
    Run it on Windows. PyInstaller cannot cross-compile, which is why the GitHub
    Actions workflow uses a windows-latest runner for this.
#>

[CmdletBinding()]
param(
    # also copy the app to %LOCALAPPDATA%\Programs and add a Start menu entry
    [switch] $Install,
    # skip the self-test of the built executable
    [switch] $NoTest,
    # where the zip goes (defaults to .\release)
    [string] $OutDir = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Venv = Join-Path $Root ".venv-gui"
$Python = Join-Path $Venv "Scripts\python.exe"
$Build = Join-Path $Root "build"
$Dist = Join-Path $Root "dist"
if (-not $OutDir) { $OutDir = Join-Path $Root "release" }

function Say($message) { Write-Host "==> $message" -ForegroundColor Cyan }

$version = (Select-String -Path (Join-Path $Root "maplead\art.py") `
            -Pattern '^VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
$zipName = "MAPLEAD-$version-$arch.zip"

Say "1/7  python environment ($arch)"
if (-not (Test-Path $Python)) {
    python -m venv $Venv
    if (-not (Test-Path $Python)) {
        throw "could not create the virtual environment; is Python 3.10+ on PATH?"
    }
}
& $Python -c "import PySide6" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install --quiet --upgrade pip
    & $Python -m pip install --quiet "PySide6-Essentials>=6.8" pyinstaller
}
& $Python -c "import PySide6; from PySide6 import QtCore; print('    PySide6', QtCore.__version__)"

Say "2/7  icons"
# the .ico is committed, so a Windows build works without Qt for rendering
if (-not (Test-Path (Join-Path $Root "packaging\maplead.ico"))) {
    & $Python (Join-Path $Root "packaging\render_icon.py")
}

Say "3/7  pyinstaller (this is the slow part)"
if (Test-Path (Join-Path $Dist "maplead")) {
    Remove-Item -Recurse -Force (Join-Path $Dist "maplead")
}
& $Python -m PyInstaller --noconfirm --clean `
    --distpath $Dist --workpath (Join-Path $Build "work") `
    (Join-Path $Root "packaging\maplead.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $Dist "maplead\maplead.exe"
if (-not (Test-Path $exe)) { throw "maplead.exe was not produced" }

Say "4/7  packaging the zip"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$zip = Join-Path $OutDir $zipName
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $Dist "maplead") -DestinationPath $zip -CompressionLevel Optimal
$sizeMb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "    $zip  ($sizeMb MB)"

Say "5/7  quick checks"
$version = Start-Process -FilePath $exe -ArgumentList "--version" `
    -Wait -PassThru -NoNewWindow
if ($version.ExitCode -ne 0) { throw "the built executable does not run" }

Say "6/7  self-test"
if ($NoTest) {
    Write-Host "    skipped (--NoTest)"
} else {
    # a windowed exe has no console: it writes %TEMP%\maplead-selftest.log.
    # Start-Process -Wait is required because PowerShell does not block on
    # GUI-subsystem executables, so $LASTEXITCODE would be unreliable.
    $env:QT_QPA_PLATFORM = "offscreen"
    $process = Start-Process -FilePath $exe -ArgumentList "--selftest" `
        -Wait -PassThru -NoNewWindow
    Remove-Item Env:\QT_QPA_PLATFORM
    $code = $process.ExitCode

    $log = Join-Path $env:TEMP "maplead-selftest.log"
    if (Test-Path $log) {
        Get-Content $log -Tail 10 | ForEach-Object { Write-Host "    $_" }
    }
    if ($code -ne 0) { throw "self-test failed (exit code $code)" }
    Write-Host "    self-test passed (exit code 0)"
}

Say "7/7  install"
if ($Install) {
    $target = Join-Path $env:LOCALAPPDATA "Programs\maplead"
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Recurse (Join-Path $Dist "maplead\*") $target

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut(
        (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\MAPLEAD.lnk"))
    $shortcut.TargetPath = Join-Path $target "maplead.exe"
    $shortcut.WorkingDirectory = $target
    $shortcut.IconLocation = (Join-Path $Root "packaging\maplead.ico")
    $shortcut.Description = "MAPLEAD - Google Maps lead extractor"
    $shortcut.Save()
    Write-Host "    installed in $target"
    Write-Host "    Start menu entry: MAPLEAD"
}

Say "done"
Write-Host ""
Write-Host "  $zip"
Write-Host ""
Write-Host "  run:     maplead.exe"
Write-Host "  keys:    $env:APPDATA\maplead\.env"
Write-Host "  exports: $env:USERPROFILE\Documents\maplead\"
Write-Host ""