from __future__ import annotations

import hmac
import json
import logging
import os
from hashlib import sha1
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib import request
from Qt.QtWidgets import QCheckBox, QWidget, QComboBox, QLabel, QHBoxLayout
from Qt.QtGui import QTextCursor, QRegExpValidator
from Qt.QtCore import QRegExp
from pipe.db import DB
from typing import Optional


if TYPE_CHECKING:
    from typing import Any, Sequence
from pipe.glui.dialogs import (
    FilteredListDialog,
    MessageDialog,
    MessageDialogCustomButtons,
)
from pipe.struct.db import Asset, SGEntity
from shared.util import get_production_path
from env import PIPEBOT_SECRET, PIPEBOT_URL

from .publisher import Publisher

try:
    from modelChecker.modelChecker_UI import UI as MCUI
except TypeError:
    # this external code throws errors when in headless mode
    MCUI = object

log = logging.getLogger(__name__)


class PublishAssetDialog(FilteredListDialog):
    _substance_only: QCheckBox
    _geo_var_widget: QWidget

    def __init__(
        self, parent: QWidget | None, items: Sequence[str], conn: Optional[DB]
    ) -> None:
        super().__init__(
            parent,
            items,
            "Publish Asset",
            "Select asset to publish",
            accept_button_name="Publish",
        )

        self._substance_only = QCheckBox(
            "Export Substance-only file? ONLY USE IF INSTRUCTED BY A LEAD"
        )
        self._layout.insertWidget(1, self._substance_only)

        self._conn = conn

        geo_var_widget = QWidget(self)
        geo_var_layout = QHBoxLayout(geo_var_widget)
        geo_var_layout.setContentsMargins(0, 0, 0, 0)
        geo_var_layout.setSpacing(0)
        geo_var_settings_widget = QWidget()
        geo_var_settings_layout = QHBoxLayout(geo_var_settings_widget)
        geo_var_label = QLabel("Geometry Variant:")
        geo_var_settings_layout.addWidget(geo_var_label, 30)

        # Editable combo box for geo variant
        self._geo_var_dropdown = QComboBox()
        self._geo_var_dropdown.setEditable(True)
        self._geo_var_dropdown.setCurrentText("default")
        pattern = QRegExp("[a-z][a-z_\d]*")
        geo_var_validator = QRegExpValidator(pattern)
        self._geo_var_dropdown.setValidator(geo_var_validator)
        geo_var_settings_layout.addWidget(self._geo_var_dropdown, 70)
        geo_var_layout.addWidget(geo_var_settings_widget, 90)
        self._layout.addWidget(geo_var_widget)

        self._populate_geo_var(None)

    def get_selected_variant(self) -> str:
        return self._geo_var_dropdown.currentText()

    @property
    def is_substance_only(self) -> bool:
        """Return whether the substance-only option is checked."""
        return self._substance_only.isChecked()

    def get_selected_item(self) -> str | None:
        selected_items = self._list_widget.selectedItems()
        if selected_items:
            return selected_items[0].text()
        return None

    def _on_item_selected(self) -> None:
        selected = self.get_selected_item()
        if self._conn and selected:
            asset = self._conn.get_asset_by_name(selected)
        else:
            return
        self._populate_geo_var(asset)

    def _populate_geo_var(self, asset: Asset | None) -> None:
        """Populate the variant selector with variants from the selected asset."""
        if asset and hasattr(asset, "geometry_variants"):
            var_set = set(asset.geometry_variants)
            var_set.add("main")
            variants = list(var_set)
        else:
            variants = []

        self._geo_var_dropdown.clear()
        self._geo_var_dropdown.addItems(variants)


