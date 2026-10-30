"""Measurements and presentation of calibrated thermal pixels, without Qt."""

from __future__ import annotations

import base64
import csv
import html
import io
import json
import math
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from PIL import ImageDraw

from ._thermal import ThermalError
from ._thermal import ThermalFrame
from ._thermal import colourise
from ._thermal import temperatures

PALETTES = {
    "iron": "Iron",
    "white_hot": "White hot",
    "black_hot": "Black hot",
    "rainbow": "Rainbow",
}
UNITS = {"C": "°C", "F": "°F", "K": "K"}
PARAMETERS = (
    "emissivity",
    "distance",
    "reflected_kelvin",
    "air_kelvin",
    "humidity",
    "window_transmission",
    "window_kelvin",
)


def convert(
    value: float | NDArray, unit: str, *, delta: bool = False
) -> float | NDArray:
    if unit == "F":
        return value * 1.8 + (0 if delta else 32)
    if unit == "K":
        return value + (0 if delta else 273.15)
    if unit != "C":
        raise ThermalError("Unknown temperature unit.")
    return value


def celsius(value: float, unit: str) -> float:
    if unit == "F":
        return (value - 32) / 1.8
    if unit == "K":
        return value - 273.15
    if unit != "C":
        raise ThermalError("Unknown temperature unit.")
    return value


@dataclass(frozen=True)
class Display:
    palette: str = "iron"
    distribution: str = "linear"
    isotherm: str = "off"
    lower: float = 30
    upper: float = 40
    markers: bool = False

    @classmethod
    def read(cls, data: dict) -> Display:
        if not isinstance(data, dict):
            raise ThermalError("Invalid thermal display settings.")
        result = cls(
            **{key: value for key, value in data.items() if key in asdict(cls())}
        )
        if (
            result.palette not in PALETTES
            or result.distribution not in {"linear", "histogram"}
            or result.isotherm not in {"off", "above", "below", "between"}
            or not isinstance(result.markers, bool)
            or not all(
                isinstance(v, int | float) and math.isfinite(v)
                for v in (result.lower, result.upper)
            )
            or result.lower > result.upper
        ):
            raise ThermalError("Invalid thermal display settings.")
        return result


def recalculate(frame: ThermalFrame, overrides: dict) -> ThermalFrame:
    if not isinstance(overrides, dict) or not set(overrides).issubset(PARAMETERS):
        raise ThermalError("Unknown thermal measurement parameter.")
    if not all(
        isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)
        for v in overrides.values()
    ):
        raise ThermalError("Invalid thermal measurement parameter.")
    metadata = dict(frame.metadata)
    recorded = metadata.get("recorded_parameters", {k: metadata[k] for k in PARAMETERS})
    metadata.update(recorded)
    metadata.update(overrides)
    metadata["recorded_parameters"] = recorded
    result = ThermalFrame(temperatures(frame.raw, metadata), frame.raw, metadata)
    result.limits
    return result


def isotherm_mask(values: NDArray, display: Display) -> NDArray[np.bool_]:
    valid = np.isfinite(values)
    if display.isotherm == "above":
        return valid & (values >= display.lower)
    if display.isotherm == "below":
        return valid & (values <= display.lower)
    if display.isotherm == "between":
        return valid & (values >= display.lower) & (values <= display.upper)
    return np.zeros(values.shape, dtype=bool)


def render(
    frame: ThermalFrame, low: float, high: float, display: Display
) -> NDArray[np.uint8]:
    values = frame.celsius
    if not (math.isfinite(low) and math.isfinite(high) and high > low):
        raise ThermalError("The upper display limit must exceed the lower limit.")
    scaled = np.nan_to_num(np.clip((values - low) / (high - low), 0, 1))
    valid = np.isfinite(values)
    if display.distribution == "histogram" and valid.any():
        # Equalize only in-range values so clipping still follows the limits.
        interior = valid & (values > low) & (values < high)
        if interior.any():
            samples, counts = np.unique(values[interior], return_counts=True)
            if len(samples) > 1:
                cumulative = counts.cumsum()
                positions = (cumulative - cumulative[0]) / (
                    cumulative[-1] - cumulative[0]
                )
                scaled[interior] = np.interp(values[interior], samples, positions)
    if display.palette == "iron":
        rgb = colourise(scaled, 0, 1)
    elif display.palette in {"white_hot", "black_hot"}:
        channel = np.rint(
            (1 - scaled if display.palette == "black_hot" else scaled) * 255
        ).astype(np.uint8)
        rgb = np.repeat(channel[..., None], 3, axis=-1)
    else:
        stops = np.array(
            [[0, 0, 128], [0, 128, 255], [0, 255, 128], [255, 255, 0], [255, 0, 0]],
            dtype=float,
        )
        rgb = (
            np.stack(
                [
                    np.interp(scaled, np.linspace(0, 1, len(stops)), channel)
                    for channel in stops.T
                ],
                axis=-1,
            )
            .round()
            .astype(np.uint8)
        )
    rgb[~valid] = 0
    rgb[isotherm_mask(values, display)] = [0, 255, 0]
    if display.markers and valid.any():
        image = Image.fromarray(rgb)
        painter = ImageDraw.Draw(image)
        finite_values = np.where(valid, values, np.nan)
        for index, colour in (
            (np.nanargmin(finite_values), "cyan"),
            (np.nanargmax(finite_values), "red"),
        ):
            y, x = np.unravel_index(index, values.shape)
            painter.line((x - 5, y, x + 5, y), fill="black", width=3)
            painter.line((x, y - 5, x, y + 5), fill="black", width=3)
            painter.line((x - 4, y, x + 4, y), fill=colour)
            painter.line((x, y - 4, x, y + 4), fill=colour)
        rgb = np.array(image)
    return rgb


