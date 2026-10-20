#Requires -Version 5.1
<#
.SYNOPSIS
    Build MAPLEAD for Windows x64 - portable folder + ZIP.

.DESCRIPTION
    One command, no admin rights, nothing installed system-wide:

        powershell -ExecutionPolicy Bypass -File .\build-windows.ps1

    What it does, in order:
      1. creates/updates .venv-win (PySide6-Essentials + PyInstaller);
      2. renders the PNG icons and the multi-size maplead.ico from the SVG;
      3. runs PyInstaller with packaging/maplead-win.spec - one folder with
         MAPLEAD.exe (desktop) and maplead-cli.exe (terminal wizard);
      4. runs the headless self-test, from source and from the frozen build;
      5. zips the result into %USERPROFILE%\Apps\MAPLEAD-<version>-win64.zip.

.PARAMETER OutDir
    Where the ZIP is written. Defaults to %USERPROFILE%\Apps (outside the repo,
    so a `git clean` never eats the product).

.PARAMETER NoTest
    Skip the self-tests.

.PARAMETER Install
    Also install into %LOCALAPPDATA%\Programs\MAPLEAD (Start Menu + PATH).

.PARAMETER Python
    Bootstrap interpreter to create the venv with. Defaults to `py` / `python`.

.EXAMPLE
    .\build-windows.ps1 -Install
