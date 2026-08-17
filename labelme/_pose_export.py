from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np

from ._label_file import ShapeDict
from ._label_file import read_label_file
from ._pose import SkeletonTemplate
from ._pose import ensure_skeleton_oriented_bbox
from ._pose import skeleton_template_from_shape
from ._pose import write_skeleton_file
from ._pose import yolo_dataset_yaml
from ._pose import yolo_pose_rows
from ._shape import Shape
from ._shape import ShapeType
from ._utils import img_data_to_pil


@dataclass(frozen=True)
class PoseExportResult:
    images: int
    instances: int
    classes: tuple[str, ...]
    train_images: int
    val_images: int


@dataclass(frozen=True)
class _ExportItem:
    annotation_path: Path
    image_suffix: str
    image_data: bytes
    shapes: list[Shape]
    image_width: int
    image_height: int


def export_yolo_pose_dataset(
    *,
    annotation_dir: str | Path,
    output_dir: str | Path,
    val_fraction: float = 0.2,
) -> PoseExportResult:
    """Export a directory of Annotation Files as a YOLO pose dataset."""

    annotation_root = Path(annotation_dir).resolve()
    output_root = Path(output_dir).resolve()
    if not annotation_root.is_dir():
        raise ValueError(f"annotation directory does not exist: {annotation_root}")
    if not 0 <= val_fraction < 1:
        raise ValueError("val_fraction must be between 0 (inclusive) and 1 (exclusive)")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"output directory must be empty: {output_root}")

    annotation_paths = sorted(
        path
        for path in annotation_root.rglob("*.json")
        if not path.name.endswith(".skeleton.json") and output_root not in path.parents
    )
    if not annotation_paths:
        raise ValueError(f"no Annotation Files found in: {annotation_root}")

    items = [_read_export_item(path=path) for path in annotation_paths]
    skeleton_shapes = [
        shape
        for item in items
        for shape in item.shapes
        if shape.shape_type == "skeleton"
    ]
    if not skeleton_shapes:
        raise ValueError("no Skeleton Shapes found in the Annotation Files")
    templates = _templates_by_label(shapes=skeleton_shapes)
    class_names = sorted(templates)
    ordered_templates = [templates[label] for label in class_names]
    # Validate the dataset-wide keypoint count and flip mapping before writing.
    yaml_text = yolo_dataset_yaml(skeletons=ordered_templates)
    label_texts = {
        item.annotation_path: yolo_pose_rows(
            shapes=item.shapes,
            class_names=class_names,
            image_width=item.image_width,
            image_height=item.image_height,
        )
        for item in items
    }

    ranked = sorted(
        items,
        key=lambda item: hashlib.sha256(
            str(item.annotation_path.relative_to(annotation_root)).encode()
        ).digest(),
    )
    val_count = 0
    if len(ranked) > 1 and val_fraction > 0:
        val_count = max(1, round(len(ranked) * val_fraction))
        val_count = min(val_count, len(ranked) - 1)
    val_paths = {item.annotation_path for item in ranked[:val_count]}

    for item in items:
        split = "val" if item.annotation_path in val_paths else "train"
        relative = item.annotation_path.relative_to(annotation_root)
        image_relative = relative.with_suffix(item.image_suffix)
        image_path = output_root / "images" / split / image_relative
        label_path = output_root / "labels" / split / relative.with_suffix(".txt")
        image_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(item.image_data)
        label_path.write_text(
            label_texts[item.annotation_path],
            encoding="utf-8",
        )

    skeleton_dir = output_root / "skeletons"
    skeleton_dir.mkdir(parents=True, exist_ok=True)
    for index, skeleton in enumerate(ordered_templates):
        write_skeleton_file(skeleton_dir / f"{index}.skeleton.json", skeleton=skeleton)
    if val_count == 0:
        yaml_text = yolo_dataset_yaml(skeletons=ordered_templates, val="images/train")
    (output_root / "data.yaml").write_text(yaml_text, encoding="utf-8")
    return PoseExportResult(
        images=len(items),
        instances=len(skeleton_shapes),
        classes=tuple(class_names),
        train_images=len(items) - val_count,
        val_images=val_count,
    )


def _read_export_item(*, path: Path) -> _ExportItem:
    annotation = read_label_file(str(path))
    shapes = [_shape_from_dict(shape) for shape in annotation.shapes]
    image = img_data_to_pil(img_data=annotation.image_data)
    image_suffix = {
        "JPEG": ".jpg",
        "PNG": ".png",
    }.get(image.format or "", Path(annotation.image_path).suffix.lower() or ".jpg")
    return _ExportItem(
        annotation_path=path,
        image_suffix=image_suffix,
        image_data=annotation.image_data,
        shapes=shapes,
        image_width=image.width,
        image_height=image.height,
    )


def _shape_from_dict(shape: ShapeDict) -> Shape:
    loaded = Shape(
        label=shape["label"],
        group_id=shape["group_id"],
        shape_type=cast(ShapeType, shape["shape_type"]),
        flags=shape["flags"],
        description=shape["description"],
        mask=shape["mask"],
        points=np.asarray(shape["points"], dtype=np.float64),
        other_data=shape["other_data"],
        closed=True,
    )
    if loaded.shape_type == "skeleton":
        ensure_skeleton_oriented_bbox(loaded)
    return loaded


def _templates_by_label(*, shapes: list[Shape]) -> dict[str, SkeletonTemplate]:
    templates: dict[str, SkeletonTemplate] = {}
    for shape in shapes:
        if not shape.label:
            raise ValueError("every Skeleton Shape must have a non-empty label")
        candidate = skeleton_template_from_shape(shape)
        previous = templates.get(shape.label)
        if previous is not None and (
            previous.keypoints != candidate.keypoints
            or previous.edges != candidate.edges
            or previous.flip_idx != candidate.flip_idx
        ):
            raise ValueError(
                f"Skeleton Shapes for label {shape.label!r} use incompatible templates"
            )
        templates[shape.label] = candidate
    return templates
