"""Maintainer-only bundle builder. Network happens here, never on first launch.

Run with a developer Python 3.13 x64 and --download. Only verified archives and
exact-version wheels enter .runtime; user accounts and existing venvs are not copied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / '.local/build-downloads'
RUNTIME = ROOT / '.runtime'
ARCHIVES = {
    'python': ('https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip',
               'd1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'),
    'codex': ('https://github.com/openai/codex/releases/download/rust-v0.157.1/codex-x86_64-pc-windows-msvc.exe.zip',
              '9b0cbcd72bcbea43433d18b82a50c09a7065f6bd6c503a3d9606a539283b89bf'),
}
NOTICES = {
    'LICENSE': ('https://raw.githubusercontent.com/openai/codex/rust-v0.157.1/LICENSE',
                'd17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc'),
    'NOTICE': ('https://raw.githubusercontent.com/openai/codex/rust-v0.157.1/NOTICE',
               '9d71575ecfd9a843fc1677b0efb08053c6ba9fd686a0de1a6f5382fd3c220915'),
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def distributable(path):
    relative = path.relative_to(RUNTIME)
    # pip's unused CLI launchers/direct_url metadata can embed the maintainer path.
    return (path.is_file() and '__pycache__' not in relative.parts and
            relative.name != 'direct_url.json' and
            not relative.as_posix().startswith('python/Lib/site-packages/bin/'))


def archive(url, expected):
    path = DOWNLOADS / url.rsplit('/', 1)[-1]
    if not path.is_file() or digest(path) != expected:
        temporary = path.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open('wb') as output:
            while block := source.read(1024 * 1024):
                output.write(block)
        if digest(temporary) != expected:
            raise ValueError('Official archive checksum mismatch: ' + path.name)
        temporary.replace(path)
    return path


def extract(path, folder):
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as source:
        for item in source.infolist():
            if not (folder / item.filename).resolve().is_relative_to(folder.resolve()):
                raise ValueError('Unsafe archive path.')
        source.extractall(folder)


def build():
    if os.name != 'nt' or sys.version_info[:2] != (3, 13):
        raise RuntimeError('Build with Windows x64 Python 3.13.')
    if (RUNTIME / 'manifest.json').exists():
        raise RuntimeError('A completed runtime already exists. Use a fresh build checkout for dependency updates.')
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in ARCHIVES.items():
        print('Preparing bundled ' + name, flush=True)
        extract(archive(url, sha), RUNTIME / name)
    for name, (url, sha) in NOTICES.items():
        (RUNTIME / 'codex' / name).write_bytes(archive(url, sha).read_bytes())
    python = RUNTIME / 'python'
    (python / 'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n..\\..\nimport site\n')
    libraries = python / 'Lib/site-packages'
    wheels = DOWNLOADS / 'wheels'
    wheels.mkdir(exist_ok=True)
    subprocess.run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--no-deps',
                    '--disable-pip-version-check', '--dest', str(wheels),
                    '-r', str(ROOT / 'requirements-lock.txt')], check=True)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile',
                    '--disable-pip-version-check', '--find-links', str(wheels), '--target', str(libraries),
                    '-r', str(ROOT / 'requirements-lock.txt')], check=True)
    sys.path.insert(0, str(ROOT))
    import bootstrap
    bootstrap.verify_signature(python / 'python.exe', 'Python Software Foundation')
    bootstrap.verify_signature(RUNTIME / 'codex/codex-x86_64-pc-windows-msvc.exe', 'OpenAI')
    bootstrap.run_process([python / 'python.exe', '-c', 'from agents import Agent; from jsonschema import validate; from PIL import Image; print("Bundle imports passed")'])
    files = {p.relative_to(RUNTIME).as_posix(): digest(p)
             for p in sorted(RUNTIME.rglob('*')) if distributable(p)}
    manifest = {'platform': 'windows-x64', 'python': '3.13.15', 'codex': '0.157.1',
                'archives': {name: {'url': url, 'sha256': sha} for name, (url, sha) in ARCHIVES.items()},
                'notices': {name: {'url': url, 'sha256': sha} for name, (url, sha) in NOTICES.items()},
                'requirements_sha256': hashlib.sha256((ROOT / 'requirements-lock.txt').read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                'wheels': {p.name: digest(p) for p in sorted(wheels.glob('*.whl'))}, 'files': files}
    (RUNTIME / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Bundled {len(files)} verified files. No account data copied.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Approve maintainer downloads for this build')
    if not parser.parse_args().download:
        parser.error('--download is required; this is a maintainer build, not end-user setup')
    build()
