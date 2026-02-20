from Qt.QtGui import QStandardItem, QStandardItemModel
from Qt.QtWidgets import QFrame, QHBoxLayout, QListView, QVBoxLayout, QWidget


class RigSelectList(QListView):
    def __init__(self):
        super().__init__()

        self.item_model = QStandardItemModel(self)
        self.setModel(self.item_model)
        self.setSelectionMode(QListView.SingleSelection)

        self.setSpacing(2)

    def add_item(self, label: str):
        item = QStandardItem(label)
        item.setEditable(False)
        item.setSelectable(True)
        self.item_model.appendRow(item)


class RigSelect(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setup_ui()
        self.populate_rigs()
        pass

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        self.setLayout(main_layout)

        self.rig_panel = RigSelectList()
        main_layout.addWidget(self.rig_panel)

        self.variant_panel = RigSelectList()
        main_layout.addWidget(self.variant_panel)

        pass

    def populate_rigs(self):
        rigs = [
            "Mr. Yoon",
            "Goon",
            "Mr. Wichman",
        ]
        for rig in rigs:
            self.rig_panel.add_item(rig)
        self.select_first_item()

    def select_first_item(self):
        if self.rig_panel.item_model.rowCount() > 0:
            first_index = self.rig_panel.item_model.index(0, 0)
            self.rig_panel.setCurrentIndex(first_index)
