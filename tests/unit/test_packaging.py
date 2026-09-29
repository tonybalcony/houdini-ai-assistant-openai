"""Release boundaries that must survive copying to a clean, different checkout."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import panel_install
from tests.support import find_hython

ROOT = Path(__file__).resolve().parents[2]


class PackagingTests(unittest.TestCase):
    def test_panel_uses_new_location_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='astra moved checkout ') as folder:
            root=Path(folder)
            (root/'astra.pypanel').write_bytes((ROOT/'astra.pypanel').read_bytes())
            target=panel_install.prepare_panel(root)
            script=ET.parse(target).find('.//script').text
            compile(script,'generated-panel','exec')
            self.assertIn(repr(str(root.resolve())),script)
            self.assertNotIn('__ASTRA_INSTALL_ROOT__',script)



    def test_invalid_hython_override_is_not_silently_ignored(self):
        with patch.dict(os.environ,{'HOUDINI_ASTRA_HYTHON':'does-not-exist/hython.exe'}):
            with self.assertRaises(FileNotFoundError):
                find_hython()


if __name__=='__main__':
    unittest.main()
