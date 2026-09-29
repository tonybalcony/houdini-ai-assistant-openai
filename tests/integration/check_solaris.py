"""Disposable native Solaris/MaterialX authoring check; --render adds one small XPU render."""
from tests.support import ARTIFACTS
import json
import sys
import time
from pathlib import Path
import hou
from PySide6 import QtWidgets
import solaris_tools as tools
from pxr import Usd,UsdShade

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
hou.hipFile.save(str(ARTIFACTS / 'solaris-test.hipnc'))
root = hou.node('/obj').createNode('geo','SOLARIS_CHECK',run_init_scripts=False)
box = root.createNode('box')
stage = hou.node('/stage')
last = None
def create(name, **config):
    global last
    result = tools.call('houdini_solaris_create',{'parent':stage.path(),'input_path':last,'name':name,'config':config})
    assert result['status']=='success',result
    last = result['path']
    print('PASS:',name,flush=True)
    return result

create('import_check',kind='import_sop',source_path=box.path(),prim_path='/World/box')
material = create('blue_material',kind='material',prim_pattern='/World/box',base_color=[.02,.2,.8],roughness=.35,metalness=.2)
create('key_light',kind='light',light_type='dome',position=[0,0,0],rotation=[0,0,0],color=[1,1,1],intensity=1,exposure=0)
create('rect_light',kind='light',light_type='rect',position=[2,3,4],rotation=[-30,20,0],color=[1,1,1],intensity=1,exposure=2)
cam = create('render_camera',kind='camera',position=[0,0,5],rotation=[0,0,0],focal_length=50)
karma = create('working_karma',kind='karma',camera_prim=cam['prim_path'],resolution=[960,960] if '--wip' in sys.argv else [256,256],samples=32 if '--wip' in sys.argv else 16)
inspection = tools.inspect(last,'/')
usd = hou.node(last).stage()
assert UsdShade.MaterialBindingAPI(usd.GetPrimAtPath('/World/box')).ComputeBoundMaterial()[0].GetPath() == material['material_path']
assert any(p['type']=='Shader' and str(p.get('shader_id','')).startswith('ND_standard_surface') for p in inspection['prims'])
assert any(p['type'].startswith('DomeLight') for p in inspection['prims'])
assert any(p['type']=='RectLight' for p in inspection['prims'])
copy = Usd.Stage.Open(usd.Flatten())
tools.optimize_working_stage(copy,karma['render_settings'])
settings = copy.GetPrimAtPath(karma['render_settings'])
attrs = {a.GetName():str(a.Get()) for a in settings.GetAttributes() if any(w in a.GetName() for w in ('sample','engine','limit','resolution','delegate'))}
assert settings.GetAttribute('karma:object:reflectlimit').Get()<=2
assert settings.GetAttribute('karma:object:refractlimit').Get()<=2
assert max(settings.GetAttribute('resolution').Get())<=960
assert settings.GetAttribute('karma:global:pathtracedsamples').Get()<=32
report = {'passed':True,'native_usd_inspection':inspection,'working_render_attributes':attrs}
if '--render' in sys.argv:
    start = tools.render_start(last,1,'','working')
    report['job_id']=start['job_id']
    print('STARTED JOB:',start['job_id'],flush=True)
    import render_jobs
    deadline = time.monotonic()+180
    saw_wip=False
    while time.monotonic()<deadline:
        result = render_jobs.status(start['job_id'])
        if result['status']=='running' and result.get('preview_available'):
            saw_wip=True
            assert render_jobs.preview(start['job_id']).get('image_base64')
            if '--wip' in sys.argv:
                render_jobs.cancel(start['job_id'])
        if result['status'] not in ('starting','running','preparing'):
            break
        time.sleep(1)
    report['render']=result
    report['image_available_before_completion']=saw_wip
    assert result['status'] in ('completed','cancelled'), result
    assert render_jobs.preview(start['job_id']).get('image_base64'),result
    print('PASS: XPU render status '+result['status']+'; WIP available before completion: '+str(saw_wip),flush=True)
(ARTIFACTS / ('validation-solaris-render.json' if '--render' in sys.argv else 'validation-solaris.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PASS: Solaris import, MaterialX USD binding, lights, camera and Karma XPU settings',flush=True)
