from __future__ import annotations

import math
import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._frame_extraction import ExtractionCancelled
from .._frame_extraction import _create_batch
from .._frame_extraction import safe_name
from .._thermal import THERMAL_COLOUR_STOPS
from .._thermal import ThermalFrame
from .._thermal import ThermalSource
from .._thermal import colourise
from .._thermal import save_frame
from .._thermal_analysis import UNITS
from .._thermal_analysis import Measurement
from .._thermal_analysis import celsius
from .._thermal_analysis import convert
from .frame_extractor_dialog import FrameExtractorDialog
from .thermal_options import ThermalOptions


def thermal_qimage(frame: ThermalFrame, low: float, high: float) -> QtGui.QImage:
    rgb = colourise(frame.celsius, low, high)
    height, width = rgb.shape[:2]
    return QtGui.QImage(
        rgb.data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888
    ).copy()


class ThermalControls(QtWidgets.QWidget):
    range_changed = QtCore.Signal(float, float)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.frame: ThermalFrame | None = None
        self._limits: tuple[float, float] | None = None
        self._slider_bounds = (0.0, 100.0)
        layout = QtWidgets.QVBoxLayout(self)
        self.statistics = QtWidgets.QLabel()
        self.statistics.setWordWrap(True)
        self.statistics.setMinimumHeight(
            self.statistics.fontMetrics().lineSpacing() * 4 + 4
        )
        self.statistics.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.statistics)
        gradient = QtWidgets.QLabel()
        self.gradient = gradient
        gradient.setFixedHeight(18)
        stops = ",".join(
            f"stop:{position:.9f} rgb({red},{green},{blue})"
            for position, (red, green, blue) in THERMAL_COLOUR_STOPS
        )
        gradient.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,{stops}); "
            "border: 1px solid gray;"
        )
        gradient.setAccessibleName(
            self.tr(
                "Thermal colour scale: dark blue, purple, red, orange, yellow, white"
            )
        )
        layout.addWidget(gradient)
        self.low = QtWidgets.QDoubleSpinBox()
        self.high = QtWidgets.QDoubleSpinBox()
        self.low_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.high_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        for title, spin, slider in (
            (self.tr("Lower display limit"), self.low, self.low_slider),
            (self.tr("Upper display limit"), self.high, self.high_slider),
        ):
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(title))
            spin.setRange(-273.15, 1_000_000)
            spin.setDecimals(2)
            spin.setSuffix(" °C")
            spin.setKeyboardTracking(False)
            spin.setAccessibleName(title)
            row.addWidget(spin)
            layout.addLayout(row)
            slider.setRange(0, 10000)
            slider.setAccessibleName(title + self.tr(" temperature slider"))
            layout.addWidget(slider)
        self.keep_scale = QtWidgets.QCheckBox(self.tr("Keep scale across frames"))
        self.keep_scale.setChecked(True)
        layout.addWidget(self.keep_scale)
        self.auto = QtWidgets.QPushButton(self.tr("Fit scale to this frame"))
        self.auto.clicked.connect(self._auto_range)
        layout.addWidget(self.auto)
        self.spot = QtWidgets.QLabel(
            self.tr("Move over the image to read a temperature.")
        )
        self.spot.setWordWrap(True)
        self.spot.setMinimumHeight(self.spot.fontMetrics().lineSpacing() * 2 + 4)
        layout.addWidget(self.spot)
        hint = QtWidgets.QLabel(
            self.tr(
                "Temperatures outside the display limits use the palette endpoints. "
                "Statistics use the full frame. Invalid temperature pixels are black."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.low.valueChanged.connect(lambda _: self._spin_changed(True))
        self.high.valueChanged.connect(lambda _: self._spin_changed(False))
        self.low_slider.valueChanged.connect(lambda v: self._slider_changed(True, v))
        self.high_slider.valueChanged.connect(lambda v: self._slider_changed(False, v))
        self.clear()
        self.options = ThermalOptions(self)

    @property
    def limits(self) -> tuple[float, float]:
        unit = self.options.unit if hasattr(self, "options") else "C"
        return celsius(self.low.value(), unit), celsius(self.high.value(), unit)

    def clear(self) -> None:
        self.frame = None
        self.statistics.setText(self.tr("No thermal frame loaded."))
        self.spot.clear()
        if hasattr(self, "options"):
            self.options.clear()
        for control in (
            self.low,
            self.high,
            self.low_slider,
            self.high_slider,
            self.auto,
        ):
            control.setEnabled(False)

    def set_frame(
        self, frame: ThermalFrame, limits: tuple[float, float] | None = None
    ) -> None:
        self.frame = frame
        if hasattr(self, "options"):
            self.options.set_frame(frame)
        minimum, maximum = self.frame.limits
        self.refresh_statistics()
        for control in (
            self.low,
            self.high,
            self.low_slider,
            self.high_slider,
            self.auto,
        ):
            control.setEnabled(True)
        if limits is None:
            limits = self._limits if self.keep_scale.isChecked() else None
        self._set_range(*(limits or (minimum, max(maximum, minimum + 0.1))))
        self.spot.setText(self.tr("Move over the image to read a temperature."))

    def refresh_statistics(self) -> None:
        if self.frame is None:
            return
        frame = self.frame
        minimum, maximum = frame.limits
        unit = self.options.unit if hasattr(self, "options") else "C"
        valid = np.isfinite(frame.celsius)
        invalid = valid.size - np.count_nonzero(valid)
        self.statistics.setText(
            self.tr(
                "Minimum: {minimum:.2f} {unit}\nMaximum: {maximum:.2f} {unit}\n"
                "Mean: {mean:.2f} {unit}\n"
                "Sensor: {width} × {height} | Invalid pixels: {invalid}"
            ).format(
                minimum=convert(minimum, unit),
                maximum=convert(maximum, unit),
                mean=convert(float(frame.celsius[valid].mean()), unit),
                unit=UNITS[unit],
                width=frame.celsius.shape[1],
                height=frame.celsius.shape[0],
                invalid=invalid,
            )
        )

    def _set_range(self, low: float, high: float) -> None:
        unit = self.options.unit if hasattr(self, "options") else "C"
        with QtCore.QSignalBlocker(self.low), QtCore.QSignalBlocker(self.high):
            self.low.setValue(math.floor(convert(low, unit) * 100 + 1e-8) / 100)
            self.high.setValue(
                max(
                    math.ceil(convert(high, unit) * 100 - 1e-8) / 100,
                    self.low.value() + 0.01,
                )
            )
        self._limits = self.limits
        minimum, maximum = self.frame.limits if self.frame else self.limits
        span = max(maximum - minimum, high - low, 1)
        self._slider_bounds = (
            max(-273.15, min(low, minimum) - span / 4),
            max(high, maximum) + span / 4,
        )
        self._sync_sliders()

    def _sync_sliders(self) -> None:
        lower, upper = self._slider_bounds
        for value, slider in (
            (self.limits[0], self.low_slider),
            (self.limits[1], self.high_slider),
        ):
            with QtCore.QSignalBlocker(slider):
                slider.setValue(round((value - lower) / (upper - lower) * 10000))

    def _spin_changed(self, low_changed: bool) -> None:
        if hasattr(self, "options") and self.options._restoring:
            return
        if self.frame is None:
            return
        if self.high.value() <= self.low.value():
            spin = self.low if low_changed else self.high
            with QtCore.QSignalBlocker(spin):
                spin.setValue(
                    self.high.value() - 0.01 if low_changed else self.low.value() + 0.01
                )
        self._limits = self.limits
        lower, upper = self._slider_bounds
        if not lower <= self.limits[0] < self.limits[1] <= upper:
            self._set_range(*self.limits)
        self._sync_sliders()
        self.range_changed.emit(*self.limits)

    def _slider_changed(self, low: bool, value: int) -> None:
        lower, upper = self._slider_bounds
        unit = self.options.unit
        (self.low if low else self.high).setValue(
            convert(lower + (upper - lower) * value / 10000, unit)
        )

    def _auto_range(self) -> None:
        if self.frame:
            low, high = self.frame.limits
            self._set_range(low, max(high, low + 0.1))
            self.range_changed.emit(*self.limits)

    def show_temperature(self, x: float, y: float) -> None:
        if self.frame is None:
            return
        ix, iy = math.floor(x), math.floor(y)
        height, width = self.frame.celsius.shape
        if not (0 <= ix < width and 0 <= iy < height):
            self.spot.clear()
            return
        value = self.frame.celsius[iy, ix]
        unit = self.options.unit
        self.spot.setText(
            f"x={ix}, y={iy}: {convert(value, unit):.2f} {UNITS[unit]}"
            if math.isfinite(value)
            else self.tr("No valid temperature at this pixel.")
        )


class _Preview(QtWidgets.QWidget):
    moved = QtCore.Signal(float, float)
    measured = QtCore.Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self.image = QtGui.QImage()
        self._rect = QtCore.QRectF()
        self.mode = "inspect"
        self.measurements: list[Measurement] = []
        self._start: QtCore.QPointF | None = None
        self._end: QtCore.QPointF | None = None
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtCore.Qt.GlobalColor.black)
        if self.image.isNull():
            return
        self._update_rect()
        painter.drawImage(self._rect, self.image)
        painter.save()
        painter.setClipRect(self._rect)
        painter.translate(self._rect.topLeft())
        factor = self._rect.width() / self.image.width()
        painter.scale(factor, factor)
        painter.setPen(QtGui.QPen(QtGui.QColor("cyan"), 2 / factor))
        font = painter.font()
        font.setPixelSize(max(1, round(12 / factor)))
        painter.setFont(font)
        items = list(self.measurements)
        if self._start is not None and self._end is not None:
            items.append(
                Measurement(
                    "",
                    self.mode,
                    (
                        (self._start.x(), self._start.y()),
                        (self._end.x(), self._end.y()),
                    ),
                )
            )
        for number, item in enumerate(items, 1):
            points = [QtCore.QPointF(*point) for point in item.points]
            if item.kind == "point":
                p = points[0]
                painter.drawLine(
                    p + QtCore.QPointF(-4 / factor, 0),
                    p + QtCore.QPointF(4 / factor, 0),
                )
                painter.drawLine(
                    p + QtCore.QPointF(0, -4 / factor),
                    p + QtCore.QPointF(0, 4 / factor),
                )
            elif item.kind == "rectangle":
                painter.drawRect(QtCore.QRectF(points[0], points[1]).normalized())
            elif item.kind == "circle":
                radius = math.dist(item.points[0], item.points[1])
                painter.drawEllipse(points[0], radius, radius)
            elif item.kind == "line":
                painter.drawLine(points[0], points[1])
            else:
                painter.drawPolygon(QtGui.QPolygonF(points))
            painter.drawText(points[0], str(number))
        painter.restore()

    def _update_rect(self) -> None:
        if self.image.isNull():
            self._rect = QtCore.QRectF()
            return
        size = QtCore.QSizeF(self.image.size())
        size.scale(
            QtCore.QSizeF(self.size()), QtCore.Qt.AspectRatioMode.KeepAspectRatio
        )
        self._rect = QtCore.QRectF(
            (self.width() - size.width()) / 2,
            (self.height() - size.height()) / 2,
            size.width(),
            size.height(),
        )

    def _position(self, point: QtCore.QPointF) -> QtCore.QPointF:
        self._update_rect()
        return QtCore.QPointF(
            (point.x() - self._rect.x()) * self.image.width() / self._rect.width(),
            (point.y() - self._rect.y()) * self.image.height() / self._rect.height(),
        )

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self._update_rect()
        if (
            event.button() != QtCore.Qt.MouseButton.LeftButton
            or self.mode == "inspect"
            or self.image.isNull()
            or not self._rect.contains(event.position())
        ):
            return
        point = self._position(event.position())
        if self.mode == "point":
            self.measured.emit("point", [[point.x(), point.y()]])
        else:
            self._start = point
            self._end = point

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._start is None or event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        point = self._position(event.position())
        self.measured.emit(
            self.mode, [[self._start.x(), self._start.y()], [point.x(), point.y()]]
        )
        self._start = self._end = None
        self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self._update_rect()
        if not self.image.isNull() and self._rect.width() > 0:
            if self._start is not None:
                self._end = self._position(event.position())
                self.update()
            self.moved.emit(
                (event.position().x() - self._rect.x())
                * self.image.width()
                / self._rect.width(),
                (event.position().y() - self._rect.y())
                * self.image.height()
                / self._rect.height(),
            )


class _ReadThread(QtCore.QThread):
    progress = QtCore.Signal(int, str)

    def __init__(self, operation: Callable, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self.operation = operation
        self.cancel = threading.Event()
        self.result: tuple[ThermalSource, int, ThermalFrame] | None = None
        self.error: str | None = None

    def run(self) -> None:
        try:
            self.result = self.operation(self.cancel, self.progress.emit)
        except ExtractionCancelled:
            pass
        except Exception as error:
            self.error = str(error)


class ThermalDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("FLIR Thermal Images and Video"))
        self.resize(1050, 720)
        self.source: ThermalSource | None = None
        self.index = 0
        self.exported_image: Path | None = None
        self._thread: _ReadThread | None = None
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            self.tr(
                "Open a FLIR radiometric JPEG or CSQ recording. Inspect measurements, "
                "adjust display or environmental parameters, and export frames "
                "to annotate at the sensor resolution."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        buttons = QtWidgets.QHBoxLayout()
        self.open = QtWidgets.QPushButton(self.tr("Open FLIR Image or CSQ…"))
        self.extract = QtWidgets.QPushButton(self.tr("Extract Recording Frames…"))
        self.save = QtWidgets.QPushButton(self.tr("Save Current Frame…"))
        self.annotate = QtWidgets.QPushButton(self.tr("Save and Open for Annotation…"))
        for button in (self.open, self.extract, self.save, self.annotate):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        measurement_tools = QtWidgets.QHBoxLayout()
        measurement_tools.addWidget(QtWidgets.QLabel(self.tr("Measurement tool")))
        self.measurement_tool = QtWidgets.QComboBox()
        for label, kind in (
            ("Inspect", "inspect"),
            ("Spot", "point"),
            ("Box", "rectangle"),
            ("Circle", "circle"),
            ("Line", "line"),
        ):
            self.measurement_tool.addItem(self.tr(label), kind)
        measurement_tools.addWidget(self.measurement_tool)
        measurement_tools.addStretch()
        layout.addLayout(measurement_tools)
        body = QtWidgets.QHBoxLayout()
        self.preview = _Preview()
        body.addWidget(self.preview, 1)
        self.controls = ThermalControls()
        self.controls.setMinimumWidth(380)
        self.controls.setMaximumWidth(400)
        body.addWidget(self.controls)
        layout.addLayout(body, 1)
        navigation = QtWidgets.QHBoxLayout()
        self.previous = QtWidgets.QPushButton(self.tr("Previous"))
        self.next = QtWidgets.QPushButton(self.tr("Next"))
        self.frame_number = QtWidgets.QSpinBox()
        self.frame_number.setRange(1, 1)
        self.frame_number.setKeyboardTracking(False)
        self.frame_number.setAccessibleName(
            self.tr("Thermal frame number (starts at 1)")
        )
        self.frame_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.frame_slider.setRange(1, 1)
        self.frame_slider.setAccessibleName(self.tr("Thermal recording frame"))
        for widget in (self.previous, self.frame_slider, self.frame_number, self.next):
            navigation.addWidget(widget)
        layout.addLayout(navigation)
        self.status = QtWidgets.QLabel(self.tr("Ready. No file loaded."))
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.close_button = QtWidgets.QPushButton(self.tr("Close"))
        layout.addWidget(self.close_button)
        self.close_button.clicked.connect(self.reject)
        self.open.clicked.connect(self._choose)
        self.save.clicked.connect(lambda: self._save(False))
        self.annotate.clicked.connect(lambda: self._save(True))
        self.extract.clicked.connect(self._extract)
        self.previous.clicked.connect(lambda: self._read(self.index - 1))
        self.next.clicked.connect(lambda: self._read(self.index + 1))
        self.frame_number.valueChanged.connect(lambda number: self._read(number - 1))
        self.frame_slider.sliderReleased.connect(
            lambda: self._read(self.frame_slider.value() - 1)
        )
        self.frame_slider.valueChanged.connect(self._slider_changed)
        self.controls.range_changed.connect(self._render)
        self.preview.moved.connect(self.controls.show_temperature)
        self.preview.measured.connect(self.controls.options.add_measurement)
        self.measurement_tool.currentIndexChanged.connect(
            self._measurement_mode_changed
        )
        self._enable_controls()

    def _slider_changed(self, value: int) -> None:
        if not self.frame_slider.isSliderDown():
            self._read(value - 1)

    def _enable_controls(self) -> None:
        ready = self.source is not None and self._thread is None
        self.open.setEnabled(self._thread is None)
        self.save.setEnabled(ready)
        self.annotate.setEnabled(ready)
        self.extract.setEnabled(ready and self.source.path.suffix.lower() == ".csq")
        self.previous.setEnabled(ready and self.index > 0)
        self.next.setEnabled(ready and self.index + 1 < len(self.source))
        self.frame_number.setEnabled(ready)
        self.frame_slider.setEnabled(ready)
        self.measurement_tool.setEnabled(ready)
        self.close_button.setText(
            self.tr("Cancel Loading") if self._thread else self.tr("Close")
        )

    def _choose(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Open FLIR Thermal File"),
            "",
            self.tr("FLIR thermal files (*.jpg *.jpeg *.csq *.JPG *.JPEG *.CSQ)"),
        )
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        def load(cancel: threading.Event, progress: Callable) -> tuple:
            source = ThermalSource(path, cancel, progress)
            return source, 0, source.read(0, cancel)

        self._start(load)

    def _read(self, index: int) -> None:
        source = self.source
        if (
            self._thread
            or source is None
            or not 0 <= index < len(source)
            or index == self.index
        ):
            return
        self._start(
            lambda cancel, progress: (source, index, source.read(index, cancel))
        )

    def _start(self, operation: Callable) -> None:
        if self._thread:
            return
        self._thread = _ReadThread(operation, self)
        self._thread.progress.connect(lambda _, message: self.status.setText(message))
        self._thread.finished.connect(self._loaded)
        self._enable_controls()
        self.status.setText(self.tr("Reading thermal data…"))
        self._thread.start()

    def _loaded(self) -> None:
        thread = self._thread
        assert thread is not None
        self._thread = None
        if thread.cancel.is_set():
            self.status.setText(self.tr("Loading cancelled."))
        elif thread.error:
            self.status.setText(self.tr("Could not read thermal file: ") + thread.error)
        elif thread.result and not thread.cancel.is_set():
            if self.source is not thread.result[0]:
                self.controls.options.restore({})
            self.source, self.index, frame = thread.result
            frame = ThermalFrame(
                frame.celsius,
                frame.raw,
                dict(
                    frame.metadata, source=str(self.source.path), frame_index=self.index
                ),
            )
            self.controls.set_frame(frame)
            self._render()
            self.status.setText(
                f"{self.source.path} | Frame {self.index + 1:,} / {len(self.source):,}"
                + (
                    "\n" + "\n".join(self.source.warnings)
                    if self.source.warnings
                    else ""
                )
            )
        else:
            self.status.setText(self.tr("Loading cancelled."))
        if self.source:
            with (
                QtCore.QSignalBlocker(self.frame_number),
                QtCore.QSignalBlocker(self.frame_slider),
            ):
                self.frame_number.setRange(1, len(self.source))
                self.frame_slider.setRange(1, len(self.source))
                self.frame_number.setValue(self.index + 1)
                self.frame_slider.setValue(self.index + 1)
        self._enable_controls()
        thread.deleteLater()

    def _render(self, *_: float) -> None:
        if self.controls.frame:
            self.preview.image = self.controls.options.image()
            self.preview.measurements = self.controls.options.all_measurements()
            self.preview.update()

    def _measurement_mode_changed(self, *_: int) -> None:
        self.preview.mode = self.measurement_tool.currentData()
        self.preview._start = self.preview._end = None
        self.preview.update()

    def _extract(self) -> None:
        assert self.source is not None
        dialog = FrameExtractorDialog(self)
        dialog.add_videos([self.source.path])
        dialog.thermal_range = self.controls.limits
        dialog.thermal_analysis = self.controls.options.state()
        dialog.exec()
        dialog.deleteLater()

    def _save(self, annotate: bool) -> None:
        if self.source is None or self.controls.frame is None:
            return
        parent = QtWidgets.QFileDialog.getExistingDirectory(
            self, self.tr("Choose Output Parent Folder")
        )
        if not parent:
            return
        batch: Path | None = None
        try:
            batch = _create_batch(Path(parent))
            name = f"{safe_name(self.source.path.stem)}_frame_{self.index:09d}.png"
            with tempfile.TemporaryDirectory(prefix=".thermal-", dir=batch) as stage:
                image = Path(stage) / name
                save_frame(
                    self.controls.options.frame_for_export(),
                    image,
                    *self.controls.limits,
                    source=str(self.source.path),
                    index=self.index,
                    display=self.controls.options.state()["display"],
                )
                for file in Path(stage).iterdir():
                    file.rename(batch / file.name)
            image = batch / name
            self.status.setText(
                self.tr("Saved image and temperature data: ") + str(image)
            )
            if annotate:
                self.exported_image = image
                self.accept()
        except (OSError, ValueError) as error:
            if batch is not None:
                shutil.rmtree(batch, ignore_errors=True)
            self.status.setText(self.tr("Could not save thermal frame: ") + str(error))

    def reject(self) -> None:
        if self._thread:
            self._thread.cancel.set()
            self.status.setText(self.tr("Cancelling thermal read…"))
            return
        super().reject()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._thread:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
