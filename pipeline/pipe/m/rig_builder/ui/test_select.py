from typing import Sequence

from Qt import QtCore
from Qt.QtGui import QStandardItem, QStandardItemModel
from Qt.QtWidgets import QListView

from ..test import RIG_BUILD_TESTS, RigBuildTest


class TestItem(QStandardItem):
    def __init__(self, test: RigBuildTest):
        super().__init__(test.name)
        self.test = test
        self.setEditable(False)
        self.setSelectable(False)
        self.setCheckable(True)
        self.setCheckState(QtCore.Qt.CheckState.Checked)

    def run(self):
        self.test.run()
        pass


class TestSelectList(QListView):
    def __init__(self):
        super().__init__()
        self.setResizeMode(QListView.Adjust)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.item_model = QStandardItemModel(self)
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

    def run_tests(self):
        for test_item in self.test_items:
            test_item.run()
