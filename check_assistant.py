"""Compatibility entry point for the new SDK integration checks."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name("check_sdk_assistant.py")), run_name="__main__")
