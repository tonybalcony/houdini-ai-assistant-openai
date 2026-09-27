"""One half of the real two-process restart check; called only by check_chat_restart.py."""
import json
from pathlib import Path
import sys
import time
import hou
from PySide6 import QtCore, QtWidgets
from astra_panel import AstraPanel
from chat_store import ChatStore

phase, directory = int(sys.argv[1]), Path(sys.argv[2])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
scene_name = 'FIRST_SESSION' if phase == 1 else 'SECOND_SESSION'
hou.node('/obj').createNode('geo', scene_name, run_init_scripts=False)
panel = AstraPanel(chat_store=ChatStore(directory))
if phase == 1:
    panel.model.setCurrentIndex(2)
else:
    assert panel.chat is not None and panel.reopened_chat
    assert 'cedar lantern' in panel.transcript.toPlainText().lower()
panel.effort.setCurrentIndex(0)
panel.connect_worker()
sent, finished, failure = False, False, None
started = time.monotonic()
timer = QtCore.QTimer()


def poll():
    global sent, finished, failure
    try:
        if time.monotonic() - started > 200:
            raise TimeoutError('Restart check timed out')
        if panel.errors and not panel.busy:
            raise RuntimeError(' | '.join(panel.errors))
        if not sent and panel.connected:
            text = ('Our project nickname is cedar lantern. Remember it. Use Houdini MCP get_scene_info '
                    'to inspect this scene and report the only geometry object directly under /obj. '
                    'Reply in one sentence with the nickname and object name. Do not edit anything.' if phase == 1 else
                    'What was our project nickname? Use Houdini MCP get_scene_info again to inspect '
                    'the CURRENT scene and report the only geometry object directly under /obj. '
                    'Reply in one sentence with the remembered nickname and current object name. Do not edit anything.')
            panel.input.setPlainText(text)
            panel.send()
            sent = True
        elif sent and not panel.busy:
            assert panel.last_run_status == 'completed', panel.errors
            answer = panel.transcript.toPlainText().split('Astra:')[-1]
            assert 'cedar lantern' in answer.lower(), answer
            assert scene_name in answer, answer
            assert any(r['tool'] == 'mcp:get_scene_info' and r['result']['status'] == 'completed'
                       for r in panel.last_tool_results), panel.last_tool_results
            record = panel.chat_store.get(panel.chat['id'])
            (directory / f'phase{phase}.json').write_text(json.dumps({
                'passed': True, 'chat_id': record['id'], 'thread_id': record['codex_thread_id'],
                'model': record['model'], 'answer': answer.strip(),
                'mcp_port': panel.mcp_session.port,
                'resumed': panel.reopened_chat,
            }, indent=2), encoding='utf-8')
            finished = True
            timer.stop()
            panel.shutdown()
            app.quit()
    except Exception as exc:
        failure = str(exc)
        timer.stop()
        panel.shutdown()
        app.quit()


timer.timeout.connect(poll)
timer.start(100)
app.exec()
assert finished and not failure, failure or 'Did not finish'
print(f'PASS: Houdini session {phase}, model memory and live MCP scene inspection', flush=True)
