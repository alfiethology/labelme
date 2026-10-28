from __future__ import annotations

from PySide6 import QtGui
from PySide6 import QtWidgets

from .._config._crosshair import MAX_CROSSHAIR_WIDTH
from .._config._crosshair import MIN_CROSSHAIR_WIDTH
from .._config._crosshair import clamp_crosshair_width
from ._color_button import ColorButton


class _WidthSpinBox(QtWidgets.QSpinBox):
    def validate(self, text: str, pos: int) -> tuple[QtGui.QValidator.State, str, int]:
        # Let users finish typing an out-of-range number, then clamp on commit.
        if text.lstrip("-").isdigit():
            return QtGui.QValidator.State.Acceptable, text, pos
        return super().validate(text, pos)

    def valueFromText(self, text: str) -> int:
        try:
            return clamp_crosshair_width(int(text))
        except ValueError:
            return self.value()


class CrosshairDialog(QtWidgets.QDialog):
    def __init__(
        self, parent: QtWidgets.QWidget, *, color: QtGui.QColor, width: int
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Crosshair Appearance"))
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.color_button = ColorButton()
        self.color_button.set_color(color)
        self.color_button.clicked.connect(self._choose_color)
        form.addRow(self.tr("Crosshair colour"), self.color_button)
        self.width = _WidthSpinBox()
        self.width.setRange(MIN_CROSSHAIR_WIDTH, MAX_CROSSHAIR_WIDTH)
        self.width.setKeyboardTracking(False)
        self.width.setValue(clamp_crosshair_width(width))
        form.addRow(self.tr("Thickness (pixels)"), self.width)
        layout.addLayout(form)
        hint = QtWidgets.QLabel(
            self.tr("Thickness is limited to 1–5 screen pixels; higher values use 5.")
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(self.sizeHint() * 1.5)

    def _choose_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(
            self.color_button.color, self, self.tr("Crosshair colour")
        )
        if color.isValid():
            self.color_button.set_color(color)

    def accept(self) -> None:
        self.width.interpretText()
        super().accept()
