from __future__ import annotations

import contextlib
import json
import os
import stat
import tempfile
from collections.abc import Iterable
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LabelMergeError(Exception):
    pass


@dataclass(frozen=True)
class LabelDocument:
    path: Path
    original: bytes
    data: dict[str, Any]


@dataclass(frozen=True)
class LabelChange:
    path: Path
    original: bytes
    updated: bytes
    count: int


def read_label_documents(paths: Iterable[Path]) -> list[LabelDocument]:
    """Read JSON without decoding images, masks, or changing unknown fields."""
    documents = []
    for path in dict.fromkeys(path.resolve() for path in paths):
        try:
            try:
                original = path.read_bytes()
            except FileNotFoundError:
                # Images without an annotation file are normal in the file list.
                continue
            data = json.loads(original)
            if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
                raise ValueError("Expected an annotation object with a shapes list")
            if not all(
                isinstance(shape, dict) and isinstance(shape.get("label"), str)
                for shape in data["shapes"]
            ):
                raise ValueError("Every shape must have a string label")
            documents.append(LabelDocument(path, original, data))
        except (OSError, ValueError) as error:
            raise LabelMergeError(f"{path}: {error}") from error
    return documents


def prepare_label_changes(
    documents: Iterable[LabelDocument], source: str, target: str
) -> list[LabelChange]:
    if not source or not target or source == target:
        raise ValueError("Choose two different, non-empty labels")
    changes = []
    for document in documents:
        count = sum(shape["label"] == source for shape in document.data["shapes"])
        if not count:
            continue
        data = {
            **document.data,
            "shapes": [
                {**shape, "label": target} if shape["label"] == source else shape
                for shape in document.data["shapes"]
            ],
        }
        updated = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        changes.append(LabelChange(document.path, document.original, updated, count))
    return changes


def _replace_file(path: Path, content: bytes) -> None:
    # Stage beside the original so replacement is atomic and retains permissions.
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, staged = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            os.chmod(staged, mode)
        os.replace(staged, path)
    finally:
        Path(staged).unlink(missing_ok=True)


@contextlib.contextmanager
def write_label_changes(changes: Iterable[LabelChange]) -> Iterator[None]:
    """Roll back completed writes if a file or the caller's settings write fails."""
    completed = []
    try:
        for change in changes:
            if change.path.read_bytes() != change.original:
                raise LabelMergeError(
                    f"{change.path}: annotation changed during the merge"
                )
            _replace_file(change.path, change.updated)
            completed.append(change)
        yield
    except Exception as error:
        failures = []
        for change in reversed(completed):
            try:
                if change.path.read_bytes() != change.updated:
                    raise LabelMergeError("annotation changed after writing")
                _replace_file(change.path, change.original)
            except (OSError, LabelMergeError) as rollback_error:
                failures.append(f"{change.path}: {rollback_error}")
        message = str(error)
        if failures:
            message += "\nCould not restore these files:\n" + "\n".join(failures)
        raise LabelMergeError(message) from error
