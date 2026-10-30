from __future__ import annotations

import threading
from pathlib import Path

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._frame_extraction import ExtractionOptions
from .._frame_extraction import ExtractionResult
from .._frame_extraction import VideoSource
from .._frame_extraction import extract_frames
from .._frame_extraction import safe_name


class SamplingPreview(QtWidgets.QWidget):
    """Small schematic, never a preview of the actual random draw."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(72)
        self.setAccessibleName(self.tr("Sampling examples: evenly spaced and random"))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        for y, title, dots in (
            (25, self.tr("Evenly spaced"), (0, 0.2, 0.4, 0.6, 0.8, 1)),
            (64, self.tr("Random"), (0.04, 0.12, 0.39, 0.44, 0.74, 0.96)),
        ):
            painter.setPen(palette.color(QtGui.QPalette.ColorRole.Text))
            label_width = max(
                140, self.fontMetrics().horizontalAdvance(self.tr("Evenly spaced")) + 15
            )
            painter.drawText(0, y + 5, title)
            left, right = label_width, max(label_width + 20, self.width() - 12)
            painter.setPen(QtGui.QPen(palette.color(QtGui.QPalette.ColorRole.Mid), 2))
            painter.drawLine(left, y, right, y)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(palette.color(QtGui.QPalette.ColorRole.Highlight))
            for dot in dots:
                painter.drawEllipse(
                    QtCore.QPointF(left + dot * (right - left), y), 4, 4
                )


class ExtractionThread(QtCore.QThread):
    progress = QtCore.Signal(int, str)

    def __init__(self, options: ExtractionOptions, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self.options = options
        self.cancel = threading.Event()
        self.result: ExtractionResult | None = None
        self.error: str | None = None

    def run(self) -> None:
        try:
            self.result = extract_frames(self.options, self.cancel, self.progress.emit)
        except Exception as error:
            self.error = str(error)


class FrameExtractorDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Extract Video Frames"))
        self.resize(760, 760)
        self._thread: ExtractionThread | None = None
        self._videos: list[Path] = []
        self.thermal_range: tuple[float, float] | None = None
        self.thermal_analysis: dict | None = None
        layout = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        content = QtWidgets.QWidget()
        form = QtWidgets.QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        intro = QtWidgets.QLabel(
            self.tr(
                "Extract PNG images from MP4, AVI and FLIR CSQ videos. "
                "CSQ frames include temperature data; keep each PNG and "
                ".thermal.npz file together. MP4/AVI require FFmpeg 5.1+ and ffprobe; "
                "compressed CSQ requires FFmpeg. Your current image, unsaved "
                "annotations and File List stay unchanged."
            )
        )
        intro.setWordWrap(True)
        form.addWidget(intro)
        videos_group = QtWidgets.QGroupBox(self.tr("1. Videos"))
        videos_layout = QtWidgets.QVBoxLayout(videos_group)
        self.videos = QtWidgets.QTableWidget(0, 2)
        self.videos.setHorizontalHeaderLabels(
            [self.tr("Video"), self.tr("Output name (editable)")]
        )
        self.videos.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.videos.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.videos.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.videos.setFixedHeight(125)
        videos_layout.addWidget(self.videos)
        video_buttons = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton(self.tr("Add Videos…"))
        self.remove_button = QtWidgets.QPushButton(self.tr("Remove Selected"))
        self.add_button.clicked.connect(self._choose_videos)
        self.remove_button.clicked.connect(self._remove_videos)
        video_buttons.addWidget(self.add_button)
        video_buttons.addWidget(self.remove_button)
        video_buttons.addStretch()
        videos_layout.addLayout(video_buttons)
        form.addWidget(videos_group)

        sampling = QtWidgets.QGroupBox(self.tr("2. Frames from each video"))
        sampling_layout = QtWidgets.QVBoxLayout(sampling)
        count_row = QtWidgets.QHBoxLayout()
        self.amount_mode = QtWidgets.QComboBox()
        self.amount_mode.addItems([self.tr("Percentage"), self.tr("Number of frames")])
        self.percentage = QtWidgets.QDoubleSpinBox()
        self.percentage.setRange(0.01, 100)
        self.percentage.setDecimals(2)
        self.percentage.setValue(100)
        self.percentage.setSuffix(" %")
        self.percentage.setAccessibleName(self.tr("Percentage from each video"))
        self.count = QtWidgets.QSpinBox()
        self.count.setRange(1, 2_147_483_647)
        self.count.setValue(100)
        self.count.setAccessibleName(self.tr("Number of frames from each video"))
        count_row.addWidget(self.amount_mode)
        count_row.addWidget(self.percentage)
        count_row.addWidget(self.count)
        sampling_layout.addLayout(count_row)
        hint = QtWidgets.QLabel(
            self.tr(
                "100% extracts every frame. Percentages round up (at least one frame). "
                "A count larger than the video extracts all its frames."
            )
        )
        hint.setWordWrap(True)
        sampling_layout.addWidget(hint)
        self.method_group = QtWidgets.QGroupBox(self.tr("When extracting a subset"))
        method_layout = QtWidgets.QVBoxLayout(self.method_group)
        methods = QtWidgets.QHBoxLayout()
        self.even = QtWidgets.QRadioButton(
            self.tr("Evenly spaced throughout the video")
        )
        self.random = QtWidgets.QRadioButton(self.tr("Random (no duplicates)"))
        self.even.setChecked(True)
        methods.addWidget(self.even)
        methods.addWidget(self.random)
        method_layout.addLayout(methods)
        method_layout.addWidget(SamplingPreview())
        sampling_layout.addWidget(self.method_group)
        form.addWidget(sampling)

        output_group = QtWidgets.QGroupBox(self.tr("3. Output"))
        output_layout = QtWidgets.QVBoxLayout(output_group)
        output_row = QtWidgets.QHBoxLayout()
        self.output = QtWidgets.QLineEdit()
        self.output.setPlaceholderText(self.tr("Choose an existing destination folder"))
        self.output.setAccessibleName(self.tr("Output parent folder"))
        self.browse = QtWidgets.QPushButton(self.tr("Browse…"))
        self.browse.clicked.connect(self._choose_output)
        output_row.addWidget(self.output)
        output_row.addWidget(self.browse)
        output_layout.addLayout(output_row)
        self.layout_mode = QtWidgets.QComboBox()
        self.layout_mode.addItems(
            [
                self.tr("Separate folder for each video"),
                self.tr("All videos in one shared folder"),
            ]
        )
        output_layout.addWidget(self.layout_mode)
        self.output_preview = QtWidgets.QLabel()
        self.output_preview.setWordWrap(True)
        self.output_preview.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        output_layout.addWidget(self.output_preview)
        form.addWidget(output_group)
        form.addStretch()

        self.status = QtWidgets.QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setFixedHeight(72)
        self.status.setAccessibleName(self.tr("Extraction status"))
        self.status.setPlainText(
            self.tr("Ready. Add videos and choose an output folder.")
        )
        layout.addWidget(self.status)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.start = QtWidgets.QPushButton(self.tr("Extract Frames"))
        self.start.setDefault(True)
        self.close_button = QtWidgets.QPushButton(self.tr("Close"))
        self.start.clicked.connect(self._start)
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.start)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self._settings = content
        self.amount_mode.currentIndexChanged.connect(self._update_sampling)
        self.percentage.valueChanged.connect(self._update_sampling)
        self.output.textChanged.connect(self._update_preview)
        self.layout_mode.currentIndexChanged.connect(self._update_preview)
        self.videos.itemChanged.connect(self._update_preview)
        self._update_sampling()
        self._update_preview()

    def _update_sampling(self) -> None:
        percentage = self.amount_mode.currentIndex() == 0
        self.percentage.setVisible(percentage)
        self.count.setVisible(not percentage)
        self.method_group.setEnabled(not percentage or self.percentage.value() < 100)

    def _choose_videos(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            self.tr("Select MP4, AVI or FLIR CSQ videos"),
            "",
            self.tr("Videos (*.mp4 *.avi *.csq *.MP4 *.AVI *.CSQ)"),
        )
        self.add_videos([Path(path) for path in paths])

    def add_videos(self, paths: list[Path]) -> None:
        for path in paths:
            path = path.resolve()
            if path in self._videos or path.suffix.lower() not in {
                ".mp4",
                ".avi",
                ".csq",
            }:
                continue
            used = {
                item.text().casefold()
                for row in range(self.videos.rowCount())
                if (item := self.videos.item(row, 1)) is not None
            }
            base = safe_name(path.stem)
            name, number = base, 2
            while name.casefold() in used:
                name = f"{base[:90]}_{number}"
                number += 1
            row = self.videos.rowCount()
            self._videos.append(path)
            self.videos.insertRow(row)
            item = QtWidgets.QTableWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.videos.setItem(row, 0, item)
            self.videos.setItem(row, 1, QtWidgets.QTableWidgetItem(name))
        self._update_preview()

    def _remove_videos(self) -> None:
        for row in sorted(
            {index.row() for index in self.videos.selectedIndexes()}, reverse=True
        ):
            self.videos.removeRow(row)
            del self._videos[row]
        self._update_preview()

    def _choose_output(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, self.tr("Choose output parent folder"), self.output.text()
        )
        if path:
            self.output.setText(path)

    def _update_preview(self) -> None:
        item = self.videos.item(0, 1) if self.videos.rowCount() else None
        name = item.text() if item else "video"
        parent = self.output.text().strip() or self.tr("destination")
        folder = Path(parent) / "extracted_frames"
        if self.layout_mode.currentIndex() == 0:
            folder /= name
        self.output_preview.setText(
            self.tr(
                "A new extracted_frames folder (or extracted_frames_2, etc.) "
                "keeps existing files safe.\n"
                "Example: {path}\n"
                "Frame numbers start at 0. Open or reload the output folder "
                "when you are ready to annotate."
            ).format(path=folder / f"{name}_frame_000000000.png")
        )

    def _options(self) -> ExtractionOptions:
        if not self._videos:
            raise ValueError(self.tr("Add at least one MP4, AVI or CSQ video."))
        if not self.output.text().strip():
            raise ValueError(self.tr("Choose an existing output folder."))
        output = Path(self.output.text().strip()).expanduser().resolve()
        if not output.is_dir():
            raise ValueError(self.tr("Choose an existing output folder."))
        sources = []
        names: set[str] = set()
        for row, path in enumerate(self._videos):
            if not path.is_file():
                raise ValueError(
                    self.tr("Video no longer exists: {path}").format(path=path)
                )
            item = self.videos.item(row, 1)
            assert item is not None
            name = item.text().strip()
            if safe_name(name) != name:
                raise ValueError(
                    self.tr(
                        "Use a valid folder name without path separators: {name}"
                    ).format(name=name)
                )
            if name.casefold() in names:
                raise ValueError(
                    self.tr("Give each video a unique output name: {name}").format(
                        name=name
                    )
                )
            names.add(name.casefold())
            sources.append(VideoSource(path, name))
        percentage = self.amount_mode.currentIndex() == 0
        return ExtractionOptions(
            tuple(sources),
            output,
            separate_folders=self.layout_mode.currentIndex() == 0,
            percentage=percentage,
            amount=self.percentage.value() if percentage else self.count.value(),
            random=self.random.isChecked(),
            thermal_range=self.thermal_range,
            thermal_analysis=self.thermal_analysis,
        )

    def _start(self) -> None:
        try:
            options = self._options()
        except ValueError as error:
            self.status.setPlainText(str(error))
            return
        self._settings.setEnabled(False)
        self.start.setEnabled(False)
        self.close_button.setText(self.tr("Cancel Extraction"))
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setPlainText(self.tr("Starting extraction…"))
        self._thread = ExtractionThread(options, self)
        self._thread.progress.connect(self._on_progress)
        # Only allow closing once QThread has actually finished, not from run().
        self._thread.finished.connect(self._finished)
        self._thread.start()

    def _on_progress(self, value: int, message: str) -> None:
        # Video decoding/counting is indeterminate; never pretend it has stalled.
        self.status.setPlainText(
            self.tr("Batch {value}% — {message}").format(value=value, message=message)
        )

    def _finished(self) -> None:
        assert self._thread is not None
        thread = self._thread
        if thread.error:
            self.status.setPlainText(
                self.tr("Extraction failed: {error}").format(error=thread.error)
            )
        else:
            assert thread.result is not None
            result = thread.result
            title = self.tr("Cancelled") if result.cancelled else self.tr("Finished")
            if result.errors and not result.cancelled:
                title = self.tr("Finished with errors")
            message = self.tr(
                "{title}: saved {count:,} frames from {videos} completed video(s).\n"
                "Output: {output}\n"
                "Completed videos are kept; unfinished video output is discarded."
            ).format(
                title=title,
                count=result.saved,
                videos=result.completed,
                output=result.output,
            )
            if result.errors:
                message += "\n" + "\n".join(result.errors)
            self.status.setPlainText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(
            0 if thread.error or (thread.result and thread.result.cancelled) else 100
        )
        self._thread = None
        thread.deleteLater()
        self._settings.setEnabled(True)
        self.start.setEnabled(True)
        self.close_button.setEnabled(True)
        self.close_button.setText(self.tr("Close"))

    def reject(self) -> None:
        if self._thread is not None:
            self._thread.cancel.set()
            self.close_button.setEnabled(False)
            self.status.setPlainText(
                self.tr("Cancelling… Completed videos will be kept.")
            )
            return
        super().reject()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._thread is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
