from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._thermal import ThermalSource
from labelme._thermal import save_frame
from tests.e2e.conftest import MainWinFactory
from tests.thermal_helpers import fff


def test_thermal_scale_preserves_annotations_and_reopens(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = tmp_path / "camera.fff"
    source.write_bytes(fff())
    image = tmp_path / "frame.png"
    frame = ThermalSource(source).read(0)
    save_frame(frame, image, 10, 40, source=str(source), index=0)
    window = main_win(file_or_dir=image, config_overrides={"auto_save": False})
    controls = window._thermal_controls
    assert controls.frame is not None
    assert controls.limits == (10, 40)
    assert not window._actions.brightness_contrast.isEnabled()
    shape = Shape(label="warm", shape_type="point", points=np.array([[1.0, 1.0]]))
    window._load_shapes([shape])
    canvas = window._canvas_widgets.canvas
    old_pixmap = canvas.pixmap.cacheKey()
    controls.low.setValue(20)
    canvas.select_shapes([shape])
    assert controls.options.table.rowCount() == 1
    controls.options.palette.setCurrentIndex(
        controls.options.palette.findData("black_hot")
    )
    controls.options.units.setCurrentIndex(controls.options.units.findData("F"))
    controls.options.parameters["emissivity"].setValue(0.8)
    controls.options.apply_parameters.click()
    temperatures = controls.frame.celsius.copy()
    assert canvas.shapes == [shape]
    assert canvas.pixmap.cacheKey() != old_pixmap
    assert window._is_changed
    label = tmp_path / "frame.json"
    assert window.save_labels(str(label))
    assert json.loads(label.read_text())["thermal_display_celsius"] == [20, 40]
    window._is_changed = False
    ordinary = tmp_path / "ordinary.png"
    Image.new("RGB", (4, 4)).save(ordinary)
    window._load_file(str(ordinary))
    assert controls.frame is None
    assert window._thermal_dock.isHidden()
    window._load_file(str(image))
    assert controls.limits == (20, 40)
    assert controls.frame is not None
    assert controls.options.display.palette == "black_hot"
    assert controls.options.unit == "F"
    assert controls.options.overrides["emissivity"] == 0.8
    np.testing.assert_allclose(controls.frame.celsius, temperatures)
    assert len(canvas.shapes) == 1
    np.testing.assert_array_equal(canvas.shapes[0].points, [[1, 1]])
    assert not window._is_changed
