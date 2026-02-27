from maya import cmds

from .. import RigBuildTest
from ..common import get_all_controls_by_name


class TestControlsZeroed(RigBuildTest):
    """
    Checks that the scene has no controls that aren't zeroed (translate rotate scale shear).
    If a control has a dagPose node that can be used to return to rest pose, the control will also pass.
    """

    def __init__(self):
        super().__init__("All controls zeroed")

    def run(self) -> bool:
        controls = get_all_controls_by_name()

        EPSILON = 0.0001
        defaults: dict[str, tuple[float, float, float]] = {
            "translate": (0.0, 0.0, 0.0),
            "rotate": (0.0, 0.0, 0.0),
            "shear": (0.0, 0.0, 0.0),
            "scale": (1.0, 1.0, 1.0),
        }
        problem_controls: list[str] = []

        def has_dag_pose(control: str) -> bool:
            pose_nodes = cmds.listConnections(
                f"{control}.message", source=False, destination=True, type="dagPose"
            )
            return True if pose_nodes else False

        for control in controls:
            # If the control has a dagPose that can be used to return the control to rest positon,
            # that's better than zeroing anyway. We won't enforce zeroing for this control.
            if has_dag_pose(control):
                continue

            for attr, default_val in defaults.items():
                full_attr_path = f"{control}.{attr}"
                # If the attribute can't be set (locked) then it being zeroed doesn't matter to the animator.
                if not cmds.getAttr(full_attr_path, settable=True):
                    continue
                attr_val = cmds.getAttr(full_attr_path)[0]
                if any(
                    abs(current - default) > EPSILON
                    for current, default in zip(attr_val, default_val)
                ):
                    problem_controls.append(control)
                    break  # Move to next control as soon as one error is found

        if problem_controls:
            self.log_warn(
                f"Scene has controls with non zeroed transforms: {problem_controls}"
            )
            return False
        else:
            self.log_success()
            return True
