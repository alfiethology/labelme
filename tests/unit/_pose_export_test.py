from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import PIL.Image
import pytest

from labelme._app import _shape_to_dict
from labelme._label_file import Annotation
from labelme._label_file import write_label_file
from labelme._pose import SkeletonTemplate
from labelme._pose import make_skeleton_shape
from labelme._pose_export import export_yolo_pose_dataset


def _image_data() -> bytes:
    image = PIL.Image.new("RGB", (200, 100), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _write_annotation(path: Path, *, x_offset: float) -> None:
    skeleton = SkeletonTemplate(
        label="hen",
        keypoints=("beak", "tail"),
        edges=((0, 1),),
        positions=np.array([[0.2, 0.5], [0.8, 0.5]]),
        flip_idx=(0, 1),
    )
    shape = make_skeleton_shape(
        skeleton=skeleton, bounds=(10 + x_offset, 20, 110 + x_offset, 80)
    )
    write_label_file(
        filename=str(path),
        annotation=Annotation(
            image_path=f"{path.stem}.png",
            image_data=_image_data(),
            shapes=[_shape_to_dict(shape)],
            flags={},
            other_data={},
        ),
        image_height=100,
        image_width=200,
        save_image_data=True,
    )


def test_export_yolo_pose_dataset(tmp_path: Path) -> None:
    annotations = tmp_path / "annotations"
    annotations.mkdir()
    _write_annotation(annotations / "one.json", x_offset=0)
    _write_annotation(annotations / "two.json", x_offset=20)
    output = tmp_path / "yolo"

    result = export_yolo_pose_dataset(
        annotation_dir=annotations, output_dir=output, val_fraction=0.2
    )

    assert result.images == 2
    assert result.instances == 2
    assert result.classes == ("hen",)
    assert result.train_images == 1
    assert result.val_images == 1
    assert len(list((output / "images" / "train").glob("*.png"))) == 1
    assert len(list((output / "images" / "val").glob("*.png"))) == 1
    label_paths = sorted((output / "labels").rglob("*.txt"))
    assert len(label_paths) == 2
    assert all(
        path.read_text(encoding="utf-8").startswith("0 ") for path in label_paths
    )
    yaml_text = (output / "data.yaml").read_text(encoding="utf-8")
    assert "kpt_shape: [2, 3]" in yaml_text
    assert '0: "hen"' in yaml_text
    assert (output / "skeletons" / "0.skeleton.json").is_file()


def test_export_rejects_non_empty_output_before_writing(tmp_path: Path) -> None:
    annotations = tmp_path / "annotations"
    annotations.mkdir()
    _write_annotation(annotations / "one.json", x_offset=0)
    output = tmp_path / "yolo"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("mine", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        export_yolo_pose_dataset(annotation_dir=annotations, output_dir=output)

    assert marker.read_text(encoding="utf-8") == "mine"
