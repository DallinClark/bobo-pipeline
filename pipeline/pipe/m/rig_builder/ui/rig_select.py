from Qt import QtCore
from Qt.QtGui import QStandardItem, QStandardItemModel
from Qt.QtWidgets import QHBoxLayout, QListView, QWidget

from ....db.sgaadb import SGaaDB


class RigItem(QStandardItem):
    def __init__(self, name: str, display_name: str, use_display_name: bool = False):
        super().__init__(display_name if use_display_name else name)
        self.setEditable(False)
        self.setSelectable(True)
        self.setData(name, QtCore.Qt.UserRole)


class RigSelectList(QListView):
    def __init__(self):
        super().__init__()
        self.item_model = QStandardItemModel(self)
        self.setModel(self.item_model)
        self.setSelectionMode(QListView.SingleSelection)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setSpacing(2)

    def add_item(self, name: str, display_name: str):
        item = RigItem(name, display_name)
        self.item_model.appendRow(item)


class RigSelect(QWidget):
    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.name = name
        self.setup_ui()
        pass

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        self.setMinimumSize(32, 28)
        self.setLayout(main_layout)

        self.rig_panel = RigSelectList()
        main_layout.addWidget(self.rig_panel)

        self.variant_panel = RigSelectList()
        main_layout.addWidget(self.variant_panel)

        pass

    def populate_rigs(self, database: SGaaDB, type: str):
        rig_names = database.get_asset_name_list_by_type([type])
        rig_display_names = database.get_asset_display_name_list_by_type([type])
        for rig_name, rig_display_name in zip(rig_names, rig_display_names):
            self.rig_panel.add_item(rig_name, rig_display_name)
        self.select_first_item()

    def select_first_item(self):
        if self.rig_panel.item_model.rowCount() > 0:
            first_index = self.rig_panel.item_model.index(0, 0)
            self.rig_panel.setCurrentIndex(first_index)

    def get_selected_rig(self) -> str | None:
        index = self.rig_panel.currentIndex()
        if not index.isValid():
            return None
        return index.data(QtCore.Qt.UserRole)

    def get_rig_type(self) -> str:
        return self.name
