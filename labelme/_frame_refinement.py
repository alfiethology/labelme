from __future__ import annotations

import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore

from ._label_file import Annotation
from ._label_file import ShapeDict
from ._label_file import read_image_file
from ._label_file import write_label_file
from ._shape import Shape
from ._yolo_predictions import shapes_from_yolo_result


@dataclass(frozen=True)
class FramePrediction:
    image_path: Path
    shapes: list[Shape]


class FrameInferenceWorker(QtCore.QObject):
    progress = QtCore.Signal(int, str)
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        *,
        image_paths: list[Path],
        model_path: Path,
        confidence: float,
    ) -> None:
        super().__init__()
        self._image_paths = image_paths
        self._model_path = model_path
        self._confidence = confidence
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @QtCore.Slot()
    def run(self) -> None:
        try:
            from ultralytics import YOLO

            model = YOLO(str(self._model_path))
            model_yaml = getattr(getattr(model, "model", None), "yaml", None)
            metadata = model_yaml if isinstance(model_yaml, dict) else {}
            predictions: list[FramePrediction] = []
            for index, image_path in enumerate(self._image_paths, start=1):
                if self._cancelled:
                    self.completed.emit([])
                    return
                results = model.predict(
                    source=str(image_path),
                    conf=self._confidence,
                    verbose=False,
                )
                if not results:
                    raise RuntimeError(f"Model returned no result for {image_path}")
                predictions.append(
                    FramePrediction(
                        image_path=image_path,
                        shapes=shapes_from_yolo_result(
                            results[0],
                            model_path=self._model_path,
                            model_metadata=metadata,
                        ),
                    )
                )
                self.progress.emit(index, image_path.name)
            self.completed.emit(predictions)
        except Exception:
            self.failed.emit(traceback.format_exc())


class VideoInferenceWorker(QtCore.QObject):
    progress = QtCore.Signal(int, str)
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        *,
        video_path: Path,
        frame_indices: list[int],
        cache_dir: Path,
        model_path: Path,
        confidence: float,
    ) -> None:
        super().__init__()
        self._video_path = video_path
        self._frame_indices = frame_indices
        self._cache_dir = cache_dir
        self._model_path = model_path
        self._confidence = confidence
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @QtCore.Slot()
    def run(self) -> None:
        capture = None
        try:
            import cv2
            from ultralytics import YOLO

            model = YOLO(str(self._model_path))
            model_yaml = getattr(getattr(model, "model", None), "yaml", None)
            metadata = model_yaml if isinstance(model_yaml, dict) else {}
            capture = cv2.VideoCapture(str(self._video_path))
            if not capture.isOpened():
                raise RuntimeError(f"Could not open video: {self._video_path}")

            predictions: list[FramePrediction] = []
            for sample_number, frame_index in enumerate(self._frame_indices, start=1):
                if self._cancelled:
                    self.completed.emit([])
                    return
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError(
                        f"Could not read frame {frame_index} from {self._video_path}"
                    )
                frame_path = (
                    self._cache_dir / f"{self._video_path.stem}-{frame_index:08d}.jpg"
                )
                if not cv2.imwrite(str(frame_path), frame):
                    raise RuntimeError(f"Could not write extracted frame: {frame_path}")
                results = model.predict(
                    source=str(frame_path),
                    conf=self._confidence,
                    verbose=False,
                )
                if not results:
                    raise RuntimeError(f"Model returned no result for {frame_path}")
                predictions.append(
                    FramePrediction(
                        image_path=frame_path,
                        shapes=shapes_from_yolo_result(
                            results[0],
                            model_path=self._model_path,
                            model_metadata=metadata,
                        ),
                    )
                )
                self.progress.emit(sample_number, f"frame {frame_index + 1}")
            self.completed.emit(predictions)
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if capture is not None:
                capture.release()


def save_refined_frame(
    *,
    source_root: Path,
    output_root: Path,
    image_path: Path,
    shapes: list[Shape],
    image_height: int,
    image_width: int,
) -> tuple[Path, Path]:
    """Copy one hard frame and write its edited Labelme annotation."""

    relative_path = image_path.relative_to(source_root)
    in_place = output_root.resolve() == source_root.resolve()
    destination_image = image_path if in_place else output_root / relative_path
    destination_label = destination_image.with_suffix(".json")
    if destination_label.exists():
        raise FileExistsError(
            f"Annotation already exists and was not overwritten: {destination_label}"
        )
    if not in_place and destination_image.exists():
        raise FileExistsError(
            f"Refinement image already exists and was not overwritten: "
            f"{destination_image}"
        )
    copied_image = False
    if not in_place:
        destination_image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, destination_image)
        copied_image = True
    image_data = read_image_file(str(destination_image))
    annotation = Annotation(
        image_path=destination_image.name,
        image_data=image_data,
        shapes=[
            ShapeDict(
                label=shape.label or "",
                points=shape.points.tolist(),
                shape_type=shape.shape_type,
                flags=shape.flags or {},
                description=shape.description or "",
                group_id=shape.group_id,
                mask=shape.mask,
                other_data=shape.other_data,
            )
            for shape in shapes
        ],
        flags={},
        other_data={"refinementSource": str(image_path)},
    )
    try:
        write_label_file(
            str(destination_label),
            annotation,
            image_height=image_height,
            image_width=image_width,
            save_image_data=False,
        )
    except Exception:
        if copied_image:
            destination_image.unlink(missing_ok=True)
        raise
    return destination_image, destination_label
