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
JOB_ROOT = None  # Tests may inject a disposable directory; production follows saved $HIP.


def job_root():
    from access_policy import project_data
    return JOB_ROOT if JOB_ROOT is not None else project_data('renders')


def job_dir(job_id):
    if not re.fullmatch('[a-f0-9]{32}', job_id):
        raise ValueError('Invalid render job ID.')
    from access_policy import contained
    return contained(job_root() / job_id, job_root())


def write_state(directory, state):
    temporary = directory / 'state.tmp'
    temporary.write_text(json.dumps(state,indent=2),encoding='utf-8')
    # Windows readers briefly deny replacing an open destination. A status poll
    # must not kill a healthy render; retry only the atomic publication step.
    for attempt in range(6):
        try:
            temporary.replace(directory / 'state.json')
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(.025 * (2 ** attempt))


def validate_launch_state(directory, state):
    """Recheck persisted inputs before starting any renderer process."""
    from access_policy import allowed_file, contained
    directory = directory.resolve()
    output = Path(state['output']).resolve()
    default = directory / ('render.png' if state['quality'] == 'working' else 'render.exr')
    if output != default:
        output = allowed_file(str(output), write=True)
    contained(directory / 'snapshots', directory)
    snapshot = contained(state['snapshot'], directory)
    if snapshot != directory / 'scene.usdc' or not snapshot.is_file():
        raise PermissionError('Access denied: invalid render snapshot.')
    installation = os.environ.get('HFS')
    if not installation:
        raise PermissionError('Access denied: Houdini runtime location is unavailable.')
    husk = (Path(installation) / 'bin/husk.exe').resolve()
    if Path(state['husk']).resolve() != husk or not husk.is_file():
        raise PermissionError('Access denied: invalid renderer executable.')
    if state['quality'] not in ('working', 'final') or output.suffix.lower() not in ('.png', '.exr'):
        raise ValueError('Invalid render format or quality.')
    if not isinstance(state['frame'], (int, float)) or not str(state['settings']).startswith('/'):
        raise ValueError('Invalid frame or render settings.')
    return output


def prepare(output_file, frame, node_path, quality):
    job_id = uuid.uuid4().hex
    directory = job_dir(job_id)
    from access_policy import allowed_file
    output = allowed_file(output_file, write=True) if output_file else directory / ('render.png' if quality=='working' else 'render.exr')
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
    python = ROOT / '.runtime/python/python.exe'
    if not python.is_file():
        raise ValueError('Bundled render helper is missing. Open Account to verify this installation.')
    from access_policy import child_environment
    env = child_environment()
    env.pop('UTHANA_API_KEY', None)
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
        files = sorted(job_root().glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]
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
