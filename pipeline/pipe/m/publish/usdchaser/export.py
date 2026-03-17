from __future__ import annotations

import traceback
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import attrs
import mayaUsd.lib as mayaUsdLib  # type: ignore[import-not-found]
from pxr import Sdf, Usd

from .utils import (
    find_and_move_prim,
    make_topo_attrs_default,
    path_to_maya_dag_map,
    scale_down_geo,
    split_by_namespace,
    split_preroll,
    update_material_bindings,
)

if TYPE_CHECKING:
    from typing import Protocol

    class TimeSampleble(Protocol):
        def GetTimeSamples(self) -> list[float]: ...

        def GetNumTimeSamples(self) -> int: ...


from env_sg import DB_Config
from shared.util import get_production_path

from pipe.db import DB
from pipe.struct.timeline import Timeline
from pipe.util import log_errors


class ExportChaserMode(IntEnum):
    ANIM = 1
    CAM = 2
    CHAR = 3


@attrs.define
class ChaserArgs:
    mode: ExportChaserMode = attrs.field(converter=int)
    timeline: Optional[Timeline] = attrs.field(
        default=None,
        kw_only=True,
        converter=lambda t: Timeline.from_json(t) if t else None,
    )


class ExportChaser(mayaUsdLib.ExportChaser):
    ID: str = "lnd"

    _chaser_args: ChaserArgs
    _dag_to_usd: mayaUsdLib.DagToUsdMap
    _stage: Usd.Stage

    def __init__(self, factoryContext, *args, **kwargs) -> None:
        super(ExportChaser, self).__init__(factoryContext, *args, **kwargs)

        self._dag_to_usd = factoryContext.GetDagToUsdMap()
        self._stage = factoryContext.GetStage()
        self.job_args = factoryContext.GetJobArgs()
        self._chaser_args = ChaserArgs(**self.job_args.allChaserArgs[self.ID])

    @log_errors
    def PostExport(self) -> bool:
        if self._chaser_args.mode == ExportChaserMode.ANIM:
            self._post_export_anim()

        elif self._chaser_args.mode == ExportChaserMode.CHAR:
            self._post_export_char()

        elif self._chaser_args.mode == ExportChaserMode.CAM:
            self._post_export_cam()
        else:
            raise ValueError(
                f"{self._chaser_args.mode} is not a valid LnD chaser mode."
            )

        return True

    def _post_export_anim(self):
        assert self._chaser_args.timeline is not None
        path_dag_mapping = path_to_maya_dag_map(self._dag_to_usd)

        scale_down_geo(self._stage)
        make_topo_attrs_default(self._stage)
        layers = split_by_namespace(self._stage, "anim", path_dag_mapping)

        root_layer = self._stage.GetRootLayer()
        root_layer_path = Path(root_layer.realPath)

        conn = DB.Get(DB_Config)

        for name, layer in layers.items():
            # takes off the end number if it's a copy in maya
            base_name = ""
            if name[-1].isdigit():
                base_name = name[:-1]
            else:
                base_name = name

            rig_geo_path = Sdf.Path("/rig/geo")

            stitched_layer = split_preroll(
                layer, name, rig_geo_path, self._chaser_args.timeline
            )

            anim_prim_spec: Sdf.PrimSpec
            anim_prim_spec = Sdf.CreatePrimInLayer(
                root_layer, Sdf.Path(f"__class__/anim/{name}")
            )

            anim_prim_spec.specifier = Sdf.SpecifierOver

            reference = Sdf.Reference(
                f"./{Path(stitched_layer.realPath).relative_to(root_layer_path.parent)}",
                rig_geo_path,
            )

            anim_prim_spec.referenceList.appendedItems = [reference]

            asset = None
            relative_path_str = None
            try:
                asset = conn.get_asset_by_name(base_name)

                assert asset.asset_path
                rig_path = (
                    str(asset.asset_path).replace("\\", "/")
                    + "/publish/rig/usd/main.usd"
                )
                walk_up_len = (
                    len(root_layer_path.relative_to(get_production_path()).parts) - 1
                )

                relative_path_str = "../" * walk_up_len + rig_path
                relative_path = Sdf.Path(relative_path_str)
                if str(relative_path) not in root_layer.subLayerPaths:  # type: ignore
                    root_layer.subLayerPaths.append(str(relative_path))
                print(f"[chaser] added rig sublayer for {name}: {relative_path_str}")
            except Exception:
                print(f"[chaser] asset link failed for {name} (base={base_name})")
                print(
                    f"    asset={getattr(asset, 'asset_path', None)} rig_path={rig_path if 'rig_path' in locals() else None}"
                )
                print(
                    f"    relative_path={relative_path_str} root_layer={root_layer.realPath}"
                )
                print(traceback.format_exc())
            if name != base_name and relative_path_str:
                # Create a concrete rig instance for this namespace so the
                # class-based clips can bind to a real prim.
                character_parent = Sdf.CreatePrimInLayer(root_layer, Sdf.Path("/anim"))
                character_parent.specifier = Sdf.SpecifierOver

                instance_prim_path = Sdf.Path(f"/anim/{name}")
                instance_prim_spec = Sdf.CreatePrimInLayer(
                    root_layer, instance_prim_path
                )
                instance_prim_spec.specifier = Sdf.SpecifierDef

                rig_prim_path = Sdf.Path(f"/anim/{base_name}")
                instance_reference = Sdf.Reference(relative_path_str, rig_prim_path)
                instance_prim_spec.referenceList.appendedItems = [instance_reference]
                instance_prim_spec.inheritPathList.prependedItems = [
                    Sdf.Path(f"/__class__/anim/{name}")
                ]

    def _post_export_char(self):
        scale_down_geo(self._stage)
        update_material_bindings(self._stage, "/ROOT", "/ROOT/MODEL", "MAT_")

    def _post_export_cam(self):
        # We don't scale down the camera here because we need to import it
        # back into Maya. Instead we'll scale it down when we import it into
        # Solaris.

        new_shotCam_path = Sdf.Path("/LnD_shotCam")
        find_and_move_prim(
            self._stage.GetEditTarget().GetLayer(), "world_CTRL", new_shotCam_path
        )
        self._stage.SetDefaultPrim(self._stage.GetPrimAtPath(new_shotCam_path))
