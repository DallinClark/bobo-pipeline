from maya import cmds

from .. import RigBuildTest


class TestNgSkinData(RigBuildTest):
    """
    Checks that the scene has no ngst2SkinLayerData nodes.
    These are the nodes that store the layer information for Ng Skin Tools and they can easily become very big and bloat the rig file.
    Their data is baked into the skinCluster node weights during each painting step anyways, so they should be deleted for final rig publish.
    """

    def __init__(self):
        super().__init__("No NgSkinTools data nodes")

    def run(self) -> bool:
        ng_data_nodes = cmds.ls(type="ngst2SkinLayerData")
        if ng_data_nodes:
            self.log_warn(f"Scene has ngst2SkinLayerData nodes: {ng_data_nodes}")
            return False
        else:
            self.log_success()
            return True
