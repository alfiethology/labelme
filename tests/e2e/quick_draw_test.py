from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets.canvas import _CanvasMode
from labelme._widgets.quick_draw_dialog import QuickDrawDialog

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import drag_canvas
from .conftest import image_to_widget_pos
from .conftest import show_window_and_wait_for_imagedata


@pytest.fixture()
def quick_draw_win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[MainWindow]:
    for name in ("a", "b", "c"):
        Image.new("RGB", (100, 100)).save(tmp_path / f"{name}.png")
    win = main_win(file_or_dir=tmp_path, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot, win)
    # Deliberately choose in reverse file order to exercise random navigation.
    monkeypatch.setattr("labelme._app.random.choice", lambda paths: paths[-1])
    # Report assertion failures without blocking teardown on the unsaved dialog.
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Discard,
    )
    yield win
    win.mark_clean()


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    labels: tuple[str, ...] = ("cat", "cat", "dog"),
    shape_type: str = "rectangle",
) -> None:
    def configure(dialog: QuickDrawDialog) -> int:
        dialog.table.setColumnCount(0)
        for row, label in enumerate(labels):
            dialog.add_class()
            item = dialog.table.item(0, row)
            assert item is not None
            item.setText(label)
        dialog.shape_type.setCurrentIndex(dialog.shape_type.findData(shape_type))
        dialog.random_images.setChecked(True)
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(QuickDrawDialog, "exec", configure)


def _write_existing_annotation(image: Path, *, label_path: Path | None = None) -> dict:
    data = {
        "version": "6.3.1",
        "flags": {"reviewed": True},
        "imagePath": image.name,
        "imageData": None,
        "imageHeight": 100,
        "imageWidth": 100,
        "shapes": [
            {
                "label": "existing_rat",
                "points": [[10, 10], [30, 30]],
                "shape_type": "rectangle",
                "group_id": 7,
                "description": "keep this rat",
                "flags": {"occluded": True},
                "rat_id": "original",
            }
        ],
        "dataset_note": "keep image metadata",
    }
    target = label_path or image.with_suffix(".json")
    if target.parent != image.parent:
        data["imagePath"] = os.path.relpath(image, target.parent)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data))
    return data


def _path(win: MainWindow) -> Path:
    assert win._image_path is not None
    return Path(win._image_path)


def _box(win: MainWindow, qtbot: QtBot) -> None:
    canvas = win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))


