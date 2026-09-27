"""Durable local render jobs; independent of panel and Codex worker lifetimes."""
import base64
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent
JOB_ROOT = ROOT / '.render_jobs'


def job_dir(job_id):
    if not re.fullmatch('[a-f0-9]{32}', job_id):
        raise ValueError('Invalid render job ID.')
    return JOB_ROOT / job_id


def write_state(directory, state):
    temporary = directory / 'state.tmp'
    temporary.write_text(json.dumps(state,indent=2),encoding='utf-8')
    temporary.replace(directory / 'state.json')


def prepare(output_file, frame, node_path, quality):
    job_id = uuid.uuid4().hex
    directory = job_dir(job_id)
    output = Path(output_file).expanduser() if output_file else directory / ('render.png' if quality=='working' else 'render.exr')
    if not output.is_absolute() or output.suffix.lower() not in ('.exr','.png'):
        raise ValueError('Output must be an absolute .exr or .png file path.')
    if output.exists():
        raise ValueError('Output already exists. Choose a new filename; existing images are preserved.')
    directory.mkdir(parents=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    state = {'job_id':job_id,'status':'preparing','engine':'Karma XPU','quality':quality,
             'frame':frame,'node_path':node_path,'output':str(output),'created':time.time(),'updated':time.time()}
    write_state(directory,state)
    return directory,state


def launch(directory, state, husk, snapshot, settings):
    state.update(husk=str(husk), snapshot=str(snapshot), settings=settings,status='starting')
    write_state(directory,state)
    python = ROOT / '.mcp-venv/Scripts/python.exe'
    if not python.is_file():
        raise ValueError('Render helper Python is missing. Run setup_mcp.ps1.')
    env = dict(os.environ)
    for key in list(env):
        if key.upper() in ('PYTHONHOME','PYTHONPATH','OPENAI_API_KEY','CODEX_API_KEY','UTHANA_API_KEY'):
            env.pop(key)
    subprocess.Popen([str(python),str(ROOT/'render_job_worker.py'),state['job_id']],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        env=env,cwd=str(ROOT),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
    return {k:v for k,v in state.items() if k not in ('husk','snapshot')}


def status(job_id,wait_seconds=0):
    if not 0<=wait_seconds<=10:
        raise ValueError('Status wait must be between 0 and 10 seconds.')
    if job_id and wait_seconds:
        before=status(job_id)
        deadline=time.monotonic()+wait_seconds
        while before['status'] in ('starting','running','preparing') and time.monotonic()<deadline:
            time.sleep(.2)
            current=status(job_id)
            if current['status'] not in ('starting','running','preparing') or current['preview_updated']!=before['preview_updated']:
                return current
        return status(job_id)
    if not job_id:
        files = sorted(JOB_ROOT.glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]
        return {'jobs':[status(p.parent.name) for p in files]}
    directory = job_dir(job_id)
    state = json.loads((directory/'state.json').read_text(encoding='utf-8'))
    if state['status'] in ('preparing','starting','running') and time.time()-state['updated'] > 40:
        state['status'] = 'unknown'
        state['note'] = 'Render supervisor is no longer reporting. Inspect output/logs; do not automatically resubmit.'
    state['preview_available'] = (directory/'preview.jpg').is_file()
    state['preview_updated'] = (directory/'preview.jpg').stat().st_mtime if state['preview_available'] else None
    return {k:v for k,v in state.items() if k not in ('husk','snapshot')}


def cancel(job_id):
    state = status(job_id)
    if state['status'] not in ('starting','running'):
        return state
    (job_dir(job_id)/'cancel').touch()
    return {'job_id':job_id,'status':'cancel_requested','note':'Check status; partial images remain.'}


def preview(job_id):
    state = status(job_id)
    path = job_dir(job_id)/'preview.jpg'
    if not path.is_file():
        return {'status':'pending','job':state,'note':'No readable image yet. Do not judge the image until this tool returns it.'}
    payload = path.read_bytes()
    if len(payload)>1_000_000:
        raise ValueError('Preview image exceeded the transport limit.')
    return {'status':'success','job':state,'image_base64':base64.b64encode(payload).decode('ascii'),
            'mime_type':'image/jpeg','note':'WIP image; judge framing, lighting and materials. Noise/detail may be unfinished.'}
