from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from labelme._thermal import ThermalFrame
from labelme._thermal import ThermalSource
from labelme._widgets.thermal import ThermalControls
from labelme._widgets.thermal import ThermalDialog
from tests.thermal_helpers import fff
from tests.thermal_helpers import radiometric_jpeg


def test_temperature_controls_do_not_change_measurements(qtbot: QtBot) -> None:
    values = np.array([[10, 20], [30, np.nan]])
    controls = ThermalControls()
    qtbot.addWidget(controls)
    controls.show()
    assert controls.low.isVisible()
    assert controls.statistics.isVisible()
    frame = ThermalFrame(values, np.zeros((2, 2), dtype=np.uint16), {})
    controls.set_frame(frame)
    stats = controls.statistics.text()
    with qtbot.waitSignal(controls.range_changed):
        controls.low.setValue(15)
    controls.high.setValue(25)
    controls.low_slider.setValue(controls.high_slider.value())
    assert controls.low.value() < controls.high.value()
    assert controls.statistics.text() == stats
    controls.show_temperature(1, 0)
    assert "20.00 °C" in controls.spot.text()
    controls.show_temperature(-0.1, 0)
    assert not controls.spot.text()
    controls.show_temperature(1, 1)
    assert "No valid temperature" in controls.spot.text()
    np.testing.assert_array_equal(frame.celsius, values)


def test_fixed_and_auto_scale_between_frames(qtbot: QtBot) -> None:
    controls = ThermalControls()
    qtbot.addWidget(controls)
    raw = np.zeros((1, 2), dtype=np.uint16)
    controls.set_frame(ThermalFrame(np.array([[10.0, 20.0]]), raw, {}))
    controls.low.setValue(12)
    controls.clear()
    controls.set_frame(ThermalFrame(np.array([[30.0, 40.0]]), raw, {}))
    assert controls.limits == (12, 20)
    controls.auto.click()
    assert controls.limits == (30, 40)
    controls.keep_scale.setChecked(False)
    controls.set_frame(ThermalFrame(np.array([[-5.0, -5.0]]), raw, {}))
    assert controls.low.value() <= -5 < controls.high.value()


def test_dialog_browses_csq_and_rejects_nonradiometric_image(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "sample.csq"
    path.write_bytes(fff() * 3)
    dialog = ThermalDialog()
    qtbot.addWidget(dialog)
    dialog.open_path(path)
    qtbot.waitUntil(lambda: dialog._thread is None)
    assert dialog.source is not None and len(dialog.source) == 3
    assert dialog.controls.frame is not None
    assert not dialog.preview.image.isNull()
    assert dialog.extract.isEnabled()
    dialog.next.click()
    qtbot.waitUntil(lambda: dialog._thread is None)
    assert dialog.index == 1
    assert dialog.frame_number.value() == 2
    dialog.frame_slider.setValue(3)
    qtbot.waitUntil(lambda: dialog._thread is None)
    assert dialog.index == 2
    jpeg = tmp_path / "radiometric.jpg"
    jpeg.write_bytes(radiometric_jpeg(fff()))
    dialog.open_path(jpeg)
    qtbot.waitUntil(lambda: dialog._thread is None)
    assert dialog.source.path == jpeg
    assert not dialog.extract.isEnabled()
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"invalid")
    dialog.open_path(bad)
    qtbot.waitUntil(lambda: dialog._thread is None)
    assert "Could not read" in dialog.status.text()
    assert dialog.source.path == jpeg  # A failed open preserves the previous frame.


