"""Shared texture paths; importable in Houdini without HTTP/image dependencies."""
from pathlib import Path
from runtime_settings import texture_library
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'texture_cache'
_library = texture_library()
LIBRARIES = ([_library] if _library else []) + [CACHE.resolve()]
EXTENSIONS = {'.png','.jpg','.jpeg','.tif','.tiff','.exr','.hdr','.bmp','.tga'}

def allowed_texture(value):
    path = Path(value).resolve()
    if path.suffix.lower() not in EXTENSIONS or not path.is_file() or not any(path.is_relative_to(root) for root in LIBRARIES):
        raise ValueError('Texture must be an image in the configured Megascans library or Astra texture cache.')
    return path
