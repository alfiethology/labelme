"""FLIR radiometry, independent of Qt and the annotation codec.

FFF layout/tag reference: https://exiftool.org/TagNames/FLIR.html
Radiometric model: https://github.com/gtatters/Thermimage (raw2temp).
Only files containing factory calibration and sensor data are accepted.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import shutil
import struct
import subprocess
import tempfile
import threading
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ._frame_extraction import ExtractionCancelled


class ThermalError(ValueError):
    pass


THERMAL_COLOUR_STOPS = (
    (0.0, (0, 0, 32)),
    (0.2, (75, 0, 130)),
    (0.4, (200, 0, 45)),
    (0.6, (255, 100, 0)),
    (0.8, (255, 220, 0)),
    (1.0, (255, 255, 255)),
)


@dataclass(frozen=True)
class ThermalFrame:
    celsius: NDArray[np.float64]
    raw: NDArray[np.uint16]
    metadata: dict

    @property
    def limits(self) -> tuple[float, float]:
        finite = self.celsius[np.isfinite(self.celsius)]
        if not finite.size:
            raise ThermalError("No valid temperatures in this frame.")
        return float(finite.min()), float(finite.max())


def colourise(values: NDArray, low: float, high: float) -> NDArray[np.uint8]:
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        raise ThermalError("The white temperature must be above the blue temperature.")
    scaled = np.nan_to_num(np.clip((values - low) / (high - low), 0, 1))
    positions, colours = zip(*THERMAL_COLOUR_STOPS, strict=True)
    rgb = np.stack(
        [
            np.interp(scaled, positions, channel)
            for channel in zip(*colours, strict=True)
        ],
        axis=-1,
    )
    rgb = np.rint(rgb).astype(np.uint8)
    rgb[~np.isfinite(values)] = 0
    return rgb


def temperatures(raw: NDArray, m: dict) -> NDArray[np.float64]:
    """Apply the recorded emissivity, reflected, atmospheric and window settings."""
    if not all(math.isfinite(v) for v in m.values() if isinstance(v, int | float)):
        raise ThermalError("Non-finite FLIR calibration values.")
    e, distance, window, humidity = (
        m["emissivity"],
        m["distance"],
        m["window_transmission"],
        m["humidity"],
    )
    if not (0 < e <= 1 and 0 < window <= 1 and 0 <= humidity <= 1 and distance >= 0):
        raise ThermalError("Invalid emissivity, distance, humidity or window settings.")
    if min(m["r1"], m["r2"], m["b"]) <= 0:
        raise ThermalError("Missing or invalid factory radiometric calibration.")
    if min(m["reflected_kelvin"], m["air_kelvin"], m["window_kelvin"]) <= 0:
        raise ThermalError("Invalid recorded environmental temperatures.")

    def signal(kelvin: float) -> float:
        return (
            m["r1"] / (m["r2"] * math.expm1(m["b"] / kelvin) + m["r2"] * (1 - m["f"]))
            - m["o"]
        )

    air_c = m["air_kelvin"] - 273.15
    try:
        water = humidity * math.exp(
            1.5587 + 0.06939 * air_c - 0.00027816 * air_c**2 + 0.00000068455 * air_c**3
        )
        path = math.sqrt(distance / 2)
        tau = m["atx"] * math.exp(-path * (m["alpha1"] + m["beta1"] * math.sqrt(water)))
        tau += (1 - m["atx"]) * math.exp(
            -path * (m["alpha2"] + m["beta2"] * math.sqrt(water))
        )
        if not 0 < tau <= 1:
            raise ThermalError(
                "Recorded atmospheric settings give invalid transmission."
            )
        reflected = (1 - e) / e * signal(m["reflected_kelvin"])
        atmosphere = (1 - tau) / (e * tau) * signal(m["air_kelvin"])
        atmosphere += (1 - tau) / (e * tau**2 * window) * signal(m["air_kelvin"])
        window_signal = (1 - window) / (e * tau * window) * signal(m["window_kelvin"])
        corrected = raw.astype(np.float64) / (e * tau**2 * window)
        corrected -= reflected + atmosphere + window_signal
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            argument = m["r1"] / (m["r2"] * (corrected + m["o"])) + m["f"]
            result = m["b"] / np.log(argument) - 273.15
        result[(argument <= 1) | (corrected + m["o"] <= 0)] = np.nan
        result[~np.isfinite(result)] = np.nan
        return result
    except (OverflowError, ZeroDivisionError) as error:
        raise ThermalError("Invalid recorded radiometric settings.") from error


def _order(data: bytes) -> str:
    if data[:2] == b"\x02\x00":
        return "<"
    if data[:2] == b"\x00\x02":
        return ">"
    raise ThermalError("Unsupported FLIR record byte order.")


def _calibration(data: bytes) -> dict:
    if len(data) < 0x310:
        raise ThermalError("Incomplete FLIR camera calibration record.")
    order = _order(data)
    fields = {
        "emissivity": 0x20,
        "distance": 0x24,
        "reflected_kelvin": 0x28,
        "air_kelvin": 0x2C,
        "window_kelvin": 0x30,
        "window_transmission": 0x34,
        "humidity": 0x3C,
        "r1": 0x58,
        "b": 0x5C,
        "f": 0x60,
        "alpha1": 0x70,
        "alpha2": 0x74,
        "beta1": 0x78,
        "beta2": 0x7C,
        "atx": 0x80,
        "r2": 0x30C,
    }
    metadata = {
        key: struct.unpack_from(order + "f", data, offset)[0]
        for key, offset in fields.items()
    }
    metadata["o"] = struct.unpack_from(order + "i", data, 0x308)[0]
    if metadata["humidity"] > 2:
        metadata["humidity"] /= 100
    metadata["camera"] = data[0xD4:0xF4].split(b"\0")[0].decode("utf-8", "replace")
    return metadata


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ExtractionCancelled


def _decode_sensor(data: bytes, cancel: threading.Event | None) -> NDArray[np.uint16]:
    if len(data) < 32:
        raise ThermalError("Truncated FLIR sensor record.")
    order = _order(data)
    width, height = struct.unpack_from(order + "HH", data, 2)
    if not (
        0 < width <= 16384 and 0 < height <= 16384 and width * height <= 32_000_000
    ):
        raise ThermalError("Invalid thermal sensor dimensions.")
    payload = data[32:]
    if payload.startswith(b"\x89PNG"):
        with Image.open(io.BytesIO(payload)) as image:
            if image.size != (width, height):
                raise ThermalError(
                    "Thermal PNG dimensions disagree with the sensor record."
                )
            # FLIR PNG samples store little-endian words in a big-endian PNG.
            raw = np.asarray(image).astype(np.uint16).byteswap()
    elif payload.startswith(b"\xff\xd8"):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ThermalError(
                "Compressed CSQ frames need FFmpeg on PATH. "
                "Install FFmpeg and restart Labelme."
            )
        with tempfile.TemporaryDirectory(prefix="labelme-thermal-") as directory:
            source = Path(directory) / "sensor.jls"
            target = Path(directory) / "sensor.raw"
            source.write_bytes(payload)
            command = [
                ffmpeg,
                "-v",
                "error",
                "-nostdin",
                "-xerror",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-pix_fmt",
                "gray16le",
                "-f",
                "rawvideo",
                str(target),
            ]
            with subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ) as process:
                try:
                    while True:
                        _check_cancel(cancel)
                        try:
                            _, stderr = process.communicate(timeout=0.2)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                except BaseException:
                    process.kill()
                    process.communicate()
                    raise
            if process.returncode:
                raise ThermalError(
                    "Could not decode the CSQ sensor image: "
                    + stderr.decode("utf-8", "replace")[-1000:]
                )
            raw = np.frombuffer(target.read_bytes(), dtype="<u2")
    else:
        raw = np.frombuffer(payload, dtype=order + "u2")
    if raw.size != width * height or raw.ndim > 2:
        raise ThermalError("Thermal sensor data has an unexpected size.")
    return raw.reshape(height, width).astype(np.uint16)


def _directory(
    header: bytes, directory: bytes, available: int
) -> tuple[list[tuple[int, int, int]], int]:
    if header[:4] != b"FFF\0" or len(header) < 64:
        raise ThermalError("Expected a FLIR FFF frame.")
    order = next(
        (
            o
            for o in ("<", ">")
            if 100 <= struct.unpack_from(o + "I", header, 20)[0] < 200
        ),
        None,
    )
    if order is None:
        raise ThermalError("Unsupported FLIR frame version.")
    offset, count = struct.unpack_from(order + "II", header, 24)
    if offset < 64 or not 1 <= count <= 4096 or len(directory) != count * 32:
        raise ThermalError("Invalid or truncated FLIR frame directory.")
    end = offset + len(directory)
    records = []
    for position in range(0, len(directory), 32):
        kind = struct.unpack_from(order + "H", directory, position)[0]
        start, length = struct.unpack_from(order + "II", directory, position + 12)
        if not kind or not length:
            continue
        if start < offset + len(directory) or start + length > available:
            raise ThermalError("Invalid or truncated FLIR frame record.")
        records.append((kind, start, length))
        end = max(end, start + length)
    if not {1, 32}.issubset({r[0] for r in records}):
        raise ThermalError(
            "This frame has no thermal sensor data or factory calibration."
        )
    return records, end


def _fff_frame(data: bytes, cancel: threading.Event | None = None) -> ThermalFrame:
    records, _ = _read_directory(io.BytesIO(data), 0, len(data))
    found = {
        kind: data[start : start + length]
        for kind, start, length in records
        if kind in {1, 32}
    }
    m = _calibration(found[32])
    raw = _decode_sensor(found[1], cancel)
    frame = ThermalFrame(temperatures(raw, m), raw, m)
    frame.limits  # Reject files with no interpretable temperatures.
    return frame


def _read_directory(
    stream: BinaryIO, start: int, size: int
) -> tuple[list[tuple[int, int, int]], int]:
    stream.seek(start)
    header = stream.read(64)
    if len(header) != 64 or header[:4] != b"FFF\0":
        raise ThermalError("Expected a FLIR FFF frame.")
    order = next(
        (
            o
            for o in ("<", ">")
            if 100 <= struct.unpack_from(o + "I", header, 20)[0] < 200
        ),
        None,
    )
    if order is None:
        raise ThermalError("Unsupported FLIR frame version.")
    offset, count = struct.unpack_from(order + "II", header, 24)
    if offset < 64 or not 1 <= count <= 4096 or offset + count * 32 > size - start:
        raise ThermalError("Invalid or truncated FLIR frame directory.")
    stream.seek(start + offset)
    return _directory(header, stream.read(count * 32), size - start)


def _jpeg_thermal(path: Path) -> bytes:
    chunks: dict[int, bytes] = {}
    total = None
    with path.open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            raise ThermalError("Expected a radiometric JPEG image.")
        while True:
            if stream.read(1) != b"\xff":
                raise ThermalError("Invalid JPEG segment.")
            marker = stream.read(1)
            while marker == b"\xff":
                marker = stream.read(1)
            if marker in (b"", b"\xda", b"\xd9"):
                break
            length_data = stream.read(2)
            if len(length_data) != 2:
                raise ThermalError("Truncated JPEG segment.")
            length = int.from_bytes(length_data, "big") - 2
            if length < 0:
                raise ThermalError("Invalid JPEG segment length.")
            segment = stream.read(length)
            if len(segment) != length:
                raise ThermalError("Truncated JPEG segment.")
            if marker == b"\xe1" and segment.startswith(b"FLIR\0") and length >= 8:
                index, last = segment[6:8]
                if total is not None and last + 1 != total:
                    raise ThermalError("Inconsistent FLIR JPEG chunk counts.")
                total = last + 1
                # Some cameras write zero counters for every segment.
                chunks[index] = chunks.get(index, b"") + segment[8:]
    if not chunks:
        raise ThermalError("This JPEG has no embedded FLIR temperature data.")
    if set(chunks) != set(range(total or 0)):
        raise ThermalError("Incomplete FLIR JPEG temperature data.")
    return b"".join(chunks[index] for index in sorted(chunks))


class ThermalSource:
    """Index frame offsets without loading the recording into memory."""

    def __init__(
        self,
        path: Path,
        cancel: threading.Event | None = None,
        progress: Callable[[int, str], None] | None = None,
    ) -> None:
        self.path = path.resolve()
        self.offsets: list[tuple[int, int]] = []
        self.warnings: list[str] = []
        self._jpeg: bytes | None = None
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            self._jpeg = _jpeg_thermal(self.path)
            self.offsets = [(0, len(self._jpeg))]
            return
        if path.suffix.lower() not in {".csq", ".fff"}:
            raise ThermalError("Choose a FLIR radiometric JPEG or CSQ recording.")
        size = self.path.stat().st_size
        with self.path.open("rb") as stream:
            position = 0
            while position < size:
                _check_cancel(cancel)
                stream.seek(position)
                chunk = stream.read(min(1024 * 1024, size - position))
                offset = chunk.find(b"FFF\0")
                if offset < 0:
                    if len(chunk) <= 3:
                        break
                    position += len(chunk) - 3
                    continue
                position += offset
                try:
                    _, length = _read_directory(stream, position, size)
                except ThermalError as error:
                    if not self.offsets:
                        raise
                    self.warnings.append(
                        f"Stopped indexing at byte {position:,}: {error} "
                        "Only preceding complete frames are available."
                    )
                    break
                self.offsets.append((position, length))
                position += length
                if progress and len(self.offsets) % 100 == 0:
                    progress(
                        position * 100 // size,
                        f"Indexed {len(self.offsets):,} thermal frames",
                    )
        if not self.offsets:
            raise ThermalError(
                "No supported radiometric frames found in this recording."
            )

    def __len__(self) -> int:
        return len(self.offsets)

    def read(self, index: int, cancel: threading.Event | None = None) -> ThermalFrame:
        _check_cancel(cancel)
        offset, length = self.offsets[index]
        if self._jpeg is not None:
            return _fff_frame(self._jpeg, cancel)
        with self.path.open("rb") as stream:
            stream.seek(offset)
            return _fff_frame(stream.read(length), cancel)


def sidecar_path(image: Path) -> Path:
    return image.with_suffix(".thermal.npz")


def save_frame(
    frame: ThermalFrame,
    image: Path,
    low: float,
    high: float,
    *,
    source: str,
    index: int,
    display: dict | None = None,
) -> None:
    """Write into a private extraction staging directory; never overwrite inputs."""
    if image.exists() or sidecar_path(image).exists():
        raise ThermalError("Thermal frame output already exists.")
    if display is None:
        rgb = colourise(frame.celsius, low, high)
    else:
        from ._thermal_analysis import Display
        from ._thermal_analysis import render

        rgb = render(frame, low, high, Display.read(display))
    Image.fromarray(rgb).save(image)
    metadata = dict(frame.metadata, source=source, frame_index=index)
    np.savez_compressed(
        sidecar_path(image),
        version=np.array(1),
        celsius=frame.celsius,
        raw=frame.raw,
        metadata=np.array(json.dumps(metadata)),
        display_range=np.array([low, high]),
        image_sha256=np.array(hashlib.sha256(image.read_bytes()).hexdigest()),
    )


def load_frame(image: Path) -> tuple[ThermalFrame, tuple[float, float]]:
    try:
        return _load_frame(image)
    except (zipfile.BadZipFile, EOFError, zlib.error) as error:
        raise ThermalError(
            "The thermal temperature file is incomplete or damaged."
        ) from error


def _load_frame(image: Path) -> tuple[ThermalFrame, tuple[float, float]]:
    with np.load(sidecar_path(image), allow_pickle=False) as data:
        if int(data["version"]) != 1:
            raise ThermalError("Unsupported thermal data version.")
        if str(data["image_sha256"]) != hashlib.sha256(image.read_bytes()).hexdigest():
            raise ThermalError(
                "The image has changed and no longer matches its temperature data."
            )
        values, raw = data["celsius"], data["raw"]
        if values.ndim != 2 or values.shape != raw.shape:
            raise ThermalError("Invalid thermal frame dimensions.")
        with Image.open(image) as preview:
            if preview.size != (values.shape[1], values.shape[0]):
                raise ThermalError("The image and temperature dimensions disagree.")
        low, high = map(float, data["display_range"])
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            raise ThermalError("Invalid thermal display range.")
        frame = ThermalFrame(
            values.astype(np.float64),
            raw.astype(np.uint16),
            json.loads(str(data["metadata"])),
        )
    frame.limits
    return frame, (low, high)
