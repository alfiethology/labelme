from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from loguru import logger


class _FileLabels(NamedTuple):
    signature: tuple[int, int, int]
    labels: tuple[str, ...]


class LabelNameIndex:
    """Cache class names without retaining embedded image data from each JSON."""

    def __init__(self) -> None:
        self._files: dict[Path, _FileLabels] = {}

    def names(self, paths: Iterable[Path]) -> list[str]:
        active: set[Path] = set()
        names: dict[str, None] = {}
        for candidate in paths:
            try:
                path = candidate.resolve()
                if path in active:
                    continue
                active.add(path)
                try:
                    info = path.stat()
                except FileNotFoundError:
                    self._files.pop(path, None)
                    continue
                signature = (info.st_mtime_ns, info.st_ctime_ns, info.st_size)
                entry = self._files.get(path)
                if entry is None or entry.signature != signature:
                    labels: tuple[str, ...] = ()
                    try:
                        data = json.loads(path.read_bytes())
                        if not isinstance(data, dict) or not isinstance(
                            data.get("shapes"), list
                        ):
                            raise ValueError(
                                "Expected an annotation object with a shapes list"
                            )
                        labels = tuple(
                            dict.fromkeys(
                                shape["label"]
                                for shape in data["shapes"]
                                if isinstance(shape, dict)
                                and isinstance(shape.get("label"), str)
                                and shape["label"]
                            )
                        )
                    except (OSError, ValueError) as error:
                        logger.warning(
                            "Could not read label names from {}: {}", path, error
                        )
                    entry = _FileLabels(signature, labels)
                    self._files[path] = entry
                names.update(dict.fromkeys(entry.labels))
            except OSError as error:
                logger.warning("Could not inspect annotation {}: {}", candidate, error)
        self._files = {
            path: entry for path, entry in self._files.items() if path in active
        }
        return list(names)