@dataclass(frozen=True)
class Measurement:
    name: str
    kind: str
    points: tuple[tuple[float, float], ...]

    @classmethod
    def read(cls, data: dict) -> Measurement:
        if not isinstance(data, dict) or not isinstance(data.get("name"), str):
            raise ThermalError("Invalid thermal measurement.")
        kind = data.get("kind")
        points = np.asarray(data.get("points"), dtype=float)
        counts = {
            "point": 1,
            "rectangle": 2,
            "circle": 2,
            "line": 2,
            "polygon": 3,
            "oriented_rectangle": 4,
        }
        if (
            kind not in counts
            or points.ndim != 2
            or points.shape[1] != 2
            or len(points) < counts[kind]
            or len(points) > 10000
            or not np.isfinite(points).all()
        ):
            raise ThermalError("Invalid thermal measurement geometry.")
        return cls(data["name"], kind, tuple(map(tuple, points.tolist())))


def sample(frame: ThermalFrame, measurement: Measurement) -> tuple[NDArray, NDArray]:
    """Return pixel coordinates (x,y) and temperatures; use pixel centres for areas."""
    height, width = frame.celsius.shape
    points = np.asarray(measurement.points, dtype=float)
    if measurement.kind == "point":
        xy = np.floor(np.clip(points[:1], -1, (width, height))).astype(int)
    elif measurement.kind == "line":
        start, end = points[:2]
        direction = end - start
        enter, leave = 0.0, 1.0
        # Clip the segment before sampling, including out-of-image annotations.
        for axis, limit in enumerate((width, height)):
            if direction[axis] == 0:
                if not 0 <= start[axis] < limit:
                    return np.empty((0, 2), dtype=int), np.empty(0)
            else:
                a, b = sorted(
                    (
                        -start[axis] / direction[axis],
                        (limit - 1e-9 - start[axis]) / direction[axis],
                    )
                )
                enter, leave = max(enter, a), min(leave, b)
        if enter > leave:
            return np.empty((0, 2), dtype=int), np.empty(0)
        first, last = start + enter * direction, start + leave * direction
        count = math.ceil(np.max(np.abs(last - first))) + 1
        xy = np.floor(np.linspace(first, last, count)).astype(int)
        # Retain spatial order; a profile must not sort coordinates lexically.
        xy = xy[np.r_[True, np.any(np.diff(xy, axis=0), axis=1)]]
    else:
        if measurement.kind == "circle":
            centre = points[0]
            radius = float(np.linalg.norm(points[1] - centre))
            lower, upper = centre - radius, centre + radius
        else:
            lower, upper = points.min(axis=0), points.max(axis=0)
        x0, y0 = np.floor(np.clip(lower, 0, (width, height))).astype(int)
        x1, y1 = np.ceil(np.clip(upper, 0, (width, height))).astype(int)
        if x0 >= x1 or y0 >= y1:
            return np.empty((0, 2), dtype=int), np.empty(0)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        cx, cy = xx + 0.5, yy + 0.5
        if measurement.kind == "rectangle":
            inside = (
                (cx >= lower[0]) & (cx < upper[0]) & (cy >= lower[1]) & (cy < upper[1])
            )
        elif measurement.kind == "circle":
            inside = (cx - centre[0]) ** 2 + (cy - centre[1]) ** 2 <= radius**2
        else:
            # Even-odd polygon rule; no Qt or full-image raster allocation.
            inside = np.zeros(xx.shape, dtype=bool)
            for first, last in zip(points, np.roll(points, -1, axis=0), strict=True):
                if first[1] == last[1]:
                    continue
                crossing = (first[1] > cy) != (last[1] > cy)
                boundary = (last[0] - first[0]) * (cy - first[1]) / (
                    last[1] - first[1]
                ) + first[0]
                inside ^= crossing & (cx < boundary)
        xy = np.column_stack((xx[inside], yy[inside]))
    within = (
        (xy[:, 0] >= 0) & (xy[:, 0] < width) & (xy[:, 1] >= 0) & (xy[:, 1] < height)
    )
    xy = xy[within]
    return xy, frame.celsius[xy[:, 1], xy[:, 0]]


