from typing import Sequence

from Qt.QtCore import QObject, Signal

from .test import RigBuildTest


class ProgressManager(QObject):
    progress_changed: Signal = Signal(float)

    def __init__(self):
        super().__init__()
        self._progress: float = 0

    def reset_progress(self):
        self._progress = 0
        self.progress_changed.emit(self._progress)

    def get_progress(self) -> float:
        """Gives a progress between 0 and 1"""
        return self._progress

    def update_progress(self):
        self.progress_changed.emit(self._progress)

    def update_progress_finished(self):
        self._progress = 1
        self.progress_changed.emit(self._progress)


class RigBuildProgressManager(ProgressManager):
    def __init__(
        self,
    ):
        super().__init__()
        self.reset_progress()

    def update_progress_with_step(self, progress: float, step_name: str | None = None):
        self._progress = progress
        self.update_progress()


class TestProgressManager(ProgressManager):
    def __init__(
        self,
        tests: Sequence[RigBuildTest],
    ):
        super().__init__()
        self._total_tests: int = len(tests)
        self.reset_progress()

    def update_progress_from_test_run(self, test: RigBuildTest, passed: bool):
        self._progress += 1 / self._total_tests
        self.update_progress()
