from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from logging import getLogger
from typing import Callable, Counter, DefaultDict, Iterable

from maya import cmds
from maya.api.OpenMaya import MFnDagNode, MItDag

log = getLogger(__name__)


class TestRunner:
    def __init__(
        self,
        tests: Iterable[RigBuildTest],
        test_run_callback: Callable[[RigBuildTest, bool], None] | None = None,
    ) -> None:
        self.tests = tests
        self._test_run_callback = test_run_callback

    def run_tests(self) -> bool:
        """Runs all of the TestRunner's tests and returns True if all tests passed."""
        passing: bool = True
        for test in self.tests:
            test_passed = test.run()
            if self._test_run_callback is not None:
                self._test_run_callback(test, test_passed)
            if not test_passed:
                passing = False
        return passing


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
        def iter_dag_nodes(dag_iterator: MItDag) -> Iterator[MFnDagNode]:
            while not dag_iterator.isDone():
                current_node = dag_iterator.currentItem()
                dag_fn = MFnDagNode(current_node)
                yield dag_fn
                dag_iterator.next()

        dag_iterator = MItDag(MItDag.kDepthFirst)
        short_name_counter = Counter()
        name_to_paths = DefaultDict(list[str])
        for dag_fn in iter_dag_nodes(dag_iterator):
            short_name = dag_fn.name()
            full_path = dag_fn.fullPathName()
            short_name_counter[short_name] += 1
            name_to_paths[short_name].append(full_path)

        duplicates = [
            name_to_paths[name]
            for name, count in short_name_counter.items()
            if count > 1
        ]
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