def summary(frame: ThermalFrame, measurement: Measurement | None = None) -> dict:
    values = frame.celsius if measurement is None else sample(frame, measurement)[1]
    finite = values[np.isfinite(values)]
    return {
        "pixels": int(values.size),
        "valid": int(finite.size),
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
    }


def export_csv(path: Path, frame: ThermalFrame, unit: str) -> None:
    # Matrix layout: columns are x coordinates, rows are y coordinates.
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["y / x (" + UNITS[unit] + ")", *range(frame.celsius.shape[1])])
        for y, row in enumerate(convert(frame.celsius, unit)):
            writer.writerow([y, *[f"{v:.6f}" if math.isfinite(v) else "" for v in row]])


def export_report(
    path: Path,
    frame: ThermalFrame,
    low: float,
    high: float,
    display: Display,
    unit: str,
    measurements: list[Measurement],
    *,
    reference: int = -1,
) -> None:
    image = Image.fromarray(render(frame, low, high, display))
    painter = ImageDraw.Draw(image)
    for number, item in enumerate(measurements, 1):
        points = item.points
        if item.kind == "rectangle":
            x = sorted(p[0] for p in points[:2])
            y = sorted(p[1] for p in points[:2])
            painter.rectangle((x[0], y[0], x[1], y[1]), outline="cyan", width=2)
        elif item.kind == "circle":
            x, y = points[0]
            radius = math.dist(points[0], points[1])
            painter.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                outline="cyan",
                width=2,
            )
        elif item.kind == "point":
            x, y = points[0]
            painter.ellipse((x - 2, y - 2, x + 2, y + 2), fill="cyan")
        else:
            painter.line(
                [*points, *([points[0]] if item.kind != "line" else [])],
                fill="cyan",
                width=2,
            )
        painter.text(
            points[0], str(number), fill="white", stroke_width=1, stroke_fill="black"
        )
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    picture = base64.b64encode(stream.getvalue()).decode("ascii")
    rows = []
    reference_mean = (
        summary(frame, measurements[reference])["mean"]
        if 0 <= reference < len(measurements)
        else None
    )
    for name, stats in [
        ("Full frame", summary(frame)),
        *[(f"{i}. {m.name}", summary(frame, m)) for i, m in enumerate(measurements, 1)],
    ]:
        cells = [html.escape(name), str(stats["valid"])]
        cells += [
            "—" if stats[k] is None else f"{convert(stats[k], unit):.2f}"
            for k in ("min", "max", "mean")
        ]
        cells.append(
            "—"
            if reference_mean is None or stats["mean"] is None
            else f"{convert(stats['mean'] - reference_mean, unit, delta=True):+.2f}"
        )
        rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    metadata = html.escape(json.dumps(frame.metadata, indent=2, ensure_ascii=False))
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Thermal analysis</title>"
        "<style>body{font:16px sans-serif;max-width:1000px;margin:2em auto}"
        "img{max-width:100%}td,th{padding:.5em;border:1px solid #aaa}"
        "table{border-collapse:collapse}pre{white-space:pre-wrap}</style></head><body>"
        f"<h1>Thermal analysis</h1><p>Temperatures in {UNITS[unit]}. "
        f"Palette: {PALETTES[display.palette]}; scale: {convert(low, unit):.2f} "
        f"to {convert(high, unit):.2f} {UNITS[unit]}; "
        f"distribution: {display.distribution}.</p>"
        "<img alt='Thermal image and numbered measurements' "
        f"src='data:image/png;base64,{picture}'>"
        "<table><tr><th>Measurement</th><th>Valid pixels</th><th>Minimum</th>"
        "<th>Maximum</th><th>Mean</th><th>Δ mean</th></tr>" + "".join(rows) + "</table>"
        "<p>Measurements use recorded camera calibration "
        "and the environmental settings below. "
        "Display clipping and isotherm highlights do not change temperatures.</p>"
        f"<h2>Source and measurement parameters</h2><pre>{metadata}</pre>"
        "</body></html>",
        encoding="utf-8",
    )
