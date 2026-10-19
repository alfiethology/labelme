from PySide6 import QtGui
from PySide6 import QtWidgets


class ColorButton(QtWidgets.QPushButton):
    def set_color(self, color: QtGui.QColor) -> None:
        self.color = QtGui.QColor(color)
        self.setText(color.name().upper())
        swatch = QtGui.QPixmap(20, 20)
        swatch.fill(color)
        self.setIcon(QtGui.QIcon(swatch))
