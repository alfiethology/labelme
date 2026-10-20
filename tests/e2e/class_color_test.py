from pathlib import Path
from typing import Literal

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme import _config
from labelme._widgets.class_color_dialog import ClassColorDialog
from labelme._yaml import safe_load

from .conftest import MainWinFactory


@pytest.mark.gui
@pytest.mark.parametrize("outcome", ["accept", "cancel", "write_error"])
def test_class_menu_selects_both_point_colours_and_persists_them(
    main_win: MainWinFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: Literal["accept", "cancel", "write_error"],
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    original_config = "labels: [bird, cat]\nshape_color:\n  mode: auto\n"
    config_file.write_text(original_config)
    win = main_win(config_file=config_file)
    canvas = win._canvas_widgets.canvas
    original = canvas._resolve_palette("bird")
    other = canvas._resolve_palette("cat")
    choices = iter([QtGui.QColor(12, 34, 56), QtGui.QColor(210, 220, 230)])
    monkeypatch.setattr(QtWidgets.QColorDialog, "getColor", lambda *args: next(choices))

    def edit_colours(dialog: ClassColorDialog) -> int:
        assert dialog.inner_button.color == original.vertex_fill
        assert dialog.outer_button.color == original.vertex_outline
        dialog.inner_button.click()
        dialog.outer_button.click()
        if outcome == "cancel":
            dialog.reject()
        else:
            dialog.accept()
        return dialog.result()

    class Menu:
        def __init__(self, parent: QtWidgets.QWidget) -> None:
            self.parent = parent

        def addAction(self, text: str) -> QtGui.QAction:
            assert text in ("Change Class Color…", "Merge with…")
            action = QtGui.QAction(text, self.parent)
            if text == "Change Class Color…":
                self.action = action
            return action

        def exec(self, *args: object) -> QtGui.QAction:
            return self.action

    monkeypatch.setattr(ClassColorDialog, "exec", edit_colours)
    warnings: list[str] = []
    if outcome == "write_error":

        def fail_write(*args: object, **kwargs: object) -> None:
            raise OSError("Cannot write config")

        monkeypatch.setattr(_config, "set_overrides", fail_write)
        monkeypatch.setattr(
            QtWidgets.QMessageBox,
            "warning",
            lambda *args: warnings.append(args[2]),
        )

    label_list = win._docks.unique_label_list
    item = label_list.find_label_item("bird")
    assert item is not None
    with monkeypatch.context() as menu_patch:
        menu_patch.setattr(QtWidgets, "QMenu", Menu)
        win.show_unique_label_list_menu(label_list.visualItemRect(item).center())
    palette = canvas._resolve_palette("bird")
    if outcome != "accept":
        assert palette == original
        assert config_file.read_text() == original_config
        assert warnings == (["Cannot write config"] if outcome == "write_error" else [])
        return

    assert palette.vertex_fill == QtGui.QColor(12, 34, 56)
    assert palette.vertex_outline == QtGui.QColor(210, 220, 230)
    assert palette.line == palette.vertex_fill
    assert canvas._resolve_palette("cat") == other
    assert canvas._draft_palette.vertex_fill == original.vertex_fill
    assert safe_load(config_file.read_text())["shape"]["point_colors_by_label"] == {
        "bird": {"inner": [12, 34, 56], "outer": [210, 220, 230]}
    }
    assert not win._is_changed

    win.close()
    reopened = main_win(config_file=config_file)
    new_canvas = reopened._canvas_widgets.canvas
    assert new_canvas._resolve_palette("bird") == palette
    assert new_canvas._resolve_palette("cat") == other
    # The menu must reopen with the saved pair rather than the global defaults.
    original = palette
    choices = iter([QtGui.QColor(65, 43, 21), QtGui.QColor(30, 20, 10)])
    label_list = reopened._docks.unique_label_list
    item = label_list.find_label_item("bird")
    assert item is not None
    with monkeypatch.context() as menu_patch:
        menu_patch.setattr(QtWidgets, "QMenu", Menu)
        reopened.show_unique_label_list_menu(label_list.visualItemRect(item).center())
    updated = new_canvas._resolve_palette("bird")
    assert updated.vertex_fill == QtGui.QColor(65, 43, 21)
    assert updated.vertex_outline == QtGui.QColor(30, 20, 10)
