from .duplicates import TestDuplicateDagNames
from .joints import TestHiddenJoints
from .ng import TestNgSkinData
from .nodes import TestUnknownNodes

RIG_BUILD_TESTS = [
    TestHiddenJoints(),
    TestUnknownNodes(),
    TestDuplicateDagNames(),
    TestNgSkinData(),
]

__all__ = [
    "RIG_BUILD_TESTS",
    "TestDuplicateDagNames",
    "TestHiddenJoints",
    "TestNgSkinData",
    "TestUnknownNodes",
]
