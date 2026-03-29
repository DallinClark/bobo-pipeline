from ...test.core import RigBuildTest
from .control import TestControlsInSet, TestControlsTagged, TestControlsZeroed
from .cycle import TestCyclesDG
from .duplicate import TestDuplicateDagNames
from .geo import TestGeoInSet
from .hierarchy import TestSingleHierachy
from .joint import TestHiddenJoints
from .namespace import TestNamespaces
from .ng import TestNgSkinData
from .node import TestUnknownNodes
from .root_transform import TestRootRotate, TestRootScale, TestRootTranslation

RIG_BUILD_TESTS: list[type[RigBuildTest]] = [
    TestHiddenJoints,
    TestControlsInSet,
    TestControlsTagged,
    TestControlsZeroed,
    TestDuplicateDagNames,
    TestGeoInSet,
    TestSingleHierachy,
    TestNamespaces,
    TestUnknownNodes,
    TestCyclesDG,
    TestNgSkinData,
    TestRootTranslation,
    TestRootRotate,
    TestRootScale,
]

__all__ = [
    "RIG_BUILD_TESTS",
    "TestControlsInSet",
    "TestControlsTagged",
    "TestControlsZeroed",
    "TestCyclesDG",
    "TestDuplicateDagNames",
    "TestGeoInSet",
    "TestSingleHierachy",
    "TestHiddenJoints",
    "TestNamespaces",
    "TestNgSkinData",
    "TestUnknownNodes",
    "TestRootTranslation",
    "TestRootRotate",
    "TestRootScale",
]
