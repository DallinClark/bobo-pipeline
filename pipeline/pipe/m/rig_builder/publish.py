import logging
from typing import Callable, Iterable

from .build import RigBuilder
from .progress import ProgressStep, TestProgressManager
from .test import RIG_BUILD_TESTS, RigBuildTest, TestRunner

log = logging.getLogger(__name__)


class RigPublisher:
    def __init__(self) -> None:
        self.root_progress = ProgressStep("Build, Publish and Test")
        self.build_progress = ProgressStep("Rig Build", 15)
        self.root_progress.add_child_step(self.build_progress)
        self.test_progress = ProgressStep("Rig Test", 1)
        self.root_progress.add_child_step(self.test_progress)
        self.publish_progress = ProgressStep("Rig Publish", 2)
        self.root_progress.add_child_step(self.publish_progress)
        self.test_progress_manager: TestProgressManager | None = None
        self._test_view_update_callback: Callable[[RigBuildTest, bool], None] | None = (
            None
        )

    def connect_progress(self, progress_slot: Callable[[float], None]):
        """Stores the slot (e.g., progress_bar.update_progress) to connect later."""
        self.root_progress.connect_progress(progress_slot)

    def connect_test_view(
        self, test_view_update_callback: Callable[[RigBuildTest, bool], None]
    ):
        self._test_view_update_callback = test_view_update_callback

    def _on_test_run(self, test: RigBuildTest, passed: bool):
        if self.test_progress_manager is not None:
            self.test_progress_manager.update_progress_from_test_run(test, passed)
        if self._test_view_update_callback is not None:
            self._test_view_update_callback(test, passed)

    def _build_rig(self, rig_name: str, rig_type: str):
        rig_builder = RigBuilder()
        rig_builder.connect_progress(self.build_progress.update_progress)
        rig_builder.build_rig(rig_name, rig_type)

    def _run_tests(self, tests: Iterable[type[RigBuildTest]]) -> bool:
        self.build_progress.finish_step()
        test_objects = [test() for test in tests]
        self.test_progress_manager = TestProgressManager(
            test_objects,
        )
        self.test_progress_manager.progress_changed.connect(
            self.test_progress.update_progress
        )
        test_runner = TestRunner(test_objects, self._on_test_run)
        return test_runner.run_tests()

    def _publish_rig(self, rig_name: str):
        self.publish_progress.finish_step()
        log.info(
            f"{rig_name} would have just been published if publishing was implemented :)"
        )

        pass

    def build_test_and_publish(self, rig_name: str, rig_type: str):
        self._build_rig(rig_name, rig_type)
        tests_passed = self._run_tests(RIG_BUILD_TESTS)
        if tests_passed:
            self._publish_rig(rig_name)
        else:
            log.error(
                f"{rig_name} failed one or more required tests and wasn't published!"
            )
            return
