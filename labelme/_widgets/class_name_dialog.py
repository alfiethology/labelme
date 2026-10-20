from __future__ import annotations

from collections.abc import Collection

from PySide6 import QtCore
from PySide6 import QtWidgets


class ClassNameDialog(QtWidgets.QDialog):
    def __init__(
        self,
        *,
        label: str,
        existing_labels: Collection[str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._original_name = label
        self._existing_labels = set(existing_labels)
        self.setWindowTitle(self.tr("Change Class Name"))
        self.resize(480, 240)
        layout = QtWidgets.QVBoxLayout(self)
        name_label = QtWidgets.QLabel(self.tr("New class name:"))
        self.name_edit = QtWidgets.QLineEdit(label)
        name_label.setBuddy(self.name_edit)
        layout.addWidget(name_label)
        layout.addWidget(self.name_edit)
        self.note = QtWidgets.QLabel(
            self.tr(
                "This will change all instances of this class in all JSON files "
                "in the current File List. Changes are saved automatically.\n\n"
                "Other unsaved changes on the open image remain unsaved."
            )
        )
        self.note.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.error = QtWidgets.QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.rename_button = buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        self.rename_button.setText(self.tr("Rename"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name_edit.textChanged.connect(self._validate)
        self._validate()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def new_name(self) -> str:
        return self.name_edit.text().strip()

    def _validate(self) -> None:
        name = self.new_name()
        message = ""
        if not name:
            message = self.tr("Enter a class name.")
        elif name != self._original_name and name in self._existing_labels:
            message = self.tr(
                "That class name already exists. Use Merge with… instead."
            )
        self.error.setText(message)
        self.rename_button.setEnabled(not message and name != self._original_name)

    def accept(self) -> None:
        self._validate()
        if self.rename_button.isEnabled():
            super().accept()
