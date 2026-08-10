from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from ._pose import POSE_DATA_KEY
from ._shape import Shape


def _to_numpy(value: Any) -> npt.NDArray[Any]:  # noqa: ANN401
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def _class_name(names: Mapping[int, str] | list[str], class_id: int) -> str:
    if isinstance(names, Mapping):
        return str(names[class_id])
    return str(names[class_id])


def _description(*, confidence: float, model_path: Path) -> str:
    return json.dumps({"confidence": confidence, "model": str(model_path)})


def _prediction_values(predictions: Any) -> tuple[npt.NDArray, npt.NDArray]:  # noqa: ANN401
    return (
        _to_numpy(predictions.conf).astype(np.float64),
        _to_numpy(predictions.cls).astype(int),
    )


def _pose_metadata(
    *, model_metadata: Mapping[str, Any] | None, keypoint_count: int
) -> tuple[list[str], list[list[int]], list[int]]:
    metadata = model_metadata or {}
    raw_names = metadata.get("kpt_names") or metadata.get("keypoint_names")
    if (
        isinstance(raw_names, list)
        and len(raw_names) == keypoint_count
        and all(isinstance(name, str) and name for name in raw_names)
    ):
        names = raw_names
    else:
        names = [f"keypoint_{index + 1}" for index in range(keypoint_count)]

    uses_one_based_edges = bool(metadata.get("skeleton"))
    raw_edges = metadata.get("skeleton") or metadata.get("edges") or []
    edges: list[list[int]] = []
    if isinstance(raw_edges, list):
        for raw_edge in raw_edges:
            if not (
                isinstance(raw_edge, list | tuple)
                and len(raw_edge) == 2
                and all(isinstance(index, int) for index in raw_edge)
            ):
                continue
            first, second = raw_edge
            # Ultralytics plotting skeletons use one-based indices. Labelme's
            # generic ``edges`` metadata is already zero-based.
            if uses_one_based_edges:
                first -= 1
                second -= 1
            if 0 <= first < keypoint_count and 0 <= second < keypoint_count:
                edges.append([first, second])

    raw_flip_idx = metadata.get("flip_idx")
    if (
        isinstance(raw_flip_idx, list)
        and len(raw_flip_idx) == keypoint_count
        and sorted(raw_flip_idx) == list(range(keypoint_count))
    ):
        flip_idx = raw_flip_idx
    else:
        flip_idx = list(range(keypoint_count))
    return list(names), edges, list(flip_idx)


def shapes_from_yolo_result(
    result: Any,  # noqa: ANN401
    *,
    model_path: Path,
    model_metadata: Mapping[str, Any] | None = None,
) -> list[Shape]:
    """Convert one Ultralytics result into editable Labelme shapes."""

    names = result.names
    if result.obb is not None:
        confidences, class_ids = _prediction_values(result.obb)
        points = _to_numpy(result.obb.xyxyxyxy).astype(np.float64)
        return [
            Shape(
                label=_class_name(names, int(class_id)),
                shape_type="oriented_rectangle",
                points=prediction_points,
                flags={},
                description=_description(
                    confidence=float(confidence), model_path=model_path
                ),
                closed=True,
            )
            for prediction_points, confidence, class_id in zip(
                points, confidences, class_ids, strict=True
            )
        ]

    boxes = result.boxes
    if boxes is None:
        return []
    confidences, class_ids = _prediction_values(boxes)

    if result.keypoints is not None:
        boxes_xyxy = _to_numpy(boxes.xyxy).astype(np.float64)
        keypoints = _to_numpy(result.keypoints.xy).astype(np.float64)
        keypoint_confidence = getattr(result.keypoints, "conf", None)
        if keypoint_confidence is None:
            detected = np.any(keypoints != 0, axis=2)
        else:
            detected = (np.any(keypoints != 0, axis=2)) & (
                _to_numpy(keypoint_confidence) > 0
            )
        visibility = np.where(detected, 2, 0)
        shapes: list[Shape] = []
        for box, nodes, node_visibility, confidence, class_id in zip(
            boxes_xyxy,
            keypoints,
            visibility,
            confidences,
            class_ids,
            strict=True,
        ):
            left, top, right, bottom = box
            bbox = np.array(
                [[left, top], [right, top], [right, bottom], [left, bottom]]
            )
            keypoint_names, edges, flip_idx = _pose_metadata(
                model_metadata=model_metadata, keypoint_count=len(nodes)
            )
            shapes.append(
                Shape(
                    label=_class_name(names, int(class_id)),
                    shape_type="skeleton",
                    points=np.vstack((bbox, nodes)),
                    point_labels=np.full(4 + len(nodes), 2, dtype=int),
                    flags={},
                    description=_description(
                        confidence=float(confidence), model_path=model_path
                    ),
                    other_data={
                        POSE_DATA_KEY: {
                            "keypoints": keypoint_names,
                            "edges": edges,
                            "flip_idx": flip_idx,
                            "visibility": node_visibility.astype(int).tolist(),
                        }
                    },
                    closed=True,
                )
            )
        return shapes

    if result.masks is not None:
        polygons = result.masks.xy
        return [
            Shape(
                label=_class_name(names, int(class_id)),
                shape_type="polygon",
                points=_to_numpy(points).astype(np.float64),
                flags={},
                description=_description(
                    confidence=float(confidence), model_path=model_path
                ),
                closed=True,
            )
            for points, confidence, class_id in zip(
                polygons, confidences, class_ids, strict=True
            )
            if len(points) >= 3
        ]

    xyxy = _to_numpy(boxes.xyxy).astype(np.float64)
    return [
        Shape(
            label=_class_name(names, int(class_id)),
            shape_type="rectangle",
            points=np.array([[left, top], [right, bottom]], dtype=np.float64),
            flags={},
            description=_description(
                confidence=float(confidence), model_path=model_path
            ),
            closed=True,
        )
        for (left, top, right, bottom), confidence, class_id in zip(
            xyxy, confidences, class_ids, strict=True
        )
    ]
