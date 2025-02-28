from __future__ import annotations

from Qt import QtWidgets

import substance_painter as sp

import pipe.sp
from pipe.sp.ui import SubstanceExportWindow
from pipe.glui.dialogs import MessageDialog


plugin_widgets: list[QtWidgets.QWidget] = []


def start_plugin():
    # Create text widget for menu
    action = QtWidgets.QAction("Bobo — Publish Textures")
    action.triggered.connect(launch_exporter)

    # Add widget to the File menu
    sp.ui.add_action(sp.ui.ApplicationMenu.File, action)

    # Store the widget for proper cleanup later
    plugin_widgets.append(action)

    # Create text widget for menu
    action = QtWidgets.QAction("Bobo — Publish Batch")
    action.triggered.connect(launch_batch_exporter)

    # Add widget to the File menu
    sp.ui.add_action(sp.ui.ApplicationMenu.File, action)

    # Store the widget for proper cleanup later
    plugin_widgets.append(action)


def close_plugin():
    for widget in plugin_widgets:
        sp.ui.delete_ui_element(widget)

    plugin_widgets.clear()


if __name__ == "__main__":
    window = start_plugin()


def launch_batch_exporter():
    launch_exporter(is_batch=True)
    print("Launching Batch Exporter")


def launch_exporter(is_batch: bool = False):
    if not sp.project.is_open():
        MessageDialog(
            pipe.sp.local.get_main_qt_window(),
            "Please open a project before trying to publish",
            "No project open",
        ).exec_()
        return

    # remove existing windows before opening a new one
    for widget in plugin_widgets:
        if isinstance(widget, SubstanceExportWindow):
            widget.close()
            sp.ui.delete_ui_element(widget)
            plugin_widgets.remove(widget)
            break

    # launch window
    global window
    window = SubstanceExportWindow(is_batch=is_batch)
    window.show()

    print("Launching Substance Exporter")
