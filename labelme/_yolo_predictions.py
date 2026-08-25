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


def _model_description(*, model_path: Path) -> str:
    return json.dumps({"model": str(model_path)})


def _resample_closed_contour(
    points: npt.NDArray[Any], *, point_spacing: float
) -> npt.NDArray[np.float64]:
    """Return points at approximately equal arc-length intervals."""

    if point_spacing <= 0:
        raise ValueError("Polygon point spacing must be greater than zero")
    contour = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(contour) < 3:
        return contour
    keep = np.r_[True, np.any(np.diff(contour, axis=0) != 0, axis=1)]
    contour = contour[keep]
    if len(contour) > 1 and np.array_equal(contour[0], contour[-1]):
        contour = contour[:-1]
    if len(contour) < 3:
        return contour

    following = np.roll(contour, -1, axis=0)
    segment_lengths = np.linalg.norm(following - contour, axis=1)
    nonzero = segment_lengths > 0
    contour = contour[nonzero]
    segment_lengths = segment_lengths[nonzero]
    if len(contour) < 3:
        return contour
    perimeter = float(segment_lengths.sum())
    if perimeter == 0:
        return contour

    point_count = max(3, int(np.ceil(perimeter / point_spacing)))
    offsets = np.arange(point_count, dtype=np.float64) * perimeter / point_count
    cumulative = np.r_[0.0, np.cumsum(segment_lengths)]
    segment_indices = np.searchsorted(cumulative, offsets, side="right") - 1
    fractions = (offsets - cumulative[segment_indices]) / segment_lengths[
        segment_indices
    ]
    following = np.roll(contour, -1, axis=0)
    return contour[segment_indices] + fractions[:, None] * (
        following[segment_indices] - contour[segment_indices]
    )


def _semantic_shapes(
    result: Any,  # noqa: ANN401
    *,
    model_path: Path,
    point_spacing: float,
) -> list[Shape]:
    """Convert a dense semantic class map into one polygon per class region."""

    import cv2

    class_map = _to_numpy(result.semantic_mask.data)
    if class_map.ndim == 3 and class_map.shape[0] == 1:
        class_map = class_map[0]
    if class_map.ndim != 2:
        raise ValueError(
            "Expected the YOLO semantic mask to have shape (height, width), "
            f"but got {class_map.shape}"
        )

    names = result.names
    shapes_by_area: list[tuple[float, Shape]] = []
    for raw_class_id in np.unique(class_map):
        class_id = int(raw_class_id)
        if len(names) == 1:
            # Ultralytics reserves 0 for the background of a binary semantic
            # model and writes its only named class as 1 in the dense map.
            if class_id != 1:
                continue
            label = _class_name(names, 0)
        else:
            try:
                label = _class_name(names, class_id)
            except (IndexError, KeyError):
                continue
        binary_mask = (class_map == raw_class_id).astype(np.uint8)
        contours, _ = cv2.findContours(
            binary_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_NONE,
        )
        for raw_contour in contours:
            if len(raw_contour) < 3 or cv2.contourArea(raw_contour) <= 0:
                continue
            points = _resample_closed_contour(
                raw_contour[:, 0, :], point_spacing=point_spacing
            )
            if len(points) < 3:
                continue
            shapes_by_area.append(
                (
                    float(cv2.contourArea(raw_contour)),
                    Shape(
                        label=label,
                        shape_type="polygon",
                        points=points,
                        flags={},
                        description=_model_description(model_path=model_path),
                        closed=True,
                    ),
                )
            )
    # Large enclosing regions must be drawn first so nested, smaller regions
    # can overwrite them when Labelme rasterizes overlapping polygons.
    return [shape for _, shape in sorted(shapes_by_area, key=lambda item: -item[0])]


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
    polygon_point_spacing: float | None = None,
) -> list[Shape]:
    """Convert one Ultralytics result into editable Labelme shapes."""

    names = result.names
    if getattr(result, "semantic_mask", None) is not None:
        return _semantic_shapes(
            result,
            model_path=model_path,
            point_spacing=(
                10.0 if polygon_point_spacing is None else polygon_point_spacing
            ),
        )
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
                points=(
                    _resample_closed_contour(
                        _to_numpy(points), point_spacing=polygon_point_spacing
                    )
                    if polygon_point_spacing is not None
                    else _to_numpy(points).astype(np.float64)
                ),
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
