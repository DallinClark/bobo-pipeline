import maya.cmds as cmds
import mayaUsd.lib as mayaUsdLib  # type: ignore[import-not-found]
from mayaUsd.lib import proxyAccessor as pa  # type: ignore[import-not-found]
from pxr import UsdGeom
from PySide6 import QtWidgets  # type: ignore[import-not-found]
import maya.OpenMayaUI as omui
from shiboken6 import wrapInstance  # type: ignore[import-not-found]
from env_sg import DB_Config
from pipe.glui.dialogs import FilteredListDialog
from pipe.db import DB
from shared.util import get_production_path


class SelectFromGroup(FilteredListDialog):
    def __init__(self, items, title, command, parent=None):
        super().__init__(
            parent or SelectFromGroup.get_maya_main_window(),
            items,
            title,
            command,
            accept_button_name="Select",
        )

    @staticmethod
    def get_maya_main_window():
        ptr = omui.MQtUtil.mainWindow()
        if ptr is not None:
            return wrapInstance(int(ptr), QtWidgets.QWidget)
        return None

    def get_selected_item(self):
        selected_items = self._list_widget.selectedItems()
        if selected_items:
            return selected_items[0].text()
        return None


# Methods for creating layouts for previs


def ask_for_name(label):
    """Show a Qt input dialog asking for environment name."""
    parent = SelectFromGroup.get_maya_main_window()
    text, ok = QtWidgets.QInputDialog.getText(
        parent, f"{label} Name", f"Enter {label} name:"
    )
    if ok and text.strip():
        return text.strip()
    return None


def get_usd_selection():
    # Get current selection
    stagePath, sdfPath = pa.getSelectedDagAndPrim()
    print(f"Stage Path: {stagePath}, sdfPath: {sdfPath}")
    if sdfPath[-3:] != "geo":
        return

    # Get USD stage from DAG path
    stage = mayaUsdLib.GetPrim(stagePath).GetStage()
    if not stage:
        print("No USD stage found.")
        return

    prim = stage.GetPrimAtPath(sdfPath)
    if not prim or not prim.IsValid():
        print("Invalid USD prim.")
        return

    # Go two parents up
    parent1 = prim.GetParent()
    parent2 = parent1.GetParent() if parent1 else None
    parent3 = parent2.GetParent() if parent2 else None

    if parent3 and parent3.IsValid():
        # Set new selection to the grandparent prim
        newPath = f"{stagePath},{parent3.GetPath()}"
        cmds.select(newPath, replace=True)
        print(f"Changed selection to: {newPath}")
    else:
        print("Grandparent prim not found or invalid.")


def create_environment_xform():
    # Ensure mayaUsdPlugin is loaded
    if not cmds.pluginInfo("mayaUsdPlugin", q=True, loaded=True):
        cmds.loadPlugin("mayaUsdPlugin")

    # Create transform and proxyShape nodes
    proxy_transform = cmds.createNode("transform", name="environment")
    proxy_shape = cmds.createNode(
        "mayaUsdProxyShape", name="environmentShape", parent=proxy_transform
    )

    # Select the proxy shape
    cmds.select(proxy_shape)

    # Get the USD paths
    shapePath, sdfPath = pa.getSelectedDagAndPrim()

    # Get the stage from the proxy shape prim
    stage = mayaUsdLib.GetPrim(shapePath).GetStage()
    if not stage:
        cmds.error("Could not get USD stage from proxy shape.")
        return

    # Ask user for environment name
    env_name = ask_for_name("environment")
    if not env_name:
        cmds.warning("Environment name not provided, operation canceled.")
        return

    # Define a new Xform prim with user input name at root level
    new_xform_path = f"/{env_name}"
    UsdGeom.Xform.Define(stage, new_xform_path)

    # Optionally save the stage
    cmds.scriptJob(event=["SelectionChanged", get_usd_selection], protected=True)

    print(f"Created Xform prim at {new_xform_path}")


