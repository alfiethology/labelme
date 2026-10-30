from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from labelme._thermal import ThermalError
from labelme._thermal import ThermalFrame
from labelme._thermal import ThermalSource
from labelme._thermal_analysis import Display
from labelme._thermal_analysis import Measurement
from labelme._thermal_analysis import celsius
from labelme._thermal_analysis import convert
from labelme._thermal_analysis import export_csv
from labelme._thermal_analysis import export_report
from labelme._thermal_analysis import isotherm_mask
from labelme._thermal_analysis import recalculate
from labelme._thermal_analysis import render
from labelme._thermal_analysis import sample
from labelme._thermal_analysis import summary
from tests.thermal_helpers import fff


def grid() -> ThermalFrame:
    values = np.arange(16, dtype=float).reshape(4, 4)
    values[0, 3] = np.nan
    return ThermalFrame(values, np.zeros((4, 4), dtype=np.uint16), {})


@pytest.mark.parametrize(
    "kind,points,expected",
    [
        ("point", [[1.9, 2.9]], [9]),
        ("point", [[-0.1, 0]], []),
        ("rectangle", [[2, 2], [0, 0]], [0, 1, 4, 5]),
        ("rectangle", [[-100, -100], [1, 1]], [0]),
        ("rectangle", [[100, 100], [101, 101]], []),
        ("circle", [[2, 2], [3, 2]], [5, 6, 9, 10]),
        ("polygon", [[0, 0], [4, 0], [0, 4]], [0, 1, 2, 4, 5, 8]),
        ("line", [[3.1, 3.1], [0.1, 0.1]], [15, 10, 5, 0]),
        ("line", [[-100, 1.5], [100, 1.5]], [4, 5, 6, 7]),
        ("line", [[-100, -1], [100, -1]], []),
    ],
)
def test_measurement_geometry_and_clipping(
    kind: str, points: list, expected: list
) -> None:
    measurement = Measurement.read({"name": "test", "kind": kind, "points": points})
    _, values = sample(grid(), measurement)
    assert values.tolist() == expected


def test_stats_exclude_invalid_pixels_and_count_region_pixels() -> None:
    stats = summary(grid(), Measurement("top row", "rectangle", ((0, 0), (4, 1))))
    assert stats == {"pixels": 4, "valid": 3, "min": 0, "max": 2, "mean": 1}


@pytest.mark.parametrize("unit,value", [("C", 20), ("F", 68), ("K", 293.15)])
def test_units_round_trip_and_deltas(unit: str, value: float) -> None:
    assert convert(20, unit) == pytest.approx(value)
    assert celsius(value, unit) == pytest.approx(20)
    assert convert(10, unit, delta=True) == pytest.approx(18 if unit == "F" else 10)


def test_palettes_isotherms_histogram_leave_temperatures_unchanged() -> None:
    frame = grid()
    original = frame.celsius.copy()
    assert render(frame, 0, 15, Display(palette="white_hot"))[3, 3].tolist() == [
        255,
        255,
        255,
    ]
    assert render(frame, 0, 15, Display(palette="black_hot"))[3, 3].tolist() == [
        0,
        0,
        0,
    ]
    for palette in ("iron", "white_hot", "black_hot", "rainbow"):
        for distribution in ("linear", "histogram"):
            display = Display(
                palette=palette,
                distribution=distribution,
                isotherm="between",
                lower=5,
                upper=7,
            )
            rgb = render(frame, 2, 10, display)
            assert rgb[1, 1].tolist() == [0, 255, 0]
            assert rgb[0, 3].tolist() == [0, 0, 0]
            assert int(isotherm_mask(frame.celsius, display).sum()) == 3
    np.testing.assert_array_equal(frame.celsius, original)
    for invalid in (
        {"palette": "missing"},
        {"lower": 50, "upper": 10},
        {"upper": float("nan")},
    ):
        with pytest.raises(ThermalError):
            Display.read(invalid)


def test_recalculation_is_reversible_from_original_sensor_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "camera.fff"
    path.write_bytes(fff())
    original = ThermalSource(path).read(0)
    adjusted = recalculate(original, {"emissivity": 0.5})
    assert not np.allclose(adjusted.celsius, original.celsius)
    np.testing.assert_array_equal(adjusted.raw, original.raw)
    reset = recalculate(adjusted, {})
    np.testing.assert_allclose(reset.celsius, original.celsius)
    assert reset.metadata["emissivity"] == original.metadata["emissivity"]
    with pytest.raises(ThermalError):
        recalculate(original, {"emissivity": 0})


def test_csv_matrix_and_self_contained_escaped_report(tmp_path: Path) -> None:
    frame = grid()
    frame.metadata["source"] = "<script>alert('source')</script>"
    csv_path = tmp_path / "matrix.csv"
    export_csv(csv_path, frame, "F")
    with csv_path.open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["y / x (°F)", "0", "1", "2", "3"]
    assert rows[1] == ["0", "32.000000", "33.800000", "35.600000", ""]
    report = tmp_path / "report.html"
    measurement = Measurement("<hot area>", "rectangle", ((0, 0), (2, 2)))
    export_report(report, frame, 0, 15, Display(), "C", [measurement])
    content = report.read_text()
    assert "data:image/png;base64," in content
    assert "&lt;script&gt;" in content and "<script>" not in content
    assert "&lt;hot area&gt;" in content
    assert Measurement.read(asdict(measurement)) == measurement
