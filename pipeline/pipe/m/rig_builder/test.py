from __future__ import annotations

from abc import ABC, abstractmethod

from maya import cmds


class RigBuildTest(ABC):
    def __init__(self, name: str):
        self.name = name
        pass

    @abstractmethod
    def run(self) -> bool:
        """Should be implemented in all tests, returns True if the test passed."""
        pass


class TestHiddenJoints(RigBuildTest):
    def __init__(self):
        super().__init__("No visible joints without shapes")

    def run(self):
        visible_joints = cmds.ls(type="joint", visible=True)
        problem_joints: list[str] = []
        for joint in visible_joints:
            joint_shapes = cmds.listRelatives(joint, children=True, shapes=True)
            if not joint_shapes:
                problem_joints.append(joint)
                continue
            if cmds.getAttr(f"{joint}.drawStyle") != 2:
                problem_joints.append(joint)

        if problem_joints:
            return False
        else:
            return True


RIG_BUILD_TESTS = [TestHiddenJoints()]
