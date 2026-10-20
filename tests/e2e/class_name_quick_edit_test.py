from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._pose import SkeletonTemplate
from labelme._pose import make_skeleton_shape
from labelme._shape import Shape
from labelme._shape import ShapeType
from labelme._widgets.class_name_quick_edit import ClassNameQuickEditPopup

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import image_to_widget_pos
from .conftest import show_window_and_wait_for_imagedata


def _shape(kind: ShapeType = "rectangle") -> Shape:
    points = [[10, 10], [30, 30]]
    if kind in ("polygon", "linestrip"):
        points = [[10, 10], [20, 30], [30, 10]]
    elif kind == "oriented_rectangle":
        points = [[10, 10], [30, 10], [30, 30], [10, 30]]
    elif kind == "circle":
        points = [[20, 20], [30, 20]]
    elif kind == "point":
        points = [[20, 20]]
    elif kind == "points":
        points = [[20, 20], [25, 25]]
    shape = Shape(label="old", shape_type=kind, points=np.array(points), closed=True)
    if kind == "mask":
        shape.mask = np.ones((21, 21), dtype=bool)
    if kind == "skeleton":
        shape = make_skeleton_shape(
            skeleton=SkeletonTemplate(
                label="old",
                keypoints=("head", "tail"),
                edges=((0, 1),),
                positions=np.array([[0.3, 0.3], [0.7, 0.7]]),
                flip_idx=(0, 1),
            ),
            bounds=(10, 10, 30, 30),
        )
    shape.flags = {"occluded": True}
    shape.group_id = 7
    shape.description = "Preserve this description"
    shape.other_data["custom"] = {"keep": 42}
    return shape


@pytest.fixture()
def name_edit_win(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> MainWindow:
    for name in ("a", "b", "c"):
        Image.new("RGB", (100, 100)).save(tmp_path / f"{name}.png")
    (tmp_path / "b.json").write_text(
        json.dumps(
            {
                "imagePath": "b.png",
                "imageData": None,
                "imageWidth": 100,
                "imageHeight": 100,
                "shapes": [
                    {"label": "new class", "shape_type": "point", "points": [[50, 50]]}
                ],
                "flags": {},
            }
        )
    )
    win = main_win(file_or_dir=tmp_path, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot, win)
    other = Shape(
        label="other", shape_type="rectangle", points=np.array([[60, 60], [90, 90]])
    )
    win._load_shapes([_shape(), other])
    win._class_name_quick_edit_action.trigger()
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Discard,
    )
    return win


def _choose(
    monkeypatch: pytest.MonkeyPatch, name: str | None = "new class"
) -> list[list[str]]:
    offered: list[list[str]] = []

    def select(popup: ClassNameQuickEditPopup) -> int:
        offered.append(
            [popup.results.item(row).text() for row in range(popup.results.count())]
        )
        items = popup.results.findItems(name or "", Qt.MatchFlag.MatchExactly)
        if name is not None and items:
            popup._choose(items[0])
        else:
            popup.reject()
        return popup.result()

    monkeypatch.setattr(ClassNameQuickEditPopup, "exec", select)
    return offered


@pytest.mark.parametrize(
    "kind",
    [
        "polygon",
        "rectangle",
        "oriented_rectangle",
        "point",
        "points",
        "circle",
        "line",
        "linestrip",
        "mask",
        "skeleton",
    ],
)
def test_one_click_relabels_any_shape_without_changing_metadata_or_geometry(
    name_edit_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    kind: ShapeType,
) -> None:
    win = name_edit_win
    canvas = win._canvas_widgets.canvas
    shape = _shape(kind)
    win._docks.label_list.clear()
    win._load_shapes([shape])
    original = shape.copy()
    offered = _choose(monkeypatch)
    path = win._image_path
    click_canvas_fraction(
        qtbot, canvas, (0.2, 0.3) if kind == "linestrip" else (0.2, 0.2)
    )
    assert len(offered) == 1 and "new class" in offered[0]
    assert shape.label == "new class"
    np.testing.assert_array_equal(shape.points, original.points)
    np.testing.assert_array_equal(shape.point_labels, original.point_labels)
    if original.mask is not None:
        np.testing.assert_array_equal(shape.mask, original.mask)
    assert (shape.flags, shape.group_id, shape.description, shape.other_data) == (
        original.flags,
        original.group_id,
        original.description,
        original.other_data,
    )
    assert win._image_path == path
    assert win._is_changed
    assert canvas.selected_shapes == [shape]
    win.mark_clean()


