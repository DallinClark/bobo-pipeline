from maya import cmds

from .. import RigBuildTest
from ..common import (
    GEO_SET_NAME,
    format_max_items,
    get_all_visible_meshes,
    is_control,
)


class TestGeoInSet(RigBuildTest):
    """
    Checks that the scene has no visible geometry that isn't in the geo set.
    This set is used for animation export and as such all non-control visible geometry should be in it.
    """

    def __init__(self):
        super().__init__("All geometry in set")

    def run(self) -> bool:
        visible_geo: set[str] = set(get_all_visible_meshes())
        problem_meshes: set[str]
        try:
            meshes_in_set: list[str] = cmds.sets(GEO_SET_NAME, query=True)  # type: ignore
            visible_meshes_not_in_set = visible_geo - set(meshes_in_set)
            problem_meshes = set(
                mesh for mesh in visible_meshes_not_in_set if not is_control(mesh)
            )
        except ValueError:
            problem_meshes = visible_geo

        if problem_meshes:
            self.log_warn(
                f"Scene has geometry that isn't in the geo set: "
                f'{format_max_items(problem_meshes, "mesh(es)")} needs added to the "{GEO_SET_NAME}" set.'
            )
            return False
        else:
            self.log_success()
            return True
