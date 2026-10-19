from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets.command_palette import Command
from labelme._widgets.command_palette import CommandPalette
from labelme._widgets.command_palette import action_title
from labelme._widgets.command_palette import collect_action_commands


def test_menu_mnemonics_are_removed_without_losing_literal_ampersands() -> None:
    assert action_title("&Save\n") == "Save"
    assert action_title("Brightness && Contrast…") == "Brightness & Contrast…"


def test_search_matches_substrings_case_insensitively_and_menu_locations(
    qtbot: QtBot,
) -> None:
    contrast = Command("Brightness Contrast", "View")
    dialog = CommandPalette(
        [contrast, Command("Black Canvas", "View"), Command("Open", "File")]
    )
    qtbot.addWidget(dialog)
    for query in ("trast", "CONTRAST", "view brightness", "brightness contrast"):
        dialog._search.setText(query)
        assert dialog._matches == [contrast]
    dialog._search.setText("view")
    assert len(dialog._matches) == 2
    dialog._search.setText("contrast")
    assert dialog._matches[0] is contrast
    dialog._search.setText("does not exist")
    assert dialog._results.count() == 0
    assert not dialog._empty.isHidden()
    qtbot.keyClick(dialog._search, QtCore.Qt.Key.Key_Down)
    qtbot.keyClick(dialog._search, QtCore.Qt.Key.Key_Return)
    assert dialog.selected_command is None


def test_command_name_matches_rank_before_menu_location_matches(qtbot: QtBot) -> None:
    context = Command("Allow points outside image", "Drawing and canvas")
    name = Command("Black Canvas Background", "View")
    dialog = CommandPalette([context, name])
    qtbot.addWidget(dialog)
    dialog._search.setText("canvas")
    assert dialog._matches == [name, context]


def test_keyboard_selection_skips_unavailable_commands_and_preserves_search_focus(
    qtbot: QtBot,
) -> None:
    first = Command("A command", "View")
    second = Command("C command", "Tools")
    dialog = CommandPalette(
        [first, Command("B command", "Tools", enabled=False), second]
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.activateWindow()
    qtbot.waitUntil(dialog._search.hasFocus)
    assert dialog._matches[dialog._results.currentRow()] is first
    qtbot.keyClick(dialog._search, QtCore.Qt.Key.Key_Down)
    assert dialog._matches[dialog._results.currentRow()] is second
    assert dialog._search.hasFocus()
    qtbot.keyClick(dialog._search, QtCore.Qt.Key.Key_Up)
    assert dialog._matches[dialog._results.currentRow()] is first
    qtbot.keyClick(dialog._search, QtCore.Qt.Key.Key_Up)
    assert dialog._matches[dialog._results.currentRow()] is second
    qtbot.keyClick(dialog._search, QtCore.Qt.Key.Key_Return)
    assert dialog.selected_command is second
    assert not dialog.isVisible()


def test_command_cannot_run_if_its_action_becomes_disabled(qtbot: QtBot) -> None:
    action = QtGui.QAction("Delete")
    triggered: list[bool] = []
    action.triggered.connect(lambda: triggered.append(True))
    command = Command("Delete", "Edit", action=action)
    dialog = CommandPalette([command])
    qtbot.addWidget(dialog)
    action.setEnabled(False)
    qtbot.keyClick(dialog._search, QtCore.Qt.Key.Key_Return)
    command.invoke()
    assert dialog.selected_command is None
    assert not triggered


def test_clicking_an_unavailable_item_does_not_run_the_current_selection(
    qtbot: QtBot,
) -> None:
    dialog = CommandPalette(
        [
            Command("A available", "Edit"),
            Command("B unavailable", "Edit", enabled=False),
        ]
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    assert dialog._results.currentRow() == 0
    item = dialog._results.item(1)
    qtbot.mouseClick(
        dialog._results.viewport(),
        QtCore.Qt.MouseButton.LeftButton,
        pos=dialog._results.visualItemRect(item).center(),
    )
    assert dialog.selected_command is None
    assert dialog.isVisible()


def test_click_selects_command_and_escape_runs_nothing(qtbot: QtBot) -> None:
    action = QtGui.QAction("Black Canvas Background")
    action.setCheckable(True)
    action.setChecked(True)
    action.setShortcut("Ctrl+B")
    command = Command("Black Canvas Background", "View", action=action)
    dialog = CommandPalette([command])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    item = dialog._results.item(0)
    assert "On" in item.text()
    assert (
        action.shortcut().toString(QtGui.QKeySequence.SequenceFormat.NativeText)
        in item.text()
    )
    qtbot.mouseClick(
        dialog._results.viewport(),
        QtCore.Qt.MouseButton.LeftButton,
        pos=dialog._results.visualItemRect(item).center(),
    )
    assert dialog.selected_command is command
    assert action.isChecked(), (
        "Selection closes the palette before the caller invokes it"
    )
    command.invoke()
    assert not action.isChecked()

    dismissed = CommandPalette([command])
    qtbot.addWidget(dismissed)
    dismissed.show()
    qtbot.keyClick(dismissed._search, QtCore.Qt.Key.Key_Escape)
    assert dismissed.selected_command is None
    assert not dismissed.isVisible()


def test_menu_collection_includes_submenus_and_deduplicates_toolbar_actions(
    qtbot: QtBot,
) -> None:
    window = QtWidgets.QMainWindow()
    qtbot.addWidget(window)
    edit = window.menuBar().addMenu("&Edit")
    palette = edit.addAction("Command Palette…")
    speed = edit.addMenu("Zoom Speed")
    speed.addAction("4×")
    shared = edit.addAction("&Shared")
    hidden = edit.addAction("Hidden")
    hidden.setVisible(False)
    edit.addSeparator()
    blocked = edit.addMenu("Blocked submenu")
    blocked.setEnabled(False)
    blocked.addAction("Unavailable")
    toolbar = window.addToolBar("Tools")
    toolbar.addAction(shared)
    toolbar.addAction("Toolbar only")
    window.show()
    qtbot.waitExposed(window)
    commands = collect_action_commands(window.menuBar(), [toolbar], exclude=palette)
    assert [c.title for c in commands].count("Shared") == 1
    assert {c.title for c in commands} == {
        "4×",
        "Shared",
        "Unavailable",
        "Toolbar only",
    }
    assert next(c for c in commands if c.title == "4×").section == "Edit › Zoom Speed"
    assert not next(c for c in commands if c.title == "Unavailable").is_enabled()
