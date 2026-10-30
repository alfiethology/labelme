from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets.directory_dialog import DirectoryDialog
from labelme._widgets.directory_dialog import get_existing_directory


def test_folders_first_on_open_and_navigation(qtbot: QtBot, tmp_path: Path) -> None:
    for parent in (tmp_path, tmp_path / "z_folder"):
        parent.mkdir(exist_ok=True)
        (parent / "z_folder").mkdir()
        (parent / "b_folder").mkdir()
        (parent / "a_file.txt").write_text("larger file")
        (parent / "c_file.txt").touch()

    dialog = DirectoryDialog(None, "Open Directory", str(tmp_path))
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.testOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog)
    assert dialog.testOption(QtWidgets.QFileDialog.Option.DontResolveSymlinks)
    assert dialog.fileMode() == QtWidgets.QFileDialog.FileMode.Directory

    view = dialog.findChild(QtWidgets.QTreeView, "treeView")
    assert view is not None
    model = view.model()
    assert model is not None

    def names() -> list[str]:
        root = view.rootIndex()
        return [model.index(row, 0, root).data() for row in range(model.rowCount(root))]

    def check_names() -> None:
        assert names() == ["b_folder", "z_folder", "a_file.txt", "c_file.txt"]

    qtbot.waitUntil(check_names)
    dialog.setDirectory(str(tmp_path / "z_folder"))
    qtbot.waitUntil(check_names)

    view.sortByColumn(0, QtCore.Qt.SortOrder.DescendingOrder)
    assert names() == ["z_folder", "b_folder", "c_file.txt", "a_file.txt"]
    view.sortByColumn(1, QtCore.Qt.SortOrder.AscendingOrder)
    assert names() == ["b_folder", "z_folder", "c_file.txt", "a_file.txt"]


@pytest.mark.parametrize("accepted", [True, False])
def test_directory_selection_and_cancellation(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    accepted: bool,
) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()

    def execute(dialog: DirectoryDialog) -> int:
        qtbot.addWidget(dialog)
        dialog.selectFile(str(selected))
        return (
            QtWidgets.QDialog.DialogCode.Accepted
            if accepted
            else QtWidgets.QDialog.DialogCode.Rejected
        )

    monkeypatch.setattr(DirectoryDialog, "exec", execute)
    assert get_existing_directory(None, "Open Directory", str(tmp_path)) == (
        str(selected) if accepted else ""
    )
