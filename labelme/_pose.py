from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Final
from typing import cast

import numpy as np
import numpy.typing as npt

from ._shape import Shape

SKELETON_FILE_VERSION: Final[int] = 1
POSE_DATA_KEY: Final[str] = "pose"


@dataclass(frozen=True)
class SkeletonTemplate:
    """Reusable definition and neutral layout for one pose class."""

    label: str
    keypoints: tuple[str, ...]
    edges: tuple[tuple[int, int], ...]
    positions: npt.NDArray[np.float64]
    flip_idx: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("skeleton label must not be empty")
        if not self.keypoints:
            raise ValueError("skeleton must define at least one keypoint")
        if any(not name.strip() for name in self.keypoints):
            raise ValueError("keypoint names must not be empty")
        if len(set(self.keypoints)) != len(self.keypoints):
            raise ValueError("keypoint names must be unique")

        positions = np.array(self.positions, dtype=np.float64).reshape(-1, 2)
        if len(positions) != len(self.keypoints):
            raise ValueError(
                "positions must contain one [x, y] pair per keypoint: "
                f"expected {len(self.keypoints)}, got {len(positions)}"
            )
        if not np.isfinite(positions).all():
            raise ValueError("keypoint positions must be finite")
        if ((positions < 0) | (positions > 1)).any():
            raise ValueError("keypoint positions must be normalized between 0 and 1")
        object.__setattr__(self, "positions", positions)

        keypoint_count = len(self.keypoints)
        for edge in self.edges:
            if len(edge) != 2 or any(i < 0 or i >= keypoint_count for i in edge):
                raise ValueError(f"invalid skeleton edge: {edge!r}")
            if edge[0] == edge[1]:
                raise ValueError(
                    f"skeleton edge cannot join a point to itself: {edge!r}"
                )

        if len(self.flip_idx) != keypoint_count:
            raise ValueError(
                "flip_idx must contain one index per keypoint: "
                f"expected {keypoint_count}, got {len(self.flip_idx)}"
            )
        if sorted(self.flip_idx) != list(range(keypoint_count)):
            raise ValueError("flip_idx must be a permutation of the keypoint indices")
        if any(self.flip_idx[self.flip_idx[i]] != i for i in range(keypoint_count)):
            raise ValueError("flip_idx must be symmetric")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SKELETON_FILE_VERSION,
            "label": self.label,
            "keypoints": list(self.keypoints),
            "edges": [list(edge) for edge in self.edges],
            "positions": self.positions.tolist(),
            "flip_idx": list(self.flip_idx),
        }

    @classmethod
    def from_dict(cls, value: object) -> SkeletonTemplate:
        if not isinstance(value, dict):
            raise TypeError("skeleton file must contain a JSON object")
        value = cast(dict[str, Any], value)
        if value.get("version") != SKELETON_FILE_VERSION:
            raise ValueError(
                "unsupported skeleton file version: "
                f"{value.get('version')!r}; expected {SKELETON_FILE_VERSION}"
            )

        label = value.get("label")
        keypoints = value.get("keypoints")
        edges = value.get("edges", [])
        positions = value.get("positions")
        flip_idx = value.get("flip_idx")
        if not isinstance(label, str):
            raise TypeError("skeleton label must be a string")
        if not isinstance(keypoints, list) or not all(
            isinstance(name, str) for name in keypoints
        ):
            raise TypeError("skeleton keypoints must be a list of strings")
        if not isinstance(edges, list) or not all(
            isinstance(edge, list)
            and len(edge) == 2
            and all(isinstance(i, int) and not isinstance(i, bool) for i in edge)
            for edge in edges
        ):
            raise TypeError("skeleton edges must be a list of [from, to] indices")
        if not isinstance(positions, list):
            raise TypeError("skeleton positions must be a list of [x, y] pairs")
        if flip_idx is None:
            flip_idx = list(range(len(keypoints)))
        if not isinstance(flip_idx, list) or not all(
            isinstance(i, int) and not isinstance(i, bool) for i in flip_idx
        ):
            raise TypeError("skeleton flip_idx must be a list of indices")
        return cls(
            label=label,
            keypoints=tuple(keypoints),
            edges=tuple(tuple(edge) for edge in edges),
            positions=np.asarray(positions, dtype=np.float64),
            flip_idx=tuple(flip_idx),
        )


