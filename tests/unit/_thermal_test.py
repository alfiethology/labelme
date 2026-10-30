from __future__ import annotations

import math
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from labelme._frame_extraction import ExtractionOptions
from labelme._frame_extraction import VideoSource
from labelme._frame_extraction import extract_frames
from labelme._thermal import ThermalError
from labelme._thermal import ThermalSource
from labelme._thermal import colourise
from labelme._thermal import load_frame
from labelme._thermal import save_frame
from labelme._thermal import sidecar_path
from labelme._thermal import temperatures
from tests.thermal_helpers import fff
from tests.thermal_helpers import radiometric_jpeg


@pytest.mark.parametrize("order", ["<", ">"])
@pytest.mark.parametrize("png", [True, False])
def test_radiometric_sensor_words_and_calibration(
    tmp_path: Path, order: str, png: bool
) -> None:
    path = tmp_path / "camera.jpg"
    raw = np.array([[18109, 19500], [18500, 19000]], dtype=np.uint16)
    path.write_bytes(radiometric_jpeg(fff(raw, order=order, png=png)))
    frame = ThermalSource(path).read(0)
    np.testing.assert_array_equal(frame.raw, raw)
    # Independent blackbody inversion with known factory calibration.
    expected = (
        1501 / np.log(21106.77 / (0.012545258 * (raw.astype(float) - 7340)) + 1)
        - 273.15
    )
    np.testing.assert_allclose(frame.celsius, expected, atol=0.0001)
    assert frame.metadata["camera"] == "Test"


def test_environmental_compensation_reference(tmp_path: Path) -> None:
    path = tmp_path / "sensor.fff"
    path.write_bytes(fff())
    frame = ThermalSource(path).read(0)
    m = dict(
        frame.metadata,
        emissivity=0.8,
        distance=2,
        window_transmission=0.7,
        reflected_kelvin=280,
        air_kelvin=290,
        window_kelvin=300,
        alpha1=-math.log(0.9),
        beta1=0,
        atx=1,
    )

    def radiation(kelvin: float) -> float:
        return m["r1"] / (m["r2"] * (math.exp(m["b"] / kelvin) - m["f"])) - m["o"]

    # Forward radiation transfer for a 40 C object through two atmospheric
    # segments (90% each) and a 70% transmitting window. Recover 40 C.
    outgoing = 0.8 * radiation(313.15) + 0.2 * radiation(280)
    before_window = outgoing * 0.9 + radiation(290) * 0.1
    after_window = before_window * 0.7 + radiation(300) * 0.3
    measured = after_window * 0.9 + radiation(290) * 0.1
    value = temperatures(np.array([[measured]]), m)[0, 0]
    assert value == pytest.approx(40, abs=0.0001)
    m["emissivity"] = 0
    with pytest.raises(ThermalError, match="Invalid emissivity"):
        temperatures(frame.raw, m)


def test_jpeg_zero_counters_and_missing_thermal_data(tmp_path: Path) -> None:
    path = tmp_path / "test.jpg"
    path.write_bytes(radiometric_jpeg(fff(), zero_counters=True))
    assert ThermalSource(path).read(0).raw.shape == (2, 2)
    Image.new("RGB", (4, 4)).save(path)
    with pytest.raises(ThermalError, match="no embedded"):
        ThermalSource(path)


def test_csq_index_and_truncated_tail_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "camera.csq"
    frame = fff()
    path.write_bytes(frame + frame + frame[:-4])
    source = ThermalSource(path)
    assert len(source) == 2
    assert "Only preceding complete frames" in source.warnings[0]
    np.testing.assert_array_equal(source.read(0).raw, source.read(1).raw)
    path.write_bytes(frame[:-4])
    with pytest.raises(ThermalError, match="truncated"):
        ThermalSource(path)


def test_palette_clipping_and_invalid_pixels() -> None:
    values = np.array([[-10, 10, 15, 20, 30, 40, 50, 60, 70, np.nan]])
    rgb = colourise(values, 10, 60)
    assert rgb.tolist() == [
        [
            [0, 0, 32],
            [0, 0, 32],
            [38, 0, 81],
            [75, 0, 130],
            [200, 0, 45],
            [255, 100, 0],
            [255, 220, 0],
            [255, 255, 255],
            [255, 255, 255],
            [0, 0, 0],
        ]
    ]
    with pytest.raises(ThermalError, match="white temperature"):
        colourise(values, 20, 20)


