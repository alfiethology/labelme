from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme import _config
from labelme import _label_merge
from labelme._app import MainWindow
from labelme._shape import Shape
from labelme._widgets.class_name_dialog import ClassNameDialog
from labelme._yaml import safe_load

from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def _dataset(root: Path, output: Path | None = None) -> list[Path]:
    image_dir = root / "images"
    image_dir.mkdir()
    label_dir = output or image_dir
    label_dir.mkdir(exist_ok=True)
    paths = []
    for index, name in enumerate(("a", "b", "c")):
        image = image_dir / f"{name}.png"
        Image.new("RGB", (100, 100)).save(image)
        if name == "c":
            continue
        data = {
            "version": "test",
            "imagePath": os.path.relpath(image, label_dir),
            "imageData": None,
            "imageWidth": 100,
            "imageHeight": 100,
            "flags": {"reviewed": True},
            "custom": {"label": "snakes"},
            "shapes": [
                {
                    "label": "snakes",
                    "shape_type": "rectangle" if index else "polygon",
                    "points": [[10, 10], [30, 30]]
                    if index
                    else [[10, 10], [30, 10], [20, 30]],
                    "group_id": 4,
                    "flags": {"occluded": True},
                    "description": "snakes stay in the description",
                    "custom": {"label": "snakes"},
                },
                {
                    "label": "snakes" if not index else "snake",
                    "shape_type": "point",
                    "points": [[50, 50]],
                },
            ],
        }
        path = label_dir / f"{name}.json"
        path.write_text(json.dumps(data))
        paths.append(path)
    return paths


@pytest.fixture()
def merge_win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> MainWindow:
    _dataset(tmp_path)
    win = main_win(
        file_or_dir=tmp_path / "images", config_overrides={"auto_save": False}
    )
    show_window_and_wait_for_imagedata(qtbot, win)
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Discard,
    )
    return win


def _choose_target(
    monkeypatch: pytest.MonkeyPatch, target: str = "snake", accepted: bool = True
) -> list[list[str]]:
    offered: list[list[str]] = []

    def choose(
        parent: QtWidgets.QWidget,
        title: str,
        text: str,
        choices: list[str],
        current: int,
        editable: bool,
    ) -> tuple[str, bool]:
        assert not editable
        offered.append(choices)
        return target, accepted

    monkeypatch.setattr(QtWidgets.QInputDialog, "getItem", choose)
    return offered


