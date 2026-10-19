from __future__ import annotations

import dataclasses
from collections.abc import Callable
from collections.abc import Sequence

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets


def action_title(text: str) -> str:
    """Remove Qt menu mnemonics while preserving escaped ampersands."""
    return " ".join(
        text.replace("&&", "\0").replace("&", "").replace("\0", "&").split()
    )


@dataclasses.dataclass(frozen=True)
class Command:
    title: str
    section: str
    action: QtGui.QAction | None = None
    callback: Callable[[], object] | None = None
    enabled: bool = True
    checked: bool | None = None
    keywords: str = ""

    def is_enabled(self) -> bool:
        return self.enabled and (
            self.action is None or (self.action.isEnabled() and self.action.isVisible())
        )

    def checked_state(self) -> bool | None:
        if self.action is not None and self.action.isCheckable():
            return self.action.isChecked()
        return self.checked

    def invoke(self) -> None:
        if not self.is_enabled():
            return
        if self.action is not None:
            self.action.trigger()
        elif self.callback is not None:
            self.callback()


def collect_action_commands(
    menu_bar: QtWidgets.QMenuBar,
    toolbars: Sequence[QtWidgets.QToolBar],
    *,
    exclude: QtGui.QAction,
) -> list[Command]:
    commands: list[Command] = []
    seen: set[QtGui.QAction] = {exclude}

    def visit(actions: Sequence[QtGui.QAction], section: str, enabled: bool) -> None:
        for action in actions:
            if action.isSeparator() or not action.isVisible():
                continue
            title = action_title(action.text())
            if not title:
                continue
            menu = QtWidgets.QMenu.menuInAction(action)
            if isinstance(menu, QtWidgets.QMenu):
                visit(
                    menu.actions(),
                    f"{section} › {title}" if section else title,
                    enabled and action.isEnabled(),
                )
            elif action not in seen:
                seen.add(action)
                commands.append(Command(title, section, action=action, enabled=enabled))

    visit(menu_bar.actions(), "", True)
    for toolbar in toolbars:
        if toolbar.isVisible():
            visit(
                toolbar.actions(),
                action_title(toolbar.windowTitle()),
                toolbar.isEnabled(),
            )
    return commands


class CommandPalette(QtWidgets.QDialog):
    def __init__(
        self, commands: Sequence[Command], parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Command Palette"))
        self.selected_command: Command | None = None
        self._commands = list(commands)
        self._matches: list[Command] = []

        self._search = QtWidgets.QLineEdit()
        self._search.setPlaceholderText(
            self.tr("Search commands, tools, and settings…")
        )
        self._search.setAccessibleName(self.tr("Search commands"))
        self._search.setClearButtonEnabled(True)
        self._search.installEventFilter(self)
        self._results = QtWidgets.QListWidget()
        self._results.setAccessibleName(self.tr("Matching commands"))
        self._results.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._results.setUniformItemSizes(True)
        self._results.installEventFilter(self)
        self._empty = QtWidgets.QLabel(self.tr("No matching commands"))
        self._empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        hint = QtWidgets.QLabel(
            self.tr("↑/↓ to navigate · Enter to run · Esc to close")
        )
        hint.setForegroundRole(QtGui.QPalette.ColorRole.PlaceholderText)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._results, stretch=1)
        layout.addWidget(self._empty, stretch=1)
        layout.addWidget(hint)
        self._search.textChanged.connect(self._filter)
        self._results.itemClicked.connect(self._activate_clicked)
        self._filter("")
        self.resize(
            QtCore.QSize(680, 460).boundedTo(self.screen().availableGeometry().size())
        )
        self._search.setFocus()

    def _filter(self, query: str) -> None:
        query = " ".join(query.casefold().split())
        words = query.split()

        def matches(command: Command) -> bool:
            text = f"{command.title} {command.section} {command.keywords}".casefold()
            return all(word in text for word in words)

        def rank(command: Command) -> tuple[int, str, str]:
            title = command.title.casefold()
            if title.startswith(query):
                priority = 0
            elif query in title:
                priority = 1
            elif all(word in title for word in words):
                priority = 2
            else:
                priority = 3
            return priority, title, command.section.casefold()

        self._matches = sorted(
            (command for command in self._commands if matches(command)),
            key=rank,
        )
        self._results.clear()
        for command in self._matches:
            details = [command.section]
            if command.action is not None:
                shortcuts = [
                    s.toString(QtGui.QKeySequence.SequenceFormat.NativeText)
                    for s in command.action.shortcuts()
                ]
                details.extend(shortcuts)
            checked = command.checked_state()
            if checked is not None:
                details.append(self.tr("On") if checked else self.tr("Off"))
            enabled = command.is_enabled()
            if not enabled:
                details.append(self.tr("Unavailable in the current context"))
            item = QtWidgets.QListWidgetItem(
                f"{command.title}\n{' · '.join(detail for detail in details if detail)}"
            )
            item.setSizeHint(QtCore.QSize(0, self.fontMetrics().height() * 2 + 16))
            item.setToolTip(item.text())
            if command.action is not None:
                item.setIcon(command.action.icon())
            if not enabled:
                item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self._results.addItem(item)
        self._empty.setVisible(not self._matches)
        self._results.setVisible(bool(self._matches))
        self._results.setCurrentRow(-1)
        self._move_selection(1)

    def _move_selection(self, direction: int) -> None:
        count = len(self._matches)
        if not count:
            return
        row = self._results.currentRow()
        if row < 0 and direction < 0:
            row = count
        for _ in range(count):
            row = (row + direction) % count
            if self._matches[row].is_enabled():
                self._results.setCurrentRow(row)
                return

    def _activate_current(self) -> None:
        row = self._results.currentRow()
        if row < 0 or not self._matches[row].is_enabled():
            return
        self.selected_command = self._matches[row]
        self.accept()

    def _activate_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        row = self._results.row(item)
        if row >= 0 and self._matches[row].is_enabled():
            self._results.setCurrentRow(row)
            self._activate_current()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.KeyPress and isinstance(
            event, QtGui.QKeyEvent
        ):
            if event.key() in (QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Up):
                self._move_selection(1 if event.key() == QtCore.Qt.Key.Key_Down else -1)
                return True
            if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                self._activate_current()
                return True
        return super().eventFilter(watched, event)
