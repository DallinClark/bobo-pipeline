from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from logging import getLogger
from typing import Counter

from maya import cmds
from maya.api.OpenMaya import MFn, MFnDagNode, MItDag

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


class TestUnknownNodes(RigBuildTest):
    """
    Checks that the scene has no nodes of an unkown type (due to a missing plugin or otherwise).
    """

    def __init__(self):
        super().__init__("No unkown nodes")

    def run(self):
        unkown_nodes = cmds.ls(type="unkown")
        if unkown_nodes:
            self.log_warn(f"Scene has unkown nodes: {unkown_nodes}")
            return False
        else:
            self.log_success()
            return True


class TestDuplicateDagNames(RigBuildTest):
    """
    Checks that the scene has no duplicate DAG names (these types of nodes may cause problems for third party tools).
    """

    def __init__(self):
        super().__init__("No duplicate DAG names")

    def run(self):
        def iter_dag_names(dag_iterator: MItDag) -> Iterator[str]:
            while not dag_iterator.isDone():
                current_node = dag_iterator.currentItem()
                dag_fn = MFnDagNode(current_node)
                short_name: str = dag_fn.name()
                yield short_name
                dag_iterator.next()

        dag_iterator = MItDag(MItDag.kDepthFirst)
        counter = Counter(iter_dag_names(dag_iterator))
        duplicates = [name for name, count in counter.items() if count > 1]

        if duplicates:
            self.log_warn(f"Scene has duplicate DAG node names: {duplicates}")
            return False
        else:
            self.log_success()
            return True


class TestNgSkinData(RigBuildTest):
    """
    Checks that the scene has no ngst2SkinLayerData nodes.
    These are the nodes that store the layer information for Ng Skin Tools and they can easily become very big and bloat the rig file.
    Their data is baked into the skinCluster node weights during each painting step anyways, so they should be deleted for final rig publish.
    """

    def __init__(self):
        super().__init__("No NgSkinTools data nodes")

    def run(self):
        ng_data_nodes = cmds.ls(type="ngst2SkinLayerData")
        if ng_data_nodes:
            self.log_warn(f"Scene has ngst2SkinLayerData nodes: {ng_data_nodes}")
            return False
        else:
            self.log_success()
            return True


RIG_BUILD_TESTS = [
    TestHiddenJoints(),
    TestUnknownNodes(),
    TestDuplicateDagNames(),
    TestNgSkinData(),
]
