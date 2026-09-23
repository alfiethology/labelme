from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import skimage.measure
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._shape import Shape
from ._shape_render import Palette
from ._shape_render import ShapeRenderContext
from ._shape_render import _build_shape_points_paths


def read_label_shortcuts(path: str | Path) -> list[tuple[str, str]]:
    """Read ``label,key`` rows used by the change-labels review dialog."""
    choices: list[tuple[str, str]] = []
    labels: set[str] = set()
    keys: set[str] = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for line_number, row in enumerate(csv.reader(stream), start=1):
            if not row or row[0].lstrip().startswith("#"):
                continue
            if len(row) != 2:
                raise ValueError(f"Line {line_number} must contain exactly: label,key")
            label, key = (value.strip() for value in row)
            normalized_key = key.casefold()
            if not label or len(key) != 1 or not key.isprintable():
                raise ValueError(
                    f"Line {line_number} needs a non-empty label and one printable key"
                )
            if label in labels:
                raise ValueError(f"Duplicate label on line {line_number}: {label}")
            if normalized_key in keys:
                raise ValueError(f"Duplicate key on line {line_number}: {key}")
            labels.add(label)
            keys.add(normalized_key)
            choices.append((label, key))
    if not choices:
        raise ValueError("The label shortcut file contains no choices")
    return choices


class _ShapeHighlightItem(QtWidgets.QGraphicsItem):
    def __init__(self, *, shape: Shape, image_size: QtCore.QSize) -> None:
        super().__init__()
        self.shape = shape
        self._bounds = QtCore.QRectF(
            0.0, 0.0, float(image_size.width()), float(image_size.height())
        )

    def boundingRect(self) -> QtCore.QRectF:
        return self._bounds

    def set_shape(self, shape: Shape) -> None:
        self.shape = shape
        self.update()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: QtWidgets.QWidget | None = None,
    ) -> None:
        del option, widget
        transform = painter.worldTransform()
        view_scale = max((transform.m11() ** 2 + transform.m12() ** 2) ** 0.5, 0.001)
        context = ShapeRenderContext(
            scale=1.0,
            palette=Palette.from_rgb((255, 235, 0)),
            point_size=8.0 / view_scale,
            point_type="round",
            selected=True,
            fill=False,
            highlight=None,
            rotation_highlight=None,
            skeleton_node_size=max(8, round(8.0 / view_scale)),
        )
        paths = _build_shape_points_paths(shape=self.shape, context=context)

        line_pen = QtGui.QPen(QtGui.QColor(255, 235, 0))
        line_pen.setWidthF(2.0)
        line_pen.setCosmetic(True)
        line_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(line_pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(paths.line)
        painter.drawPath(paths.orientation_arrow)
        self._draw_mask_contour(painter)

        painter.setBrush(QtGui.QColor(255, 235, 0))
        painter.drawPath(paths.vertices)
        painter.setBrush(QtGui.QColor(255, 0, 0))
        painter.drawPath(paths.negative_vertices)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor(128, 128, 128), 2.0))
        painter.drawPath(paths.missing_vertices)

    def _draw_mask_contour(self, painter: QtGui.QPainter) -> None:
        if self.shape.shape_type != "mask" or self.shape.mask is None:
            return
        origin = self.shape.points[0]
        path = QtGui.QPainterPath()
        pad = 1
        contours = skimage.measure.find_contours(np.pad(self.shape.mask, pad_width=pad))
        for contour in contours:
            contour = contour - pad + [origin[1], origin[0]]
            path.moveTo(float(contour[0, 1]), float(contour[0, 0]))
            for point in contour[1:]:
                path.lineTo(float(point[1]), float(point[0]))
        painter.drawPath(path)


class ChangeLabelsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        *,
        image: QtGui.QImage,
        shapes: list[Shape],
        choices: list[tuple[str, str]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if not shapes:
            raise ValueError("Change Labels requires at least one shape")
        self.setWindowTitle(self.tr("Change Labels"))
        self.setWindowFlag(QtCore.Qt.WindowType.Window, True)
        self.resize(1000, 760)
        self._image = image
        self._shapes = shapes
        self._choices = choices
        self._labels = [shape.label or "" for shape in shapes]
        self._index = 0
        self._skip_frame_requested = False

        self._heading = QtWidgets.QLabel()
        self._heading.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        font = self._heading.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self._heading.setFont(font)

        self._scene = QtWidgets.QGraphicsScene(self)
        self._scene.addPixmap(QtGui.QPixmap.fromImage(image))
        self._highlight = _ShapeHighlightItem(shape=shapes[0], image_size=image.size())
        self._scene.addItem(self._highlight)
        self._view = QtWidgets.QGraphicsView(self._scene)
        self._view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._view.setBackgroundBrush(QtGui.QColor("#20252b"))

        choice_layout = QtWidgets.QHBoxLayout()
        for label, key in choices:
            button = QtWidgets.QPushButton(f"{key.upper()}  {label}")
            button.setMinimumHeight(42)
            button.clicked.connect(
                lambda _checked=False, selected=label: self._choose(selected)
            )
            choice_layout.addWidget(button)

        previous = QtWidgets.QPushButton(self.tr("← Previous"))
        previous.clicked.connect(self._previous)
        next_ = QtWidgets.QPushButton(self.tr("Next →"))
        next_.clicked.connect(self._next)
        skip = QtWidgets.QPushButton(self.tr("Skip / Don’t know"))
        skip.clicked.connect(self._request_frame_skip)
        exit_ = QtWidgets.QPushButton(self.tr("Exit and apply"))
        exit_.clicked.connect(self.accept)
        navigation = QtWidgets.QHBoxLayout()
        navigation.addWidget(previous)
        navigation.addWidget(next_)
        navigation.addStretch()
        navigation.addWidget(skip)
        navigation.addWidget(exit_)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._heading)
        layout.addWidget(self._view, 1)
        layout.addLayout(choice_layout)
        layout.addLayout(navigation)
        self._show_current()

    @property
    def labels(self) -> list[str]:
        return list(self._labels)

    @property
    def skip_frame_requested(self) -> bool:
        return self._skip_frame_requested

    def reject(self) -> None:
        self.accept()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.text().casefold()
        for label, shortcut in self._choices:
            if key == shortcut.casefold():
                self._choose(label)
                return
        if event.key() == QtCore.Qt.Key.Key_Left:
            self._previous()
            return
        if event.key() == QtCore.Qt.Key.Key_Right:
            self._next()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_image()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._fit_image()

    def _fit_image(self) -> None:
        self._view.fitInView(
            QtCore.QRectF(self._image.rect()),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _request_frame_skip(self) -> None:
        self._skip_frame_requested = True
        self.accept()

    def _choose(self, label: str) -> None:
        self._labels[self._index] = label
        if self._index < len(self._shapes) - 1:
            self._index += 1
        self._show_current()

    def _previous(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._show_current()

    def _next(self) -> None:
        if self._index < len(self._shapes) - 1:
            self._index += 1
            self._show_current()

    def _show_current(self) -> None:
        shape = self._shapes[self._index]
        self._heading.setText(
            self.tr("Annotation {current} of {total} — current label: {label}").format(
                current=self._index + 1,
                total=len(self._shapes),
                label=self._labels[self._index] or self.tr("(none)"),
            )
        )
        self._highlight.set_shape(shape)
