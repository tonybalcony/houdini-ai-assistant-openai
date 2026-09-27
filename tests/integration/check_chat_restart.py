"""Two short Terra subscription turns across a full Houdini and worker restart."""
from tests.support import ARTIFACTS
import json
import os
from pathlib import Path
import subprocess
import tempfile
from codex_worker import subscription_environment

ROOT = Path(__file__).resolve().parents[2]
from tests.support import find_hython
HYTHON = find_hython()
env = subscription_environment(os.environ)
env['QT_QPA_PLATFORM'] = 'offscreen'
env['PYTHONUTF8'] = '1'
with tempfile.TemporaryDirectory(prefix='astra-restart-') as directory:
    for phase in (1, 2):
        subprocess.run([HYTHON, '-m', 'tests.integration.check_chat_restart_houdini', str(phase), directory],
                       cwd=ROOT, env=env, check=True, timeout=240,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    results = [json.loads((Path(directory)/f'phase{i}.json').read_text(encoding='utf-8')) for i in (1, 2)]
    assert results[0]['thread_id'] == results[1]['thread_id']
    assert results[0]['chat_id'] == results[1]['chat_id']
    assert results[0]['mcp_port'] != results[1]['mcp_port']
    report = {'passed': True, 'subscription_turns': 2, 'sessions': results}
    (ARTIFACTS/'validation-chat-restart.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS: conversation survived full process restart; model remembered nickname and read the new scene', flush=True)
