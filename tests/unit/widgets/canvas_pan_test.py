from __future__ import annotations

from collections.abc import Generator

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._widgets.canvas import Canvas


@pytest.fixture()
def canvas(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> Generator[Canvas]:
    widget = Canvas()
    widget.pixmap = QtGui.QPixmap(300, 200)
    widget.resize(300, 200)
    qtbot.addWidget(widget)
    monkeypatch.setattr(widget, "_is_image_overflowing_viewport", lambda: True)
    monkeypatch.setattr(QtWidgets.QApplication, "startDragDistance", lambda: 10)
    monkeypatch.setattr(
        "labelme._widgets.canvas.download_ai_model", lambda **kwargs: True
    )
    yield widget
    widget._finish_pan()


def _event(
    canvas: Canvas, kind: QtCore.QEvent.Type, pos: QtCore.QPointF
) -> QtGui.QMouseEvent:
    moving = kind == QtCore.QEvent.Type.MouseMove
    return QtGui.QMouseEvent(
        kind,
        pos,
        QtCore.QPointF(canvas.mapToGlobal(pos.toPoint())),
        QtCore.Qt.MouseButton.NoButton if moving else QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.NoButton
        if kind == QtCore.QEvent.Type.MouseButtonRelease
        else QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
    )


def _set_mode(canvas: Canvas, mode: str) -> None:
    if mode == "skeleton":
        canvas.start_skeleton_drawing()
    elif mode != "edit":
        canvas.set_editing(False)
        canvas.create_mode = mode


@pytest.mark.parametrize("mode", ["edit", "point", "ai_points_to_shape", "skeleton"])
@pytest.mark.parametrize("move_event", [False, True])
def test_empty_drag_pans_without_creating_points(
    canvas: Canvas, qtbot: QtBot, mode: str, move_event: bool
) -> None:
    _set_mode(canvas, mode)
    start, end = QtCore.QPointF(100, 70), QtCore.QPointF(140, 100)
    deltas: list[QtCore.QPoint] = []
    canvas.pan_request.connect(deltas.append)
    with (
        qtbot.assertNotEmitted(canvas.new_shape),
        qtbot.assertNotEmitted(canvas.skeleton_node_requested),
    ):
        canvas.mousePressEvent(
            _event(canvas, QtCore.QEvent.Type.MouseButtonPress, start)
        )
        assert canvas._pending_left_pan is not None
        if move_event:
            canvas.mouseMoveEvent(_event(canvas, QtCore.QEvent.Type.MouseMove, end))
            assert canvas._pan_anchor is not None
        canvas.mouseReleaseEvent(
            _event(canvas, QtCore.QEvent.Type.MouseButtonRelease, end)
        )
    assert sum(delta.x() for delta in deltas) == 40
    assert sum(delta.y() for delta in deltas) == 30
    assert not canvas.shapes
    assert canvas._current is None
    assert canvas._pan_anchor is None
    assert canvas._pending_left_pan is None
    assert not canvas._left_button_held


@pytest.mark.parametrize("mode", ["point", "ai_points_to_shape", "skeleton"])
def test_click_with_small_jitter_places_point_at_press_position(
    canvas: Canvas, qtbot: QtBot, mode: str
) -> None:
    _set_mode(canvas, mode)
    requested: list[QtCore.QPointF] = []
    canvas.skeleton_node_requested.connect(requested.append)
    start, end = QtCore.QPointF(100, 70), QtCore.QPointF(101, 71)
    with qtbot.assertNotEmitted(canvas.pan_request):
        canvas.mousePressEvent(
            _event(canvas, QtCore.QEvent.Type.MouseButtonPress, start)
        )
        assert not canvas.shapes
        assert canvas._current is None
        assert not requested
        canvas.mouseMoveEvent(_event(canvas, QtCore.QEvent.Type.MouseMove, end))
        canvas.mouseReleaseEvent(
            _event(canvas, QtCore.QEvent.Type.MouseButtonRelease, end)
        )
    if mode == "point":
        assert len(canvas.shapes) == 1
        np.testing.assert_array_equal(canvas.shapes[0].points, [[100, 70]])
    elif mode == "ai_points_to_shape":
        assert canvas._current is not None
        assert canvas._current.points == (start,)
    else:
        assert requested == [start]


@pytest.mark.parametrize("location", [(20, 20), (50, 20), (50, 50), (16, 20)])
def test_press_on_shape_body_edge_or_vertex_does_not_pan(
    canvas: Canvas, qtbot: QtBot, location: tuple[int, int]
) -> None:
    polygon = Shape(
        shape_type="polygon",
        points=np.array([(20, 20), (90, 20), (90, 90), (20, 90)]),
        closed=True,
    )
    canvas.load_shapes([polygon])
    canvas.selection_changed.connect(
        lambda selected: setattr(canvas, "selected_shapes", selected)
    )
    start = QtCore.QPointF(*location)
    end = start + QtCore.QPointF(20, 20)
    with qtbot.assertNotEmitted(canvas.pan_request):
        canvas.mousePressEvent(
            _event(canvas, QtCore.QEvent.Type.MouseButtonPress, start)
        )
        assert canvas._pending_left_pan is None
        canvas.mouseMoveEvent(_event(canvas, QtCore.QEvent.Type.MouseMove, end))
        canvas.mouseReleaseEvent(
            _event(canvas, QtCore.QEvent.Type.MouseButtonRelease, end)
        )


def test_empty_drag_preserves_selected_shapes(canvas: Canvas, qtbot: QtBot) -> None:
    point = Shape(shape_type="point", points=np.array([[20, 20]]))
    canvas.load_shapes([point])
    canvas.selected_shapes = [point]
    backup_count = len(canvas.shape_backups)
    with (
        qtbot.assertNotEmitted(canvas.shape_moved),
        qtbot.assertNotEmitted(canvas.selection_changed),
    ):
        canvas.mousePressEvent(
            _event(canvas, QtCore.QEvent.Type.MouseButtonPress, QtCore.QPointF(100, 70))
        )
        canvas.mouseMoveEvent(
            _event(canvas, QtCore.QEvent.Type.MouseMove, QtCore.QPointF(140, 100))
        )
        canvas.mouseReleaseEvent(
            _event(
                canvas, QtCore.QEvent.Type.MouseButtonRelease, QtCore.QPointF(140, 100)
            )
        )
    assert canvas.selected_shapes == [point]
    np.testing.assert_array_equal(point.points, [[20, 20]])
    assert len(canvas.shape_backups) == backup_count


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("cancel", ["focus", "leave", "escape", "mode", "reset"])
def test_interrupted_gesture_cannot_place_a_point_on_release(
    canvas: Canvas, started: bool, cancel: str
) -> None:
    _set_mode(canvas, "point")
    start, end = QtCore.QPointF(100, 70), QtCore.QPointF(140, 100)
    canvas.mousePressEvent(_event(canvas, QtCore.QEvent.Type.MouseButtonPress, start))
    if started:
        canvas.mouseMoveEvent(_event(canvas, QtCore.QEvent.Type.MouseMove, end))
    if cancel == "focus":
        canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.Type.FocusOut))
    elif cancel == "leave":
        canvas.leaveEvent(QtCore.QEvent(QtCore.QEvent.Type.Leave))
    elif cancel == "escape":
        canvas.keyPressEvent(
            QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyPress,
                QtCore.Qt.Key.Key_Escape,
                QtCore.Qt.KeyboardModifier.NoModifier,
            )
        )
    elif cancel == "mode":
        canvas.set_editing(True)
    else:
        canvas.reset_state()
    canvas.mouseReleaseEvent(_event(canvas, QtCore.QEvent.Type.MouseButtonRelease, end))
    assert not canvas.shapes
    assert canvas._pending_left_pan is None
    assert canvas._pan_anchor is None


@pytest.mark.parametrize("started", [False, True])
def test_cancelled_pan_cannot_turn_into_dragging_a_selected_shape(
    canvas: Canvas, started: bool
) -> None:
    point = Shape(shape_type="point", points=np.array([[20, 20]]))
    canvas.load_shapes([point])
    canvas.selected_shapes = [point]
    start, end = QtCore.QPointF(100, 70), QtCore.QPointF(140, 100)
    canvas.mousePressEvent(_event(canvas, QtCore.QEvent.Type.MouseButtonPress, start))
    if started:
        canvas.mouseMoveEvent(_event(canvas, QtCore.QEvent.Type.MouseMove, end))
    canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.Type.FocusOut))
    canvas.mouseMoveEvent(_event(canvas, QtCore.QEvent.Type.MouseMove, end))
    canvas.mouseReleaseEvent(_event(canvas, QtCore.QEvent.Type.MouseButtonRelease, end))
    np.testing.assert_array_equal(point.points, [[20, 20]])
    assert canvas.selected_shapes == [point]
