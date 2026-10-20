from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from labelme import _label_merge
from labelme._label_merge import LabelMergeError
from labelme._label_merge import prepare_label_changes
from labelme._label_merge import read_label_documents
from labelme._label_merge import write_label_changes


def _annotation(path: Path, label: str = "snakes") -> bytes:
    content = json.dumps({"shapes": [{"label": label, "points": [[1, 2]]}]}).encode()
    path.write_bytes(content)
    return content


def test_merge_changes_only_exact_shape_labels_and_preserves_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.json"
    original = {
        "version": "older-version",
        "imageData": "keep encoded data",
        "imagePath": "a.png",
        "flags": {"reviewed": True},
        "custom": {"label": "snakes"},
        "shapes": [
            {
                "label": "snakes",
                "shape_type": shape_type,
                "points": [[1, 2]],
                "flags": {"occluded": True},
                "group_id": 7,
                "description": "snakes",
                "mask": "encoded-mask",
                "custom": {"label": "snakes"},
            }
            for shape_type in (
                "polygon",
                "rectangle",
                "oriented_rectangle",
                "point",
                "line",
                "circle",
                "linestrip",
                "points",
                "skeleton",
                "mask",
            )
        ]
        + [{"label": label} for label in ("snake", "Snakes", "snakeskin", "snakes;")],
    }
    path.write_text(json.dumps(original))
    documents = read_label_documents([path, path.parent / "." / path.name])
    assert len(documents) == 1
    changes = prepare_label_changes(documents, "snakes", "蛇")
    assert changes[0].count == 10
    with write_label_changes(changes):
        pass
    expected = original.copy()
    expected["shapes"] = [
        {**shape, "label": "蛇"} if shape["label"] == "snakes" else shape
        for shape in original["shapes"]
    ]
    assert json.loads(path.read_bytes()) == expected
    assert documents[0].data == original


def test_missing_and_nonmatching_files_are_not_written(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    original = _annotation(path, "snake")
    documents = read_label_documents([path, tmp_path / "missing.json"])
    changes = prepare_label_changes(documents, "snakes", "snake")
    assert changes == []
    with write_label_changes(changes):
        pass
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "content",
    [
        "broken",
        "[]",
        "{}",
        '{"shapes": {}}',
        '{"shapes": [null]}',
        '{"shapes": [{"label": 1}]}',
    ],
)
def test_invalid_json_is_rejected_before_any_changes(
    tmp_path: Path, content: str
) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    original = _annotation(first)
    second.write_text(content)
    with pytest.raises(LabelMergeError, match="b.json"):
        read_label_documents([first, second])
    assert first.read_bytes() == original
    assert second.read_text() == content


def test_write_failure_restores_completed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    originals = {path: _annotation(path) for path in (first, second)}
    first.chmod(0o640)
    changes = prepare_label_changes(
        read_label_documents([first, second]), "snakes", "snake"
    )
    replace = _label_merge._replace_file

    def fail_second(path: Path, content: bytes) -> None:
        if path == second:
            raise OSError("disk full")
        replace(path, content)

    monkeypatch.setattr(_label_merge, "_replace_file", fail_second)
    with pytest.raises(LabelMergeError, match="disk full"):
        with write_label_changes(changes):
            pytest.fail("Should not reach settings write")
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert stat.S_IMODE(first.stat().st_mode) == 0o640
    assert not list(tmp_path.glob("*.tmp"))


def test_external_changes_are_not_overwritten_and_prior_writes_are_restored(
    tmp_path: Path,
) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    original = _annotation(first)
    _annotation(second)
    changes = prepare_label_changes(
        read_label_documents([first, second]), "snakes", "snake"
    )
    external = _annotation(second, "edited elsewhere")
    with pytest.raises(LabelMergeError, match="annotation changed during"):
        with write_label_changes(changes):
            pass
    assert first.read_bytes() == original
    assert second.read_bytes() == external


def test_settings_failure_rolls_back_json_changes(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    original = _annotation(path)
    changes = prepare_label_changes(read_label_documents([path]), "snakes", "snake")
    with pytest.raises(LabelMergeError, match="cannot save preferences"):
        with write_label_changes(changes):
            assert json.loads(path.read_bytes())["shapes"][0]["label"] == "snake"
            raise OSError("cannot save preferences")
    assert path.read_bytes() == original


def test_failed_atomic_replacement_keeps_original_and_cleans_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.json"
    original = _annotation(path)
    changes = prepare_label_changes(read_label_documents([path]), "snakes", "snake")

    def fail(*args: object) -> None:
        raise PermissionError("cannot replace")

    monkeypatch.setattr(_label_merge.os, "replace", fail)
    with pytest.raises(LabelMergeError, match="cannot replace"):
        with write_label_changes(changes):
            pass
    assert path.read_bytes() == original
    assert set(tmp_path.iterdir()) == {path}


def test_rollback_failure_reports_files_that_remain_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.json"
    _annotation(path)
    changes = prepare_label_changes(read_label_documents([path]), "snakes", "snake")
    replace = _label_merge._replace_file

    def fail_restore(path: Path, content: bytes) -> None:
        if content == changes[0].original:
            raise OSError("read only")
        replace(path, content)

    monkeypatch.setattr(_label_merge, "_replace_file", fail_restore)
    with pytest.raises(LabelMergeError, match="Could not restore these files") as error:
        with write_label_changes(changes):
            raise OSError("settings write failed")
    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    ("source", "target"), [("snakes", "snakes"), ("", "snake"), ("snakes", "")]
)
def test_invalid_merge_names_are_rejected(source: str, target: str) -> None:
    with pytest.raises(ValueError):
        prepare_label_changes([], source, target)
