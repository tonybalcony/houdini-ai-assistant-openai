"""Supervise husk, save intermediate previews, and survive Houdini reconnections."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from render_jobs import job_dir,write_state
from diagnostics import DiagnosticLog,redact


def main(job_id):
    from PIL import Image
    directory = job_dir(job_id)
    state = json.loads((directory/'state.json').read_text(encoding='utf-8'))
    log = DiagnosticLog('render')
    process = None
    tail = []
    try:
        output = Path(state['output'])
        if output.exists():
            raise ValueError('Output appeared before render launch; refusing to overwrite it.')
        snapshots=directory/'snapshots'
        snapshots.mkdir(exist_ok=True)
        args = [state['husk'],'--renderer','BRAY_HdKarmaXPU','--engine','xpu',
                '--settings',state['settings'],'--frame',str(state['frame']),
                '--output',output.name,'--headlight','none','--snapshot','2' if state['quality']=='working' else '5',
                '--snapshot-path',str(snapshots).replace('\\','/'),'--snapshot-suffix','_wip',
                '--disable-delegate-products','--disable-slapcomp']
        if state['quality']=='working':
            args += ['--disable-motionblur']
        args.append(state['snapshot'])
        process = subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,cwd=str(output.parent),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        state.update(status='running',pid=process.pid,updated=time.time())
        write_state(directory,state)
        log.event('render_started',job_id=job_id,pid=process.pid,quality=state['quality'])
        def reader():
            for line in iter(process.stdout.readline,b''):
                text = redact(line.decode('utf-8',errors='replace').strip())
                if 'Failed to initialize Optix' in text:
                    state['gpu_warning'] = text
                tail.append(text)
                del tail[:-40]
                log.stderr(line)
        threading.Thread(target=reader,daemon=True).start()
        previous = None
        def capture():
            nonlocal previous
            wip=snapshots/(output.stem+'_wip'+output.suffix)
            candidates = [output,wip] if process.poll() is not None else [wip]
            source = next((p for p in candidates if p.is_file()),None)
            if source is None:
                return
            stamp = (str(source),source.stat().st_mtime_ns,source.stat().st_size)
            if stamp == previous:
                return
            try:
                image_source=source
                if source.suffix.lower()=='.exr':
                    converted=directory/'display.png'
                    conversion=subprocess.run([str(Path(state['husk']).with_name('iconvert.exe')),
                        '--ocio','-d','byte',str(source),str(converted)],stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if conversion.returncode:
                        return
                    image_source=converted
                with Image.open(image_source) as im:
                    im = im.convert('RGB')
                    im.thumbnail((1024,1024))
                    im.save(directory/'preview.tmp',format='JPEG',quality=85)
                (directory/'preview.tmp').replace(directory/'preview.jpg')
                previous = stamp
                state['preview_source'] = 'wip' if source==wip else 'completed'
                log.event('preview_saved',job_id=job_id,source=state['preview_source'])
            except (OSError,ValueError,subprocess.SubprocessError):
                pass  # The renderer may still be replacing its snapshot file.
        while process.poll() is None:
            capture()
            if (directory/'cancel').exists():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                state['status']='cancelled'
                break
            state.update(updated=time.time())
            write_state(directory,state)
            time.sleep(1)
        process.wait(timeout=10)
        capture()
        if state['status']!='cancelled':
            state['status']='completed' if process.returncode==0 and output.is_file() and output.stat().st_size else 'failed'
        state.update(exit_code=process.returncode,updated=time.time(),log_tail=tail)
        if state.get('gpu_warning'):
            state['note']='XPU reported a GPU initialization/driver error. Check render status and output; do not claim GPU acceleration was verified.'
        log.event('render_finished',job_id=job_id,status=state['status'],exit_code=process.returncode)
    except Exception as exc:
        state.update(status='failed',error=redact(exc),updated=time.time())
        log.event('render_failed',job_id=job_id,error=redact(exc))
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        write_state(directory,state)
        log.close()


if __name__=='__main__':
    main(sys.argv[1])
