import functools
from typing import Literal
from PyQt5.QtCore import QTimer, QPointF
import imgviz
import numpy as np
import osam
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

import labelme.utils
from labelme._automation import polygon_from_mask
from labelme.shape import Shape

# TODO(unknown):
# - [maybe] Find optimal epsilon value.


CURSOR_DEFAULT = QtCore.Qt.ArrowCursor  # type: ignore[attr-defined]
CURSOR_POINT = QtCore.Qt.PointingHandCursor  # type: ignore[attr-defined]
CURSOR_DRAW = QtCore.Qt.CrossCursor  # type: ignore[attr-defined]
CURSOR_MOVE = QtCore.Qt.ClosedHandCursor  # type: ignore[attr-defined]
CURSOR_GRAB = QtCore.Qt.OpenHandCursor  # type: ignore[attr-defined]

MOVE_SPEED = 5.0


class Canvas(QtWidgets.QWidget):
    zoomRequest = QtCore.pyqtSignal(int, QtCore.QPoint)
    scrollRequest = QtCore.pyqtSignal(int, int)
    newShape = QtCore.pyqtSignal()
    selectionChanged = QtCore.pyqtSignal(list)
    shapeMoved = QtCore.pyqtSignal()
    drawingPolygon = QtCore.pyqtSignal(bool)
    vertexSelected = QtCore.pyqtSignal(bool)
    mouseMoved = QtCore.pyqtSignal(QtCore.QPointF)
    zoomRectSelected = QtCore.pyqtSignal(QtCore.QRectF)  # Signal for zoom-to-rectangle
    zoomFinished = QtCore.pyqtSignal()  # Signal to notify zoom is finished

    CREATE, EDIT = 0, 1

    # polygon, rectangle, line, or point
    _createMode = "polygon"

    _fill_drawing = False

    prevPoint: QtCore.QPointF
    prevMovePoint: QtCore.QPointF
    offsets: tuple[QtCore.QPointF, QtCore.QPointF]
    _fill_editing = False

    def fillDrawing(self):
        return self._fill_drawing

    def setFillDrawing(self, value):
        print(f"[DEBUG] setFillDrawing called with value: {value}")
        self._fill_drawing = value

    def fillEditing(self):
        return self._fill_editing

    def setFillEditing(self, value):
        print(f"[DEBUG] setFillEditing called with value: {value}")
        self._fill_editing = value

    def __init__(self, *args, **kwargs):
        self.epsilon = kwargs.pop("epsilon", 10.0)
        self.double_click = kwargs.pop("double_click", "close")
        if self.double_click not in [None, "close"]:
            raise ValueError(
                "Unexpected value for double_click event: {}".format(self.double_click)
            )
        self.num_backups = kwargs.pop("num_backups", 10)
        self._crosshair = kwargs.pop(
            "crosshair",
            {
                "polygon": False,
                "rectangle": True,
                "circle": False,
                "line": False,
                "point": False,
                "linestrip": False,
                "ai_polygon": False,
                "ai_mask": False,
            },
        )
        super(Canvas, self).__init__(*args, **kwargs)
        # Initialise local state.
        self.mode = self.EDIT
        self.shapes = []
        self.shapesBackups = []
        self.current = None
        self.selectedShapes = []  # save the selected shapes here
        self.selectedShapesCopy = []
        # self.line represents:
        #   - createMode == 'polygon': edge from last point to current
        #   - createMode == 'rectangle': diagonal line of the rectangle
        #   - createMode == 'line': the line
        #   - createMode == 'point': the point
        self.line = Shape()
        self.prevPoint = QtCore.QPointF()
        self.prevMovePoint = QtCore.QPointF()
        self.offsets = QtCore.QPointF(), QtCore.QPointF()
        self.scale = 1.0
        self.pixmap = QtGui.QPixmap()
        self.visible = {}
        self._hideBackround = False
        self.hideBackround = False
        self.hShape = None
        self.prevhShape = None
        self.hVertex = None
        self.prevhVertex = None
        self.hEdge = None
        self.prevhEdge = None
        self.movingShape = False
        self.snapping = True
        self.hShapeIsSelected = False
        self._painter = QtGui.QPainter()
        self._cursor = CURSOR_DEFAULT
        # Menus:
        # 0: right-click without selection and dragging of shapes
        # 1: right-click with selection and dragging of shapes
        self.menus = (QtWidgets.QMenu(), QtWidgets.QMenu())
        # Set widget options.
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.WheelFocus)  # type: ignore[attr-defined]

        self._ai_model_name: str = "sam2:latest"

        # --- Hold-to-add-point for polygon drawing ---
        self.hold_timer = QTimer(self)
        self.hold_timer.setInterval(200)  # 200ms = 0.2s
        self.hold_timer.timeout.connect(self.add_point_under_cursor)
        self.holding_mouse = False

        # --- Zoom to rectangle ---
        self.zoom_mode = False
        self._zoom_rect_start = None
        self._zoom_rect_end = None
        # --- Center dots toggle ---
        self.showCenterDots = False  # New property for View menu toggle

    def set_ai_model_name(self, model_name: str) -> None:
        logger.debug("Setting AI model to {!r}", model_name)
        self._ai_model_name = model_name

    def storeShapes(self):
        shapesBackup = []
        for shape in self.shapes:
            shapesBackup.append(shape.copy())
        if len(self.shapesBackups) > self.num_backups:
            self.shapesBackups = self.shapesBackups[-self.num_backups - 1 :]
        self.shapesBackups.append(shapesBackup)

    @property
    def isShapeRestorable(self):
        # We save the state AFTER each edit (not before) so for an
        # edit to be undoable, we expect the CURRENT and the PREVIOUS state
        # to be in the undo stack.
        if len(self.shapesBackups) < 2:
            return False
        return True

    def restoreShape(self):
        # This does _part_ of the job of restoring shapes.
        # The complete process is also done in app.py::undoShapeEdit
        # and app.py::loadShapes and our own Canvas::loadShapes function.
        if not self.isShapeRestorable:
            return
        self.shapesBackups.pop()  # latest

        # The application will eventually call Canvas.loadShapes which will
        # push this right back onto the stack.
        shapesBackup = self.shapesBackups.pop()
        self.shapes = shapesBackup
        self.selectedShapes = []
        for shape in self.shapes:
            shape.selected = False
        self.update()

    def enterEvent(self, ev):
        self.overrideCursor(self._cursor)

    def leaveEvent(self, ev):
        self.unHighlight()
        self.restoreCursor()

    def focusOutEvent(self, ev):
        self.restoreCursor()

    def isVisible(self, shape):  # type: ignore[override]
        return self.visible.get(shape, True)

    def drawing(self):
        return self.mode == self.CREATE

    def editing(self):
        return self.mode == self.EDIT

    def setEditing(self, value=True):
        self.mode = self.EDIT if value else self.CREATE
        if self.mode == self.EDIT:
            # CREATE -> EDIT
            self.repaint()  # clear crosshair
        else:
            # EDIT -> CREATE
            self.unHighlight()
            self.deSelectShape()

    def unHighlight(self):
        if self.hShape:
            self.hShape.highlightClear()
            self.update()
        self.prevhShape = self.hShape
        self.prevhVertex = self.hVertex
        self.prevhEdge = self.hEdge
        self.hShape = self.hVertex = self.hEdge = None

    def selectedVertex(self):
        return self.hVertex is not None

    def selectedEdge(self):
        return self.hEdge is not None

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        try:
            pos = self.transformPos(ev.localPos())
        except AttributeError:
            return

        # --- Zoom rectangle update ---
        if getattr(self, "zoom_mode", False) and self._zoom_rect_start is not None:
            self._zoom_rect_end = ev.pos()
            self.update()
            return

        self.mouseMoved.emit(pos)

        self.prevMovePoint = pos
        self.restoreCursor()

        is_shift_pressed = ev.modifiers() & QtCore.Qt.ShiftModifier  # type: ignore[attr-defined]

        # Polygon drawing.
        if self.drawing():
            if self.createMode in ["ai_polygon", "ai_mask"]:
                self.line.shape_type = "points"
            else:
                self.line.shape_type = self.createMode

            self.overrideCursor(CURSOR_DRAW)
            if not self.current:
                self.repaint()  # draw crosshair
                return

            if self.outOfPixmap(pos):
                # Don't allow the user to draw outside the pixmap.
                # Project the point to the pixmap's edges.
                pos = self.intersectionPoint(self.current[-1], pos)
            elif (
                self.snapping
                and len(self.current) > 1
                and self.createMode == "polygon"
                and self.closeEnough(pos, self.current[0])
            ):
                # Attract line to starting point and
                # colorise to alert the user.
                pos = self.current[0]
                self.overrideCursor(CURSOR_POINT)
                self.current.highlightVertex(0, Shape.NEAR_VERTEX)
            if self.createMode in ["polygon", "linestrip"]:
                self.line.points = [self.current[-1], pos]
                self.line.point_labels = [1, 1]
            elif self.createMode in ["ai_polygon", "ai_mask"]:
                self.line.points = [self.current.points[-1], pos]
                self.line.point_labels = [
                    self.current.point_labels[-1],
                    0 if is_shift_pressed else 1,
                ]
            elif self.createMode == "rectangle":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "circle":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.shape_type = "circle"
            elif self.createMode == "line":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "point":
                self.line.points = [self.current[0]]
                self.line.point_labels = [1]
                self.line.close()
            assert len(self.line.points) == len(self.line.point_labels)
            self.repaint()
            self.current.highlightClear()
            return

        # Polygon copy moving.
        if QtCore.Qt.RightButton & ev.buttons():  # type: ignore[attr-defined]
            if self.selectedShapesCopy and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapesCopy, pos)
                self.repaint()
            elif self.selectedShapes:
                self.selectedShapesCopy = [s.copy() for s in self.selectedShapes]
                self.repaint()
            return

        # Polygon/Vertex moving.
        if QtCore.Qt.LeftButton & ev.buttons():  # type: ignore[attr-defined]
            if self.selectedVertex():
                self.boundedMoveVertex(pos)
                self.repaint()
                self.movingShape = True
            elif self.selectedShapes and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapes, pos)
                self.repaint()
                self.movingShape = True
            return

        # Just hovering over the canvas, 2 possibilities:
        # - Highlight shapes
        # - Highlight vertex
        # Update shape/vertex fill and tooltip value accordingly.
        self.setToolTip(self.tr("Image"))
        for shape in reversed([s for s in self.shapes if self.isVisible(s)]):
            # Look for a nearby vertex to highlight. If that fails,
            # check if we happen to be inside a shape.
            index = shape.nearestVertex(pos, self.epsilon)
            index_edge = shape.nearestEdge(pos, self.epsilon)
            if index is not None:
                if self.selectedVertex():
                    self.hShape.highlightClear()  # type: ignore[union-attr]
                self.prevhVertex = self.hVertex = index
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge
                self.hEdge = None
                shape.highlightVertex(index, shape.MOVE_VERTEX)
                self.overrideCursor(CURSOR_POINT)
                self.setToolTip(
                    self.tr(
                        "Click & Drag to move point\n"
                        "ALT + SHIFT + Click to delete point"
                    )
                )
                self.setStatusTip(self.toolTip())
                self.update()
                break
            elif index_edge is not None and shape.canAddPoint():
                if self.selectedVertex():
                    self.hShape.highlightClear()  # type: ignore[union-attr]
                self.prevhVertex = self.hVertex
                self.hVertex = None
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge = index_edge
                self.overrideCursor(CURSOR_POINT)
                self.setToolTip(self.tr("ALT + Click to create point"))
                self.setStatusTip(self.toolTip())
                self.update()
                break
            elif shape.containsPoint(pos):
                if self.selectedVertex():
                    self.hShape.highlightClear()  # type: ignore[union-attr]
                self.prevhVertex = self.hVertex
                self.hVertex = None
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge
                self.hEdge = None
                self.setToolTip(
                    self.tr("Click & drag to move shape '%s'") % shape.label
                )
                self.setStatusTip(self.toolTip())
                self.overrideCursor(CURSOR_GRAB)
                self.update()
                break
        else:  # Nothing found, clear highlights, reset state.
            self.unHighlight()
        self.vertexSelected.emit(self.hVertex is not None)

    def addPointToEdge(self):
        shape = self.prevhShape
        index = self.prevhEdge
        point = self.prevMovePoint
        if shape is None or index is None or point is None:
            return
        shape.insertPoint(index, point)
        shape.highlightVertex(index, shape.MOVE_VERTEX)
        self.hShape = shape
        self.hVertex = index
        self.hEdge = None
        self.movingShape = True

    def removeSelectedPoint(self):
        shape = self.prevhShape
        index = self.prevhVertex
        if shape is None or index is None:
            return
        shape.removePoint(index)
        shape.highlightClear()
        self.hShape = shape
        self.prevhVertex = None
        self.movingShape = True  # Save changes

    def mousePressEvent(self, ev):
        pos: QtCore.QPointF = self.transformPos(ev.localPos())
        if getattr(self, "zoom_mode", False) and ev.button() == QtCore.Qt.LeftButton:
            self._zoom_rect_start = ev.pos()
            self._zoom_rect_end = ev.pos()
            self.update()
            return

        try:
            pos = self.transformPos(ev.localPos())
        except Exception as e:
            logger.error(f"Error in transformPos: {e}")
            return

        is_shift_pressed = ev.modifiers() & QtCore.Qt.ShiftModifier  # type: ignore[attr-defined]

        # Start hold-to-add-point timer for polygon drawing
        if (
            ev.button() == QtCore.Qt.LeftButton
            and self.drawing()
            and self.createMode == "polygon"
        ):
            self.holding_mouse = True
            self.hold_timer.start()

        if ev.button() == QtCore.Qt.LeftButton:  # type: ignore[attr-defined]
            if self.drawing():
                if self.current:
                    # Add point to existing shape.
                    if self.createMode == "polygon":
                        if len(self.line) > 1:
                            self.current.addPoint(self.line[1])
                            self.line[0] = self.current[-1]
                            if self.current.isClosed():
                                self.finalise()
                        else:
                            logger.warning("Line does not have enough points to add to polygon.")
                    elif self.createMode in ["rectangle", "circle", "line"]:
                        if len(self.current.points) == 1 and len(self.line.points) == 2:
                            self.current.points = self.line.points
                            self.finalise()
                        else:
                            logger.warning("Invalid points for rectangle/circle/line.")
                    elif self.createMode == "linestrip":
                        if len(self.line) > 1:
                            self.current.addPoint(self.line[1])
                            self.line[0] = self.current[-1]
                            if int(ev.modifiers()) == QtCore.Qt.ControlModifier:  # type: ignore[attr-defined]
                                self.finalise()
                        else:
                            logger.warning("Line does not have enough points for linestrip.")
                    elif self.createMode in ["ai_polygon", "ai_mask"]:
                        if len(self.line.points) > 1 and len(self.line.point_labels) > 1:
                            self.current.addPoint(
                                self.line.points[1],
                                label=self.line.point_labels[1],
                            )
                            self.line.points[0] = self.current.points[-1]
                            self.line.point_labels[0] = self.current.point_labels[-1]
                            if ev.modifiers() & QtCore.Qt.ControlModifier:  # type: ignore[attr-defined]
                                self.finalise()
                        else:
                            logger.warning("Line does not have enough points/labels for ai_polygon/ai_mask.")
                elif not self.outOfPixmap(pos):
                    # Create new shape.
                    self.current = Shape(
                        shape_type="points"
                        if self.createMode in ["ai_polygon", "ai_mask"]
                        else self.createMode
                    )
                    self.current.addPoint(pos, label=0 if is_shift_pressed else 1)
                    # --- Ensure crosshair appears immediately for rectangle ---
                    if self.createMode == "rectangle":
                        self.prevMovePoint = pos
                        self.repaint()
                    # --- End of change ---
                    if self.createMode == "point":
                        self.finalise()
                    elif (
                        self.createMode in ["ai_polygon", "ai_mask"]
                        and ev.modifiers() & QtCore.Qt.ControlModifier  # type: ignore[attr-defined]
                    ):
                        self.finalise()
                    else:
                        if self.createMode == "circle":
                            self.current.shape_type = "circle"
                        self.line.points = [pos, pos]
                        if (
                            self.createMode in ["ai_polygon", "ai_mask"]
                            and is_shift_pressed
                        ):
                            self.line.point_labels = [0, 0]
                        else:
                            self.line.point_labels = [1, 1]
                        self.setHiding()
                        self.drawingPolygon.emit(True)
                        self.update()
            elif self.editing():
                # Allow adding a point to an edge with no modifier
                if self.selectedEdge():
                    self.addPointToEdge()
                elif self.selectedVertex() and ev.modifiers() == (
                    QtCore.Qt.AltModifier | QtCore.Qt.ShiftModifier  # type: ignore[attr-defined]
                ):
                    self.removeSelectedPoint()

                group_mode = int(ev.modifiers()) == QtCore.Qt.ControlModifier  # type: ignore[attr-defined]
                try:
                    self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                except Exception as e:
                    logger.error(f"Error in selectShapePoint: {e}")
                self.prevPoint = pos
                self.repaint()
        elif ev.button() == QtCore.Qt.RightButton and self.editing():  # type: ignore[attr-defined]
            group_mode = int(ev.modifiers()) == QtCore.Qt.ControlModifier  # type: ignore[attr-defined]
            if not self.selectedShapes or (
                self.hShape is not None and self.hShape not in self.selectedShapes
            ):
                try:
                    self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                except Exception as e:
                    logger.error(f"Error in selectShapePoint (right click): {e}")
                self.repaint()
            self.prevPoint = pos

    def mouseReleaseEvent(self, ev):
        # Stop hold-to-add-point timer for polygon drawing
        if (
            ev.button() == QtCore.Qt.LeftButton
            and self.drawing()
            and self.createMode == "polygon"
        ):
            self.holding_mouse = False
            self.hold_timer.stop()

        if ev.button() == QtCore.Qt.RightButton:  # type: ignore[attr-defined]
            menu = self.menus[len(self.selectedShapesCopy) > 0]
            self.restoreCursor()
            if not menu.exec_(self.mapToGlobal(ev.pos())) and self.selectedShapesCopy:
                # Cancel the move by deleting the shadow copy.
                self.selectedShapesCopy = []
                self.repaint()
        elif ev.button() == QtCore.Qt.LeftButton:  # type: ignore[attr-defined]
            if self.editing():
                if (
                    self.hShape is not None
                    and self.hShapeIsSelected
                    and not self.movingShape
                ):
                    self.selectionChanged.emit(
                        [x for x in self.selectedShapes if x != self.hShape]
                    )

        if self.movingShape and self.hShape:
            index = self.shapes.index(self.hShape)
            if self.shapesBackups[-1][index].points != self.shapes[index].points:
                self.storeShapes()
                self.shapeMoved.emit()

            self.movingShape = False

        if self.zoom_mode and ev.button() == QtCore.Qt.LeftButton:
            if self._zoom_rect_start and self._zoom_rect_end:
                rect = QtCore.QRectF(self._zoom_rect_start, self._zoom_rect_end).normalized()
                if rect.width() > 10 and rect.height() > 10:
                    self.zoomRectSelected.emit(rect)  # Emit the signal for MainWindow
                    self.zoomFinished.emit()  # Notify that zoom is finished
            self._zoom_rect_start = None
            self._zoom_rect_end = None
            self.zoom_mode = False
            self.update()

    def endMove(self, copy):
        assert self.selectedShapes and self.selectedShapesCopy
        assert len(self.selectedShapesCopy) == len(self.selectedShapes)
        if copy:
            for i, shape in enumerate(self.selectedShapesCopy):
                self.shapes.append(shape)
                self.selectedShapes[i].selected = False
                self.selectedShapes[i] = shape
        else:
            for i, shape in enumerate(self.selectedShapesCopy):
                self.selectedShapes[i].points = shape.points
        self.selectedShapesCopy = []
        self.repaint()
        self.storeShapes()
        return True

    def hideBackroundShapes(self, value):
        self.hideBackround = value
        if self.selectedShapes:
            # Only hide other shapes if there is a current selection.
            # Otherwise the user will not be able to select a shape.
            self.setHiding(True)
            self.update()

    def setHiding(self, enable=True):
        self._hideBackround = self.hideBackround if enable else False

    def canCloseShape(self):
        return self.drawing() and (
            (self.current and len(self.current) > 2)
            or self.createMode in ["ai_polygon", "ai_mask"]
        )

    def mouseDoubleClickEvent(self, ev):
        if self.double_click != "close":
            return

        if (
            self.createMode == "polygon" and self.canCloseShape()
        ) or self.createMode in ["ai_polygon", "ai_mask"]:
            self.finalise()

    def selectShapes(self, shapes):
        self.setHiding()
        self.selectionChanged.emit(shapes)
        self.update()

    def selectShapePoint(self, point, multiple_selection_mode):
        """Select the first shape created which contains this point."""
        if self.selectedVertex():  # A vertex is marked for selection.
            index, shape = self.hVertex, self.hShape
            if shape is not None and index is not None:
                shape.highlightVertex(index, shape.MOVE_VERTEX)  # type: ignore[union-attr]
            else:
                logger.warning("selectShapePoint: No valid shape or vertex to highlight.")
        else:
            for shape in reversed(self.shapes):
                if self.isVisible(shape) and shape.containsPoint(point):
                    self.setHiding()
                    if shape not in self.selectedShapes:
                        if multiple_selection_mode:
                            self.selectionChanged.emit(self.selectedShapes + [shape])
                        else:
                            self.selectionChanged.emit([shape])
                        self.hShapeIsSelected = False
                    else:
                        self.hShapeIsSelected = True
                    self.calculateOffsets(point)
                    return
        self.deSelectShape()

    def calculateOffsets(self, point: QtCore.QPointF) -> None:
        left = self.pixmap.width() - 1
        right = 0
        top = self.pixmap.height() - 1
        bottom = 0
        for s in self.selectedShapes:
            rect = s.boundingRect()
            if rect.left() < left:
                left = rect.left()
            if rect.right() > right:
                right = rect.right()
            if rect.top() < top:
                top = rect.top()
            if rect.bottom() > bottom:
                bottom = rect.bottom()

        x1 = left - point.x()
        y1 = top - point.y()
        x2 = right - point.x()
        y2 = bottom - point.y()
        self.offsets = QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2)
        self.offsets = QtCore.QPoint(int(x1), int(y1)), QtCore.QPoint(int(x2), int(y2))

    def boundedMoveVertex(self, pos):
        index, shape = self.hVertex, self.hShape
        point = shape[index]  # type: ignore[index]
        if self.outOfPixmap(pos):
            pos = self.intersectionPoint(point, pos)
        shape.moveVertexBy(index, pos - point)  # type: ignore[union-attr]

    def boundedMoveShapes(self, shapes, pos):
        if self.outOfPixmap(pos):
            return False  # No need to move
        o1 = pos + self.offsets[0]
        if self.outOfPixmap(o1):
            pos -= QtCore.QPointF(min(0, o1.x()), min(0, o1.y()))
        o2 = pos + self.offsets[1]
        if self.outOfPixmap(o2):
            pos += QtCore.QPointF(
                min(0, self.pixmap.width() - o2.x()),
                min(0, self.pixmap.height() - o2.y()),
            )
        # XXX: The next line tracks the new position of the cursor
        # relative to the shape, but also results in making it
        # a bit "shaky" when nearing the border and allows it to
        # go outside of the shape's area for some reason.
        # self.calculateOffsets(self.selectedShapes, pos)
        dp = pos - self.prevPoint
        if dp:
            for shape in shapes:
                shape.moveBy(dp)
            self.prevPoint = pos
            return True
        return False

    def deSelectShape(self):
        if self.selectedShapes:
            self.setHiding(False)
            self.selectionChanged.emit([])
            self.hShapeIsSelected = False
            self.update()

    def deleteSelected(self):
        deleted_shapes = []
        if self.selectedShapes:
            for shape in self.selectedShapes:
                self.shapes.remove(shape)
                deleted_shapes.append(shape)
            self.storeShapes()
            self.selectedShapes = []
            self.update()
        return deleted_shapes

    def deleteShape(self, shape):
        if shape in self.selectedShapes:
            self.selectedShapes.remove(shape)
        if shape in self.shapes:
            self.shapes.remove(shape)
        self.storeShapes()
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if not self.pixmap:
            return super(Canvas, self).paintEvent(event)

        p = self._painter
        p.begin(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.HighQualityAntialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        p.scale(self.scale, self.scale)
        p.translate(self.offsetToCenter())

        p.drawPixmap(0, 0, self.pixmap)

        p.scale(1 / self.scale, 1 / self.scale)

        # draw crosshair
        if (
            (self.createMode == "rectangle" and self.drawing() and self.prevMovePoint and not self.outOfPixmap(self.prevMovePoint))
            or (self._crosshair[self.createMode] and self.drawing() and self.prevMovePoint and not self.outOfPixmap(self.prevMovePoint))
        ):
            if self.createMode == "rectangle":
                pen = QtGui.QPen(QtGui.QColor(0, 0, 0))
                pen.setStyle(QtCore.Qt.DotLine)
                pen.setWidth(2)  # Thicker crosshair lines
                p.setPen(pen)
            else:
                p.setPen(QtGui.QColor(0, 0, 0))
            p.drawLine(
                0,
                int(self.prevMovePoint.y() * self.scale),
                self.width() - 1,
                int(self.prevMovePoint.y() * self.scale),
            )
            p.drawLine(
                int(self.prevMovePoint.x() * self.scale),
                0,
                int(self.prevMovePoint.x() * self.scale),
                self.height() - 1,
            )

        Shape.scale = self.scale
        for shape in self.shapes:
            if (shape.selected or not self._hideBackround) and self.isVisible(shape):
                # Set fill for editing mode
                if self.editing():
                    shape.fill = self.fillEditing()
                else:
                    shape.fill = shape.selected or shape == self.hShape
                shape.paint(p)
        if self.current:
            self.current.paint(p)
            assert len(self.line.points) == len(self.line.point_labels)
            self.line.paint(p)
        if self.selectedShapesCopy:
            for s in self.selectedShapesCopy:
                s.paint(p)

        if not self.current:
            p.end()
            # Draw green center dots for rectangles and polygons if toggled on
            if self.showCenterDots:
                overlay_painter = QtGui.QPainter(self)
                overlay_painter.setRenderHint(QtGui.QPainter.Antialiasing)
                overlay_painter.setRenderHint(QtGui.QPainter.HighQualityAntialiasing)
                overlay_painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
                overlay_painter.scale(self.scale, self.scale)
                overlay_painter.translate(self.offsetToCenter())
                green_brush = QtGui.QBrush(QtGui.QColor(210, 210, 0))
                dot_radius = 3  # Increased dot size
                for shape in self.shapes:
                    # Draw center dot for all rectangles and polygons, regardless of visibility
                    if shape.shape_type in ["rectangle", "polygon"] and len(shape.points) > 0:
                        xs = [pt.x() for pt in shape.points]
                        ys = [pt.y() for pt in shape.points]
                        cx = sum(xs) / len(xs)
                        cy = sum(ys) / len(ys)
                        overlay_painter.setBrush(green_brush)
                        overlay_painter.setPen(QtCore.Qt.NoPen)
                        overlay_painter.drawEllipse(QtCore.QPointF(cx, cy), dot_radius, dot_radius)
                overlay_painter.end()
            # Draw zoom rectangle overlay if in zoom mode
            if self.zoom_mode and self._zoom_rect_start and self._zoom_rect_end:
                overlay_painter = QtGui.QPainter(self)
                overlay_painter.setPen(QtGui.QPen(QtGui.QColor(0, 120, 215, 180), 2, QtCore.Qt.DashLine))
                overlay_painter.setBrush(QtCore.Qt.NoBrush)
                overlay_painter.drawRect(QtCore.QRectF(self._zoom_rect_start, self._zoom_rect_end))
                overlay_painter.end()
            return

        if (
            self.createMode == "polygon"
            and self.fillDrawing()
            and len(self.current.points) >= 2
        ):
            drawing_shape = self.current.copy()
            if drawing_shape.fill_color.getRgb()[3] == 0:
                logger.warning(
                    "fill_drawing=true, but fill_color is transparent,"
                    " so forcing to be opaque."
                )
                drawing_shape.fill_color.setAlpha(64)
            drawing_shape.addPoint(self.line[1])

        if self.createMode not in ["ai_polygon", "ai_mask"]:
            p.end()
            # Draw zoom rectangle overlay if in zoom mode
            if self.zoom_mode and self._zoom_rect_start and self._zoom_rect_end:
                overlay_painter = QtGui.QPainter(self)
                overlay_painter.setPen(QtGui.QPen(QtGui.QColor(0, 120, 215, 180), 2, QtCore.Qt.DashLine))
                overlay_painter.setBrush(QtCore.Qt.NoBrush)
                overlay_painter.drawRect(QtCore.QRectF(self._zoom_rect_start, self._zoom_rect_end))
                overlay_painter.end()
            return

        drawing_shape = self.current.copy()
        drawing_shape.addPoint(
            point=self.line.points[1],
            label=self.line.point_labels[1],
        )
        _update_shape_with_sam(
            sam=_get_ai_model(model_name=self._ai_model_name),
            pixmap=self.pixmap,
            shape=drawing_shape,
            createMode=self.createMode,
        )
        drawing_shape.fill = self.fillDrawing()
        drawing_shape.selected = True
        drawing_shape.paint(p)
        p.end()

    def transformPos(self, point: QtCore.QPointF) -> QtCore.QPointF:
        # Draw zoom rectangle overlay if in zoom mode
        if self.zoom_mode and self._zoom_rect_start and self._zoom_rect_end:
            overlay_painter = QtGui.QPainter(self)
            overlay_painter.setPen(QtGui.QPen(QtGui.QColor(0, 120, 215, 180), 2, QtCore.Qt.DashLine))
            overlay_painter.setBrush(QtCore.Qt.NoBrush)
            overlay_painter.drawRect(QtCore.QRectF(self._zoom_rect_start, self._zoom_rect_end))
            overlay_painter.end()

    def zoomToRect(self, rect):
        # Convert widget rect to image coordinates
        if self.pixmap is None or self.pixmap.isNull():
            return
        s = self.scale
        offset = self.offsetToCenter()
        x1 = (rect.left() / s) - offset.x()
        y1 = (rect.top() / s) - offset.y()
        x2 = (rect.right() / s) - offset.x()
        y2 = (rect.bottom() / s) - offset.y()
        img_rect = QtCore.QRectF(x1, y1, x2 - x1, y2 - y1).normalized()
        if img_rect.width() < 1 or img_rect.height() < 1:
            return
        # Calculate new scale
        w, h = self.width(), self.height()
        scale_x = w / img_rect.width()
        scale_y = h / img_rect.height()
        new_scale = min(scale_x, scale_y)
        self.scale = new_scale
        # Center the selected area
        cx = (img_rect.left() + img_rect.right()) / 2
        cy = (img_rect.top() + img_rect.bottom()) / 2
        px = self.pixmap.width() / 2
        py = self.pixmap.height() / 2
        dx = cx - px
        dy = cy - py
        # Optionally, you can implement panning here if needed
        self.update()

    def transformPos(self, point):
        """Convert from widget-logical coordinates to painter-logical ones."""
        return point / self.scale - self.offsetToCenter()

    def offsetToCenter(self) -> QtCore.QPointF:
        s = self.scale
        area = super(Canvas, self).size()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        aw, ah = area.width(), area.height()
        x = (aw - w) / (2 * s) if aw > w else 0
        y = (ah - h) / (2 * s) if ah > h else 0
        return QtCore.QPointF(x, y)

    def outOfPixmap(self, p):
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w - 1 and 0 <= p.y() <= h - 1)

    def finalise(self):
        assert self.current
        if self.createMode in ["ai_polygon", "ai_mask"]:
            _update_shape_with_sam(
                sam=_get_ai_model(model_name=self._ai_model_name),
                pixmap=self.pixmap,
                shape=self.current,
                createMode=self.createMode,
            )
        self.current.close()

        self.shapes.append(self.current)
        self.storeShapes()
        self.current = None
        self.setHiding(False)
        self.newShape.emit()
        self.update()

    def closeEnough(self, p1, p2):
        # d = distance(p1 - p2)
        # m = (p1-p2).manhattanLength()
        # print "d %.2f, m %d, %.2f" % (d, m, d - m)
        # divide by scale to allow more precision when zoomed in
        return labelme.utils.distance(p1 - p2) < (self.epsilon / self.scale)

    def intersectionPoint(self, p1, p2):
        # Cycle through each image edge in clockwise fashion,
        # and find the one intersecting the current line segment.
        # http://paulbourke.net/geometry/lineline2d/
        size = self.pixmap.size()
        points = [
            (0, 0),
            (size.width() - 1, 0),
            (size.width() - 1, size.height() - 1),
            (0, size.height() - 1),
        ]
        # x1, y1 should be in the pixmap, x2, y2 should be out of the pixmap
        x1 = min(max(p1.x(), 0), size.width() - 1)
        y1 = min(max(p1.y(), 0), size.height() - 1)
        x2, y2 = p2.x(), p2.y()
        d, i, (x, y) = min(self.intersectingEdges((x1, y1), (x2, y2), points))
        x3, y3 = points[i]
        x4, y4 = points[(i + 1) % 4]
        if (x, y) == (x1, y1):
            # Handle cases where previous point is on one of the edges.
            if x3 == x4:
                return QtCore.QPointF(x3, min(max(0, y2), max(y3, y4)))
            else:  # y3 == y4
                return QtCore.QPointF(min(max(0, x2), max(x3, x4)), y3)
        return QtCore.QPointF(x, y)

    def intersectingEdges(self, point1, point2, points):
        """Find intersecting edges.

        For each edge formed by `points', yield the intersection
        with the line segment `(x1,y1) - (x2,y2)`, if it exists.
        Also return the distance of `(x2,y2)' to the middle of the
        edge along with its index, so that the one closest can be chosen.
        """
        (x1, y1) = point1
        (x2, y2) = point2
        for i in range(4):
            x3, y3 = points[i]
            x4, y4 = points[(i + 1) % 4]
            denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
            nua = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
            nub = (x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)
            if denom == 0:
                # This covers two cases:
                #   nua == nub == 0: Coincident
                #   otherwise: Parallel
                continue
            ua, ub = nua / denom, nub / denom
            if 0 <= ua <= 1 and 0 <= ub <= 1:
                x = x1 + ua * (x2 - x1)
                y = y1 + ua * (y2 - y1)
                m = QtCore.QPointF((x3 + x4) / 2, (y3 + y4) / 2)
                d = labelme.utils.distance(m - QtCore.QPointF(x2, y2))
                yield d, i, (x, y)

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        if self.pixmap:
            return self.scale * self.pixmap.size()
        return super(Canvas, self).minimumSizeHint()

    def wheelEvent(self, ev):
        mods = ev.modifiers()
        delta = ev.angleDelta()
        if QtCore.Qt.ControlModifier == int(mods):  # type: ignore[attr-defined]
            # with Ctrl/Command key
            # zoom
            self.zoomRequest.emit(delta.y(), ev.pos())
        else:
            # scroll
            self.scrollRequest.emit(delta.x(), QtCore.Qt.Horizontal)  # type: ignore[attr-defined]
            self.scrollRequest.emit(delta.y(), QtCore.Qt.Vertical)  # type: ignore[attr-defined]
        ev.accept()

    def moveByKeyboard(self, offset):
        if self.selectedShapes:
            self.boundedMoveShapes(self.selectedShapes, self.prevPoint + offset)
            self.repaint()
            self.movingShape = True

    def keyPressEvent(self, ev):
        modifiers = ev.modifiers()
        key = ev.key()
        if self.drawing():
            if key == QtCore.Qt.Key_Escape and self.current:  # type: ignore[attr-defined]
                self.current = None
                self.drawingPolygon.emit(False)
                self.update()
            elif key == QtCore.Qt.Key_Return and self.canCloseShape():  # type: ignore[attr-defined]
                self.finalise()
            elif modifiers == QtCore.Qt.AltModifier:  # type: ignore[attr-defined]
                self.snapping = False
        elif self.editing():
            if key == QtCore.Qt.Key_Up:  # type: ignore[attr-defined]
                self.moveByKeyboard(QtCore.QPointF(0.0, -MOVE_SPEED))
            elif key == QtCore.Qt.Key_Down:  # type: ignore[attr-defined]
                self.moveByKeyboard(QtCore.QPointF(0.0, MOVE_SPEED))
            elif key == QtCore.Qt.Key_Left:  # type: ignore[attr-defined]
                self.moveByKeyboard(QtCore.QPointF(-MOVE_SPEED, 0.0))
            elif key == QtCore.Qt.Key_Right:  # type: ignore[attr-defined]
                self.moveByKeyboard(QtCore.QPointF(MOVE_SPEED, 0.0))

    def keyReleaseEvent(self, ev):
        modifiers = ev.modifiers()
        if self.drawing():
            if int(modifiers) == 0:
                self.snapping = True
        elif self.editing():
            if self.movingShape and self.selectedShapes:
                index = self.shapes.index(self.selectedShapes[0])
                if self.shapesBackups[-1][index].points != self.shapes[index].points:
                    self.storeShapes()
                    self.shapeMoved.emit()

                self.movingShape = False

    def setLastLabel(self, text, flags):
        assert text
        self.shapes[-1].label = text
        self.shapes[-1].flags = flags
        self.shapesBackups.pop()
        self.storeShapes()
        return self.shapes[-1]

    def undoLastLine(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.current.restoreShapeRaw()
        if self.createMode in ["polygon", "linestrip"]:
            self.line.points = [self.current[-1], self.current[0]]
        elif self.createMode in ["rectangle", "line", "circle"]:
            self.current.points = self.current.points[0:1]
        elif self.createMode == "point":
            self.current = None
        self.drawingPolygon.emit(True)

    def undoLastPoint(self):
        if not self.current or self.current.isClosed():
            return
        self.current.popPoint()
        if len(self.current) > 0:
            self.line[0] = self.current[-1]
        else:
            self.current = None
            self.drawingPolygon.emit(False)
        self.update()

    def loadPixmap(self, pixmap, clear_shapes=True):
        self.pixmap = pixmap
        if clear_shapes:
            self.shapes = []
        self.update()

    def loadShapes(self, shapes, replace=True):
        if replace:
            self.shapes = list(shapes)
        else:
            self.shapes.extend(shapes)
        self.storeShapes()
        self.current = None
        self.hShape = None
        self.hVertex = None
        self.hEdge = None
        self.update()

    def setShapeVisible(self, shape, value):
        self.visible[shape] = value
        self.update()

    def overrideCursor(self, cursor):
        self.restoreCursor()
        self._cursor = cursor
        QtWidgets.QApplication.setOverrideCursor(cursor)

    def restoreCursor(self):
        QtWidgets.QApplication.restoreOverrideCursor()

    def resetState(self):
        self.restoreCursor()
        self.pixmap = None  # type: ignore[assignment]
        self.shapesBackups = []
        self.update()

    def add_point_under_cursor(self):
        if not self.holding_mouse or not self.drawing() or self.createMode != "polygon":
            return
        global_pos = QtGui.QCursor.pos()
        # Use QPointF for floating point precision
        widget_pos = self.mapFromGlobal(global_pos)
        if hasattr(widget_pos, 'x') and hasattr(widget_pos, 'y'):
            widget_posf = QtCore.QPointF(widget_pos.x(), widget_pos.y())
        else:
            widget_posf = widget_pos  # Already QPointF
        pos = self.transformPos(widget_posf)
        # Round to 2 decimal places if you want, or just keep as float
        pos = QtCore.QPointF(round(pos.x(), 2), round(pos.y(), 2))
        if self.current:
            self.current.addPoint(pos)
            self.line[0] = self.current[-1]
            self.update()

    @property
    def createMode(self):
        return self._createMode

    @createMode.setter
    def createMode(self, value):
        self._createMode = value

    def setShowCenterDots(self, value: bool):
        self.showCenterDots = value
        self.update()


def _update_shape_with_sam(
    sam: osam.types.Model,
    pixmap: QtGui.QPixmap,
    shape: Shape,
    createMode: Literal["ai_polygon", "ai_mask"],
) -> None:
    if createMode not in ["ai_polygon", "ai_mask"]:
        raise ValueError(
            f"createMode must be 'ai_polygon' or 'ai_mask', not {createMode}"
        )

    image_embedding: osam.types.ImageEmbedding = _compute_image_embedding(
        sam=sam, pixmap=pixmap
    )

    response: osam.types.GenerateResponse = osam.apis.generate(
        osam.types.GenerateRequest(
            model=sam.name,
            image_embedding=image_embedding,
            prompt=osam.types.Prompt(
                points=[[point.x(), point.y()] for point in shape.points],
                point_labels=shape.point_labels,
            ),
        )
    )
    if not response.annotations:
        logger.warning("No annotations returned by model {!r}", sam)
        return

    if createMode == "ai_mask":
        y1: int
        x1: int
        y2: int
        x2: int
        if response.annotations[0].bounding_box is None:
            y1, x1, y2, x2 = imgviz.instances.mask_to_bbox(
                [response.annotations[0].mask]
            )[0].astype(int)
        else:
            y1 = response.annotations[0].bounding_box.ymin
            x1 = response.annotations[0].bounding_box.xmin
            y2 = response.annotations[0].bounding_box.ymax
            x2 = response.annotations[0].bounding_box.xmax
        shape.setShapeRefined(
            shape_type="mask",
            points=[QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2)],
            point_labels=[1, 1],
            mask=response.annotations[0].mask[y1 : y2 + 1, x1 : x2 + 1],
        )
    elif createMode == "ai_polygon":
        points = polygon_from_mask.compute_polygon_from_mask(
            mask=response.annotations[0].mask
        )
        if len(points) < 2:
            return
        shape.setShapeRefined(
            shape_type="polygon",
            points=[QtCore.QPointF(point[0], point[1]) for point in points],
            point_labels=[1] * len(points),
        )


