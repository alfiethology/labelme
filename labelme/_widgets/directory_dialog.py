from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets


class _FoldersFirstProxy(QtCore.QSortFilterProxyModel):
    def __init__(self, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self._collator = QtCore.QCollator()
        self._collator.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self._collator.setNumericMode(True)

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        model = self.sourceModel()
        assert isinstance(model, QtWidgets.QFileSystemModel)
        left_is_dir, right_is_dir = model.isDir(left), model.isDir(right)
        if left_is_dir != right_is_dir:
            # Keep folders first even when the user reverses the sort order.
            return (
                left_is_dir
                if self.sortOrder() == QtCore.Qt.SortOrder.AscendingOrder
                else right_is_dir
            )
        if left.column() == 1:
            left_value, right_value = model.size(left), model.size(right)
        elif left.column() == 3:
            left_value = model.lastModified(left).toMSecsSinceEpoch()
            right_value = model.lastModified(right).toMSecsSinceEpoch()
        else:
            left_value = right_value = 0
            if left.column() == 2:
                result = self._collator.compare(model.type(left), model.type(right))
                if result:
                    return result < 0
        if left_value != right_value:
            return left_value < right_value
        return self._collator.compare(model.fileName(left), model.fileName(right)) < 0


class DirectoryDialog(QtWidgets.QFileDialog):
    """Directory picker with folders-first sorting on every desktop."""

    def __init__(
        self, parent: QtWidgets.QWidget | None, caption: str, directory: str
    ) -> None:
        super().__init__(parent)
        # Native pickers control sorting themselves using desktop preferences.
        self.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        self.setOption(QtWidgets.QFileDialog.Option.DontResolveSymlinks)
        self.setWindowTitle(caption)
        self.setFileMode(QtWidgets.QFileDialog.FileMode.Directory)
        self.setOption(QtWidgets.QFileDialog.Option.ShowDirsOnly, False)
        self.setProxyModel(_FoldersFirstProxy(self))
        self.setDirectory(directory)
        view = self.findChild(QtWidgets.QTreeView, "treeView")
        assert view is not None
        view.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)


def get_existing_directory(
    parent: QtWidgets.QWidget | None, caption: str, directory: str
) -> str:
    dialog = DirectoryDialog(parent, caption, directory)
    try:
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dialog.selectedFiles()[0]
        return ""
    finally:
        dialog.deleteLater()
