from Qt.QtWidgets import QTabWidget

from .rig_select import RigSelect


class RigTypeTabWidget(QTabWidget):
    def __init__(self):
        super().__init__()
        self._tabs: list[RigSelect] = []
        pass

    def create_tab(self, name: str, display_name: str | None = None):
        tab = RigSelect(name)
        self._tabs.append(tab)
        self.addTab(tab, display_name if display_name is not None else name)
        return tab

    def get_current_tab(self) -> RigSelect:
        index = self.currentIndex()
        return self._tabs[index]
