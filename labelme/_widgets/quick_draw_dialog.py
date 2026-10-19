from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets


class _ObjectNameDelegate(QtWidgets.QStyledItemDelegate):
    def createEditor(
        self,
        parent: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtWidgets.QWidget:
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QtWidgets.QLineEdit):
            # Validate while typing so a disabled Start button doesn't force
            # the user to commit the cell with Enter or Tab before clicking it.
            editor.textEdited.connect(lambda: self.commitData.emit(editor))
        return editor


class QuickDrawDialog(QtWidgets.QDialog):
    """Configure the ordered objects to draw on every image in a session."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Quick Draw"))
        self.resize(480, 360)
        layout = QtWidgets.QVBoxLayout(self)
        help_text = QtWidgets.QLabel(
            self.tr(
                "Draw bounding boxes in the order below on randomly chosen "
                "unannotated images. Completed images save automatically.\n"
                "Space saves completed boxes and moves on, or skips an empty image. "
                "Escape stops Quick Draw.\n"
                "JSONs are saved beside the images, or in your configured "
                "annotation directory."
            )
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setItemDelegateForColumn(0, _ObjectNameDelegate(self.table))
        self.table.setHorizontalHeaderLabels(
            [self.tr("Object name"), self.tr("Boxes per image")]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.itemChanged.connect(self._update_total)
        layout.addWidget(self.table)
        row_buttons = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton(self.tr("Add object"))
        add.clicked.connect(self.add_object)
        remove = QtWidgets.QPushButton(self.tr("Remove selected"))
        remove.clicked.connect(self._remove_selected)
        row_buttons.addWidget(add)
        row_buttons.addWidget(remove)
        row_buttons.addStretch()
        layout.addLayout(row_buttons)
        self.total = QtWidgets.QLabel()
        layout.addWidget(self.total)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.start_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.start_button.setText(self.tr("Start Quick Draw"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.add_object()

    def add_object(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        count = QtWidgets.QSpinBox()
        count.setRange(1, 9999)
        count.valueChanged.connect(self._update_total)
        self.table.setCellWidget(row, 1, count)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)
        self._update_total()

    def _remove_selected(self) -> None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self.table.removeRow(row)
        self._update_total()

    def label_sequence(self) -> tuple[str, ...]:
        labels: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            count = self.table.cellWidget(row, 1)
            assert item is not None and isinstance(count, QtWidgets.QSpinBox)
            labels.extend([item.text().strip()] * count.value())
        return tuple(labels)

    def _update_total(self) -> None:
        labels = self.label_sequence()
        self.total.setText(
            self.tr("Total boxes per image: {count}").format(count=len(labels))
        )
        self.start_button.setEnabled(bool(labels) and all(labels))

    def accept(self) -> None:
        # Also guard programmatic acceptance and Enter while a cell is edited.
        labels = self.label_sequence()
        if labels and all(labels):
            super().accept()
