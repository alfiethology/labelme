from __future__ import annotations

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from labelme._shape import Shape
from labelme._widgets.change_labels_dialog import ChangeLabelsDialog
from labelme._widgets.change_labels_dialog import _ShapeHighlightItem
from labelme._widgets.change_labels_dialog import read_label_shortcuts


def test_read_label_shortcuts(tmp_path) -> None:
    path = tmp_path / "labels.txt"
    path.write_text("# bird labels\nblue_tit,b\ngreat_tit,g\n", encoding="utf-8")
    assert read_label_shortcuts(path) == [("blue_tit", "b"), ("great_tit", "g")]


@pytest.mark.parametrize(
    "text, match",
    [
        ("", "no choices"),
        ("blue_tit\n", "exactly"),
        ("blue_tit,bb\n", "one printable key"),
        ("blue_tit,b\ngreat_tit,B\n", "Duplicate key"),
        ("blue_tit,b\nblue_tit,g\n", "Duplicate label"),
    ],
)
def test_read_label_shortcuts_rejects_invalid_files(tmp_path, text, match) -> None:
    path = tmp_path / "labels.txt"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        read_label_shortcuts(path)


def test_all_supported_shape_types_render_a_highlight(
    qapp: QtWidgets.QApplication, qtbot
) -> None:
    common = dict(label="old")
    shapes = [
        Shape(**common, shape_type="polygon", points=[[2, 2], [20, 2], [10, 20]]),
        Shape(**common, shape_type="rectangle", points=[[2, 2], [20, 20]]),
        Shape(
            **common,
            shape_type="oriented_rectangle",
            points=[[2, 2], [20, 4], [18, 20], [1, 18]],
        ),
        Shape(**common, shape_type="point", points=[[10, 10]]),
        Shape(**common, shape_type="line", points=[[2, 2], [20, 20]]),
        Shape(**common, shape_type="circle", points=[[10, 10], [18, 10]]),
        Shape(**common, shape_type="linestrip", points=[[2, 2], [10, 20], [20, 2]]),
        Shape(**common, shape_type="points", points=[[5, 5], [15, 15]]),
        Shape(
            **common,
            shape_type="skeleton",
            points=[[2, 2], [20, 2], [20, 20], [2, 20], [10, 10]],
            other_data={
                "pose": {
                    "keypoints": ["nose"],
                    "edges": [],
                    "visibility": [2],
                }
            },
        ),
        Shape(
            **common,
            shape_type="mask",
            points=[[10, 10], [12, 12]],
            mask=np.ones((3, 3), dtype=bool),
        ),
    ]
    for shape in shapes:
        dialog = ChangeLabelsDialog(
            image=QtGui.QImage(30, 30, QtGui.QImage.Format.Format_RGB32),
            shapes=[shape],
            choices=[("new", "n")],
        )
        qtbot.addWidget(dialog)
        assert dialog._highlight.shape is shape


def test_highlight_is_unfilled_and_uses_a_thin_cosmetic_outline(
    qapp: QtWidgets.QApplication,
) -> None:
    item = _ShapeHighlightItem(
        shape=Shape(label="old", shape_type="rectangle", points=[[5, 5], [20, 20]]),
        image_size=QtCore.QSize(30, 30),
    )
    image = QtGui.QImage(120, 120, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    painter.scale(4, 4)
    item.paint(painter, QtWidgets.QStyleOptionGraphicsItem())
    painter.end()

    assert image.pixelColor(50, 50).alpha() == 0
    horizontal_edge_pixels = sum(
        image.pixelColor(50, y).alpha() > 0 for y in range(14, 27)
    )
    assert horizontal_edge_pixels <= 3


def test_skip_dont_know_requests_frame_move(
    qapp: QtWidgets.QApplication, qtbot
) -> None:
    dialog = ChangeLabelsDialog(
        image=QtGui.QImage(20, 20, QtGui.QImage.Format.Format_RGB32),
        shapes=[Shape(label="old", shape_type="point", points=[[10, 10]])],
        choices=[("new", "n")],
    )
    qtbot.addWidget(dialog)
    button = next(
        button
        for button in dialog.findChildren(QtWidgets.QPushButton)
        if button.text() == "Skip / Don’t know"
    )

    qtbot.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)

    assert dialog.skip_frame_requested is True


def test_shortcut_changes_label_and_advances(
    qapp: QtWidgets.QApplication, qtbot
) -> None:
    shapes = [
        Shape(label="old", shape_type="rectangle", points=[[1, 1], [10, 10]]),
        Shape(label="old", shape_type="point", points=[[20, 20]]),
    ]
    dialog = ChangeLabelsDialog(
        image=QtGui.QImage(40, 40, QtGui.QImage.Format.Format_RGB32),
        shapes=shapes,
        choices=[("blue_tit", "b"), ("great_tit", "g")],
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.keyClick(dialog, "b")
    qtbot.keyClick(dialog, "g")
    assert dialog.labels == ["blue_tit", "great_tit"]
    assert [shape.label for shape in shapes] == ["old", "old"]
