"""Houdini integration checks. --live makes two small, billable Astra API turns."""
from tests.support import ARTIFACTS
import json
import sys
import time
import tempfile
from pathlib import Path
import hou
from PySide6 import QtCore, QtWidgets
import scene_tools
from astra_panel import AstraPanel
from chat_store import ChatStore

ROOT = Path(__file__).resolve().parents[2]
report = {'backend': 'OpenAI Agents SDK / Responses API', 'model': 'gpt-6-astra', 'checks': {}}
subscription = '--subscription' in sys.argv
if subscription:
    report['backend'] = 'Codex App Server / ChatGPT subscription'
checks = report['checks']
chat_directory = tempfile.TemporaryDirectory(prefix='astra-sdk-check-')
hou.hipFile.save(str(Path(chat_directory.name) / 'scene.hipnc'))
chat_store = ChatStore()


def edit(ops):
    result = scene_tools.call('houdini_edit', {'operations': ops})
    assert all(item['ok'] for item in result), result
    return result


def params(path, **values):
    return {'action': 'set_parameters', 'path': path,
            'parameters': [{'name': k, 'value': v} for k, v in values.items()]}


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
root = hou.node('/obj').createNode('geo', 'astra_sdk_check', run_init_scripts=False)
edit([{'action': 'create', 'parent': root.path(), 'type': 'box', 'name': 'box1'}])
box_path = root.path() + '/box1'
edit([params(box_path, size=[2, 3, 4]),
      {'action': 'create', 'parent': root.path(), 'type': 'null', 'name': 'OUT'},
      {'action': 'connect', 'path': root.path() + '/OUT', 'source': box_path, 'input': 0, 'output': 0},
      {'action': 'display', 'path': root.path() + '/OUT'},
      {'action': 'layout', 'path': root.path()}])
assert hou.node(box_path).parmTuple('size').eval() == (2, 3, 4)
geo = scene_tools.call('houdini_geometry', {'path': root.path() + '/OUT'})
assert geo['points'] == 8 and not geo['errors'], geo
checks['node_parameter_connection_geometry'] = True
assert scene_tools.inspect(box_path, 'size')['parameters']
assert scene_tools.call('houdini_node_types', {'parent': root.path(), 'query': 'sphere'})
checks['inspection_and_type_discovery'] = True
partial = scene_tools.apply([params(box_path, sizex=5), params(box_path, missing_parameter=1),
                            {'action': 'create', 'parent': root.path(), 'type': 'null', 'name': 'must_not_exist'}])
assert partial[0]['ok'] and not partial[1]['ok'] and hou.node(root.path() + '/must_not_exist') is None
checks['partial_failure_stops_batch'] = True
try:
    edit([{'action': 'create', 'parent': root.path(), 'type': 'null', 'name': 'invalid_batch'}, {'action': 'delete', 'path': box_path}])
    raise AssertionError('Invalid batch was accepted')
except ValueError:
    assert hou.node(root.path() + '/invalid_batch') is None
checks['invalid_batch_rejected_before_edits'] = True

from panel_install import prepare_panel
hou.pypanel.installFile(str(prepare_panel(ROOT)))
assert hou.pypanel.interfaceByName('houdini_astra')
widget = AstraPanel(chat_store=chat_store)
assert [widget.model.itemData(i) for i in range(widget.model.count())] == ['gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-terra']
widget.model.setCurrentIndex(2)
assert widget.model.currentData() == 'gpt-5.6-terra' and 'Terra' in widget.status.text()
assert not widget.connected
widget.model.setCurrentIndex(0)
checks['model_selector_and_fresh_conversation'] = True
widget.resize(740, 740)
widget.grab().save(str(ARTIFACTS / 'panel_preview.png'))
checks['panel_load_and_render'] = True
# Exercise duplicate delivery, Stop and scene-change guards without an API call.
widget.write = lambda message: True
widget.busy = True
widget.cancelled = False  # Simulate Send after switching models/reconnecting.
widget.run_id = 'offline-test'
widget.scene_file = hou.hipFile.path()
request = {'event': 'tool_request', 'run_id': 'offline-test', 'call_id': 'duplicate-test', 'tool': 'houdini_edit',
           'arguments': {'operations': [{'action': 'create', 'parent': root.path(), 'type': 'null', 'name': 'once'}]}}
