from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6 import QtCore
from PySide6 import QtWidgets

DEFAULT_MODEL_PATH = (
    "/home/or22503/OneDrive/Celine_rat_tracking/runs/detect/"
    "mode14-26x-144e/weights/best.pt"
)


class CustomYoloWidget(QtWidgets.QWidget):
    def __init__(
        self,
        on_run: Callable[[], None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._settings = QtCore.QSettings("labelme", "labelme")
        self._init_ui(on_run=on_run)

    def _init_ui(self, on_run: Callable[[], None]) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        title = QtWidgets.QLabel(self.tr("Custom YOLO Detector"))
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        path_layout = QtWidgets.QHBoxLayout()
        self._path_edit = QtWidgets.QLineEdit()
        stored_path = cast(
            str,
            self._settings.value("customYolo/modelPath", DEFAULT_MODEL_PATH, type=str),
        )
        self._path_edit.setText(stored_path)
        self._path_edit.setPlaceholderText(self.tr("Select an Ultralytics .pt model"))
        self._path_edit.setToolTip(stored_path)
        self._path_edit.textChanged.connect(self._on_path_changed)
        path_layout.addWidget(self._path_edit, stretch=1)

        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip(self.tr("Choose YOLO model"))
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        layout.addLayout(path_layout)

        self._active_model_label = QtWidgets.QLabel()
        self._active_model_label.setToolTip(stored_path)
        self._update_active_model_label(stored_path)
        layout.addWidget(self._active_model_label)

        pose_layout = QtWidgets.QHBoxLayout()
        pose_layout.addWidget(QtWidgets.QLabel(self.tr("Pose template")))
        self._pose_template_edit = QtWidgets.QLineEdit()
        self._pose_template_edit.setPlaceholderText(self.tr("Optional .skeleton.json"))
        self._pose_template_edit.setClearButtonEnabled(True)
        self._pose_template_edit.textChanged.connect(self._on_pose_template_changed)
        self._restore_pose_template(stored_path)
        pose_layout.addWidget(self._pose_template_edit, stretch=1)
        pose_browse = QtWidgets.QToolButton()
        pose_browse.setText("…")
        pose_browse.setToolTip(
            self.tr("Choose keypoint names and bones for this pose model")
        )
        pose_browse.clicked.connect(self._browse_pose_template)
        pose_layout.addWidget(pose_browse)
        layout.addLayout(pose_layout)

        options = QtWidgets.QGridLayout()
        options.addWidget(QtWidgets.QLabel(self.tr("Confidence")), 0, 0)
        self._confidence = QtWidgets.QDoubleSpinBox()
        self._confidence.setRange(0.01, 1.0)
        self._confidence.setSingleStep(0.05)
        self._confidence.setValue(
            cast(
                float,
                self._settings.value("customYolo/confidence", 0.25, type=float),
            )
        )
        self._confidence.valueChanged.connect(
            lambda value: self._settings.setValue("customYolo/confidence", value)
        )
        options.addWidget(self._confidence, 0, 1)

        options.addWidget(QtWidgets.QLabel(self.tr("Point gap")), 1, 0)
        self._polygon_point_spacing = QtWidgets.QSpinBox()
        self._polygon_point_spacing.setRange(1, 500)
        self._polygon_point_spacing.setSuffix(self.tr(" px"))
        self._polygon_point_spacing.setToolTip(
            self.tr("Approximate spacing between polygon points")
        )
        self._polygon_point_spacing.setValue(
            cast(
                int,
                self._settings.value("customYolo/polygonPointSpacing", 10, type=int),
            )
        )
        self._polygon_point_spacing.valueChanged.connect(
            lambda value: self._settings.setValue(
                "customYolo/polygonPointSpacing", value
            )
        )
        options.addWidget(self._polygon_point_spacing, 1, 1)

        run = QtWidgets.QPushButton(self.tr("Run"))
        run.clicked.connect(on_run)
        options.addWidget(run, 0, 2, 2, 1)
        layout.addLayout(options)

        self.setMaximumWidth(320)

    @property
    def model_path(self) -> Path:
        return Path(self._path_edit.text()).expanduser()

    @property
    def pose_template_path(self) -> Path | None:
        text = self._pose_template_edit.text().strip()
        return Path(text).expanduser() if text else None

    def _pose_templates(self) -> dict[str, str]:
        stored = self._settings.value("customYolo/poseTemplates", {})
        return dict(stored) if isinstance(stored, dict) else {}

    def _restore_pose_template(self, model_path: str) -> None:
        key = str(Path(model_path).expanduser().resolve())
        path = self._pose_templates().get(key, "")
        blocker = QtCore.QSignalBlocker(self._pose_template_edit)
        self._pose_template_edit.setText(path if isinstance(path, str) else "")
        self._pose_template_edit.setToolTip(
            self.tr(
                "Use the training keypoint order; "
                "names and bones come from this template."
            )
        )
        del blocker

    def _on_pose_template_changed(self, path: str) -> None:
        templates = self._pose_templates()
        key = str(self.model_path.resolve())
        if path.strip():
            templates[key] = path.strip()
        else:
            templates.pop(key, None)
        self._settings.setValue("customYolo/poseTemplates", templates)

    def _browse_pose_template(self) -> None:
        current = self.pose_template_path
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Choose Pose Skeleton Template"),
            str(current.parent if current is not None else self.model_path.parent),
            self.tr("Skeleton templates (*.skeleton.json);;JSON files (*.json)"),
        )
        if filename:
            self._pose_template_edit.setText(filename)

    @property
    def confidence(self) -> float:
        return self._confidence.value()

    @property
    def polygon_point_spacing(self) -> int:
        return self._polygon_point_spacing.value()

    def _on_path_changed(self, path: str) -> None:
        self._settings.setValue("customYolo/modelPath", path)
        self._path_edit.setToolTip(path)
        self._active_model_label.setToolTip(path)
        self._update_active_model_label(path)
        self._restore_pose_template(path)

    def _update_active_model_label(self, path: str) -> None:
        model_path = Path(path)
        model_name = "/".join(model_path.parts[-4:]) if path else self.tr("none")
        self._active_model_label.setText(self.tr("Active model: {}").format(model_name))

    def _browse(self) -> None:
        start = str(self.model_path.parent) if self.model_path.name else ""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Choose Custom YOLO Model"),
            start,
            self.tr("PyTorch Models (*.pt);;All Files (*)"),
        )
        if path:
            self._path_edit.setText(path)
