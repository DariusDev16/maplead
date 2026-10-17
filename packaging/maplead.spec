# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build for MAPLEAD Desktop.

    .venv-gui/bin/pyinstaller --noconfirm packaging/maplead.spec

Produces a self-contained `dist/maplead/maplead` (onedir: fast startup, which is
what the AppImage ships) plus a `maplead-gui` console wrapper.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent          # noqa: F821 - injected by PyInstaller

# Windows takes an .ico, Linux/macOS ignore the icon argument entirely
import sys as _sys                                            # noqa: E402
_ICON = ROOT / "packaging" / ("maplead.ico" if _sys.platform.startswith("win")
                              else "maplead.png")

# Qt modules we never touch - dropping them roughly halves the bundle
EXCLUDES = [
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
    "tkinter", "unittest", "pydoc_data", "test", "lib2to3", "distutils",
    "matplotlib", "numpy", "pandas", "PIL", "setuptools", "pip",
]

a = Analysis(                                          # noqa: F821
    [str(ROOT / "packaging" / "gui_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "packaging" / "maplead.svg"), "share/maplead")],
    hiddenimports=[
        "maplead.gui.app",
        "maplead.gui.main_window",
        "maplead.gui.keys",
        "maplead.gui.widgets",
        "maplead.gui.worker",
        "maplead.gui.icons",
        "maplead.gui.theme",
        "PySide6.QtSvg",
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)                                     # noqa: F821

exe = EXE(                                             # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="maplead",
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
    icon=str(_ICON),
)

coll = COLLECT(                                       # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="maplead",
)