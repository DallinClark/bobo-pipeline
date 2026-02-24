import logging
from typing import Callable, Iterable

from .build import RigBuilder
from .progress import ProgressManager
from .test import RIG_BUILD_TESTS, RigBuildTest, TestRunner

log = logging.getLogger(__name__)


class RigPublisher:
    def __init__(self) -> None:
        self._progress_slot: Callable[[float], None] | None = None
        pass

    def connect_progress(self, progress_slot: Callable[[float], None]):
        """Stores the slot (e.g., progress_bar.update_progress) to connect later."""
        self._progress_slot = progress_slot

    def _build_rig(self, rig_name: str, rig_type: str):
        rig_builder = RigBuilder()
        rig_builder.build_rig(rig_name, rig_type)

    def _run_tests(self, tests: Iterable[type[RigBuildTest]]) -> bool:
        test_runner = TestRunner(test() for test in tests)
        return test_runner.run_tests()

    def _publish_rig(self, rig_name: str):
        log.info(
            f"{rig_name} would have just been published if publishing was implemented :)"
        )
        pass

    def build_test_and_publish(self, rig_name: str, rig_type: str):
        progress_manager = ProgressManager()
        if self._progress_slot is not None:
            progress_manager.progress_changed.connect(self._progress_slot)
        self._build_rig(rig_name, rig_type)
        tests_passed = self._run_tests(RIG_BUILD_TESTS)
        if tests_passed:
            self._publish_rig(rig_name)
