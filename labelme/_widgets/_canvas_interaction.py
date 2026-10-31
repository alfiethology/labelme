from __future__ import annotations

import dataclasses
import enum
from typing import Final

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtGui import QCursor
from PySide6.QtGui import QLinearGradient
from PySide6.QtGui import QPainter
from PySide6.QtGui import QPainterPath
from PySide6.QtGui import QPen
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMenu

from .._shape import Shape
from .._shape import nearest_edge_index
from .._shape import nearest_rotation_point_index
from .._shape import nearest_vertex_index
from ._shape_render import is_hit_by_point


class HitKind(enum.Enum):
    VERTEX = "vertex"
    ROTATION_HANDLE = "rotation_handle"
    EDGE = "edge"
    BODY = "body"


@dataclasses.dataclass(frozen=True)
class HitTarget:
    kind: HitKind
    shape: Shape
    index: int | None


def find_hover_target(
    *,
    shapes: list[Shape],
    point: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
    point_size: int,
    priority_shape: Shape | None,
) -> HitTarget | None:
    candidates = _build_candidates(
        shapes=shapes,
        priority_shape=priority_shape,
    )

    # Pass 1: nearest vertex or standalone point. Candidate order only breaks
    # exact ties; a previously hovered shape must not hide a closer point.
    nearest_target: HitTarget | None = None
    nearest_distance = float("inf")
    for shape in candidates:
        if shape.shape_type == "point":
            if not is_hit_by_point(
                shape=shape,
                point=point,
                scale=scale,
                point_size=point_size,
                epsilon=epsilon,
            ):
                continue
            idx = 0
            # A standalone point is selected and dragged as a whole shape.
            target = HitTarget(kind=HitKind.BODY, shape=shape, index=None)
        else:
            idx = nearest_vertex_index(
                shape=shape, point=point, scale=scale, epsilon=epsilon
            )
            if idx is None:
                continue
            target = HitTarget(kind=HitKind.VERTEX, shape=shape, index=idx)
        distance = float(np.linalg.norm((shape.points[idx] - point) * scale))
        if distance < nearest_distance:
            nearest_target = target
            nearest_distance = distance
    if nearest_target is not None:
        return nearest_target

    # Pass 2: rotation handle proximity
    for shape in candidates:
        idx = nearest_rotation_point_index(
            shape=shape, point=point, scale=scale, epsilon=epsilon
        )
        if idx is not None:
            return HitTarget(kind=HitKind.ROTATION_HANDLE, shape=shape, index=idx)

    # Pass 3: edge proximity (only shapes that support adding a point)
    for shape in candidates:
        if not shape.can_add_point():
            continue
        idx = nearest_edge_index(shape=shape, point=point, scale=scale, epsilon=epsilon)
        if idx is not None:
            return HitTarget(kind=HitKind.EDGE, shape=shape, index=idx)

    # Pass 4: body hit
    for shape in candidates:
        hit = is_hit_by_point(
            shape=shape,
            point=point,
            scale=scale,
            point_size=point_size,
            epsilon=epsilon,
        )
        if hit:
            return HitTarget(kind=HitKind.BODY, shape=shape, index=None)

    return None


def _build_candidates(
    *,
    shapes: list[Shape],
    priority_shape: Shape | None,
) -> list[Shape]:
    candidates: list[Shape] = []
    if priority_shape is not None and priority_shape.visible:
        candidates.append(priority_shape)
    for shape in reversed(shapes):
        if not shape.visible:
            continue
        if shape is priority_shape:
            continue
        candidates.append(shape)
    return candidates


def is_within_pick_threshold(
    *,
    a: npt.NDArray[np.float64],
    b: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
) -> bool:
    return bool(np.linalg.norm(a - b) < epsilon / scale)


class CursorRole(enum.Enum):
    DEFAULT = "default"
    EDIT = "edit"
    DRAW = "draw"
    HANDLE = "handle"
    GRAB = "grab"
    MOVE = "move"


_CURSOR_SHAPE_MAP: Final[dict[CursorRole, Qt.CursorShape]] = {
    CursorRole.DEFAULT: Qt.CursorShape.ArrowCursor,
    CursorRole.EDIT: Qt.CursorShape.BitmapCursor,
    CursorRole.DRAW: Qt.CursorShape.CrossCursor,
    CursorRole.HANDLE: Qt.CursorShape.PointingHandCursor,
    CursorRole.GRAB: Qt.CursorShape.OpenHandCursor,
    CursorRole.MOVE: Qt.CursorShape.ClosedHandCursor,
}
assert set(_CURSOR_SHAPE_MAP) == set(CursorRole), (
    f"_CURSOR_SHAPE_MAP missing roles: {set(CursorRole) - set(_CURSOR_SHAPE_MAP)}"
)


def cursor_shape_for(role: CursorRole) -> Qt.CursorShape:
    return _CURSOR_SHAPE_MAP[role]


def make_edit_cursor() -> QCursor:
    # Draw at double resolution for smooth edges on both standard and HiDPI
    # displays, while keeping the compact logical size and exact tip hotspot.
    pixmap = QPixmap(30, 36)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    path = QPainterPath()
    path.moveTo(1, 1)
    path.lineTo(2, 13.8)
    path.lineTo(5.4, 10)
    path.lineTo(8, 15.8)
    path.quadTo(8.3, 16.4, 8.9, 16.1)
    path.lineTo(10, 15.55)
    path.quadTo(10.5, 15.3, 10.2, 14.75)
    path.lineTo(7.5, 9.25)
    path.lineTo(12.35, 8.95)
    path.closeSubpath()
    fill = QLinearGradient(1, 1, 10, 16)
    fill.setColorAt(0, QColor("#202733"))
    fill.setColorAt(1, QColor("#394657"))
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline = QPen(Qt.GlobalColor.white, 0.9)
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(outline)
        painter.setBrush(fill)
        painter.drawPath(path)
    finally:
        painter.end()
    return QCursor(pixmap, 1, 1)


def make_drawing_cursor() -> QCursor:
    # Keep an odd-sized cursor with an explicit central hotspot.
    size = 23
    center = size // 2
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        # Match canvas rasterization: aliased odd-width lines land half a pixel
        # below/right of their coordinates, even with an exact integer hotspot.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for color, width in ((Qt.GlobalColor.white, 3), (Qt.GlobalColor.black, 1)):
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.PenCapStyle.SquareCap)
            painter.setPen(pen)
            painter.drawLine(1, center, size - 2, center)
            painter.drawLine(center, 1, center, size - 2)
    finally:
        painter.end()
    return QCursor(pixmap, center, center)


@dataclasses.dataclass
class ContextMenuPair:
    without_selection: QMenu
    with_selection: QMenu

    def menu_for(self, *, has_selection: bool) -> QMenu:
        if has_selection:
            return self.with_selection
        return self.without_selection
