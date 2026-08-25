from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from labelme._yolo_predictions import shapes_from_yolo_result


def _result(**values: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "names": {0: "rat", 1: "mouse"},
        "boxes": None,
        "obb": None,
        "masks": None,
        "keypoints": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _boxes(*, xyxy: list[list[float]], classes: list[int]) -> SimpleNamespace:
    return SimpleNamespace(
        xyxy=np.asarray(xyxy),
        conf=np.asarray([0.8] * len(xyxy)),
        cls=np.asarray(classes),
    )


def test_shapes_from_yolo_result_converts_detection_boxes() -> None:
    result = _result(boxes=_boxes(xyxy=[[1, 2, 30, 40]], classes=[0]))

    shapes = shapes_from_yolo_result(result, model_path=Path("model.pt"))

    assert len(shapes) == 1
    assert shapes[0].label == "rat"
    assert shapes[0].shape_type == "rectangle"
    np.testing.assert_array_equal(shapes[0].points, [[1, 2], [30, 40]])
    assert json.loads(shapes[0].description or "")["confidence"] == 0.8


def test_shapes_from_yolo_result_converts_oriented_boxes() -> None:
    obb = SimpleNamespace(
        xyxyxyxy=np.asarray([[[1, 2], [9, 2], [9, 8], [1, 8]]]),
        conf=np.asarray([0.8]),
        cls=np.asarray([1]),
    )

    shapes = shapes_from_yolo_result(_result(obb=obb), model_path=Path("model.pt"))

    assert shapes[0].label == "mouse"
    assert shapes[0].shape_type == "oriented_rectangle"
    np.testing.assert_array_equal(shapes[0].points, [[1, 2], [9, 2], [9, 8], [1, 8]])


def test_shapes_from_yolo_result_converts_segmentation_masks() -> None:
    boxes = _boxes(xyxy=[[1, 2, 30, 40]], classes=[0])
    masks = SimpleNamespace(xy=[np.asarray([[1, 2], [30, 2], [15, 40]])])

    shapes = shapes_from_yolo_result(
        _result(boxes=boxes, masks=masks), model_path=Path("model.pt")
    )

    assert shapes[0].shape_type == "polygon"
    np.testing.assert_array_equal(shapes[0].points, [[1, 2], [30, 2], [15, 40]])


def test_shapes_from_yolo_result_converts_semantic_regions_with_point_spacing() -> None:
    class_map = np.zeros((30, 40), dtype=np.uint8)
    class_map[5:25, 10:30] = 1
    result = _result()
    result.semantic_mask = SimpleNamespace(data=class_map)

    shapes = shapes_from_yolo_result(
        result,
        model_path=Path("yolo26n-sem.pt"),
        polygon_point_spacing=5,
    )

    assert {shape.label for shape in shapes} == {"rat", "mouse"}
    mouse = next(shape for shape in shapes if shape.label == "mouse")
    assert mouse.shape_type == "polygon"
    closed_points = np.vstack((mouse.points, mouse.points[0]))
    gaps = np.linalg.norm(np.diff(closed_points, axis=0), axis=1)
    assert gaps.max() <= 5
    assert json.loads(mouse.description or "") == {"model": "yolo26n-sem.pt"}


def test_shapes_from_yolo_result_maps_binary_semantic_class_one_to_only_name() -> None:
    class_map = np.zeros((20, 20), dtype=np.uint8)
    class_map[5:15, 5:15] = 1
    result = _result(names={0: "foreground"})
    result.semantic_mask = SimpleNamespace(data=class_map)

    shapes = shapes_from_yolo_result(result, model_path=Path("binary-sem.pt"))

    assert len(shapes) == 1
    assert shapes[0].label == "foreground"


def test_shapes_from_yolo_result_converts_pose_skeletons() -> None:
    boxes = _boxes(xyxy=[[1, 2, 30, 40]], classes=[0])
    keypoints = SimpleNamespace(
        xy=np.asarray([[[5, 6], [10, 12], [0, 0]]]),
        conf=np.asarray([[0.9, 0.5, 0.0]]),
    )

    shapes = shapes_from_yolo_result(
        _result(boxes=boxes, keypoints=keypoints),
        model_path=Path("model.pt"),
        model_metadata={
            "kpt_names": ["nose", "body", "tail"],
            "skeleton": [[1, 2], [2, 3]],
            "flip_idx": [0, 1, 2],
        },
    )

    shape = shapes[0]
    assert shape.shape_type == "skeleton"
    np.testing.assert_array_equal(
        shape.points,
        [[1, 2], [30, 2], [30, 40], [1, 40], [5, 6], [10, 12], [0, 0]],
    )
    assert shape.other_data["pose"] == {
        "keypoints": ["nose", "body", "tail"],
        "edges": [[0, 1], [1, 2]],
        "flip_idx": [0, 1, 2],
        "visibility": [2, 2, 0],
    }
