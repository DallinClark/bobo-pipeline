import json
from typing import Literal

from maya import cmds


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