def test_export_temperature_round_trip_and_image_binding(tmp_path: Path) -> None:
    path = tmp_path / "source.fff"
    path.write_bytes(fff())
    frame = ThermalSource(path).read(0)
    image = tmp_path / "frame.png"
    save_frame(frame, image, 15, 35, source="camera.csq", index=14)
    loaded, limits = load_frame(image)
    assert limits == (15, 35)
    assert loaded.metadata["frame_index"] == 14
    np.testing.assert_array_equal(loaded.raw, frame.raw)
    np.testing.assert_array_equal(loaded.celsius, frame.celsius)
    with pytest.raises(ThermalError, match="already exists"):
        save_frame(frame, image, 15, 35, source="camera.csq", index=14)
    Image.new("RGB", (2, 2)).save(image)
    with pytest.raises(ThermalError, match="no longer matches"):
        load_frame(image)


def test_damaged_temperature_archive_reports_a_readable_error(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    Image.new("RGB", (2, 2)).save(image)
    sidecar_path(image).write_bytes(b"PK\x03\x04truncated zip archive")
    with pytest.raises(ThermalError, match="incomplete or damaged"):
        load_frame(image)


@pytest.mark.parametrize("separate", [True, False])
def test_csq_sampling_retains_temperatures_and_frame_indices(
    tmp_path: Path, separate: bool
) -> None:
    path = tmp_path / "camera.csq"
    path.write_bytes(fff() * 5)
    result = extract_frames(
        ExtractionOptions(
            (VideoSource(path, "camera"),),
            tmp_path,
            amount=3,
            percentage=False,
            separate_folders=separate,
            thermal_range=(10, 30),
        ),
        threading.Event(),
        lambda *_: None,
    )
    assert not result.errors
    assert result.saved == 3 and result.completed == 1
    images = sorted(result.output.rglob("*.png"))
    assert [load_frame(image)[0].metadata["frame_index"] for image in images] == [
        0,
        2,
        4,
    ]
    assert all(load_frame(image)[1] == (10, 30) for image in images)


def test_csq_cancellation_discards_unfinished_recording(tmp_path: Path) -> None:
    path = tmp_path / "camera.csq"
    path.write_bytes(fff() * 5)
    cancel = threading.Event()

    def progress(_: int, message: str) -> None:
        if "Decoded 1" in message:
            cancel.set()

    result = extract_frames(
        ExtractionOptions((VideoSource(path, "camera"),), tmp_path), cancel, progress
    )
    assert result.cancelled and result.saved == 0
    assert not list(result.output.iterdir())


def test_csq_extraction_keeps_analysis_and_recalculated_temperatures(
    tmp_path: Path,
) -> None:
    from labelme._thermal_analysis import Display
    from labelme._thermal_analysis import recalculate
    from labelme._thermal_analysis import render

    path = tmp_path / "camera.csq"
    path.write_bytes(fff() * 2)
    analysis = {
        "display": {"palette": "black_hot"},
        "unit": "F",
        "parameters": {"emissivity": 0.8},
        "measurements": [],
    }
    result = extract_frames(
        ExtractionOptions(
            (VideoSource(path, "camera"),),
            tmp_path,
            thermal_range=(10, 40),
            thermal_analysis=analysis,
        ),
        threading.Event(),
        lambda *_: None,
    )
    assert not result.errors and result.saved == 2
    image = sorted(result.output.rglob("*.png"))[0]
    frame, limits = load_frame(image)
    expected = recalculate(ThermalSource(path).read(0), {"emissivity": 0.8})
    np.testing.assert_array_equal(frame.celsius, expected.celsius)
    assert frame.metadata["analysis"] == analysis
    np.testing.assert_array_equal(
        np.array(Image.open(image)),
        render(expected, *limits, Display(palette="black_hot")),
    )
