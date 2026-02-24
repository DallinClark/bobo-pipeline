from collections import Counter
from typing import DefaultDict, Iterator

from maya.api.OpenMaya import MFnDagNode, MItDag

from .. import RigBuildTest


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
