from __future__ import annotations

from abc import ABC, abstractmethod
from logging import getLogger

from maya import cmds

log = getLogger(__name__)


class RigBuildTest(ABC):
    def __init__(self, name: str):
        self.name = name
        pass

    @abstractmethod
    def run(self) -> bool:
        """Should be implemented in all tests, returns True if the test passed."""
        pass

    def log_warn(self, message: str):
        log.warn(f"{self.name}: {message}")

    def log_success(self):
        log.info(f"{self.name}: PASSED")


class TestHiddenJoints(RigBuildTest):
    """
    Checks that the scene has no visible joint nodes that aren't intentional
    (a joint with display mode set to none that has a shape is fine).
    """

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
            self.log_warn(f"Scene has visible joints: {problem_joints}")
            return False
        else:
            self.log_success()
            return True


RIG_BUILD_TESTS = [TestHiddenJoints()]
