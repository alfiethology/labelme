from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._shape import Shape

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import show_window_and_wait_for_imagedata


@pytest.fixture()
def quick_edit_win(
    main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path
) -> MainWindow:
    for name in ("a", "b"):
        Image.new("RGB", (100, 100)).save(tmp_path / f"{name}.png")
    win = main_win(file_or_dir=tmp_path, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot, win)
    win._load_shapes(
        [
            Shape(
                label="first",
                shape_type="rectangle",
                points=np.array([[10.0, 10.0], [30.0, 30.0]]),
                flags={"occluded": True},
                group_id=7,
                description="keep me",
            ),
            Shape(label="point", shape_type="point", points=np.array([[50.0, 50.0]])),
            Shape(
                label="second",
                shape_type="rectangle",
                points=np.array([[40.0, 40.0], [60.0, 60.0]]),
            ),
        ]
    )
    win._bounding_box_quick_edit_action.trigger()
    return win


def test_two_clicks_preserve_metadata_and_advance_only_rectangles(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    first, point, second = canvas.shapes
    original_path = win._image_path
    assert canvas.selected_shapes == [first]
    assert canvas._crosshair_pen().style() == Qt.PenStyle.DotLine
    assert canvas._crosshair_pen().color().getRgb() == (255, 235, 0, 255)
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    np.testing.assert_array_equal(first.points, [[10, 10], [30, 30]])
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    np.testing.assert_allclose(first.points, [[20, 20], [80, 80]], atol=1)
    assert (first.label, first.group_id, first.description, first.flags) == (
        "first",
        7,
        "keep me",
        {"occluded": True},
    )
    assert canvas.selected_shapes == [second]
    np.testing.assert_array_equal(point.points, [[50, 50]])
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    click_canvas_fraction(qtbot, canvas, (0.9, 0.9))
    assert canvas.selected_shapes == []
    assert win._image_path == original_path
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    assert canvas.bounding_box_quick_edit
    data = json.loads(Path(original_path).with_suffix(".json").read_text())
    np.testing.assert_allclose(
        data["shapes"][0]["points"], [[20, 20], [80, 80]], atol=1
    )
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    assert not canvas.bounding_box_quick_edit
    assert not win._bounding_box_quick_edit_action.isChecked()


def test_partial_edit_can_exit_without_changing_shape_and_completed_edit_undoes(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    assert not win._is_changed
    np.testing.assert_array_equal(canvas.shapes[0].points, [[10, 10], [30, 30]])
    win._bounding_box_quick_edit_action.trigger()
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    win.undo_shape_edit()
    np.testing.assert_array_equal(canvas.shapes[0].points, [[10, 10], [30, 30]])
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    win.mark_clean()


def test_save_failure_keeps_current_image(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    original_path = win._image_path
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._image_path == original_path
    assert win._is_changed
    assert canvas.bounding_box_quick_edit
    win.mark_clean()


def test_failed_autosave_stays_dirty_and_blocks_space(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    win._actions.save_auto.setChecked(True)
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    assert win._is_changed
    original_path = win._image_path
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._image_path == original_path
    win.mark_clean()


def test_next_annotated_image_restarts_at_first_rectangle(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    next_json = Path(win._image_path).with_name("b.json")
    assert win.save_labels(label_path=str(next_json))
    data = json.loads(next_json.read_text())
    data["imagePath"] = "b.png"
    next_json.write_text(json.dumps(data))
    # Restore the current image's save destination after creating the fixture.
    win._label_file_path = None
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    assert canvas.selected_shapes == [canvas.shapes[0]]
    assert canvas._quick_edit_index == 0
    assert canvas._quick_edit_corner is None
    click_canvas_fraction(qtbot, canvas, (0.1, 0.1))
    click_canvas_fraction(qtbot, canvas, (0.7, 0.7))
    assert canvas.selected_shapes == [canvas.shapes[2]]
    win.mark_clean()
