from __future__ import annotations

from typing import Final

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets.canvas import Canvas

from ..conftest import close_or_pause
from .conftest import drag_canvas

_DRAG_OFFSET_PX: Final[int] = 40


def _diagonal_drag_endpoints(canvas: Canvas) -> tuple[QPoint, QPoint]:
    start = QPoint(canvas.width() // 2, canvas.height() // 2)
    end = QPoint(start.x() + _DRAG_OFFSET_PX, start.y() + _DRAG_OFFSET_PX)
    return start, end


def _zoom_until_overflow(canvas: Canvas) -> None:
    # Mutates canvas.scale directly to bypass the public zoom path because
    # this fixture only needs to force overflow; if the zoom pipeline gains
    # additional side effects relevant to a test, route through that instead.
    viewport = canvas._scroll_viewport()
    assert viewport is not None
    while not (
        canvas.pixmap.width() * canvas.scale > viewport.width()
        or canvas.pixmap.height() * canvas.scale > viewport.height()
    ):
        canvas.scale *= 1.5
        canvas.adjustSize()
        canvas.update()


@pytest.mark.gui
def test_middle_drag_emits_pan_request_with_widget_pixel_delta(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    _zoom_until_overflow(canvas=canvas)

    deltas: list[QPoint] = []
    canvas.pan_request.connect(deltas.append)

    start, end = _diagonal_drag_endpoints(canvas=canvas)
    drag_canvas(
        qtbot=qtbot,
        canvas=canvas,
        button=Qt.MouseButton.MiddleButton,
        start=start,
        end=end,
    )

    assert deltas, "pan_request was not emitted during middle-drag"
    total_x = sum(p.x() for p in deltas)
    total_y = sum(p.y() for p in deltas)
    assert total_x == _DRAG_OFFSET_PX
    assert total_y == _DRAG_OFFSET_PX

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_middle_drag_no_pan_when_image_fits_viewport(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    viewport = canvas._scroll_viewport()
    assert viewport is not None
    canvas.scale = (
        min(
            viewport.width() / canvas.pixmap.width(),
            viewport.height() / canvas.pixmap.height(),
        )
        * 0.5
    )
    canvas.adjustSize()
    canvas.update()

    start, end = _diagonal_drag_endpoints(canvas=canvas)

    with qtbot.assertNotEmitted(canvas.pan_request):
        drag_canvas(
            qtbot=qtbot,
            canvas=canvas,
            button=Qt.MouseButton.MiddleButton,
            start=start,
            end=end,
        )

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("placing_points", [False, True])
def test_left_drag_empty_canvas_moves_scrollbars_without_annotations(
    qtbot: QtBot, annotated_win: MainWindow, placing_points: bool
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    canvas.load_shapes([])
    canvas.set_editing(not placing_points)
    if placing_points:
        canvas.create_mode = "point"
    viewport = canvas._scroll_viewport()
    assert viewport is not None
    canvas.scale = 2 * max(
        viewport.width() / canvas.pixmap.width(),
        viewport.height() / canvas.pixmap.height(),
    )
    canvas.adjustSize()
    qtbot.wait(10)
    bars = list(annotated_win._canvas_widgets.scroll_bars.values())
    for bar in bars:
        bar.setValue(bar.maximum() // 2)
    before = [bar.value() for bar in bars]
    start = canvas.visibleRegion().boundingRect().center()
    end = start + QPoint(_DRAG_OFFSET_PX, _DRAG_OFFSET_PX)
    with (
        qtbot.assertNotEmitted(canvas.new_shape),
        qtbot.assertNotEmitted(canvas.shape_moved),
    ):
        drag_canvas(
            qtbot=qtbot,
            canvas=canvas,
            button=Qt.MouseButton.LeftButton,
            start=start,
            end=end,
        )
    assert [bar.value() for bar in bars] == [
        value - _DRAG_OFFSET_PX for value in before
    ]
    assert not canvas.shapes
    assert canvas._pan_anchor is None
