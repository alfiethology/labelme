from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._widgets.frame_extractor_dialog import FrameExtractorDialog

from .conftest import MainWinFactory


def test_tools_extraction_preserves_open_session_in_output_parent(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    image = tmp_path / "existing.png"
    Image.new("RGB", (32, 24)).save(image)
    video = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=32x24:rate=10",
            "-frames:v",
            "5",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    window = main_win(file_or_dir=tmp_path, config_overrides={"auto_save": False})
    canvas = window._canvas_widgets.canvas
    shape = Shape(
        label="unsaved", shape_type="point", points=np.array([[10, 10]], dtype=float)
    )
    canvas.shapes.append(shape)
    window.mark_dirty()
    original_path = window._image_path
    original_images = list(window.image_list)
    original_config = window._output_dir
    original_pixmap = canvas.pixmap.cacheKey()
    files = window._docks.file_list
    original_row = files.currentRow()
    opened = []

    def run_dialog(dialog: FrameExtractorDialog) -> int:
        opened.append(dialog)
        dialog.add_videos([video])
        dialog.output.setText(str(tmp_path))
        dialog.percentage.setValue(40)
        dialog.show()
        dialog.start.click()
        qtbot.waitUntil(lambda: dialog._thread is None, timeout=10000)
        assert "saved 2 frames" in dialog.status.toPlainText()
        dialog.reject()
        return 0

    monkeypatch.setattr(FrameExtractorDialog, "exec", run_dialog)
    action = next(
        action
        for action in window._menus.tools.actions()
        if action.text() == "Extract Video Frames…"
    )
    assert action.isEnabled()
    action.trigger()
    assert len(opened) == 1
    assert len(list((tmp_path / "extracted_frames").rglob("*.png"))) == 2
    assert window._image_path == original_path
    assert window.image_list == original_images
    assert files.currentRow() == original_row
    assert window._output_dir == original_config
    assert canvas.pixmap.cacheKey() == original_pixmap
    assert canvas.shapes == [shape]
    assert window._is_changed
    assert not image.with_suffix(".json").exists()
    # Avoid an unsaved-changes prompt during fixture teardown.
    window._is_changed = False
