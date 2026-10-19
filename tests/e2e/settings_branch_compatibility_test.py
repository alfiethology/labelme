from pathlib import Path

import pytest

from labelme._yaml import safe_load

from .conftest import MainWinFactory


@pytest.mark.gui
@pytest.mark.parametrize("explicit_config", [False, True])
def test_snap_preferences_persist_with_point_colours_from_another_branch(
    main_win: MainWinFactory,
    tmp_path: Path,
    session_home: Path,
    explicit_config: bool,
) -> None:
    config_file = (
        tmp_path / "labelmerc.yaml" if explicit_config else session_home / ".labelmerc"
    )
    config_file.write_text(
        "auto_save: false\n"
        "with_image_data: true\n"
        "shape:\n"
        "  vertex_outline_color: [10, 20, 30, 255]\n"
        "  point_colors_by_label:\n"
        "    hen_point:\n"
        "      inner: [230, 97, 0]\n"
        "      outer: [249, 240, 107]\n"
    )
    original = safe_load(config_file.read_text())
    win = main_win(config_file=config_file if explicit_config else None)
    assert win._config_file == config_file
    assert win._is_settings_editable
    assert win._config["auto_save"] is False
    assert win._config["with_image_data"] is True
    palette = win._canvas_widgets.canvas._resolve_palette("hen_point")
    assert palette.vertex_fill.getRgb() == (230, 97, 0, 255)
    assert palette.vertex_outline.getRgb() == (249, 240, 107, 255)
    for key in ("snap_to_existing_points", "lock_cursor_to_pixels"):
        action = getattr(win._actions, key)
        assert not action.isChecked()
        action.trigger()
        assert action.isChecked()
        assert getattr(win._canvas_widgets.canvas, f"_{key}") is True
    win.close()

    saved = safe_load(config_file.read_text())
    assert saved["shape"] == original["shape"]
    assert saved["canvas"]["snap_to_existing_points"] is True
    assert saved["canvas"]["lock_cursor_to_pixels"] is True
    reopened = main_win(config_file=config_file if explicit_config else None)
    assert reopened._is_settings_editable
    assert reopened._canvas_widgets.canvas._resolve_palette("hen_point") == palette
    for key in ("snap_to_existing_points", "lock_cursor_to_pixels"):
        assert getattr(reopened._actions, key).isChecked()
        assert getattr(reopened._canvas_widgets.canvas, f"_{key}") is True
    assert safe_load(config_file.read_text()) == saved
