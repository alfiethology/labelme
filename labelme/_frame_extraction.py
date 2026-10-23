"""Independent, cancellable FFmpeg frame extraction (no annotation/session state)."""

from __future__ import annotations

import json
import math
import random
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path


class ExtractionCancelled(Exception):
    pass


@dataclass(frozen=True)
class VideoSource:
    path: Path
    name: str


@dataclass(frozen=True)
class ExtractionOptions:
    videos: tuple[VideoSource, ...]
    output_parent: Path
    separate_folders: bool = True
    amount: float = 100
    percentage: bool = True
    random: bool = False


def safe_name(value: str) -> str:
    """A portable single path component, also used as an image prefix."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(". ")
    if not value or value in {".", ".."}:
        return "video"
    if value.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        value = f"_{value}"
    return value[:100].rstrip(". ")


def frame_indices(
    total: int, amount: float, *, percentage: bool, random_selection: bool
) -> range | list[int]:
    if total < 1 or not math.isfinite(amount) or amount <= 0:
        raise ValueError("Frame count and requested amount must be positive.")
    if percentage and amount > 100:
        raise ValueError("Percentage must be at most 100.")
    if not percentage and not float(amount).is_integer():
        raise ValueError("The frame count must be a whole number.")
    count = min(
        total, max(1, math.ceil(total * amount / 100) if percentage else int(amount))
    )
    if count == total:
        return range(total)
    if random_selection:
        return sorted(random.sample(range(total), count))
    if count == 1:
        return [total // 2]
    return [i * (total - 1) // (count - 1) for i in range(count)]


def _selection_expression(indices: list[int]) -> str:
    # A balanced decision tree avoids testing every selected index for every frame.
    def branch(start: int, stop: int) -> str:
        if stop - start == 1:
            return f"eq(n,{indices[start]})"
        middle = (start + stop) // 2
        return (
            f"if(lte(n,{indices[middle - 1]}),"
            f"{branch(start, middle)},{branch(middle, stop)})"
        )

    return branch(0, len(indices)).replace(",", r"\,")


def _run(command: list[str], cancel: threading.Event) -> str:
    if cancel.is_set():
        raise ExtractionCancelled
    # communicate drains both pipes, including on noisy/erroring files. Never use a
    # shell: video paths and editable output names are data, not commands.
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as process:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel.is_set():
                    process.kill()
                    process.communicate()
                    raise ExtractionCancelled from None
        if cancel.is_set():
            raise ExtractionCancelled
        if process.returncode:
            raise RuntimeError(
                stderr.strip()[-4000:] or "FFmpeg could not read this video."
            )
    return stdout


def _create_batch(parent: Path) -> Path:
    if not parent.is_dir():
        raise ValueError("Choose an existing output folder.")
    for number in range(1, 1_000_000):
        path = parent / (
            "extracted_frames" if number == 1 else f"extracted_frames_{number}"
        )
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path
    raise RuntimeError("Could not create a new extraction folder.")


@dataclass
class ExtractionResult:
    output: Path | None = None
    saved: int = 0
    completed: int = 0
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)


def extract_frames(
    options: ExtractionOptions,
    cancel: threading.Event,
    progress: Callable[[int, str], None],
) -> ExtractionResult:
    """Keep completed videos on cancellation; discard the unfinished video's files."""
    result = ExtractionResult()
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError(
            "Frame extraction needs FFmpeg and ffprobe on PATH. "
            "Install FFmpeg, then restart Labelme. See https://ffmpeg.org/download.html"
        )
    names = [video.name.casefold() for video in options.videos]
    if not names or len(set(names)) != len(names):
        raise ValueError("Give every video a unique output name.")
    if any(safe_name(video.name) != video.name for video in options.videos):
        raise ValueError("Output names must be valid single folder names.")
    if cancel.is_set():
        result.cancelled = True
        return result
    result.output = _create_batch(options.output_parent)
    for position, video in enumerate(options.videos):
        base_progress = position * 100 // len(options.videos)
        try:
            indices: range | list[int] | None = None
            if options.percentage and options.amount == 100:
                # All frames need only one decode pass, with no metadata scan.
                progress(base_progress, f"Extracting all frames: {video.path.name}")
            else:
                progress(base_progress, f"Counting frames: {video.path.name}")
                # Decode to count rather than estimating from FPS/duration or
                # trusting container metadata (which can be absent or wrong).
                metadata = json.loads(
                    _run(
                        [
                            ffprobe,
                            "-v",
                            "error",
                            "-select_streams",
                            "v:0",
                            "-count_frames",
                            "-show_entries",
                            "stream=nb_read_frames",
                            "-of",
                            "json",
                            str(video.path),
                        ],
                        cancel,
                    )
                )
                total = int(metadata["streams"][0]["nb_read_frames"])
                indices = frame_indices(
                    total,
                    float(options.amount),
                    percentage=options.percentage,
                    random_selection=options.random,
                )
                progress(
                    base_progress,
                    f"Extracting {len(indices):,} / {total:,} frames: "
                    f"{video.path.name}",
                )
            # Stage inside the new batch: publication stays on the same filesystem.
            with tempfile.TemporaryDirectory(
                prefix=".extract-", dir=result.output
            ) as stage:
                stage_path = Path(stage)
                command = [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-xerror",
                    "-n",
                    "-i",
                    str(video.path),
                ]
                if isinstance(indices, list):
                    script = stage_path / "selection.txt"
                    script.write_text(
                        f"[0:v:0]select={_selection_expression(indices)}[frames]",
                        encoding="utf-8",
                    )
                    command += [
                        "-filter_complex_script",
                        str(script),
                        "-map",
                        "[frames]",
                    ]
                else:
                    command += ["-map", "0:v:0"]
                command += [
                    "-an",
                    "-sn",
                    "-fps_mode",
                    "passthrough",
                    "-compression_level",
                    "1",
                    "-start_number",
                    "0",
                    "-threads",
                    "1",
                    str(stage_path).replace("%", "%%") + "/%09d.png",
                ]
                _run(command, cancel)
                images = sorted(stage_path.glob("*.png"))
                if indices is None:
                    indices = range(len(images))
                if not images:
                    raise RuntimeError("No video frames could be decoded.")
                if len(images) != len(indices):
                    raise RuntimeError(
                        f"Expected {len(indices)} frames, but decoded {len(images)}."
                    )
                # Rename within staging first. A separate folder is published in
                # one operation. In shared mode, roll back this video's files on
                # any publication error, leaving completed videos intact.
                ready = stage_path / "ready"
                ready.mkdir()
                for image, index in zip(images, indices, strict=True):
                    if cancel.is_set():
                        raise ExtractionCancelled
                    image.rename(ready / f"{video.name}_frame_{index:09d}.png")
                if options.separate_folders:
                    ready.rename(result.output / video.name)
                else:
                    published: list[Path] = []
                    try:
                        for image in ready.iterdir():
                            if cancel.is_set():
                                raise ExtractionCancelled
                            target = result.output / image.name
                            image.rename(target)
                            published.append(target)
                    except (OSError, ExtractionCancelled):
                        for target in published:
                            target.unlink(missing_ok=True)
                        raise
                result.saved += len(images)
                result.completed += 1
        except ExtractionCancelled:
            result.cancelled = True
            break
        except (OSError, ValueError, KeyError, IndexError, RuntimeError) as error:
            result.errors.append(f"{video.path.name}: {error}")
        progress(
            (position + 1) * 100 // len(options.videos),
            f"Saved {result.saved:,} frames",
        )
    return result
