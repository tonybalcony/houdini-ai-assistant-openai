"""Codex discovery shared by the Houdini setup UI and standalone worker."""
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def find_codex():
    from access_policy import contained
    downloaded = contained(ROOT / '.runtime/codex/codex-x86_64-pc-windows-msvc.exe', ROOT)
    return str(downloaded) if downloaded.is_file() else ''
