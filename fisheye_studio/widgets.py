from __future__ import annotations

from pathlib import Path
from typing import Sequence
import math

from PySide6 import QtCore, QtGui, QtWidgets

from .models import (
    TimestampSettings,
    ViewDefinition,
    normalized_to_roll_pitch,
    roll_pitch_to_normalized,
)


class FisheyeOverlayWidget(QtWidgets.QWidget):
    view_selected = QtCore.Signal(int)
    view_changed = QtCore.Signal(int)
    create_view_requested = QtCore.Signal(float, float)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 500)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)

        self._pixmap = QtGui.QPixmap()
        self._views: list[ViewDefinition] = []
        self._selected_index = -1
        self._dragging_index = -1
        self._timestamp = TimestampSettings()
        self._hover_index = -1

    def set_source_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def set_views(self, views: Sequence[ViewDefinition], selected_index: int = -1) -> None:
        self._views = list(views)
        self._selected_index = selected_index
        self.update()

    def set_selected_index(self, index: int) -> None:
        self._selected_index = index
        self.update()

    def set_timestamp_settings(self, settings: TimestampSettings) -> None:
        self._timestamp = settings
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QtGui.QColor("#07111F"))

        if self._pixmap.isNull():
            self._draw_empty_state(painter)
            return

        image_rect = self._image_rect()
        painter.drawPixmap(image_rect.toRect(), self._pixmap)

        crop_rect = self._crop_square_rect(image_rect)
        circle_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 105), 1.5, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(circle_pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(crop_rect)

        self._draw_timestamp_rect(painter, image_rect)

        center = crop_rect.center()
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 85), 1))
        painter.drawLine(QtCore.QPointF(center.x() - 8, center.y()), QtCore.QPointF(center.x() + 8, center.y()))
        painter.drawLine(QtCore.QPointF(center.x(), center.y() - 8), QtCore.QPointF(center.x(), center.y() + 8))

        for index, view in enumerate(self._views):
            self._draw_view_box(painter, crop_rect, index, view)

        hint = "Drag a box to aim it. Double-click anywhere in the circle to add a view."
        hint_rect = QtCore.QRectF(image_rect.left() + 14, image_rect.bottom() - 42, image_rect.width() - 28, 30)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(5, 12, 24, 205))
        painter.drawRoundedRect(hint_rect, 9, 9)
        painter.setPen(QtGui.QColor("#D7E4F5"))
        font = painter.font()
        font.setPointSizeF(9.0)
        painter.setFont(font)
        painter.drawText(hint_rect, QtCore.Qt.AlignmentFlag.AlignCenter, hint)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() != QtCore.Qt.MouseButton.LeftButton or self._pixmap.isNull():
            return super().mousePressEvent(event)

        index = self._hit_test_view(event.position())
        if index >= 0:
            self._selected_index = index
            self._dragging_index = index
            self.view_selected.emit(index)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            self.update()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._dragging_index >= 0 and self._dragging_index < len(self._views):
            roll, pitch = self._point_to_roll_pitch(event.position())
            view = self._views[self._dragging_index]
            view.roll = roll
            view.pitch = pitch
            view.clamp()
            self.view_selected.emit(self._dragging_index)
            self.update()
            event.accept()
            return

        hover_index = self._hit_test_view(event.position())
        if hover_index != self._hover_index:
            self._hover_index = hover_index
            self.setCursor(
                QtCore.Qt.CursorShape.OpenHandCursor
                if hover_index >= 0
                else QtCore.Qt.CursorShape.CrossCursor
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._dragging_index >= 0:
            index = self._dragging_index
            self._dragging_index = -1
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            self.view_changed.emit(index)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton and not self._pixmap.isNull():
            if self._point_inside_crop_circle(event.position()):
                roll, pitch = self._point_to_roll_pitch(event.position())
                self.create_view_requested.emit(roll, pitch)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # noqa: N802
        self._hover_index = -1
        if self._dragging_index < 0:
            self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        super().leaveEvent(event)

    def _draw_empty_state(self, painter: QtGui.QPainter) -> None:
        painter.setPen(QtGui.QColor("#A8BAD0"))
        title_font = painter.font()
        title_font.setPointSizeF(16)
        title_font.setBold(True)
        painter.setFont(title_font)
        title_rect = QtCore.QRectF(20, self.height() / 2 - 45, self.width() - 40, 35)
        painter.drawText(title_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "Choose a fisheye video")

        body_font = painter.font()
        body_font.setPointSizeF(10)
        body_font.setBold(False)
        painter.setFont(body_font)
        body_rect = QtCore.QRectF(40, self.height() / 2, self.width() - 80, 60)
        painter.drawText(
            body_rect,
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop,
            "The first frame and draggable view partitions will appear here.",
        )

    def _draw_timestamp_rect(self, painter: QtGui.QPainter, image_rect: QtCore.QRectF) -> None:
        if not self._timestamp.enabled or self._pixmap.isNull():
            return

        scale_x = image_rect.width() / self._pixmap.width()
        scale_y = image_rect.height() / self._pixmap.height()
        rect = QtCore.QRectF(
            image_rect.left() + self._timestamp.crop_x * scale_x,
            image_rect.top() + self._timestamp.crop_y * scale_y,
            self._timestamp.crop_width * scale_x,
            self._timestamp.crop_height * scale_y,
        ).intersected(image_rect)

        if rect.isEmpty():
            return

        painter.setPen(QtGui.QPen(QtGui.QColor("#FACC15"), 2, QtCore.Qt.PenStyle.DashLine))
        painter.setBrush(QtGui.QColor(250, 204, 21, 24))
        painter.drawRoundedRect(rect, 4, 4)

        label_rect = QtCore.QRectF(rect.left() + 4, rect.bottom() + 3, 130, 22)
        if label_rect.bottom() > image_rect.bottom():
            label_rect.moveBottom(rect.top() - 3)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(20, 22, 27, 220))
        painter.drawRoundedRect(label_rect, 5, 5)
        painter.setPen(QtGui.QColor("#FDE68A"))
        font = painter.font()
        font.setPointSizeF(8.5)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(label_rect.adjusted(6, 0, -4, 0), QtCore.Qt.AlignmentFlag.AlignVCenter, "Timestamp source")

    def _draw_view_box(
        self,
        painter: QtGui.QPainter,
        crop_rect: QtCore.QRectF,
        index: int,
        view: ViewDefinition,
    ) -> None:
        x_norm, y_norm = roll_pitch_to_normalized(view.roll, view.pitch)
        center = QtCore.QPointF(
            crop_rect.left() + x_norm * crop_rect.width(),
            crop_rect.top() + y_norm * crop_rect.height(),
        )

        side = crop_rect.width()
        box_width = max(68.0, min(190.0, side * (view.h_fov / 360.0) * 0.62))
        box_height = max(46.0, min(120.0, side * (view.v_fov / 180.0) * 0.34))
        is_selected = index == self._selected_index
        is_hover = index == self._hover_index

        color = QtGui.QColor(view.color)
        if not color.isValid():
            color = QtGui.QColor("#38BDF8")

        if is_selected:
            painter.setPen(QtGui.QPen(QtGui.QColor(color).lighter(145), 1.5))
            painter.drawLine(crop_rect.center(), center)

        painter.save()
        painter.translate(center)
        painter.rotate(view.roll)
        box_rect = QtCore.QRectF(-box_width / 2, -box_height / 2, box_width, box_height)

        fill_alpha = 82 if is_selected else 46 if view.enabled else 20
        border_width = 3.2 if is_selected else 2.0
        if is_hover and not is_selected:
            border_width = 2.8

        fill = QtGui.QColor(color)
        fill.setAlpha(fill_alpha)
        painter.setBrush(fill)
        painter.setPen(QtGui.QPen(color, border_width))
        painter.drawRoundedRect(box_rect, 10, 10)

        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 215), 1.2))
        painter.drawLine(QtCore.QPointF(-9, 0), QtCore.QPointF(9, 0))
        painter.drawLine(QtCore.QPointF(0, -9), QtCore.QPointF(0, 9))
        painter.restore()

        text = f"{index + 1}. {view.name}"
        metrics = QtGui.QFontMetrics(painter.font())
        text_width = min(190, metrics.horizontalAdvance(text) + 18)
        label_rect = QtCore.QRectF(center.x() - text_width / 2, center.y() + box_height / 2 + 8, text_width, 26)
        label_rect = self._keep_inside(label_rect, crop_rect.adjusted(4, 4, -4, -4))

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        label_background = QtGui.QColor("#07111F")
        label_background.setAlpha(230)
        painter.setBrush(label_background)
        painter.drawRoundedRect(label_rect, 7, 7)
        painter.setPen(QtGui.QColor("#F7FAFC") if view.enabled else QtGui.QColor("#8393A7"))
        font = painter.font()
        font.setPointSizeF(8.5)
        font.setBold(is_selected)
        painter.setFont(font)
        painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignCenter, text)

    def _image_rect(self) -> QtCore.QRectF:
        if self._pixmap.isNull():
            return QtCore.QRectF()
        available = QtCore.QRectF(self.rect()).adjusted(8, 8, -8, -8)
        scale = min(available.width() / self._pixmap.width(), available.height() / self._pixmap.height())
        width = self._pixmap.width() * scale
        height = self._pixmap.height() * scale
        return QtCore.QRectF(
            available.center().x() - width / 2,
            available.center().y() - height / 2,
            width,
            height,
        )

    def _crop_square_rect(self, image_rect: QtCore.QRectF) -> QtCore.QRectF:
        source_width = self._pixmap.width()
        source_height = self._pixmap.height()
        side = min(source_width, source_height)
        crop_x = (source_width - side) / 2
        crop_y = (source_height - side) / 2
        scale_x = image_rect.width() / source_width
        scale_y = image_rect.height() / source_height
        return QtCore.QRectF(
            image_rect.left() + crop_x * scale_x,
            image_rect.top() + crop_y * scale_y,
            side * scale_x,
            side * scale_y,
        )

    def _view_center(self, index: int) -> QtCore.QPointF:
        if self._pixmap.isNull() or index < 0 or index >= len(self._views):
            return QtCore.QPointF(-1000, -1000)
        crop_rect = self._crop_square_rect(self._image_rect())
        x_norm, y_norm = roll_pitch_to_normalized(self._views[index].roll, self._views[index].pitch)
        return QtCore.QPointF(
            crop_rect.left() + x_norm * crop_rect.width(),
            crop_rect.top() + y_norm * crop_rect.height(),
        )

    def _hit_test_view(self, point: QtCore.QPointF) -> int:
        if self._pixmap.isNull():
            return -1
        best_index = -1
        best_distance = float("inf")
        for index in range(len(self._views)):
            center = self._view_center(index)
            distance = math.hypot(point.x() - center.x(), point.y() - center.y())
            if distance <= 46 and distance < best_distance:
                best_index = index
                best_distance = distance
        return best_index

    def _point_to_roll_pitch(self, point: QtCore.QPointF) -> tuple[float, float]:
        crop_rect = self._crop_square_rect(self._image_rect())
        if crop_rect.width() <= 0 or crop_rect.height() <= 0:
            return 0.0, 0.0
        x = (point.x() - crop_rect.left()) / crop_rect.width()
        y = (point.y() - crop_rect.top()) / crop_rect.height()
        return normalized_to_roll_pitch(x, y)

    def _point_inside_crop_circle(self, point: QtCore.QPointF) -> bool:
        crop_rect = self._crop_square_rect(self._image_rect())
        center = crop_rect.center()
        radius = crop_rect.width() / 2
        return math.hypot(point.x() - center.x(), point.y() - center.y()) <= radius

    @staticmethod
    def _keep_inside(rect: QtCore.QRectF, bounds: QtCore.QRectF) -> QtCore.QRectF:
        result = QtCore.QRectF(rect)
        if result.left() < bounds.left():
            result.moveLeft(bounds.left())
        if result.right() > bounds.right():
            result.moveRight(bounds.right())
        if result.top() < bounds.top():
            result.moveTop(bounds.top())
        if result.bottom() > bounds.bottom():
            result.moveBottom(bounds.bottom())
        return result


