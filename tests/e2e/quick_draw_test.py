from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets.quick_draw_dialog import QuickDrawDialog

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
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
    objects: tuple[tuple[str, int], ...] = (("cat", 2), ("dog", 1)),
) -> None:
    def configure(dialog: QuickDrawDialog) -> int:
        for row, (label, count) in enumerate(objects):
            if row:
                dialog.add_object()
            item = dialog.table.item(row, 0)
            spin = dialog.table.cellWidget(row, 1)
            assert item is not None and isinstance(spin, QtWidgets.QSpinBox)
            item.setText(label)
            spin.setValue(count)
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(QuickDrawDialog, "exec", configure)


def _path(win: MainWindow) -> Path:
    assert win._image_path is not None
    return Path(win._image_path)


def _box(win: MainWindow, qtbot: QtBot) -> None:
    canvas = win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.2, 0.2))
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))


def test_ordered_labels_save_and_random_advance(
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
    assert "box 1/3 — cat" in win._quick_draw_progress.text()
    for label in ("cat", "cat"):
        _box(win, qtbot)
        assert canvas.shapes[-1].label == label
        assert not path.with_suffix(".json").exists()
    assert "box 3/3 — dog" in win._quick_draw_progress.text()
    _box(win, qtbot)
    qtbot.waitUntil(lambda: _path(win).name == "b.png")
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
    # Skips are eligible again in a fresh run; c's saved annotation is protected.
    win._toggle_quick_draw(True)
    assert _path(win).name == "b.png"


def test_existing_jsons_and_annotations_created_during_run_are_protected(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    folder = _path(win).parent
    # Any existing JSON, even empty or malformed, excludes the image.
    (folder / "c.json").write_text("already reviewed")
    win._toggle_quick_draw(True)
    assert _path(win).name == "b.png"
    (folder / "a.json").write_text("new annotations from another process")
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    assert win._quick_draw is None
    assert (folder / "c.json").read_text() == "already reviewed"
    assert (folder / "a.json").read_text() == "new annotations from another process"


def test_auto_save_is_deferred_and_keep_previous_does_not_copy_boxes(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, (("cat", 2),))
    win._actions.save_auto.setChecked(True)
    win._actions.toggle_keep_prev_mode.setChecked(True)
    win._toggle_quick_draw(True)
    path = _path(win)
    _box(win, qtbot)
    assert win._is_changed
    assert not path.with_suffix(".json").exists()
    _box(win, qtbot)
    assert _path(win).name == "b.png"
    assert not win._canvas_widgets.canvas.shapes
    assert win._actions.save_auto.isChecked()
    assert win._actions.toggle_keep_prev_mode.isChecked()


@pytest.mark.parametrize("complete", [False, True])
def test_save_failure_keeps_image_and_space_retries(
    quick_draw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    complete: bool,
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, (("cat", 1 if complete else 2),))
    win._toggle_quick_draw(True)
    original_path = win._image_path
    assert original_path is not None
    save = win.save_labels
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    _box(win, qtbot)
    if not complete:
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
    _configure(monkeypatch, (("cat", 1), ("dog", 1)))
    win._toggle_quick_draw(True)
    path = _path(win)
    _box(win, qtbot)
    win.undo_shape_edit()
    assert "box 1/2 — cat" in win._quick_draw_progress.text()
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
    _configure(monkeypatch, (("dog", 1),))
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
    _configure(monkeypatch, (("cat", 1),))
    win._toggle_quick_draw(True)
    original_path = _path(win)
    _box(win, qtbot)
    assert (output / original_path.with_suffix(".json").name).exists()
    assert not original_path.with_suffix(".json").exists()
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Space)
    win._toggle_quick_draw(True)
    assert _path(win) != original_path


def test_dialog_counts_validation_and_removal(qtbot: QtBot) -> None:
    dialog = QuickDrawDialog()
    qtbot.addWidget(dialog)
    assert not dialog.start_button.isEnabled()

    dialog.accept()
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Rejected
    first = dialog.table.item(0, 0)
    assert first is not None
    first.setText(" cat ")
    count = dialog.table.cellWidget(0, 1)
    assert isinstance(count, QtWidgets.QSpinBox)
    count.setValue(2)
    dialog.add_object()
    assert not dialog.start_button.isEnabled()
    second = dialog.table.item(1, 0)
    assert second is not None
    second.setText("dog")
    assert dialog.start_button.isEnabled()
    assert dialog.label_sequence() == ("cat", "cat", "dog")
    assert "3" in dialog.total.text()
    dialog.table.selectRow(1)
    dialog._remove_selected()
    assert dialog.label_sequence() == ("cat", "cat")
    dialog.table.selectRow(0)
    dialog._remove_selected()
    assert not dialog.start_button.isEnabled()


def test_completing_final_image_saves_and_exits(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, (("cat", 1),))
    win._toggle_quick_draw(True)
    folder = _path(win).parent
    for name in ("c", "b", "a"):
        assert _path(win).stem == name
        _box(win, qtbot)
        assert len(json.loads((folder / f"{name}.json").read_text())["shapes"]) == 1
    assert win._quick_draw is None
    assert not win._quick_draw_action.isChecked()
    assert not win._is_changed
    assert _path(win).name == "a.png"


def test_undo_after_failed_completion_resumes_the_expected_object(
    quick_draw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch, (("cat", 1), ("dog", 1)))
    win._toggle_quick_draw(True)
    path = _path(win)
    save = win.save_labels
    monkeypatch.setattr(win, "save_labels", lambda **kwargs: False)
    _box(win, qtbot)
    _box(win, qtbot)
    assert _path(win) == path
    win.undo_shape_edit()
    assert "box 2/2 — dog" in win._quick_draw_progress.text()
    monkeypatch.setattr(win, "save_labels", save)
    _box(win, qtbot)
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


def test_no_unannotated_images_leaves_current_image_open(
    quick_draw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = quick_draw_win
    _configure(monkeypatch)
    path = _path(win)
    for image in win.image_list:
        Path(image).with_suffix(".json").write_text("already reviewed")
    win._toggle_quick_draw(True)
    assert win._quick_draw is None
    assert _path(win) == path
    assert not win._quick_draw_action.isChecked()


def test_dialog_accepts_name_entered_through_table_editor(qtbot: QtBot) -> None:
    dialog = QuickDrawDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    item = dialog.table.item(0, 0)
    assert item is not None
    dialog.table.editItem(item)
    editor = dialog.table.viewport().findChild(
        QtWidgets.QLineEdit, options=Qt.FindChildOption.FindDirectChildrenOnly
    )
    assert editor is not None
    qtbot.keyClicks(editor, "cat")
    qtbot.waitUntil(dialog.start_button.isEnabled)
    qtbot.mouseClick(dialog.start_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted
    assert dialog.label_sequence() == ("cat",)
