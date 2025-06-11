import maya.cmds as cmds
import os

# Define your rig paths for each OS
RIG_PATHS = {
    "Windows": "G:/bobo/previs/Rigs/FX_card_rig_v02.ma",
    "Linux": "/groups/bobo/previs/Rigs/FX_card_rig_v02.ma",
}


def reference_rig_with_namespace(rig_path, base_namespace):
    # Generate a unique namespace
    i = 1
    namespace = base_namespace
    while cmds.namespace(exists=namespace):
        namespace = f"{base_namespace}_{i}"
        i += 1

    # Reference the file
    try:
        cmds.file(rig_path, reference=True, namespace=namespace)
        cmds.inViewMessage(
            amg=f"Referenced <hl>{rig_path}</hl> as <hl>{namespace}</hl>",
            pos="topCenter",
            fade=True,
        )
    except Exception as e:
        cmds.error(f"Failed to reference rig: {e}")


def open_reference_ui():
    # Close previous window if open
    if cmds.window("rigRefUI", exists=True):
        cmds.deleteUI("rigRefUI")

    window = cmds.window("rigRefUI", title="Rig Reference Tool", sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAlign="center")

    cmds.text(label="Enter reference name:")
    ref_name_field = cmds.textField(placeholderText="e.g., myCharacter")

    cmds.text(label="Select your OS:")
    os_menu = cmds.optionMenuGrp(label="Operating System")
    cmds.menuItem(label="Windows")
    cmds.menuItem(label="Linux")

    def on_submit(*args):
        ref_name = cmds.textField(ref_name_field, q=True, text=True)
        os_selected = cmds.optionMenuGrp(os_menu, q=True, value=True)

        if not ref_name:
            cmds.warning("Please enter a reference name.")
            return

        rig_path = RIG_PATHS.get(os_selected)
        if not rig_path or not os.path.exists(rig_path):
            cmds.error(f"Rig path not found for {os_selected}: {rig_path}")
            return

        reference_rig_with_namespace(rig_path, ref_name)
        cmds.deleteUI("rigRefUI")

    cmds.button(label="Reference Rig", command=on_submit)

    cmds.showWindow(window)
