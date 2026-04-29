# -*- encoding: utf-8 -*-

import html

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

from .escapable_qlist_widget import EscapableQListWidget


class UniqueLabelQListWidget(EscapableQListWidget):
    def mousePressEvent(self, event):
        super(UniqueLabelQListWidget, self).mousePressEvent(event)
        if not self.indexAt(event.pos()).isValid():
            self.clearSelection()

    def findItemByLabel(self, label):
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.UserRole) == label:  # type: ignore[attr-defined,union-attr]
                return item

    def createItemFromLabel(self, label):
        if self.findItemByLabel(label):
            raise ValueError("Item for label '{}' already exists".format(label))

        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.UserRole, label)  # type: ignore[attr-defined]
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)  # type: ignore[attr-defined]
        item.setCheckState(Qt.Checked)  # type: ignore[attr-defined]
        return item

    def setItemLabel(self, item, label, color=None):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(item.checkState() == Qt.Checked)  # type: ignore[attr-defined]
        checkbox.stateChanged.connect(
            lambda state: item.setCheckState(
                Qt.Checked if state == Qt.Checked else Qt.Unchecked  # type: ignore[attr-defined]
            )
        )
        layout.addWidget(checkbox)

        qlabel = QtWidgets.QLabel()
        if color is None:
            qlabel.setText("{}".format(label))
        else:
            qlabel.setText(
                '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                    html.escape(label), *color
                )
            )
        qlabel.setAlignment(Qt.AlignBottom)  # type: ignore[attr-defined]
        layout.addWidget(qlabel, 1)

        item.setSizeHint(widget.sizeHint())

        self.setItemWidget(item, widget)
