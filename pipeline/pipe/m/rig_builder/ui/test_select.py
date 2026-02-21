from typing import Sequence

from Qt import QtCore
from Qt.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from Qt.QtWidgets import QApplication, QListView

from ..test import RIG_BUILD_TESTS, RigBuildTest


class TestSelectListModel(QStandardItemModel):
    def __init__(self, parent: QtCore.QObject | None):
        super().__init__(parent=parent)
        self.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item: QStandardItem):
        if isinstance(item, TestItem):
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                item.enable_test()
            else:
                item.disable_test()


class TestItem(QStandardItem):
    def __init__(self, test: RigBuildTest):
        super().__init__(test.name)
        self.test = test
        self.test_enabled: bool = True
        self.setEditable(False)
        self.setSelectable(False)
        self.setCheckable(True)
        self.setCheckState(QtCore.Qt.CheckState.Checked)

    def run(self):
        result = self.test.run()
        self.update_status(result)

    def update_status(self, passed: bool):
        if passed:
            self.setBackground(QBrush(QColor(21, 112, 78)))
        else:
            self.setBackground(QBrush(QColor(153, 62, 23)))

    def clear_status(self):
        self.setBackground(QBrush())

    def is_enabled(self) -> bool:
        return self.test_enabled

    def enable_test(self):
        self.test_enabled = True

    def disable_test(self):
        self.test_enabled = False


class TestSelectList(QListView):
    def __init__(self):
        super().__init__()
        self.setResizeMode(QListView.Adjust)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setMinimumSize(32, 22)
        self.item_model = TestSelectListModel(self)
        self.setModel(self.item_model)
        self.setSelectionMode(QListView.SingleSelection)
        self.setSpacing(2)

        self.test_items: list[TestItem] = []
        self.populate_tests(RIG_BUILD_TESTS)

    def populate_tests(self, tests: Sequence[RigBuildTest]):
        for test in tests:
            self.add_item(test)

    def add_item(self, test: RigBuildTest):
        item = TestItem(test)
        item.setCheckState(QtCore.Qt.CheckState.Checked)
        self.item_model.appendRow(item)
        self.test_items.append(item)

    def clear_test_status(self):
        for test_item in self.test_items:
            test_item.clear_status()

    def run_tests(self, selected_only: bool = True):
        self.clear_test_status()
        QApplication.processEvents()
        for test_item in self.test_items:
            if test_item.is_enabled():
                test_item.run()
                QApplication.processEvents()

    def enable_all_tests(self):
        for test_item in self.test_items:
            test_item.setCheckState(QtCore.Qt.CheckState.Checked)

    def disable_all_tests(self):
        for test_item in self.test_items:
            test_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
