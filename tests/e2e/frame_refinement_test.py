from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytest import MonkeyPatch
from pytestqt.qtbot import QtBot

from labelme._app import FrameRefinementWindow
from labelme._app import MainWindow
from labelme._app import VideoSkimRefinementWindow
from labelme._frame_refinement import FramePrediction
from labelme._shape import Shape

from .conftest import dismiss_active_modal


def _write_test_video(path: Path) -> None:
    import cv2
    import numpy as np

    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        5.0,
        (40, 30),
    )
    assert writer.isOpened()
    try:
        writer.write(np.full((30, 40, 3), (255, 255, 255), dtype=np.uint8))
        writer.write(np.full((30, 40, 3), (0, 0, 0), dtype=np.uint8))
    finally:
        writer.release()


class _ProgressEmitter(QtCore.QObject):
    progress = QtCore.Signal(int, str)
    done = QtCore.Signal()

    @QtCore.Slot()
    def emit_progress(self) -> None:
        self.progress.emit(1, "frame.png")
        self.done.emit()


class _ProgressRecorder:
    def __init__(self) -> None:
        self.threads: list[QtCore.QThread] = []

    def setLabelText(self, _text: str) -> None:
        self.threads.append(QtCore.QThread.currentThread())

    def setValue(self, _value: int) -> None:
        self.threads.append(QtCore.QThread.currentThread())


def test_refinement_progress_updates_run_on_gui_thread(
    raw_win: MainWindow,
    qapp: QtWidgets.QApplication,
    qtbot: QtBot,
) -> None:
    window = raw_win
    recorder = _ProgressRecorder()
    window._refine_progress = recorder
    window._refine_total_frames = 1
    emitter = _ProgressEmitter()
    thread = QtCore.QThread()
    emitter.moveToThread(thread)
    emitter.progress.connect(window._on_refine_inference_progress)
    thread.started.connect(emitter.emit_progress)
    emitter.done.connect(thread.quit)

    thread.start()
    qtbot.waitUntil(lambda: len(recorder.threads) == 2)
    thread.wait()

    assert all(delivery_thread == qapp.thread() for delivery_thread in recorder.threads)


def test_frame_refinement_skips_easy_frame_and_saves_refined_frame(
    qapp: QtWidgets.QApplication,
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = tmp_path / "frames"
    source.mkdir()
    first = source / "frame-001.png"
    second = source / "frame-002.png"
    Image.new("RGB", (40, 30), "white").save(first)
    Image.new("RGB", (40, 30), "white").save(second)
    shape = Shape(
        label="rat",
        shape_type="rectangle",
        points=[[2, 3], [20, 25]],
        closed=True,
    )
    window = FrameRefinementWindow(
        predictions=[
            FramePrediction(image_path=first, shapes=[shape]),
            FramePrediction(image_path=second, shapes=[shape]),
        ],
        source_dir=source,
        output_dir=source,
        model_path=Path("model.pt"),
        config_file=None,
        config_overrides={},
    )
    qtbot.addWidget(window)
    window.show()

    assert window._skip_frame_button.font().bold()
    assert window._skip_frame_button.font().pointSize() >= 18
    assert window._leave_refinement_button.font().bold()
    assert window._leave_refinement_button.font().pointSize() >= 18
    assert window._refine_frame_button.font().bold()
    assert window._refine_frame_button.font().pointSize() >= 18

    qtbot.mouseClick(window._skip_frame_button, QtCore.Qt.MouseButton.LeftButton)
    assert window._frame_index == 1
    assert not first.with_suffix(".json").exists()

    qtbot.mouseClick(window._refine_frame_button, QtCore.Qt.MouseButton.LeftButton)
    assert window._frame_refining
    assert window._refine_frame_button.text() == "SAVE && NEXT"

    QtCore.QTimer.singleShot(0, lambda: dismiss_active_modal(qtbot=qtbot))
    qtbot.mouseClick(window._refine_frame_button, QtCore.Qt.MouseButton.LeftButton)

    assert not first.with_suffix(".json").exists()
    assert second.exists()
    annotation = json.loads(second.with_suffix(".json").read_text())
    assert annotation["shapes"][0]["label"] == "rat"
    assert window._frame_kept == 1
    assert window._frame_skipped == 1


def test_frame_refinement_can_leave_early_after_saving_finished_jsons(
    qapp: QtWidgets.QApplication,
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = tmp_path / "frames"
    source.mkdir()
    first = source / "frame-001.png"
    second = source / "frame-002.png"
    Image.new("RGB", (40, 30), "white").save(first)
    Image.new("RGB", (40, 30), "white").save(second)
    shape = Shape(
        label="rat",
        shape_type="rectangle",
        points=[[2, 3], [20, 25]],
        closed=True,
    )
    window = FrameRefinementWindow(
        predictions=[
            FramePrediction(image_path=first, shapes=[shape]),
            FramePrediction(image_path=second, shapes=[shape]),
        ],
        source_dir=source,
        output_dir=source,
        model_path=Path("model.pt"),
        config_file=None,
        config_overrides={},
    )
    window.show()

    qtbot.mouseClick(window._refine_frame_button, QtCore.Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._refine_frame_button, QtCore.Qt.MouseButton.LeftButton)

    assert first.with_suffix(".json").exists()
    assert window._frame_index == 1

    qtbot.mouseClick(window._leave_refinement_button, QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.isVisible())

    assert first.with_suffix(".json").exists()
    assert not second.with_suffix(".json").exists()


def test_video_skim_refinement_saves_only_refined_sampled_frames(
    qapp: QtWidgets.QApplication,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    video_path = tmp_path / "clip.avi"
    output_dir = tmp_path / "clip_refined_frames"
    _write_test_video(video_path)
    window = VideoSkimRefinementWindow(
        video_path=video_path,
        output_dir=output_dir,
        frame_indices=[0, 1],
        model_path=Path("model.pt"),
        confidence=0.25,
        config_file=None,
        config_overrides={},
    )
    monkeypatch.setattr(
        window,
        "_load_video_prediction_for_current_frame",
        lambda: True,
    )
    window.show()

    qtbot.mouseClick(window._video_skip_button, QtCore.Qt.MouseButton.LeftButton)
    assert window._video_index == 1

    qtbot.mouseClick(window._video_refine_button, QtCore.Qt.MouseButton.LeftButton)
    QtCore.QTimer.singleShot(0, lambda: dismiss_active_modal(qtbot=qtbot))
    qtbot.mouseClick(window._video_refine_button, QtCore.Qt.MouseButton.LeftButton)

    saved_jsons = sorted(output_dir.glob("*.json"))
    saved_images = sorted(output_dir.glob("*.jpg"))
    assert len(saved_jsons) == 1
    assert len(saved_images) == 1
    assert saved_jsons[0].stem == saved_images[0].stem
    window.close()
