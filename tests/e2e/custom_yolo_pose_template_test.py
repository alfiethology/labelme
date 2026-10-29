from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._frame_refinement import FrameInferenceWorker
from labelme._frame_refinement import VideoInferenceWorker
from labelme._pose import SkeletonTemplate
from labelme._pose import write_skeleton_file
from labelme._widgets._custom_yolo_widget import CustomYoloWidget


def _template(path: Path, count: int = 3) -> None:
    names = ("nose", "body", "tail")[:count]
    write_skeleton_file(
        path,
        skeleton=SkeletonTemplate(
            label="template_class",
            keypoints=names,
            edges=tuple((i, i + 1) for i in range(count - 1)),
            positions=np.full((count, 2), 0.5),
            flip_idx=tuple(range(count)),
        ),
    )


def _fake_yolo(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeYolo:
        def __init__(self, path: str) -> None:
            self.model = SimpleNamespace(
                yaml={"kpt_names": ["wrong1", "wrong2", "wrong3"]}
            )

        def predict(self, **kwargs: object) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    names={0: "rat"},
                    obb=None,
                    masks=None,
                    boxes=SimpleNamespace(
                        xyxy=np.array([[1, 2, 30, 40]]),
                        conf=np.array([0.9]),
                        cls=np.array([0]),
                    ),
                    keypoints=SimpleNamespace(
                        xy=np.array([[[5, 6], [10, 12], [0, 0]]]),
                        conf=np.array([[0.9, 0.7, 0.0]]),
                    ),
                )
            ]

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=FakeYolo))


def test_pose_template_browse_is_remembered_per_model_and_can_be_cleared(
    raw_win: MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    widget = raw_win._custom_yolo
    model_a = tmp_path / "a.pt"
    model_b = tmp_path / "b.pt"
    template = tmp_path / "rat.skeleton.json"
    _template(template)
    widget._path_edit.setText(str(model_a))
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getOpenFileName", lambda *a: (str(template), "")
    )
    widget._browse_pose_template()
    assert widget.pose_template_path == template
    widget._path_edit.setText(str(model_b))
    assert widget.pose_template_path is None
    widget._path_edit.setText(str(model_a))
    assert widget.pose_template_path == template
    reopened = CustomYoloWidget(on_run=lambda: None)
    qtbot.addWidget(reopened)
    assert reopened.model_path == model_a
    assert reopened.pose_template_path == template
    reopened._pose_template_edit.clear()
    again = CustomYoloWidget(on_run=lambda: None)
    qtbot.addWidget(again)
    assert again.pose_template_path is None


def test_custom_detector_uses_template_names_and_bones_without_changing_predictions(
    raw_win: MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "pose.pt"
    model.write_bytes(b"unchanged model")
    template = tmp_path / "rat.skeleton.json"
    _template(template)
    _fake_yolo(monkeypatch)
    raw_win._custom_yolo._path_edit.setText(str(model))
    raw_win._custom_yolo._pose_template_edit.setText(str(template))
    raw_win._run_custom_yolo()
    shape = raw_win._canvas_widgets.canvas.shapes[-1]
    assert shape.label == "rat"  # The template does not change model class labels.
    assert shape.other_data["pose"] == {
        "keypoints": ["nose", "body", "tail"],
        "edges": [[0, 1], [1, 2]],
        "flip_idx": [0, 1, 2],
        "visibility": [2, 2, 0],
    }
    np.testing.assert_array_equal(shape.points[4:], [[5, 6], [10, 12], [0, 0]])
    assert model.read_bytes() == b"unchanged model"


def test_wrong_template_keypoint_count_is_rejected_without_adding_shapes(
    raw_win: MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "pose.pt"
    model.write_bytes(b"model")
    template = tmp_path / "wrong.skeleton.json"
    _template(template, count=2)
    _fake_yolo(monkeypatch)
    raw_win._custom_yolo._path_edit.setText(str(model))
    raw_win._custom_yolo._pose_template_edit.setText(str(template))
    errors = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "critical", lambda *args: errors.append(args)
    )
    raw_win._run_custom_yolo()
    assert not raw_win._canvas_widgets.canvas.shapes
    assert errors
    assert "template has 2 keypoints" in str(errors)
    assert "model predicts 3" in str(errors)


@pytest.mark.parametrize("video", [False, True])
def test_refinement_workers_use_the_selected_pose_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    video: bool,
) -> None:
    _fake_yolo(monkeypatch)
    template = tmp_path / "rat.skeleton.json"
    _template(template)
    image = tmp_path / "frame.png"
    Image.new("RGB", (100, 100)).save(image)
    if video:
        import cv2

        capture = SimpleNamespace(
            isOpened=lambda: True,
            set=lambda *a: None,
            read=lambda: (True, np.zeros((100, 100, 3), dtype=np.uint8)),
            release=lambda: None,
        )
        monkeypatch.setattr(cv2, "VideoCapture", lambda *a: capture)
        worker = VideoInferenceWorker(
            video_path=tmp_path / "clip.avi",
            frame_indices=[0],
            cache_dir=tmp_path,
            model_path=tmp_path / "pose.pt",
            confidence=0.25,
            pose_template_path=template,
        )
    else:
        worker = FrameInferenceWorker(
            image_paths=[image],
            model_path=tmp_path / "pose.pt",
            confidence=0.25,
            pose_template_path=template,
        )
    completed = []
    errors = []
    worker.completed.connect(completed.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert not errors
    shape = completed[0][0].shapes[0]
    assert shape.other_data["pose"]["keypoints"] == ["nose", "body", "tail"]
    assert shape.other_data["pose"]["edges"] == [[0, 1], [1, 2]]
