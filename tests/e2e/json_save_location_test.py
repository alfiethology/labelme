import json
from pathlib import Path
from typing import Literal

import numpy as np
import PIL.Image
import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets

from labelme._app import MainWindow
from labelme._shape import Shape

from .conftest import MainWinFactory


@pytest.fixture
def image_paths(tmp_path: Path) -> tuple[Path, Path]:
    paths = (tmp_path / "first" / "photo.png", tmp_path / "second" / "photo.png")
    for path in paths:
        path.parent.mkdir()
        PIL.Image.new("RGB", (30, 20), "gray").save(path)
    return paths


def _annotate(win: MainWindow) -> None:
    win._load_shapes(
        [
            Shape(
                label="target",
                shape_type="point",
                points=np.array([[10, 10]], dtype=float),
            )
        ]
    )
    win.mark_dirty()
    assert win._is_changed


def _choose_mode(
    win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    choice: Literal["image_path", "manual"] | None,
) -> list[bool]:
    calls: list[bool] = []

    def choose() -> Literal["image_path", "manual"] | None:
        calls.append(True)
        return choice

    monkeypatch.setattr(win, "_prompt_json_save_mode", choose)
    return calls


@pytest.mark.gui
@pytest.mark.parametrize("choice", ["image_path", "manual", None])
def test_session_choice_dialog_has_both_requested_options_and_can_be_cancelled(
    main_win: MainWinFactory, choice: Literal["image_path", "manual"] | None
) -> None:
    win = main_win()
    seen: list[str] = []

    def click_choice() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        if not isinstance(dialog, QtWidgets.QMessageBox):
            return
        seen.extend(button.text() for button in dialog.buttons())
        target = (
            "Save jsons to image path"
            if choice == "image_path"
            else "Choose json path manually"
        )
        if choice is None:
            dialog.reject()
        else:
            button = next((b for b in dialog.buttons() if b.text() == target), None)
            if button is None:
                dialog.reject()
            else:
                button.click()

    QtCore.QTimer.singleShot(0, click_choice)
    assert win._prompt_json_save_mode() == choice
    assert "Save jsons to image path" in seen
    assert "Choose json path manually" in seen


@pytest.mark.gui
def test_image_path_choice_saves_beside_each_image_and_is_session_only(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=image_paths[0], config_overrides={"auto_save": False})
    choices = _choose_mode(win, monkeypatch, "image_path")

    def unexpected_picker(*args: object, **kwargs: object) -> tuple[str, str]:
        pytest.fail("Saving beside the image must not open a file chooser")

    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", unexpected_picker)
    for path in image_paths:
        win._load_from_file_or_dir(str(path))
        _annotate(win)
        win._save_label_file()
        target = path.with_suffix(".json")
        assert target.exists()
        assert json.loads(target.read_text())["imagePath"] == "photo.png"
        assert win._label_file_path == str(target)
        assert not win._is_changed
    assert len(choices) == 1
    # Saving an existing annotation reuses its file without another prompt.
    _annotate(win)
    win._save_label_file()
    assert len(choices) == 1
    win.close()
    reopened = main_win(
        file_or_dir=image_paths[0], config_overrides={"auto_save": False}
    )
    assert reopened._json_save_mode is None


@pytest.mark.gui
def test_manual_choice_opens_file_picker_for_each_new_image(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=image_paths[0], config_overrides={"auto_save": False})
    choices = _choose_mode(win, monkeypatch, "manual")
    targets = (tmp_path / "labels" / "first.json", tmp_path / "labels" / "second.json")
    picked: list[Path] = []

    def pick_file(*args: object, **kwargs: object) -> tuple[str, str]:
        assert len(choices) == 1, "Ask for the session choice before the file chooser"
        target = targets[len(picked)]
        picked.append(target)
        return str(target), ""

    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", pick_file)
    for path in image_paths:
        win._load_from_file_or_dir(str(path))
        _annotate(win)
        win._save_label_file()
        assert not path.with_suffix(".json").exists()
    assert len(choices) == 1
    assert picked == list(targets)
    assert all(path.exists() for path in targets)


@pytest.mark.gui
def test_cancelling_the_choice_keeps_annotations_dirty_and_asks_again(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=image_paths[0], config_overrides={"auto_save": False})
    choices = _choose_mode(win, monkeypatch, None)
    _annotate(win)
    win._save_label_file()
    assert win._json_save_mode is None
    assert win._is_changed
    assert not image_paths[0].with_suffix(".json").exists()
    assert choices == [True]
    _choose_mode(win, monkeypatch, "image_path")
    win._save_label_file()
    assert image_paths[0].with_suffix(".json").exists()
    assert not win._is_changed


