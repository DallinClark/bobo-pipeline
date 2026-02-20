from Qt.QtCompat import wrapInstance
from Qt.QtWidgets import QMainWindow
from maya.OpenMayaUI import MQtUtil
from maya import cmds

def get_maya_main_window():
    mw_ptr = MQtUtil.mainWindow()
    return wrapInstance(int(mw_ptr), QMainWindow)


def delete_workspace_control(control):
    if cmds.workspaceControl(control, query=True, exists=True):
        cmds.workspaceControl(control, edit=True, close=True)
        cmds.deleteUI(control, control=True)
