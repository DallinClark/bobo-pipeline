from pipe.m.rig_builder.test.core import RigBuildTest

from .cycle import TestLargeCycles
from .duplicate import TestDuplicateDagNames
from .joint import TestHiddenJoints
from .ng import TestNgSkinData
from .node import TestUnknownNodes

RIG_BUILD_TESTS: list[type[RigBuildTest]] = [
    TestHiddenJoints,
    TestUnknownNodes,
    TestDuplicateDagNames,
    TestNgSkinData,
    TestLargeCycles,
]

__all__ = [
    "RIG_BUILD_TESTS",
    "TestDuplicateDagNames",
    "TestHiddenJoints",
    "TestNgSkinData",
    "TestUnknownNodes",
    "TestLargeCycles",
]