#>
[CmdletBinding()]
param(
    [string]$OutDir = (Join-Path $env:USERPROFILE "Apps"),
    [switch]$NoTest,
    [switch]$Install,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Invoke-Python {
    param([string[]]$Arguments)
    & $script:Py @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "python $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

$Venv = Join-Path $Root ".venv-win"
$Py = Join-Path $Venv "Scripts\python.exe"
$Dist = Join-Path $Root "dist\MAPLEAD"

$Version = (Select-String -Path (Join-Path $Root "maplead\art.py") `
        -Pattern 'VERSION = "([^"]+)"' -AllMatches).Matches[0].Groups[1].Value
if (-not $Version) { throw "could not read VERSION from maplead\art.py" }

# --------------------------------------------------------------------------- #
Write-Step "1/6  python environment"
# --------------------------------------------------------------------------- #
if (-not (Test-Path -LiteralPath $Py)) {
    if ($Python) {
        $bootstrap = $Python
    }
    else {
        $bootstrap = $null
        foreach ($name in @("py", "python", "python3")) {
            $found = Get-Command $name -ErrorAction SilentlyContinue
            if ($found) { $bootstrap = $found.Source; break }
        }
        if (-not $bootstrap) {
            throw "Python 3.9+ not found. Install it from https://www.python.org/downloads/windows/"
        }
    }
    Write-Host "    creating $Venv with $bootstrap"
    & $bootstrap -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        throw "could not create the virtual environment (Python 3.9+ and the venv module are required)"
    }
}

& $Py -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Python @("-m", "ensurepip", "--upgrade")
}

& $Py -c "import PySide6, PyInstaller" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    installing PySide6-Essentials + PyInstaller (this downloads ~150 MB)"
    Invoke-Python @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
    Invoke-Python @("-m", "pip", "install", "--quiet", "PySide6-Essentials>=6.8", "pyinstaller")
}
$qt = & $Py -c "from PySide6 import QtCore; print(QtCore.__version__)"
Write-Host "    python $(& $Py -c 'import sys; print(sys.version.split()[0])')  |  PySide6 $qt"

# --------------------------------------------------------------------------- #
Write-Step "2/6  icons"
# --------------------------------------------------------------------------- #
$env:QT_QPA_PLATFORM = "offscreen"
Invoke-Python @("packaging/render_icon.py")

# --------------------------------------------------------------------------- #
Write-Step "3/6  pyinstaller (this is the slow part)"
# --------------------------------------------------------------------------- #
# A terminal or Explorer window left open inside dist\MAPLEAD keeps the folder
# locked, which PyInstaller can only report as "Access is denied" -name it early.
if (Test-Path -LiteralPath $Dist) {
    try {
        Remove-Item -LiteralPath $Dist -Recurse -Force -ErrorAction Stop
    }
    catch {
        throw "cannot replace $Dist - something still has it open. Close any terminal or Explorer window inside that folder and run again."
    }
}

Invoke-Python @("-m", "PyInstaller", "--noconfirm", "--clean",
    "--distpath", (Join-Path $Root "dist"),
    "--workpath", (Join-Path $Root "build\work"),
    "packaging/maplead-win.spec")

if (-not (Test-Path -LiteralPath (Join-Path $Dist "MAPLEAD.exe"))) {
    throw "build finished without dist\MAPLEAD\MAPLEAD.exe"
}


# --------------------------------------------------------------------------- #
Write-Step "4/6  portable extras"
# --------------------------------------------------------------------------- #
@'
@echo off
"%~dp0maplead-cli.exe" %*
'@ | Set-Content -LiteralPath (Join-Path $Dist "maplead.cmd") -Encoding ASCII

Copy-Item -LiteralPath (Join-Path $Root "packaging\install-windows.ps1") `
    -Destination (Join-Path $Dist "install.ps1") -Force
Copy-Item -LiteralPath (Join-Path $Root "packaging\uninstall-windows.ps1") `
    -Destination (Join-Path $Dist "uninstall.ps1") -Force
foreach ($doc in @("README.md", "LICENSE", "CHANGELOG.md")) {
    $path = Join-Path $Root $doc
    if (Test-Path -LiteralPath $path) {
        Copy-Item -LiteralPath $path -Destination (Join-Path $Dist $doc) -Force
    }
}

# --------------------------------------------------------------------------- #
Write-Step "5/6  smoke test"
# --------------------------------------------------------------------------- #
if ($NoTest) {
    Write-Host "    skipped (-NoTest)"
}
else {
    Write-Host "    source build: terminal wizard"
    $leads = Join-Path $env:TEMP "maplead-selftest-cli"
    Invoke-Python @("maplead.py", "--demo", "--country", "Germany", "--city", "Berlin",
        "--business", "dentist", "--fields", "rec", "--limit", "30",
        "--format", "xlsx", "--outdir", $leads)

    Write-Host "    source build: desktop app (headless)"
    Invoke-Python @("maplead-gui.py", "--selftest")

    Write-Host "    frozen build: terminal wizard"
    & (Join-Path $Dist "maplead-cli.exe") --demo --country Germany --city Berlin `
        --business dentist --fields rec --limit 20 --format csv --outdir $leads
    if ($LASTEXITCODE -ne 0) { throw "the frozen wizard failed (exit $LASTEXITCODE)" }

    Write-Host "    frozen build: desktop app (headless)"
    $proc = Start-Process -FilePath (Join-Path $Dist "MAPLEAD.exe") `
        -ArgumentList "--selftest" -WorkingDirectory $Dist -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "the frozen desktop app failed (exit $($proc.ExitCode))" }
    Write-Host "    ok"
}
Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue

# --------------------------------------------------------------------------- #
Write-Step "6/6  zip"
# --------------------------------------------------------------------------- #
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$zip = Join-Path $OutDir "MAPLEAD-$Version-win64.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path $Dist -DestinationPath $zip -CompressionLevel Optimal
$sizeMb = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 1)

# --------------------------------------------------------------------------- #
if ($Install) {
    Write-Step "installing"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $Dist "install.ps1") -Source $Dist
    if ($LASTEXITCODE -ne 0) { throw "the installer failed (exit $LASTEXITCODE)" }
}

Write-Host ""
Write-Host "MAPLEAD $Version for Windows x64" -ForegroundColor Green
Write-Host "  folder  : $Dist"
Write-Host "  zip     : $zip  ($sizeMb MB)"
Write-Host "  desktop : $Dist\MAPLEAD.exe"
Write-Host "  wizard  : $Dist\maplead-cli.exe  (or: maplead.cmd)"
Write-Host ""
Write-Host "To install: unpack the ZIP and run  .\install.ps1"
Write-Host ""