def read_skeleton_file(filename: str | Path) -> SkeletonTemplate:
    with open(filename, encoding="utf-8") as file:
        return SkeletonTemplate.from_dict(json.load(file))


def write_skeleton_file(filename: str | Path, *, skeleton: SkeletonTemplate) -> None:
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(skeleton.to_dict(), file, ensure_ascii=False, indent=2)
        file.write("\n")


def make_skeleton_shape(
    *,
    skeleton: SkeletonTemplate,
    bounds: tuple[float, float, float, float],
) -> Shape:
    """Place a template in an image-space (left, top, right, bottom) box."""

    left, top, right, bottom = bounds
    if not all(np.isfinite((left, top, right, bottom))):
        raise ValueError("skeleton bounds must be finite")
    if right <= left or bottom <= top:
        raise ValueError("skeleton bounds must have positive width and height")
    size = np.array([right - left, bottom - top], dtype=np.float64)
    keypoints = skeleton.positions * size + np.array([left, top])
    bbox = np.array(
        [[left, top], [right, top], [right, bottom], [left, bottom]],
        dtype=np.float64,
    )
    points = np.vstack((bbox, keypoints))
    return Shape(
        label=skeleton.label,
        shape_type="skeleton",
        points=points,
        point_labels=np.array([2] * len(points), dtype=np.int_),
        closed=True,
        other_data={
            POSE_DATA_KEY: {
                "keypoints": list(skeleton.keypoints),
                "edges": [list(edge) for edge in skeleton.edges],
                "flip_idx": list(skeleton.flip_idx),
                "visibility": [2] * len(skeleton.keypoints),
            }
        },
    )


def make_skeleton_shape_from_nodes(
    *,
    label: str,
    keypoints: tuple[str, ...],
    points: npt.ArrayLike,
    edges: tuple[tuple[int, int], ...],
    flip_idx: tuple[int, ...],
) -> Shape:
    """Create a Skeleton Shape around interactively placed image-space nodes."""

    node_points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(node_points) != len(keypoints):
        raise ValueError(
            "points must contain one [x, y] pair per keypoint: "
            f"expected {len(keypoints)}, got {len(node_points)}"
        )
    if not len(node_points):
        raise ValueError("place at least one skeleton node")
    if not np.isfinite(node_points).all():
        raise ValueError("skeleton node positions must be finite")
    minimum = node_points.min(axis=0)
    maximum = node_points.max(axis=0)
    span = maximum - minimum
    margin = np.maximum(span * 0.1, np.array([10.0, 10.0]))
    left, top = minimum - margin
    right, bottom = maximum + margin
    positions = (node_points - np.array([left, top])) / np.array(
        [right - left, bottom - top]
    )
    skeleton = SkeletonTemplate(
        label=label,
        keypoints=keypoints,
        edges=edges,
        positions=positions,
        flip_idx=flip_idx,
    )
    return make_skeleton_shape(skeleton=skeleton, bounds=(left, top, right, bottom))