def test_context_menu_merges_open_and_unopened_images_and_removes_source(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = merge_win
    paths = sorted((tmp_path / "images").glob("*.json"))
    originals = {path: json.loads(path.read_bytes()) for path in paths}
    assert win._docks.unique_label_list.find_label_item("snake") is None
    offered = _choose_target(monkeypatch)
    menu_items: list[str] = []

    class Menu:
        def __init__(self, parent: QtWidgets.QWidget) -> None:
            self.parent = parent
            self.actions: list[QtGui.QAction] = []

        def addAction(self, text: str) -> QtGui.QAction:
            action = QtGui.QAction(text, self.parent)
            self.actions.append(action)
            menu_items.append(text)
            return action

        def exec(self, *args: object) -> QtGui.QAction:
            return next(
                action for action in self.actions if action.text() == "Merge with…"
            )

    label_list = win._docks.unique_label_list
    item = label_list.find_label_item("snakes")
    assert item is not None
    with monkeypatch.context() as patch:
        patch.setattr(QtWidgets, "QMenu", Menu)
        win.show_unique_label_list_menu(label_list.visualItemRect(item).center())
    assert menu_items == ["Change Class Color…", "Change Class Name…", "Merge with…"]
    assert offered == [["snake"]]
    assert label_list.find_label_item("snakes") is None
    assert label_list.find_label_item("snake") is not None
    assert all(shape.label == "snake" for shape in win._canvas_widgets.canvas.shapes)
    assert all("snake" in item.text() for item in win._docks.label_list)
    assert not win._label_dialog.label_list.findItems(
        "snakes", Qt.MatchFlag.MatchExactly
    )
    assert "snakes" not in win._label_dialog.label_history
    assert not win._is_changed
    for path, original in originals.items():
        for shape in original["shapes"]:
            if shape["label"] == "snakes":
                shape["label"] = "snake"
        assert json.loads(path.read_bytes()) == original
    assert not (tmp_path / "images/c.json").exists()
    win._docks.file_list.setCurrentRow(1)
    assert all(shape.label == "snake" for shape in win._canvas_widgets.canvas.shapes)
    assert label_list.find_label_item("snakes") is None


def test_cancel_merge_changes_nothing(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    originals = {
        path: path.read_bytes() for path in (tmp_path / "images").glob("*.json")
    }
    _choose_target(monkeypatch, accepted=False)
    merge_win._merge_label("snakes")
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert all(
        shape.label == "snakes" for shape in merge_win._canvas_widgets.canvas.shapes
    )
    assert merge_win._docks.unique_label_list.find_label_item("snakes") is not None
    assert not merge_win._is_changed


def test_invalid_empty_target_reports_error_without_changing_files(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = merge_win
    originals = {
        path: path.read_bytes() for path in (tmp_path / "images").glob("*.json")
    }
    win._docks.unique_label_list.add_label_item("", (0, 0, 0))
    _choose_target(monkeypatch, target="")
    errors: list[str] = []
    monkeypatch.setattr(
        win, "show_error_message", lambda title, message: errors.append(message)
    )
    win._merge_label("snakes")
    assert errors and "non-empty" in errors[0]
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert win._docks.unique_label_list.find_label_item("snakes") is not None


def test_unsaved_geometry_and_new_shapes_stay_unsaved(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = merge_win
    _choose_target(monkeypatch)
    first = win._canvas_widgets.canvas.shapes[0]
    first.points[0] = [15, 16]
    win._insert_shapes(
        [Shape(label="snakes", shape_type="point", points=np.array([[70, 80]]))]
    )
    win._merge_label("snakes")
    assert win._is_changed
    assert len(win._canvas_widgets.canvas.shapes) == 3
    assert all(shape.label == "snake" for shape in win._canvas_widgets.canvas.shapes)
    np.testing.assert_array_equal(first.points[0], [15, 16])
    saved = json.loads((tmp_path / "images/a.json").read_bytes())
    assert len(saved["shapes"]) == 2
    assert saved["shapes"][0]["points"][0] == [10, 10]
    assert all(shape["label"] == "snake" for shape in saved["shapes"])
    assert win.save_labels(win.current_label_file_path())
    win.mark_clean()
    saved = json.loads((tmp_path / "images/a.json").read_bytes())
    assert len(saved["shapes"]) == 3
    assert saved["shapes"][0]["points"][0] == [15, 16]


def test_undo_clipboard_and_point_cache_do_not_restore_retired_label(
    merge_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = merge_win
    _choose_target(monkeypatch)
    canvas = win._canvas_widgets.canvas
    win._shape_clipboard.store(canvas.shapes)
    win._point_mode_label_state = ("snakes", {"occluded": True}, 4, "description")
    canvas.backup_shapes()
    canvas.shapes[0].points[0] = [12, 13]
    canvas.backup_shapes()
    win._merge_label("snakes")
    win.undo_shape_edit()
    assert all(shape.label == "snake" for shape in canvas.shapes)
    assert all(shape.label == "snake" for shape in win._shape_clipboard.paste())
    assert win._point_mode_label_state == (
        "snake",
        {"occluded": True},
        4,
        "description",
    )
    assert win._docks.unique_label_list.find_label_item("snakes") is None
    win.mark_clean()


def test_malformed_annotation_blocks_merge_without_partial_changes(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "images/a.json"
    original = first.read_bytes()
    (tmp_path / "images/b.json").write_text("broken JSON")
    errors: list[str] = []
    monkeypatch.setattr(
        merge_win, "show_error_message", lambda title, message: errors.append(message)
    )
    _choose_target(monkeypatch)
    merge_win._merge_label("snakes")
    assert len(errors) == 1 and "b.json" in errors[0]
    assert first.read_bytes() == original
    assert merge_win._docks.unique_label_list.find_label_item("snakes") is not None
    assert all(
        shape.label == "snakes" for shape in merge_win._canvas_widgets.canvas.shapes
    )


def test_write_failure_rolls_back_and_leaves_sidebar_unchanged(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    originals = {
        path: path.read_bytes() for path in (tmp_path / "images").glob("*.json")
    }
    _choose_target(monkeypatch)
    replace = _label_merge._replace_file

    def fail_second(path: Path, content: bytes) -> None:
        if path.name == "b.json":
            raise PermissionError("read only")
        replace(path, content)

    errors: list[str] = []
    monkeypatch.setattr(_label_merge, "_replace_file", fail_second)
    monkeypatch.setattr(
        merge_win, "show_error_message", lambda title, message: errors.append(message)
    )
    merge_win._merge_label("snakes")
    assert errors and "read only" in errors[0]
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert merge_win._docks.unique_label_list.find_label_item("snakes") is not None
    assert all(
        shape.label == "snakes" for shape in merge_win._canvas_widgets.canvas.shapes
    )


@pytest.mark.parametrize("write_error", [False, True])
def test_predefined_names_are_persisted_or_merge_rolls_back(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    write_error: bool,
) -> None:
    paths = _dataset(tmp_path)
    originals = {path: path.read_bytes() for path in paths}
    config = tmp_path / "labelmerc.yaml"
    config.write_text("auto_save: false\nlabels: [snakes, snake]\n")
    original_config = config.read_bytes()
    win = main_win(file_or_dir=tmp_path / "images", config_file=config)
    show_window_and_wait_for_imagedata(qtbot, win)
    _choose_target(monkeypatch)
    errors: list[str] = []
    monkeypatch.setattr(
        win, "show_error_message", lambda title, message: errors.append(message)
    )
    if write_error:

        def fail_config(*args: object, **kwargs: object) -> None:
            raise OSError("cannot save settings")

        monkeypatch.setattr(_config, "set_overrides", fail_config)
    win._merge_label("snakes")
    if write_error:
        assert errors and "cannot save settings" in errors[0]
        assert all(path.read_bytes() == content for path, content in originals.items())
        assert win._docks.unique_label_list.find_label_item("snakes") is not None
        assert config.read_bytes() == original_config
        return
    assert safe_load(config.read_text())["labels"] == ["snake"]
    assert win._config["labels"] == ["snake"]
    win.close()
    reopened = main_win(file_or_dir=tmp_path / "images", config_file=config)
    assert reopened._docks.unique_label_list.find_label_item("snakes") is None
    assert reopened._docks.unique_label_list.find_label_item("snake") is not None


def test_configured_annotation_directory_and_manual_current_path_are_included(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _dataset(tmp_path, tmp_path / "labels")
    # A sibling annotation outside the selected annotation directory is untouched.
    sibling = tmp_path / "images/b.json"
    sibling.write_bytes(paths[1].read_bytes())
    original_sibling = sibling.read_bytes()
    win = main_win(file_or_dir=tmp_path / "images", output_dir=tmp_path / "labels")
    show_window_and_wait_for_imagedata(qtbot, win)
    manual = tmp_path / "manual.json"
    manual.write_bytes(paths[0].read_bytes())
    win._label_file_path = str(manual)
    _choose_target(monkeypatch)
    win._merge_label("snakes")
    for path in [*paths, manual]:
        assert all(
            shape["label"] == "snake"
            for shape in json.loads(path.read_bytes())["shapes"]
        )
    assert sibling.read_bytes() == original_sibling


def test_open_json_without_file_list_can_merge_current_annotations(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _dataset(tmp_path)
    win = main_win(file_or_dir=paths[1])
    show_window_and_wait_for_imagedata(qtbot, win)
    assert not win.image_list
    _choose_target(monkeypatch)
    win._merge_label("snakes")
    assert all(shape.label == "snake" for shape in win._canvas_widgets.canvas.shapes)
    assert all(
        shape["label"] == "snake"
        for shape in json.loads(paths[1].read_bytes())["shapes"]
    )
    assert json.loads(paths[0].read_bytes())["shapes"][0]["label"] == "snakes"


def test_unsaved_only_annotations_are_renamed_without_creating_json(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = merge_win
    win._docks.file_list.setCurrentRow(2)
    win._insert_shapes(
        [Shape(label="snakes", shape_type="point", points=np.array([[20, 30]]))]
    )
    _choose_target(monkeypatch)
    win._merge_label("snakes")
    assert win._canvas_widgets.canvas.shapes[0].label == "snake"
    assert win._is_changed
    assert not (tmp_path / "images/c.json").exists()
    win.mark_clean()


@pytest.mark.parametrize("visible", [False, True])
def test_target_keeps_its_custom_colours_and_visibility(
    merge_win: MainWindow, monkeypatch: pytest.MonkeyPatch, visible: bool
) -> None:
    win = merge_win
    _choose_target(monkeypatch)
    win._config["shape"]["point_colors_by_label"] = {
        "snake": {"inner": [12, 34, 56], "outer": [210, 220, 230]},
        "snakes": {"inner": [90, 80, 70], "outer": [40, 30, 20]},
    }
    canvas = win._canvas_widgets.canvas
    expected = canvas._resolve_palette("snake")
    labels = win._docks.unique_label_list
    labels.add_label_item("snake", (12, 34, 56))
    target = labels.find_label_item("snake")
    source = labels.find_label_item("snakes")
    assert target is not None and source is not None
    target.setCheckState(Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
    source.setCheckState(Qt.CheckState.Unchecked if visible else Qt.CheckState.Checked)
    win._merge_label("snakes")
    assert canvas._resolve_palette("snake") == expected
    assert all(shape.visible == visible for shape in canvas.shapes)
    assert labels.currentItem() == target
    assert not win._is_changed


def _enter_class_name(
    monkeypatch: pytest.MonkeyPatch, name: str = "reptile", *, cancel: bool = False
) -> None:
    def edit(dialog: ClassNameDialog) -> int:
        assert dialog.name_edit.text() == "snakes"
        dialog.name_edit.setText(name)
        if cancel:
            dialog.reject()
        else:
            dialog.accept()
        return dialog.result()

    monkeypatch.setattr(ClassNameDialog, "exec", edit)


def test_class_name_context_action_updates_all_jsons_and_preserves_data(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = merge_win
    originals = {
        path: json.loads(path.read_bytes())
        for path in (tmp_path / "images").glob("*.json")
    }
    _enter_class_name(monkeypatch)
    palette = win._canvas_widgets.canvas._resolve_palette("snakes")

    class Menu:
        def __init__(self, parent: QtWidgets.QWidget) -> None:
            self.parent = parent
            self.rename: QtGui.QAction | None = None

        def addAction(self, text: str) -> QtGui.QAction:
            action = QtGui.QAction(text, self.parent)
            if text == "Change Class Name…":
                self.rename = action
            return action

        def exec(self, *args: object) -> QtGui.QAction:
            assert self.rename is not None
            return self.rename

    labels = win._docks.unique_label_list
    source = labels.find_label_item("snakes")
    assert source is not None
    with monkeypatch.context() as patch:
        patch.setattr(QtWidgets, "QMenu", Menu)
        win.show_unique_label_list_menu(labels.visualItemRect(source).center())
    assert labels.find_label_item("snakes") is None
    assert labels.find_label_item("reptile") is source
    assert win._canvas_widgets.canvas._resolve_palette("reptile") == palette
    assert all(shape.label == "reptile" for shape in win._canvas_widgets.canvas.shapes)
    assert "snakes" not in win._label_dialog.label_history
    assert not win._label_dialog.label_list.findItems(
        "snakes", Qt.MatchFlag.MatchExactly
    )
    assert not win._is_changed
    for path, data in originals.items():
        for shape in data["shapes"]:
            if shape["label"] == "snakes":
                shape["label"] = "reptile"
        assert json.loads(path.read_bytes()) == data
    assert not (tmp_path / "images/c.json").exists()


@pytest.mark.parametrize("name", ["snakes", "  ", "snake", "reptile"])
def test_cancel_or_invalid_class_name_leaves_files_unchanged(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    originals = {
        path: path.read_bytes() for path in (tmp_path / "images").glob("*.json")
    }
    # "snake" exists only in the unopened image and must still be rejected.
    _enter_class_name(monkeypatch, name, cancel=name == "reptile")
    merge_win._change_class_name("snakes")
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert merge_win._docks.unique_label_list.find_label_item("snakes") is not None
    assert all(
        shape.label == "snakes" for shape in merge_win._canvas_widgets.canvas.shapes
    )


def test_rename_keeps_pending_edits_and_updates_undo_and_point_cache(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = merge_win
    _enter_class_name(monkeypatch)
    canvas = win._canvas_widgets.canvas
    win._shape_clipboard.store(canvas.shapes)
    win._point_mode_label_state = ("snakes", {"occluded": True}, 4, "description")
    canvas.shapes[0].points[0] = [15, 16]
    win._insert_shapes(
        [Shape(label="snakes", shape_type="point", points=np.array([[70, 80]]))]
    )
    win._change_class_name("snakes")
    assert win._is_changed
    assert len(canvas.shapes) == 3
    assert all(shape.label == "reptile" for shape in canvas.shapes)
    np.testing.assert_array_equal(canvas.shapes[0].points[0], [15, 16])
    saved = json.loads((tmp_path / "images/a.json").read_bytes())
    assert len(saved["shapes"]) == 2
    assert saved["shapes"][0]["points"][0] == [10, 10]
    assert win._point_mode_label_state == (
        "reptile",
        {"occluded": True},
        4,
        "description",
    )
    assert all(shape.label == "reptile" for shape in win._shape_clipboard.paste())
    win.undo_shape_edit()
    assert all(shape.label == "reptile" for shape in canvas.shapes)
    assert win._docks.unique_label_list.find_label_item("snakes") is None
    win.mark_clean()


@pytest.mark.parametrize("write_error", [False, True])
def test_renamed_colours_and_predefined_names_persist_or_roll_back(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    write_error: bool,
) -> None:
    paths = _dataset(tmp_path)
    originals = {path: path.read_bytes() for path in paths}
    config = tmp_path / "labelmerc.yaml"
    original_config = (
        "auto_save: false\nlabels: [snakes, snake]\n"
        "shape:\n  point_colors_by_label:\n    snakes:\n"
        "      inner: [12, 34, 56]\n      outer: [210, 220, 230]\n"
        "shape_color:\n  mode: by_label\n  by_label:\n"
        "    colors:\n      snakes: [12, 34, 56]\n"
    )
    config.write_text(original_config)
    win = main_win(file_or_dir=tmp_path / "images", config_file=config)
    show_window_and_wait_for_imagedata(qtbot, win)
    _enter_class_name(monkeypatch)
    source = win._docks.unique_label_list.find_label_item("snakes")
    assert source is not None
    source.setCheckState(Qt.CheckState.Unchecked)
    expected_palette = win._canvas_widgets.canvas._resolve_palette("snakes")
    errors: list[str] = []
    monkeypatch.setattr(
        win, "show_error_message", lambda title, message: errors.append(message)
    )
    if write_error:

        def fail_config(*args: object, **kwargs: object) -> None:
            raise OSError("cannot save settings")

        monkeypatch.setattr(_config, "set_overrides", fail_config)
    win._change_class_name("snakes")
    if write_error:
        assert errors and "cannot save settings" in errors[0]
        assert all(path.read_bytes() == content for path, content in originals.items())
        assert config.read_text() == original_config
        assert source.data(Qt.ItemDataRole.UserRole) == "snakes"
        return
    assert not errors
    assert source.data(Qt.ItemDataRole.UserRole) == "reptile"
    assert all(not shape.visible for shape in win._canvas_widgets.canvas.shapes)
    updated = safe_load(config.read_text())
    assert updated["labels"] == ["reptile", "snake"]
    assert updated["shape"]["point_colors_by_label"] == {
        "reptile": {"inner": [12, 34, 56], "outer": [210, 220, 230]}
    }
    assert updated["shape_color"]["by_label"]["colors"] == {"reptile": [12, 34, 56]}
    assert win._canvas_widgets.canvas._resolve_palette("reptile") == expected_palette
    win.close()
    reopened = main_win(file_or_dir=tmp_path / "images", config_file=config)
    assert reopened._docks.unique_label_list.find_label_item("snakes") is None
    assert (
        reopened._canvas_widgets.canvas._resolve_palette("reptile") == expected_palette
    )


def test_rename_write_failure_restores_files_and_original_name(
    merge_win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    originals = {
        path: path.read_bytes() for path in (tmp_path / "images").glob("*.json")
    }
    _enter_class_name(monkeypatch)
    replace = _label_merge._replace_file

    def fail_second(path: Path, content: bytes) -> None:
        if path.name == "b.json":
            raise PermissionError("read only")
        replace(path, content)

    errors: list[str] = []
    monkeypatch.setattr(_label_merge, "_replace_file", fail_second)
    monkeypatch.setattr(
        merge_win, "show_error_message", lambda title, message: errors.append(message)
    )
    merge_win._change_class_name("snakes")
    assert errors and "read only" in errors[0]
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert merge_win._docks.unique_label_list.find_label_item("snakes") is not None


def test_rename_uses_configured_output_directory(
    main_win: MainWinFactory,
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _dataset(tmp_path, tmp_path / "labels")
    win = main_win(file_or_dir=tmp_path / "images", output_dir=tmp_path / "labels")
    show_window_and_wait_for_imagedata(qtbot, win)
    _enter_class_name(monkeypatch)
    win._change_class_name("snakes")
    for path in paths:
        assert all(
            shape["label"] != "snakes"
            for shape in json.loads(path.read_bytes())["shapes"]
        )
    assert not (tmp_path / "images/a.json").exists()
