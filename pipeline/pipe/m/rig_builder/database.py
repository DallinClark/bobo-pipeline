from env_sg import DB_Config
from Qt import QtCore

from pipe.db import DB


class DBWorker(QtCore.QObject):
    # Signals to send data back to the main thread
    rigs_loaded = QtCore.Signal(list, list)

    def __init__(self):
        super().__init__()

    def get_asset_by_type(self, type: str) -> list[tuple[str, str]]:
        database = DB.Get(DB_Config)
        asset_names = database.get_asset_name_list_by_type([type])
        asset_display_names = database.get_asset_display_name_list_by_type([type])
        return list(zip(asset_names, asset_display_names))

    def get_rig_data(self) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        characters = self.get_asset_by_type(type="Character")
        props = self.get_asset_by_type(type="Rigged Prop")
        self.rigs_loaded.emit(characters, props)
        return (characters, props)
