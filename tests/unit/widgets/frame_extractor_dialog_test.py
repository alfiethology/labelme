from __future__ import annotations

import threading
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from labelme._frame_extraction import ExtractionOptions
from labelme._frame_extraction import ExtractionResult
from labelme._widgets import frame_extractor_dialog as module
from labelme._widgets.frame_extractor_dialog import FrameExtractorDialog


def test_sampling_controls_and_output_names(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = FrameExtractorDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    assert not dialog.method_group.isEnabled()
    dialog.percentage.setValue(25)
    assert dialog.method_group.isEnabled()
    dialog.amount_mode.setCurrentIndex(1)
    assert dialog.count.isVisible() and not dialog.percentage.isVisible()
    paths = [tmp_path / "one" / "same.mp4", tmp_path / "two" / "same.avi"]
    dialog.add_videos(paths + paths)
    assert dialog.videos.rowCount() == 2
    first, second = dialog.videos.item(0, 1), dialog.videos.item(1, 1)
    assert first is not None and second is not None
    assert first.text() == "same"
    assert second.text() == "same_2"
    dialog.videos.selectRow(0)
    dialog.remove_button.click()
    assert dialog._videos == [paths[1]]


def test_invalid_destinations_and_names_are_rejected(
    qtbot: QtBot, tmp_path: Path
) -> None:
    dialog = FrameExtractorDialog()
    qtbot.addWidget(dialog)
    with pytest.raises(ValueError, match="at least one"):
        dialog._options()
    path = tmp_path / "video.mp4"
    path.touch()
    dialog.add_videos([path])
    with pytest.raises(ValueError, match="existing output"):
        dialog._options()
    dialog.output.setText(str(tmp_path))
    item = dialog.videos.item(0, 1)
    assert item is not None
    item.setText("../escape")
    with pytest.raises(ValueError, match="valid folder name"):
        dialog._options()
    item.setText("new name")
    assert dialog._options().videos[0].name == "new name"


def test_close_cancels_and_waits_for_worker_without_destroying_it(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    started = threading.Event()

    def fake_extract(
        options: ExtractionOptions, cancel: threading.Event, progress: object
    ) -> ExtractionResult:
        started.set()
        cancel.wait(5)
        return ExtractionResult(cancelled=cancel.is_set())

    monkeypatch.setattr(module, "extract_frames", fake_extract)
    dialog = FrameExtractorDialog()
    qtbot.addWidget(dialog)
    path = tmp_path / "video.mp4"
    path.touch()
    dialog.add_videos([path])
    dialog.output.setText(str(tmp_path))
    dialog.show()
    dialog.start.click()
    qtbot.waitUntil(started.is_set)
    assert not dialog.start.isEnabled()
    dialog.close()
    assert dialog.isVisible()
    qtbot.waitUntil(lambda: dialog._thread is None)
    assert "Cancelled" in dialog.status.toPlainText()
    assert dialog.start.isEnabled()
    dialog.close()
    assert not dialog.isVisible()
