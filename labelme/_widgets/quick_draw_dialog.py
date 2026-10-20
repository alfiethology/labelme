from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets


class _ObjectNameDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, labels: tuple[str, ...], parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self._labels = labels

    def createEditor(
        self,
        parent: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtWidgets.QWidget:
        editor = QtWidgets.QComboBox(parent)
        editor.setEditable(True)
        editor.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        editor.addItems(self._labels)
        completer = editor.completer()
        assert completer is not None
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        # Validate while typing, without requiring Enter or Tab before Start.
        editor.editTextChanged.connect(lambda: self.commitData.emit(editor))
        if self._labels:
            QtCore.QTimer.singleShot(0, editor.showPopup)
        return editor

    def setEditorData(
        self,
        editor: QtWidgets.QWidget,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        assert isinstance(editor, QtWidgets.QComboBox)
        blocker = QtCore.QSignalBlocker(editor)
        editor.setEditText(index.data(QtCore.Qt.ItemDataRole.EditRole) or "")
        del blocker

    def setModelData(
        self,
        editor: QtWidgets.QWidget,
        model: QtCore.QAbstractItemModel,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        assert isinstance(editor, QtWidgets.QComboBox)
        model.setData(index, editor.currentText(), QtCore.Qt.ItemDataRole.EditRole)


class QuickDrawDialog(QtWidgets.QDialog):
    """Configure the ordered objects to draw on every image in a session."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        labels: tuple[str, ...] = (),
    ) -> None:
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
        self.table.setItemDelegateForColumn(0, _ObjectNameDelegate(labels, self.table))
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
        self.table.clicked.connect(self._edit_object_name)
        layout.addWidget(self.table)
        count_hint = QtWidgets.QLabel(
            self.tr(
                "(0 for no limit). Put an unlimited object in the last row; "
                "press Space to save and move on."
            )
        )
        count_hint.setWordWrap(True)
        layout.addWidget(count_hint)
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
        count.setRange(0, 9999)
        count.setValue(1)
        count.valueChanged.connect(self._update_total)
        self.table.setCellWidget(row, 1, count)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)
        self._update_total()

    def _edit_object_name(self, index: QtCore.QModelIndex) -> None:
        if index.column() == 0:
            item = self.table.item(index.row(), 0)
            assert item is not None
            self.table.editItem(item)

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

    def unlimited_label(self) -> str | None:
        if not self.table.rowCount():
            return None
        row = self.table.rowCount() - 1
        count = self.table.cellWidget(row, 1)
        item = self.table.item(row, 0)
        assert item is not None and isinstance(count, QtWidgets.QSpinBox)
        return item.text().strip() if count.value() == 0 else None

    def is_valid(self) -> bool:
        if not self.table.rowCount():
            return False
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            count = self.table.cellWidget(row, 1)
            assert item is not None and isinstance(count, QtWidgets.QSpinBox)
            if not item.text().strip():
                return False
            if count.value() == 0 and row != self.table.rowCount() - 1:
                return False
        return True

    def _update_total(self) -> None:
        labels = self.label_sequence()
        if self.unlimited_label() is not None:
            self.total.setText(self.tr("Total boxes per image: no limit"))
        else:
            self.total.setText(
                self.tr("Total boxes per image: {count}").format(count=len(labels))
            )
        self.start_button.setEnabled(self.is_valid())

    def accept(self) -> None:
        # Also guard programmatic acceptance and Enter while a cell is edited.
        if self.is_valid():
            super().accept()
