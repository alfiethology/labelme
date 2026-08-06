from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from labelme._app import _shape_to_dict
from labelme._app import _shapes_from_dicts
from labelme._pose import SkeletonTemplate
from labelme._pose import ensure_skeleton_oriented_bbox
from labelme._pose import make_skeleton_shape
from labelme._pose import make_skeleton_shape_from_nodes
from labelme._pose import read_skeleton_file
from labelme._pose import skeleton_shape_parts
from labelme._pose import skeleton_template_from_shape
from labelme._pose import write_skeleton_file
from labelme._pose import yolo_dataset_yaml
from labelme._pose import yolo_pose_row
from labelme._pose import yolo_pose_rows


@pytest.fixture
def skeleton() -> SkeletonTemplate:
    return SkeletonTemplate(
        label="hen",
        keypoints=("beak", "left_foot", "right_foot"),
        edges=((0, 1), (0, 2)),
        positions=np.array([[0.5, 0.1], [0.25, 0.9], [0.75, 0.9]]),
        flip_idx=(0, 2, 1),
    )


def test_skeleton_file_round_trip(
    *, skeleton: SkeletonTemplate, tmp_path: Path
) -> None:
    path = tmp_path / "hen.skeleton.json"

    write_skeleton_file(path, skeleton=skeleton)

    loaded = read_skeleton_file(path)
    assert loaded.label == skeleton.label
    assert loaded.keypoints == skeleton.keypoints
    assert loaded.edges == skeleton.edges
    assert loaded.flip_idx == skeleton.flip_idx
    np.testing.assert_array_equal(loaded.positions, skeleton.positions)


def test_skeleton_file_defaults_flip_idx_to_identity(tmp_path: Path) -> None:
    path = tmp_path / "hen.skeleton.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "label": "hen",
                "keypoints": ["beak", "tail"],
                "edges": [[0, 1]],
                "positions": [[0.1, 0.2], [0.8, 0.7]],
            }
        ),
        encoding="utf-8",
    )

    assert read_skeleton_file(path).flip_idx == (0, 1)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda value: value.update(version=2), "unsupported skeleton file version"),
        (lambda value: value.update(keypoints=["beak", "beak"]), "must be unique"),
        (lambda value: value.update(edges=[[0, 3]]), "invalid skeleton edge"),
        (lambda value: value.update(flip_idx=[1, 1, 0]), "must be a permutation"),
    ],
)
def test_invalid_skeleton_file_is_rejected(
    *,
    skeleton: SkeletonTemplate,
    change: object,
    message: str,
) -> None:
    value = skeleton.to_dict()
    change(value)  # type: ignore[operator]

    with pytest.raises(ValueError, match=message):
        SkeletonTemplate.from_dict(value)


def test_make_skeleton_shape_places_normalized_template(
    skeleton: SkeletonTemplate,
) -> None:
    shape = make_skeleton_shape(skeleton=skeleton, bounds=(10, 20, 110, 220))

    assert shape.shape_type == "skeleton"
    assert shape.label == "hen"
    np.testing.assert_array_equal(
        shape.points,
        np.array(
            [
                [10, 20],
                [110, 20],
                [110, 220],
                [10, 220],
                [60, 40],
                [35, 200],
                [85, 200],
            ]
        ),
    )
    assert shape.other_data["pose"]["visibility"] == [2, 2, 2]


def test_make_skeleton_shape_from_interactively_placed_nodes() -> None:
    shape = make_skeleton_shape_from_nodes(
        label="rat",
        keypoints=("snout", "neck_base", "tail_base"),
        points=np.array([[20, 30], [50, 40], [80, 50]]),
        edges=((0, 1), (1, 2)),
        flip_idx=(0, 1, 2),
    )

    assert shape.shape_type == "skeleton"
    assert shape.label == "rat"
    _, keypoints = skeleton_shape_parts(shape=shape)
    np.testing.assert_array_equal(keypoints, [[20, 30], [50, 40], [80, 50]])
    assert shape.other_data["pose"]["keypoints"] == [
        "snout",
        "neck_base",
        "tail_base",
    ]
    assert shape.other_data["pose"]["edges"] == [[0, 1], [1, 2]]