widget.handle_tool(request)
widget.handle_tool(request)
assert len([n for n in root.children() if n.name().startswith('once')]) == 1
checks['duplicate_tool_delivery_executes_once'] = True
widget.cancelled = True
request['call_id'] = 'stopped-test'
request['arguments']['operations'][0]['name'] = 'blocked_by_stop'
widget.handle_tool(request)
assert hou.node(root.path() + '/blocked_by_stop') is None
checks['stop_blocks_queued_edits'] = True
widget.cancelled = False
widget.on_hip_event(hou.hipFileEventType.BeforeLoad)
request['call_id'] = 'scene-change-test'
request['arguments']['operations'][0]['name'] = 'blocked_by_scene_change'
widget.handle_tool(request)
assert hou.node(root.path() + '/blocked_by_scene_change') is None
checks['scene_change_blocks_stale_edits'] = True
widget.shutdown()
print('PASS: Houdini geometry, tools, panel, duplicate-call, Stop and scene-change checks', flush=True)

if '--live' not in sys.argv:
    (ARTIFACTS / 'validation-sdk-offline.json').write_text(json.dumps(report, indent=2))
    sys.exit(0)

widget = AstraPanel(chat_store=chat_store)
widget.resize(740, 740)
if not subscription:
    widget.backend.setCurrentIndex(1)
widget.connect_worker()
phase = 0
started = time.monotonic()
timer = QtCore.QTimer()
live_box = '/obj/astra_sdk_check/API_BOX'
usage = []


def finish(error=None):
    timer.stop()
    if error:
        report['error'] = str(error)
        print('FAIL:', error, flush=True)
    report['live_passed'] = not bool(error) and phase == 3
    report['usage'] = usage
    widget.grab().save(str(ARTIFACTS / 'panel_preview.png'))
    (ARTIFACTS / ('validation-subscription-live.json' if subscription else 'validation-sdk-live.json')).write_text(json.dumps(report, indent=2))
    widget.shutdown()
    app.quit()


def poll():
    global phase
    try:
        if time.monotonic() - started > 240:
            raise TimeoutError('Live integration check exceeded four minutes.')
        if widget.errors and not widget.busy:
            raise RuntimeError(' | '.join(widget.errors))
        if phase == 0 and widget.connected:
            checks['worker_ready'] = True
            print('PASS: ' + ('Codex subscription authenticated' if subscription else 'standalone Agents SDK worker ready'), flush=True)
            widget.effort.setCurrentIndex(0)
            widget.input.setPlainText('Inside /obj/astra_sdk_check create one box SOP named API_BOX. Set its size tuple to (2, 3, 4). Inspect its cooked geometry to verify it. Do not edit other nodes. Remember the word cobalt for my next message. Answer briefly.')
            widget.send()
            phase = 1
        elif phase == 1 and not widget.busy:
            assert widget.last_run_status == 'completed', widget.errors
            assert hou.node(live_box) is not None, 'Astra did not create API_BOX'
            assert hou.node(live_box).parmTuple('size').eval() == (2, 3, 4)
            assert any(r['tool'] == 'houdini_geometry' for r in widget.last_tool_results)
            checks['model_create_edit_verify'] = True
            usage.append(widget.usage.text())
            print('PASS: Astra created and sized a box and verified its geometry', flush=True)
            widget.input.setPlainText('Change only that box size X to 5, preserving its other dimensions. What word did I ask you to remember? Answer briefly.')
            widget.send()
            phase = 2
        elif phase == 2 and not widget.busy:
            assert widget.last_run_status == 'completed', widget.errors
            assert hou.node(live_box).parmTuple('size').eval() == (5, 3, 4)
            assert 'cobalt' in widget.transcript.toPlainText().split('Astra:')[-1].lower()
            assert hou.node(box_path).parmTuple('size').eval() == (5, 3, 4)
            checks['model_followup_and_memory'] = True
            checks['existing_geometry_preserved'] = True
            usage.append(widget.usage.text())
            phase = 3
            print('PASS: follow-up edit, conversation memory and existing geometry preservation', flush=True)
            finish()
    except Exception as exc:
        finish(exc)


timer.timeout.connect(poll)
timer.start(100)
app.exec()
sys.exit(0 if report.get('live_passed') else 1)
