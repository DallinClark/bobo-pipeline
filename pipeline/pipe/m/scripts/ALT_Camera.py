import maya.cmds as cmds
import os

# Corrected rig paths
WINDOWS_RIG_PATH = "G:/bobo/previs/Rigs/boboShotCam_v01.mb"
LINUX_RIG_PATH = "/groups/bobo/previs/Rigs/boboShotCam_v01.mb"


def reference_and_match_rig():
    def get_rigs_with_cam_namespace():
        rigs = []
        for ref in cmds.file(query=True, reference=True) or []:
            namespace = cmds.referenceQuery(ref, namespace=True).replace(":", "")
            if "CAM" in namespace:
                rigs.append(namespace)
        return rigs

    def get_top_level_transforms(namespace):
        return [
            obj
            for obj in cmds.ls(f"{namespace}:*", transforms=True)
            if ":" not in obj.split("|")[-1]
        ]

    def generate_new_namespace(base_ns):
        base_name = f"{base_ns}_ALT"
        i = 1
        while cmds.namespace(exists=f"{base_name}{i:02}"):
            i += 1
        return f"{base_name}{i:02}"

    def match_transforms(source_ns, target_ns):
        control_names = [
            "world_CTRL",
            "main_CTRL",
            "dolly_CTRL",
            "tilt_pan_CTRL",
            "ClippingPlane_CTRL",
            "focusDistance_CTRL",
        ]

        for ctrl in control_names:
            source_ctrl = f"{source_ns}:{ctrl}"
            target_ctrl = f"{target_ns}:{ctrl}"

            if cmds.objExists(source_ctrl) and cmds.objExists(target_ctrl):
                pos = cmds.xform(target_ctrl, query=True, ws=True, t=True)
                rot = cmds.xform(target_ctrl, query=True, ws=True, ro=True)

                cmds.xform(source_ctrl, ws=True, t=pos)
                cmds.xform(source_ctrl, ws=True, ro=rot)
            else:
                print(f"Skipping '{ctrl}' — not found in one of the rigs.")

    def on_apply(*args):
        os_type = cmds.optionMenu(os_option_menu, query=True, value=True)
        rig_path = WINDOWS_RIG_PATH if os_type == "Windows" else LINUX_RIG_PATH

        if not os.path.exists(rig_path):
            cmds.warning(f"Rig file not found: {rig_path}")
            return

        selected_rig_ns = cmds.optionMenu(rig_option_menu, query=True, value=True)
        new_ns = generate_new_namespace(selected_rig_ns)

        # Reference rig
        cmds.file(rig_path, reference=True, namespace=new_ns)

        # Match transforms
        match_transforms(f"{new_ns}", f"{selected_rig_ns}")
        cmds.confirmDialog(
            title="Success",
            message=f"Rig referenced and matched as {new_ns}",
            button=["OK"],
        )

    # UI
    if cmds.window("rigMatchUI", exists=True):
        cmds.deleteUI("rigMatchUI")

    rigs = get_rigs_with_cam_namespace()
    if not rigs:
        cmds.warning("No rigs with 'CAM' in namespace found.")
        return

    window = cmds.window(
        "rigMatchUI", title="Rig Reference and Match", widthHeight=(400, 150)
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAlign="center")

    cmds.text(label="Select Your OS:")
    os_option_menu = cmds.optionMenu()
    cmds.menuItem(label="Windows")
    cmds.menuItem(label="Linux")

    cmds.text(label="Select Target Rig (CAM):")
    rig_option_menu = cmds.optionMenu()
    for rig in rigs:
        cmds.menuItem(label=rig)

    cmds.button(label="Reference and Match Rig", command=on_apply)

    cmds.showWindow(window)


reference_and_match_rig()
