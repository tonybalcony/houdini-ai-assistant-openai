"""Compatibility entry for the SDK integration check."""
import runpy
runpy.run_module("tests.integration.check_sdk_assistant", run_name="__main__")
