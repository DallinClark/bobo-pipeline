import hou

try:
    me: hou.Node = kwargs["node"]  # type: ignore[name-defined] # noqa: F821
    basename = me.parm("basename")
    assert basename is not None
    basename.set("$OS")
except Exception:  # in case this is created as a locked node
    pass