@functools.lru_cache(maxsize=1)
def _get_ai_model(model_name: str) -> osam.types.Model:
    return osam.apis.get_model_type_by_name(name=model_name)()


def _compute_image_embedding(
    sam: osam.types.Model, pixmap: QtGui.QPixmap
) -> osam.types.ImageEmbedding:
    return __compute_image_embedding(sam=sam, pixmap=_QPixmapForLruCache(pixmap))


class _QPixmapForLruCache(QtGui.QPixmap):
    def __hash__(self) -> int:
        qimage: QtGui.QImage = self.toImage()
        bits = qimage.constBits()
        if bits is None:
            return hash(None)
        return hash(bits.asstring(qimage.sizeInBytes()))

    def __eq__(self, other) -> bool:
        if not isinstance(other, _QPixmapForLruCache):
            return False
        return self.__hash__() == other.__hash__()


@functools.lru_cache(maxsize=3)
def __compute_image_embedding(
    sam: osam.types.Model, pixmap: _QPixmapForLruCache
) -> osam.types.ImageEmbedding:
    logger.debug("Computing image embeddings for model {!r}", sam.name)
    image: np.ndarray = labelme.utils.img_qt_to_arr(pixmap.toImage())
    return sam.encode_image(image=imgviz.asrgb(image))
