from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from PIL import Image

from labelme._frame_extraction import ExtractionCancelled
from labelme._frame_extraction import ExtractionOptions
from labelme._frame_extraction import VideoSource
from labelme._frame_extraction import _run
from labelme._frame_extraction import extract_frames
from labelme._frame_extraction import frame_indices
from labelme._frame_extraction import safe_name


@pytest.mark.parametrize(
    "total,amount,percentage,expected",
    [
        (11, 100, True, list(range(11))),
        (11, 25, True, [0, 5, 10]),
        (11, 4, False, [0, 3, 6, 10]),
        (11, 1, False, [5]),
        (11, 999, False, list(range(11))),
        (11, 0.01, True, [5]),
        (1, 1, False, [0]),
    ],
)
def test_sampling(
    total: int, amount: float, percentage: bool, expected: list[int]
) -> None:
    assert (
        list(
            frame_indices(total, amount, percentage=percentage, random_selection=False)
        )
        == expected
    )


def test_random_sampling_is_unique_and_chronological() -> None:
    indices = frame_indices(1000, 37, percentage=False, random_selection=True)
    assert len(indices) == len(set(indices)) == 37
    assert list(indices) == sorted(indices)
    assert all(0 <= index < 1000 for index in indices)


@pytest.mark.parametrize(
    "amount,percentage",
    [(0, True), (-1, False), (101, True), (1.2, False), (float("nan"), True)],
)
def test_invalid_amount(amount: float, percentage: bool) -> None:
    with pytest.raises(ValueError):
        frame_indices(11, amount, percentage=percentage, random_selection=False)


@pytest.mark.parametrize(
    "name", ["../video", "", "CON", "bad:name", "a/../b", "name.", "a" * 99 + " .more"]
)
def test_portable_output_names(name: str) -> None:
    clean = safe_name(name)
    assert clean == safe_name(clean)
    assert clean not in {"", ".", ".."}
    assert "/" not in clean and "\\" not in clean


@pytest.fixture(params=[".mp4", ".avi"])
def video(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe are required for video integration tests")
    path = tmp_path / f"test video{request.param}"
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
            "11",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "mpeg4",
            "-threads",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@pytest.mark.parametrize("separate", [True, False])
def test_ffmpeg_extracts_correct_source_frames_without_touching_existing_files(
    video: Path,
    tmp_path: Path,
    separate: bool,
) -> None:
    # Include percent signs in the output parent (FFmpeg image pattern escaping).
    parent = tmp_path / "100% images"
    parent.mkdir()
    existing = parent / "annotation.json"
    existing.write_text('{"untouched": true}')
    sources = (VideoSource(video, "custom name"),)
    full = extract_frames(
        ExtractionOptions(sources, parent, separate), threading.Event(), lambda *_: None
    )
    assert not full.errors
    assert full.saved == 11
    assert full.output == parent / "extracted_frames"
    for random in (False, True):
        subset = extract_frames(
            ExtractionOptions(
                sources, parent, separate, amount=4, percentage=False, random=random
            ),
            threading.Event(),
            lambda *_: None,
        )
        assert not subset.errors
        assert subset.saved == 4
        assert subset.output is not None
        images = sorted(subset.output.rglob("*.png"))
        indices = [int(image.stem.rsplit("_", 1)[1]) for image in images]
        assert len(set(indices)) == 4
        if not random:
            assert indices == [0, 3, 6, 10]
        assert full.output is not None
        for image in images:
            reference = next(full.output.rglob(image.name))
            with Image.open(image) as selected, Image.open(reference) as original:
                assert selected.tobytes() == original.tobytes()
    assert existing.read_text() == '{"untouched": true}'
    assert not list(parent.rglob(".extract-*"))


def test_cancel_keeps_completed_videos_and_cleans_unfinished_staging(
    video: Path, tmp_path: Path
) -> None:
    cancel = threading.Event()
    extractions = 0

    def progress(_percent: int, message: str) -> None:
        nonlocal extractions
        if message.startswith("Extracting"):
            extractions += 1
            if extractions == 2:
                cancel.set()

    result = extract_frames(
        ExtractionOptions(
            (VideoSource(video, "first"), VideoSource(video, "second")), tmp_path
        ),
        cancel,
        progress,
    )
    assert result.cancelled and result.completed == 1 and result.saved == 11
    assert result.output is not None
    assert sorted(path.name for path in result.output.iterdir()) == ["first"]


def test_bad_video_does_not_abort_remaining_batch(video: Path, tmp_path: Path) -> None:
    bad = tmp_path / "broken.mp4"
    bad.write_text("not a video")
    result = extract_frames(
        ExtractionOptions(
            (VideoSource(bad, "bad"), VideoSource(video, "good")), tmp_path
        ),
        threading.Event(),
        lambda *_: None,
    )
    assert len(result.errors) == 1 and result.errors[0].startswith("broken.mp4:")
    assert result.completed == 1 and result.saved == 11


def test_cancelling_terminates_subprocess_promptly() -> None:
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    timer.start()
    try:
        with pytest.raises(ExtractionCancelled):
            _run([sys.executable, "-c", "import time; time.sleep(30)"], cancel)
    finally:
        timer.cancel()
        timer.join()


def test_missing_ffmpeg_has_actionable_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Install FFmpeg"):
        extract_frames(
            ExtractionOptions((), tmp_path), threading.Event(), lambda *_: None
        )
    assert not list(tmp_path.iterdir())
