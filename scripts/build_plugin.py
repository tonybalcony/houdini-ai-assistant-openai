"""Build the audited source plus manifest-verified portable Windows runtime."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_FOLDERS = {'tests', 'scripts', '.github'}


def build():
    subprocess.run([sys.executable,str(ROOT/'scripts/audit_release.py')],cwd=ROOT,check=True)
    version = subprocess.check_output(['git','show',':VERSION'],cwd=ROOT).decode().strip()
    names = [n for n in subprocess.check_output(['git','ls-files','--cached','-z'],cwd=ROOT).decode().split('\0') if n]
    output = ROOT / 'dist' / ('houdini-ai-assistant-' + version + '.zip')
    output.parent.mkdir(exist_ok=True)
    runtime = ROOT / '.runtime'
    manifest_path = runtime / 'manifest.json'
    if not manifest_path.is_file():
        raise RuntimeError('Build the offline runtime first: python scripts/build_runtime.py --download')
    manifest = json.loads(manifest_path.read_text())
    requirement_hash = hashlib.sha256(subprocess.check_output(['git', 'show', ':requirements-lock.txt'], cwd=ROOT)).hexdigest()
    if manifest['requirements_sha256'] != requirement_hash:
        raise ValueError('Runtime does not match staged dependency versions.')
    temporary = output.with_suffix('.zip.part')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            if name.split('/')[0] in DEVELOPMENT_FOLDERS:
                continue
            target = name if name == 'houdini-ai-assistant.json' else 'houdini-ai-assistant-openai/' + name
            archive.writestr(target,subprocess.check_output(['git','show',':'+name],cwd=ROOT))
        for name, expected in manifest['files'].items():
            path = (runtime / name).resolve()
            if not path.is_relative_to(runtime.resolve()):
                raise ValueError('Unsafe runtime manifest path.')
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError('Runtime checksum mismatch: ' + name)
            archive.write(path, 'houdini-ai-assistant-openai/.runtime/' + name)
        archive.write(manifest_path, 'houdini-ai-assistant-openai/.runtime/manifest.json')
    temporary.replace(output)
    print(output)
    return output


if __name__=='__main__':
    build()
