from pathlib import Path

import pytest

from labelme import _config


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"": {"inner": [0, 0, 0], "outer": [255, 255, 255]}},
        {"cat": [0, 0, 0]},
        {"cat": {"inner": [0, 0, 0]}},
        {"cat": {"inner": [0, 0, 256], "outer": [255, 255, 255]}},
        {"cat": {"inner": [0, 0, 0], "outer": [True, 255, 255]}},
    ],
)
def test_invalid_point_colours_cannot_be_loaded_or_written(
    tmp_path: Path, value: object
) -> None:
    with pytest.raises(ValueError, match="shape.point_colors_by_label"):
        _config.load_config(
            config_file=None,
            config_overrides={"shape": {"point_colors_by_label": value}},
        )
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: false\n")
    with pytest.raises(ValueError, match="shape.point_colors_by_label"):
        _config.set_overrides(
            config_file=config_file,
            overrides=[(("shape", "point_colors_by_label"), value)],
        )
    assert config_file.read_text() == "auto_save: false\n"


def test_class_names_and_both_colours_round_trip(tmp_path: Path) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    colors = {
        "cat.eye": {"inner": [12, 34, 56], "outer": [210, 220, 230]},
        "dog / nose": {"inner": [65, 43, 21], "outer": [30, 20, 10]},
    }
    _config.set_overrides(
        config_file=config_file,
        overrides=[(("shape", "point_colors_by_label"), colors)],
    )
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["shape"]["point_colors_by_label"] == colors
