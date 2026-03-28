from ...test.core import RigBuildTest
from .control import TestControlsInSet, TestControlsTagged, TestControlsZeroed
from .cycle import TestCyclesDG
from .duplicate import TestDuplicateDagNames
from .geo import TestGeoInSet
from .joint import TestHiddenJoints
from .ng import TestNgSkinData
from .node import TestUnknownNodes

RIG_BUILD_TESTS: list[type[RigBuildTest]] = [
    TestHiddenJoints,
    TestControlsInSet,
    TestControlsTagged,
    TestControlsZeroed,
    TestDuplicateDagNames,
    TestGeoInSet,
    TestUnknownNodes,
    TestCyclesDG,
    TestNgSkinData,
]

__all__ = [
    "RIG_BUILD_TESTS",
    "TestControlsInSet",
    "TestControlsTagged",
    "TestControlsZeroed",
    "TestCyclesDG",
    "TestDuplicateDagNames",
    "TestGeoInSet",
    "TestHiddenJoints",
    "TestNgSkinData",
    "TestUnknownNodes",
]
