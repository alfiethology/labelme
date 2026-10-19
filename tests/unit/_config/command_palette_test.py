import json
from pathlib import Path

import pytest

from labelme import _config


@pytest.mark.parametrize(
    ("old", "expected"),
    [
        ("Ctrl+P", "Ctrl+Shift+P"),
        ("ctrl + p", "Ctrl+Shift+P"),
        (["Ctrl+P", "Alt+K"], ["Ctrl+Shift+P", "Alt+K"]),
        (["Ctrl+Shift+P", "Ctrl+P"], ["Ctrl+Shift+P"]),
        ("Alt+P", "Alt+P"),
        (None, None),
    ],
)
def test_previous_annotation_shortcut_migrates_in_files_and_inline_config(
    tmp_path: Path, old: object, expected: object
) -> None:
    overrides = {"shortcuts": {"toggle_keep_prev_mode": old}}
    config_file = tmp_path / "labelmerc.yaml"
    original = json.dumps(overrides)
    config_file.write_text(original)
    for config in (
        _config.load_config(config_file=config_file, config_overrides={}),
        _config.load_config(config_file=None, config_overrides=overrides),
    ):
        assert config["shortcuts"]["toggle_keep_prev_mode"] == expected
        assert config["shortcuts"]["command_palette"] == "Ctrl+P"
    assert overrides["shortcuts"]["toggle_keep_prev_mode"] == old
    assert config_file.read_text() == original


def test_command_palette_and_previous_annotation_shortcuts_are_distinct() -> None:
    config = _config.load_config(config_file=None, config_overrides={})
    assert config["shortcuts"]["command_palette"] == "Ctrl+P"
    assert config["shortcuts"]["toggle_keep_prev_mode"] == "Ctrl+Shift+P"
