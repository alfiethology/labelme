from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._thermal import ThermalError
from .._thermal import ThermalFrame
from .._thermal_analysis import PALETTES
from .._thermal_analysis import PARAMETERS
from .._thermal_analysis import UNITS
from .._thermal_analysis import Display
from .._thermal_analysis import Measurement
from .._thermal_analysis import celsius
from .._thermal_analysis import convert
from .._thermal_analysis import export_csv
from .._thermal_analysis import export_report
from .._thermal_analysis import isotherm_mask
from .._thermal_analysis import recalculate
from .._thermal_analysis import render
from .._thermal_analysis import sample
from .._thermal_analysis import summary

if TYPE_CHECKING:
    from .thermal import ThermalControls


def qimage(rgb: np.ndarray) -> QtGui.QImage:
    height, width = rgb.shape[:2]
    return QtGui.QImage(
        rgb.data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888
    ).copy()


class ThermalOptions(QtCore.QObject):
    """Additional analysis tabs shared by the viewer and annotation editor."""

    def __init__(self, owner: ThermalControls) -> None:
        super().__init__(owner)
        self.owner = owner
        self.unit = "C"
        self.display = Display()
        self.overrides: dict = {}
        self.measurements: list[Measurement] = []
        self.annotation_measurements: list[Measurement] = []
        self.original: ThermalFrame | None = None
        self._restoring = False
        self._pending_reference: int | None = None
        layout = owner.layout()
        display_content = QtWidgets.QWidget()
        display_layout = QtWidgets.QVBoxLayout(display_content)
        # Move the existing scale controls into a scrollable Display tab.
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                display_layout.addWidget(item.widget())
            elif item.layout() is not None:
                display_layout.addLayout(item.layout())
            else:
                display_layout.addItem(item)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)
        self.palette = QtWidgets.QComboBox()
        for key, name in PALETTES.items():
            self.palette.addItem(name, key)
        self.units = QtWidgets.QComboBox()
        for key, name in UNITS.items():
            self.units.addItem(name, key)
        self.distribution = QtWidgets.QComboBox()
        self.distribution.addItem(self.tr("Temperature linear"), "linear")
        self.distribution.addItem(self.tr("Histogram equalization"), "histogram")
        form = QtWidgets.QFormLayout()
        form.addRow(self.tr("Palette"), self.palette)
        form.addRow(self.tr("Temperature units"), self.units)
        form.addRow(self.tr("Colour distribution"), self.distribution)
        display_layout.insertLayout(0, form)
        self.markers = QtWidgets.QCheckBox(self.tr("Mark coldest / hottest pixels"))
        display_layout.addWidget(self.markers)
        self.isotherm = QtWidgets.QComboBox()
        for label, key in (
            ("Off", "off"),
            ("At or above", "above"),
            ("At or below", "below"),
            ("Between", "between"),
        ):
            self.isotherm.addItem(self.tr(label), key)
        self.threshold = QtWidgets.QDoubleSpinBox()
        self.threshold_upper = QtWidgets.QDoubleSpinBox()
        for control, value in ((self.threshold, 30), (self.threshold_upper, 40)):
            control.setRange(-273.15, 1_000_000)
            control.setValue(value)
            control.setSuffix(" °C")
            control.setKeyboardTracking(False)
        isoform = QtWidgets.QFormLayout()
        isoform.addRow(self.tr("Green isotherm highlight"), self.isotherm)
        isoform.addRow(self.tr("Threshold / lower limit"), self.threshold)
        isoform.addRow(self.tr("Upper limit"), self.threshold_upper)
        display_layout.addLayout(isoform)
        self.coverage = QtWidgets.QLabel()
        self.coverage.setWordWrap(True)
        display_layout.addWidget(self.coverage)
        display_layout.addStretch()
        self._add_tab(display_content, self.tr("Display"))

        measurements = QtWidgets.QWidget()
        ml = QtWidgets.QVBoxLayout(measurements)
        note = QtWidgets.QLabel(
            self.tr(
                "Viewer: choose Spot, Box, Circle or Line above the image, "
                "then click or drag. In Labelme, select annotation Shapes to "
                "measure them. Area measurements use pixel centres."
            )
        )
        note.setWordWrap(True)
        ml.addWidget(note)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [self.tr(t) for t in ("Measurement", "Min", "Max", "Mean", "Δ mean")]
        )
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        ml.addWidget(self.table)
        self.reference = QtWidgets.QComboBox()
        self.reference.addItem(self.tr("No reference"), -1)
        ml.addWidget(
            QtWidgets.QLabel(self.tr("Temperature difference reference (mean)"))
        )
        ml.addWidget(self.reference)
        self.remove = QtWidgets.QPushButton(self.tr("Remove viewer measurements"))
        self.remove.clicked.connect(self.clear_measurements)
        ml.addWidget(self.remove)
        self.profile = QtWidgets.QLabel(
            self.tr("Select a line measurement to see its temperature profile.")
        )
        self.profile.setWordWrap(True)
        self.profile.setMinimumHeight(120)
        ml.addWidget(self.profile)
        self.profile_export = QtWidgets.QPushButton(
            self.tr("Export Selected Line Profile CSV…")
        )
        self.profile_export.clicked.connect(self._export_profile)
        ml.addWidget(self.profile_export)
        self._add_tab(measurements, self.tr("Measure"))

        parameters = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(parameters)
        explanation = QtWidgets.QLabel(
            self.tr(
                "Recalculate temperatures from the original sensor values. "
                "Factory calibration is preserved. Parameters apply to the whole frame."
            )
        )
        explanation.setWordWrap(True)
        pl.addWidget(explanation)
        pf = QtWidgets.QFormLayout()
        pl.addLayout(pf)
        self.parameters: dict[str, QtWidgets.QDoubleSpinBox] = {}
        for key, label, minimum, maximum, decimals, suffix in (
            ("emissivity", "Emissivity", 0.01, 1, 3, ""),
            ("distance", "Object distance", 0, 100000, 2, " m"),
            ("reflected_kelvin", "Reflected temperature", -273.14, 10000, 2, " °C"),
            ("air_kelvin", "Atmospheric temperature", -273.14, 1000, 2, " °C"),
            ("humidity", "Relative humidity", 0, 100, 1, " %"),
            ("window_transmission", "IR window transmission", 0.01, 1, 3, ""),
            ("window_kelvin", "IR window temperature", -273.14, 10000, 2, " °C"),
        ):
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setDecimals(decimals)
            spin.setSuffix(suffix)
            spin.setKeyboardTracking(False)
            self.parameters[key] = spin
            pf.addRow(self.tr(label), spin)
        self.apply_parameters = QtWidgets.QPushButton(
            self.tr("Apply Measurement Parameters")
        )
        self.apply_parameters.clicked.connect(self._apply_parameters)
        pl.addWidget(self.apply_parameters)
        self.reset_parameters = QtWidgets.QPushButton(
            self.tr("Restore Camera Parameters")
        )
        self.reset_parameters.clicked.connect(self._reset_parameters)
        pl.addWidget(self.reset_parameters)
        self.parameter_status = QtWidgets.QLabel()
        self.parameter_status.setWordWrap(True)
        pl.addWidget(self.parameter_status)
        pl.addStretch()
        self._add_tab(parameters, self.tr("Parameters"))

        exports = QtWidgets.QWidget()
        el = QtWidgets.QVBoxLayout(exports)
        self.csv_export = QtWidgets.QPushButton(
            self.tr("Export Temperature Matrix CSV…")
        )
        self.report_export = QtWidgets.QPushButton(self.tr("Export HTML Report…"))
        self.csv_export.clicked.connect(lambda: self._export(False))
        self.report_export.clicked.connect(lambda: self._export(True))
        el.addWidget(self.csv_export)
        el.addWidget(self.report_export)
        self.export_status = QtWidgets.QLabel(
            self.tr(
                "Exports use the current parameters and temperature units. "
                "The HTML report includes an image, numbered measurements "
                "and source metadata."
            )
        )
        self.export_status.setWordWrap(True)
        el.addWidget(self.export_status)
        el.addStretch()
        self._add_tab(exports, self.tr("Export"))
        for combo in (self.palette, self.distribution, self.isotherm):
            combo.currentIndexChanged.connect(self._display_changed)
        self.markers.toggled.connect(self._display_changed)
        self.threshold.valueChanged.connect(self._display_changed)
        self.threshold_upper.valueChanged.connect(self._display_changed)
        self.units.currentIndexChanged.connect(self._unit_changed)
        self.reference.currentIndexChanged.connect(self._reference_changed)
        self.table.itemSelectionChanged.connect(self._profile_changed)
        self.clear()
        self._display_changed()

    def _add_tab(self, content: QtWidgets.QWidget, title: str) -> None:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, title)

    def clear(self) -> None:
        self.original = None
        self.annotation_measurements.clear()
        self.table.setRowCount(0)
        self.profile.clear()
        self.coverage.clear()
        for widget in (
            self.csv_export,
            self.report_export,
            self.apply_parameters,
            self.reset_parameters,
            self.profile_export,
        ):
            widget.setEnabled(False)

    def set_frame(self, frame: ThermalFrame) -> None:
        self.original = frame
        if self.overrides and all(k in frame.metadata for k in PARAMETERS):
            self.owner.frame = recalculate(frame, self.overrides)
        self.owner.refresh_statistics()
        self._fill_parameters()
        self.csv_export.setEnabled(True)
        self.report_export.setEnabled(True)
        self._update_coverage()
        self.refresh_measurements()
        self._update_gradient()

    def state(self) -> dict:
        return {
            "display": asdict(self.display),
            "unit": self.unit,
            "parameters": dict(self.overrides),
            "measurements": [asdict(m) for m in self.measurements],
            "reference": self.reference.currentData(),
        }

    def restore(self, state: dict) -> None:
        if not isinstance(state, dict):
            raise ThermalError("Invalid thermal analysis settings.")
        display = Display.read(state.get("display", {}))
        unit = state.get("unit", "C")
        if unit not in UNITS:
            raise ThermalError("Unknown temperature unit.")
        overrides = state.get("parameters", {})
        if not isinstance(overrides, dict) or not set(overrides).issubset(PARAMETERS):
            raise ThermalError("Unknown thermal measurement parameters.")
        measurements = [Measurement.read(m) for m in state.get("measurements", [])]
        reference = state.get("reference", -1)
        if not isinstance(reference, int) or reference < -1:
            raise ThermalError("Invalid thermal difference reference.")
        self._restoring = True
        try:
            limits = self.owner.limits
            self.display, self.unit, self.overrides = display, unit, dict(overrides)
            self.measurements = measurements
            self._pending_reference = reference
            for combo, value in (
                (self.palette, display.palette),
                (self.distribution, display.distribution),
                (self.isotherm, display.isotherm),
                (self.units, unit),
            ):
                combo.setCurrentIndex(combo.findData(value))
            self.markers.setChecked(display.markers)
            self._unit_ranges()
            self.threshold.setValue(convert(display.lower, unit))
            self.threshold_upper.setValue(convert(display.upper, unit))
            self.owner._set_range(*limits)
            self.threshold.setEnabled(display.isotherm != "off")
            self.threshold_upper.setEnabled(display.isotherm == "between")
        finally:
            self._restoring = False

    def frame_for_export(self) -> ThermalFrame:
        frame = self.owner.frame
        assert frame is not None
        return ThermalFrame(
            frame.celsius, frame.raw, dict(frame.metadata, analysis=self.state())
        )

    def image(self) -> QtGui.QImage:
        assert self.owner.frame is not None
        return qimage(render(self.owner.frame, *self.owner.limits, self.display))

    def _notify(self) -> None:
        if self.owner.frame is not None and not self._restoring:
            self.owner.range_changed.emit(*self.owner.limits)

    def _display_changed(self, *_: object) -> None:
        if self._restoring:
            return
        lower = celsius(self.threshold.value(), self.unit)
        upper = celsius(self.threshold_upper.value(), self.unit)
        if lower > upper:
            with QtCore.QSignalBlocker(self.threshold_upper):
                self.threshold_upper.setValue(self.threshold.value())
            upper = lower
        self.display = Display(
            self.palette.currentData(),
            self.distribution.currentData(),
            self.isotherm.currentData(),
            lower,
            upper,
            self.markers.isChecked(),
        )
        self.threshold.setEnabled(self.display.isotherm != "off")
        self.threshold_upper.setEnabled(self.display.isotherm == "between")
        self._update_gradient()
        self._update_coverage()
        self._notify()

    def _unit_ranges(self) -> None:
        suffix = " " + UNITS[self.unit]
        for spin in (
            self.owner.low,
            self.owner.high,
            self.threshold,
            self.threshold_upper,
        ):
            spin.setRange(convert(-273.15, self.unit), convert(1_000_000, self.unit))
            spin.setSuffix(suffix)

    def _unit_changed(self, *_: object) -> None:
        if self._restoring:
            return
        limits = self.owner.limits
        self.unit = self.units.currentData()
        self._restoring = True
        try:
            self._unit_ranges()
            self.owner._set_range(*limits)
            self.threshold.setValue(convert(self.display.lower, self.unit))
            self.threshold_upper.setValue(convert(self.display.upper, self.unit))
        finally:
            self._restoring = False
        self.owner.refresh_statistics()
        self.refresh_measurements()
        self._notify()

    def _update_gradient(self) -> None:
        values = np.linspace(0, 1, 256)[None, :]
        frame = ThermalFrame(values, np.zeros_like(values, dtype=np.uint16), {})
        # A legend is linear even when the image uses histogram equalization.
        image = qimage(render(frame, 0, 1, Display(palette=self.display.palette)))
        self.owner.gradient.setScaledContents(True)
        self.owner.gradient.setPixmap(QtGui.QPixmap.fromImage(image))
        self.owner.gradient.setAccessibleName(
            PALETTES[self.display.palette] + self.tr(" thermal colour scale")
        )

    def _update_coverage(self) -> None:
        frame = self.owner.frame
        if frame is None or self.display.isotherm == "off":
            self.coverage.clear()
            return
        valid = int(np.isfinite(frame.celsius).sum())
        selected = int(isotherm_mask(frame.celsius, self.display).sum())
        self.coverage.setText(
            self.tr(
                "Highlighted: {count:,} / {valid:,} valid pixels ({percent:.2f}%)"
            ).format(
                count=selected,
                valid=valid,
                percent=100 * selected / valid if valid else 0,
            )
        )

    def _fill_parameters(self) -> None:
        frame = self.owner.frame
        available = frame is not None and all(k in frame.metadata for k in PARAMETERS)
        for key, spin in self.parameters.items():
            spin.setEnabled(available)
            if available:
                value = frame.metadata[key]
                spin.setValue(
                    value - 273.15
                    if key.endswith("kelvin")
                    else value * 100
                    if key == "humidity"
                    else value
                )
        self.apply_parameters.setEnabled(available)
        self.reset_parameters.setEnabled(available)

    def _apply_parameters(self) -> None:
        if self.original is None:
            return
        values = {
            key: spin.value() + 273.15
            if key.endswith("kelvin")
            else spin.value() / 100
            if key == "humidity"
            else spin.value()
            for key, spin in self.parameters.items()
        }
        try:
            frame = recalculate(self.original, values)
        except (ValueError, KeyError, TypeError) as error:
            self.parameter_status.setText(str(error))
            return
        self.overrides = values
        self.owner.frame = frame
        self.owner.refresh_statistics()
        self.refresh_measurements()
        self._update_coverage()
        self.parameter_status.setText(
            self.tr("Parameters applied. Original sensor values preserved.")
        )
        self._notify()

    def _reset_parameters(self) -> None:
        if self.original is None:
            return
        self.owner.frame = recalculate(self.original, {})
        self.overrides = {}
        self._fill_parameters()
        self.owner.refresh_statistics()
        self.refresh_measurements()
        self._update_coverage()
        self.parameter_status.setText(self.tr("Camera parameters restored."))
        self._notify()

    def add_measurement(self, kind: str, points: list) -> None:
        self.measurements.append(
            Measurement.read(
                {
                    "name": f"{kind.title()} {len(self.measurements) + 1}",
                    "kind": kind,
                    "points": points,
                }
            )
        )
        self.refresh_measurements()
        self._notify()

    def clear_measurements(self) -> None:
        self.measurements.clear()
        self.refresh_measurements()
        self._notify()

    def all_measurements(self) -> list[Measurement]:
        return self.measurements + self.annotation_measurements

    def refresh_measurements(self, *_: object) -> None:
        frame = self.owner.frame
        if frame is None:
            return
        items = self.all_measurements()
        reference_index = self.reference.currentData()
        if self._pending_reference is not None:
            reference_index = self._pending_reference
            self._pending_reference = None
        with QtCore.QSignalBlocker(self.reference):
            self.reference.clear()
            self.reference.addItem(self.tr("No reference"), -1)
            for index, item in enumerate(items):
                self.reference.addItem(item.name, index)
            self.reference.setCurrentIndex(
                max(0, self.reference.findData(reference_index))
            )
        results = [summary(frame, item) for item in items]
        reference_index = self.reference.currentData()
        ref = (
            results[reference_index]["mean"]
            if 0 <= reference_index < len(results)
            else None
        )
        with QtCore.QSignalBlocker(self.table):
            self.table.setRowCount(len(items))
            for index, (item, stats) in enumerate(zip(items, results, strict=True)):
                values = [item.name] + [
                    "—"
                    if stats[key] is None
                    else f"{convert(stats[key], self.unit):.2f}"
                    for key in ("min", "max", "mean")
                ]
                values.append(
                    "—"
                    if ref is None or stats["mean"] is None
                    else f"{convert(stats['mean'] - ref, self.unit, delta=True):+.2f}"
                )
                for column, value in enumerate(values):
                    self.table.setItem(index, column, QtWidgets.QTableWidgetItem(value))
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("Measurement"),
                *[
                    f"{name} ({UNITS[self.unit]})"
                    for name in ("Min", "Max", "Mean", "Δ mean")
                ],
            ]
        )
        self._profile_changed()

    def _reference_changed(self, *_: object) -> None:
        self.refresh_measurements()
        self._notify()

    def _selected_line(self) -> Measurement | None:
        row = self.table.currentRow()
        items = self.all_measurements()
        return (
            items[row] if 0 <= row < len(items) and items[row].kind == "line" else None
        )

    def _profile_changed(self) -> None:
        line = self._selected_line()
        frame = self.owner.frame
        self.profile_export.setEnabled(line is not None)
        if line is None or frame is None:
            self.profile.setText(
                self.tr("Select a line measurement to see its temperature profile.")
            )
            return
        _, values = sample(frame, line)
        values = convert(values, self.unit)
        valid = np.isfinite(values)
        if not valid.any():
            self.profile.setText(self.tr("No valid temperatures on this line."))
            return
        picture = QtGui.QPixmap(300, 140)
        picture.fill(QtCore.Qt.GlobalColor.white)
        painter = QtGui.QPainter(picture)
        painter.setPen(QtCore.Qt.GlobalColor.black)
        low, high = float(values[valid].min()), float(values[valid].max())
        painter.drawText(
            5, 15, f"{low:.2f}–{high:.2f} {UNITS[self.unit]} | {len(values)} pixels"
        )
        painter.drawLine(15, 120, 290, 120)
        painter.setPen(QtGui.QPen(QtGui.QColor("darkred"), 2))
        previous = None
        for index, value in enumerate(values):
            if not np.isfinite(value):
                previous = None
                continue
            point = QtCore.QPointF(
                15 + index / max(len(values) - 1, 1) * 275,
                115 - (value - low) / max(high - low, 0.01) * 85,
            )
            if previous is not None:
                painter.drawLine(previous, point)
            previous = point
        painter.end()
        self.profile.setPixmap(picture)

    def _export_profile(self) -> None:
        line = self._selected_line()
        if line is None or self.owner.frame is None:
            return
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.owner, self.tr("Export Line Profile"), "profile.csv", "CSV (*.csv)"
        )
        if not filename:
            return
        try:
            xy, values = sample(self.owner.frame, line)
            with Path(filename).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    ["x", "y", "distance_pixels", "temperature_" + self.unit]
                )
                distances = np.linalg.norm(xy - xy[0], axis=1) if len(xy) else []
                for point, distance, value in zip(
                    xy, distances, convert(values, self.unit), strict=True
                ):
                    writer.writerow(
                        [
                            *point,
                            f"{distance:.6f}",
                            f"{value:.6f}" if np.isfinite(value) else "",
                        ]
                    )
        except OSError as error:
            QtWidgets.QMessageBox.warning(
                self.owner, self.tr("Export Failed"), str(error)
            )

    def _export(self, report: bool) -> None:
        if self.owner.frame is None:
            return
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.owner,
            self.tr("Export Thermal Analysis"),
            "thermal-report.html" if report else "temperatures.csv",
            "HTML (*.html)" if report else "CSV (*.csv)",
        )
        if not filename:
            return
        try:
            frame = self.frame_for_export()
            if report:
                export_report(
                    Path(filename),
                    frame,
                    *self.owner.limits,
                    self.display,
                    self.unit,
                    self.all_measurements(),
                    reference=self.reference.currentData(),
                )
            else:
                export_csv(Path(filename), frame, self.unit)
            self.export_status.setText(self.tr("Saved: ") + filename)
        except (OSError, ValueError) as error:
            self.export_status.setText(self.tr("Export failed: ") + str(error))
