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
    """Configure one shape type and an ordered set of classes for a session."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        labels: tuple[str, ...] = (),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Quick Draw"))
        self.resize(720, 360)
        layout = QtWidgets.QVBoxLayout(self)
        help_text = QtWidgets.QLabel(
            self.tr(
                "Choose one shape type for this session. Shapes automatically use "
                "the classes from left to right, repeating on each image.\n"
                "After drawing a shape, press its class key (1–9) to change its class. "
                "Space saves and moves on, or skips an empty image. "
                "E lets you edit any existing shape; press E again to resume "
                "drawing, or finish one move/resize to resume automatically. "
                "Escape stops Quick Draw. Existing annotations are kept; "
                "each image is visited once per run. Start at the selected image "
                "and continue down the list, or enable random selection.\n"
                "JSONs are saved beside the images, or in your configured "
                "annotation directory."
            )
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        shape_row = QtWidgets.QFormLayout()
        self.shape_type = QtWidgets.QComboBox()
        self.shape_type.addItem(self.tr("Bounding box"), "rectangle")
        self.shape_type.addItem(self.tr("Polygon"), "polygon")
        shape_row.addRow(self.tr("Shape type"), self.shape_type)
        layout.addLayout(shape_row)
        self.table = QtWidgets.QTableWidget(1, 0)
        self.table.verticalHeader().hide()
        self.table.setItemDelegate(_ObjectNameDelegate(labels, self.table))
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectColumns
        )
        self.table.itemChanged.connect(self._update_validation)
        self.table.clicked.connect(self._edit_object_name)
        layout.addWidget(self.table)
        self.random_images = QtWidgets.QCheckBox(self.tr("Choose images randomly"))
        layout.addWidget(self.random_images)
        row_buttons = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton(self.tr("Add class"))
        self.add_button.clicked.connect(self.add_class)
        remove = QtWidgets.QPushButton(self.tr("Remove selected"))
        remove.clicked.connect(self._remove_selected)
        row_buttons.addWidget(self.add_button)
        row_buttons.addWidget(remove)
        row_buttons.addStretch()
        layout.addLayout(row_buttons)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.start_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.start_button.setText(self.tr("Start Quick Draw"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.add_class()

    def restore_settings(self, settings: QtCore.QSettings) -> None:
        shape_type = settings.value("quickDraw/shapeType", "rectangle")
        index = self.shape_type.findData(shape_type)
        if index >= 0:
            self.shape_type.setCurrentIndex(index)
        random_images = settings.value("quickDraw/randomImages", False)
        self.random_images.setChecked(
            random_images is True
            or (isinstance(random_images, str) and random_images.lower() == "true")
        )
        classes = settings.value("quickDraw/classes", [])
        if isinstance(classes, str):
            classes = [classes]
        if (
            isinstance(classes, list | tuple)
            and 1 <= len(classes) <= 9
            and all(isinstance(label, str) and label.strip() for label in classes)
        ):
            blocker = QtCore.QSignalBlocker(self.table)
            self.table.setColumnCount(0)
            for label in classes:
                self.add_class()
                self.table.item(0, self.table.columnCount() - 1).setText(label)
            del blocker
            self._update_validation()

    def save_settings(self, settings: QtCore.QSettings) -> None:
        settings.setValue("quickDraw/shapeType", self.shape_type.currentData())
        settings.setValue("quickDraw/classes", list(self.label_sequence()))
        settings.setValue("quickDraw/randomImages", self.random_images.isChecked())

    def add_class(self) -> None:
        column = self.table.columnCount()
        if column >= 9:
            return
        blocker = QtCore.QSignalBlocker(self.table)
        self.table.insertColumn(column)
        self.table.setItem(0, column, QtWidgets.QTableWidgetItem(""))
        self.table.setCurrentCell(0, column)
        del blocker
        self._update_validation()

    def _edit_object_name(self, index: QtCore.QModelIndex) -> None:
        item = self.table.item(0, index.column())
        assert item is not None
        self.table.editItem(item)

    def _remove_selected(self) -> None:
        columns = {index.column() for index in self.table.selectedIndexes()}
        for column in sorted(columns, reverse=True):
            self.table.removeColumn(column)
        self._update_validation()

    def label_sequence(self) -> tuple[str, ...]:
        return tuple(
            self.table.item(0, column).text().strip()
            for column in range(self.table.columnCount())
        )

    def is_valid(self) -> bool:
        labels = self.label_sequence()
        return bool(labels) and all(labels)

    def _update_validation(self) -> None:
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("Class {key}").format(key=i + 1)
                for i in range(self.table.columnCount())
            ]
        )
        self.add_button.setEnabled(self.table.columnCount() < 9)
        self.start_button.setEnabled(self.is_valid())

    def accept(self) -> None:
        # Also guard programmatic acceptance and Enter while a cell is edited.
        if self.is_valid():
            super().accept()
