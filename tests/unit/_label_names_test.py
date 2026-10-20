from __future__ import annotations

import json
from pathlib import Path

import pytest

from labelme._label_names import LabelNameIndex


def _write(path: Path, labels: list[str]) -> None:
    path.write_text(json.dumps({"shapes": [{"label": label} for label in labels]}))


def test_names_are_unique_across_jsons_and_all_shape_types(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    first.write_text(
        json.dumps(
            {
                "imageData": "opaque data that must not be decoded",
                "shapes": [
                    {"label": label, "shape_type": shape_type}
                    for label, shape_type in (
                        ("snake", "rectangle"),
                        ("bird", "point"),
                        ("snake", "mask"),
                    )
                ],
            }
        )
    )
    _write(second, ["bird", "蝶"])
    assert LabelNameIndex().names(
        [first, second, first, tmp_path / "missing.json"]
    ) == ["snake", "bird", "蝶"]


def test_unchanged_jsons_are_cached_and_edited_jsons_are_refreshed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    _write(first, ["snake"])
    _write(second, ["bird"])
    original_read = Path.read_bytes
    reads: list[Path] = []

    def read(path: Path) -> bytes:
        reads.append(path)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    index = LabelNameIndex()
    assert index.names([first, second]) == ["snake", "bird"]
    assert index.names([first, second]) == ["snake", "bird"]
    assert reads == [first, second]
    _write(second, ["elephant"])
    assert index.names([first, second]) == ["snake", "elephant"]
    assert reads == [first, second, second]


def test_deleted_new_and_removed_files_update_the_name_pool(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    _write(first, ["snake"])
    index = LabelNameIndex()
    assert index.names([first, second]) == ["snake"]
    _write(second, ["bird"])
    assert index.names([first, second]) == ["snake", "bird"]
    assert index.names([first]) == ["snake"]
    first.unlink()
    assert index.names([first]) == []
    _write(first, ["new snake"])
    assert index.names([first]) == ["new snake"]


@pytest.mark.parametrize("invalid", ["broken", "[]", "{}", '{"shapes": 1}'])
def test_invalid_json_does_not_hide_names_in_valid_files(
    tmp_path: Path, invalid: str
) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    first.write_text(invalid)
    _write(second, ["bird"])
    index = LabelNameIndex()
    assert index.names([first, second]) == ["bird"]
    _write(first, ["repaired"])
    assert index.names([first, second]) == ["repaired", "bird"]


def test_invalid_shapes_and_empty_names_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(
        json.dumps(
            {"shapes": [None, 1, {}, {"label": 2}, {"label": ""}, {"label": "bird"}]}
        )
    )
    assert LabelNameIndex().names([path]) == ["bird"]
