from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import show_window_and_wait_for_imagedata


def _write(path: Path, image: Path, labels: list[str]) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": "test",
                "imagePath": os.path.relpath(image, path.parent),
                "imageData": None,
                "imageWidth": 100,
                "imageHeight": 100,
                "flags": {},
                "shapes": [
                    {
                        "label": label,
                        "shape_type": "rectangle",
                        "points": [[10, 10], [30, 30]],
                        "flags": {},
                    }
                    for label in labels
                ],
            }
        )
    )


def _open_dataset(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    *,
    output_dir: bool = False,
    exact: bool = False,
) -> MainWindow:
    images = tmp_path / "images"
    images.mkdir()
    for name in ("a", "b", "c"):
        Image.new("RGB", (100, 100)).save(images / f"{name}.png")
    labels = tmp_path / "labels" if output_dir else images
    _write(labels / "a.json", images / "a.png", ["old"])
    _write(
        labels / "b.json", images / "b.png", ["unopened", "another class", "unopened"]
    )
    config: dict[str, object] = {"auto_save": False, "labels": ["old", "predefined"]}
    if exact:
        config["validate_label"] = "exact"
    win = main_win(
        file_or_dir=images,
        output_dir=labels if output_dir else None,
        config_overrides=config,
    )
    show_window_and_wait_for_imagedata(qtbot, win)
    return win


@pytest.fixture()
def name_win(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> MainWindow:
    win = _open_dataset(main_win, tmp_path, qtbot)
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Discard,
    )
    return win


def _names(win: MainWindow) -> list[str]:
    labels = win._label_dialog.label_list
    return [labels.item(row).text() for row in range(labels.count())]


def test_sidebar_contains_all_classes_as_soon_as_directory_opens(
    name_win: MainWindow,
) -> None:
    sidebar = name_win._docks.unique_label_list
    names = [
        sidebar.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(sidebar.count())
    ]
    assert set(names) == {"old", "predefined", "unopened", "another class"}
    assert len(names) == len(set(names))
    assert (
        name_win._image_path is not None and Path(name_win._image_path).name == "a.png"
    )
    assert len(name_win._canvas_widgets.canvas.shapes) == 1
    assert "unopened" not in name_win._label_dialog.label_history
    assert not name_win._is_changed


def test_directory_without_predefined_labels_shows_all_json_classes(
    main_win: MainWinFactory, tmp_path: Path, qtbot: QtBot
) -> None:
    for name, label in (("a", "snake"), ("b", "snakes")):
        image = tmp_path / f"{name}.png"
        Image.new("RGB", (100, 100)).save(image)
        _write(image.with_suffix(".json"), image, [label])
    win = main_win(file_or_dir=tmp_path, config_overrides={"auto_save": False})
    show_window_and_wait_for_imagedata(qtbot, win)
    sidebar = win._docks.unique_label_list
    assert sidebar.count() == 2
    assert sidebar.find_label_item("snake") is not None
    assert sidebar.find_label_item("snakes") is not None
    assert win._image_path is not None and Path(win._image_path).name == "a.png"
    assert not win._is_changed


def test_unopened_class_visibility_and_colour_survive_image_navigation(
    name_win: MainWindow,
) -> None:
    win = name_win
    sidebar = win._docks.unique_label_list
    item = sidebar.find_label_item("unopened")
    assert item is not None
    palette = win._canvas_widgets.canvas._resolve_palette("unopened")
    item.setCheckState(Qt.CheckState.Unchecked)
    for row in (1, 0, 1):
        win._docks.file_list.setCurrentRow(row)
        assert sidebar.find_label_item("unopened") is item
        assert item.checkState() == Qt.CheckState.Unchecked
        assert win._canvas_widgets.canvas._resolve_palette("unopened") == palette
        assert all(
            not shape.visible
            for shape in win._canvas_widgets.canvas.shapes
            if shape.label == "unopened"
        )
    assert not win._is_changed


def test_new_json_classes_are_added_before_that_image_is_opened(
    name_win: MainWindow, tmp_path: Path
) -> None:
    images = tmp_path / "images"
    _write(images / "c.json", images / "c.png", ["new external class"])
    name_win._docks.file_list.setCurrentRow(1)
    assert (
        name_win._image_path is not None and Path(name_win._image_path).name == "b.png"
    )
    assert (
        name_win._docks.unique_label_list.find_label_item("new external class")
        is not None
    )
    assert all(
        shape.label != "new external class"
        for shape in name_win._canvas_widgets.canvas.shapes
    )
    assert not name_win._is_changed


def test_dropped_image_classes_are_added_to_sidebar(
    name_win: MainWindow, tmp_path: Path
) -> None:
    folder = tmp_path / "dropped"
    folder.mkdir()
    image = folder / "new.png"
    Image.new("RGB", (100, 100)).save(image)
    _write(image.with_suffix(".json"), image, ["dropped class"])
    name_win.import_dropped_image_files([str(image)])
    assert (
        name_win._docks.unique_label_list.find_label_item("dropped class") is not None
    )
    assert not name_win._is_changed


