from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._pose import SkeletonTemplate
from labelme._widgets.canvas import _CanvasMode

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import drag_canvas
from .conftest import image_to_widget_pos
from .conftest import show_window_and_wait_for_imagedata


@pytest.fixture()
def skeleton_win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[MainWindow]:
    for name in ("a", "b"):
        Image.new("RGB", (100, 100)).save(tmp_path / f"{name}.png")
    win = main_win(file_or_dir=tmp_path, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot, win)
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Discard,
    )
    win._start_quick_skeleton_drawing(
        SkeletonTemplate(
            label="rat",
            keypoints=("snout", "tail_base"),
            edges=((0, 1),),
            positions=np.array([(0.3, 0.3), (0.7, 0.6)]),
            flip_idx=(0, 1),
        )
    )
    yield win
    win.mark_clean()


def _draw(win: MainWindow, qtbot: QtBot) -> None:
    canvas = win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    click_canvas_fraction(qtbot, canvas, (0.7, 0.6))
    assert canvas.skeleton_drawing_mode == "bbox"
    drag_canvas(
        qtbot,
        canvas,
        QtCore.Qt.MouseButton.LeftButton,
        image_to_widget_pos(canvas, QtCore.QPointF(10, 10)),
        image_to_widget_pos(canvas, QtCore.QPointF(90, 90)),
    )


def test_finishing_one_skeleton_is_immediately_ready_for_another(
    skeleton_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    for count in (1, 2):
        _draw(win, qtbot)
        assert len(canvas.shapes) == count
        assert canvas.is_drawing_skeleton
        assert canvas.skeleton_drawing_mode == "nodes"
        assert canvas.next_skeleton_node_name == "snout"
        assert canvas.skeleton_drawing().points == ()
        assert win._quick_skeleton_template is not None
        assert win._skeleton_drawing_toolbar.isVisible()
        assert Path(win._image_path).name == "a.png"
    assert all(s.shape_type == "skeleton" and s.label == "rat" for s in canvas.shapes)


def test_e_toggles_edit_mode_and_one_node_edit_resumes_placement(
    skeleton_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    _draw(win, qtbot)
    shape = canvas.shapes[0]
    original = shape.points.copy()
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_E)
    assert canvas.mode == _CanvasMode.EDIT
    assert not canvas.is_drawing_skeleton
    assert canvas.selected_shapes == [shape]
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_E)
    assert canvas.is_drawing_skeleton
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_E)
    start = image_to_widget_pos(canvas, QtCore.QPointF(30, 30))
    qtbot.mouseMove(canvas, start)
    drag_canvas(
        qtbot,
        canvas,
        QtCore.Qt.MouseButton.LeftButton,
        start,
        image_to_widget_pos(canvas, QtCore.QPointF(35, 35)),
    )
    assert (shape.points != original).any()
    assert canvas.is_drawing_skeleton
    assert canvas.next_skeleton_node_name == "snout"
    assert win._quick_skeleton_template is not None
    _draw(win, qtbot)
    assert len(canvas.shapes) == 2


@pytest.mark.parametrize("editing", [False, True])
def test_space_saves_finished_skeletons_and_reuses_template_on_next_image(
    skeleton_win: MainWindow,
    qtbot: QtBot,
    editing: bool,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    win._actions.toggle_keep_prev_mode.setChecked(True)
    path = Path(win._image_path)
    _draw(win, qtbot)
    click_canvas_fraction(qtbot, canvas, (0.4, 0.4))  # An unfinished second animal.
    if editing:
        qtbot.keyClick(canvas, QtCore.Qt.Key.Key_E)
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    saved = json.loads(path.with_suffix(".json").read_text())
    assert len(saved["shapes"]) == 1
    assert saved["shapes"][0]["shape_type"] == "skeleton"
    assert not canvas.shapes  # Keep Previous must not copy the old animals.
    assert canvas.is_drawing_skeleton
    assert canvas.next_skeleton_node_name == "snout"
    assert canvas.skeleton_drawing().points == ()
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_Space)  # End of list stays here.
    assert Path(win._image_path).name == "b.png"
    assert not path.with_name("b.json").exists()


