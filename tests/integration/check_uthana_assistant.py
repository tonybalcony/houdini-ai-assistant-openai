"""Offline native Houdini test using an already downloaded Uthana motion."""
from tests.support import ARTIFACTS
import json
import math
from pathlib import Path
import sys
import tempfile
import shutil
import hou
from PySide6 import QtWidgets, QtCore
import scene_tools
from astra_panel import AstraPanel
from uthana_qt import UthanaCall
from tests.support import isolated_chat_store

ROOT = Path(__file__).resolve().parents[2]
if len(sys.argv) != 3:
    raise SystemExit('Usage: hython -m tests.integration.check_uthana_assistant <already-downloaded-asset-id> <existing-cache-root>; no new generation is performed')
asset_id = sys.argv[1]
from uthana_client import cache_dir
test_project = tempfile.TemporaryDirectory(prefix='motion-scope-', dir=ARTIFACTS)
hou.hipFile.save(str(Path(test_project.name) / 'motion.hipnc'))
source_cache = Path(sys.argv[2]).resolve()
source_asset = (source_cache / asset_id).resolve()
assert source_asset.is_relative_to(source_cache)
assert len(asset_id) == 24 and all(c in '0123456789abcdef' for c in asset_id)
# Copy only an existing generated motion fixture, never accounts or other caches.
shutil.copytree(source_asset, cache_dir(asset_id), ignore=shutil.ignore_patterns('*.lock'))
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
root = hou.node('/obj').createNode('geo', 'uthana_integration_check', run_init_scripts=False)
electra = root.createNode('testgeometry_electra::2.0')
electra.parm('output').set('scene')
original = root.createNode('apex::sceneanimate', 'original_animation')
original.setInput(0, electra)
original_geo = original.geometry()
initial_frame = hou.frame()
print('Importing existing cached test motion', flush=True)
imported = scene_tools.call('houdini_uthana_import', {'asset_id': asset_id, 'parent': root.path(),
                           'name': 'Uthana_Wave', 'start_frame': 10})
print(json.dumps({k:v for k,v in imported.items() if k != 'joints'}), flush=True)
assert imported['ok'] and imported['frame_range'][0] == 10
source = hou.node(imported['source_path'])
offset_pose = source.geometryAtFrame(10).pointFloatAttribValues('P')
source.parm('useplaybackstarttime').set(False)
unshifted_pose = source.geometryAtFrame(1).pointFloatAttribValues('P')
source.parm('useplaybackstarttime').set(True)
assert all(math.isclose(a,b,abs_tol=1e-5) for a,b in zip(offset_pose,unshifted_pose))
print('Retargeting locally onto Electra', flush=True)
result = scene_tools.call('houdini_uthana_retarget', {'source_path': imported['source_path'],
    'target_path': original.path(), 'rig_path': '/electra.char/Base.rig', 'skeleton_path': '/electra.char/Base.skel',
    'clip_name': 'Uthana_Wave', 'mapping_mode': 'mappingproperty'})
print(json.dumps(result), flush=True)
assert result['ok'], result
assert result['keyed_channels'] > 20 and result['varying_channels'] > 10
assert result['active_clip'] == '/animation/Uthana_Wave.clip'
output = hou.node(result['animate_path'])
output.geometry()
assert not output.errors()
original_stash = original.parm('animation').eval()
assert original.inputs()[0] == electra and (original_stash is None or not original_stash.prims())
assert hou.frame() == initial_frame
details = scene_tools.call('houdini_apex_inspect', {'path': output.path(), 'rig_path': '/electra.char/Base.rig',
    'parameter_filter': 'R_hand', 'frame': 50, 'offset': 0})
assert details['channels']
checks = {'cached_fbx_import': True, 'clip_start_offset': True, 'local_biped_retarget': True,
    'native_apex_channels': True, 'generated_clip_active': True, 'original_scene_preserved': True,
    'playhead_preserved': True}

# The external helper must work asynchronously through Qt without model traffic.
panel = AstraPanel(chat_store=isolated_chat_store())
panel.busy, panel.connected = True, True
panel.run_id = 'test-uthana'
panel.scene_file = hou.hipFile.path()
panel.run_generation = panel.generation
messages = []
panel.write = lambda m: messages.append(m) or True
request = {'tool': 'uthana_cached_motions', 'arguments': {}, 'call_id': 'once', 'run_id': panel.run_id}
panel.handle_tool(request)
panel.handle_tool(request)
assert len(panel.remote_calls) == 1
loop = QtCore.QEventLoop()
timer = QtCore.QTimer()
timer.timeout.connect(lambda: loop.quit() if messages else None)
timer.start(20)
QtCore.QTimer.singleShot(15_000, loop.quit)
loop.exec()
assert len(messages) == 1 and messages[0]['result']['motions']
assert not panel.remote_calls
checks['nonblocking_external_helper_and_duplicate_guard'] = True
# A result arriving after Stop must never be dispatched back into a newer turn.
messages.clear()
panel.cancelled = True
panel.finish_remote(request, {'status': 'FINISHED'})
assert not messages
checks['stopped_result_guard'] = True
panel.shutdown()
report = {'houdini': hou.applicationVersionString(), 'asset_id': asset_id,
          'checks': checks, 'retarget': result,
          'scope': 'Uses cached text-only Uthana test output. No API calls or uploads in this check; native viewport review remains manual.'}
(ARTIFACTS / 'validation-uthana.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
hou.hipFile.clear(suppress_save_prompt=True)
test_project.cleanup()