def _edit_names(
    win: MainWindow, monkeypatch: pytest.MonkeyPatch, target: str | None = None
) -> list[str]:
    offered: list[str] = []

    def popup(*args: object, **kwargs: object) -> tuple:
        offered.extend(_names(win))
        return (None, None, None, None) if target is None else (target, {}, None, "")

    win._docks.label_list.select_item(next(iter(win._docks.label_list)))
    with monkeypatch.context() as patch:
        patch.setattr(win._label_dialog, "popup", popup)
        win._edit_label()
    return offered


def test_edit_label_offers_unopened_json_names_without_loading_or_drawing(
    name_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = name_win
    original_path = win._image_path
    originals = {
        path: path.read_bytes() for path in (tmp_path / "images").glob("*.json")
    }
    names = _edit_names(win, monkeypatch)
    assert names == ["another class", "old", "predefined", "unopened"]
    assert win._image_path == original_path
    assert win._docks.unique_label_list.find_label_item("unopened") is not None
    assert len(win._canvas_widgets.canvas.shapes) == 1
    assert not win._is_changed
    assert all(path.read_bytes() == content for path, content in originals.items())


def test_newly_typed_edit_name_is_available_immediately_without_drawing(
    name_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = name_win
    _edit_names(win, monkeypatch, "newly typed")
    assert "newly typed" in _names(win)
    assert "newly typed" in win._label_dialog.label_history
    assert "newly typed" in _edit_names(win, monkeypatch)
    assert len(win._canvas_widgets.canvas.shapes) == 1
    assert win._canvas_widgets.canvas.shapes[0].label == "newly typed"
    assert (
        json.loads((tmp_path / "images/a.json").read_text())["shapes"][0]["label"]
        == "old"
    )
    assert win._is_changed
    win.mark_clean()


def test_updated_new_and_deleted_jsons_refresh_suggestions(
    name_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = name_win
    images = tmp_path / "images"
    assert "unopened" in _edit_names(win, monkeypatch)
    _write(images / "b.json", images / "b.png", ["renamed elsewhere"])
    _write(images / "c.json", images / "c.png", ["brand new"])
    names = _edit_names(win, monkeypatch)
    assert "renamed elsewhere" in names and "brand new" in names
    assert "unopened" not in names and "another class" not in names
    (images / "b.json").unlink()
    assert "renamed elsewhere" not in _edit_names(win, monkeypatch)


def test_filtering_file_list_refreshes_dataset_names(
    name_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = name_win
    assert "unopened" in _edit_names(win, monkeypatch)
    win._import_images_from_dir(root_dir=str(tmp_path / "images"), pattern=r"a\.png$")
    win._docks.file_list.setCurrentRow(0)
    assert len(win.image_list) == 1
    _edit_names(win, monkeypatch)
    assert "unopened" not in win._label_dialog.dataset_labels
    win._import_images_from_dir(root_dir=str(tmp_path / "images"))
    win._docks.file_list.setCurrentRow(0)
    assert "unopened" in _edit_names(win, monkeypatch)


def test_suggestions_use_output_directory_and_manual_current_json(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = _open_dataset(main_win, tmp_path, qtbot, output_dir=True)
    images = tmp_path / "images"
    _write(images / "b.json", images / "b.png", ["outside selected output"])
    manual = tmp_path / "manual.json"
    _write(manual, images / "a.png", ["manual location"])
    win._label_file_path = str(manual)
    names = _edit_names(win, monkeypatch)
    assert "unopened" in names and "manual location" in names
    assert "outside selected output" not in names
    sidebar = win._docks.unique_label_list
    assert sidebar.find_label_item("unopened") is not None
    assert sidebar.find_label_item("manual location") is not None
    assert sidebar.find_label_item("outside selected output") is None


def test_exact_validation_accepts_existing_dataset_class(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = _open_dataset(main_win, tmp_path, qtbot, exact=True)
    errors: list[str] = []
    monkeypatch.setattr(
        win, "show_error_message", lambda title, message: errors.append(message)
    )
    names = _edit_names(win, monkeypatch, "unopened")
    assert "unopened" in names
    assert win._canvas_widgets.canvas.shapes[0].label == "unopened"
    assert not errors
    win.mark_clean()


def test_malformed_json_does_not_block_editing_other_labels(
    name_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    images = tmp_path / "images"
    (images / "b.json").write_text("broken JSON")
    _write(images / "c.json", images / "c.png", ["valid elsewhere"])
    assert "valid elsewhere" in _edit_names(name_win, monkeypatch)


def test_new_shape_picker_also_offers_all_dataset_names(
    name_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = name_win
    offered: list[str] = []

    def popup(*args: object, **kwargs: object) -> tuple:
        offered.extend(_names(win))
        return "unopened", {}, None, ""

    monkeypatch.setattr(win._label_dialog, "popup", popup)
    win._switch_canvas_mode(edit=False, create_mode="rectangle")
    canvas = win._canvas_widgets.canvas
    click_canvas_fraction(qtbot, canvas, (0.4, 0.4))
    click_canvas_fraction(qtbot, canvas, (0.8, 0.8))
    assert "unopened" in offered
    assert canvas.shapes[-1].label == "unopened"
    win.mark_clean()


def test_rebuilding_dialog_for_settings_keeps_dataset_names_available(
    name_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "unopened" in _edit_names(name_win, monkeypatch)
    assert name_win._apply_setting_change(("sort_labels",), False)
    assert "unopened" in _edit_names(name_win, monkeypatch)
