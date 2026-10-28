from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets.crosshair_dialog import CrosshairDialog
from labelme._yaml import safe_load

from .conftest import MainWinFactory


@pytest.mark.parametrize(
    ("typed", "expected"), [("30", 5), ("999", 5), ("0", 1), ("3", 3)]
)
def test_typed_crosshair_width_is_clamped_on_accept(
    qtbot: QtBot,
    typed: str,
    expected: int,
) -> None:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    dialog = CrosshairDialog(parent, color=QtGui.QColor("yellow"), width=2)
    qtbot.addWidget(dialog)
    dialog.show()
    editor = dialog.width.lineEdit()
    assert editor is not None
    editor.selectAll()
    qtbot.keyClicks(editor, typed)
    dialog.accept()
    assert dialog.width.value() == expected


def test_tool_applies_colour_and_width_and_settings_restore_after_restart(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("{}\n")
    win = main_win(config_file=config_file)
    canvas = win._canvas_widgets.canvas
    assert canvas._crosshair_pen().width() == 2
    colour = QtGui.QColor(120, 30, 210)

    def configure(dialog: CrosshairDialog) -> int:
        monkeypatch.setattr(QtWidgets.QColorDialog, "getColor", lambda *a: colour)
        dialog.color_button.click()
        editor = dialog.width.lineEdit()
        assert editor is not None
        editor.selectAll()
        qtbot.keyClicks(editor, "30")
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(CrosshairDialog, "exec", configure)
    win._choose_crosshair_appearance()
    assert canvas._crosshair_pen().color() == colour
    assert canvas._crosshair_pen().width() == 5
    stored = safe_load(config_file.read_text())["canvas"]
    assert stored["crosshair_color"] == [120, 30, 210, 255]
    assert stored["crosshair_width"] == 5
    win._open_settings()
    settings = win._settings_dialog
    assert settings is not None
    width_editor = settings._editors[("canvas", "crosshair_width")]
    assert isinstance(width_editor, QtWidgets.QComboBox)
    assert width_editor.currentData() == 5
    width_editor.setCurrentIndex(width_editor.findData(3))
    assert canvas._crosshair_pen().width() == 3
    settings.close()
    win.close()
    reopened = main_win(config_file=config_file)
    assert reopened._canvas_widgets.canvas._crosshair_pen().color() == colour
    assert reopened._canvas_widgets.canvas._crosshair_pen().width() == 3


def test_cancelling_tool_preserves_crosshair_settings(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()
    canvas = win._canvas_widgets.canvas
    before = canvas._crosshair_pen()

    def cancel(dialog: CrosshairDialog) -> int:
        dialog.color_button.set_color(QtGui.QColor("red"))
        dialog.width.setValue(4)
        return QtWidgets.QDialog.DialogCode.Rejected

    monkeypatch.setattr(CrosshairDialog, "exec", cancel)
    win._choose_crosshair_appearance()
    assert canvas._crosshair_pen() == before


def test_tool_write_failure_does_not_change_live_style(
    main_win: MainWinFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("{}\n")
    win = main_win(config_file=config_file)
    before = win._canvas_widgets.canvas._crosshair_pen()

    def configure(dialog: CrosshairDialog) -> int:
        dialog.color_button.set_color(QtGui.QColor("red"))
        dialog.width.setValue(5)
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(CrosshairDialog, "exec", configure)
    monkeypatch.setattr(win, "_try_set_overrides", lambda *args: False)
    win._choose_crosshair_appearance()
    assert win._canvas_widgets.canvas._crosshair_pen() == before
    assert config_file.read_text() == "{}\n"
