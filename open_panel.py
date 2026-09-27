"""Run this file from a Houdini shelf tool to open the assistant."""
import sys
from pathlib import Path
import hou

root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
from launch_ui import launch
launch()
