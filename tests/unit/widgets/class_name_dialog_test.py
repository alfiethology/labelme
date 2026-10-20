from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._widgets.class_name_dialog import ClassNameDialog


def test_name_field_and_scope_note(qtbot: QtBot) -> None:
    dialog = ClassNameDialog(label="snakes", existing_labels={"snakes", "bird"})
    qtbot.addWidget(dialog)
    assert dialog.name_edit.text() == "snakes"
    assert "all instances" in dialog.note.text()
    assert "all JSON files" in dialog.note.text()
    assert "current File List" in dialog.note.text()
    assert not dialog.rename_button.isEnabled()
    dialog.name_edit.setText("  snake  ")
    assert dialog.new_name() == "snake"
    assert dialog.rename_button.isEnabled()
    dialog.accept()
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted


def test_empty_unchanged_and_existing_names_do_not_accept(qtbot: QtBot) -> None:
    dialog = ClassNameDialog(label="snakes", existing_labels={"snakes", "snake"})
    qtbot.addWidget(dialog)
    for name in ("", "   ", "snakes", "snake"):
        dialog.name_edit.setText(name)
        assert not dialog.rename_button.isEnabled()
        dialog.accept()
        assert dialog.result() == QtWidgets.QDialog.DialogCode.Rejected
    assert "Merge with…" in dialog.error.text()


def test_typing_a_single_character_name_and_cancelling(qtbot: QtBot) -> None:
    dialog = ClassNameDialog(label="snakes", existing_labels={"snakes"})
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.keyClicks(dialog.name_edit, "x")
    assert dialog.new_name() == "x"
    assert dialog.rename_button.isEnabled()
    qtbot.keyClick(dialog.name_edit, Qt.Key.Key_Escape)
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Rejected
