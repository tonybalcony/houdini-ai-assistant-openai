"""Offline Houdini/Qt regressions. Run with hython; no model requests."""
import json
from pathlib import Path
import hou
import apex
from PySide6 import QtCore, QtWidgets, QtTest
import scene_tools
from astra_panel import AstraPanel
from check_support import isolated_chat_store

checks = {}
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
root = hou.node('/obj').createNode('geo', 'astra_apex_check', run_init_scripts=False)
electra = root.createNode('testgeometry_electra::2.0')
electra.parm('output').set('scene')
animate = root.createNode('apex::sceneanimate', 'animate')
animate.setInput(0, electra)
rig = '/electra.char/Base.rig'


def inspect(frame=1, filter='C_root_t', target=animate):
    return scene_tools.call('houdini_apex_inspect', {'path': target.path(), 'rig_path': rig,
        'parameter_filter': filter, 'frame': frame, 'offset': 0})


def write(layer, keys, interpolation='linear', target=animate, parameter='C_root_t'):
    return scene_tools.call('houdini_apex_keyframes', {'path': target.path(), 'rig_path': rig,
        'layer': layer, 'interpolation': interpolation, 'tracks': [{'parameter': parameter,
        'keys': [{'frame': f, 'value': v} for f, v in keys]}]})


def value(frame, target=animate):
    return inspect(frame, target=target)['parameters'][0]['value']


start_frame = hou.frame()
assert inspect()['parameters'][0]['name'] == 'C_root_t'
assert not inspect()['channels']
checks['rig_and_control_discovery'] = True
result = write('Astra Bounce', [(1, [0, 0, 0]), (12, [0, 2, 0]), (24, [0, 0, 0])])
assert result['component_keys_written'] == 9
assert value(12) == [0, 2, 0]
assert abs(value(6.5)[1] - 1) < 1e-5
checks['native_keys_persist_and_evaluate'] = True
write('Astra Bounce', [(12, [0, 3, 0])])
assert value(12) == [0, 3, 0]
channels = [c for c in inspect()['channels'] if c['layer'] == result['layer']]
assert len(channels) == 3 and all(c['key_count'] == 3 for c in channels), channels
assert len(inspect()['layers']) == 2
checks['existing_keys_preserved'] = True
write('Hand Wave', [(1, [0, 0, 0]), (12, [0, 0, 25])], parameter='L_hand_fk_r')
write('Astra Bounce', [(12, [0, 3, 0])])
assert value(12) == [0, 3, 0]
checks['other_layers_preserved'] = True
write('IK Switch', [(1, 0.0), (12, 1.0)], parameter='L_arm_ikfk_x')
assert inspect(12, 'L_arm_ikfk_x')['parameters'][0]['value'] == 1.0
checks['scalar_controls'] = True
before = inspect(12)
for keys in ([(2, [0, 9, 0]), (3, [0, 1])], [(2, [0, float('nan'), 0])], [(2, [0, 0, 0]), (2, [0, 1, 0])]):
    try:
        write('Invalid', keys)
        raise AssertionError('Invalid key batch accepted')
    except ValueError:
        assert before == inspect(12)
checks['invalid_batches_commit_nothing'] = True
write('Smooth', [(1, [0, 0, 0]), (12, [0, 2, 0]), (24, [0, 0, 0])], 'smooth')
assert value(12) == [0, 2, 0]
checks['smooth_interpolation'] = True
write('Held', [(1, [0, 1, 0]), (12, [0, 4, 0])], 'constant')
assert value(6) == [0, 1, 0]
checks['constant_interpolation'] = True
# Lock a layer through native APEX and ensure the adapter respects it.
scene = apex.Scene()
scene.loadFromGeometry(animate.geometry())
scene.initializeAnimStack()
scene.layer('Hand_Wave').lock()
stash = hou.Geometry(animate.parm('animation').eval())
scene.saveToGeometry(stash, '/animation/**', animate.inputGeometry(0))
animate.parm('animation').set(stash)
try:
    write('Hand Wave', [(1, [0, 0, 90])], parameter='L_hand_fk_r')
    raise AssertionError('Locked layer accepted')
except ValueError:
    assert next(v for v in inspect()['layers'] if v['name'] == 'Hand_Wave')['locked']
checks['locked_layers_rejected'] = True
# A downstream node inherits upstream layers. Write on a fresh layer only.
downstream = root.createNode('apex::sceneanimate', 'downstream')
downstream.setInput(0, animate)
assert all(v['inherited'] for v in inspect(target=downstream)['layers'])
before = inspect(12, target=downstream)
try:
    write('Held', [(1, [0, 8, 0])], target=downstream)
    raise AssertionError('Inherited layer accepted')
except ValueError:
    assert before == inspect(12, target=downstream)
write('Downstream', [(1, [0, 6, 0])], target=downstream)
assert value(1, downstream) == [0, 6, 0]
assert value(1) == [0, 1, 0]
checks['inherited_layers_preserved'] = True
assert hou.frame() == start_frame
checks['playhead_unchanged'] = True

# Real Qt mouse events, using another input to emulate focus leaving the panel.
window = QtWidgets.QWidget()
layout = QtWidgets.QVBoxLayout(window)
widget = AstraPanel(chat_store=isolated_chat_store())
other = QtWidgets.QLineEdit()
layout.addWidget(widget)
layout.addWidget(other)
window.resize(740, 800)
window.show()
window.activateWindow()
app.processEvents()
widget.input.setPlainText('draft')
for _ in range(10):
    QtTest.QTest.mouseClick(other, QtCore.Qt.MouseButton.LeftButton)
    assert other.hasFocus()
    widget.append_text('stream update\n')
    assert other.hasFocus(), 'Streaming stole focus'
    QtTest.QTest.mouseClick(widget.input.viewport(), QtCore.Qt.MouseButton.LeftButton)
    assert widget.input.hasFocus()
    assert widget.input.cursorWidth() > 0
    QtTest.QTest.keyClicks(widget.input, 'x')
assert widget.input.toPlainText().count('x') == 10
checks['single_click_focus_and_typing'] = True
assert widget.focusProxy() is widget.input
QtTest.QTest.mouseClick(other, QtCore.Qt.MouseButton.LeftButton)
widget.setFocus()
assert widget.input.hasFocus()
checks['panel_focus_proxy'] = True
widget.shutdown()
window.close()
report = {'houdini': hou.applicationVersionString(), 'checks': checks,
          'note': 'Separate headless scene and Qt window. Live docked-pane caret and viewport refresh still need user verification.'}
Path(__file__).with_name('validation-apex.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
