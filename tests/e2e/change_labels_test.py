from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def _start_change_labels(win: MainWindow) -> None:
    win._change_label_choices = {"g": "blue_tit", "gt": "great_tit"}
    win._change_label_index = 0
    win._change_label_input = ""
    win._select_change_label_shape()


def test_change_labels_buffers_sequence_until_enter_or_space(
    annotated_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    _start_change_labels(win)
    original_labels = [shape.label for shape in canvas.shapes]

    qtbot.keyClick(canvas, "g")
    assert [shape.label for shape in canvas.shapes] == original_labels
    assert win._change_label_input == "g"

    qtbot.keyClick(canvas, "x")
    qtbot.keyClick(canvas, Qt.Key.Key_Backspace)
    qtbot.keyClick(canvas, "t")
    assert win._change_label_input == "gt"
    qtbot.keyClick(canvas, Qt.Key.Key_Return)

    assert canvas.shapes[0].label == "great_tit"
    assert win._change_label_index == 1
    assert win._change_label_input == ""

    qtbot.keyClick(canvas, "g")
    qtbot.keyClick(canvas, Qt.Key.Key_Space)

    assert canvas.shapes[1].label == "blue_tit"
    assert win._change_label_index == 2


def test_change_labels_saves_and_opens_next_image_after_final_shape(
    annotated_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    _start_change_labels(win)
    win._change_label_index = len(canvas.shapes) - 1
    win._select_change_label_shape()
    save_and_advance_calls = 0

    def save_and_advance() -> None:
        nonlocal save_and_advance_calls
        save_and_advance_calls += 1

    monkeypatch.setattr(win, "_save_and_advance_change_label_image", save_and_advance)

    qtbot.keyClick(canvas, "g")
    qtbot.keyClick(canvas, "t")
    qtbot.keyClick(canvas, Qt.Key.Key_Space)

    assert canvas.shapes[-1].label == "great_tit"
    assert save_and_advance_calls == 1


def test_skipped_image_and_annotation_move_beside_labels_directory(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    images_dir = data_path / "annotated_nested" / "images"
    labels_dir = data_path / "annotated_nested" / "annotations"
    skipped_dir = data_path / "annotated_nested" / "skipped_images"
    win = main_win(file_or_dir=images_dir, output_dir=labels_dir)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    image_path = images_dir / "2011_000003.jpg"
    annotation_path = labels_dir / "2011_000003.json"
    original_file_count = win._docks.file_list.count()

    win._move_current_frame_to_skipped()

    assert not image_path.exists()
    assert not annotation_path.exists()
    assert (skipped_dir / image_path.name).exists()
    assert (skipped_dir / annotation_path.name).exists()
    assert skipped_dir.parent == labels_dir.parent
    assert not (labels_dir / "skipped_frames").exists()
    assert win._docks.file_list.count() == original_file_count - 1
    assert win._image_path is not None
    assert win._image_path != str(image_path)
