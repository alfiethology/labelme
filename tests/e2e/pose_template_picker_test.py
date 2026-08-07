from __future__ import annotations

from pathlib import Path

import numpy as np

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
