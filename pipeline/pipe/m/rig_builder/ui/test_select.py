from Qt import QtCore
from Qt.QtGui import QStandardItem, QStandardItemModel
from Qt.QtWidgets import QListView


class TestSelectList(QListView):
    def __init__(self):
        super().__init__()
        self.setResizeMode(QListView.Adjust)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.item_model = QStandardItemModel(self)
        self.setModel(self.item_model)
        self.setSelectionMode(QListView.SingleSelection)
        self.setSpacing(2)
        self.populate_tests()

    def populate_tests(self):
        tests = [
            "geometry set",
            "control set",
            "no visible joints without shapes",
            "attributes locked",
            "no large cycles",
            "no unsupported nodes",
            "no ngskintools data",
            "frame time < 24ms",
            "no duplicate DAG names",
            "single shape per transform",
            "zeroed geometry pivots and transforms",
            "same geo vertex order and naming as last build",
            "non zeroed controls",
            "controls tagged",
            "rig nodes (ik handles etc) hidden",
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
