"""Download the exact reviewed upstream source; never fetch a moving branch."""
import hashlib
import io
from pathlib import Path
import tempfile
import urllib.request
import zipfile

from mcp_config import REPOSITORY, REVISION

URL = f'https://codeload.github.com/oculairmedia/houdini-mcp/zip/{REVISION}'
SHA256 = '54856e1acaf69a66a4b619a0ec3d437739f39428ee6310991c8c665172c2e187'


def unpack(data, destination):
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('MCP source checksum mismatch. Refusing to install.')
    destination = Path(destination).resolve()
    prefix = 'houdini-mcp-' + REVISION + '/'
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            if not item.filename.startswith(prefix):
                raise ValueError('Unexpected MCP archive layout.')
            relative = item.filename[len(prefix):]
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Unsafe archive path.')
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))


def main():
    if REPOSITORY.exists():
        if not (REPOSITORY / 'pyproject.toml').is_file() or not (REPOSITORY / 'houdini_plugin/python').is_dir():
            raise RuntimeError('Incomplete MCP source folder. Move it aside and rerun setup.')
        print('Using existing pinned MCP source. Runtime code is not automatically updated.')
        return
    REPOSITORY.parent.mkdir(exist_ok=True)
    with urllib.request.urlopen(URL, timeout=90) as response:
        data = response.read(10_000_001)
    if len(data) > 10_000_000:
        raise ValueError('Unexpectedly large MCP source download.')
    with tempfile.TemporaryDirectory(prefix='astra-mcp-', dir=REPOSITORY.parent) as staging:
        extracted = Path(staging) / 'source'
        unpack(data, extracted)
        extracted.rename(REPOSITORY)
    print('Verified and installed MCP source revision ' + REVISION)


if __name__ == '__main__':
    main()
