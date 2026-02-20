from __future__ import annotations

import Qt
from maya import cmds
from maya.api.OpenMaya import MSceneMessage
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin  # type: ignore
from maya.OpenMayaUI import MQtUtil
from Qt.QtCompat import wrapInstance
from Qt.QtCore import QObject
from Qt.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .core import delete_workspace_control, get_maya_main_window

_window_instance: RigBuilderWindow | None = None

WINDOW_OBJECT_NAME = "rigBuilderWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"

# This uiScript is called by Maya to recreate the widget when restoring layout.
# It must be a string that Maya can evaluate via Python.
UI_SCRIPT = """
import rig_builder.ui.window
rig_builder.ui.window._restore()
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


class RigBuilderWindow(MayaQWidgetDockableMixin, QWidget):
    def __init__(
        self,
        parent,
    ) -> None:
        super().__init__(parent=parent)
        self.setup_ui()

    def setup_ui(self):
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("The Rig-Build-inator")

        # ---------- MAIN LAYOUT ----------
        main_layout = QVBoxLayout(self)
        self.setLayout(main_layout)

        self.main_splitter = QSplitter()
        self.main_splitter.setOrientation(Qt.QtCore.Qt.Vertical)
        main_layout.addWidget(self.main_splitter)

        # Build Section
        self.top_container = QWidget()
        self.main_splitter.addWidget(self.top_container)

        self.top_layout = QVBoxLayout(self.top_container)
        self.top_layout.setContentsMargins(0, 8, 0, 8)
        self.build_label = QLabel()
        self.build_label.setText("Build")
        self.top_layout.addWidget(self.build_label)
        self.build_tabs = QTabWidget()
        self.top_layout.addWidget(self.build_tabs)

        # Build Options
        self.build_horizontal_layout = QHBoxLayout()
        self.top_layout.addLayout(self.build_horizontal_layout)

        self.dev_build_switch = QCheckBox()
        self.dev_build_switch.setText("Dev Build")
        self.build_horizontal_layout.addWidget(self.dev_build_switch, 1)

        self.dev_build_switch = QPushButton()
        self.dev_build_switch.setText("Build Rig")
        self.build_horizontal_layout.addWidget(self.dev_build_switch, 2)

        # Test Section
        self.mid_container = QWidget()
        self.main_splitter.addWidget(self.mid_container)

        self.mid_layout = QVBoxLayout(self.mid_container)
        self.test_label = QLabel()
        self.test_label.setText("Test")
        self.mid_layout.addWidget(self.test_label)

        self.test_list = QListView()
        self.mid_layout.addWidget(self.test_list)

        self.rig_test_button = QPushButton()
        self.rig_test_button.setText("Run Selected Tests")
        self.mid_layout.addWidget(self.rig_test_button)

        # Publish Section
        self.publish_label = QLabel()
        self.publish_label.setText("Publish")
        self.mid_layout.addWidget(self.publish_label)

        # Publish Options
        self.publish_horizontal_layout = QHBoxLayout()
        self.mid_layout.addLayout(self.publish_horizontal_layout)

        self.rig_version_spinbox = QDoubleSpinBox()
        self.rig_version_spinbox.setPrefix("v")
        self.rig_version_spinbox.setValue(1)
        self.publish_horizontal_layout.addWidget(self.rig_version_spinbox, 1)

        self.rig_publish_button = QPushButton()
        self.rig_publish_button.setText("Build Test and Publish")
        self.publish_horizontal_layout.addWidget(self.rig_publish_button, 2)

        # Build Log Section
        self.rig_build_progress_bar = QProgressBar()
        self.mid_layout.addWidget(self.rig_build_progress_bar)

        self.bottom_container = QWidget()
        self.main_splitter.addWidget(self.bottom_container)
        self.bottom_layout = QVBoxLayout(self.bottom_container)
        self.rig_build_log_box = QPlainTextEdit()
        self.rig_build_log_box.setPlainText("Rig Build Log")
        self.rig_build_log_box.setReadOnly(True)
        self.bottom_layout.addWidget(self.rig_build_log_box)
