"""Portable discovery and synthetic fixtures for integration checks, not runtime tools."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".local/checks"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def find_hython():
    explicit = os.environ.get('HOUDINI_ASTRA_HYTHON')
    if explicit:
        if not Path(explicit).is_file():
            raise FileNotFoundError('HOUDINI_ASTRA_HYTHON does not point to hython.exe')
        return explicit
    candidate = shutil.which('hython.exe')
    if candidate:
        return candidate
    if os.environ.get('HFS'):
        candidate = Path(os.environ['HFS']) / 'bin/hython.exe'
        if candidate.is_file():
            return str(candidate)
    base = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Side Effects Software'
    candidates = list(base.glob('Houdini 22.*/bin/hython.exe'))
    if len(candidates) == 1:
        return str(candidates[0])
    raise RuntimeError('Set HOUDINI_ASTRA_HYTHON to the Houdini 22 hython.exe you want to test.')


def isolated_chat_store():
    from chat_store import ChatStore
    temporary = tempfile.TemporaryDirectory(prefix='astra-check-chat-')
    # Keep the temporary directory alive for the lifetime of the store.
    store = ChatStore(temporary.name)
    store._test_directory = temporary
    return store
