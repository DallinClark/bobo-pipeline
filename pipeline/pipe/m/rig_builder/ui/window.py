from __future__ import annotations

from maya.OpenMayaUI import MQtUtil
from Qt.QtWidgets import QWidget

from .core import delete_workspace_control, get_maya_main_window
from .window_ui import RigBuilderWindowUI

_window_instance: RigBuilderWindow | None = None

WINDOW_OBJECT_NAME = "rigBuilderWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"

# This uiScript is called by Maya to recreate the widget when restoring layout.
# It must be a string that Maya can evaluate via Python.
UI_SCRIPT = """
import pipe.m.rig_builder.ui.window
pipe.m.rig_builder.ui.window._restore()
"""


def _restore() -> None:
    """Called by Maya's workspaceControl restore mechanism."""
    global _window_instance

    # Always recreate the widget on restore
    _window_instance = RigBuilderWindow(parent=get_maya_main_window())

    # Tell Maya this is a restore operation
    _window_instance.show(
        dockable=True,
        workspaceControlName=WORKSPACE_CONTROL_NAME,
        restore=True,
    )
    # Locate the workspace control that Maya already created.
    workspace_ptr = MQtUtil.findControl(WORKSPACE_CONTROL_NAME)
    # Get a pointer to our widget so we can hand it to Maya.
    widget_ptr = MQtUtil.findControl(_window_instance.objectName())
    if workspace_ptr and widget_ptr:
        MQtUtil.addWidgetToMayaLayout(int(widget_ptr), int(workspace_ptr))


def close() -> None:
    global _window_instance
    if _window_instance is not None:
        _window_instance.close()


def launch() -> None:
    global _window_instance
    if _window_instance is not None:
        _window_instance.close()

    delete_workspace_control(WORKSPACE_CONTROL_NAME)

    _window_instance = RigBuilderWindow(parent=get_maya_main_window())
    _window_instance.show(
        dockable=True,
        uiScript=UI_SCRIPT,
        workspaceControlName=WORKSPACE_CONTROL_NAME,
    )


class RigBuilderWindow(RigBuilderWindowUI):
    def __init__(
        self,
        parent: QWidget | None,
    ) -> None:
        super().__init__(parent=parent, window_object_name=WINDOW_OBJECT_NAME)
        self.connect_ui()

    def connect_ui(self):
        pass
