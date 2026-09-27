"""Real Codex -> MCP -> disposable Houdini check. --live adds one subscription turn."""
from tests.support import ARTIFACTS
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

from codex_worker import CodexBridge, find_codex, subscription_environment
from mcp_config import ROOT, REVISION

from tests.support import find_hython
HYTHON = find_hython()
checks = {}
events = queue.Queue()
notifications = []
flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
processes = []
log_path = ROOT / '.local/mcp_check_stderr.log'
log_path.parent.mkdir(exist_ok=True)


def read_lines(process, name):
    for line in process.stdout:
        try:
            events.put((name, json.loads(line)))
        except ValueError:
            pass
    events.put((name, {'eof': True}))


def data(result):
    if result.get('isError'):
        raise AssertionError(result)
    value = result.get('structuredContent')
    if value is None:
        value = json.loads(next(c['text'] for c in result['content'] if c.get('type') == 'text'))
    assert value.get('status') in ('success', 'connected'), value
    return value


with log_path.open('w', encoding='utf-8') as log:
    try:
        env = subscription_environment(os.environ)
        env['QT_QPA_PLATFORM'] = 'offscreen'
        env['PYTHONUTF8'] = '1'
        host = subprocess.Popen([HYTHON, '-m', 'tests.integration.check_mcp_houdini_host'], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8', creationflags=flags)
        processes.append(host)
        threading.Thread(target=read_lines, args=(host, 'host'), daemon=True).start()
        name, started = events.get(timeout=45)
        assert name == 'host' and started.get('ready'), started
        checks['isolated_houdini_started'] = True
        codex = subprocess.Popen([find_codex(), '-c', 'model_provider="openai"', 'app-server', '--listen', 'stdio://'],
            cwd=ROOT, env=subscription_environment(os.environ), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=log, text=True, encoding='utf-8', creationflags=flags)
        processes.append(codex)
        threading.Thread(target=read_lines, args=(codex, 'codex'), daemon=True).start()

        def send(message):
            codex.stdin.write(json.dumps(message)+'\n')
            codex.stdin.flush()

        def emit(message):
            notifications.append(message)
            if message['event'] == 'fatal':
                raise AssertionError(message)

        bridge = CodexBridge(emit, send, mcp_port=started['port'])

        def pump_until(predicate, timeout=90):
            deadline = time.monotonic()+timeout
            while not predicate():
                assert time.monotonic() < deadline, 'Integration step timed out; see .local/mcp_check_stderr.log'
                try:
                    name, message = events.get(timeout=.2)
                except queue.Empty:
                    bridge.tick()
                    continue
                assert not message.get('eof'), f'{name} exited unexpectedly'
                if name == 'codex':
                    bridge.receive(message)

        bridge.initialize()
        pump_until(lambda: bridge.ready)
        checks['subscription_signin_and_mcp_scene_read'] = True
        print('PASS: Codex connected to the real Houdini MCP server and read the scene', flush=True)

        def request(method, params):
            results = []
            bridge.request(method, params, results.append, timeout=75)
            pump_until(lambda: bool(results))
            return results[0]

        inventory = request('mcpServerStatus/list', {'threadId': bridge.thread_id, 'detail': 'toolsAndAuthOnly', 'limit': 100})
        server = next(s for s in inventory['data'] if s['name'] == 'houdini')
        names = sorted(server['tools'])
        checks['mcp_tool_inventory'] = len(names)

        def call(tool, arguments):
            result = data(request('mcpServer/tool/call', {'threadId': bridge.thread_id, 'server': 'houdini',
                'tool': tool, 'arguments': arguments}))
            print('PASS:', tool, flush=True)
            return result

        parent = '/obj/MCP_INTEGRATION_TEST'
        call('create_node', {'node_type': 'box', 'parent_path': parent, 'name': 'box_mcp'})
        call('set_parameter', {'node_path': parent+'/box_mcp', 'param_name': 'size', 'value': [2,3,4]})
        call('create_node', {'node_type': 'null', 'parent_path': parent, 'name': 'OUT_MCP'})
        call('connect_nodes', {'src_path': parent+'/box_mcp', 'dst_path': parent+'/OUT_MCP'})
        info = call('get_node_info', {'node_path': parent+'/OUT_MCP', 'include_input_details': True})
        assert 'box_mcp' in json.dumps(info), info
        geometry = call('get_geo_summary', {'node_path': parent+'/OUT_MCP'})
        checks['native_create_edit_wire_inspect_geometry'] = True
        code = call('execute_code', {'code': 'print(hou.node("/obj/MCP_INTEGRATION_TEST/box_mcp").parmTuple("size").eval())',
                                    'policy': 'normal'})
        assert '2.0, 3.0, 4.0' in json.dumps(code), code
        checks['houdini_python_execution'] = True
        if '--solaris' in sys.argv:
            assert 'houdini_solaris_create' in names and 'texture_write' in names
            assert 'render_viewport' not in names and 'create_material' not in names
            previous = None
            def create_solaris(name,config):
                global previous
                result=call('houdini_solaris_create',{'parent':'/stage','input_path':previous,'name':name,'config':config})
                previous=result['path']
                return result
            create_solaris('import_mcp',{'kind':'import_sop','source_path':parent+'/box_mcp','prim_path':'/World/mcp_box'})
            material=create_solaris('material_mcp',{'kind':'material','prim_pattern':'/World/mcp_box','base_color':[.1,.3,.8],'roughness':.3,'metalness':0})
            texture=call('texture_write',{'name':'validation_'+uuid.uuid4().hex+'.png','pattern':'checker','size':32,'color_a':[0,0,0],'color_b':[1,1,1],'scale':4,'seed':1})
            call('houdini_materialx_textures',{'shader_path':material['shader_path'],'base_color_file':texture['path'],
                 'roughness_file':'','metalness_file':'','normal_file':'','displacement_file':'','displacement_scale':0})
            call('houdini_solaris_inspect',{'path':previous,'root_prim':'/World'})
            library=call('texture_library_search',{'query':Path(texture['path']).stem})
            assert library['assets']
            checks['native_mcp_solaris_materialx_and_texture_tools']=True
            # Optional real render transport check; no developer-specific job ID.
            report_path=ARTIFACTS/'validation-solaris-render.json'
            if report_path.is_file():
                job=json.loads(report_path.read_text(encoding='utf-8'))['job_id']
                preview=request('mcpServer/tool/call',{'threadId':bridge.thread_id,'server':'houdini',
                    'tool':'houdini_solaris_render_preview','arguments':{'job_id':job}})
                assert any(c.get('type')=='image' for c in preview.get('content',[])), 'Preview is not model-viewable image content'
                checks['native_mcp_preview_is_actual_image']=True
            else:
                checks['native_mcp_preview_is_actual_image']='skipped: run hython -m tests.integration.check_solaris --render first'
        request_id = bridge.serial
        bridge.new_thread(reset=True)
        pump_until(lambda: bridge.ready and bridge.serial > request_id)
        checks['new_chat_reconnects_mcp'] = True
        if '--live' in sys.argv:
            bridge.dispatch({'command': 'send', 'run_id': 'mcp-live-check', 'effort': 'low',
                'text': 'Use only the Houdini MCP server for this test. Create a null named ASTRA_MCP_LIVE '
                        'under /obj/MCP_INTEGRATION_TEST, then inspect it with MCP get_node_info. '
                        'Do not make any other edits. Reply briefly when verified.',
                'context': {'test_scene': True, 'parent': parent}})
            pump_until(lambda: any(n.get('event') == 'run_finished' and n.get('run_id') == 'mcp-live-check'
                                   for n in notifications), timeout=180)
            finish = next(n for n in notifications if n.get('event') == 'run_finished')
            assert finish['status'] == 'completed', finish
            completed = [n['tool'] for n in notifications if n.get('event') == 'mcp_tool' and n.get('status') == 'completed']
            assert 'create_node' in completed and 'get_node_info' in completed, completed
            call('get_node_info', {'node_path': parent+'/ASTRA_MCP_LIVE', 'compact': True})
            checks['astra_chose_and_executed_mcp_tools'] = True
        report = {'passed': True, 'revision': REVISION, 'model_turns': int('--live' in sys.argv), 'checks': checks, 'tools': names}
        (ARTIFACTS/'validation-mcp.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({'passed': True, 'checks': checks}), flush=True)
    finally:
        for process in reversed(processes):
            try:
                process.stdin.close()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=5)
