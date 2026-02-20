from Qt import QtCore
from Qt.QtGui import QStandardItem, QStandardItemModel
from Qt.QtWidgets import QListView, QWidget


class TestSelectList(QListView):
    def __init__(self):
        super().__init__()

        self.item_model = QStandardItemModel(self)
        self.setModel(self.item_model)
        self.setSelectionMode(QListView.SingleSelection)
        self.setSpacing(2)
        self.populate_tests()

    def populate_tests(self):
        tests = [
            "Mr. Yoon",
            "Goon",
            "Mr. Wichman",
        ]
        for test in tests:
            self.add_item(test)

    def add_item(self, label: str):
        item = QStandardItem(label)
        item.setEditable(False)
        item.setSelectable(False)
        item.setCheckable(True)
        item.setCheckState(QtCore.Qt.CheckState.Checked)
        self.item_model.appendRow(item)
