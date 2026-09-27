"""Run this file from a Houdini shelf tool to open the assistant."""
import sys
from pathlib import Path
import hou

root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
from panel_install import prepare_panel
hou.pypanel.installFile(str(prepare_panel(root)))
hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.PythonPanel,
                                         python_panel_interface='houdini_astra')
