from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6 import QtGui
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._shape import Shape
from labelme._widgets._shape_render import render_shape

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


def test_tab_skips_third_of_four_same_class_boxes_and_space_advances_image(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    win._docks.label_list.clear()
    win._load_shapes(
        [
            Shape(
                label="animal",
                shape_type="rectangle",
                points=np.array([[10.0 + i, 10.0], [30.0 + i, 30.0]]),
            )
            for i in range(4)
        ]
    )
    win._toggle_bounding_box_quick_edit(True)
    original_path = win._image_path
    skipped_points = canvas.shapes[2].points.copy()
    for _ in range(2):
        click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
        click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    assert canvas.selected_shapes == [canvas.shapes[2]]
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    assert canvas.selected_shapes == [canvas.shapes[3]]
    assert canvas.hasFocus()
    assert win._image_path == original_path
    np.testing.assert_array_equal(canvas.shapes[2].points, skipped_points)
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    click_canvas_fraction(qtbot, canvas, (0.9, 0.9))
    assert canvas.selected_shapes == []
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)  # No remaining box: stay on this image.
    assert win._image_path == original_path
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    shapes = json.loads(Path(original_path).with_suffix(".json").read_text())["shapes"]
    np.testing.assert_allclose(shapes[0]["points"], [[20, 20], [80, 80]], atol=1)
    np.testing.assert_allclose(shapes[1]["points"], [[20, 20], [80, 80]], atol=1)
    np.testing.assert_array_equal(shapes[2]["points"], skipped_points)
    np.testing.assert_allclose(shapes[3]["points"], [[30, 30], [90, 90]], atol=1)


