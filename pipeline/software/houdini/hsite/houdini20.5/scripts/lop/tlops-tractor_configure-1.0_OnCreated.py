import hou

try:
    me: hou.Node = kwargs["node"]  # type: ignore[name-defined] # noqa: F821
    overscan = me.parm("overscan")
    assert overscan is not None
    overscan.set(6.0)
except Exception:  # in case this is created as a locked node
    pass
