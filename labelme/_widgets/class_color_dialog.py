from PySide6 import QtGui
from PySide6 import QtWidgets

from ._color_button import ColorButton


class ClassColorDialog(QtWidgets.QDialog):
    def __init__(
        self,
        *,
        label: str,
        inner: QtGui.QColor,
        outer: QtGui.QColor,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Choose Colours for '{}'").format(label))
        self.inner_button = ColorButton()
        self.outer_button = ColorButton()
        self.inner_button.set_color(inner)
        self.outer_button.set_color(outer)
        inner_title = self.tr("Inner point / class colour")
        outer_title = self.tr("Point outer ring colour")
        self.inner_button.setAccessibleName(inner_title)
        self.outer_button.setAccessibleName(outer_title)
        self.inner_button.clicked.connect(
            lambda: self._choose_color(self.inner_button, inner_title)
        )
        self.outer_button.clicked.connect(
            lambda: self._choose_color(self.outer_button, outer_title)
        )
        form = QtWidgets.QFormLayout()
        form.addRow(inner_title, self.inner_button)
        form.addRow(outer_title, self.outer_button)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _choose_color(self, button: ColorButton, title: str) -> None:
        color = QtWidgets.QColorDialog.getColor(button.color, self, title)
        if color.isValid():
            color.setAlpha(button.color.alpha())
            button.set_color(color)

    def colours(self) -> dict[str, list[int]]:
        return {
            name: [button.color.red(), button.color.green(), button.color.blue()]
            for name, button in (
                ("inner", self.inner_button),
                ("outer", self.outer_button),
            )
        }
