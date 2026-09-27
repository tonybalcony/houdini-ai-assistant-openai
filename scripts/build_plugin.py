"""Build a source-only Houdini package archive from the audited Git index."""
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    subprocess.run([sys.executable,str(ROOT/'scripts/audit_release.py')],cwd=ROOT,check=True)
    version = subprocess.check_output(['git','show',':VERSION'],cwd=ROOT).decode().strip()
    names = [n for n in subprocess.check_output(['git','ls-files','--cached','-z'],cwd=ROOT).decode().split('\0') if n]
    output = ROOT / 'dist' / ('houdini-ai-assistant-' + version + '.zip')
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            target = name if name == 'houdini-ai-assistant.json' else 'houdini-ai-assistant-openai/' + name
            archive.writestr(target,subprocess.check_output(['git','show',':'+name],cwd=ROOT))
    print(output)
    return output


if __name__=='__main__':
    build()
