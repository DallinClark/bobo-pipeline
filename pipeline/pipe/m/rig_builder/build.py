from contextlib import contextmanager
import logging
from typing import Callable
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
    ):
        """
        This function is meant to call the rig build of an external rigging library (currently y-rig).
        However I hope that it is easy enough to change that if needed the underlying rig build system
        could be replaced without any trouble.
        """
        from yrig.build.mgear_api import build_from_file

        # 1. Grab the external logger
        build_logger = logging.getLogger("yrig")

        rig_build_filepath = (
            get_rig_build_path() / rig_type / rig_name / "data/template.sgt"
        )

        if not rig_build_filepath.exists():
            log.error(
                f"Couldn't find the build data for {rig_name}. The build file should be located at {rig_build_filepath}"
            )
            raise FileNotFoundError(
                f"Couldn't find the build data for {rig_name}. The build file should be located at {rig_build_filepath}"
            )

        with redirect_external_logger(build_logger, log):
            build_from_file(
                get_rig_build_path() / rig_type / rig_name / "data/guide.sgt",
                dev_build,
            )
