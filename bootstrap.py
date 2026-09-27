"""First-run setup; stdlib only, called in a Qt worker thread, never on the UI thread."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
PYTHON_URL = 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe'
PYTHON_SHA = 'edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403'
CODEX_URL = 'https://github.com/openai/codex/releases/download/rust-v0.157.1/codex-x86_64-pc-windows-msvc.exe.zip'
CODEX_SHA = '9b0cbcd72bcbea43433d18b82a50c09a7065f6bd6c503a3d9606a539283b89bf'


def clean_environment():
    return {k:v for k,v in os.environ.items() if k.upper() not in {
        'PYTHONHOME','PYTHONPATH','OPENAI_API_KEY','CODEX_API_KEY','UTHANA_API_KEY','OPENAI_BASE_URL'}}


def fingerprint():
    digest = hashlib.sha256()
    for name in ('requirements-lock.txt','requirements-mcp-lock.txt','install_mcp_source.py'):
        digest.update((ROOT/name).read_bytes())
    return digest.hexdigest()


def ready():
    try:
        marker = json.loads((ROOT/'.local/setup.json').read_text())
        return marker.get('fingerprint') == fingerprint() and all((ROOT/p).is_file() for p in (
            '.venv/Scripts/python.exe','.mcp-venv/Scripts/python.exe',
            'vendor/houdini-mcp-7e5cd7a2484b899a6e9251c6f7b90228c2ec7990/pyproject.toml'))
    except (OSError,ValueError):
        return False


def run_process(args, timeout=1200, env=None):
    # The setup log contains package output only; keys are removed from the environment.
    folder=ROOT/'.local'
    folder.mkdir(exist_ok=True)
    with (folder/'setup.log').open('ab') as log:
        result=subprocess.run([str(a) for a in args],cwd=ROOT,env=env or clean_environment(),
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,timeout=timeout,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode not in (0,3010):
        raise RuntimeError('Setup could not finish this step. Open the setup log for details, then retry.')


def verify_signature(path, publisher):
    powershell = Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    # A parent PowerShell 7 process can export incompatible module paths to 5.1.
    # Use only Windows' own modules for signature verification.
    env={k:v for k,v in clean_environment().items() if k.upper()!='PSMODULEPATH'}
    env['PSModulePath']=str(powershell.parent/'Modules')
    env.update(ASTRA_VERIFY_FILE=str(path),ASTRA_VERIFY_PUBLISHER=publisher)
    command = "$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $env:ASTRA_VERIFY_FILE; if ($s.Status -ne 'Valid' -or -not $s.SignerCertificate.Subject.Contains($env:ASTRA_VERIFY_PUBLISHER)) { exit 1 }"
    run_process([powershell,'-NoProfile','-NonInteractive','-Command',command],timeout=60,env=env)


def download(url,path,sha,progress,cancel):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==sha:
        return
    temporary=path.with_suffix(path.suffix+'.part')
    digest=hashlib.sha256()
    try:
        with urllib.request.urlopen(url,timeout=60) as response, temporary.open('wb') as output:
            size=int(response.headers.get('Content-Length',0))
            count=0
            last=time.monotonic()
            while True:
                if cancel.is_set():
                    raise RuntimeError('Setup cancelled. You can retry later.')
                block=response.read(1024*1024)
                if not block:
                    break
                count+=len(block)
                if count>500_000_000:
                    raise ValueError('Download exceeded its size limit.')
                output.write(block)
                digest.update(block)
                if size and time.monotonic()-last>1:
                    progress(f'Downloading required software: {round(count*100/size)}%')
                    last=time.monotonic()
        if digest.hexdigest()!=sha:
            raise ValueError('Download verification failed. No downloaded program was started.')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def python_candidates():
    yield ROOT/'.python313/python.exe'
    if os.name=='nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive,r'Software\Python\PythonCore\3.13\InstallPath') as key:
                    yield Path(winreg.QueryValueEx(key,'ExecutablePath')[0])
            except OSError:
                continue


def ensure_python(progress,cancel):
    for candidate in python_candidates():
        if candidate.is_file():
            try:
                verify_signature(candidate,'Python Software Foundation')
                run_process([candidate,'-c','import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize("P")==8'],timeout=15)
                return candidate
            except (OSError,RuntimeError,subprocess.SubprocessError):
                continue
    progress('Downloading a verified Python runtime...')
    installer=ROOT/'.local/downloads/python-3.13.15-amd64.exe'
    download(PYTHON_URL,installer,PYTHON_SHA,progress,cancel)
    verify_signature(installer,'Python Software Foundation')
    progress('Installing Python for this user...')
    run_process([installer,'/quiet','InstallAllUsers=0','TargetDir='+str(ROOT/'.python313'),
        'Include_launcher=0','PrependPath=0','AssociateFiles=0','Shortcuts=0',
        'Include_test=0','Include_doc=0','Include_tcltk=0','Include_pip=1'])
    candidate=ROOT/'.python313/python.exe'
    verify_signature(candidate,'Python Software Foundation')
    return candidate


def ensure_codex(progress,cancel):
    from codex_paths import find_codex
    if find_codex():
        return
    progress('Downloading verified Codex software...')
    archive=ROOT/'.local/downloads/codex-0.157.1.zip'
    download(CODEX_URL,archive,CODEX_SHA,progress,cancel)
    folder=ROOT/'.local/codex'
    if folder.exists():
        raise RuntimeError('Incomplete Codex installation. Open the setup log or choose an installed Codex executable.')
    with tempfile.TemporaryDirectory(prefix='codex-',dir=ROOT/'.local') as temporary:
        target=Path(temporary).resolve()
        with zipfile.ZipFile(archive) as zipped:
            for item in zipped.infolist():
                if not (target/item.filename).resolve().is_relative_to(target):
                    raise ValueError('Invalid Codex archive path.')
            zipped.extractall(target)
        verify_signature(target/'codex-x86_64-pc-windows-msvc.exe','OpenAI')
        target.rename(folder)


def setup(backend,progress,cancel):
    if backend not in ('subscription','api'):
        raise ValueError('Unknown sign-in choice.')
    if os.name!='nt':
        raise RuntimeError('This release supports Windows only.')
    # One installation at a time across all Houdini panels/processes.
    from chat_store import ChatLease
    from types import SimpleNamespace
    (ROOT/'.local').mkdir(exist_ok=True)
    try:
        lease=ChatLease(SimpleNamespace(directory=ROOT/'.local'),'0'*32)
    except RuntimeError:
        raise RuntimeError('Setup is already running in another Houdini window. Finish it there, then retry.') from None
    try:
        if not ready():
            base=ensure_python(progress,cancel)
            for folder,requirements in (('.venv','requirements-lock.txt'),('.mcp-venv','requirements-mcp-lock.txt')):
                if cancel.is_set():
                    raise RuntimeError('Setup cancelled. You can retry later.')
                progress('Preparing assistant tools...' if folder=='.venv' else 'Preparing Houdini tools...')
                python=ROOT/folder/'Scripts/python.exe'
                if not python.is_file():
                    run_process([base,'-m','venv',ROOT/folder])
                run_process([python,'-m','pip','install','--disable-pip-version-check','-r',ROOT/requirements])
                run_process([python,'-m','pip','check'])
            progress('Preparing the Houdini scene connection...')
            run_process([base,ROOT/'install_mcp_source.py'])
            from mcp_config import REPOSITORY
            run_process([ROOT/'.mcp-venv/Scripts/python.exe','-m','pip','install','--disable-pip-version-check','--no-deps',REPOSITORY])
            run_process([ROOT/'.mcp-venv/Scripts/python.exe','-m','pip','check'])
            (ROOT/'.local/setup.json').write_text(json.dumps({'fingerprint':fingerprint()}),encoding='utf-8')
        if cancel.is_set():
            raise RuntimeError('Setup cancelled. You can retry later.')
        if backend=='subscription':
            ensure_codex(progress,cancel)
        progress('Setup complete')
    finally:
        lease.close()