class PreviewCard(QtWidgets.QFrame):
    clicked = QtCore.Signal(int)
    enabled_changed = QtCore.Signal(int, bool)

    def __init__(self, index: int, view: ViewDefinition, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.setObjectName("PreviewCard")
        self.setProperty("selected", False)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(280)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.image_label = QtWidgets.QLabel("Preview not generated")
        self.image_label.setObjectName("PreviewImage")
        self.image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(260, 146)
        self.image_label.setMaximumHeight(210)
        self.image_label.setScaledContents(False)
        layout.addWidget(self.image_label)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        self.enable_box = QtWidgets.QCheckBox()
        self.enable_box.setChecked(view.enabled)
        self.enable_box.setToolTip("Include this view in the final render")
        self.enable_box.toggled.connect(lambda checked: self.enabled_changed.emit(self.index, checked))
        header.addWidget(self.enable_box)

        self.name_label = QtWidgets.QLabel(view.name)
        self.name_label.setObjectName("PreviewName")
        self.name_label.setWordWrap(True)
        header.addWidget(self.name_label, 1)
        layout.addLayout(header)

        self.details_label = QtWidgets.QLabel()
        self.details_label.setObjectName("MutedLabel")
        layout.addWidget(self.details_label)
        self.update_view(view)

    def update_view(self, view: ViewDefinition) -> None:
        self.name_label.setText(view.name)
        self.enable_box.blockSignals(True)
        self.enable_box.setChecked(view.enabled)
        self.enable_box.blockSignals(False)
        self.details_label.setText(
            f"Roll {view.roll:.1f}°   Pitch {view.pitch:.1f}°   "
            f"FOV {view.h_fov:.0f}×{view.v_fov:.0f}°"
        )
        self.setProperty("disabledView", not view.enabled)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_preview(self, pixmap: QtGui.QPixmap | None) -> None:
        if pixmap is None or pixmap.isNull():
            self.image_label.setText("Preview unavailable")
            self.image_label.setPixmap(QtGui.QPixmap())
            return
        target = self.image_label.size()
        scaled = pixmap.scaled(
            target,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")

    def set_loading(self, loading: bool) -> None:
        if loading:
            self.image_label.setPixmap(QtGui.QPixmap())
            self.image_label.setText("Generating preview…")

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
            event.accept()
            return
        super().mousePressEvent(event)


class StatusPill(QtWidgets.QLabel):
    def __init__(self, text: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("StatusPill")
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.set_status("neutral", text)

    def set_status(self, status: str, text: str) -> None:
        self.setText(text)
        self.setProperty("status", status)
        self.style().unpolish(self)
        self.style().polish(self)