@pytest.mark.parametrize("partial", [False, True])
def test_tab_leaves_boxes_unchanged_and_does_not_add_undo_history(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
    partial: bool,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    first, point, second = canvas.shapes
    first_points = first.points.copy()
    original_path = win._image_path
    backups = len(canvas.shape_backups)
    if partial:
        click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
        assert canvas._quick_edit_corner is not None
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    assert canvas.selected_shapes == [second]  # The intervening point is ignored.
    assert canvas._quick_edit_corner is None
    assert not win._is_changed
    assert len(canvas.shape_backups) == backups
    np.testing.assert_array_equal(first.points, first_points)
    np.testing.assert_array_equal(point.points, [[50, 50]])
    assert (first.label, first.group_id, first.description, first.flags) == (
        "first",
        7,
        "keep me",
        {"occluded": True},
    )
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    assert canvas.selected_shapes == []
    assert win._image_path == original_path
    assert not win._is_changed
    assert len(canvas.shape_backups) == backups
    assert not Path(original_path).with_suffix(".json").exists()


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_active_box_is_thin_dashed_and_unfilled_until_skipped(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
    scale: float,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    canvas.scale = scale
    first, _, second = canvas.shapes
    background = QtGui.QColor(32, 48, 64)

    def render(shape: Shape) -> QtGui.QImage:
        image = QtGui.QImage(200, 200, QtGui.QImage.Format.Format_ARGB32)
        image.fill(background)
        painter = QtGui.QPainter(image)
        try:
            render_shape(
                painter, shape, canvas._render_context(shape, highlighted=False)
            )
        finally:
            painter.end()
        return image

    active = render(first)
    # The middle of the animal remains unobscured even with Fill Editing enabled.
    assert canvas._fill_editing
    assert active.pixelColor(int(20 * scale), int(20 * scale)) == background
    start, end = int(16 * scale), int(24 * scale)
    edge_y = int(10 * scale)
    edge = [active.pixelColor(x, edge_y) for x in range(start, end)]
    assert background in edge  # Gaps between dashes.
    assert any(color != background for color in edge)
    # Only one screen-pixel row is occupied away from the corner handles.
    assert all(
        active.pixelColor(x, edge_y - 1) == background for x in range(start, end)
    )
    assert all(
        active.pixelColor(x, edge_y + 1) == background for x in range(start, end)
    )

    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    assert canvas.selected_shapes == [second]
    skipped = render(first)
    assert all(skipped.pixelColor(x, edge_y) != background for x in range(start, end))
    second_image = render(second)
    assert second_image.pixelColor(int(50 * scale), int(50 * scale)) == background
    win._toggle_bounding_box_quick_edit(False)
    canvas.select_shapes([first])
    normal = render(first)
    assert normal.pixelColor(int(20 * scale), int(20 * scale)) != background
    win.mark_clean()


@pytest.mark.parametrize("key", [Qt.Key.Key_Tab, Qt.Key.Key_Backtab])
def test_shift_tab_reselects_previous_box_without_reverting_edits(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
    key: Qt.Key,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    first, point, second = canvas.shapes
    path = Path(win._image_path)
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    edited_points = first.points.copy()
    history_size = len(canvas.shape_backups)
    assert canvas.selected_shapes == [second]
    # Going back cancels only this unfinished preview, not the first box's edit.
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    qtbot.keyClick(canvas, key, Qt.KeyboardModifier.ShiftModifier)
    assert canvas.selected_shapes == [first]
    assert canvas._quick_edit_corner is None
    assert canvas.hasFocus()
    assert len(canvas.shape_backups) == history_size
    assert win._is_changed
    np.testing.assert_array_equal(first.points, edited_points)
    np.testing.assert_array_equal(point.points, [[50, 50]])
    # At the first box, stay there rather than wrapping or opening another image.
    qtbot.keyClick(canvas, key, Qt.KeyboardModifier.ShiftModifier)
    assert canvas.selected_shapes == [first]
    assert Path(win._image_path) == path
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    assert canvas.selected_shapes == []
    qtbot.keyClick(canvas, key, Qt.KeyboardModifier.ShiftModifier)
    assert canvas.selected_shapes == [second]
    assert len(canvas.shape_backups) == history_size
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    saved = json.loads(path.with_suffix(".json").read_text())["shapes"]
    np.testing.assert_array_equal(saved[0]["points"], edited_points)


def test_shift_tab_navigation_on_unchanged_boxes_stays_clean(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    first = canvas.shapes[0]
    history_size = len(canvas.shape_backups)
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    qtbot.keyClick(canvas, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert canvas.selected_shapes == [first]
    assert not win._is_changed
    assert len(canvas.shape_backups) == history_size


def test_quick_edit_visits_nearby_boxes_and_keeps_route_after_edits_and_undo(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    # File order deliberately jumps between opposite sides of the image.
    centers = [
        ("far_top", 80, 10),
        ("start", 10, 10),
        ("far_bottom", 80, 20),
        ("near_bottom", 20, 20),
        ("near_top", 20, 10),
    ]
    win._docks.label_list.clear()
    win._load_shapes(
        [
            Shape(
                label=label,
                shape_type="rectangle",
                points=np.array([[x - 3.0, y - 3.0], [x + 3.0, y + 3.0]]),
            )
            for label, x, y in centers
        ]
    )
    win._toggle_bounding_box_quick_edit(True)
    original_shapes = list(canvas.shapes)
    assert canvas.selected_shapes[0].label == "start"
    # Moving the first box to the other side must not change the planned route.
    click_canvas_fraction(qtbot, canvas, (0.85, 0.85))
    click_canvas_fraction(qtbot, canvas, (0.95, 0.95))
    assert canvas.selected_shapes[0].label == "near_top"
    win.undo_shape_edit()
    assert canvas.selected_shapes[0].label == "near_top"
    # Undo replaces the Shape objects, but navigation still uses the same route.
    assert canvas.shapes[1] is not original_shapes[1]
    seen = [canvas.selected_shapes[0].label]
    for _ in range(3):
        qtbot.keyClick(canvas, Qt.Key.Key_Tab)
        seen.append(canvas.selected_shapes[0].label)
    assert seen == ["near_top", "near_bottom", "far_bottom", "far_top"]
    for expected in reversed(["start", *seen[:-1]]):
        qtbot.keyClick(canvas, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        assert canvas.selected_shapes[0].label == expected
    # Returning to the start allows editing it again without rearranging JSON.
    click_canvas_fraction(qtbot, canvas, (0.85, 0.85))
    click_canvas_fraction(qtbot, canvas, (0.95, 0.95))
    path = Path(win._image_path)
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    saved = json.loads(path.with_suffix(".json").read_text())["shapes"]
    assert [shape["label"] for shape in saved] == [label for label, _, _ in centers]
    np.testing.assert_allclose(saved[1]["points"], [[85, 85], [95, 95]], atol=1)


def test_nearby_order_is_deterministic_when_box_centres_tie(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    win._docks.label_list.clear()
    win._load_shapes(
        [
            Shape(
                label=label,
                shape_type="rectangle",
                points=np.array(points, dtype=float),
            )
            for label, points in [
                ("right", [[55, 5], [65, 15]]),
                ("left", [[35, 5], [45, 15]]),
                ("left_duplicate", [[35, 5], [45, 15]]),
            ]
        ]
    )
    win._toggle_bounding_box_quick_edit(True)
    assert canvas.selected_shapes[0].label == "left"
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    assert canvas.selected_shapes[0].label == "left_duplicate"
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    assert canvas.selected_shapes[0].label == "right"
    win._toggle_bounding_box_quick_edit(False)
    win._toggle_bounding_box_quick_edit(True)
    assert canvas.selected_shapes[0].label == "left"


def test_other_boxes_are_hidden_during_first_pass_and_return_for_review(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    canvas.scale = 1.0
    first, point, second = canvas.shapes
    point.visible = False
    canvas.set_show_labels(True)
    canvas.set_show_center_dots(True)
    background = QtGui.QColor(32, 48, 64)
    original_points = [shape.points.copy() for shape in canvas.shapes]
    history_size = len(canvas.shape_backups)

    def render() -> QtGui.QImage:
        image = QtGui.QImage(140, 100, QtGui.QImage.Format.Format_ARGB32)
        image.fill(background)
        painter = QtGui.QPainter(image)
        try:
            canvas._draw_committed_shapes_layer(painter)
            canvas._draw_center_dots_layer(painter)
        finally:
            painter.end()
        return image

    image = render()
    assert image.pixelColor(20, 20) != background  # Current box's centre dot.
    # The other box's outline, handles, label, fill, and centre dot all disappear.
    assert all(
        image.pixelColor(x, y) == background
        for x in range(35, 130)
        for y in range(20, 68)
    )
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    image = render()
    assert image.pixelColor(20, 20) == background
    assert image.pixelColor(10, 20) == background
    assert image.pixelColor(10, 10) == background
    assert image.pixelColor(50, 50) != background
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    image = render()
    assert image.pixelColor(20, 20) != background
    assert image.pixelColor(50, 50) != background
    qtbot.keyClick(canvas, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    review = render()
    assert review.pixelColor(20, 20) == background
    assert review.pixelColor(50, 50) != background
    assert (
        canvas._render_context(second, highlighted=False).line_style
        == Qt.PenStyle.DashLine
    )
    assert (
        canvas._render_context(first, highlighted=False).line_style
        == Qt.PenStyle.SolidLine
    )
    qtbot.keyClick(canvas, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    review = render()
    assert review.pixelColor(20, 20) != background
    assert review.pixelColor(50, 50) == background
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    review = render()
    assert review.pixelColor(20, 20) == background
    assert review.pixelColor(50, 50) != background
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    overview = render()
    assert overview.pixelColor(20, 20) != background
    assert overview.pixelColor(50, 50) != background
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    restored = render()
    assert restored.pixelColor(20, 20) != background
    assert restored.pixelColor(50, 50) != background
    assert first.visible and second.visible
    assert not point.visible
    assert not win._is_changed
    assert len(canvas.shape_backups) == history_size
    for shape, original in zip(canvas.shapes, original_points, strict=True):
        np.testing.assert_array_equal(shape.points, original)


@pytest.mark.parametrize("finish_with_tab", [False, True])
def test_finishing_last_box_shows_all_and_next_image_starts_with_one_box(
    quick_edit_win: MainWindow,
    qtbot: QtBot,
    finish_with_tab: bool,
) -> None:
    win = quick_edit_win
    canvas = win._canvas_widgets.canvas
    first, _, second = canvas.shapes
    path = Path(win._image_path)
    # The next image has the same boxes, so review state must reset per image.
    path.with_name("b.json").write_text(
        json.dumps(
            {
                "version": "6.3.1",
                "flags": {},
                "imagePath": "b.png",
                "imageData": None,
                "imageHeight": 100,
                "imageWidth": 100,
                "shapes": [
                    {
                        "label": shape.label,
                        "points": shape.points.tolist(),
                        "shape_type": shape.shape_type,
                        "flags": shape.flags,
                    }
                    for shape in canvas.shapes
                ],
            }
        )
    )
    qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    assert canvas.selected_shapes == [second]
    assert not canvas._should_render_shape(first)
    if finish_with_tab:
        qtbot.keyClick(canvas, Qt.Key.Key_Tab)
    else:
        click_canvas_fraction(qtbot, canvas, (0.4, 0.4))
        click_canvas_fraction(qtbot, canvas, (0.7, 0.7))
    assert canvas.selected_shapes == []
    assert canvas._should_render_shape(first)
    assert canvas._should_render_shape(second)
    assert Path(win._image_path) == path
    # Revisiting isolates the selected box; finishing restores the overview.
    qtbot.keyClick(canvas, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert canvas.selected_shapes == [second]
    assert not canvas._should_render_shape(first)
    click_canvas_fraction(qtbot, canvas, (0.4, 0.4))
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    assert canvas._should_render_shape(first)
    assert canvas._should_render_shape(second)
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert Path(win._image_path).name == "b.png"
    assert canvas.selected_shapes == [canvas.shapes[0]]
    assert canvas._should_render_shape(canvas.shapes[0])
    assert not canvas._should_render_shape(canvas.shapes[2])
