from typing import FrozenSet

from maya import cmds

from .. import RigBuildTest
from ..common import get_evaluation_manager_nodes


class TestLargeCyclesEM(RigBuildTest):
    """
    Checks that the scene has no large evaluation manager cycles. Currently the threshold is 75 nodes.
    """

    CYCLE_THRESHOLD = 75

    def __init__(self):
        super().__init__("No large cycles (EM)")

    def run(self):
        # invalidate the graph so we can query it after a build.
        cmds.evaluationManager(invalidate=True)
        evaluation_nodes: list[str] = get_evaluation_manager_nodes()

        # Evaluation Manager Cycles
        processed_nodes: set[str] = set()
        large_cycle_clusters: list[list[str]] = []
        unique_clusters: set[FrozenSet[str]] = set()
        for node in evaluation_nodes:
            if node in processed_nodes:
                continue
            cycle_cluster: list[str] = cmds.evaluationManager(cycleCluster=node)  # type: ignore
            if cycle_cluster:
                processed_nodes.update(cycle_cluster)
                if len(cycle_cluster) > self.CYCLE_THRESHOLD:
                    cluster_set = frozenset(cycle_cluster)
                    if cluster_set in unique_clusters:
                        continue
                    large_cycle_clusters.append(cycle_cluster)
                    unique_clusters.add(cluster_set)
            else:
                processed_nodes.add(node)

        cycle_sizes_and_names = (
            (len(cluster), cluster[0]) for cluster in large_cycle_clusters
        )

        if large_cycle_clusters:
            cluster_log_strings: list[str] = [
                f"{cluster_data[1]}: {cluster_data[0]} nodes"
                for cluster_data in sorted(
                    cycle_sizes_and_names, key=lambda x: x[0], reverse=True
                )
            ]
            formatted_clusters = "\n".join(cluster_log_strings)
            self.log_warn(f"Scene has large EM cluster(s): {formatted_clusters}")
            return False
        else:
            self.log_success()
            return True


class TestLargeCyclesDG(RigBuildTest):
    """
    Checks that the scene has no large dependency graph cycles. Currently the threshold is 10 nodes.
    """

    CYCLE_THRESHOLD = 10

    def __init__(self):
        super().__init__("No large cycles (DG)")

    def run(self):
        # Dependency Graph Cycles
        dg_cycle_nodes: list[str] = cmds.cycleCheck(all=True, list=True) or []  # type: ignore

        processed_nodes: set[str] = set()
        large_cycle_clusters: list[list[str]] = []
        unique_clusters: set[FrozenSet[str]] = set()
        for node in dg_cycle_nodes:
            if node in processed_nodes:
                continue
            cycle_cluster: list[str] = cmds.cycleCheck(node, list=True)  # type: ignore
            if cycle_cluster:
                processed_nodes.update(cycle_cluster)
                if len(cycle_cluster) > self.CYCLE_THRESHOLD:
                    cluster_set = frozenset(cycle_cluster)
                    if cluster_set in unique_clusters:
                        continue
                    large_cycle_clusters.append(cycle_cluster)
                    unique_clusters.add(cluster_set)
            else:
                processed_nodes.add(node)

        cycle_sizes_and_names = (
            (len(cluster), cluster[0]) for cluster in large_cycle_clusters
        )

        if large_cycle_clusters:
            cluster_log_strings: list[str] = [
                f"{cluster_data[1]}: {cluster_data[0]} nodes"
                for cluster_data in sorted(
                    cycle_sizes_and_names, key=lambda x: x[0], reverse=True
                )
            ]
            formatted_clusters = "\n".join(cluster_log_strings)
            self.log_warn(f"Scene has large DG cluster(s): {formatted_clusters}")
            return False
        else:
            self.log_success()
            return True
