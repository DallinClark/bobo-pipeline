from ...test.core import RigBuildTest
from .control import TestControlsTagged, TestControlsZeroed
from .cycle import TestCyclesDG
from .duplicate import TestDuplicateDagNames
from .joint import TestHiddenJoints
from .ng import TestNgSkinData
from .node import TestUnknownNodes

RIG_BUILD_TESTS: list[type[RigBuildTest]] = [
    TestHiddenJoints,
    TestControlsTagged,
    TestControlsZeroed,
    TestDuplicateDagNames,
    TestUnknownNodes,
    TestCyclesDG,
    TestNgSkinData,
]

__all__ = [
    "RIG_BUILD_TESTS",
    "TestDuplicateDagNames",
    "TestHiddenJoints",
    "TestNgSkinData",
    "TestUnknownNodes",
    "TestCyclesDG",
    "TestControlsTagged",
    "TestControlsZeroed",
]
