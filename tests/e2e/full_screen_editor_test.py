from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def test_f11_hides_chrome_and_restores_previous_layout(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    Image.new("RGB", (100, 100)).save(tmp_path / "a.png")
    win = main_win(file_or_dir=tmp_path)
    show_window_and_wait_for_imagedata(qtbot, win)
    win._docks.flag_dock.hide()
    qtbot.wait(10)
    chrome = [
        win.menuBar(),
        win.statusBar(),
        *win.findChildren(QtWidgets.QToolBar),
        *win.findChildren(QtWidgets.QDockWidget),
    ]
    visibility = {widget: not widget.isHidden() for widget in chrome}
    size = win.size()
    old_canvas_size = win.centralWidget().size()
    canvas = win._canvas_widgets.canvas
    qtbot.keyClick(canvas, Qt.Key.Key_F11)
    qtbot.wait(10)
    assert win._full_screen_editor_action.isChecked()
    assert not win.isFullScreen()
    assert win.size() == size
    assert all(widget.isHidden() for widget in chrome)
    assert win.centralWidget().width() > old_canvas_size.width()
    assert win.centralWidget().height() > old_canvas_size.height()
    assert win.centralWidget().geometry() == win.contentsRect()
    qtbot.keyClick(canvas, Qt.Key.Key_F11)
    qtbot.wait(10)
    assert not win._full_screen_editor_action.isChecked()
    assert {widget: not widget.isHidden() for widget in chrome} == visibility
    assert win.size() == size


def test_canvas_only_mode_survives_navigation_and_explicit_bar_show(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    for name in ("a", "b"):
        Image.new("RGB", (100, 100)).save(tmp_path / f"{name}.png")
    win = main_win(file_or_dir=tmp_path)
    show_window_and_wait_for_imagedata(qtbot, win)
    win._full_screen_editor_action.trigger()
    win._open_next_image()
    win.statusBar().show()
    win._skeleton_drawing_toolbar.show()
    win._docks.file_dock.show()
    qtbot.wait(10)
    assert Path(win._image_path).name == "b.png"
    assert win.statusBar().isHidden()
    assert win._skeleton_drawing_toolbar.isHidden()
    assert win._docks.file_dock.isHidden()
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_F11)
    assert win.statusBar().isVisible()
    assert win._skeleton_drawing_toolbar.isHidden()


def test_closing_canvas_only_mode_saves_normal_layout(
    main_win: MainWinFactory,
    qtbot: QtBot,
) -> None:
    win = main_win()
    win.show()
    qtbot.wait(10)
    win._docks.flag_dock.hide()
    expected = win.saveState()
    win._full_screen_editor_action.trigger()
    win.close()
    assert win._window_state.value("window/state") == expected
    reopened = main_win()
    reopened.show()
    qtbot.wait(10)
    assert not reopened._full_screen_editor_action.isChecked()
    assert reopened.menuBar().isVisible()
    assert reopened._docks.file_dock.isVisible()
    assert reopened._docks.flag_dock.isHidden()
