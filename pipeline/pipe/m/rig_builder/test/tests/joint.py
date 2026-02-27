from maya import cmds
from maya.api.OpenMaya import MDagPath, MSelectionList

from .. import RigBuildTest


class TestHiddenJoints(RigBuildTest):
    """
    Checks that the scene has no visible joint nodes that aren't intentional
    (a joint with display mode set to none is fine).
    """

    def __init__(self):
        super().__init__("No visible joints without shapes")

    def run(self) -> bool:
        visiblity_on_joints = cmds.ls(type="joint", visible=True)

        visible_joints: list[str] = []
        for joint in visiblity_on_joints:
            sel: MSelectionList = MSelectionList()
            sel.add(joint)
            joint_dag: MDagPath = sel.getDagPath(0)
            if not joint_dag.isVisible():
                continue
            visible_joints.append(joint_dag.partialPathName())

        problem_joints: list[str] = []
        for joint in visible_joints:
            if cmds.getAttr(f"{joint}.drawStyle") != 2:
                problem_joints.append(joint)
        if problem_joints:
            self.log_warn(f"Scene has visible joints: {problem_joints}")
            return False
        else:
            self.log_success()
            return True
