from __future__ import annotations

import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

import maya.cmds as mc

from .publisher import Publisher
from .usdchaser import ChaserMode, ExportChaser

log = logging.getLogger(__name__)

CACHE_SET = "cache_SET"
PROP_SET = "prop_SET"
RIG_SET = "rig_SET"


class RigPublisher(Publisher):
    def __init__(self) -> None:
        super().__init__(use_sg_entity=False)

    def _get_entity_list(self) -> list[str]:
        return self._conn.get_asset_name_list(sorted=True)

    def _get_mayausd_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "chaser": [ExportChaser.ID],
            "chaserArgs": [(ExportChaser.ID, "mode", ChaserMode.CHAR)],
            "exportCollectionBasedBindings": True,
            "exportMaterialCollections": True,
            "legacyMaterialScope": True,
            "materialCollectionsPath": "/ROOT/MODEL",
            "shadingMode": "useRegistry",
        }

        return kwargs

    def _presave(self) -> bool:
        mc.select(self._selected_item + ":" + CACHE_SET)
        return True
