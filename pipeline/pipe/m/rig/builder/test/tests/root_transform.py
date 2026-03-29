from typing import Iterable

import numpy as np
from maya import cmds
from maya.api.OpenMaya import (
    MDagPath,
    MEulerRotation,
    MFnMesh,
    MFnTransform,
    MItDag,
    MMatrix,
    MPointArray,
    MSelectionList,
    MSpace,
    MVector,
)
from numpy.typing import NDArray

from .. import RigBuildTest
from ..common import get_all_visible_meshes, get_dag_path, is_control

EPSILON: float = 0.01


def _get_root_control() -> str | None:
    it = MItDag(MItDag.kBreadthFirst)
    while not it.isDone():
        dag: MDagPath = it.getPath()
        name = dag.partialPathName()
        if not name:
            it.next()
            continue
        if is_control(name, strict=False):
            return name
        it.next()
    return None


def _get_visible_mesh_shapes() -> list[str]:
    visible_mesh_transforms = get_all_visible_meshes()
    visible_mesh_shapes: list[str] = [
        shape
        for mesh in visible_mesh_transforms
        for shape in (
            cmds.listRelatives(mesh, shapes=True, type="mesh", noIntermediate=True)
            or []
        )
    ]
    return visible_mesh_shapes


def _get_mesh_points(mesh_shape: str) -> NDArray[np.float64]:
    msel: MSelectionList = MSelectionList()
    msel.add(mesh_shape)
    mesh_dag: MDagPath = msel.getDagPath(0)

    # make the function set and get the points
    fn_mesh: MFnMesh = MFnMesh(mesh_dag)

    mesh_points: MPointArray = fn_mesh.getPoints(space=MSpace.kWorld)
    np_points = np.array(
        [[pt.x, pt.y, pt.z, pt.w] for pt in mesh_points], dtype=np.float64
    )
    return np_points


def _transform_mesh_points(
    points: NDArray[np.float64], matrix: MMatrix
) -> NDArray[np.float64]:
    np_matrix = np.array(matrix, dtype=np.float64).reshape(4, 4)
    return points @ np_matrix


def _compare_points(
    current_points: NDArray[np.float64],
    expected_points: NDArray[np.float64],
    epsilon: float = EPSILON,
) -> bool:
    return np.allclose(current_points, expected_points, atol=EPSILON)


def _compare_before_after_transform(
    control: str,
    meshes: Iterable[str],
    translation: tuple[float, float, float] | None = None,
    rotation: tuple[float, float, float] | None = None,
    scale: tuple[float, float, float] | None = None,
) -> bool:
    mesh_points_mapping = {mesh: _get_mesh_points(mesh) for mesh in meshes}

    control_dag = get_dag_path(control)
    transform_mfn = MFnTransform(control_dag)
    original_world_matrix: MMatrix = control_dag.inclusiveMatrix()

    original_translation = transform_mfn.translation(MSpace.kTransform)
    original_rotation = transform_mfn.rotation(MSpace.kTransform)
    original_scale = transform_mfn.scale()

    # Apply our transform
    if translation is not None:
        transform_mfn.translateBy(MVector(translation), MSpace.kTransform)
    if rotation is not None:
        transform_mfn.rotateBy(MEulerRotation(rotation), MSpace.kTransform)
    if scale is not None:
        transform_mfn.scaleBy(scale)

    new_world_matrix: MMatrix = control_dag.inclusiveMatrix()
    offset_matrix = original_world_matrix.inverse() * new_world_matrix
    all_match = True
    for mesh, original_points in mesh_points_mapping.items():
        # Transform the original points by the offset
        transformed_points = _transform_mesh_points(original_points, offset_matrix)
        new_points = _get_mesh_points(mesh)
        if not _compare_points(transformed_points, new_points):
            all_match = False
            break

    # Reset transform
    if translation is not None:
        transform_mfn.setTranslation(original_translation, MSpace.kTransform)
    if rotation is not None:
        transform_mfn.setRotation(original_rotation, MSpace.kTransform)
    if scale is not None:
        transform_mfn.setScale(original_scale)

    return all_match


class TestRootTranslation(RigBuildTest):
    """
    Checks that scaling the root control behaves as expected (a rigid transformation of the points).
    """

    def __init__(self):
        super().__init__("Root control translation")

    def run(self) -> bool:
        root_control = _get_root_control()
        if root_control is None:
            self.log_warn("Rig had no root control")
            return False
        visible_mesh_shapes = _get_visible_mesh_shapes()
        translation_value = (1, 1, 1)
        passed = _compare_before_after_transform(
            control=root_control,
            meshes=visible_mesh_shapes,
            translation=translation_value,
        )
        if not passed:
            self.log_warn(
                f"Rig did not behave properly when {root_control} was translated by {translation_value}"
            )
            return False
        else:
            self.log_success()
            return True


class TestRootRotate(RigBuildTest):
    """
    Checks that scaling the root control behaves as expected (a rigid transformation of the points).
    """

    def __init__(self):
        super().__init__("Root control rotate")

    def run(self) -> bool:
        root_control = _get_root_control()
        if root_control is None:
            self.log_warn("Rig had no root control")
            return False
        visible_mesh_shapes = _get_visible_mesh_shapes()
        rotation_value = (0, 90, 0)
        passed = _compare_before_after_transform(
            control=root_control,
            meshes=visible_mesh_shapes,
            rotation=rotation_value,
        )
        if not passed:
            self.log_warn(
                f"Rig did not behave properly when {root_control} was rotated by {rotation_value}"
            )
            return False
        else:
            self.log_success()
            return True


class TestRootScale(RigBuildTest):
    """
    Checks that scaling the root control behaves as expected (a rigid transformation of the points).
    """

    def __init__(self):
        super().__init__("Root control scale")

    def run(self) -> bool:
        root_control = _get_root_control()
        if root_control is None:
            self.log_warn("Rig had no root control")
            return False
        visible_mesh_shapes = _get_visible_mesh_shapes()
        scale_value = (5, 5, 5)
        passed = _compare_before_after_transform(
            control=root_control, meshes=visible_mesh_shapes, scale=scale_value
        )
        if not passed:
            self.log_warn(
                f"Rig did not behave properly when {root_control} was scaled by {scale_value}"
            )
            return False
        else:
            self.log_success()
            return True
