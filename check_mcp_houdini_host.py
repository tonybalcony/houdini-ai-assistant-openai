"""Disposable Houdini scene used by check_mcp.py; never loads a user scene."""
import json
import queue
import sys
import threading

import hou
from PySide6 import QtCore, QtWidgets
from mcp_session import HoudiniMcpSession

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
session = HoudiniMcpSession()
hou.node('/obj').createNode('geo', 'MCP_INTEGRATION_TEST', run_init_scripts=False)
port = session.start()
print(json.dumps({'ready': True, 'port': port}), flush=True)
messages = queue.Queue()
threading.Thread(target=lambda: messages.put(sys.stdin.readline()), daemon=True).start()
timer = QtCore.QTimer()
timer.timeout.connect(lambda: app.quit() if not messages.empty() else None)
timer.start(100)
try:
    app.exec()
finally:
    session.stop()
