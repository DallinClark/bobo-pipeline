from __future__ import annotations

import logging

from maya import cmds
from maya.OpenMayaUI import MQtUtil
from Qt.QtWidgets import QWidget

from .. import build

from ...local import get_main_qt_window
from .core import (
    check_and_restore_workspace_control,
    delete_workspace_control,
    get_maya_main_window,
)
from .window_ui import RigBuilderWindowUI

_window_instance: RigBuilderWindow | None = None

WINDOW_OBJECT_NAME = "rigBuilderWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"

# This uiScript is called by Maya to recreate the widget when restoring layout.
# It must be a string that Maya can evaluate via Python.
UI_SCRIPT = """
import pipe.m.rig_builder.ui
pipe.m.rig_builder.ui.window._restore()
"""


def _restore() -> None:
    """Called by Maya's workspaceControl restore mechanism."""
    global _window_instance

    # Always recreate the widget on restore
    _window_instance = RigBuilderWindow(parent=get_maya_main_window())  # type: ignore

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

    delete_workspace_control(WORKSPACE_CONTROL_NAME)

    _window_instance = RigBuilderWindow(parent=get_main_qt_window())  # type: ignore
    _window_instance.show(
        dockable=True,  # type: ignore
        uiScript=UI_SCRIPT,  # type: ignore
        workspaceControlName=WORKSPACE_CONTROL_NAME,  # type: ignore
    )


class RigBuilderWindow(RigBuilderWindowUI):
    def __init__(
        self,
        parent: QWidget | None,
    ) -> None:
        super().__init__(parent=parent, window_object_name=WINDOW_OBJECT_NAME)
        self.connect_ui()

    def connect_ui(self):
        self.enable_tests_button.clicked.connect(self.test_list.enable_all_tests)
        self.disable_tests_button.clicked.connect(self.test_list.disable_all_tests)

        self.rig_test_button.clicked.connect(self.rig_build_log_box.clear_log)
        self.rig_test_button.clicked.connect(self.test_list.run_tests)
        test_logger = logging.getLogger("pipe.m.rig_builder.test")
        test_logger.setLevel(logging.DEBUG)
        self.rig_build_log_box.connect_test_logger(test_logger)

        self.build_rig_button.clicked.connect(self._build_rig)
        build_logger = logging.getLogger("pipe.m.rig_builder.build")
        build_logger.setLevel(logging.DEBUG)
        self.rig_build_log_box.connect_logger(build_logger)

    def _build_rig(self):
        build.build_rig("yoon")
