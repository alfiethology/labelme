from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from PySide6 import QtCore

from labelme._app import MainWindow
from labelme._pose import SkeletonTemplate
from labelme._pose import read_skeleton_file
from labelme._pose import write_skeleton_file


def _write_rat_template(path: Path) -> None:
    write_skeleton_file(
        path,
        skeleton=SkeletonTemplate(
            label="rat",
            keypoints=("snout", "tail_base"),
            edges=((0, 1),),
            positions=np.array([(0.8, 0.3), (0.2, 0.7)]),
            flip_idx=(0, 1),
        ),
    )


def test_skeleton_is_a_left_toolbar_draw_action(raw_win: MainWindow) -> None:
    assert ("skeleton", raw_win._actions.create_skeleton_mode) in raw_win._actions.draw
    assert raw_win._actions.create_skeleton_mode.text() == "Skeleton"
    assert raw_win._actions.create_skeleton_mode.isEnabled()
    assert raw_win._actions.create_quick_skeleton_mode.text() == ("Quick-Draw Skeleton")
    assert raw_win._actions.create_quick_skeleton_mode.isEnabled()


def test_remembered_skeleton_template_can_be_reused(
    raw_win: MainWindow, tmp_path: Path
) -> None:
    path = tmp_path / "rat.skeleton.json"
    _write_rat_template(path)

    raw_win._remember_skeleton_template(str(path))
    raw_win._remember_skeleton_template(str(path))

    assert raw_win._recent_skeleton_template_paths == [str(path.resolve())]
    templates = raw_win._recent_skeleton_templates()
    assert len(templates) == 1
    assert templates[0][0] == str(path.resolve())
    assert templates[0][1].label == "rat"


def test_placed_skeleton_uses_small_centered_default(
    raw_win: MainWindow, tmp_path: Path
) -> None:
    path = tmp_path / "rat.skeleton.json"
    _write_rat_template(path)

    raw_win._place_skeleton(read_skeleton_file(path))

    shape = raw_win._canvas_widgets.canvas.shapes[-1]
    width = raw_win._image.width()
    height = raw_win._image.height()
    np.testing.assert_allclose(
        shape.points[:4],
        [
            (width * 0.4, height * 0.4),
            (width * 0.6, height * 0.4),
            (width * 0.6, height * 0.6),
            (width * 0.4, height * 0.6),
        ],
    )


def test_edit_skeleton_template_uses_drawing_toolbar_and_finish_saves(
    raw_win: MainWindow, tmp_path: Path
) -> None:
    path = tmp_path / "rat.skeleton.json"
    _write_rat_template(path)

    raw_win._edit_skeleton_template_from_file(str(path))

    canvas = raw_win._canvas_widgets.canvas
    assert canvas.is_drawing_skeleton
    assert canvas.skeleton_drawing().names == ("snout", "tail_base")
    assert raw_win._skeleton_drawing_toolbar.isVisible()
    assert raw_win._skeleton_place_action.isEnabled()
    assert raw_win._skeleton_connect_action.isEnabled()
    assert raw_win._skeleton_rename_action.isEnabled()
    assert raw_win._editing_skeleton_template_path == str(path.resolve())
    canvas.set_skeleton_drawing_mode("rename")
    canvas.rename_skeleton_node(index=0, name="nose")
    canvas.set_skeleton_drawing_mode("nodes")
    left, top, right, bottom = raw_win._editing_skeleton_bounds or (0, 0, 0, 0)
    canvas._move_skeleton_draft_node(
        index=0,
        pos=QtCore.QPointF(
            left + (right - left) * 0.25,
            top + (bottom - top) * 0.75,
        ),
    )

    raw_win._finish_skeleton_drawing()

    saved = read_skeleton_file(path)
    assert saved.keypoints == ("nose", "tail_base")
    assert saved.positions[0].tolist() == pytest.approx([0.25, 0.75])
    assert canvas.shapes[-1].other_data["pose"]["keypoints"] == [
        "nose",
        "tail_base",
    ]


def test_quick_draw_places_nodes_in_template_order_then_uses_drawn_box(
    raw_win: MainWindow, tmp_path: Path
) -> None:
    path = tmp_path / "rat.skeleton.json"
    _write_rat_template(path)
    skeleton = read_skeleton_file(path)

    raw_win._start_quick_skeleton_drawing(skeleton)
    raw_win._name_skeleton_node(QtCore.QPointF(30, 30))
    raw_win._name_skeleton_node(QtCore.QPointF(70, 60))

    raw_win._finish_quick_skeleton_drawing(
        top_left=QtCore.QPointF(10, 10),
        bottom_right=QtCore.QPointF(100, 90),
    )

    shape = raw_win._canvas_widgets.canvas.shapes[-1]
    assert shape.other_data["pose"]["keypoints"] == ["snout", "tail_base"]
    np.testing.assert_array_equal(shape.points[4:], [[30, 30], [70, 60]])


def test_quick_draw_menu_can_start_a_new_skeleton(
    raw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_skeleton = Mock()
    monkeypatch.setattr(raw_win, "_new_skeleton", new_skeleton)
    monkeypatch.setattr(raw_win, "_recent_skeleton_templates", lambda: [])

    class Menu:
        def __init__(self, parent: MainWindow) -> None:
            self.actions: dict[str, object] = {}

        def addAction(self, text: str) -> object:
            self.actions[text] = object()
            return self.actions[text]

        def exec(self, pos: object) -> object:
            return self.actions["Draw New Skeleton…"]

    monkeypatch.setattr("labelme._app.QtWidgets.QMenu", Menu)

    raw_win._choose_skeleton_to_quick_draw()

    new_skeleton.assert_called_once_with()


def test_finishing_new_skeleton_prompts_to_save_template(
    raw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_template = Mock()
    monkeypatch.setattr(raw_win, "_save_skeleton_template", save_template)
    monkeypatch.setattr(
        raw_win, "_prompt_skeleton_flip_idx", lambda *, names: tuple(range(len(names)))
    )
    raw_win._skeleton_drawing_label = "rat"
    raw_win._canvas_widgets.canvas.start_skeleton_drawing()
    raw_win._canvas_widgets.canvas.add_skeleton_node(
        name="snout", point=QtCore.QPointF(30, 30)
    )

    raw_win._finish_skeleton_drawing()

    save_template.assert_called_once()
    assert save_template.call_args.args[0].label == "rat"
