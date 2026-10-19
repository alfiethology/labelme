from __future__ import annotations

from pathlib import Path

import numpy as np
import PIL.Image
import PIL.ImageEnhance
import pytest
from PySide6 import QtGui
from pytestqt.qtbot import QtBot

import labelme._utils
from labelme._app import MainWindow
from labelme._widgets.brightness_contrast_dialog import BrightnessContrastDialog

from ..conftest import close_or_pause
from .conftest import MainWinFactory


@pytest.mark.gui
def test_brightness_contrast_dialog(
    annotated_win: MainWindow,
    qtbot: QtBot,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    original_pixmap = canvas.pixmap.copy()

    assert annotated_win._annotation is not None
    dialog = BrightnessContrastDialog(
        img=labelme._utils.img_data_to_pil(annotated_win._annotation.image_data),
        callback=annotated_win._on_brightness_contrast_changed,
        parent=annotated_win,
    )
    qtbot.addWidget(dialog)

    dialog.slider_brightness.setValue(75)
    dialog.slider_contrast.setValue(25)
    dialog.apply()

    updated_pixmap = canvas.pixmap
    assert original_pixmap.toImage() != updated_pixmap.toImage()

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.fixture
def brightness_images(tmp_path: Path) -> Path:
    directory = tmp_path / "images"
    directory.mkdir()
    image = PIL.Image.fromarray(
        np.array(
            [
                [(30 + x * 8, 40 + y * 10, 80 + x * 3) for x in range(16)]
                for y in range(8)
            ],
            dtype=np.uint8,
        )
    )
    for name in ("a.png", "b.png", "c.png", "d.png"):
        image.save(directory / name)
    return directory


def _open_dialog(
    win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    expected: tuple[int, int],
    adjustment: tuple[int, int] | None = None,
) -> None:
    def interact(dialog: BrightnessContrastDialog) -> int:
        assert (
            dialog.slider_brightness.value(),
            dialog.slider_contrast.value(),
        ) == expected
        if adjustment is not None:
            dialog.slider_brightness.setValue(adjustment[0])
            dialog.slider_contrast.setValue(adjustment[1])
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(BrightnessContrastDialog, "exec", interact)
    win.open_brightness_contrast_dialog(value=True)


def _assert_display(win: MainWindow, values: tuple[int, int]) -> None:
    assert win._annotation is not None
    original = labelme._utils.img_data_to_pil(win._annotation.image_data).convert("RGB")
    expected = PIL.ImageEnhance.Brightness(original).enhance(values[0] / 50)
    expected = PIL.ImageEnhance.Contrast(expected).enhance(values[1] / 50)
    actual = labelme._utils.img_qt_to_arr(
        win._canvas_widgets.canvas.pixmap.toImage().convertToFormat(
            QtGui.QImage.Format.Format_RGB888
        )
    )
    np.testing.assert_array_equal(actual[..., :3], np.asarray(expected))
    assert not win._is_changed


@pytest.mark.gui
def test_images_restore_their_own_values_and_inherit_the_last_actual_adjustment(
    main_win: MainWinFactory,
    brightness_images: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: false\n")
    source_files = {path: path.read_bytes() for path in brightness_images.iterdir()}
    win = main_win(file_or_dir=brightness_images, config_file=config_file)
    assert win._config["keep_prev_brightness_contrast"] is True
    assert win._actions.toggle_keep_prev_brightness_contrast.isChecked()
    assert win._image_path == str(brightness_images / "a.png")
    _assert_display(win, (50, 50))
    _open_dialog(win, monkeypatch, expected=(50, 50))
    assert win._last_brightness_contrast_values is None
    assert win._brightness_contrast_values == {}

    _open_dialog(win, monkeypatch, expected=(50, 50), adjustment=(75, 40))
    _assert_display(win, (75, 40))
    win._open_next_image()
    assert win._image_path == str(brightness_images / "b.png")
    _assert_display(win, (75, 40))
    _open_dialog(win, monkeypatch, expected=(75, 40))
    assert win._image_path not in win._brightness_contrast_values
    _open_dialog(win, monkeypatch, expected=(75, 40), adjustment=(60, 80))
    _assert_display(win, (60, 80))

    win._open_prev_image()
    _assert_display(win, (75, 40))
    _open_dialog(win, monkeypatch, expected=(75, 40))
    assert win._last_brightness_contrast_values == (60, 80)
    win._docks.file_list.setCurrentRow(2)
    _assert_display(win, (60, 80))
    assert win._image_path not in win._brightness_contrast_values

    win._docks.file_list.setCurrentRow(1)
    _open_dialog(win, monkeypatch, expected=(60, 80), adjustment=(90, 35))
    win._docks.file_list.setCurrentRow(2)
    _assert_display(win, (90, 35))
    win._docks.file_list.setCurrentRow(0)
    _assert_display(win, (75, 40))
    win._docks.file_list.setCurrentRow(3)
    _assert_display(win, (90, 35))
    assert len(win._brightness_contrast_values) == 2
    assert {
        path: path.read_bytes() for path in brightness_images.iterdir()
    } == source_files


@pytest.mark.gui
def test_resetting_an_image_to_neutral_becomes_the_new_default(
    main_win: MainWinFactory,
    brightness_images: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=brightness_images)
    _open_dialog(win, monkeypatch, expected=(50, 50), adjustment=(75, 25))
    win._open_next_image()
    _open_dialog(win, monkeypatch, expected=(75, 25), adjustment=(50, 50))
    assert win._last_brightness_contrast_values == (50, 50)
    win._open_next_image()
    _assert_display(win, (50, 50))
    win._docks.file_list.setCurrentRow(0)
    _assert_display(win, (75, 25))
    win._docks.file_list.setCurrentRow(1)
    _assert_display(win, (50, 50))


@pytest.mark.gui
def test_disabling_carry_over_still_restores_each_images_adjustments(
    main_win: MainWinFactory,
    brightness_images: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=brightness_images)
    _open_dialog(win, monkeypatch, expected=(50, 50), adjustment=(75, 25))
    win._actions.toggle_keep_prev_brightness_contrast.trigger()
    assert not win._config["keep_prev_brightness_contrast"]
    win._open_next_image()
    _assert_display(win, (50, 50))
    win._open_prev_image()
    _assert_display(win, (75, 25))
    win._actions.toggle_keep_prev_brightness_contrast.trigger()
    win._open_next_image()
    _assert_display(win, (75, 25))