def skeleton_template_from_shape(shape: Shape) -> SkeletonTemplate:
    """Recover a reusable normalized template from a Skeleton Shape."""

    pose_data, keypoint_names, _ = _pose_metadata(shape)
    edges = pose_data.get("edges", [])
    flip_idx = pose_data.get("flip_idx", list(range(len(keypoint_names))))
    if not isinstance(edges, list) or not all(
        isinstance(edge, list)
        and len(edge) == 2
        and all(isinstance(i, int) and not isinstance(i, bool) for i in edge)
        for edge in edges
    ):
        raise ValueError("skeleton pose metadata has invalid edges")
    if not isinstance(flip_idx, list) or not all(
        isinstance(i, int) and not isinstance(i, bool) for i in flip_idx
    ):
        raise ValueError("skeleton pose metadata has invalid flip_idx")

    bbox, keypoint_points = skeleton_shape_parts(shape=shape)
    if len(bbox) == 2:
        (x1, y1), (x2, y2) = bbox
        left, right = sorted((float(x1), float(x2)))
        top, bottom = sorted((float(y1), float(y2)))
        origin = np.array([left, top])
        basis = np.array([[right - left, 0.0], [0.0, bottom - top]])
    else:
        origin = bbox[0]
        basis = np.column_stack((bbox[1] - bbox[0], bbox[3] - bbox[0]))
    if abs(float(np.linalg.det(basis))) <= np.finfo(np.float64).eps:
        raise ValueError("skeleton bounding box must have positive width and height")
    positions = np.linalg.solve(basis, (keypoint_points - origin).T).T
    if ((positions < 0) | (positions > 1)).any():
        raise ValueError("every keypoint must be inside the skeleton bounding box")
    return SkeletonTemplate(
        label=shape.label or "",
        keypoints=tuple(keypoint_names),
        edges=tuple(tuple(edge) for edge in edges),
        positions=positions,
        flip_idx=tuple(flip_idx),
    )


def yolo_pose_row(
    *,
    shape: Shape,
    class_index: int,
    image_width: int,
    image_height: int,
) -> str:
    """Convert one Skeleton Shape to an Ultralytics YOLO pose row."""

    if class_index < 0:
        raise ValueError("class_index must not be negative")
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    _, keypoint_names, visibility = _pose_metadata(shape)
    bbox, keypoint_points = skeleton_shape_parts(shape=shape)
    if len(visibility) != len(keypoint_names):
        raise ValueError("skeleton visibility does not match its keypoint definition")

    left = float(bbox[:, 0].min())
    right = float(bbox[:, 0].max())
    top = float(bbox[:, 1].min())
    bottom = float(bbox[:, 1].max())
    box = (
        ((left + right) / 2) / image_width,
        ((top + bottom) / 2) / image_height,
        (right - left) / image_width,
        (bottom - top) / image_height,
    )
    values: list[str] = [str(class_index), *(_format_number(v) for v in box)]
    for (x, y), visible in zip(keypoint_points, visibility, strict=True):
        if visible == 0:
            x = y = 0.0
        values.extend(
            (
                _format_number(float(x) / image_width),
                _format_number(float(y) / image_height),
                str(visible),
            )
        )
    return " ".join(values)


def yolo_pose_rows(
    *,
    shapes: list[Shape],
    class_names: list[str],
    image_width: int,
    image_height: int,
) -> str:
    """Export every Skeleton Shape in one Annotation as YOLO pose text."""

    if len(set(class_names)) != len(class_names):
        raise ValueError("class_names must be unique")
    class_indices = {name: index for index, name in enumerate(class_names)}
    skeleton_shapes = [shape for shape in shapes if shape.shape_type == "skeleton"]
    labels = [shape.label for shape in skeleton_shapes]
    if not all(isinstance(label, str) for label in labels):
        raise ValueError("every skeleton shape must have a label")
    string_labels = cast(list[str], labels)
    unknown = sorted(set(string_labels) - class_indices.keys())
    if unknown:
        raise ValueError(f"skeleton labels are not in class_names: {unknown!r}")
    rows = [
        yolo_pose_row(
            shape=shape,
            class_index=class_indices[label],
            image_width=image_width,
            image_height=image_height,
        )
        for shape, label in zip(skeleton_shapes, string_labels, strict=True)
    ]
    return "" if not rows else "\n".join(rows) + "\n"


