import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets.class_color_dialog import ClassColorDialog


def test_cancelled_colour_picker_keeps_each_original_colour(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = ClassColorDialog(
        label="bird", inner=QtGui.QColor(12, 34, 56), outer=QtGui.QColor(210, 220, 230)
    )
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        QtWidgets.QColorDialog, "getColor", lambda *args: QtGui.QColor()
    )
    dialog.inner_button.click()
    dialog.outer_button.click()
    assert dialog.colours() == {"inner": [12, 34, 56], "outer": [210, 220, 230]}
