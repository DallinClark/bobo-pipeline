from maya import cmds

from .. import RigBuildTest


class TestUnknownNodes(RigBuildTest):
    """
    Checks that the scene has no nodes of an unknown type (due to a missing plugin or otherwise).
    """

    def __init__(self):
        super().__init__("No unknown nodes")

    def run(self) -> bool:
        unknown_nodes = cmds.ls(type="unknown")
        if unknown_nodes:
            self.log_warn(f"Scene has unknown nodes: {unknown_nodes}")
            return False
        else:
            self.log_success()
            return True
