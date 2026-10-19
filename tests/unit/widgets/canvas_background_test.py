import pytest
from PySide6 import QtGui
from pytestqt.qtbot import QtBot

from labelme._widgets.canvas import Canvas


@pytest.mark.parametrize("with_image", [False, True])
@pytest.mark.parametrize("scale", [0.5, 1.0, 2.0])
def test_canvas_background_switches_without_changing_image_pixels(
    qtbot: QtBot, with_image: bool, scale: float
) -> None:
    canvas = Canvas()
    qtbot.addWidget(canvas)
    canvas.resize(200, 160)
    image_colour = QtGui.QColor(37, 53, 71)
    if with_image:
        pixmap = QtGui.QPixmap(40, 20)
        pixmap.fill(image_colour)
        canvas.load_pixmap(pixmap)
    else:
        canvas.setEnabled(False)
    canvas.scale = scale
    original = canvas.pixmap.toImage()
    canvas.show()
    qtbot.waitExposed(canvas)
    assert canvas.grab().toImage().pixelColor(0, 0) == QtGui.QColor("white")

    for black, colour in ((True, "black"), (False, "white")):
        canvas.set_black_background(black)
        rendered = canvas.grab().toImage()
        assert rendered.pixelColor(0, 0) == QtGui.QColor(colour)
        assert rendered.pixelColor(
            rendered.width() - 1, rendered.height() - 1
        ) == QtGui.QColor(colour)
        assert canvas.pixmap.toImage() == original
        if with_image:
            assert (
                rendered.pixelColor(rendered.width() // 2, rendered.height() // 2)
                == image_colour
            )
