from abc import ABC, abstractmethod
from typing import Any, Callable, Sequence

from Qt.QtCore import QObject, Signal

from .test import RigBuildTest

class ProgressManager(QObject):
    progress_changed: Signal = Signal(float)

    def __init__(self):
        super().__init__()
        self._progress = 0

    def reset_progress(self):
        self._progress = 0
        self.progress_changed.emit(self._progress)

    def get_progress(self) -> float:
        """Gives a progress between 0 and 1"""
        return self._progress

    @abstractmethod
    def update_progress(self):
        pass


class RigBuildProgressManager(ProgressManager):
    def __init__(
        self,
        rig_builder: RigBuilder,
    ):
        super().__init__()
        self.reset_progress()

    def update_progress(self):
        self.progress_changed.emit(self._progress)

class TestProgressManager(ProgressManager):
    def __init__(
        self,
        tests: Sequence[RigBuildTest],
    ):
        super().__init__()
        self._total_tests = len(tests)
        self.reset_progress()

    def update_progress(self):
        self._progress += 1 / self._total_tests
        self.progress_changed.emit(self._progress)
