from maya import cmds

from .. import RigBuildTest


class TestHiddenJoints(RigBuildTest):
    """
    Checks that the scene has no visible joint nodes that aren't intentional
    (a joint with display mode set to none is fine).
    """

    def __init__(self):
        super().__init__("No visible joints without shapes")

    def run(self):
        visible_joints = cmds.ls(type="joint", visible=True)
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
