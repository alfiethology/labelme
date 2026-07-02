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

        options = QtWidgets.QHBoxLayout()
        options.addWidget(QtWidgets.QLabel(self.tr("Confidence")))
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
        options.addWidget(self._confidence)

        run = QtWidgets.QPushButton(self.tr("Run"))
        run.clicked.connect(on_run)
        options.addWidget(run)
        layout.addLayout(options)

        self.setMaximumWidth(320)

    @property
    def model_path(self) -> Path:
        return Path(self._path_edit.text()).expanduser()

    @property
    def confidence(self) -> float:
        return self._confidence.value()

    def _on_path_changed(self, path: str) -> None:
        self._settings.setValue("customYolo/modelPath", path)
        self._path_edit.setToolTip(path)

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
