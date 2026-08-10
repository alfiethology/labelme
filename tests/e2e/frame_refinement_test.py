from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import FrameRefinementWindow
from labelme._app import MainWindow
from labelme._frame_refinement import FramePrediction
from labelme._shape import Shape

from .conftest import dismiss_active_modal


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
