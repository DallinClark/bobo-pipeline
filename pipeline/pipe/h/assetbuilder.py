from pathlib import Path

from typing import Optional, Union, cast

import hou

from pipe.h import nodelayouts


class AssetComponentBuilder:
    """Build and publish a component network for a Maya-exported asset."""

    def __init__(self, asset_path: Union[str, Path]) -> None:
        path = Path(asset_path)
        if not path.exists():
            raise FileNotFoundError(path)
        self.asset_path = path.resolve()

    def run(self) -> None:
        """Generate the component network and export the USD."""
        self._prepare_hip()
        stage = self._prepare_stage()
        component_output = self._build_component(stage)
        self._configure_import(component_output)
        self._configure_output(component_output)
        self._save(component_output)

    def _prepare_hip(self) -> None:
        # Ensure $HIP resolves close to the asset we are processing so that
        # existing node layouts that rely on it continue to function.
        hou.hipFile.clear(suppress_save_prompt=True)
        hip_path = self.asset_path.with_suffix(".hip")
        hou.hipFile.setName(str(hip_path))

    def _prepare_stage(self) -> hou.Node:
        stage = hou.node("/stage")
        if stage is None:
            root = hou.node("/")
            if root is None:
                raise RuntimeError("Unable to locate Houdini root node")
            stage = root.createNode("lopnet", "stage")
        for child in stage.children():
            child.destroy()
        return stage

    def _build_component(self, stage: hou.Node) -> hou.Node:
        kwargs = {"node": stage}
        component_output = nodelayouts.bobo_componentsetup(kwargs)
        return component_output

    def _configure_import(self, component_output: hou.Node) -> None:
        component_geometry = None
        component_config = component_output.inputs()[0]
        if component_config is not None:
            component_material = component_config.inputs()[0]
            if component_material is not None:
                component_geometry = component_material.inputs()[0]
        if (
            component_geometry is None
            or component_geometry.type().name() != "componentgeometry"
        ):
            raise RuntimeError("Component geometry node was not created")

        sopnet = component_geometry.node("sopnet/geo")
        if sopnet is None:
            raise RuntimeError("Component geometry SOP network is missing")

        usd_import = next(
            (
                node
                for node in sopnet.allSubChildren()
                if node.type().name() == "usdimport"
            ),
            None,
        )
        if usd_import is None:
            raise RuntimeError(
                "Unable to locate USD Import node inside component geometry"
            )

        filename_parm = None
        for parm_name in ("filepath1", "file", "filename"):
            parm = usd_import.parm(parm_name)
            if parm is not None:
                filename_parm = parm
                break
        if filename_parm is None:
            raise RuntimeError("USD Import node does not expose a filename parameter")

        filename_parm.set(str(self.asset_path))

        polyreduce: Optional[hou.SopNode] = next(
            (
                cast("hou.SopNode", node)
                for node in sopnet.allSubChildren()
                if node.type().name() == "polyreduce"
            ),
            None,
        )
        if polyreduce is None:
            raise RuntimeError("Unable to find polyreduce node to set display flag")

        polyreduce.setDisplayFlag(True)
        polyreduce.setCurrent(True, clear_all_selected=True)

    def _configure_output(self, component_output: hou.Node) -> None:
        self.asset_path.parent.mkdir(parents=True, exist_ok=True)
        lopoutput = component_output.parm("lopoutput")
        if lopoutput is not None:
            lopoutput.set(str(self.asset_path))

    def _save(self, component_output: hou.Node) -> None:
        for parm_name in ("execute", "save", "save_to_disk"):
            parm = component_output.parm(parm_name)
            if parm is not None:
                parm.pressButton()
                return
        raise RuntimeError("Component output node has no save/execute parameter")
