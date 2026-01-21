from __future__ import annotations

import logging
from abc import abstractmethod
from pathlib import Path
from typing import Iterable, Optional, cast

import maya.api.OpenMaya as om
import maya.cmds as mc
import mayaUsd  # type: ignore[import-not-found]
from env_sg import DB_Config
from pxr import Sdf, Usd, UsdGeom
from shared.util import get_production_path
from timeline_marker.ui import TimelineMarker  # type: ignore[import-not-found]

from pipe.db import DB
from pipe.m.local import get_main_qt_window
from pipe.struct.db import SGEntity, Shot
from pipe.util import FileManager, log_errors

from .timeline import shot_timeline_generator

log = logging.getLogger(__name__)


class MShotFileManager(FileManager):
    MAYA_OVERRIDE = "maya_override.usd"
    FOREST_LAYOUT_NAME = "Forest_layout"
    FOREST_OVERRIDE_USD = "/groups/bobo/set/Forest_layout/maya.usd"
    shot: Shot

    def __init__(self, **kwargs) -> None:
        conn = DB.Get(DB_Config)
        window = get_main_qt_window()
        super().__init__(conn, Shot, window, versioning=True, **kwargs)

    @classmethod
    def get_stage_shape(cls) -> str:
        if ss := mc.ls(type="mayaUsdProxyShape", long=True)[0]:
            return ss
        raise RuntimeError("No USD stage found in scene")

    @classmethod
    def get_stage(cls) -> Usd.Stage:
        return mayaUsd.ufe.getStage(cls.get_stage_shape())

    @classmethod
    def _normalize_usd_path(cls, path: str) -> str:
        return path.replace("\\", "/")

    @classmethod
    def _path_has_layout_name(cls, path: str, layout_name: str) -> bool:
        parts = [part for part in cls._normalize_usd_path(path).split("/") if part]
        return layout_name in parts

    @classmethod
    def _resolve_env_usd_path(cls, layout_path: str) -> str:
        if cls._path_has_layout_name(layout_path, cls.FOREST_LAYOUT_NAME):
            return cls.FOREST_OVERRIDE_USD
        return "/".join((layout_path, "main.usd"))

    @classmethod
    def _find_root_layer_path(cls, scene_path: Path) -> Optional[Path]:
        for parent in scene_path.parents:
            candidate = parent / "maya_root.usd"
            if candidate.exists():
                return candidate
        return None

    @classmethod
    def _guard_forest_layout_before_open(cls, scene_path: Path) -> None:
        root_layer_path = cls._find_root_layer_path(scene_path)
        if not root_layer_path:
            return

        root_layer = Sdf.Layer.FindOrOpen(str(root_layer_path))
        if not root_layer:
            return

        updated = False
        new_paths: list[str] = []
        for sub_path in list(cast(Iterable[str], root_layer.subLayerPaths)):
            if cls._path_has_layout_name(
                sub_path, cls.FOREST_LAYOUT_NAME
            ) and cls._normalize_usd_path(sub_path).endswith("/main.usd"):
                if sub_path != cls.FOREST_OVERRIDE_USD:
                    new_paths.append(cls.FOREST_OVERRIDE_USD)
                    updated = True
                else:
                    new_paths.append(sub_path)
            else:
                new_paths.append(sub_path)

        if updated:
            root_layer.subLayerPaths[:] = new_paths
            root_layer.Save()

    @classmethod
    @log_errors
    def run_on_open(cls) -> None:
        """Function to run on file open via script node"""

        # save edit target layer on save
        beforeSaveId = om.MSceneMessage.addCallback(
            om.MSceneMessage.kBeforeSave,
            lambda _: MShotFileManager.get_stage().GetEditTarget().GetLayer().Save(),
        )

        # remove callback before opening a new file
        om.MSceneMessage.addCallback(
            om.MSceneMessage.kBeforeOpen,
            lambda kwargs: om.MSceneMessage.removeCallback(kwargs["ID"]),
            {"ID": beforeSaveId},
        )

        # change default render resolution
        mc.setAttr("defaultResolution.width", 1920)  # type: ignore[arg-type]
        mc.setAttr("defaultResolution.height", 1080)  # type: ignore[arg-type]
        mc.setAttr("defaultResolution.pixelAspect", 1.0)  # type: ignore[arg-type]
        mc.setAttr("defaultResolution.deviceAspectRatio", 1920 / 1080)  # type: ignore[arg-type]

        # set session USD target layer to the override layer
        try:
            shot_code = ""
            try:
                shot_code = mc.fileInfo("code", query=True)[0]
            except IndexError:
                mc.error(
                    "Could not find shot code in fileInfo! USD edit target not set"
                )
            if shot_code:
                mc.mayaUsdEditTarget(  # type: ignore[attr-defined]
                    cls.get_stage_shape(),
                    edit=True,
                    editTarget="/".join(["shot", shot_code, "set", cls.MAYA_OVERRIDE]),
                )

                conn = DB.Get(DB_Config)
                shot = conn.get_shot_by_code(shot_code)

                # Import Timeline
                frames, colors, comments = shot_timeline_generator(shot.cut_duration)
                TimelineMarker.clear()
                TimelineMarker.set(frames, colors, comments)
                mc.playbackOptions(
                    animationStartTime=frames[0],
                    animationEndTime=frames[-1],
                    minTime=frames[0],
                    maxTime=frames[-1],
                )
        except Exception:
            mc.error("Warning! Could not set edit target!")

    def _check_unsaved_changes(self) -> bool:
        if mc.file(query=True, modified=True):
            warning_response = mc.confirmDialog(
                title="Do you want to save?",
                message="The current file has not been saved. Continue anyways?",
                button=["Continue", "Cancel"],
                defaultButton="Cancel",
                cancelButton="Cancel",
                dismissString="Cancel",
            )
            if warning_response == "Cancel":
                return False
        return True

    def _generate_filename_ext(self, entity) -> tuple[str, str]:
        shot = cast(Shot, entity)
        return shot.code, "mb"

    def _open_file(self, path: Path) -> None:
        self._guard_forest_layout_before_open(path)
        mc.file(str(path), open=True, force=True)

    def _post_open_file(self, entity: SGEntity) -> None:
        """create `lndOnOpen` script node"""
        ON_OPEN_SCRIPT = "lndOnOpen"

        if mc.objExists(ON_OPEN_SCRIPT):
            return

        classname = self.__class__.__name__
        mc.scriptNode(
            beforeScript=(
                f"from pipe.m.shotfile import {classname};"
                f"{classname}.{self.__class__.run_on_open.__name__}()"
            ),
            name=ON_OPEN_SCRIPT,
            scriptType=1,
            sourceType="python",
        )
        # script node is created, will not run this session, so run manually
        self.run_on_open()

    def _import_camera(self) -> None:
        assert self.shot.path is not None
        root_layer = self.get_stage().GetRootLayer()

        # mc.mayaUsdLayerEditor(cam_layer.identifier, edit=True, lockLayer=(2, 0, stageShape))

        cam_file_layer = Sdf.Layer.FindOrOpenRelativeToLayer(
            root_layer, "/".join((self.shot.path, "cam", "cam.usd"))
        )
        if not cam_file_layer:
            mc.warning("No exported camera found")
            return

        if cam_file_layer.identifier not in root_layer.subLayerPaths:  # type: ignore[operator]
            root_layer.subLayerPaths.append(cam_file_layer.identifier)

    def _import_env(self) -> None:
        assert self.shot.path is not None
        stage = self.get_stage()
        root_layer = stage.GetRootLayer()
        # locked_layers: list[str] = []

        ## Fix env scale
        stage.SetEditTarget(Usd.EditTarget(root_layer))
        env_prim = stage.OverridePrim(Sdf.Path("/environment"))
        env_xformable = UsdGeom.Xformable(env_prim)
        env_xformable.ClearXformOpOrder()
        env_scale_op = env_xformable.AddScaleOp()
        env_scale_op.Set((100, 100, 100))

        # Set up shot-level overrides
        env_override_layer = Sdf.Layer.FindOrOpenRelativeToLayer(
            root_layer,
            "/".join((self.shot.path, "set", MShotFileManager.MAYA_OVERRIDE)),
        ) or Sdf.Layer.CreateNew(
            str(
                get_production_path()
                / self.shot.path
                / "set"
                / MShotFileManager.MAYA_OVERRIDE
            )
        )
        env_override_layer.Save()

        if env_override_layer.identifier not in root_layer.subLayerPaths:  # type: ignore[operator]
            root_layer.subLayerPaths.append(env_override_layer.identifier)

        stage.SetEditTarget(Usd.EditTarget(env_override_layer))

        env_stubs = self.shot.sets
        if env_stubs:
            for env_stub in env_stubs:
                layout = self._conn.get_env_by_stub(env_stub)
                if layout and layout.path:
                    env_path = self._resolve_env_usd_path(layout.path)
                    env_file_layer = Sdf.Layer.FindOrOpenRelativeToLayer(
                        root_layer, env_path
                    )
                    if env_file_layer.identifier not in root_layer.subLayerPaths:  # type: ignore[operator]
                        root_layer.subLayerPaths.append(env_file_layer.identifier)
                    # locked_layers.append(env_file_layer.identifier)
                    env_file_layer.SetPermissionToSave(False)
        else:
            # Fallback to depreciated single set logic if no sets are assigned
            if not (env_stub := self.shot.set):  # type: ignore[assignment]
                if not self.shot.sequence:
                    env_stub = None
                else:
                    env_stub = self._conn.get_sequence_by_stub(self.shot.sequence).set

            if env_stub and (env := self._conn.get_env_by_stub(env_stub)) and env.path:
                env_path = self._resolve_env_usd_path(env.path)
                env_file_layer = Sdf.Layer.FindOrOpenRelativeToLayer(
                    root_layer, env_path
                )
                if env_file_layer.identifier not in root_layer.subLayerPaths:  # type: ignore[operator]
                    root_layer.subLayerPaths.append(env_file_layer.identifier)
                # locked_layers.append(env_file_layer.identifier)
                env_file_layer.SetPermissionToSave(False)

        # for id in locked_layers:
        #     mc.mayaUsdLayerEditor(id, edit=True, lockLayer=(2, 0, stageShape))

    @abstractmethod
    def _setup_scene(self) -> None:
        pass

    def _setup_file(self, path: Path, entity) -> None:
        mc.file(rename=str(path))

        self.shot = cast(Shot, entity)
        assert self.shot.path is not None

        # Create USD Stage
        transform = mc.createNode("transform", name="stage_transform")
        mc.createNode("mayaUsdProxyShape", name="stage", parent=transform)
        stage_shape = self.get_stage_shape()
        mc.connectAttr("time1.outTime", f"{stage_shape}.time")

        ROOT_LAYER = "maya_root.usd"
        root_layer_path = str(get_production_path() / self.shot.path / ROOT_LAYER)
        root_layer = Sdf.Layer.FindOrOpen(root_layer_path) or Sdf.Layer.CreateNew(
            root_layer_path
        )
        root_layer.Save()
        mc.setAttr(f"{stage_shape}.filePath", "../" + ROOT_LAYER, type="string")

        # mc.mayaUsdLayerEditor(str(get_production_path() / "root.usda"), edit=True, lockLayer=(2, 0, stage_shape))

        # Set up stage
        self._setup_scene()
        root_layer.Save()
        root_layer.SetPermissionToSave(False)

        # Save USD Edits to the scene file and don't prompt about it
        mc.optionVar(intValue=("mayaUsd_SerializedUsdEditsLocationPrompt", 0))
        mc.optionVar(intValue=("mayaUsd_SerializedUsdEditsLocation", 2))

        # Save shot code to file
        mc.fileInfo("code", self.shot.code)
        mc.file(save=True, force=True)
