from __future__ import annotations

import pytest

from .conftest import MainWinFactory


@pytest.mark.gui
def test_edit_menu_action_toggles_snap_to_existing_points(
    main_win: MainWinFactory,
) -> None:
    win = main_win()
    action = win._actions.snap_to_existing_points
    canvas = win._canvas_widgets.canvas

    assert action in win._menus.edit.actions()
    assert action.isCheckable()
    assert not action.isChecked()
    assert canvas._snap_to_existing_points is False

    action.trigger()

    assert action.isChecked()
    assert canvas._snap_to_existing_points is True
