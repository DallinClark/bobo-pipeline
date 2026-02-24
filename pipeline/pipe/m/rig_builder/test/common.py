import json
from typing import Iterator, Literal

from maya import cmds
from maya.api.OpenMaya import MFnDagNode, MItDag


def get_evaluation_graph(attributes: Literal["nodes", "plugs", "connections"]):
    return json.loads(
        cmds.dbpeek(
            operation="graph",
            evaluationGraph=True,
            argument=attributes,
            allObjects=True,
        )  # type: ignore
    )


def get_evaluation_manager_nodes() -> list[str]:
    raw_json = get_evaluation_graph("nodes")
    if not raw_json:
        return []
    nodeList = raw_json["nodes"]
    return nodeList


def iter_dag_nodes(dag_iterator: MItDag) -> Iterator[MFnDagNode]:
    while not dag_iterator.isDone():
        current_node = dag_iterator.currentItem()
        dag_fn = MFnDagNode(current_node)
        yield dag_fn
        dag_iterator.next()
