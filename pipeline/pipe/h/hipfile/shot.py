from __future__ import annotations

import hou
import logging
from enum import Enum
from pathlib import Path
from typing import cast

import pipe.h
from pipe.glui.dialogs import FilteredListDialog
from pipe.struct.db import SGEntity, Shot

from .filemanager import HFileManager


log = logging.getLogger(__name__)


class HShotFileManager(HFileManager):
    _department: DEPARTMENT

    class DEPARTMENT(str, Enum):
        CFX = "cfx"
        FX = "fx"
        LIGHTING = "lighting"
        ENVFX = "envfx"

    def __init__(self):
        department_dialog = FilteredListDialog(
            pipe.h.local.get_main_qt_window(),
            [
                self.DEPARTMENT.CFX,
                self.DEPARTMENT.FX,
                self.DEPARTMENT.ENVFX,
                self.DEPARTMENT.LIGHTING,
            ],
            "Department Select",
            include_filter_field=False,
            accept_button_name="Select",
        )
        department_dialog.exec_()

        self._department = department_dialog.get_selected_item()
        if not self._department:
            return
        super().__init__(Shot, versioning=True, version_glob="{}_v*.{}")

    def _generate_filename_ext(self, entity) -> tuple[str, str]:
        return self._department, "hipnc"

    def _get_subpath(self) -> str:
        return self._department

    def _post_open_file(self, entity: SGEntity):
        shot = cast(Shot, entity)
        hou.playbar.setFrameRange(shot.cut_in - 5, shot.cut_out + 5)
        hou.playbar.setPlaybackRange(shot.cut_in - 5, shot.cut_out + 5)
        sets = shot.sets
        if sets:
            for idx, environment_stub in enumerate(sets):
                layout = self._conn.get_env_by_stub(environment_stub)
                if layout and layout.path:
                    hou.putenv(f"SET{idx+1}_PATH", layout.path)
        else:
            # Fallback to depreciated single set logic if no sets are assigned
            if environment_stub := (
                shot.set or self._conn.get_sequence_by_stub(shot.sequence).set  # type: ignore[assignment, arg-type]
            ):
                layout = self._conn.get_env_by_stub(environment_stub)
                if layout and layout.path:
                    hou.putenv("SET_PATH", layout.path)

    def _setup_file(self, path: Path, entity: SGEntity) -> None:
        super(HShotFileManager, HShotFileManager)._setup_file(self, path, entity)
        shot = cast(Shot, entity)

        if shot.path:
            hou.setContextOption("SHOT", shot.path)

        stage: hou.Node = hou.node("/stage")  # type: ignore[assignment]

        muted_departments: list[str] = []
        if self._department == self.DEPARTMENT.CFX:
            muted_departments = ["cfx", "fx", "envfx", "layout", "lighting"]
        elif self._department == self.DEPARTMENT.FX:
            muted_departments = ["fx"]
        elif self._department == self.DEPARTMENT.ENVFX:
            muted_departments = ["envfx"]
        elif self._department == self.DEPARTMENT.LIGHTING:
            muted_departments = ["lighting"]
        else:
            muted_departments = []

        load_layers = []
        sets = shot.sets
        if sets:
            for environment_stub in sets:
                load_layer = stage.createNode("dbclark::main::Bobo_Load_Layers::1.0")
                load_layer.setUserData("nodeshape", "bulge_down")
                load_layer.parm("shot").set("$JOB/`@SHOT`")  # type: ignore[union-attr]

                for department in muted_departments:
                    load_layer.parm(f"{department}_enable").set(0)  # type: ignore[union-attr]

                layout = self._conn.get_env_by_stub(environment_stub)
                if layout and layout.path:
                    load_layer.parm("layout_path").set(f"$JOB/{layout.path}/main.usd")  # type: ignore[union-attr]
                load_layers.append(load_layer)
        else:
            # Fallback to depreciated single set logic if no sets are assigned
            load_layer = stage.createNode("dbclark::main::Bobo_Load_Layers::1.0")
            load_layer.setUserData("nodeshape", "bulge_down")
            load_layer.parm("shot").set("$JOB/`@SHOT`")  # type: ignore[union-attr]

            for department in muted_departments:
                load_layer.parm(f"{department}_enable").set(0)  # type: ignore[union-attr]

            if env_stub := (
                shot.set or self._conn.get_sequence_by_stub(shot.sequence).set  # type: ignore[arg-type]
            ):
                layout = self._conn.get_env_by_stub(env_stub)
                if layout and layout.path:
                    load_layer.parm("layout_path").set(f"$JOB/{layout.path}/main.usd")  # type: ignore[union-attr]
                load_layers.append(load_layer)

        # Merge load layers if there are multiple
        if len(load_layers) > 1:
            merge_node = stage.createNode("merge")
            merge_node.setName("LOAD_LAYERS")
            for idx, load_layer in enumerate(load_layers):
                merge_node.setInput(idx, load_layer)
            input_node = merge_node
        else:
            input_node = load_layers[0]

        layer_break = stage.createNode("layerbreak")
        layer_break.setInput(0, input_node)

        begin_dep = stage.createNode("null")
        begin_dep.setName(f"BEGIN_{self._department.upper()}")

        end_dep = stage.createNode("null")
        end_dep.setName(f"END_{self._department.upper()}")

        publish = stage.createNode("usd_rop")
        publish.setName("PUBLISH")
        publish.parm("lopoutput").set("$HIP/usd/main.usd")  # type: ignore[union-attr]

        layer_break.setInput(0, input_node)
        begin_dep.setInput(0, layer_break)
        end_dep.setInput(0, begin_dep)
        publish.setInput(0, end_dep)

        end_dep.setPosition((0, 1))
        begin_dep.setPosition((0, 4))
        layer_break.setPosition((0, 5))
        input_node.setPosition((0, 6))

        self._post_open_file(shot)

        hou.hipFile.save()
