"""Exercise rejection BEFORE node cook or expression evaluation; no accounts/models."""
from pathlib import Path
import tempfile
import hou
from PySide6 import QtWidgets
import scene_tools
from scene_policy import validate_cook, validate_node
from tests.support import ARTIFACTS

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

def denied(call):
    try:
        result = call()
    except PermissionError as exc:
        assert 'Access denied' in str(exc)
        return
    if isinstance(result, list) and result and not result[-1]['ok']:
        assert 'Access denied' in result[-1]['error'], result
        return
    raise AssertionError('Expected access denial, got ' + repr(result))

with tempfile.TemporaryDirectory(prefix='checked-tools-', dir=ARTIFACTS) as directory:
    hou.hipFile.save(str(Path(directory) / 'checked.hipnc'))
    parent = hou.node('/obj').createNode('geo', run_init_scripts=False)
    box = parent.createNode('box')
    validate_cook(box)
    edited = scene_tools.apply([{'action':'set_parameters','path':box.path(),
                                'parameters':[{'name':'size','value':[2,3,4]}]}])
    assert edited[0]['ok'], edited
    assert scene_tools.call('houdini_geometry', {'path':box.path()})['points'] == 8
    for typename in ('python', 'attribwrangle', 'file'):
        denied(lambda:scene_tools.apply([{'action':'create','parent':parent.path(),
                                          'name':'forbidden','type':typename}]))
    # Even harmless user-written Python is rejected as an expression.
    box.parm('sizex').setExpression('1', hou.exprLanguage.Python)
    denied(lambda:validate_cook(box))
    box.parm('sizex').deleteAllKeyframes()
    box.parm('sizex').set(2)
    called=[]
    def callback(**kwargs):
        called.append(True)
    box.addEventCallback((hou.nodeEventType.ParmTupleChanged,), callback)
    denied(lambda:scene_tools.apply([{'action':'set_parameters','path':box.path(),
                                     'parameters':[{'name':'size','value':[1,1,1]}]}]))
    assert not called
    box.removeAllEventCallbacks()
    light = hou.node('/stage').createNode('light')
    validate_node(light)  # Exact factory computations are allowed.
    light.parm('lookatprimposx').setExpression('1', hou.exprLanguage.Python)
    denied(lambda:validate_node(light))
    importer = hou.node('/stage').createNode('sopimport')
    outside = ARTIFACTS.parents[2] / 'outside-scope-test.usd'
    importer.parm('savepath').set(str(outside))
    denied(lambda:validate_node(importer))
hou.hipFile.clear(suppress_save_prompt=True)
print('PASS: native safe geometry/tuple edits; Python, file nodes, modified expressions, callbacks and outside outputs rejected')
