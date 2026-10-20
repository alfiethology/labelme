from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._widgets.class_name_quick_edit import ClassNameQuickEditPopup


def test_single_click_accepts_selected_name(qtbot: QtBot) -> None:
    popup = ClassNameQuickEditPopup(
        labels=["old", "new class", "new class"], current_label="old"
    )
    qtbot.addWidget(popup)
    popup.show()
    assert popup.results.count() == 2
    item = popup.results.item(1)
    assert item is not None
    qtbot.mouseClick(
        popup.results.viewport(),
        Qt.MouseButton.LeftButton,
        pos=popup.results.visualItemRect(item).center(),
    )
    assert popup.selected_label == "new class"
    assert not popup.isVisible()


def test_search_and_enter_choose_name_with_spaces(qtbot: QtBot) -> None:
    popup = ClassNameQuickEditPopup(
        labels=["old", "New Class", "another"], current_label="old"
    )
    qtbot.addWidget(popup)
    popup.show()
    qtbot.keyClicks(popup.search, "new cla")
    assert popup.results.count() == 1
    qtbot.keyClick(popup.search, Qt.Key.Key_Return)
    assert popup.selected_label == "New Class"


def test_escape_and_empty_search_do_not_change_label(qtbot: QtBot) -> None:
    popup = ClassNameQuickEditPopup(labels=["old"], current_label="old")
    qtbot.addWidget(popup)
    popup.show()
    qtbot.keyClicks(popup.search, "no matching class")
    qtbot.keyClick(popup.search, Qt.Key.Key_Return)
    assert popup.isVisible()
    assert popup.empty.isVisible()
    assert popup.selected_label is None
    qtbot.keyClick(popup.search, Qt.Key.Key_Escape)
    assert not popup.isVisible()
    assert popup.selected_label is None


def test_popup_position_stays_on_screen(qtbot: QtBot) -> None:
    popup = ClassNameQuickEditPopup(labels=["old"], current_label="old")
    qtbot.addWidget(popup)
    bounds = popup.screen().availableGeometry()
    popup.move_near(QPoint(bounds.right(), bounds.bottom()))
    assert bounds.contains(popup.geometry())
