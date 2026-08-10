from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from labelme._frame_refinement import save_refined_frame
from labelme._shape import Shape


def test_save_refined_frame_preserves_relative_directory(tmp_path: Path) -> None:
    source = tmp_path / "frames"
    image_path = source / "camera-1" / "frame-001.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (20, 10), "white").save(image_path)
    output = tmp_path / "hard-frames"
    shape = Shape(
        label="rat",
        shape_type="rectangle",
        points=[[1, 2], [10, 8]],
        closed=True,
    )

    saved_image, saved_label = save_refined_frame(
        source_root=source,
        output_root=output,
        image_path=image_path,
        shapes=[shape],
        image_height=10,
        image_width=20,
    )

    assert saved_image == output / "camera-1" / "frame-001.png"
    assert saved_label == output / "camera-1" / "frame-001.json"
    assert saved_image.read_bytes() == image_path.read_bytes()
    payload = json.loads(saved_label.read_text())
    assert payload["imagePath"] == "frame-001.png"
    assert payload["imageData"] is None
    assert payload["shapes"][0]["shape_type"] == "rectangle"
    assert payload["refinementSource"] == str(image_path)


def test_save_refined_frame_does_not_overwrite_output(tmp_path: Path) -> None:
    source = tmp_path / "frames"
    source.mkdir()
    image_path = source / "frame.png"
    Image.new("RGB", (2, 2), "white").save(image_path)
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "frame.png"
    existing.write_bytes(b"keep me")

    try:
        save_refined_frame(
            source_root=source,
            output_root=output,
            image_path=image_path,
            shapes=[],
            image_height=2,
            image_width=2,
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected existing refinement output to be rejected")

    assert existing.read_bytes() == b"keep me"


def test_save_refined_frame_can_write_json_beside_source_image(
    tmp_path: Path,
) -> None:
    source = tmp_path / "to_label"
    source.mkdir()
    image_path = source / "frame.png"
    Image.new("RGB", (5, 4), "white").save(image_path)
    original_image = image_path.read_bytes()

    saved_image, saved_label = save_refined_frame(
        source_root=source,
        output_root=source,
        image_path=image_path,
        shapes=[],
        image_height=4,
        image_width=5,
    )

    assert saved_image == image_path
    assert saved_label == source / "frame.json"
    assert image_path.read_bytes() == original_image
    assert json.loads(saved_label.read_text())["imagePath"] == "frame.png"
