"""Audit the exact Git index, not ignored private files. No secret values are printed."""
import ast
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DENIED_PARTS = {'.secrets','.env','.chat_history','.logs','.render_jobs','motion_cache',
    'texture_cache','vendor','protocol','.venv','.mcp-venv','.python313','.runtime-install',
    '.local','__pycache__','output','render','backup','tmp','build','dist','.codex','.agents'}
ALLOWED_SUFFIXES = {'.py','.ps1','.md','.txt','.pypanel','.json','.yml','.yaml'}
ALLOWED_NAMES = {'.gitignore','.gitattributes','LICENSE','VERSION'}
HOME_PATH = re.compile(r'(?i)[A-Z]:[/\\]Users[/\\][^/\\\s]+')


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def main():
    names = [n for n in git('ls-files','--cached','-z').decode('utf-8').split('\0') if n]
    if not names:
        raise SystemExit('No staged/tracked source to audit.')
    failures=[]
    for name in names:
        path=Path(name)
        denied = set(path.parts) & DENIED_PARTS
        if denied or path.name in {'local_settings.json','panel_preview.png','auth.json','validation.json'} or path.name.startswith('validation-'):
            failures.append((name,'private/generated path'))
            continue
        if path.suffix not in ALLOWED_SUFFIXES and path.name not in ALLOWED_NAMES:
            failures.append((name,'unexpected file type; review release contents'))
            continue
        data=git('show',':'+name)
        try:
            text=data.decode('utf-8')
            if '\0' in text or len(data)>1_000_000:
                failures.append((name,'binary or oversized content'))
                continue
            if HOME_PATH.search(text):
                failures.append((name,'machine-specific user path'))
            if path.suffix=='.py':
                ast.parse(text,filename=name)
            if path.suffix=='.pypanel':
                ET.fromstring(text)
            if path.suffix=='.md':
                for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
                    if '://' in target or target.startswith('#'):
                        continue
                    destination=(path.parent/target.split('#')[0]).as_posix()
                    if destination not in names:
                        failures.append((name,'link is not included in release: '+destination))
        except (UnicodeError,SyntaxError,ET.ParseError) as exc:
            failures.append((name,type(exc).__name__))
    for name,reason in failures:
        print(name+': '+reason)
    print(f'Audited {len(names)} index files; {len(failures)} findings. Run a separate credential scanner too.')
    return bool(failures)


if __name__=='__main__':
    sys.exit(main())
