from maya import cmds

from .. import RigBuildTest
from ..common import format_max_items

DEFAULT_NODES = {"persp", "top", "front", "side"}


class TestSingleHierachy(RigBuildTest):
    """
    Checks that the scene consists of only a single rig hierarchy.
    (No more than one root node).
    """

    def __init__(self):
        super().__init__("Single hierarchy")

    def run(self) -> bool:
        top_level_nodes = cmds.ls(assemblies=True)
        non_default_top_level_nodes = [
            node for node in top_level_nodes if node not in DEFAULT_NODES
        ]
        if len(non_default_top_level_nodes) > 1:
            self.log_warn(
                f"Scene has more than one root node: {format_max_items(non_default_top_level_nodes, 'node(s)')}"
            )
            return False
        else:
            self.log_success()
            return True