def test_ordered_labels_repeat_and_wait_for_space_with_random_opt_in(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    monkeypatch.setattr(
        win._label_dialog, "popup", lambda *args: pytest.fail("Label popup")
    )
    win._quick_draw_action.trigger()
    assert _path(win).name == "c.png"
    path = _path(win)
    canvas = win._canvas_widgets.canvas
    assert canvas.create_mode == "rectangle"
    assert "box 1 — cat" in win._quick_draw_progress.text()
    for label in ("cat", "cat"):
        _box(win, qtbot)
        assert canvas.shapes[-1].label == label
        assert not path.with_suffix(".json").exists()
    assert "box 3 — dog" in win._quick_draw_progress.text()
    _box(win, qtbot)
    qtbot.wait(20)  # No deferred automatic navigation after the last listed label.
    assert _path(win) == path
    assert not path.with_suffix(".json").exists()
    assert "box 4 — cat" in win._quick_draw_progress.text()
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert _path(win).name == "b.png"
    data = json.loads(path.with_suffix(".json").read_text())
    assert [shape["label"] for shape in data["shapes"]] == ["cat", "cat", "dog"]
    assert all(shape["shape_type"] == "rectangle" for shape in data["shapes"])
    assert not canvas.shapes
    assert win._quick_draw is not None
    assert not win._is_changed


def test_space_saves_partial_and_skips_empty_without_revisiting(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    win._toggle_quick_draw(True)
    folder = _path(win).parent
    canvas = win._canvas_widgets.canvas
    _box(win, qtbot)
    # Discard an unfinished second box while saving the first one.
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert _path(win).name == "b.png"
    assert len(json.loads((folder / "c.json").read_text())["shapes"]) == 1
    click_canvas_fraction(qtbot, canvas, (0.4, 0.4))
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert _path(win).name == "a.png"
    assert not (folder / "b.json").exists()
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._quick_draw is None
    assert not win._quick_draw_action.isChecked()
    assert not (folder / "a.json").exists()
    # A fresh run includes saved images too, preserving their previous shapes.
    win._toggle_quick_draw(True)
    assert _path(win).name == "c.png"
    assert len(canvas.shapes) == 1


def test_existing_annotations_and_jsons_created_during_run_are_loaded(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    folder = _path(win).parent
    _write_existing_annotation(folder / "c.png")
    win._toggle_quick_draw(True)
    assert _path(win).name == "c.png"
    assert win._canvas_widgets.canvas.shapes[0].label == "existing_rat"
    data = _write_existing_annotation(folder / "b.png")
    before = (folder / "b.json").read_bytes()
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert _path(win).name == "b.png"
    assert win._canvas_widgets.canvas.shapes[0].label == "existing_rat"
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert _path(win).name == "a.png"
    assert (folder / "b.json").read_bytes() == before
    assert json.loads(before)["shapes"] == data["shapes"]


def test_auto_save_is_deferred_and_keep_previous_does_not_copy_boxes(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat", "cat"))
    win._actions.save_auto.setChecked(True)
    win._actions.toggle_keep_prev_mode.setChecked(True)
    win._toggle_quick_draw(True)
    path = _path(win)
    _box(win, qtbot)
    assert win._is_changed
    assert not path.with_suffix(".json").exists()
    _box(win, qtbot)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert _path(win).name == "b.png"
    assert not win._canvas_widgets.canvas.shapes
    assert win._actions.save_auto.isChecked()
    assert win._actions.toggle_keep_prev_mode.isChecked()


def test_save_failure_keeps_image_and_space_retries(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat",))
    win._toggle_quick_draw(True)
    original_path = win._image_path
    assert original_path is not None
    save = win.save_labels
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    _box(win, qtbot)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert win._image_path == original_path
    assert win._is_changed
    assert win._quick_draw is not None
    assert len(win._canvas_widgets.canvas.shapes) == 1
    monkeypatch.setattr(win, "save_labels", save)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert _path(win).name == "b.png"
    assert Path(original_path).with_suffix(".json").exists()


def test_undo_reuses_expected_label_and_empty_skip_creates_no_file(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat", "dog"))
    win._toggle_quick_draw(True)
    path = _path(win)
    _box(win, qtbot)
    win.undo_shape_edit()
    assert "box 1 — cat" in win._quick_draw_progress.text()
    _box(win, qtbot)
    assert win._canvas_widgets.canvas.shapes[0].label == "cat"
    win.undo_shape_edit()
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert _path(win).name == "b.png"
    assert not path.with_suffix(".json").exists()


def test_escape_keeps_completed_boxes_and_cancels_draft(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    win._toggle_quick_draw(True)
    canvas = win._canvas_widgets.canvas
    path = win._image_path
    _box(win, qtbot)
    click_canvas_fraction(qtbot, canvas, (0.4, 0.4))
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    assert win._quick_draw is None
    assert not canvas.is_drawing
    assert win._quick_draw_progress.isHidden()
    assert win._image_path == path
    assert len(canvas.shapes) == 1
    assert win._is_changed
    win.mark_clean()


def test_switching_to_quick_edit_exits_quick_draw(
    quick_draw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    win._toggle_quick_draw(True)
    win._bounding_box_quick_edit_action.trigger()
    assert win._quick_draw is None
    assert win._bounding_box_quick_edit_active
    win._quick_draw_action.trigger()
    assert win._quick_draw is not None
    assert not win._bounding_box_quick_edit_active


def test_cancel_setup_leaves_existing_mode_and_image(
    quick_draw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    win._bounding_box_quick_edit_action.trigger()
    path = win._image_path
    monkeypatch.setattr(
        QuickDrawDialog, "exec", lambda self: QtWidgets.QDialog.DialogCode.Rejected
    )
    win._quick_draw_action.trigger()
    assert win._image_path == path
    assert win._quick_draw is None
    assert not win._quick_draw_action.isChecked()
    assert win._bounding_box_quick_edit_active


def test_setup_rejects_labels_outside_exact_vocabulary(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Image.new("RGB", (100, 100)).save(tmp_path / "a.png")
    win = main_win(
        file_or_dir=tmp_path,
        config_overrides={"validate_label": "exact", "labels": ["cat"]},
    )
    show_window_and_wait_for_imagedata(qtbot, win)
    _configure(monkeypatch, ("dog",))
    errors: list[str] = []
    monkeypatch.setattr(
        win, "show_error_message", lambda title, message: errors.append(message)
    )
    win._toggle_quick_draw(True)
    assert win._quick_draw is None
    assert not win._quick_draw_action.isChecked()
    assert len(errors) == 1 and "dog" in errors[0]


def test_configured_annotation_directory_is_used(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    for name in ("a", "b"):
        Image.new("RGB", (100, 100)).save(images / f"{name}.png")
    output = tmp_path / "labels"
    win = main_win(file_or_dir=images, output_dir=output)
    show_window_and_wait_for_imagedata(qtbot, win)
    _configure(monkeypatch, ("cat",))
    monkeypatch.setattr("labelme._app.random.choice", lambda paths: paths[-1])
    win._toggle_quick_draw(True)
    original_path = _path(win)
    _box(win, qtbot)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert (output / original_path.with_suffix(".json").name).exists()
    assert not original_path.with_suffix(".json").exists()
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Escape)
    win._toggle_quick_draw(True)
    assert _path(win).resolve() == original_path.resolve()


def test_dialog_names_validation_and_removal(qtbot: QtBot) -> None:
    dialog = QuickDrawDialog()
    qtbot.addWidget(dialog)
    assert not dialog.start_button.isEnabled()

    dialog.accept()
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Rejected
    first = dialog.table.item(0, 0)
    assert first is not None
    first.setText(" cat ")
    assert dialog.table.columnCount() == 1
    assert not dialog.random_images.isChecked()
    dialog.add_class()
    assert not dialog.start_button.isEnabled()
    second = dialog.table.item(0, 1)
    assert second is not None
    second.setText("dog")
    assert dialog.start_button.isEnabled()
    assert dialog.label_sequence() == ("cat", "dog")
    dialog.table.selectColumn(1)
    dialog._remove_selected()
    assert dialog.label_sequence() == ("cat",)
    dialog.table.selectColumn(0)
    dialog._remove_selected()
    assert not dialog.start_button.isEnabled()


def test_completing_final_image_saves_and_exits(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat",))
    win._toggle_quick_draw(True)
    folder = _path(win).parent
    for name in ("c", "b", "a"):
        assert _path(win).stem == name
        _box(win, qtbot)
        assert win._quick_draw is not None
        qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
        assert len(json.loads((folder / f"{name}.json").read_text())["shapes"]) == 1
    assert win._quick_draw is None
    assert not win._quick_draw_action.isChecked()
    assert not win._is_changed
    assert _path(win).name == "a.png"


def test_undo_after_failed_save_resumes_the_expected_object(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat", "dog"))
    win._toggle_quick_draw(True)
    path = _path(win)
    save = win.save_labels
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    _box(win, qtbot)
    _box(win, qtbot)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert _path(win) == path
    win.undo_shape_edit()
    assert "box 2 — dog" in win._quick_draw_progress.text()
    monkeypatch.setattr(win, "save_labels", save)
    _box(win, qtbot)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert _path(win) != path
    data = json.loads(path.with_suffix(".json").read_text())
    assert [shape["label"] for shape in data["shapes"]] == ["cat", "dog"]


def test_manual_navigation_stops_quick_draw(
    quick_draw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    win._toggle_quick_draw(True)
    win._docks.file_list.setCurrentRow(0)
    assert _path(win).name == "a.png"
    assert win._quick_draw is None
    assert not win._quick_draw_action.isChecked()


def test_cancel_unsaved_prompt_when_starting_preserves_boxes(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    win._toggle_quick_draw(True)
    path = _path(win)
    _box(win, qtbot)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Escape)
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Cancel,
    )
    win._toggle_quick_draw(True)
    assert win._quick_draw is None
    assert _path(win) == path
    assert len(win._canvas_widgets.canvas.shapes) == 1
    assert win._is_changed
    win.mark_clean()


def test_fully_annotated_folder_is_visited_once_and_skips_keep_jsons_unchanged(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    for image in win.image_list:
        _write_existing_annotation(Path(image))
    before = {
        Path(image).with_suffix(".json"): Path(image).with_suffix(".json").read_bytes()
        for image in win.image_list
    }
    win._toggle_quick_draw(True)
    for expected in ("c.png", "b.png", "a.png"):
        assert _path(win).name == expected
        assert win._quick_draw is not None
        qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert win._quick_draw is None
    assert all(path.read_bytes() == data for path, data in before.items())


def test_dialog_accepts_name_entered_through_table_editor(qtbot: QtBot) -> None:
    dialog = QuickDrawDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    item = dialog.table.item(0, 0)
    assert item is not None
    dialog.table.editItem(item)
    combo = dialog.table.viewport().findChild(
        QtWidgets.QComboBox, options=Qt.FindChildOption.FindDirectChildrenOnly
    )
    assert combo is not None
    editor = combo.lineEdit()
    assert editor is not None
    qtbot.keyClicks(editor, "cat")
    qtbot.waitUntil(dialog.start_button.isEnabled)
    qtbot.mouseClick(dialog.start_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted
    assert dialog.label_sequence() == ("cat",)


def test_empty_image_is_skipped_without_json(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat",))
    win._toggle_quick_draw(True)
    path = _path(win)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert _path(win).name == "b.png"
    assert not path.with_suffix(".json").exists()


def test_name_click_shows_labels_and_allows_new_name(qtbot: QtBot) -> None:
    dialog = QuickDrawDialog(labels=("cat", "dog"))
    qtbot.addWidget(dialog)
    dialog.show()
    item = dialog.table.item(0, 0)
    assert item is not None
    qtbot.mouseClick(
        dialog.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=dialog.table.visualItemRect(item).center(),
    )
    combo = dialog.table.viewport().findChild(
        QtWidgets.QComboBox, options=Qt.FindChildOption.FindDirectChildrenOnly
    )
    assert combo is not None
    qtbot.waitUntil(combo.view().isVisible)
    assert [combo.itemText(i) for i in range(combo.count())] == ["cat", "dog"]
    # Clicking a suggestion commits it and enables Start immediately.
    choice = combo.model().index(1, 0)
    qtbot.mouseClick(
        combo.view().viewport(),
        Qt.MouseButton.LeftButton,
        pos=combo.view().visualRect(choice).center(),
    )
    assert dialog.label_sequence() == ("dog",)
    assert dialog.start_button.isEnabled()
    editor = combo.lineEdit()
    assert editor is not None
    editor.selectAll()
    qtbot.keyClicks(editor, "snake")
    qtbot.waitUntil(dialog.start_button.isEnabled)
    qtbot.mouseClick(dialog.start_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted
    assert dialog.label_sequence() == ("snake",)


def test_setup_suggestions_include_current_label_list_and_unopened_jsons(
    quick_draw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    # The JSON appears after opening the folder, so setup must refresh names.
    (_path(win).parent / "b.json").write_text(
        json.dumps({"shapes": [{"label": "snake"}]})
    )
    label_list = win._docks.unique_label_list
    label_list.add_label_item("cat", (255, 0, 0))
    labels: list[str] = []

    def inspect(dialog: QuickDrawDialog) -> int:
        delegate = dialog.table.itemDelegate()
        assert delegate is not None
        editor = delegate.createEditor(
            dialog, QtWidgets.QStyleOptionViewItem(), dialog.table.model().index(0, 0)
        )
        assert isinstance(editor, QtWidgets.QComboBox)
        labels.extend(editor.itemText(i) for i in range(editor.count()))
        return QtWidgets.QDialog.DialogCode.Rejected

    monkeypatch.setattr(QuickDrawDialog, "exec", inspect)
    win._toggle_quick_draw(True)
    assert set(labels) == {"cat", "snake"}


@pytest.mark.parametrize("random_images", [False, True])
def test_image_order_is_sequential_unless_random_is_checked(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    random_images: bool,
) -> None:
    win = quick_draw_win

    def configure(dialog: QuickDrawDialog) -> int:
        dialog.table.item(0, 0).setText("cat")
        assert not dialog.random_images.isChecked()
        dialog.random_images.setChecked(random_images)
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(QuickDrawDialog, "exec", configure)
    win._toggle_quick_draw(True)
    names = ("c", "b", "a") if random_images else ("a", "b", "c")
    for name in names:
        assert _path(win).stem == name
        qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert win._quick_draw is None


@pytest.mark.parametrize("resize", [False, True])
def test_e_edits_latest_box_once_then_resumes_drawing(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    resize: bool,
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat",))
    win._toggle_quick_draw(True)
    canvas = win._canvas_widgets.canvas
    path = _path(win)
    qtbot.keyClick(canvas, Qt.Key.Key_E)  # Harmless before the first box.
    assert canvas.mode == _CanvasMode.CREATE
    _box(win, qtbot)
    shape = canvas.shapes[-1]
    original = shape.points.copy()
    qtbot.keyClick(canvas, Qt.Key.Key_E)
    assert canvas.mode == _CanvasMode.EDIT
    assert canvas.selected_shapes == [shape]
    start = QPointF(20, 20) if resize else QPointF(50, 50)
    end = start + QPointF(5, 5)
    qtbot.mouseMove(canvas, image_to_widget_pos(canvas, start))
    drag_canvas(
        qtbot,
        canvas,
        Qt.MouseButton.LeftButton,
        image_to_widget_pos(canvas, start),
        image_to_widget_pos(canvas, end),
    )
    assert (shape.points != original).any()
    assert canvas.mode == _CanvasMode.CREATE
    assert win._quick_draw is not None and not win._quick_draw.editing
    assert _path(win) == path
    assert not path.with_suffix(".json").exists()
    _box(win, qtbot)
    assert len(canvas.shapes) == 2
    assert canvas.shapes[-1].label == "cat"
    qtbot.keyClick(canvas, Qt.Key.Key_E)
    assert canvas.selected_shapes == [canvas.shapes[-1]]
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert _path(win) != path
    assert canvas.mode == _CanvasMode.CREATE
    assert not win._quick_draw.editing
    assert len(json.loads(path.with_suffix(".json").read_text())["shapes"]) == 2


@pytest.mark.parametrize("shape_type", ["rectangle", "polygon"])
def test_class_keys_override_latest_shape_and_preserve_default_order(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    shape_type: str,
) -> None:
    win = quick_draw_win
    classes = tuple(f"class_{i}" for i in range(1, 10))
    _configure(monkeypatch, classes, shape_type)
    monkeypatch.setattr(
        win._label_dialog, "popup", lambda *args: pytest.fail("Label popup")
    )
    win._toggle_quick_draw(True)
    canvas = win._canvas_widgets.canvas
    path = _path(win)
    assert canvas.create_mode == shape_type
    qtbot.keyClick(canvas, Qt.Key.Key_9)  # No completed shape yet.

    def draw() -> None:
        if shape_type == "rectangle":
            _box(win, qtbot)
        else:
            for xy in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)):
                click_canvas_fraction(qtbot, canvas, xy)
            qtbot.keyClick(canvas, Qt.Key.Key_Return)
        assert canvas.mode == _CanvasMode.CREATE
        assert canvas.create_mode == shape_type

    draw()
    assert canvas.shapes[-1].label == "class_1"
    for key in range(9, 0, -1):
        qtbot.keyClick(canvas, getattr(Qt.Key, f"Key_{key}"))
        assert canvas.shapes[-1].label == f"class_{key}"
    qtbot.keyClick(canvas, Qt.Key.Key_9)
    assert "9: class_9" in win._quick_draw_progress.text()
    assert "2 — class_2" in win._quick_draw_progress.text()
    win.undo_shape_edit()
    assert len(canvas.shapes) == 1
    assert canvas.shapes[0].label == "class_1"
    qtbot.keyClick(canvas, Qt.Key.Key_9)
    draw()
    assert [shape.label for shape in canvas.shapes] == ["class_9", "class_2"]
    # Class keys during a draft must leave both the draft and previous shape alone.
    click_canvas_fraction(qtbot, canvas, (0.3, 0.3))
    qtbot.keyClick(canvas, Qt.Key.Key_8)
    assert canvas.is_drawing
    assert canvas.shapes[-1].label == "class_2"
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    saved = json.loads(path.with_suffix(".json").read_text())["shapes"]
    assert [shape["label"] for shape in saved] == ["class_9", "class_2"]
    assert all(shape["shape_type"] == shape_type for shape in saved)
    assert canvas.create_mode == shape_type
    draw()
    assert canvas.shapes[-1].label == "class_1"


def test_polygon_e_edit_resumes_polygon_drawing(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat", "dog"), "polygon")
    win._toggle_quick_draw(True)
    canvas = win._canvas_widgets.canvas
    for xy in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)):
        click_canvas_fraction(qtbot, canvas, xy)
    qtbot.keyClick(canvas, Qt.Key.Key_Return)
    shape = canvas.shapes[-1]
    original = shape.points.copy()
    qtbot.keyClick(canvas, Qt.Key.Key_E)
    start = image_to_widget_pos(canvas, QPointF(20, 20))
    qtbot.mouseMove(canvas, start)
    drag_canvas(
        qtbot,
        canvas,
        Qt.MouseButton.LeftButton,
        start,
        image_to_widget_pos(canvas, QPointF(25, 25)),
    )
    assert (shape.points != original).any()
    assert canvas.mode == _CanvasMode.CREATE
    assert canvas.create_mode == "polygon"
    assert win._quick_draw is not None


def test_dialog_has_one_shape_type_and_up_to_nine_class_columns(qtbot: QtBot) -> None:
    dialog = QuickDrawDialog()
    qtbot.addWidget(dialog)
    assert [
        dialog.shape_type.itemData(i) for i in range(dialog.shape_type.count())
    ] == ["rectangle", "polygon"]
    assert dialog.table.rowCount() == 1
    for i in range(9):
        if i:
            dialog.add_class()
        dialog.table.item(0, i).setText(f"class_{i + 1}")
        assert dialog.table.horizontalHeaderItem(i).text() == f"Class {i + 1}"
    assert not dialog.add_button.isEnabled()
    dialog.add_class()
    assert dialog.table.columnCount() == 9
    assert dialog.start_button.isEnabled()
    dialog.table.selectColumn(3)
    dialog._remove_selected()
    assert dialog.add_button.isEnabled()
    assert dialog.table.horizontalHeaderItem(3).text() == "Class 4"
    assert dialog.label_sequence()[3] == "class_5"


def test_unassigned_class_key_does_nothing(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("cat",))
    win._toggle_quick_draw(True)
    canvas = win._canvas_widgets.canvas
    _box(win, qtbot)
    before = len(canvas.shape_backups)
    qtbot.keyClick(canvas, Qt.Key.Key_9)
    assert canvas.shapes[-1].label == "cat"
    assert len(canvas.shape_backups) == before
    assert win._quick_draw is not None


@pytest.mark.parametrize("shape_type", ["rectangle", "polygon"])
@pytest.mark.parametrize("separate_output", [False, True])
def test_quick_draw_adds_shapes_preserves_existing_metadata_and_resets_class_order(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    shape_type: str,
    separate_output: bool,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    for name in ("a", "b"):
        Image.new("RGB", (100, 100)).save(images / f"{name}.png")
    output = tmp_path / "labels" if separate_output else images
    old = _write_existing_annotation(images / "b.png", label_path=output / "b.json")
    _write_existing_annotation(images / "a.png", label_path=output / "a.json")
    win = main_win(
        file_or_dir=images,
        output_dir=output if separate_output else None,
        config_overrides={"auto_save": False},
    )
    show_window_and_wait_for_imagedata(qtbot, win)
    monkeypatch.setattr("labelme._app.random.choice", lambda paths: paths[-1])
    monkeypatch.setattr(
        win._label_dialog, "popup", lambda *args: pytest.fail("Label popup")
    )
    _configure(monkeypatch, ("cat", "dog"), shape_type)
    win._toggle_quick_draw(True)
    canvas = win._canvas_widgets.canvas
    assert _path(win).resolve() == (images / "b.png").resolve()
    assert "1 — cat" in win._quick_draw_progress.text()
    # Before adding a shape, number keys and E must not alter an existing rat.
    qtbot.keyClick(canvas, Qt.Key.Key_2)
    qtbot.keyClick(canvas, Qt.Key.Key_E)
    assert canvas.shapes[0].label == "existing_rat"
    assert canvas.mode == _CanvasMode.CREATE

    def draw() -> None:
        if shape_type == "rectangle":
            _box(win, qtbot)
        else:
            for xy in ((0.4, 0.4), (0.8, 0.4), (0.8, 0.8)):
                click_canvas_fraction(qtbot, canvas, xy)
            qtbot.keyClick(canvas, Qt.Key.Key_Return)

    draw()
    assert [s.label for s in canvas.shapes] == ["existing_rat", "cat"]
    win.undo_shape_edit()
    assert [s.label for s in canvas.shapes] == ["existing_rat"]
    assert "1 — cat" in win._quick_draw_progress.text()
    draw()
    draw()
    assert [s.label for s in canvas.shapes] == ["existing_rat", "cat", "dog"]
    qtbot.keyClick(canvas, Qt.Key.Key_1)
    assert canvas.shapes[-1].label == "cat"
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    saved = json.loads((output / "b.json").read_text())
    assert len(saved["shapes"]) == 3
    for key, value in old["shapes"][0].items():
        assert saved["shapes"][0][key] == value
    assert saved["flags"] == old["flags"]
    assert saved["dataset_note"] == old["dataset_note"]
    assert all(s["shape_type"] == shape_type for s in saved["shapes"][1:])
    assert _path(win).resolve() == (images / "a.png").resolve()
    assert "1 — cat" in win._quick_draw_progress.text()
    draw()
    assert canvas.shapes[-1].label == "cat"
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._quick_draw is None


def test_malformed_existing_json_stops_quick_draw_without_overwriting(
    quick_draw_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    path = _path(win).parent / "c.json"
    path.write_text("invalid annotation")
    errors = []
    monkeypatch.setattr(
        win, "_show_file_open_error", lambda **kwargs: errors.append(kwargs)
    )
    win._toggle_quick_draw(True)
    assert win._quick_draw is None
    assert errors
    assert path.read_text() == "invalid annotation"


@pytest.mark.parametrize("random_images", [False, True])
def test_starting_from_selected_image_uses_remaining_list_or_random_whole_list(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    random_images: bool,
) -> None:
    win = quick_draw_win
    win._docks.file_list.setCurrentRow(1)
    assert _path(win).name == "b.png"

    def configure(dialog: QuickDrawDialog) -> int:
        dialog.table.item(0, 0).setText("rat")
        dialog.random_images.setChecked(random_images)
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(QuickDrawDialog, "exec", configure)
    win._toggle_quick_draw(True)
    expected = ("c.png", "b.png", "a.png") if random_images else ("b.png", "c.png")
    for name in expected:
        assert _path(win).name == name
        qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert win._quick_draw is None


def test_clicking_visited_image_then_restarting_resumes_from_it(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, ("rat",))
    configure_random = QuickDrawDialog.exec

    def configure(dialog: QuickDrawDialog) -> int:
        result = configure_random(dialog)
        dialog.random_images.setChecked(False)
        return result

    monkeypatch.setattr(QuickDrawDialog, "exec", configure)
    win._docks.file_list.setCurrentRow(1)
    win._toggle_quick_draw(True)
    canvas = win._canvas_widgets.canvas
    _box(win, qtbot)
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert _path(win).name == "c.png"
    files = win._docks.file_list
    qtbot.mouseClick(
        files.viewport(),
        Qt.MouseButton.LeftButton,
        pos=files.visualItemRect(files.item(1)).center(),
    )
    assert _path(win).name == "b.png"
    assert win._quick_draw is None
    assert len(canvas.shapes) == 1
    win._toggle_quick_draw(True)
    assert _path(win).name == "b.png"
    assert len(canvas.shapes) == 1
    _box(win, qtbot)
    assert len(canvas.shapes) == 2
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert _path(win).name == "c.png"
    qtbot.keyClick(canvas, Qt.Key.Key_Space)
    assert win._quick_draw is None
    assert len(json.loads(_path(win).with_name("b.json").read_text())["shapes"]) == 2


@pytest.mark.parametrize("classes", [("rat",), ("rat", "rat", "mouse")])
@pytest.mark.parametrize("shape_type", ["rectangle", "polygon"])
@pytest.mark.parametrize("random_images", [False, True])
def test_quick_draw_remembers_last_started_settings_after_reopening_and_restart(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shape_type: str,
    random_images: bool,
    classes: tuple[str, ...],
) -> None:
    Image.new("RGB", (100, 100)).save(tmp_path / "a.png")
    win = main_win(file_or_dir=tmp_path)
    show_window_and_wait_for_imagedata(qtbot, win)

    def configure(dialog: QuickDrawDialog) -> int:
        for column, label in enumerate(classes):
            if column:
                dialog.add_class()
            dialog.table.item(0, column).setText(label)
        dialog.shape_type.setCurrentIndex(dialog.shape_type.findData(shape_type))
        dialog.random_images.setChecked(random_images)
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(QuickDrawDialog, "exec", configure)
    win._toggle_quick_draw(True)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Escape)
    inspected = []

    def inspect_then_cancel(dialog: QuickDrawDialog) -> int:
        assert dialog.label_sequence() == classes
        assert dialog.shape_type.currentData() == shape_type
        assert dialog.random_images.isChecked() == random_images
        assert dialog.start_button.isEnabled()
        inspected.append(True)
        # Changes cancelled here must not replace the last started settings.
        dialog.table.item(0, 0).setText("cancelled")
        dialog.shape_type.setCurrentIndex(1 - dialog.shape_type.currentIndex())
        dialog.random_images.setChecked(not random_images)
        return QtWidgets.QDialog.DialogCode.Rejected

    monkeypatch.setattr(QuickDrawDialog, "exec", inspect_then_cancel)
    win._toggle_quick_draw(True)
    win.close()
    reopened = main_win(file_or_dir=tmp_path)
    show_window_and_wait_for_imagedata(qtbot, reopened)
    reopened._toggle_quick_draw(True)
    assert len(inspected) == 2


@pytest.mark.parametrize("classes", [[], [""], ["rat"] * 10, [12]])
def test_invalid_remembered_classes_fall_back_to_empty_setup(
    quick_draw_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    classes: list,
) -> None:
    win = quick_draw_win
    win._window_state.setValue("quickDraw/classes", classes)
    win._window_state.setValue("quickDraw/shapeType", "unsupported")

    def inspect(dialog: QuickDrawDialog) -> int:
        assert dialog.shape_type.currentData() == "rectangle"
        assert dialog.label_sequence() == ("",)
        assert not dialog.start_button.isEnabled()
        return QtWidgets.QDialog.DialogCode.Rejected

    monkeypatch.setattr(QuickDrawDialog, "exec", inspect)
    win._toggle_quick_draw(True)
