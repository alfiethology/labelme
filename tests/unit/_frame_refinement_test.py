from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np
from PIL import Image
from pytest import MonkeyPatch

from labelme._frame_refinement import FramePrediction
from labelme._frame_refinement import VideoInferenceWorker
from labelme._frame_refinement import save_refined_frame
from labelme._shape import Shape


def test_video_inference_worker_extracts_and_predicts_sampled_frames(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    import cv2

    video_path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),  # ty: ignore[unresolved-attribute]
        5.0,
        (40, 30),
    )
    assert writer.isOpened()
    try:
        for value in (255, 127, 0):
            writer.write(np.full((30, 40, 3), value, dtype=np.uint8))
    finally:
        writer.release()

    predicted_sources: list[str] = []

    class FakeYolo:
        def __init__(self, _model_path: str) -> None:
            self.model = SimpleNamespace(yaml={})

        def predict(self, *, source: str, **_kwargs: object) -> list[SimpleNamespace]:
            predicted_sources.append(source)
            return [
                SimpleNamespace(
                    names={},
                    obb=None,
                    boxes=None,
                    keypoints=None,
                    masks=None,
                )
            ]

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=FakeYolo))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    worker = VideoInferenceWorker(
        video_path=video_path,
        frame_indices=[0, 2],
        cache_dir=cache_dir,
        model_path=Path("model.pt"),
        confidence=0.25,
    )
    completed: list[object] = []
    progress: list[tuple[int, str]] = []
    worker.completed.connect(completed.append)
    worker.progress.connect(lambda count, name: progress.append((count, name)))

    worker.run()

    assert len(completed) == 1
    predictions = cast(list[FramePrediction], completed[0])
    assert isinstance(predictions, list)
    assert [prediction.image_path.name for prediction in predictions] == [
        "clip-00000000.jpg",
        "clip-00000002.jpg",
    ]
    assert all(prediction.image_path.exists() for prediction in predictions)
    assert predicted_sources == [
        str(prediction.image_path) for prediction in predictions
    ]
    assert progress == [(1, "frame 1"), (2, "frame 3")]


def test_save_refined_frame_preserves_relative_directory(tmp_path: Path) -> None:
    source = tmp_path / "frames"
    image_path = source / "camera-1" / "frame-001.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (20, 10), "white").save(image_path)
    output = tmp_path / "hard-frames"
    shape = Shape(
        label="rat",
        shape_type="rectangle",
        points=np.array([[1, 2], [10, 8]], dtype=np.float64),
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