def test_space_save_failure_keeps_current_image_and_draft(
    skeleton_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    path = Path(win._image_path)
    _draw(win, qtbot)
    click_canvas_fraction(qtbot, canvas, (0.4, 0.4))
    save = win.save_labels
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_Space)
    assert Path(win._image_path) == path
    assert win._is_changed
    assert len(canvas.skeleton_drawing().points) == 1
    monkeypatch.setattr(win, "save_labels", save)
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    assert len(json.loads(path.with_suffix(".json").read_text())["shapes"]) == 1


@pytest.mark.parametrize("editing", [False, True])
def test_escape_or_switching_tools_stops_repeating_skeleton_mode(
    skeleton_win: MainWindow,
    qtbot: QtBot,
    editing: bool,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    _draw(win, qtbot)
    template = win._quick_skeleton_template
    if editing:
        qtbot.keyClick(canvas, QtCore.Qt.Key.Key_E)
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_Escape)
    assert win._quick_skeleton_template is None
    assert not canvas.is_drawing_skeleton
    assert len(canvas.shapes) == 1
    win._start_quick_skeleton_drawing(template)
    win._switch_canvas_mode(edit=False, create_mode="rectangle")
    assert win._quick_skeleton_template is None
    assert not canvas.is_drawing_skeleton
    assert canvas.create_mode == "rectangle"


@pytest.mark.parametrize("editing", [False, True])
def test_manual_file_selection_exits_quick_skeleton_mode(
    skeleton_win: MainWindow,
    qtbot: QtBot,
    editing: bool,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    _draw(win, qtbot)
    if editing:
        qtbot.keyClick(canvas, QtCore.Qt.Key.Key_E)
    win.mark_clean()
    win._docks.file_list.setCurrentRow(1)
    assert Path(win._image_path).name == "b.png"
    assert win._quick_skeleton_template is None
    assert not canvas.is_drawing_skeleton


def test_space_skips_an_empty_draft_without_creating_json(
    skeleton_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    path = Path(win._image_path)
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_E)  # No completed shape to edit yet.
    assert len(canvas.skeleton_drawing().points) == 1
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    assert not path.with_suffix(".json").exists()
    assert canvas.is_drawing_skeleton
    assert canvas.skeleton_drawing().points == ()


def test_ctrl_z_undoes_draft_nodes_without_removing_completed_animals(
    skeleton_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    _draw(win, qtbot)
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    qtbot.keyClick(
        canvas, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier
    )
    assert len(canvas.shapes) == 1
    assert canvas.is_drawing_skeleton
    assert canvas.skeleton_drawing().points == ()
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    click_canvas_fraction(qtbot, canvas, (0.7, 0.6))
    qtbot.keyClick(
        canvas, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier
    )
    assert len(canvas.shapes) == 1
    assert canvas.skeleton_drawing_mode == "nodes"
    assert len(canvas.skeleton_drawing().points) == 1


def test_failed_autosave_keeps_completed_animal_dirty_for_space_retry(
    skeleton_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = skeleton_win
    canvas = win._canvas_widgets.canvas
    win._actions.save_auto.setChecked(True)
    path = Path(win._image_path)
    save = win.save_labels
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    _draw(win, qtbot)
    assert win._is_changed
    assert canvas.is_drawing_skeleton
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_Space)
    assert Path(win._image_path) == path
    assert len(canvas.shapes) == 1
    monkeypatch.setattr(win, "save_labels", save)
    qtbot.keyClick(canvas, QtCore.Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    assert len(json.loads(path.with_suffix(".json").read_text())["shapes"]) == 1
    assert canvas.is_drawing_skeleton
