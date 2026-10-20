from __future__ import annotations

from collections.abc import Sequence

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .label_dialog import LabelQLineEdit


class ClassNameQuickEditPopup(QtWidgets.QDialog):
    """Choose a class with one click, without editing other shape metadata."""

    def __init__(
        self,
        *,
        labels: Sequence[str],
        current_label: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent, QtCore.Qt.WindowType.Popup)
        self.setWindowTitle(self.tr("Class Name Quick Edit"))
        self.selected_label: str | None = None
        self._labels = list(dict.fromkeys(labels))
        self._current_label = current_label
        layout = QtWidgets.QVBoxLayout(self)
        current = QtWidgets.QLabel(
            self.tr("Current class: {label}").format(label=current_label)
        )
        current.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        current.setWordWrap(True)
        layout.addWidget(current)
        self.search = LabelQLineEdit()
        self.search.setPlaceholderText(self.tr("Search class names…"))
        self.search.setAccessibleName(self.tr("Search class names"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.results = QtWidgets.QListWidget()
        self.results.setAccessibleName(self.tr("Class name suggestions"))
        self.results.setUniformItemSizes(True)
        self.search.set_list_widget(self.results)
        layout.addWidget(self.results)
        self.empty = QtWidgets.QLabel(self.tr("No matching class names"))
        layout.addWidget(self.empty)
        layout.addWidget(
            QtWidgets.QLabel(self.tr("Click a name to apply · Esc to cancel"))
        )
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._choose_current)
        self.results.itemClicked.connect(self._choose)
        self._filter("")
        self.resize(360, 320)
        self.search.setFocus()

    def _filter(self, query: str) -> None:
        self.results.clear()
        for label in self._labels:
            if query.casefold() in label.casefold():
                self.results.addItem(label)
        matches = self.results.findItems(
            self._current_label, QtCore.Qt.MatchFlag.MatchExactly
        )
        if matches:
            self.results.setCurrentItem(matches[0])
        elif self.results.count():
            self.results.setCurrentRow(0)
        self.empty.setVisible(self.results.count() == 0)

    def _choose(self, item: QtWidgets.QListWidgetItem) -> None:
        self.selected_label = item.text()
        self.accept()

    def _choose_current(self) -> None:
        item = self.results.currentItem()
        if item is not None:
            self._choose(item)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            self._choose_current()
            return
        super().keyPressEvent(event)

    def move_near(self, point: QtCore.QPoint) -> None:
        screen = QtGui.QGuiApplication.screenAt(point) or self.screen()
        available = screen.availableGeometry()
        self.resize(self.size().boundedTo(available.size()))
        self.move(
            max(available.left(), min(point.x(), available.right() - self.width() + 1)),
            max(
                available.top(), min(point.y(), available.bottom() - self.height() + 1)
            ),
        )
