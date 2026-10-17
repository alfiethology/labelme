from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_edit_menu_toggles_pixel_lock_and_saves_whole_pixel_coordinates(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "image.png"
    Image.new("RGB", (100, 100)).save(image_path)
    win = main_win(file_or_dir=image_path, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot, win)
    monkeypatch.setattr(
        win._label_dialog, "popup", lambda text: ("target", {}, None, "")
    )
    canvas = win._canvas_widgets.canvas
    action = win._actions.lock_cursor_to_pixels
    assert action in win._menus.edit.actions()
    assert action.isCheckable()
    assert not action.isChecked()
    action.trigger()
    assert action.isChecked()
    assert canvas._lock_cursor_to_pixels

    for create_action, positions in (
        (win._actions.create_point_mode, [(20.25, 15.75)]),
        (win._actions.create_rectangle_mode, [(30.2, 25.8), (75.6, 65.2)]),
    ):
        create_action.trigger()
        canvas.scale = 0.65
        for x, y in positions:
            pos = (QPointF(x, y) + canvas._compute_image_origin_offset()) * canvas.scale
            canvas.mousePressEvent(
                QtGui.QMouseEvent(
                    QtCore.QEvent.Type.MouseButtonPress,
                    pos,
                    pos,
                    Qt.MouseButton.LeftButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                )
            )

    label_path = tmp_path / "image.json"
    assert win.save_labels(label_path=str(label_path))
    win.mark_clean()
    shapes = json.loads(label_path.read_text())["shapes"]
    assert len(shapes) == 2
    assert shapes[0]["points"] == [[20.0, 16.0]]
    assert shapes[1]["points"] == [[30.0, 26.0], [76.0, 65.0]]
    original = [shape.points.copy() for shape in canvas.shapes]
    action.trigger()
    assert not action.isChecked()
    assert not canvas._lock_cursor_to_pixels
    for shape, points in zip(canvas.shapes, original, strict=True):
        np.testing.assert_array_equal(shape.points, points)
