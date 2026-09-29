"""Audit/extract a full plugin ZIP against the index; verify the relocated offline runtime.

No account access, sign-in, model request or download. Keeps the test installation
under .local/checks for native UI inspection. Run after build_plugin.py.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'houdini-ai-assistant-openai/'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main(filename):
    archive_path = Path(filename).resolve()
    checks = ROOT / '.local/checks'
    checks.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix='clean install ', dir=checks))
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), 'Duplicate ZIP entries'
        assert all((target/name).resolve().is_relative_to(target) for name in names), 'Unsafe ZIP path'
        forbidden = {'.state', '.secrets', '.astra', '.git', '.local', '__pycache__', '.venv',
                     '.chat_history', 'motion_cache', 'texture_cache', 'auth.json'}
        assert not any(set(Path(name).parts) & forbidden for name in names), 'Private/generated ZIP content'
        manifest = json.loads(archive.read(PREFIX+'.runtime/manifest.json'))
        expected = {PREFIX+'.runtime/manifest.json'}
        for name in git('ls-files', '--cached', '-z').decode().split('\0'):
            if not name or name.split('/')[0] in {'tests', 'scripts', '.github'}:
                continue
            destination = name if name == 'houdini-ai-assistant.json' else PREFIX+name
            expected.add(destination)
            assert archive.read(destination) == git('show', ':'+name), 'Source/index mismatch: '+name
        for name, checksum in manifest['files'].items():
            destination = PREFIX+'.runtime/'+name
            expected.add(destination)
            with archive.open(destination) as stream:
                assert hashlib.file_digest(stream,'sha256').hexdigest() == checksum, 'Runtime hash mismatch: '+name
        assert set(names) == expected, 'Unexpected or missing archive content'
        archive.extractall(target)
    plugin = target / PREFIX
    python = plugin / '.runtime/python/python.exe'
    env = {k:v for k,v in os.environ.items() if k.upper() not in ('PYTHONPATH', 'PYTHONHOME', 'CODEX_HOME')}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    script = "import pathlib, threading, access_policy, bootstrap; from agents import Agent; from openai import AsyncOpenAI; from PIL import Image; assert access_policy.ROOT == pathlib.Path.cwd(); bootstrap.setup('subscription', lambda message: None, threading.Event(), consent=True); assert bootstrap.ready(); print('PASS: relocated bundled imports and offline setup')"
    subprocess.run([str(python), '-c', script], cwd=plugin, env=env, check=True, timeout=180)
    with archive_path.open('rb') as stream:
        checksum = hashlib.file_digest(stream,'sha256').hexdigest()
    result = {'zip':str(archive_path), 'sha256':checksum, 'bytes':archive_path.stat().st_size,
              'entries':len(names), 'runtime_files':len(manifest['files']),
              'extracted':str(target), 'passed':True}
    (checks/'validation-package-060.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
