from pathlib import Path

import PIL.Image
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets.command_palette import CommandPalette
from labelme._yaml import safe_load

from .conftest import MainWinFactory


def _run_palette(
    win: MainWindow, qtbot: QtBot, query: str, *, run: bool = True
) -> None:
    opened: list[bool] = []
    errors: list[Exception] = []

    def interact() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        if not isinstance(dialog, CommandPalette):
            return
        opened.append(True)
        try:
            qtbot.waitUntil(dialog._search.hasFocus)
            qtbot.keyClicks(dialog._search, query)
            qtbot.keyClick(
                dialog._search,
                QtCore.Qt.Key.Key_Return if run else QtCore.Qt.Key.Key_Escape,
            )
        except Exception as error:
            errors.append(error)
        finally:
            if dialog.isVisible():
                dialog.reject()

    win.activateWindow()
    win._canvas_widgets.canvas.setFocus()
    qtbot.waitUntil(win.isActiveWindow)
    QtCore.QTimer.singleShot(0, interact)
    qtbot.keyClick(win, QtCore.Qt.Key.Key_P, QtCore.Qt.KeyboardModifier.ControlModifier)
    if errors:
        raise errors[0]
    assert opened == [True], "Ctrl+P must open the palette"


@pytest.mark.gui
def test_palette_shortcut_changes_setting_without_toggling_keep_previous(
    main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("shortcuts:\n  toggle_keep_prev_mode: Ctrl+P\n")
    win = main_win(config_file=config_file)
    assert win._actions.command_palette in win._menus.edit.actions()
    assert win._actions.toggle_keep_prev_mode.shortcut() == QtGui.QKeySequence(
        "Ctrl+Shift+P"
    )
    _run_palette(win, qtbot, "black canvas")
    assert win._config["canvas"]["black_background"]
    assert win._canvas_widgets.canvas._black_background
    assert safe_load(config_file.read_text())["canvas"]["black_background"]
    assert not win._actions.toggle_keep_prev_mode.isChecked()
    assert not win._is_changed
    # Reopening rebuilds the checked states and can reverse the same preference.
    _run_palette(win, qtbot, "black canvas")
    assert not win._canvas_widgets.canvas._black_background
    win.activateWindow()
    qtbot.waitUntil(win.isActiveWindow)
    qtbot.keyClick(
        win,
        QtCore.Qt.Key.Key_P,
        QtCore.Qt.KeyboardModifier.ControlModifier
        | QtCore.Qt.KeyboardModifier.ShiftModifier,
    )
    assert win._actions.toggle_keep_prev_mode.isChecked()


@pytest.mark.gui
def test_settings_only_checkbox_is_searchable_and_updates_live_state(
    main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("display_label_popup: true\n")
    win = main_win(config_file=config_file)
    _run_palette(win, qtbot, "label popup")
    assert not win._config["display_label_popup"]
    assert safe_load(config_file.read_text())["display_label_popup"] is False


@pytest.mark.gui
def test_non_boolean_setting_opens_settings_at_the_control(
    main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: false\n")
    win = main_win(config_file=config_file)
    _run_palette(win, qtbot, "point outer ring colour")
    dialog = win._settings_dialog
    assert dialog is not None
    assert dialog.isVisible()
    editor = dialog._editors[("shape", "vertex_outline_color")]
    qtbot.waitUntil(editor.hasFocus)
    viewport = dialog._page._scroll_area.viewport()
    position = editor.mapTo(viewport, QtCore.QPoint())
    assert viewport.rect().contains(position + editor.rect().center())


@pytest.mark.gui
def test_disabled_commands_and_readonly_settings_cannot_be_invoked(
    main_win: MainWinFactory, qtbot: QtBot
) -> None:
    win = main_win(config_overrides={"auto_save": False})
    commands = win._command_palette_commands()
    save = next(c for c in commands if c.action is win._actions.save)
    language = next(c for c in commands if c.title == "Language")
    assert not save.is_enabled()
    assert not language.is_enabled()
    language.invoke()
    assert win._settings_dialog is None
    _run_palette(win, qtbot, "no matching command", run=False)
    assert win._settings_dialog is None
    assert not win._is_changed


@pytest.mark.gui
def test_palette_runs_tools_and_search_typing_does_not_change_canvas_mode(
    main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path
) -> None:
    image_path = tmp_path / "image.png"
    PIL.Image.new("RGB", (40, 30)).save(image_path)
    win = main_win(file_or_dir=image_path, config_overrides={"auto_save": False})
    canvas = win._canvas_widgets.canvas
    original_mode = canvas.create_mode
    _run_palette(win, qtbot, "point", run=False)
    assert canvas.create_mode == original_mode
    _run_palette(win, qtbot, "bounding box quick edit")
    assert win._bounding_box_quick_edit_active
    assert win._bounding_box_quick_edit_action.isChecked()


@pytest.mark.gui
def test_palette_indexes_pose_tools_submenus_and_all_settings(
    main_win: MainWinFactory,
) -> None:
    win = main_win()
    commands = win._command_palette_commands()
    assert any(c.section.startswith("Pose") for c in commands)
    assert any(c.section == "Edit › Zoom Speed" and c.title == "4×" for c in commands)
    assert any(c.title == "Predefined labels" for c in commands)
    assert any(c.title == "Default model" for c in commands)
    actions = [c.action for c in commands if c.action is not None]
    assert len(actions) == len(set(actions))