def test_space_saves_and_advances_then_empty_image_can_be_skipped(
    name_edit_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = name_edit_win
    _choose(monkeypatch)
    canvas = win._canvas_widgets.canvas
    assert win._image_path is not None
    first = Path(win._image_path)
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    assert canvas.shapes[1].label == "other"
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._image_path is not None and Path(win._image_path).name == "b.png"
    saved = json.loads(first.with_suffix(".json").read_text())
    assert [shape["label"] for shape in saved["shapes"]] == ["new class", "other"]
    assert win._class_name_quick_edit_active
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._image_path is not None and Path(win._image_path).name == "c.png"
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert Path(win._image_path).name == "c.png"
    assert not first.with_name("c.json").exists()
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    assert not win._class_name_quick_edit_active
    assert not win._class_name_quick_edit_action.isChecked()


@pytest.mark.parametrize("choice", [None, "old"])
def test_cancel_or_current_name_is_a_noop(
    name_edit_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    choice: str | None,
) -> None:
    _choose(monkeypatch, choice)
    canvas = name_edit_win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    assert canvas.shapes[0].label == "old"
    assert not name_edit_win._is_changed
    assert name_edit_win._class_name_quick_edit_active


def test_blank_or_hidden_shape_does_not_open_picker(
    name_edit_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    offered = _choose(monkeypatch)
    canvas = name_edit_win._canvas_widgets.canvas
    canvas.shapes[0].visible = False
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    click_canvas_fraction(qtbot, canvas, (0.95, 0.95))
    assert not offered
    assert not name_edit_win._is_changed


def test_uppermost_shape_is_changed_and_undo_restores_name(
    name_edit_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = name_edit_win
    canvas = win._canvas_widgets.canvas
    top = _shape()
    top.label = "top"
    win._load_shapes([top], replace=False)
    _choose(monkeypatch)
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    assert canvas.shapes[0].label == "old"
    assert canvas.shapes[-1].label == "new class"
    win.undo_shape_edit()
    assert canvas.shapes[-1].label == "top"
    assert win._class_name_quick_edit_active
    win.mark_clean()


@pytest.mark.parametrize("auto_save", [False, True])
def test_save_failure_keeps_current_image_and_space_retries(
    name_edit_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    auto_save: bool,
) -> None:
    win = name_edit_win
    win._actions.save_auto.setChecked(auto_save)
    _choose(monkeypatch)
    original_path = win._image_path
    save = win.save_labels
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    canvas = win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._image_path == original_path
    assert win._is_changed
    monkeypatch.setattr(win, "save_labels", save)
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._image_path != original_path
    assert not win._is_changed


def test_dragging_a_vertex_does_not_change_geometry(
    name_edit_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    _choose(monkeypatch, None)
    canvas = name_edit_win._canvas_widgets.canvas
    original = canvas.shapes[0].points.copy()
    start = image_to_widget_pos(canvas, QPointF(10, 10))
    end = image_to_widget_pos(canvas, QPointF(40, 40))
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=end)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    np.testing.assert_array_equal(canvas.shapes[0].points, original)
    assert not name_edit_win._is_changed


def test_modes_are_exclusive_and_box_tool_has_clearer_name(
    name_edit_win: MainWindow,
) -> None:
    win = name_edit_win
    assert win._bounding_box_quick_edit_action.text() == "Bounding Box Shape Quick Edit"
    win._bounding_box_quick_edit_action.trigger()
    assert not win._class_name_quick_edit_active
    assert win._bounding_box_quick_edit_active
    win._class_name_quick_edit_action.trigger()
    assert win._class_name_quick_edit_active
    assert not win._bounding_box_quick_edit_active
    win._switch_canvas_mode(edit=False, create_mode="point")
    assert not win._class_name_quick_edit_active


@pytest.mark.parametrize("cancel", [False, True])
def test_real_popup_applies_on_one_click_or_cancels_with_escape(
    name_edit_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
) -> None:
    original_exec = ClassNameQuickEditPopup.exec
    errors: list[Exception] = []

    def interact(popup: ClassNameQuickEditPopup) -> None:
        try:
            if cancel:
                qtbot.keyClick(popup.search, Qt.Key.Key_Escape)
                return
            qtbot.keyClicks(popup.search, "new class")
            item = popup.results.item(0)
            assert item is not None and item.text() == "new class"
            qtbot.mouseClick(
                popup.results.viewport(),
                Qt.MouseButton.LeftButton,
                pos=popup.results.visualItemRect(item).center(),
            )
        except Exception as error:
            errors.append(error)
            popup.reject()

    def execute(popup: ClassNameQuickEditPopup) -> int:
        QTimer.singleShot(0, lambda: interact(popup))
        return original_exec(popup)

    monkeypatch.setattr(ClassNameQuickEditPopup, "exec", execute)
    canvas = name_edit_win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    if errors:
        raise errors[0]
    assert canvas.shapes[0].label == ("old" if cancel else "new class")
    assert name_edit_win._class_name_quick_edit_active
    name_edit_win.mark_clean()
