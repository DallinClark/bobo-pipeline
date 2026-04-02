from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pipe.asset import paths_for_asset
from pipe.glui.dialogs import MessageDialog

if TYPE_CHECKING:
    from typing import Any

import maya.cmds as mc

from .publisher import Publisher
from .usdchaser import ExportChaser, ExportChaserMode

log = logging.getLogger(__name__)

CACHE_SET = "rig_geo_grp"


class RigPublisher(Publisher):
    def __init__(self) -> None:
        super().__init__(use_sg_entity=False)

    def _get_entity_list(self) -> list[str]:
        rigged_assets = self._conn.get_assets_by_tag(tags="SKD_rigged")
        return [asset.display_name for asset in rigged_assets]

    def _get_mayausd_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "chaser": [ExportChaser.ID],
            "chaserArgs": [(ExportChaser.ID, "mode", ExportChaserMode.CHAR)],
            "exportCollectionBasedBindings": True,
            "exportMaterialCollections": True,
            "legacyMaterialScope": True,
            "materialCollectionsPath": "/rig/geo",
            "shadingMode": "useRegistry",
        }

        return kwargs

    def _presave(self) -> bool:
        mc.select(CACHE_SET)
        return True

    def _get_save_path(self) -> Path | None:
        asset = self._conn.get_asset_by_display_name(self._selected_item)

        try:
            assert asset.asset_path
        except AssertionError:
            error = MessageDialog(
                self._window,
                "Error: Could not resolve the location for this asset in ShotGrid. Nothing exported",
                "Error",
            )
            error.exec_()
            return None

        rig_usd_dir = paths_for_asset(asset).rig_path / "usd"
        filename = "geo.usd"
        save_path = rig_usd_dir / filename

        return save_path
