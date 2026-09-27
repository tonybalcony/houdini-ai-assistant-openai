"""Optional local paths; no credentials belong in this file."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def texture_library():
    value = os.environ.get('HOUDINI_ASTRA_TEXTURE_LIBRARY', '').strip()
    if not value:
        path = ROOT / 'local_settings.json'
        if path.is_file():
            settings = json.loads(path.read_text(encoding='utf-8'))
            value = settings.get('texture_library', '')
            if not isinstance(value, str):
                raise ValueError('local_settings.json: texture_library must be a folder path.')
    return Path(value).expanduser().resolve() if value else None
