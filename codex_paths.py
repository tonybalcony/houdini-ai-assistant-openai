"""Codex discovery shared by the Houdini setup UI and standalone worker."""
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def find_codex():
    explicit = os.environ.get('HOUDINI_ASTRA_CODEX')
    if explicit:
        return explicit if Path(explicit).is_file() else ''
    found = shutil.which('codex.exe') or shutil.which('codex')
    if found:
        return found
    candidates = list((Path(os.environ.get('LOCALAPPDATA', '')) / 'OpenAI/Codex/bin').glob('*/codex.exe'))
    if candidates:
        return str(max(candidates, key=lambda p: p.stat().st_mtime))
    downloaded = ROOT / '.local/codex/codex-x86_64-pc-windows-msvc.exe'
    return str(downloaded) if downloaded.is_file() else ''