@pytest.mark.gui
def test_cancelling_manual_file_picker_remembers_the_manual_choice(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=image_paths[0], config_overrides={"auto_save": False})
    choices = _choose_mode(win, monkeypatch, "manual")
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", "")
    )
    _annotate(win)
    win._save_label_file()
    win._save_label_file()
    assert choices == [True]
    assert win._json_save_mode == "manual"
    assert win._is_changed
    assert not image_paths[0].with_suffix(".json").exists()
    win.mark_clean()


@pytest.mark.gui
@pytest.mark.parametrize("choose_first", [False, True])
def test_save_as_keeps_file_picker_and_preserves_session_choice(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    choose_first: bool,
) -> None:
    win = main_win(file_or_dir=image_paths[0], config_overrides={"auto_save": False})
    choices = _choose_mode(win, monkeypatch, "image_path")
    _annotate(win)
    if choose_first:
        win._save_label_file()
    target = tmp_path / "copy.json"
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), ""),
    )
    win._save_label_file(save_as=True)
    assert target.exists()
    assert win._json_save_mode == ("image_path" if choose_first else None)
    assert choices == ([True] if choose_first else [])


@pytest.mark.gui
@pytest.mark.parametrize("replace", [False, True])
def test_image_path_choice_confirms_overwriting_an_unloaded_json(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    replace: bool,
) -> None:
    win = main_win(file_or_dir=image_paths[0], config_overrides={"auto_save": False})
    _choose_mode(win, monkeypatch, "image_path")
    _annotate(win)
    target = image_paths[0].with_suffix(".json")
    original = '{"external": true}\n'
    target.write_text(original)
    confirmations: list[bool] = []

    def confirm(
        *args: object, **kwargs: object
    ) -> QtWidgets.QMessageBox.StandardButton:
        confirmations.append(True)
        return (
            QtWidgets.QMessageBox.StandardButton.Yes
            if replace
            else QtWidgets.QMessageBox.StandardButton.No
        )

    monkeypatch.setattr(QtWidgets.QMessageBox, "question", confirm)
    win._save_label_file()
    assert confirmations == [True]
    if replace:
        assert json.loads(target.read_text())["shapes"][0]["label"] == "target"
        assert not win._is_changed
    else:
        assert target.read_text() == original
        assert win._is_changed
        win.mark_clean()


@pytest.mark.gui
def test_failed_image_path_save_keeps_the_choice_and_can_be_retried(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=image_paths[0], config_overrides={"auto_save": False})
    choices = _choose_mode(win, monkeypatch, "image_path")
    _annotate(win)
    errors: list[bool] = []

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("Cannot write annotation")

    with monkeypatch.context() as write_patch:
        write_patch.setattr("labelme._app.write_label_file", fail_write)
        write_patch.setattr(
            win, "show_error_message", lambda *args: errors.append(True)
        )
        win._save_label_file()
    assert errors == [True]
    assert win._is_changed
    assert win._json_save_mode == "image_path"
    assert not image_paths[0].with_suffix(".json").exists()
    win._save_label_file()
    assert choices == [True]
    assert not win._is_changed
    assert image_paths[0].with_suffix(".json").exists()


@pytest.mark.gui
def test_existing_annotation_saves_without_asking_for_a_session_choice(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = image_paths[0].with_suffix(".json")
    win = main_win(file_or_dir=image_paths[0], config_overrides={"auto_save": False})
    _annotate(win)
    assert win.save_labels(str(target))
    win.mark_clean()
    win.close()
    reopened = main_win(
        file_or_dir=image_paths[0], config_overrides={"auto_save": False}
    )
    choices = _choose_mode(reopened, monkeypatch, None)
    _annotate(reopened)
    reopened._save_label_file()
    assert not choices
    assert reopened._json_save_mode is None
    assert not reopened._is_changed


@pytest.mark.gui
def test_explicit_output_directory_keeps_existing_file_picker(
    main_win: MainWinFactory,
    image_paths: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "labels"
    target = output_dir / "photo.json"
    win = main_win(
        file_or_dir=image_paths[0],
        output_dir=output_dir,
        config_overrides={"auto_save": False},
    )
    choices = _choose_mode(win, monkeypatch, "image_path")
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), ""),
    )
    _annotate(win)
    win._save_label_file()
    assert not choices
    assert target.exists()
    assert not image_paths[0].with_suffix(".json").exists()
