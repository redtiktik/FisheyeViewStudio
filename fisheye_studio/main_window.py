from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Callable, Iterable
import json
import os
import subprocess
import tempfile
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

from .ffmpeg_service import (
    VIDEO_EXTENSIONS,
    build_extract_frame_args,
    build_preview_args,
    build_render_command,
    detect_nvenc,
    estimate_output_bytes,
    human_size,
    locate_ffmpeg,
    probe_media,
    resource_path,
)
from .models import (
    MediaInfo,
    RenderSettings,
    TimestampSettings,
    ViewDefinition,
    VIEW_COLORS,
    default_views,
)
from .widgets import FisheyeOverlayWidget, PreviewCard, StatusPill


class WorkerSignals(QtCore.QObject):
    result = QtCore.Signal(object)
    error = QtCore.Signal(str)
    finished = QtCore.Signal()


class FunctionWorker(QtCore.QRunnable):
    def __init__(self, function: Callable[..., object], *args: object) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self.function(*self.args)
        except Exception as exc:  # noqa: BLE001
            details = str(exc).strip() or exc.__class__.__name__
            self.signals.error.emit(details)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class MainWindow(QtWidgets.QMainWindow):
    MAX_VIEWS = 8

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Fisheye View Studio")
        self.setMinimumSize(1220, 780)
        self.resize(1600, 970)
        self.setAcceptDrops(True)

        icon_path = resource_path("assets/fisheye.ico")
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))

        self.settings = QtCore.QSettings("FisheyeViewStudio", "FisheyeViewStudio")
        self.thread_pool = QtCore.QThreadPool.globalInstance()
        self.temp_dir = tempfile.TemporaryDirectory(prefix="fisheye-view-studio-")
        self.temp_path = Path(self.temp_dir.name)

        self.views: list[ViewDefinition] = default_views()
        self.selected_index = 0
        self.timestamp_settings = TimestampSettings()
        self.render_settings = RenderSettings()
        self.media_info: MediaInfo | None = None
        self.input_path: Path | None = None
        self.output_dir: Path | None = None
        self.source_pixmap = QtGui.QPixmap()
        self.preview_pixmaps: dict[str, QtGui.QPixmap] = {}
        self.preview_cards: list[PreviewCard] = []

        self.ffmpeg_path: Path | None = None
        self.ffprobe_path: Path | None = None
        self.nvenc_available = False
        self._ffmpeg_check_in_progress = False
        self._updating_controls = False
        self._loading_media = False
        self._processing = False
        self._cancel_requested = False

        self.frame_process = QtCore.QProcess(self)
        self.frame_process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        self.frame_process.finished.connect(self._frame_process_finished)

        self.preview_process = QtCore.QProcess(self)
        self.preview_process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        self.preview_process.finished.connect(self._preview_process_finished)
        self.preview_queue: deque[int] = deque()
        self.current_preview_index = -1

        self.render_process = QtCore.QProcess(self)
        self.render_process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        self.render_process.readyReadStandardOutput.connect(self._read_render_output)
        self.render_process.finished.connect(self._render_finished)

        self.preview_debounce = QtCore.QTimer(self)
        self.preview_debounce.setSingleShot(True)
        self.preview_debounce.setInterval(450)
        self.preview_debounce.timeout.connect(self._refresh_selected_preview_now)

        self._build_ui()
        self._rebuild_view_list()
        self._rebuild_preview_cards()
        self._select_view(0)
        self._restore_settings()
        self._resolve_ffmpeg()
        self._update_estimate()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)

        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        outer.addWidget(self._build_header())

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_source_card())
        splitter.addWidget(self._build_right_column())
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([880, 700])
        outer.addWidget(splitter, 1)

        outer.addWidget(self._build_render_bar())

    def _build_header(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("HeaderCard")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        icon_label = QtWidgets.QLabel()
        icon = self.windowIcon()
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(42, 42))
        icon_label.setFixedSize(46, 46)
        icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        title = QtWidgets.QLabel("Fisheye View Studio")
        title.setObjectName("AppTitle")
        subtitle = QtWidgets.QLabel(
            "Aim normal 1080p views directly on a circular fisheye frame, preview them, and render with FFmpeg."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles, 1)

        self.ffmpeg_status = StatusPill("Checking FFmpeg…")
        layout.addWidget(self.ffmpeg_status)

        choose_ffmpeg = QtWidgets.QPushButton("Choose FFmpeg")
        choose_ffmpeg.clicked.connect(self._choose_ffmpeg)
        layout.addWidget(choose_ffmpeg)
        return frame

    def _build_source_card(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top = QtWidgets.QHBoxLayout()
        section = QtWidgets.QLabel("1. Choose and aim the source")
        section.setObjectName("SectionTitle")
        top.addWidget(section)
        top.addStretch(1)

        select_button = QtWidgets.QPushButton("Select video")
        select_button.setObjectName("PrimaryButton")
        select_button.clicked.connect(self._choose_video)
        top.addWidget(select_button)
        layout.addLayout(top)

        self.file_path_label = QtWidgets.QLabel("No video selected. You can also drag an MP4 onto this window.")
        self.file_path_label.setObjectName("FilePath")
        self.file_path_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.file_path_label.setWordWrap(True)
        layout.addWidget(self.file_path_label)

        source_controls = QtWidgets.QHBoxLayout()
        source_controls.setSpacing(8)
        self.media_details_label = QtWidgets.QLabel("Waiting for a video")
        self.media_details_label.setObjectName("MutedLabel")
        source_controls.addWidget(self.media_details_label, 1)

        source_controls.addWidget(QtWidgets.QLabel("Preview at"))
        self.preview_time_spin = QtWidgets.QDoubleSpinBox()
        self.preview_time_spin.setDecimals(1)
        self.preview_time_spin.setRange(0.0, 0.0)
        self.preview_time_spin.setSingleStep(1.0)
        self.preview_time_spin.setSuffix(" sec")
        self.preview_time_spin.setFixedWidth(105)
        source_controls.addWidget(self.preview_time_spin)

        reload_frame = QtWidgets.QPushButton("Load frame")
        reload_frame.clicked.connect(self._extract_source_frame)
        source_controls.addWidget(reload_frame)
        layout.addLayout(source_controls)

        self.overlay = FisheyeOverlayWidget()
        self.overlay.view_selected.connect(self._overlay_view_selected)
        self.overlay.view_changed.connect(self._overlay_view_changed)
        self.overlay.create_view_requested.connect(self._add_view_at)
        self.overlay.set_timestamp_settings(self.timestamp_settings)
        layout.addWidget(self.overlay, 1)

        layout_buttons = QtWidgets.QHBoxLayout()
        reset_button = QtWidgets.QPushButton("Reset five views")
        reset_button.clicked.connect(self._reset_views)
        layout_buttons.addWidget(reset_button)

        load_layout = QtWidgets.QPushButton("Load layout")
        load_layout.clicked.connect(self._load_layout)
        layout_buttons.addWidget(load_layout)

        save_layout = QtWidgets.QPushButton("Save layout")
        save_layout.clicked.connect(self._save_layout)
        layout_buttons.addWidget(save_layout)
        layout_buttons.addStretch(1)
        layout.addLayout(layout_buttons)
        return frame

    def _build_right_column(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_view_controls_card())
        layout.addWidget(self._build_previews_card(), 1)
        return container

    def _build_view_controls_card(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("2. Fine-tune the selected view")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)

        add_button = QtWidgets.QPushButton("Add")
        add_button.clicked.connect(self._add_view)
        header.addWidget(add_button)
        duplicate_button = QtWidgets.QPushButton("Duplicate")
        duplicate_button.clicked.connect(self._duplicate_view)
        header.addWidget(duplicate_button)
        delete_button = QtWidgets.QPushButton("Delete")
        delete_button.setObjectName("DangerButton")
        delete_button.clicked.connect(self._delete_view)
        header.addWidget(delete_button)
        layout.addLayout(header)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(12)

        self.view_list = QtWidgets.QListWidget()
        self.view_list.setMaximumWidth(210)
        self.view_list.setMinimumWidth(170)
        self.view_list.currentRowChanged.connect(self._view_list_changed)
        body.addWidget(self.view_list)

        editor = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(editor)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(9)
        grid.setVerticalSpacing(9)

        grid.addWidget(QtWidgets.QLabel("Name"), 0, 0)
        self.view_name_edit = QtWidgets.QLineEdit()
        self.view_name_edit.editingFinished.connect(self._view_name_changed)
        grid.addWidget(self.view_name_edit, 0, 1, 1, 3)

        self.view_enabled_box = QtWidgets.QCheckBox("Include in final render")
        self.view_enabled_box.toggled.connect(self._view_enabled_changed)
        grid.addWidget(self.view_enabled_box, 1, 0, 1, 4)

        self.roll_slider, self.roll_spin = self._make_slider_row(-180.0, 180.0, 0.1)
        grid.addWidget(QtWidgets.QLabel("Roll"), 2, 0)
        grid.addWidget(self.roll_slider, 2, 1, 1, 2)
        grid.addWidget(self.roll_spin, 2, 3)

        self.pitch_slider, self.pitch_spin = self._make_slider_row(0.0, 88.0, 0.1)
        grid.addWidget(QtWidgets.QLabel("Pitch"), 3, 0)
        grid.addWidget(self.pitch_slider, 3, 1, 1, 2)
        grid.addWidget(self.pitch_spin, 3, 3)

        self.hfov_slider, self.hfov_spin = self._make_slider_row(40.0, 140.0, 1.0)
        grid.addWidget(QtWidgets.QLabel("Horizontal FOV"), 4, 0)
        grid.addWidget(self.hfov_slider, 4, 1, 1, 2)
        grid.addWidget(self.hfov_spin, 4, 3)

        self.vfov_slider, self.vfov_spin = self._make_slider_row(30.0, 110.0, 1.0)
        grid.addWidget(QtWidgets.QLabel("Vertical FOV"), 5, 0)
        grid.addWidget(self.vfov_slider, 5, 1, 1, 2)
        grid.addWidget(self.vfov_spin, 5, 3)

        self.roll_slider.valueChanged.connect(lambda value: self._slider_changed("roll", value / 10.0))
        self.roll_spin.valueChanged.connect(lambda value: self._spin_changed("roll", value))
        self.pitch_slider.valueChanged.connect(lambda value: self._slider_changed("pitch", value / 10.0))
        self.pitch_spin.valueChanged.connect(lambda value: self._spin_changed("pitch", value))
        self.hfov_slider.valueChanged.connect(lambda value: self._slider_changed("h_fov", float(value)))
        self.hfov_spin.valueChanged.connect(lambda value: self._spin_changed("h_fov", value))
        self.vfov_slider.valueChanged.connect(lambda value: self._slider_changed("v_fov", float(value)))
        self.vfov_spin.valueChanged.connect(lambda value: self._spin_changed("v_fov", value))

        refresh_button = QtWidgets.QPushButton("Refresh selected preview")
        refresh_button.clicked.connect(self._refresh_selected_preview_now)
        grid.addWidget(refresh_button, 6, 1, 1, 3)

        body.addWidget(editor, 1)
        layout.addLayout(body)
        return frame

    def _build_previews_card(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("First-frame previews")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        subtitle = QtWidgets.QLabel("These are generated by the same FFmpeg v360 settings used for the final files.")
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        header.addWidget(subtitle, 1)
        refresh_all = QtWidgets.QPushButton("Refresh all")
        refresh_all.clicked.connect(self._queue_all_previews)
        header.addWidget(refresh_all)
        layout.addLayout(header)

        self.preview_scroll = QtWidgets.QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_container = QtWidgets.QWidget()
        self.preview_grid = QtWidgets.QGridLayout(self.preview_container)
        self.preview_grid.setContentsMargins(0, 0, 0, 0)
        self.preview_grid.setHorizontalSpacing(10)
        self.preview_grid.setVerticalSpacing(10)
        self.preview_scroll.setWidget(self.preview_container)
        layout.addWidget(self.preview_scroll, 1)
        return frame

    def _build_render_bar(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("RenderBar")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        top = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("3. Render the enabled views")
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        top.addStretch(1)

        self.estimate_label = QtWidgets.QLabel("Estimated size: waiting for a video")
        self.estimate_label.setObjectName("MutedLabel")
        top.addWidget(self.estimate_label)
        layout.addLayout(top)

        options = QtWidgets.QGridLayout()
        options.setHorizontalSpacing(9)
        options.setVerticalSpacing(8)

        options.addWidget(QtWidgets.QLabel("Output folder"), 0, 0)
        self.output_edit = QtWidgets.QLineEdit()
        self.output_edit.textChanged.connect(self._output_path_changed)
        options.addWidget(self.output_edit, 0, 1, 1, 5)
        browse_output = QtWidgets.QPushButton("Browse")
        browse_output.clicked.connect(self._choose_output_dir)
        options.addWidget(browse_output, 0, 6)

        options.addWidget(QtWidgets.QLabel("Encoder"), 1, 0)
        self.encoder_combo = QtWidgets.QComboBox()
        self.encoder_combo.addItem("Auto: NVIDIA when available", "auto")
        self.encoder_combo.addItem("NVIDIA NVENC", "nvenc")
        self.encoder_combo.addItem("CPU: libx264", "cpu")
        self.encoder_combo.currentIndexChanged.connect(self._render_setting_changed)
        options.addWidget(self.encoder_combo, 1, 1)

        options.addWidget(QtWidgets.QLabel("Output"), 1, 2)
        output_label = QtWidgets.QLabel("1920 × 1080 H.264")
        output_label.setObjectName("MutedLabel")
        options.addWidget(output_label, 1, 3)

        options.addWidget(QtWidgets.QLabel("Bitrate"), 1, 4)
        self.bitrate_spin = QtWidgets.QSpinBox()
        self.bitrate_spin.setRange(1000, 12000)
        self.bitrate_spin.setValue(3000)
        self.bitrate_spin.setSingleStep(250)
        self.bitrate_spin.setSuffix(" kbps")
        self.bitrate_spin.valueChanged.connect(self._render_setting_changed)
        options.addWidget(self.bitrate_spin, 1, 5)

        self.test_box = QtWidgets.QCheckBox("20-second test render")
        self.test_box.toggled.connect(self._render_setting_changed)
        options.addWidget(self.test_box, 1, 6)

        self.timestamp_box = QtWidgets.QCheckBox("Preserve the original running timestamp and camera name")
        self.timestamp_box.setChecked(True)
        self.timestamp_box.toggled.connect(self._timestamp_enabled_changed)
        options.addWidget(self.timestamp_box, 2, 0, 1, 4)

        self.advanced_button = QtWidgets.QToolButton()
        self.advanced_button.setText("Show timestamp and quality settings")
        self.advanced_button.setCheckable(True)
        self.advanced_button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.advanced_button.toggled.connect(self._toggle_advanced)
        options.addWidget(self.advanced_button, 2, 4, 1, 3, QtCore.Qt.AlignmentFlag.AlignRight)

        layout.addLayout(options)

        self.advanced_widget = self._build_advanced_settings()
        self.advanced_widget.setVisible(False)
        layout.addWidget(self.advanced_widget)

        actions = QtWidgets.QHBoxLayout()
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready")
        actions.addWidget(self.progress_bar, 1)

        self.log_button = QtWidgets.QToolButton()
        self.log_button.setText("Show log")
        self.log_button.setCheckable(True)
        self.log_button.toggled.connect(self._toggle_log)
        actions.addWidget(self.log_button)

        self.open_output_button = QtWidgets.QPushButton("Open output")
        self.open_output_button.clicked.connect(self._open_output_folder)
        actions.addWidget(self.open_output_button)

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.setObjectName("DangerButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_render)
        actions.addWidget(self.cancel_button)

        self.render_button = QtWidgets.QPushButton("Render views")
        self.render_button.setObjectName("PrimaryButton")
        self.render_button.clicked.connect(self._start_render)
        actions.addWidget(self.render_button)
        layout.addLayout(actions)

        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(1500)
        self.log_edit.setMinimumHeight(140)
        self.log_edit.setVisible(False)
        layout.addWidget(self.log_edit)
        return frame

    def _build_advanced_settings(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(widget)
        grid.setContentsMargins(0, 4, 0, 2)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)

        self.ts_x_spin = self._integer_spin(0, 10000, self.timestamp_settings.crop_x)
        self.ts_y_spin = self._integer_spin(0, 10000, self.timestamp_settings.crop_y)
        self.ts_w_spin = self._integer_spin(1, 10000, self.timestamp_settings.crop_width)
        self.ts_h_spin = self._integer_spin(1, 1000, self.timestamp_settings.crop_height)
        self.ts_overlay_w_spin = self._integer_spin(80, 1920, self.timestamp_settings.overlay_width)
        self.ts_overlay_x_spin = self._integer_spin(0, 1920, self.timestamp_settings.overlay_x)
        self.ts_overlay_y_spin = self._integer_spin(0, 1080, self.timestamp_settings.overlay_y)

        timestamp_spins = [
            self.ts_x_spin,
            self.ts_y_spin,
            self.ts_w_spin,
            self.ts_h_spin,
            self.ts_overlay_w_spin,
            self.ts_overlay_x_spin,
            self.ts_overlay_y_spin,
        ]
        for spin in timestamp_spins:
            spin.valueChanged.connect(self._timestamp_setting_changed)

        grid.addWidget(QtWidgets.QLabel("Timestamp crop X"), 0, 0)
        grid.addWidget(self.ts_x_spin, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Y"), 0, 2)
        grid.addWidget(self.ts_y_spin, 0, 3)
        grid.addWidget(QtWidgets.QLabel("Width"), 0, 4)
        grid.addWidget(self.ts_w_spin, 0, 5)
        grid.addWidget(QtWidgets.QLabel("Height"), 0, 6)
        grid.addWidget(self.ts_h_spin, 0, 7)

        grid.addWidget(QtWidgets.QLabel("Timestamp output width"), 1, 0)
        grid.addWidget(self.ts_overlay_w_spin, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Overlay X"), 1, 2)
        grid.addWidget(self.ts_overlay_x_spin, 1, 3)
        grid.addWidget(QtWidgets.QLabel("Overlay Y"), 1, 4)
        grid.addWidget(self.ts_overlay_y_spin, 1, 5)

        grid.addWidget(QtWidgets.QLabel("Dewarp interpolation"), 1, 6)
        self.interpolation_combo = QtWidgets.QComboBox()
        self.interpolation_combo.addItem("Cubic: balanced", "cubic")
        self.interpolation_combo.addItem("Linear: fastest", "linear")
        self.interpolation_combo.addItem("Lanczos: sharpest, slowest", "lanczos")
        self.interpolation_combo.currentIndexChanged.connect(self._render_setting_changed)
        grid.addWidget(self.interpolation_combo, 1, 7)
        return widget

    @staticmethod
    def _integer_spin(minimum: int, maximum: int, value: int) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    @staticmethod
    def _make_slider_row(
        minimum: float,
        maximum: float,
        step: float,
    ) -> tuple[QtWidgets.QSlider, QtWidgets.QDoubleSpinBox]:
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        multiplier = 10 if step < 1 else 1
        slider.setRange(int(minimum * multiplier), int(maximum * multiplier))
        slider.setSingleStep(max(1, int(step * multiplier)))

        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(1 if step < 1 else 0)
        spin.setSuffix("°")
        spin.setFixedWidth(90)
        return slider, spin

    # ------------------------------------------------------------------
    # FFmpeg discovery and media loading
    # ------------------------------------------------------------------

    def _restore_settings(self) -> None:
        saved_ffmpeg = self.settings.value("ffmpeg_path", "", str)
        self.ffmpeg_path, self.ffprobe_path = locate_ffmpeg(saved_ffmpeg or None)
        last_dir = self.settings.value("last_video_dir", "", str)
        if last_dir:
            self._last_video_dir = Path(last_dir)
        else:
            self._last_video_dir = Path.home() / "Downloads"

    def _resolve_ffmpeg(self) -> None:
        if self.ffmpeg_path is None:
            saved = self.settings.value("ffmpeg_path", "", str)
            self.ffmpeg_path, self.ffprobe_path = locate_ffmpeg(saved or None)

        if self.ffmpeg_path is None:
            self.ffmpeg_status.set_status("bad", "FFmpeg not found")
            self.nvenc_available = False
            self._update_encoder_availability()
            return

        # ffprobe is optional in the compact portable package. When it is not
        # present, the app reads the same media details from ffmpeg's input
        # summary instead.
        self.ffmpeg_status.set_status("neutral", "Checking video encoder…")
        self._ffmpeg_check_in_progress = True
        worker = FunctionWorker(detect_nvenc, self.ffmpeg_path)
        worker.signals.result.connect(self._nvenc_check_finished)
        worker.signals.error.connect(lambda _: self._nvenc_check_finished(False))
        worker.signals.finished.connect(lambda: setattr(self, "_ffmpeg_check_in_progress", False))
        self.thread_pool.start(worker)

    def _nvenc_check_finished(self, available: object) -> None:
        self.nvenc_available = bool(available)
        compact_suffix = " • compact package" if self.ffprobe_path is None else ""
        if self.nvenc_available:
            self.ffmpeg_status.set_status(
                "good",
                f"FFmpeg + NVIDIA NVENC ready{compact_suffix}",
            )
        else:
            self.ffmpeg_status.set_status(
                "warning",
                f"FFmpeg ready; CPU encoding only{compact_suffix}",
            )
        self._update_encoder_availability()

    def _update_encoder_availability(self) -> None:
        model = self.encoder_combo.model()
        item = model.item(1) if hasattr(model, "item") else None
        if item is not None:
            item.setEnabled(self.nvenc_available)
        if not self.nvenc_available and self.encoder_combo.currentData() == "nvenc":
            self.encoder_combo.setCurrentIndex(0)

    def _choose_ffmpeg(self) -> None:
        start = str(self.ffmpeg_path.parent if self.ffmpeg_path else Path.home())
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose ffmpeg.exe",
            start,
            "FFmpeg executable (ffmpeg.exe);;All files (*)",
        )
        if not filename:
            return
        selected = Path(filename)
        if selected.name.lower() != "ffmpeg.exe":
            self._show_error("Choose the file named ffmpeg.exe.")
            return
        self.settings.setValue("ffmpeg_path", str(selected))
        self.ffmpeg_path, self.ffprobe_path = locate_ffmpeg(str(selected))
        self._resolve_ffmpeg()

    def _choose_video(self) -> None:
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose fisheye video",
            str(self._last_video_dir),
            "Video files (*.mp4 *.mov *.mkv *.avi *.m4v *.ts *.mts *.m2ts);;All files (*)",
        )
        if filename:
            self._load_video(Path(filename))

    def _load_video(self, path: Path) -> None:
        path = path.expanduser().resolve()
        if not path.is_file():
            self._show_error(f"The selected video does not exist:\n{path}")
            return
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            response = QtWidgets.QMessageBox.question(
                self,
                "Unrecognized extension",
                "This file does not have a common video extension. Try to open it anyway?",
            )
            if response != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        if self.ffmpeg_path is None:
            self._show_error(
                "FFmpeg is required. Click Choose FFmpeg and select ffmpeg.exe."
            )
            return

        self.input_path = path
        self._last_video_dir = path.parent
        self.settings.setValue("last_video_dir", str(path.parent))
        self.output_dir = path.parent / f"Converted Views - {path.stem}"
        self.output_edit.setText(str(self.output_dir))
        self.file_path_label.setText(str(path))
        self.media_details_label.setText("Reading video information…")
        self._loading_media = True
        self.render_button.setEnabled(False)
        self.source_pixmap = QtGui.QPixmap()
        self.overlay.set_source_pixmap(self.source_pixmap)
        self.preview_pixmaps.clear()
        self._rebuild_preview_cards()

        worker = FunctionWorker(probe_media, self.ffmpeg_path, path, self.ffprobe_path)
        worker.signals.result.connect(self._media_probe_finished)
        worker.signals.error.connect(self._media_probe_failed)
        worker.signals.finished.connect(self._media_probe_worker_finished)
        self.thread_pool.start(worker)

    def _media_probe_finished(self, result: object) -> None:
        if not isinstance(result, MediaInfo):
            self._media_probe_failed("Unexpected media information result.")
            return
        self.media_info = result
        fps_text = f"{result.fps:.2f} fps" if result.fps > 0 else "frame rate unknown"
        audio_text = "audio" if result.has_audio else "no audio"
        self.media_details_label.setText(
            f"{result.resolution_text}   •   {result.duration_text}   •   {fps_text}   •   {audio_text}"
        )
        self.preview_time_spin.setRange(0.0, max(0.0, result.duration_seconds - 0.1))
        self.preview_time_spin.setValue(0.0)

        self.timestamp_settings.crop_width = min(700, result.width)
        self.timestamp_settings.crop_height = min(55, result.height)
        self.timestamp_settings.overlay_width = min(700, self.render_settings.output_width)
        self._sync_timestamp_controls()
        self.overlay.set_timestamp_settings(self.timestamp_settings)
        self._update_estimate()
        self._extract_source_frame()

    def _media_probe_failed(self, message: str) -> None:
        self.media_info = None
        self.media_details_label.setText("Could not read the selected video")
        self._show_error(message)

    def _media_probe_worker_finished(self) -> None:
        self._loading_media = False
        self.render_button.setEnabled(True)

    def _extract_source_frame(self) -> None:
        if self.input_path is None or self.ffmpeg_path is None:
            return
        if self.frame_process.state() != QtCore.QProcess.ProcessState.NotRunning:
            self.frame_process.kill()
            self.frame_process.waitForFinished(1000)

        frame_path = self.temp_path / "source-frame.png"
        try:
            frame_path.unlink(missing_ok=True)
        except OSError:
            pass

        self.overlay.setEnabled(False)
        self.media_details_label.setText("Extracting preview frame…")
        args = build_extract_frame_args(
            self.input_path,
            frame_path,
            self.preview_time_spin.value(),
        )
        self.frame_process.setProperty("output_path", str(frame_path))
        self.frame_process.start(str(self.ffmpeg_path), args)

    def _frame_process_finished(self, exit_code: int, exit_status: QtCore.QProcess.ExitStatus) -> None:
        self.overlay.setEnabled(True)
        output_path = Path(str(self.frame_process.property("output_path") or ""))
        output_text = bytes(self.frame_process.readAllStandardOutput()).decode("utf-8", errors="replace")

        if exit_status != QtCore.QProcess.ExitStatus.NormalExit or exit_code != 0 or not output_path.is_file():
            self._show_error(output_text.strip() or "FFmpeg could not extract the preview frame.")
            return

        pixmap = QtGui.QPixmap(str(output_path))
        if pixmap.isNull():
            self._show_error("The preview frame was created but could not be displayed.")
            return

        self.source_pixmap = pixmap
        self.overlay.set_source_pixmap(pixmap)
        self.overlay.set_views(self.views, self.selected_index)
        self.overlay.set_timestamp_settings(self.timestamp_settings)
        if self.media_info:
            fps_text = f"{self.media_info.fps:.2f} fps" if self.media_info.fps > 0 else "frame rate unknown"
            audio_text = "audio" if self.media_info.has_audio else "no audio"
            self.media_details_label.setText(
                f"{self.media_info.resolution_text}   •   {self.media_info.duration_text}   •   "
                f"{fps_text}   •   {audio_text}"
            )
        self._queue_all_previews()

    # ------------------------------------------------------------------
    # View editing
    # ------------------------------------------------------------------

    def _rebuild_view_list(self) -> None:
        self.view_list.blockSignals(True)
        self.view_list.clear()
        for index, view in enumerate(self.views):
            item = QtWidgets.QListWidgetItem(f"{index + 1}. {view.name}")
            if not view.enabled:
                item.setForeground(QtGui.QColor("#667A91"))
            item.setToolTip(f"Roll {view.roll:.1f}°, pitch {view.pitch:.1f}°")
            self.view_list.addItem(item)
        self.view_list.blockSignals(False)
        if self.views:
            self.view_list.setCurrentRow(max(0, min(self.selected_index, len(self.views) - 1)))

    def _rebuild_preview_cards(self) -> None:
        while self.preview_grid.count():
            item = self.preview_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.preview_cards = []
        for index, view in enumerate(self.views):
            card = PreviewCard(index, view)
            card.clicked.connect(self._select_view)
            card.enabled_changed.connect(self._preview_enabled_changed)
            pixmap = self.preview_pixmaps.get(view.uid)
            if pixmap is not None:
                card.set_preview(pixmap)
            card.set_selected(index == self.selected_index)
            self.preview_grid.addWidget(card, index // 2, index % 2)
            self.preview_cards.append(card)

        self.preview_grid.setRowStretch((len(self.views) + 1) // 2, 1)

    def _select_view(self, index: int) -> None:
        if index < 0 or index >= len(self.views):
            return
        self.selected_index = index
        self.view_list.blockSignals(True)
        self.view_list.setCurrentRow(index)
        self.view_list.blockSignals(False)
        self.overlay.set_selected_index(index)
        for card_index, card in enumerate(self.preview_cards):
            card.set_selected(card_index == index)
        self._load_view_controls()

    def _view_list_changed(self, row: int) -> None:
        if row >= 0:
            self._select_view(row)

    def _overlay_view_selected(self, index: int) -> None:
        self._select_view(index)
        self._load_view_controls()
        self._update_view_display(index)

    def _overlay_view_changed(self, index: int) -> None:
        self._select_view(index)
        self._update_view_display(index)
        self._schedule_preview(index)

    def _load_view_controls(self) -> None:
        if not self.views or self.selected_index >= len(self.views):
            return
        view = self.views[self.selected_index]
        self._updating_controls = True
        try:
            self.view_name_edit.setText(view.name)
            self.view_enabled_box.setChecked(view.enabled)
            self.roll_spin.setValue(view.roll)
            self.roll_slider.setValue(int(round(view.roll * 10)))
            self.pitch_spin.setValue(view.pitch)
            self.pitch_slider.setValue(int(round(view.pitch * 10)))
            self.hfov_spin.setValue(view.h_fov)
            self.hfov_slider.setValue(int(round(view.h_fov)))
            self.vfov_spin.setValue(view.v_fov)
            self.vfov_slider.setValue(int(round(view.v_fov)))
        finally:
            self._updating_controls = False

    def _slider_changed(self, field_name: str, value: float) -> None:
        if self._updating_controls or not self.views:
            return
        self._updating_controls = True
        try:
            if field_name == "roll":
                self.roll_spin.setValue(value)
            elif field_name == "pitch":
                self.pitch_spin.setValue(value)
            elif field_name == "h_fov":
                self.hfov_spin.setValue(value)
            elif field_name == "v_fov":
                self.vfov_spin.setValue(value)
        finally:
            self._updating_controls = False
        self._apply_view_value(field_name, value)

    def _spin_changed(self, field_name: str, value: float) -> None:
        if self._updating_controls or not self.views:
            return
        self._updating_controls = True
        try:
            if field_name == "roll":
                self.roll_slider.setValue(int(round(value * 10)))
            elif field_name == "pitch":
                self.pitch_slider.setValue(int(round(value * 10)))
            elif field_name == "h_fov":
                self.hfov_slider.setValue(int(round(value)))
            elif field_name == "v_fov":
                self.vfov_slider.setValue(int(round(value)))
        finally:
            self._updating_controls = False
        self._apply_view_value(field_name, value)

    def _apply_view_value(self, field_name: str, value: float) -> None:
        if self.selected_index < 0 or self.selected_index >= len(self.views):
            return
        view = self.views[self.selected_index]
        setattr(view, field_name, float(value))
        view.clamp()
        self._update_view_display(self.selected_index)
        self._schedule_preview(self.selected_index)

    def _view_name_changed(self) -> None:
        if self._updating_controls or not self.views:
            return
        name = self.view_name_edit.text().strip() or f"View {self.selected_index + 1}"
        self.views[self.selected_index].name = name
        self._rebuild_view_list()
        self._rebuild_preview_cards()
        self._select_view(self.selected_index)

    def _view_enabled_changed(self, enabled: bool) -> None:
        if self._updating_controls or not self.views:
            return
        self.views[self.selected_index].enabled = enabled
        self._update_view_display(self.selected_index)
        self._rebuild_view_list()
        self._update_estimate()

    def _preview_enabled_changed(self, index: int, enabled: bool) -> None:
        if index < 0 or index >= len(self.views):
            return
        self.views[index].enabled = enabled
        if index == self.selected_index:
            self._updating_controls = True
            self.view_enabled_box.setChecked(enabled)
            self._updating_controls = False
        self._update_view_display(index)
        self._rebuild_view_list()
        self._update_estimate()

    def _update_view_display(self, index: int) -> None:
        self.overlay.set_views(self.views, self.selected_index)
        if 0 <= index < len(self.preview_cards):
            self.preview_cards[index].update_view(self.views[index])
        if 0 <= index < self.view_list.count():
            item = self.view_list.item(index)
            item.setText(f"{index + 1}. {self.views[index].name}")
            item.setToolTip(f"Roll {self.views[index].roll:.1f}°, pitch {self.views[index].pitch:.1f}°")
            item.setForeground(
                QtGui.QColor("#E8EEF7") if self.views[index].enabled else QtGui.QColor("#667A91")
            )

    def _add_view(self) -> None:
        if len(self.views) >= self.MAX_VIEWS:
            self._show_error(f"The app supports up to {self.MAX_VIEWS} views in one render.")
            return
        if self.views:
            base = self.views[self.selected_index]
            roll = base.roll + 45.0
            pitch = base.pitch
        else:
            roll, pitch = 0.0, 55.0
        self._add_view_at(roll, pitch)

    def _add_view_at(self, roll: float, pitch: float) -> None:
        if len(self.views) >= self.MAX_VIEWS:
            self._show_error(f"The app supports up to {self.MAX_VIEWS} views in one render.")
            return
        index = len(self.views)
        view = ViewDefinition(
            name=f"Custom {index + 1}",
            roll=roll,
            pitch=pitch,
            h_fov=100.0,
            v_fov=70.0,
            color=VIEW_COLORS[index % len(VIEW_COLORS)],
        )
        view.clamp()
        self.views.append(view)
        self.selected_index = len(self.views) - 1
        self._rebuild_view_list()
        self._rebuild_preview_cards()
        self.overlay.set_views(self.views, self.selected_index)
        self._select_view(self.selected_index)
        self._schedule_preview(self.selected_index)
        self._update_estimate()

    def _duplicate_view(self) -> None:
        if not self.views:
            return
        if len(self.views) >= self.MAX_VIEWS:
            self._show_error(f"The app supports up to {self.MAX_VIEWS} views in one render.")
            return
        original = self.views[self.selected_index]
        index = len(self.views)
        duplicate = ViewDefinition(
            name=f"{original.name} copy",
            roll=original.roll,
            pitch=original.pitch,
            h_fov=original.h_fov,
            v_fov=original.v_fov,
            enabled=original.enabled,
            color=VIEW_COLORS[index % len(VIEW_COLORS)],
        )
        self.views.append(duplicate)
        self.selected_index = len(self.views) - 1
        self._rebuild_view_list()
        self._rebuild_preview_cards()
        self.overlay.set_views(self.views, self.selected_index)
        self._select_view(self.selected_index)
        self._schedule_preview(self.selected_index)
        self._update_estimate()

    def _delete_view(self) -> None:
        if not self.views:
            return
        if len(self.views) == 1:
            self._show_error("Keep at least one view.")
            return
        removed = self.views.pop(self.selected_index)
        self.preview_pixmaps.pop(removed.uid, None)
        self.selected_index = min(self.selected_index, len(self.views) - 1)
        self._rebuild_view_list()
        self._rebuild_preview_cards()
        self.overlay.set_views(self.views, self.selected_index)
        self._select_view(self.selected_index)
        self._update_estimate()

    def _reset_views(self) -> None:
        response = QtWidgets.QMessageBox.question(
            self,
            "Reset views",
            "Replace the current layout with the standard top, right, bottom, left, and center views?",
        )
        if response != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.views = default_views()
        self.selected_index = 0
        self.preview_pixmaps.clear()
        self._rebuild_view_list()
        self._rebuild_preview_cards()
        self.overlay.set_views(self.views, self.selected_index)
        self._select_view(0)
        self._queue_all_previews()
        self._update_estimate()

    # ------------------------------------------------------------------
    # Preview generation
    # ------------------------------------------------------------------

    def _schedule_preview(self, index: int) -> None:
        if index != self.selected_index:
            self.selected_index = index
        self.preview_debounce.start()

    def _refresh_selected_preview_now(self) -> None:
        if not self.views:
            return
        self._queue_previews([self.selected_index], replace_queue=True)

    def _queue_all_previews(self) -> None:
        self._queue_previews(range(len(self.views)), replace_queue=True)

    def _queue_previews(self, indices: Iterable[int], replace_queue: bool) -> None:
        if self.input_path is None or self.ffmpeg_path is None or self.source_pixmap.isNull():
            return
        valid = [index for index in indices if 0 <= index < len(self.views)]
        if not valid:
            return

        if replace_queue:
            self.preview_queue.clear()
            if self.preview_process.state() != QtCore.QProcess.ProcessState.NotRunning:
                self.preview_process.kill()
                self.preview_process.waitForFinished(500)
        for index in valid:
            if index not in self.preview_queue:
                self.preview_queue.append(index)
            if index < len(self.preview_cards):
                self.preview_cards[index].set_loading(True)

        if self.preview_process.state() == QtCore.QProcess.ProcessState.NotRunning:
            self._start_next_preview()

    def _start_next_preview(self) -> None:
        if not self.preview_queue or self.input_path is None or self.ffmpeg_path is None:
            self.current_preview_index = -1
            return
        index = self.preview_queue.popleft()
        if index < 0 or index >= len(self.views):
            self._start_next_preview()
            return

        self.current_preview_index = index
        view = self.views[index]
        output_path = self.temp_path / f"preview-{view.uid}.png"
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass

        self._sync_render_settings()
        self._sync_timestamp_settings()
        args = build_preview_args(
            input_path=self.input_path,
            output_path=output_path,
            view=view,
            timestamp=self.timestamp_settings,
            render=self.render_settings,
            timestamp_seconds=self.preview_time_spin.value(),
        )
        self.preview_process.setProperty("output_path", str(output_path))
        self.preview_process.setProperty("view_uid", view.uid)
        self.preview_process.start(str(self.ffmpeg_path), args)

    def _preview_process_finished(self, exit_code: int, exit_status: QtCore.QProcess.ExitStatus) -> None:
        index = self.current_preview_index
        output_path = Path(str(self.preview_process.property("output_path") or ""))
        view_uid = str(self.preview_process.property("view_uid") or "")
        message = bytes(self.preview_process.readAllStandardOutput()).decode("utf-8", errors="replace")

        if (
            exit_status == QtCore.QProcess.ExitStatus.NormalExit
            and exit_code == 0
            and output_path.is_file()
        ):
            pixmap = QtGui.QPixmap(str(output_path))
            if not pixmap.isNull():
                self.preview_pixmaps[view_uid] = pixmap
                if 0 <= index < len(self.preview_cards):
                    self.preview_cards[index].set_preview(pixmap)
            elif 0 <= index < len(self.preview_cards):
                self.preview_cards[index].set_preview(None)
        else:
            if 0 <= index < len(self.preview_cards):
                self.preview_cards[index].set_preview(None)
            if message.strip() and "killed" not in message.lower():
                self._append_log(f"Preview {index + 1} failed:\n{message.strip()}\n")

        self.current_preview_index = -1
        self._start_next_preview()

    # ------------------------------------------------------------------
    # Layout profiles
    # ------------------------------------------------------------------

    def _save_layout(self) -> None:
        self._sync_render_settings()
        self._sync_timestamp_settings()
        start = str(self.input_path.parent if self.input_path else self._last_video_dir)
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save fisheye layout",
            str(Path(start) / "fisheye-layout.json"),
            "Fisheye layout (*.json)",
        )
        if not filename:
            return
        payload = {
            "format": "FisheyeViewStudioLayout",
            "version": 1,
            "views": [view.to_dict() for view in self.views],
            "timestamp": self.timestamp_settings.to_dict(),
            "render": self.render_settings.to_dict(),
        }
        try:
            Path(filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            self._show_error(f"Could not save the layout:\n{exc}")

    def _load_layout(self) -> None:
        start = str(self.input_path.parent if self.input_path else self._last_video_dir)
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load fisheye layout",
            start,
            "Fisheye layout (*.json);;All files (*)",
        )
        if not filename:
            return
        try:
            payload = json.loads(Path(filename).read_text(encoding="utf-8"))
            loaded_views = [ViewDefinition.from_dict(item) for item in payload.get("views", [])]
            if not loaded_views:
                raise ValueError("The layout does not contain any views.")
            if len(loaded_views) > self.MAX_VIEWS:
                loaded_views = loaded_views[: self.MAX_VIEWS]
            self.views = loaded_views
            self.timestamp_settings = TimestampSettings.from_dict(payload.get("timestamp", {}))
            self.render_settings = RenderSettings.from_dict(payload.get("render", {}))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._show_error(f"Could not load the layout:\n{exc}")
            return

        self.selected_index = 0
        self.preview_pixmaps.clear()
        self._rebuild_view_list()
        self._rebuild_preview_cards()
        self._load_render_settings_into_controls()
        self._sync_timestamp_controls()
        self.overlay.set_timestamp_settings(self.timestamp_settings)
        self.overlay.set_views(self.views, self.selected_index)
        self._select_view(0)
        self._queue_all_previews()
        self._update_estimate()

    # ------------------------------------------------------------------
    # Timestamp and render controls
    # ------------------------------------------------------------------

    def _timestamp_enabled_changed(self, enabled: bool) -> None:
        self.timestamp_settings.enabled = enabled
        self.advanced_widget.setEnabled(enabled)
        self.overlay.set_timestamp_settings(self.timestamp_settings)
        self._queue_all_previews()

    def _timestamp_setting_changed(self) -> None:
        if self._updating_controls:
            return
        self._sync_timestamp_settings()
        self.overlay.set_timestamp_settings(self.timestamp_settings)
        self.preview_debounce.start()

    def _sync_timestamp_settings(self) -> None:
        self.timestamp_settings.enabled = self.timestamp_box.isChecked()
        self.timestamp_settings.crop_x = self.ts_x_spin.value()
        self.timestamp_settings.crop_y = self.ts_y_spin.value()
        self.timestamp_settings.crop_width = self.ts_w_spin.value()
        self.timestamp_settings.crop_height = self.ts_h_spin.value()
        self.timestamp_settings.overlay_width = self.ts_overlay_w_spin.value()
        self.timestamp_settings.overlay_x = self.ts_overlay_x_spin.value()
        self.timestamp_settings.overlay_y = self.ts_overlay_y_spin.value()

    def _sync_timestamp_controls(self) -> None:
        self._updating_controls = True
        try:
            self.timestamp_box.setChecked(self.timestamp_settings.enabled)
            self.ts_x_spin.setValue(self.timestamp_settings.crop_x)
            self.ts_y_spin.setValue(self.timestamp_settings.crop_y)
            self.ts_w_spin.setValue(self.timestamp_settings.crop_width)
            self.ts_h_spin.setValue(self.timestamp_settings.crop_height)
            self.ts_overlay_w_spin.setValue(self.timestamp_settings.overlay_width)
            self.ts_overlay_x_spin.setValue(self.timestamp_settings.overlay_x)
            self.ts_overlay_y_spin.setValue(self.timestamp_settings.overlay_y)
        finally:
            self._updating_controls = False
        self.advanced_widget.setEnabled(self.timestamp_settings.enabled)

    def _render_setting_changed(self) -> None:
        if self._updating_controls:
            return
        self._sync_render_settings()
        self._update_estimate()
        if self.input_path and not self.source_pixmap.isNull():
            self.preview_debounce.start()

    def _sync_render_settings(self) -> None:
        self.render_settings.output_width = 1920
        self.render_settings.output_height = 1080
        self.render_settings.bitrate_kbps = self.bitrate_spin.value()
        self.render_settings.maxrate_kbps = max(
            self.render_settings.bitrate_kbps,
            int(round(self.render_settings.bitrate_kbps * 1.67)),
        )
        self.render_settings.buffer_kbps = self.render_settings.bitrate_kbps * 4
        self.render_settings.encoder_mode = str(self.encoder_combo.currentData() or "auto")
        self.render_settings.interpolation = str(self.interpolation_combo.currentData() or "cubic")
        self.render_settings.test_seconds = 20 if self.test_box.isChecked() else 0

    def _load_render_settings_into_controls(self) -> None:
        self._updating_controls = True
        try:
            self.bitrate_spin.setValue(self.render_settings.bitrate_kbps)
            encoder_index = self.encoder_combo.findData(self.render_settings.encoder_mode)
            self.encoder_combo.setCurrentIndex(max(0, encoder_index))
            interpolation_index = self.interpolation_combo.findData(self.render_settings.interpolation)
            self.interpolation_combo.setCurrentIndex(max(0, interpolation_index))
            self.test_box.setChecked(self.render_settings.test_seconds > 0)
        finally:
            self._updating_controls = False

    def _toggle_advanced(self, visible: bool) -> None:
        self.advanced_widget.setVisible(visible)
        self.advanced_button.setArrowType(
            QtCore.Qt.ArrowType.DownArrow if visible else QtCore.Qt.ArrowType.RightArrow
        )
        self.advanced_button.setText(
            "Hide timestamp and quality settings" if visible else "Show timestamp and quality settings"
        )

    def _toggle_log(self, visible: bool) -> None:
        self.log_edit.setVisible(visible)
        self.log_button.setText("Hide log" if visible else "Show log")

    def _choose_output_dir(self) -> None:
        start = self.output_edit.text().strip() or str(self._last_video_dir)
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder", start)
        if directory:
            self.output_edit.setText(directory)

    def _output_path_changed(self, text: str) -> None:
        self.output_dir = Path(text).expanduser() if text.strip() else None

    def _update_estimate(self) -> None:
        self._sync_render_settings()
        active_count = sum(1 for view in self.views if view.enabled)
        if self.media_info is None:
            self.estimate_label.setText(f"{active_count} enabled view(s) at 1080p / {self.render_settings.bitrate_kbps} kbps")
            return
        per_view, total = estimate_output_bytes(
            self.media_info.duration_seconds,
            active_count,
            self.render_settings,
            self.media_info.has_audio,
        )
        test_text = " for the 20-second test" if self.render_settings.test_seconds > 0 else ""
        self.estimate_label.setText(
            f"Estimated{test_text}: {human_size(per_view)} per view, {human_size(total)} total "
            f"for {active_count} enabled view(s)"
        )

    # ------------------------------------------------------------------
    # Final rendering
    # ------------------------------------------------------------------

    def _start_render(self) -> None:
        if self._processing:
            return
        if self.input_path is None or self.media_info is None:
            self._show_error("Choose a video before rendering.")
            return
        if self.ffmpeg_path is None:
            self._show_error("FFmpeg is not configured.")
            return

        self._sync_render_settings()
        self._sync_timestamp_settings()
        active_views = [view for view in self.views if view.enabled]
        if not active_views:
            self._show_error("Enable at least one view.")
            return

        output_text = self.output_edit.text().strip()
        if not output_text:
            self._show_error("Choose an output folder.")
            return
        output_dir = Path(output_text).expanduser()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._show_error(f"The output folder could not be created:\n{exc}")
            return

        encoder_mode = self.render_settings.encoder_mode
        if encoder_mode == "nvenc" and not self.nvenc_available:
            self._show_error("NVIDIA NVENC was selected, but this FFmpeg installation does not expose h264_nvenc.")
            return
        use_nvenc = self.nvenc_available if encoder_mode == "auto" else encoder_mode == "nvenc"

        try:
            args, output_files = build_render_command(
                input_path=self.input_path,
                output_dir=output_dir,
                views=self.views,
                timestamp=self.timestamp_settings,
                render=self.render_settings,
                use_nvenc=use_nvenc,
            )
        except (ValueError, OSError) as exc:
            self._show_error(str(exc))
            return

        existing = [path for path in output_files if path.exists()]
        if existing:
            response = QtWidgets.QMessageBox.question(
                self,
                "Overwrite existing files",
                f"{len(existing)} output file(s) already exist. Overwrite them?",
            )
            if response != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        self.output_dir = output_dir
        self._processing = True
        self._cancel_requested = False
        self.render_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        encoder_label = "NVIDIA NVENC" if use_nvenc else "CPU libx264"
        self.progress_bar.setFormat(f"Starting {encoder_label} render…")
        self.log_edit.clear()
        self._append_log(f"FFmpeg: {self.ffmpeg_path}\n")
        self._append_log(f"Input: {self.input_path}\n")
        self._append_log(f"Output: {output_dir}\n")
        self._append_log(f"Encoder: {encoder_label}\n")
        self._append_log(f"Views: {len(active_views)}\n\n")

        self.render_process.start(str(self.ffmpeg_path), args)

    def _read_render_output(self) -> None:
        raw = bytes(self.render_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not raw:
            return
        self._append_log(raw)

        duration = self.render_settings.test_seconds or (self.media_info.duration_seconds if self.media_info else 0)
        if duration <= 0:
            return

        for line in raw.replace("\r", "\n").splitlines():
            if line.startswith("out_time_us="):
                try:
                    elapsed = int(line.split("=", 1)[1]) / 1_000_000
                except (ValueError, IndexError):
                    continue
                self._set_render_progress(elapsed, duration)
            elif line.startswith("out_time_ms="):
                try:
                    elapsed = int(line.split("=", 1)[1]) / 1_000_000
                except (ValueError, IndexError):
                    continue
                self._set_render_progress(elapsed, duration)

    def _set_render_progress(self, elapsed: float, duration: float) -> None:
        fraction = max(0.0, min(1.0, elapsed / max(duration, 0.001)))
        self.progress_bar.setValue(int(round(fraction * 1000)))
        elapsed_int = int(elapsed)
        duration_int = int(duration)
        self.progress_bar.setFormat(
            f"Rendering {elapsed_int // 60}:{elapsed_int % 60:02d} / "
            f"{duration_int // 60}:{duration_int % 60:02d}   {fraction * 100:.1f}%"
        )

    def _cancel_render(self) -> None:
        if self.render_process.state() == QtCore.QProcess.ProcessState.NotRunning:
            return
        self._cancel_requested = True
        self.progress_bar.setFormat("Stopping FFmpeg…")
        self.render_process.kill()

    def _render_finished(self, exit_code: int, exit_status: QtCore.QProcess.ExitStatus) -> None:
        remaining = bytes(self.render_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if remaining:
            self._append_log(remaining)
        self._processing = False
        self.render_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        if self._cancel_requested:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Render canceled")
            return

        if exit_status == QtCore.QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.progress_bar.setValue(1000)
            self.progress_bar.setFormat("Completed successfully")
            self._open_output_folder()
            QtWidgets.QMessageBox.information(
                self,
                "Render complete",
                f"The enabled views were saved to:\n{self.output_dir}",
            )
        else:
            self.progress_bar.setFormat("FFmpeg failed. Open the log for details.")
            self.log_edit.setVisible(True)
            self.log_button.setChecked(True)
            self._show_error("FFmpeg did not complete successfully. Review the log at the bottom of the app.")

    def _append_log(self, text: str) -> None:
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.log_edit.setTextCursor(cursor)
        self.log_edit.ensureCursorVisible()

    def _open_output_folder(self) -> None:
        path_text = self.output_edit.text().strip()
        if not path_text:
            return
        path = Path(path_text).expanduser()
        if not path.exists():
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------
    # General helpers and events
    # ------------------------------------------------------------------

    def _show_error(self, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Fisheye View Studio", message)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if any(url.isLocalFile() for url in urls):
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_file():
                    self._load_video(path)
                    event.acceptProposedAction()
                    return

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if self._processing:
            response = QtWidgets.QMessageBox.question(
                self,
                "Rendering is still running",
                "Stop FFmpeg and close the app?",
            )
            if response != QtWidgets.QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.render_process.kill()
            self.render_process.waitForFinished(1500)

        for process in (self.frame_process, self.preview_process):
            if process.state() != QtCore.QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(500)

        self.settings.setValue("ffmpeg_path", str(self.ffmpeg_path or ""))
        self.settings.setValue("last_video_dir", str(self._last_video_dir))
        self.temp_dir.cleanup()
        event.accept()
