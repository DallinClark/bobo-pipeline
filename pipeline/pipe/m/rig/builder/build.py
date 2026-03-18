from contextlib import contextmanager
import logging
from typing import Callable

from maya import cmds
from .progress import RigBuildProgressManager
from shared.util import get_rig_build_path

log = logging.getLogger(__name__)


@contextmanager
def redirect_external_logger(
    external_logger: logging.Logger, target_logger: logging.Logger
):
    """Temporarily hooks an external logger into a specified target."""

    # Store original state
    original_parent = external_logger.parent
    original_propagate = external_logger.propagate

    try:
        external_logger.parent = target_logger
        external_logger.propagate = True
        yield external_logger
    finally:
        # Restore original state exactly as it was
        external_logger.parent = original_parent
        external_logger.propagate = original_propagate


class RigBuilder:
    def __init__(self) -> None:
        self._progress_slot: Callable[[float], None] | None = None
        pass

    def connect_progress(self, progress_slot: Callable[[float], None]):
        """Stores the slot (e.g., progress_bar.update_progress) to connect later."""
        self._progress_slot = progress_slot

    def build_rig(
        self,
        rig_name: str,
        rig_type: str,
        rig_variant: str | None = None,
        dev_build: bool = False,
    ) -> bool:
        """
        This function is meant to call the rig build of an external rigging library (currently y-rig).
        However I hope that it is easy enough to change that if needed the underlying rig build system
        could be replaced without any trouble.

        It should return a bool: True if the rig built successfully and False if it failed or was cancelled.
        """
        from yrig.build.mgear_api import build_from_path

        # Grab the external logger
        build_logger = logging.getLogger("yrig")

        # Get paths.
        rig_build_path = get_rig_build_path() / rig_type / rig_name
        guide_path = rig_build_path / "data/guide.sgt"

        if not guide_path.exists():
            error_message = f"Couldn't find the build data for {rig_name}. The build file should be located at {guide_path}"
            log.error(error_message)
            raise FileNotFoundError(error_message)

        progress_manager = RigBuildProgressManager()
        if self._progress_slot is not None:
            progress_manager.progress_changed.connect(self._progress_slot)
        with redirect_external_logger(build_logger, log):
            cmds.file(newFile=True, force=True)
            build_result = build_from_path(
                rig_build_path,
                dev_build,
                progress_manager.update_progress_with_step,
            )
        if build_result is False:
            return False  # Early return to avoid finishing the progress bar
        progress_manager.update_progress_with_step(1)
        return build_result
