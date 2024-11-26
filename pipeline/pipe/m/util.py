from __future__ import annotations

import maya.cmds as mc

from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Generator


@contextmanager
def maintain_selection() -> Generator[None, None, None]:
    selection = mc.ls(selection=True, long=True, ufeObjects=True, absoluteName=True)
    mc.select(clear=True)

    try:
        yield
    finally:
        mc.select(*selection, replace=True)
