#Requires -Version 5.1
<#
.SYNOPSIS
    Build MAPLEAD for Windows x64 - a single portable .exe.

.DESCRIPTION
    One command, no admin rights, nothing installed system-wide:

        powershell -ExecutionPolicy Bypass -File .\build-windows.ps1

    What it does, in order:
      1. creates/updates .venv-win (PySide6-Essentials + PyInstaller);
      2. renders the PNG icons and the multi-size maplead.ico from the SVG;
      3. runs PyInstaller with packaging/maplead-win.spec -> dist\MAPLEAD.exe,
         one file that is both the desktop app and the terminal wizard;
      4. smoke-tests --version, --demo, --doctor and --selftest, from source
         and from the frozen exe;
      5. copies the result to %USERPROFILE%\Apps\MAPLEAD-<version>-windows-x64.exe.

.PARAMETER OutDir
    Where the .exe is written. Defaults to %USERPROFILE%\Apps (outside the repo,
    so a `git clean` never eats the product).

.PARAMETER NoTest
    Skip the self-tests.

.PARAMETER Python
    Bootstrap interpreter to create the venv with. Defaults to `py` / `python`.

.EXAMPLE
    .\build-windows.ps1
#>
[CmdletBinding()]
param(
    [string]$OutDir = (Join-Path $env:USERPROFILE "Apps"),
    [switch]$NoTest,
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
$Dist = Join-Path $Root "dist\MAPLEAD.exe"

$Version = (Select-String -Path (Join-Path $Root "maplead\art.py") `
        -Pattern 'VERSION = "([^"]+)"' -AllMatches).Matches[0].Groups[1].Value
if (-not $Version) { throw "could not read VERSION from maplead\art.py" }

$Product = "MAPLEAD-$Version-windows-x64.exe"

# --------------------------------------------------------------------------- #
Write-Step "1/5  python environment"
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
Write-Step "2/5  icons"
# --------------------------------------------------------------------------- #
$env:QT_QPA_PLATFORM = "offscreen"
Invoke-Python @("packaging/render_icon.py")

# --------------------------------------------------------------------------- #
Write-Step "3/5  pyinstaller (this is the slow part)"
# --------------------------------------------------------------------------- #
# A running copy of the previous build keeps the file locked; say so plainly
# instead of letting PyInstaller fail with "Access is denied".
if (Test-Path -LiteralPath $Dist) {
    try {
        Remove-Item -LiteralPath $Dist -Force -ErrorAction Stop
    }
    catch {
        throw "cannot replace $Dist - it is running. Close MAPLEAD and run again."
    }
}

Invoke-Python @("-m", "PyInstaller", "--noconfirm", "--clean",
    "--distpath", (Join-Path $Root "dist"),
    "--workpath", (Join-Path $Root "build\work"),
    "packaging/maplead-win.spec")

if (-not (Test-Path -LiteralPath $Dist)) {
    throw "build finished without dist\MAPLEAD.exe"
}

# --------------------------------------------------------------------------- #
Write-Step "4/5  smoke test"
# --------------------------------------------------------------------------- #
if ($NoTest) {
    Write-Host "    skipped (-NoTest)"
}
else {
    $leads = Join-Path $env:TEMP "maplead-selftest-cli"

    Write-Host "    source: terminal wizard"
    Invoke-Python @("maplead.py", "--demo", "--country", "Germany", "--city", "Berlin",
        "--business", "dentist", "--fields", "rec", "--limit", "30",
        "--format", "xlsx", "--outdir", $leads)

    Write-Host "    source: desktop app (headless)"
    Invoke-Python @("maplead-gui.py", "--selftest")

    Write-Host "    frozen: one exe, both interfaces"
    & $Dist --version
    if ($LASTEXITCODE -ne 0) { throw "MAPLEAD.exe --version failed" }
    & $Dist --doctor *> $null
    if ($LASTEXITCODE -ne 0) { throw "MAPLEAD.exe --doctor failed" }
    & $Dist --demo --country Germany --city Berlin --business dentist `
        --fields rec --limit 20 --format csv --outdir $leads
    if ($LASTEXITCODE -ne 0) { throw "the frozen wizard failed (exit $LASTEXITCODE)" }

    Write-Host "    frozen: desktop app (headless)"
    $proc = Start-Process -FilePath $Dist -ArgumentList "--selftest" `
        -WorkingDirectory (Join-Path $Root "dist") -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "the frozen desktop app failed (exit $($proc.ExitCode))" }
    Write-Host "    ok"
}
Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue

# --------------------------------------------------------------------------- #
Write-Step "5/5  publish"
# --------------------------------------------------------------------------- #
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$target = Join-Path $OutDir $Product
Copy-Item -LiteralPath $Dist -Destination $target -Force
$sizeMb = [math]::Round((Get-Item -LiteralPath $target).Length / 1MB, 1)

Write-Host ""
Write-Host "MAPLEAD $Version for Windows x64" -ForegroundColor Green
Write-Host "  build : $Dist"
Write-Host "  exe   : $target  ($sizeMb MB)"
Write-Host ""
Write-Host "Double-click it for the desktop app, or run it from a terminal:" -ForegroundColor DarkGray
Write-Host "  MAPLEAD.exe --cli --demo      the terminal wizard" -ForegroundColor DarkGray
Write-Host "  MAPLEAD.exe --doctor          host diagnostics" -ForegroundColor DarkGray
Write-Host ""
