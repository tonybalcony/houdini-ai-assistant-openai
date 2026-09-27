"""Shelf entry: show onboarding only when needed, otherwise open the saved account."""
from pathlib import Path
import hou
from PySide6 import QtCore
from shiboken6 import isValid
import bootstrap
from panel_install import prepare_panel
from user_account import preferences

ROOT=Path(__file__).resolve().parent
_dialog=None


def show_panel(backend=None):
    hou.pypanel.installFile(str(prepare_panel(ROOT)))
    pane=hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.PythonPanel,
                                                 python_panel_interface='houdini_astra')
    def connect_when_ready(attempt=0):
        try:
            widget=pane.activeInterfaceRootWidget()
        except hou.Error:
            return  # The user may close the pane before it finishes loading.
        if widget is not None:
            widget.start_saved_connection(backend)
        elif attempt<100:
            QtCore.QTimer.singleShot(100,lambda:connect_when_ready(attempt+1))
    QtCore.QTimer.singleShot(0,connect_when_ready)
    return pane


def account_setup(parent=None,on_ready=None):
    global _dialog
    if _dialog is not None and isValid(_dialog) and _dialog.isVisible():
        _dialog.raise_()
        _dialog.activateWindow()
        return _dialog
    from setup_ui import SetupDialog
    # The panel may close while installation is running. Keep the installer owned
    # by Houdini's main window so destroying a panel cannot destroy a live QThread.
    _dialog=SetupDialog(hou.qt.mainWindow())
    if on_ready:
        _dialog.ready.connect(on_ready)
    _dialog.show()
    return _dialog


def launch():
    if bootstrap.ready() and preferences().get('onboarding_complete'):
        return show_panel()
    return account_setup(on_ready=show_panel)
