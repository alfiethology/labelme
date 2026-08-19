from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest
from PySide6 import QtWidgets

from labelme._shape import Shape

from .conftest import MainWinFactory


def _exec_clicking_role(
    role: QtWidgets.QMessageBox.ButtonRole,
) -> Callable[[QtWidgets.QMessageBox], int]:
    def _exec(msg_box: QtWidgets.QMessageBox) -> int:
        for button in msg_box.buttons():
            if msg_box.buttonRole(button) == role:
                button.click()
                return 0
        raise AssertionError(f"no button with role {role}")

    return _exec


@pytest.mark.gui
def test_confirm_deletion_defaults_to_cancel(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()

    default_role: list[QtWidgets.QMessageBox.ButtonRole] = []

    def _capture_default(msg_box: QtWidgets.QMessageBox) -> int:
        default_role.append(msg_box.buttonRole(msg_box.defaultButton()))
        return 0

    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", _capture_default)

    win._confirm_deletion(message="delete?")

    assert default_role == [QtWidgets.QMessageBox.ButtonRole.RejectRole]


@pytest.mark.gui
def test_confirm_deletion_returns_true_when_delete_clicked(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "exec",
        _exec_clicking_role(QtWidgets.QMessageBox.ButtonRole.DestructiveRole),
    )

    assert win._confirm_deletion(message="delete?") is True


@pytest.mark.gui
def test_confirm_deletion_returns_false_when_cancel_clicked(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "exec",
        _exec_clicking_role(QtWidgets.QMessageBox.ButtonRole.RejectRole),
    )

    assert win._confirm_deletion(message="delete?") is False


@pytest.mark.gui
def test_deleting_selected_points_does_not_ask_for_confirmation(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()
    canvas = win._canvas_widgets.canvas
    point = Shape(
        label="point",
        shape_type="point",
        points=np.array([[10.0, 10.0]]),
    )
    canvas.load_shapes([point])
    win.add_label(point)
    canvas.select_shapes([point])
    monkeypatch.setattr(
        win,
        "_confirm_deletion",
        lambda *args, **kwargs: pytest.fail("point deletion asked for confirmation"),
    )
    monkeypatch.setattr(win, "mark_dirty", lambda: None)

    win.delete_selected_shapes()

    assert canvas.shapes == []


@pytest.mark.gui
def test_deleting_non_point_shape_still_asks_for_confirmation(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()
    canvas = win._canvas_widgets.canvas
    rectangle = Shape(
        label="rectangle",
        shape_type="rectangle",
        points=np.array([[10.0, 10.0], [20.0, 20.0]]),
    )
    canvas.load_shapes([rectangle])
    win.add_label(rectangle)
    canvas.select_shapes([rectangle])
    confirmations: list[str] = []
    monkeypatch.setattr(
        win,
        "_confirm_deletion",
        lambda message: confirmations.append(message) or False,
    )

    win.delete_selected_shapes()

    assert len(confirmations) == 1
    assert canvas.shapes == [rectangle]
