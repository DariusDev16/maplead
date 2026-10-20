# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build for MAPLEAD on Windows.

    .venv-win\\Scripts\\python -m PyInstaller --noconfirm packaging/maplead-win.spec

Produces `dist/MAPLEAD/`, a portable folder that needs no installer and no
Python:

    MAPLEAD.exe      windowed desktop app (no console flash)
    maplead-cli.exe  terminal wizard (real console, colours, UTF-8)
    _internal/     Qt + Python runtime shared by both

Both executables come from the same source tree but have separate `Analysis`
graphs: the console build drops PySide6 entirely (it is ~150 MB of Qt that the
wizard never uses) and hands `--gui` over to MAPLEAD.exe instead.
"""

import re
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent          # noqa: F821 - injected by PyInstaller
PACKAGING = ROOT / "packaging"

VERSION = re.search(r'VERSION = "([^"]+)"',
                    (ROOT / "maplead" / "art.py").read_text(encoding="utf-8")).group(1)
ICON = PACKAGING / ("maplead.ico" if (PACKAGING / "maplead.ico").exists()
                    else "maplead.png")


def _windows_version_resource():
    """File properties (Details tab, Apps & features) without a hand-kept file."""
    try:
        from PyInstaller.utils.win32.versioninfo import (
            FixedFileInfo, StringFileInfo, StringStruct, StringTable,
            VarFileInfo, VarStruct, VSVersionInfo,
        )
    except Exception:                                    # pragma: no cover - non-Windows
        return None

    numbers = [int(part) for part in re.findall(r"\d+", VERSION)]
    while len(numbers) < 4:
        numbers.append(0)
    quad = tuple(numbers[:4])

    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=quad, prodvers=quad, mask=0x3F, flags=0x0,
                          OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "MAPLEAD contributors"),
                StringStruct("FileDescription", "MAPLEAD - Google Maps lead extractor"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "maplead"),
                StringStruct("LegalCopyright", "MIT License"),
                StringStruct("OriginalFilename", "MAPLEAD.exe"),
                StringStruct("ProductName", "MAPLEAD"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
    target = ROOT / "build" / "version_info.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(info), encoding="utf-8")     # PyInstaller's textual format
    return target


VERSION_FILE = _windows_version_resource()
VERSION_ARG = str(VERSION_FILE) if VERSION_FILE else None


# Qt modules we never touch - dropping them roughly halves the bundle
QT_EXCLUDES = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtHelp",
    "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtSql", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtHttpServer", "PySide6.QtConcurrent", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
]

COMMON_EXCLUDES = QT_EXCLUDES + [
    "tkinter", "unittest", "pydoc_data", "test", "lib2to3", "distutils",
    "matplotlib", "numpy", "pandas", "PIL", "setuptools", "pip",
]

# --------------------------------------------------------------------------- #
# desktop app (PySide6)
# --------------------------------------------------------------------------- #

gui_a = Analysis(                                       # noqa: F821
    [str(PACKAGING / "gui_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(PACKAGING / "maplead.svg"), "share/maplead")],
    hiddenimports=[
        "maplead.gui.app",
        "maplead.gui.main_window",
        "maplead.gui.keys",
        "maplead.gui.widgets",
        "maplead.gui.worker",
        "maplead.gui.icons",
        "maplead.gui.theme",
        # `--cli` imports the wizard lazily, so PyInstaller cannot see it
        "maplead.cli",
        "PySide6.QtSvg",
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=COMMON_EXCLUDES,
    noarchive=False,
    optimize=0,
)

gui_pyz = PYZ(gui_a.pure)                               # noqa: F821

gui_exe = EXE(                                          # noqa: F821
    gui_pyz,
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name="MAPLEAD",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=VERSION_ARG,
)

# --------------------------------------------------------------------------- #
# terminal wizard (stdlib only - no Qt in this graph)
# --------------------------------------------------------------------------- #

cli_a = Analysis(                                       # noqa: F821
    [str(PACKAGING / "cli_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["maplead.cli"],
    hookspath=[],
    runtime_hooks=[],
    excludes=COMMON_EXCLUDES + ["PySide6", "shiboken6"],
    noarchive=False,
    optimize=0,
)

cli_pyz = PYZ(cli_a.pure)                               # noqa: F821

cli_exe = EXE(                                          # noqa: F821
    cli_pyz,
    cli_a.scripts,
    [],
    exclude_binaries=True,
    # NOT "maplead": Windows filenames are case-insensitive, so it would collide
    # with MAPLEAD.exe and one of the two would silently overwrite the other.
    # The bundled maplead.cmd shim gives users the `maplead` command back.
    name="maplead-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=VERSION_ARG,
)

coll = COLLECT(                                         # noqa: F821
    gui_exe,
    gui_a.binaries,
    gui_a.datas,
    cli_exe,
    cli_a.binaries,
    cli_a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MAPLEAD",
)
