from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .ffmpeg_service import resource_path
from .main_window import MainWindow
from .theme import APP_STYLE


def main() -> int:
    QtCore.QCoreApplication.setOrganizationName("FisheyeViewStudio")
    QtCore.QCoreApplication.setApplicationName("Fisheye View Studio")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationDisplayName("Fisheye View Studio")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    icon_path = resource_path("assets/fisheye.ico")
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.exists() and candidate.is_file():
            QtCore.QTimer.singleShot(250, lambda: window._load_video(candidate))

    return app.exec()
