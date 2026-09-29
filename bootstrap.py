"""Offline first-run verification. No downloader, pip, installer or registry edits."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def clean_environment():
    from access_policy import child_environment
    env = child_environment()
    env.pop('UTHANA_API_KEY', None)
    return env


def fingerprint():
    return hashlib.sha256((ROOT / '.runtime/manifest.json').read_bytes() +
                          (ROOT / 'VERSION').read_bytes()).hexdigest()


def ready():
    try:
        marker = json.loads((ROOT / '.state/setup.json').read_text())
        return marker.get('fingerprint') == fingerprint() and all((ROOT / p).is_file() for p in (
            '.runtime/python/python.exe', '.runtime/codex/codex-x86_64-pc-windows-msvc.exe'))
    except (OSError, ValueError):
        return False


def run_process(args, timeout=120, env=None):
    from access_policy import plugin_path
    folder = plugin_path('.state')
    folder.mkdir(exist_ok=True)
    with (folder / 'setup.log').open('ab') as log:
        result = subprocess.run([str(a) for a in args], cwd=ROOT, env=env or clean_environment(),
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Bundled runtime verification failed. Open the setup log for details.')


def verify_signature(path, publisher):
    powershell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    env = {k:v for k,v in clean_environment().items() if k.upper() != 'PSMODULEPATH'}
    env['PSModulePath'] = str(powershell.parent / 'Modules')
    env.update(ASTRA_VERIFY_FILE=str(path), ASTRA_VERIFY_PUBLISHER=publisher)
    command = "$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $env:ASTRA_VERIFY_FILE; if ($s.Status -ne 'Valid' -or -not $s.SignerCertificate.Subject.Contains($env:ASTRA_VERIFY_PUBLISHER)) { exit 1 }"
    run_process([powershell, '-NoProfile', '-NonInteractive', '-Command', command], timeout=60, env=env)


def verify_bundle(progress, cancel):
    from access_policy import contained
    try:
        manifest = json.loads((ROOT / '.runtime/manifest.json').read_text())
    except (OSError, ValueError):
        raise RuntimeError('Bundled runtime is missing. Install the full plugin ZIP from Releases, not GitHub Source code. Nothing was downloaded.') from None
    files = manifest.get('files', {})
    if not files or manifest.get('platform') != 'windows-x64':
        raise ValueError('Invalid runtime manifest.')
    root = contained(ROOT / '.runtime', ROOT)
    for index, (name, expected) in enumerate(files.items()):
        if cancel.is_set():
            raise RuntimeError('Setup cancelled. No software was downloaded or installed.')
        path = contained(root / name, root)
        if not path.is_file():
            raise ValueError('Bundled runtime file missing: ' + name)
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('Bundled runtime checksum failed: ' + name)
        if index % 100 == 0:
            progress(f'Verifying bundled files: {index + 1}/{len(files)}')
    return manifest


def setup(backend, progress, cancel, *, consent=False):
    if not consent:
        raise PermissionError('Please approve the displayed local setup plan first.')
    if backend not in ('subscription', 'api'):
        raise ValueError('Unknown sign-in choice.')
    if os.name != 'nt':
        raise RuntimeError('This release supports Windows x64 only.')
    from access_policy import plugin_path
    from chat_store import ChatLease
    from types import SimpleNamespace
    folder = plugin_path('.state')
    folder.mkdir(exist_ok=True)
    lease = ChatLease(SimpleNamespace(directory=folder), '0' * 32)
    try:
        verify_bundle(progress, cancel)
        progress('Checking publishers of bundled Python and Codex...')
        verify_signature(ROOT / '.runtime/python/python.exe', 'Python Software Foundation')
        verify_signature(ROOT / '.runtime/codex/codex-x86_64-pc-windows-msvc.exe', 'OpenAI')
        if cancel.is_set():
            raise RuntimeError('Setup cancelled.')
        progress('Checking bundled assistant libraries locally...')
        run_process([ROOT / '.runtime/python/python.exe', '-c',
                     'import sys; from agents import Agent; from jsonschema import validate; from PIL import Image; assert sys.version_info[:2]==(3,13)'])
        (folder / 'workspace').mkdir(exist_ok=True)
        (folder / 'setup.json').write_text(json.dumps({'fingerprint': fingerprint()}), encoding='utf-8')
        progress('Local verification complete. No downloads or system installation.')
    finally:
        lease.close()