def create_layout_group():
    # Ensure USD plugin is loaded
    if not cmds.pluginInfo("mayaUsdPlugin", q=True, loaded=True):
        cmds.loadPlugin("mayaUsdPlugin")

    # Get the stage from a proxy shape named "environment"
    proxy_shapes = cmds.ls(type="mayaUsdProxyShape")
    environment_stage = None

    for shape in proxy_shapes:
        if "environment" in shape:
            prim = mayaUsdLib.GetPrim(shape)
            stage = prim.GetStage()
            if stage:
                environment_stage = stage
                break

    if not environment_stage:
        cmds.error("No USD stage named 'environment' found.")
        raise RuntimeError("No USD stage named 'environment' found.")

    # Get first child of the root
    root = environment_stage.GetPseudoRoot()
    children = list(root.GetChildren())
    print(f"CHILDREN {children}")
    if not children:
        cmds.error("No children found on the environment stage.")
        raise RuntimeError("No children found.")

    target_prim = children[0]
    print(f"TARGET PRIM {target_prim}")
    target_path = target_prim.GetPath()
    print(f"TARGET PATH {target_path}")

    # Create a new Xform above the prim
    new_xform_name = ask_for_name("layout group")
    xform_path = target_path.AppendChild(new_xform_name)

    print(f"XFORM PATH {xform_path}")

    UsdGeom.Xform.Define(environment_stage, xform_path)


def add_reference():
    # Ensure USD plugin is loaded
    if not cmds.pluginInfo("mayaUsdPlugin", q=True, loaded=True):
        cmds.loadPlugin("mayaUsdPlugin")

    # Get the stage from a proxy shape named "environment"
    proxy_shapes = cmds.ls(type="mayaUsdProxyShape")
    environment_stage = None

    for shape in proxy_shapes:
        if "environment" in shape:
            prim = mayaUsdLib.GetPrim(shape)
            stage = prim.GetStage()
            if stage:
                environment_stage = stage
                break

    if not environment_stage:
        cmds.error("No USD stage named 'environment' found.")
        return

    # Get first child of the root (the environment root)
    root = environment_stage.GetPseudoRoot()
    children = list(root.GetChildren())
    if not children:
        cmds.error("No children found on the environment stage.")
        return

    environment_prim = children[0]
    layout_groups = list(environment_prim.GetChildren())

    if not layout_groups:
        cmds.error("No layout groups found.")
        return

    # Extract layout group names
    layout_names = [prim.GetName() for prim in layout_groups]

    # Create and show UI
    layout_dialog = SelectFromGroup(layout_names, "Layout Group", "Select your group")
    if not layout_dialog.exec_():
        return  # User cancelled

    selected_layout = layout_dialog.get_selected_item()
    print(f"User selected layout: {selected_layout}")

    conn = DB.Get(DB_Config)
    asset_list = conn.get_asset_name_list(sorted=True)

    asset_dialog = SelectFromGroup(asset_list, "Reference Asset", "Select your asset")
    if not asset_dialog.exec_():
        return  # User cancelled

    selected_asset_name = asset_dialog.get_selected_item()
    if not selected_asset_name:
        cmds.warning("No asset selected.")
        return

    selected_asset = conn.get_asset_by_name(selected_asset_name)

    print(f"SELECTED ASSET: {selected_asset.name}")

    # Define the reference prim under the selected layout group
    reference_path = (
        f"/{environment_prim.GetName()}/{selected_layout}/{selected_asset.name}"
    )
    reference_prim = UsdGeom.Xform.Define(environment_stage, reference_path)
    # reference_prim.AddScaleOp().Set((100.0, 100.0, 100.0))

    # Add a reference to the prim
    reference_file = (
        str(get_production_path())
        + f"/{selected_asset.path}/export/{selected_asset.name}.usd"
    )
    print(f"REFERENCE PATH: {reference_file}")
    reference_prim.GetPrim().GetReferences().AddReference(reference_file)

    print(f"Added reference to {reference_path}")


def export_environment_to_usd():
    # Find the environment proxy shape
    proxy_shapes = cmds.ls(type="mayaUsdProxyShape")
    environment_stage = None

    for shape in proxy_shapes:
        if "environment" in shape:
            prim = mayaUsdLib.GetPrim(shape)
            stage = prim.GetStage()
            if stage:
                environment_stage = stage
                break

    if not environment_stage:
        cmds.error("No USD stage named 'environment' found.")
        return

    # Ask the user where to save the USD file
    parent = SelectFromGroup.get_maya_main_window()
    file_dialog = QtWidgets.QFileDialog(parent)
    file_dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
    file_dialog.setNameFilter("USD Files (*.usd *.usda *.usdc)")
    file_dialog.setDefaultSuffix("usd")
    file_dialog.setWindowTitle("Export Environment USD")

    if file_dialog.exec_() != QtWidgets.QDialog.Accepted:
        cmds.warning("Export cancelled.")
        return

    selected_path = file_dialog.selectedFiles()[0]
    print(f"Exporting to: {selected_path}")

    # Export using Sdf Layer
    try:
        root_layer = environment_stage.GetRootLayer()
        root_layer.Export(selected_path)
        print(f"Environment USD successfully exported to {selected_path}")
    except Exception as e:
        cmds.error(f"Failed to export USD: {str(e)}")
