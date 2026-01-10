from __future__ import annotations

import logging

from Qt import QtWidgets
from typing import TYPE_CHECKING

from pipe.glui.dialogs import DialogButtons, FilteredListDialog, MessageDialog

if TYPE_CHECKING:
    from pipe.db import DB

log = logging.getLogger(__name__)

DEPARTMENTS = ("anim", "comp", "fx", "lighting", "previs")


class HPlayblastDialog(QtWidgets.QDialog, DialogButtons):
    _conn: "DB"
    _shot_codes: list[str] | None

    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        conn: "DB",
        default_shot_code: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._shot_codes = None

        self._init_buttons(True, "Playblast", "Cancel")
        self.setWindowTitle("Houdini Playblast")

        layout = QtWidgets.QVBoxLayout(self)

        form_layout = QtWidgets.QFormLayout()
        shot_row = QtWidgets.QHBoxLayout()
        self._shot_field = QtWidgets.QLineEdit()
        if default_shot_code:
            self._shot_field.setText(default_shot_code)
        shot_row.addWidget(self._shot_field)

        self._shot_select_button = QtWidgets.QPushButton("Select Shot")
        self._shot_select_button.clicked.connect(self._select_shot)
        shot_row.addWidget(self._shot_select_button)
        form_layout.addRow("Shot", shot_row)

        self._dept_combo = QtWidgets.QComboBox()
        self._dept_combo.addItems(DEPARTMENTS)
        form_layout.addRow("Department", self._dept_combo)
        layout.addLayout(form_layout)

        self._upload_cb = QtWidgets.QCheckBox("Upload to ShotGrid (coming soon)")
        layout.addWidget(self._upload_cb)

        layout.addWidget(self.buttons)
        self.setLayout(layout)

    @property
    def shot_code(self) -> str:
        return self._shot_field.text().strip()

    @property
    def department(self) -> str:
        return self._dept_combo.currentText()

    @property
    def upload_to_shotgrid(self) -> bool:
        return self._upload_cb.isChecked()

    def _select_shot(self) -> None:
        try:
            if self._shot_codes is None:
                self._shot_codes = self._conn.get_shot_code_list(sorted=True)
        except Exception as exc:
            log.error("Failed to fetch shot list: %s", exc, exc_info=True)
            MessageDialog(
                self,
                "Could not fetch shots from ShotGrid.",
                "Playblast",
            ).exec_()
            return

        dialog = FilteredListDialog(
            self,
            self._shot_codes,
            "Select Shot",
            "Select the shot to playblast.",
            accept_button_name="Select",
        )
        if not dialog.exec_():
            return
        selection = dialog.get_selected_item()
        if selection:
            self._shot_field.setText(selection)
