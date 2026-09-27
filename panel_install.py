"""Generate a machine-local Python Panel from the portable source template."""
from pathlib import Path


def prepare_panel(root):
    root = Path(root).resolve()
    template = (root / 'astra.pypanel').read_text(encoding='utf-8')
    if template.count('__ASTRA_INSTALL_ROOT__') != 1:
        raise ValueError('Invalid Astra panel template.')
    target = root / '.local' / 'astra.pypanel'
    target.parent.mkdir(exist_ok=True)
    target.write_text(template.replace('__ASTRA_INSTALL_ROOT__', repr(str(root))), encoding='utf-8')
    return target
