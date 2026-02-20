from __future__ import annotations

import Qt
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin  # type: ignore
from Qt.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .rig_select import RigSelect
from .test_select import TestSelectList


class RigBuilderWindowUI(MayaQWidgetDockableMixin, QWidget):
    def __init__(self, parent: QWidget | None, window_object_name: str) -> None:
        super().__init__(parent=parent)
        self.window_object_name = window_object_name
        self.setup_ui()

    def setup_ui(self):
        self.setObjectName(self.window_object_name)
        self.setWindowTitle("The Rig-Build-inator")

        # ---------- MAIN LAYOUT ----------
        main_layout = QVBoxLayout(self)
        self.setLayout(main_layout)

        self.main_splitter = QSplitter()
        self.main_splitter.setOrientation(Qt.QtCore.Qt.Vertical)  # type: ignore
        main_layout.addWidget(self.main_splitter)

        # Build Section
        self.top_container = QWidget()
        self.main_splitter.addWidget(self.top_container)

        self.top_layout = QVBoxLayout(self.top_container)
        self.top_layout.setContentsMargins(0, 0, 0, 8)
        self.build_label = QLabel()
        self.build_label.setText("Build")
        self.top_layout.addWidget(self.build_label)
        self.build_tabs = QTabWidget()
        self.top_layout.addWidget(self.build_tabs)
        self.character_select = RigSelect()
        self.build_tabs.addTab(self.character_select, "Character")
        self.prop_select = RigSelect()
        self.build_tabs.addTab(self.prop_select, "Prop")

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
        self.mid_layout.setContentsMargins(0, 8, 0, 8)
        self.test_label = QLabel()
        self.test_label.setText("Test")
        self.mid_layout.addWidget(self.test_label)

        self.test_list = TestSelectList()
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
        self.rig_version_spinbox.setSingleStep(0.01)
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
        self.bottom_layout.setContentsMargins(0, 8, 0, 0)
        self.rig_build_log_box = QPlainTextEdit()
        self.rig_build_log_box.setPlainText("Rig Build Log")
        self.rig_build_log_box.setReadOnly(True)
        self.bottom_layout.addWidget(self.rig_build_log_box)