def yolo_dataset_yaml(
    *,
    skeletons: list[SkeletonTemplate],
    train: str = "images/train",
    val: str = "images/val",
) -> str:
    """Build an Ultralytics pose dataset YAML for compatible templates."""

    if not skeletons:
        raise ValueError("at least one skeleton template is required")
    keypoint_count = len(skeletons[0].keypoints)
    if any(len(skeleton.keypoints) != keypoint_count for skeleton in skeletons):
        raise ValueError(
            "Ultralytics requires every pose class to use the same keypoint count"
        )
    if any(skeleton.flip_idx != skeletons[0].flip_idx for skeleton in skeletons):
        raise ValueError(
            "Ultralytics uses one flip_idx for the dataset; all templates must match"
        )
    if len({skeleton.label for skeleton in skeletons}) != len(skeletons):
        raise ValueError("skeleton template labels must be unique")

    lines = [
        "path: .",
        f"train: {json.dumps(train, ensure_ascii=False)}",
        f"val: {json.dumps(val, ensure_ascii=False)}",
        "",
        f"kpt_shape: [{keypoint_count}, 3]",
        f"flip_idx: {json.dumps(list(skeletons[0].flip_idx))}",
        "",
        "names:",
    ]
    for index, skeleton in enumerate(skeletons):
        lines.append(f"  {index}: {json.dumps(skeleton.label, ensure_ascii=False)}")
    lines.extend(("", "kpt_names:"))
    for index, skeleton in enumerate(skeletons):
        lines.append(
            f"  {index}: {json.dumps(list(skeleton.keypoints), ensure_ascii=False)}"
        )
    return "\n".join(lines) + "\n"


def _pose_metadata(shape: Shape) -> tuple[dict[str, Any], list[str], list[int]]:
    if shape.shape_type != "skeleton":
        raise ValueError(f"expected a skeleton shape, got {shape.shape_type!r}")
    pose_data = shape.other_data.get(POSE_DATA_KEY)
    if not isinstance(pose_data, dict):
        raise ValueError("skeleton shape is missing pose metadata")
    keypoint_names = pose_data.get("keypoints")
    visibility = pose_data.get("visibility")
    if not isinstance(keypoint_names, list) or not all(
        isinstance(name, str) for name in keypoint_names
    ):
        raise ValueError("skeleton pose metadata has invalid keypoints")
    if not isinstance(visibility, list) or not all(
        isinstance(value, int) and not isinstance(value, bool) and value in (0, 1, 2)
        for value in visibility
    ):
        raise ValueError("skeleton visibility values must be 0, 1, or 2")
    return pose_data, keypoint_names, visibility


def skeleton_shape_parts(
    *, shape: Shape
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Return bbox vertices and keypoints for current and legacy Skeleton Shapes."""

    _, keypoint_names, _ = _pose_metadata(shape)
    bbox_point_count = len(shape.points) - len(keypoint_names)
    if bbox_point_count not in (2, 4):
        raise ValueError(
            "skeleton points do not match its keypoint definition: "
            f"expected {len(keypoint_names) + 2} or {len(keypoint_names) + 4}, "
            f"got {len(shape.points)}"
        )
    return shape.points[:bbox_point_count], shape.points[bbox_point_count:]


def ensure_skeleton_oriented_bbox(shape: Shape) -> None:
    """Upgrade a legacy two-corner Skeleton Shape to four transform corners."""

    bbox, keypoints = skeleton_shape_parts(shape=shape)
    if len(bbox) == 4:
        return
    (x1, y1), (x2, y2) = bbox
    left, right = sorted((float(x1), float(x2)))
    top, bottom = sorted((float(y1), float(y2)))
    oriented_bbox = np.array(
        [[left, top], [right, top], [right, bottom], [left, bottom]],
        dtype=np.float64,
    )
    shape.points = np.vstack((oriented_bbox, keypoints))
    shape.point_labels = np.ones(len(shape.points), dtype=np.int_)


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