def test_skeleton_template_from_shape_recovers_edited_layout(
    skeleton: SkeletonTemplate,
) -> None:
    shape = make_skeleton_shape(skeleton=skeleton, bounds=(10, 20, 110, 220))
    shape.points[4] = [35, 70]

    recovered = skeleton_template_from_shape(shape)

    np.testing.assert_array_equal(
        recovered.positions, np.array([[0.25, 0.25], [0.25, 0.9], [0.75, 0.9]])
    )


def test_skeleton_shape_annotation_boundary_round_trip(
    skeleton: SkeletonTemplate,
) -> None:
    shape = make_skeleton_shape(skeleton=skeleton, bounds=(10, 20, 110, 220))
    shape.other_data["pose"]["visibility"] = [2, 1, 0]

    loaded = _shapes_from_dicts(shape_dicts=[_shape_to_dict(shape)], label_flags=None)[
        0
    ]

    assert loaded.shape_type == "skeleton"
    assert loaded.other_data == shape.other_data
    np.testing.assert_array_equal(loaded.points, shape.points)


def test_legacy_two_corner_skeleton_is_upgraded_on_load(
    skeleton: SkeletonTemplate,
) -> None:
    shape = make_skeleton_shape(skeleton=skeleton, bounds=(10, 20, 110, 220))
    shape.points = np.vstack((shape.points[[0, 2]], shape.points[4:]))
    shape.point_labels = np.ones(len(shape.points), dtype=np.int_)

    loaded = _shapes_from_dicts(shape_dicts=[_shape_to_dict(shape)], label_flags=None)[
        0
    ]

    bbox, keypoints = skeleton_shape_parts(shape=loaded)
    np.testing.assert_array_equal(bbox, [[10, 20], [110, 20], [110, 220], [10, 220]])
    np.testing.assert_array_equal(keypoints, [[60, 40], [35, 200], [85, 200]])


def test_ensure_skeleton_oriented_bbox_is_idempotent(
    skeleton: SkeletonTemplate,
) -> None:
    shape = make_skeleton_shape(skeleton=skeleton, bounds=(10, 20, 110, 220))
    original = shape.points.copy()

    ensure_skeleton_oriented_bbox(shape)

    np.testing.assert_array_equal(shape.points, original)


def test_yolo_pose_row_uses_bbox_keypoints_and_visibility(
    skeleton: SkeletonTemplate,
) -> None:
    shape = make_skeleton_shape(skeleton=skeleton, bounds=(10, 20, 110, 220))
    shape.other_data["pose"]["visibility"] = [2, 1, 0]

    row = yolo_pose_row(shape=shape, class_index=3, image_width=200, image_height=400)

    assert row == "3 0.3 0.3 0.5 0.5 0.3 0.1 2 0.175 0.5 1 0 0 0"


def test_yolo_pose_row_rejects_non_skeleton_shape(
    skeleton: SkeletonTemplate,
) -> None:
    shape = make_skeleton_shape(skeleton=skeleton, bounds=(10, 20, 110, 220))
    shape.shape_type = "rectangle"

    with pytest.raises(ValueError, match="expected a skeleton shape"):
        yolo_pose_row(shape=shape, class_index=0, image_width=200, image_height=400)


def test_yolo_pose_rows_ignores_non_pose_shapes(
    skeleton: SkeletonTemplate,
) -> None:
    pose = make_skeleton_shape(skeleton=skeleton, bounds=(10, 20, 110, 220))
    other = pose.copy()
    other.shape_type = "rectangle"

    text = yolo_pose_rows(
        shapes=[other, pose],
        class_names=["hen"],
        image_width=200,
        image_height=400,
    )

    assert text.startswith("0 0.3 0.3 0.5 0.5 ")
    assert text.endswith("\n")
    assert text.count("\n") == 1


def test_yolo_dataset_yaml(skeleton: SkeletonTemplate) -> None:
    text = yolo_dataset_yaml(skeletons=[skeleton])

    assert "kpt_shape: [3, 3]" in text
    assert "flip_idx: [0, 2, 1]" in text
    assert '0: "hen"' in text
    assert '0: ["beak", "left_foot", "right_foot"]' in text
