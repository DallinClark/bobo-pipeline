import maya.cmds as mc
import mayaUsd.lib as mayaUsdLib  # type: ignore[import-not-found]
from pxr import UsdGeom
from PySide6 import QtWidgets  # type: ignore[import-not-found]
import maya.OpenMayaUI as omui
from shiboken6 import wrapInstance  # type: ignore[import-not-found]
from env_sg import DB_Config
from pipe.glui.dialogs import FilteredListDialog
from pipe.db import DB
from shared.util import get_production_path
from pipe.struct.db import Environment
import os



class SelectFromGroup(FilteredListDialog):
    """ Helper Class that gives a window to select from a list """

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

class LayoutMaker():
    """ Different methods for making layouts in maya
        which allow them to be made in the same way
        Houdini makes layouts """
    
    @staticmethod
    def get_stage():
        proxy_shapes = mc.ls(type="mayaUsdProxyShape", long=True)
        if not proxy_shapes:
            mc.error("No mayaUsdProxyShape found in the scene.")
            return None

        proxy_shape = proxy_shapes[0]

        try:
            prim = mayaUsdLib.GetPrim(proxy_shape)
            stage = prim.GetStage()

        except Exception as e:
            mc.error(f"Failed to get USD stage: {str(e)}")
            return None

        if not stage:
            mc.error("No USD stage found.")

        return stage

    @staticmethod
    def create_layout_group():
        def ask_for_name(label):
            """Show a Qt input dialog asking for environment name."""
            parent = SelectFromGroup.get_maya_main_window()
            text, ok = QtWidgets.QInputDialog.getText(
                parent, f"{label} Name", f"Enter {label} name:"
            )
            if ok and text.strip():
                return text.strip()

            return None

        if not mc.pluginInfo("mayaUsdPlugin", q=True, loaded=True):
            mc.loadPlugin("mayaUsdPlugin")

        stage = LayoutMaker.get_stage()

        # Ensure /environment exists
        environment_prim = stage.GetPrimAtPath("/environment")
        if not environment_prim or not environment_prim.IsValid():
            mc.error("/environment prim does not exist!")
            return

        children = environment_prim.GetChildren()
        if len(children) == 0:
            mc.error("No prim under /environment to use as set!")
            return
        elif len(children) > 1:
            mc.warning("Warning: More than one prim under /environment, using the first one.")

        set_prim = children[0]
        set_prim_path = set_prim.GetPath()

        # Name for new Xform
        new_xform_name = ask_for_name("layout group")
        new_xform_path = set_prim_path.AppendChild(new_xform_name)

        # Define new Xform under the set prim
        try:
            UsdGeom.Xform.Define(stage, new_xform_path)
        except Exception as e:
            mc.error(f"Failed to make layer: {str(e)}")
            return


    @staticmethod
    def add_reference():
        # Ensure USD plugin is loaded
        if not mc.pluginInfo("mayaUsdPlugin", q=True, loaded=True):
            mc.loadPlugin("mayaUsdPlugin")

        stage = LayoutMaker.get_stage()

        # Get first child of the root (the environment root)
        root = stage.GetPseudoRoot()
        children = list(root.GetChildren())
        if not children:
            mc.error("No children found on the base stage.")
            return

        env_prim = children[0]

        children = list(env_prim.GetChildren())
        if not children:
            mc.error("No children found on the base stage.")
            return

        set_prim = children[0]

        layout_groups = list(set_prim.GetChildren())

        if not layout_groups:
            mc.error("No layout groups found.")
            return

        # Extract layout group names
        layout_names = [prim.GetName() for prim in layout_groups]

        # Create and show UI
        layout_dialog = SelectFromGroup(layout_names, "Layout Group", "Select your group")
        if not layout_dialog.exec_():
            return  # User cancelled

        selected_layout = layout_dialog.get_selected_item()

        conn = DB.Get(DB_Config)
        asset_list = conn.get_asset_name_list(sorted=True)

        asset_dialog = SelectFromGroup(asset_list, "Reference Asset", "Select your asset")
        if not asset_dialog.exec_():
            return  # User cancelled

        selected_asset_name = asset_dialog.get_selected_item()
        if not selected_asset_name:
            mc.warning("No asset selected.")
            return

        selected_asset = conn.get_asset_by_name(selected_asset_name)

        # Define the reference prim under the selected layout group
        base_path = f"/{env_prim.GetName()}/{set_prim.GetName()}/{selected_layout}"
        base_name = selected_asset.name
        reference_path = f"{base_path}/{base_name}_0"
        
        i = 1
        while stage.GetPrimAtPath(reference_path).IsValid():
            reference_path = f"{base_path}/{base_name}_{i}"
            i += 1

        reference_prim = UsdGeom.Xform.Define(stage, reference_path)

        reference_file_abs = (
            str(get_production_path())
            + f"/{selected_asset.path}/export/{selected_asset.name}.usd"
        )

        # Get Maya file path
        proxy_shapes = mc.ls(type="mayaUsdProxyShape", long=True)
        if not proxy_shapes:
            mc.error("No mayaUsdProxyShape found.")
        proxy_shape = proxy_shapes[0]

        file_path = mc.getAttr(f"{proxy_shape}.filePath")
        # Convert to relative path
        reference_file_rel = os.path.relpath(reference_file_abs, start=os.path.dirname(file_path))
        print("File path:", file_path)
        print("Reference file abs:", reference_file_abs)

        print(reference_file_rel)

        stage.SetEditTarget(stage.GetRootLayer())
        reference_prim.GetPrim().GetReferences().AddReference(reference_file_rel)

    @staticmethod
    def match_houdini():
        result = mc.confirmDialog(
            title="Confirm Match",
            message="Are you sure? This will overwrite your current file.",
            button=['Cancel', 'Continue'],
            defaultButton="Continue",
            cancelButton='Cancel',
            dismissString='Cancel'
        )

        if result == 'Cancel':
            return

        conn = DB.Get(DB_Config)
        set_list = conn.get_entity_code_list(
                Environment,
                sorted=True,
            )

        set_dialog = SelectFromGroup(set_list, "Match Houdini", "Choose layout to match")
        if not set_dialog.exec_():
            return  # User cancelled

        selected_set_name = set_dialog.get_selected_item()
        if not selected_set_name:
            mc.error("No asset selected.")
            return

        set = conn.get_entity_by_code(Environment, selected_set_name)

        houdini_set_path = get_production_path() / set.path / "main.usd"

        # Wipe the file
        current_file = mc.file(q=True, sn=True)
        mc.file(new=True, force=True)

        if not mc.pluginInfo("mayaUsdPlugin", q=True, loaded=True):
            mc.loadPlugin("mayaUsdPlugin")

        # Step 3: Create stage
        transform = mc.createNode("transform", name="main")
        proxy_shape = mc.createNode("mayaUsdProxyShape", name="mainShape", parent=transform)
        mc.setAttr(f"{proxy_shape}.filePath", str(houdini_set_path), type="string")

        if current_file:
            mc.file(rename=current_file)
            mc.file(save=True, type="mayaBinary")
        else:
            mc.error("No original Maya file path found. Scene not saved.")


