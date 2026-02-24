from maya import cmds

from .. import RigBuildTest
from ..util import get_evaluation_manager_nodes


class TestLargeCycles(RigBuildTest):
    """
    Checks that the scene has no large cycles. Currently the threshold is 75 nodes.
    """

    CYCLE_THRESHOLD = 75

    def __init__(self):
        super().__init__("No large cycles")

    def run(self):
        cmds.evaluationManager(invalidate=True)
        evaluation_nodes: list[str] = get_evaluation_manager_nodes()

        processed_nodes: set[str] = set()
        large_cycle_clusters: list[list[str]] = []

        for node in evaluation_nodes:
            if node in processed_nodes:
                continue
            cycle_cluster: list[str] = cmds.evaluationManager(cycleCluster=node)  # type: ignore
            processed_nodes = processed_nodes.union(cycle_cluster)
            if len(cycle_cluster) > self.CYCLE_THRESHOLD:
                large_cycle_clusters.append(cycle_cluster)

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
            self.log_warn(f"Scene has large cluster(s): {formatted_clusters}")
            return False
        else:
            self.log_success()
            return True