def test_dialog_cancels_read_before_it_can_be_destroyed(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()

    def read(path: Path, cancel: threading.Event, progress: object) -> None:
        started.set()
        cancel.wait(5)

    monkeypatch.setattr("labelme._widgets.thermal.ThermalSource", read)
    dialog = ThermalDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.open_path(Path("test.csq"))
    qtbot.waitUntil(started.is_set)
    dialog.close()
    assert dialog.isVisible()
    qtbot.waitUntil(lambda: dialog._thread is None)
    assert "cancelled" in dialog.status.text().lower()
    dialog.close()
    assert not dialog.isVisible()


def test_failed_frame_save_cleans_up_partial_output(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.csq"
    source.write_bytes(fff())
    dialog = ThermalDialog()
    qtbot.addWidget(dialog)
    dialog.open_path(source)
    qtbot.waitUntil(lambda: dialog._thread is None)
    monkeypatch.setattr(
        "labelme._widgets.thermal.QtWidgets.QFileDialog.getExistingDirectory",
        lambda *args: str(tmp_path),
    )

    def fail(frame: object, image: Path, *args: object, **kwargs: object) -> None:
        image.write_bytes(b"partial")
        raise OSError("Disk write failed")

    monkeypatch.setattr("labelme._widgets.thermal.save_frame", fail)
    dialog.save.click()
    assert "Disk write failed" in dialog.status.text()
    assert not (tmp_path / "extracted_frames").exists()
    assert source.exists()


def test_analysis_units_measurements_delta_and_display(qtbot: QtBot) -> None:
    controls = ThermalControls()
    qtbot.addWidget(controls)
    frame = ThermalFrame(
        np.array([[10.0, 20.0], [30.0, 40.0]]), np.zeros((2, 2), dtype=np.uint16), {}
    )
    controls.set_frame(frame, (10, 40))
    options = controls.options
    options.add_measurement("point", [[0, 0]])
    options.add_measurement("point", [[1, 1]])
    options.reference.setCurrentIndex(1)
    assert options.table.item(1, 4).text() == "+30.00"
    options.units.setCurrentIndex(options.units.findData("F"))
    assert controls.low.value() == 50
    assert controls.high.value() == 104
    assert controls.limits == (10, 40)
    assert options.table.item(1, 4).text() == "+54.00"
    assert "°F" in controls.statistics.text()
    controls.show_temperature(1, 1)
    assert "104.00 °F" in controls.spot.text()
    options.palette.setCurrentIndex(options.palette.findData("white_hot"))
    assert options.image().pixelColor(1, 1).red() == 255
    options.isotherm.setCurrentIndex(options.isotherm.findData("above"))
    options.threshold.setValue(86)
    assert "50.00%" in options.coverage.text()
    assert options.image().pixelColor(1, 1).green() == 255
    assert options.image().pixelColor(1, 1).red() == 0
    np.testing.assert_array_equal(frame.celsius, [[10, 20], [30, 40]])


def test_parameters_state_restore_and_line_profile(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "sample.fff"
    path.write_bytes(fff())
    frame = ThermalSource(path).read(0)
    controls = ThermalControls()
    qtbot.addWidget(controls)
    controls.set_frame(frame)
    options = controls.options
    options.parameters["emissivity"].setValue(0.5)
    options.apply_parameters.click()
    assert options.overrides["emissivity"] == 0.5
    assert not np.allclose(controls.frame.celsius, frame.celsius)
    options.add_measurement("line", [[0.1, 0.1], [1.1, 1.1]])
    options.table.selectRow(0)
    assert options.profile_export.isEnabled()
    assert (
        options.profile.pixmap() is not None and not options.profile.pixmap().isNull()
    )
    state = options.state()
    other = ThermalControls()
    qtbot.addWidget(other)
    other.options.restore(state)
    other.set_frame(frame)
    np.testing.assert_allclose(other.frame.celsius, controls.frame.celsius)
    assert other.options.measurements == options.measurements
    options.reset_parameters.click()
    np.testing.assert_allclose(controls.frame.celsius, frame.celsius)


def test_viewer_mouse_measurement_uses_native_sensor_coordinates(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "sample.csq"
    path.write_bytes(fff(np.arange(100, dtype=np.uint16).reshape(10, 10) + 18000))
    dialog = ThermalDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.open_path(path)
    qtbot.waitUntil(lambda: dialog._thread is None)
    dialog.measurement_tool.setCurrentIndex(dialog.measurement_tool.findData("point"))
    from PySide6 import QtCore

    qtbot.mouseClick(
        dialog.preview,
        QtCore.Qt.MouseButton.LeftButton,
        pos=dialog.preview.rect().center(),
    )
    assert len(dialog.controls.options.measurements) == 1
    x, y = dialog.controls.options.measurements[0].points[0]
    assert 4 <= x <= 6 and 4 <= y <= 6