class AssetPublisher(Publisher):
    _override: bool

    def __init__(self) -> None:
        super().__init__(PublishAssetDialog)

    def _prepublish(self) -> bool:
        checker = ModelChecker.get()
        self._override = False
        if not checker.check_selected():
            checker_fail_dialog = MessageDialogCustomButtons(
                self._window,
                "Error. This asset did not pass the model checker. Please "
                "ensure your model meets the requirements set by the model "
                "checker.",
                "Cannot export: Model Checker",
                has_cancel_button=True,
                ok_name="Override",
                cancel_name="Ok",
            )
            self._override = bool(checker_fail_dialog.exec_())
            if not self._override:
                cursor = QTextCursor(checker.reportOutputUI.textCursor())
                cursor.setPosition(0)
                cursor.insertHtml(
                    "<h1>Asset not exported. Please resolve model checks.</h1>"
                )
                return False
        return True

    def _get_entity_list(self) -> list[str]:
        return self._conn.get_asset_name_list(sorted=True)

    def _get_entity_from_name(self, name: str) -> SGEntity | None:
        return self._conn.get_asset_by_name(name)

    def _get_save_path(self) -> Path | None:
        dialog = cast(PublishAssetDialog, self._dialog)
        asset = cast(Asset, self._entity)
        variant_name = dialog.get_selected_variant()
        try:
            assert asset.path is not None

            if not variant_name:
                raise ValueError()

        except AssertionError:
            error = MessageDialog(
                self._window,
                "Error: No path for this Asset set in ShotGrid. Nothing exported",
                "Error",
            )
            error.exec_()
            return None

        except ValueError:
            error = MessageDialog(
                self._window,
                "Error: No variant selected. Nothing exported,",
                "Error",
            )
            error.exec_()
            return None

        if variant_name not in asset.geometry_variants:
            asset.geometry_variants.add(variant_name)
            log.info(f"Updating new geo variant: {variant_name}")
            self._conn.update_asset(asset)

        return (
            get_production_path()
            / asset.path
            / (
                asset.name
                + (f"_{variant_name}" if variant_name != "main" else "")
                + ("_SUBSTANCE" if dialog.is_substance_only else "")
                + ".usd"
            )
        )

    def _presave(self) -> bool:
        # notify webhook of override
        if self._override:
            asset = cast(Asset, self._entity)
            override_info = {
                "user": os.getlogin(),
                "asset": asset.disp_name,
                "path": str(self._publish_path),
            }
            data = bytes(json.dumps(override_info), encoding="utf-8")
            hashcheck = (
                "sha1=" + hmac.new(PIPEBOT_SECRET.encode(), data, sha1).hexdigest()
            )

            req = request.Request(
                url=PIPEBOT_URL + "/model_checker",
                data=data,
            )
            req.add_header("x-pipebot-signature", hashcheck)
            request.urlopen(req)
        return True

    def _get_mayausd_kwargs(self) -> dict[str, Any]:
        return {
            "shadingMode": "useRegistry",
        }


class ModelChecker(MCUI):
    @classmethod
    def get(cls):
        if not cls.qmwInstance or (type(cls.qmwInstance) is not cls):
            cls.qmwInstance = cls()
        return cls.qmwInstance

    def configure(self) -> None:
        self.uncheckAll()
        commands = [
            # "crossBorder",
            "hardEdges",
            "lamina",
            # "missingUVs",
            "ngons",
            "noneManifoldEdges",
            # "onBorder",
            # "selfPenetratingUVs",
            "zeroAreaFaces",
            "zeroLengthEdges",
        ]
        for cmd in commands:
            self.commandCheckBox[cmd].setChecked(True)

    def check_selected(self) -> bool:
        self.configure()
        self.sanityCheck(["Selection"], True)
        self.createReport("Selection")

        # loop and show UI if anything had an error
        diagnostics = self.contexts["Selection"]["diagnostics"]
        for error in self.commandsList.keys():
            if (error in diagnostics) and len(self.parseErrors(diagnostics[error])):
                self.show_UI()
                return False

        return True

    # Override
    def sanityCheck(self, contextsUuids, refreshSelection=True) -> None:
        """The `sanityCheck` function cannot handle transforms that do not
        have children. This catches those errors and warns the modelers."""
        try:
            super().sanityCheck(contextsUuids, refreshSelection)
        except RuntimeError as err:
            if (
                "(kInvalidParameter): Object is incompatible with this method"
                in err.args
            ):
                MessageDialog(
                    self.parent(),
                    "The model checker could not run. Please ensure that you do "
                    "not have any empty transforms.",
                    "Model Checker Failed",
                ).exec_()
            else:
                raise err
