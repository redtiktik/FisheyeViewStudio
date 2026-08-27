# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH)
tools_dir = project / "tools"

# Keep the portable bundle compact by shipping only ffmpeg.exe.  The app can
# read media metadata directly from FFmpeg when ffprobe.exe is not present.
binaries = []
ffmpeg_exe = tools_dir / "ffmpeg.exe"
if ffmpeg_exe.is_file():
    binaries.append((str(ffmpeg_exe), "tools"))

# Shared FFmpeg builds may require DLLs from the same folder.
for dll_path in sorted(tools_dir.glob("*.dll")):
    binaries.append((str(dll_path), "tools"))

datas = [
    (str(project / "assets"), "assets"),
]

for optional_file in ("FFMPEG_BUILD_INFO.txt", "THIRD_PARTY_NOTICES.txt"):
    candidate = tools_dir / optional_file
    if candidate.is_file():
        datas.append((str(candidate), "tools"))

licenses_dir = tools_dir / "licenses"
if licenses_dir.is_dir():
    datas.append((str(licenses_dir), "tools/licenses"))

analysis = Analysis(
    [str(project / "fisheye_view_studio.pyw")],
    pathex=[str(project)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # The application uses QtCore, QtGui, and QtWidgets only.  Excluding
        # unused optional modules reduces accidental collection if a future
        # PyInstaller hook becomes more aggressive.
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtDesigner",
        "PySide6.QtGraphs",
        "PySide6.QtLocation",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNfc",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSensors",
        "PySide6.QtSerialBus",
        "PySide6.QtSerialPort",
        "PySide6.QtSpatialAudio",
        "PySide6.QtStateMachine",
        "PySide6.QtTextToSpeech",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Fisheye View Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project / "assets" / "fisheye.ico"),
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Fisheye View Studio",
)
