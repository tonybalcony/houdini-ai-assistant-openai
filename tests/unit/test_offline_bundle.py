import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import bootstrap
import access_policy


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(bootstrap, 'ROOT', self.root).start()
        patch.object(access_policy, 'ROOT', self.root).start()
        (self.root / '.runtime').mkdir()

    def manifest(self, files):
        (self.root / '.runtime/manifest.json').write_text(json.dumps({'platform':'windows-x64', 'files':files}))

    def test_missing_bundle_never_starts_a_process_or_download(self):
        with patch.object(bootstrap, 'run_process') as run:
            with self.assertRaisesRegex(RuntimeError, 'Nothing was downloaded'):
                bootstrap.setup('api', lambda _: None, threading.Event(), consent=True)
            run.assert_not_called()
        self.assertFalse((self.root / '.state/setup.json').exists())

    def test_tamper_and_path_escape_are_rejected_before_execution(self):
        (self.root / '.runtime/fake.exe').write_bytes(b'altered')
        for files in ({'fake.exe':hashlib.sha256(b'original').hexdigest()}, {'../../outside':'0'*64}):
            self.manifest(files)
            with patch.object(bootstrap, 'run_process') as run:
                with self.assertRaises((ValueError, PermissionError)):
                    bootstrap.setup('api', lambda _: None, threading.Event(), consent=True)
                run.assert_not_called()
            self.assertFalse((self.root / '.state/setup.json').exists())

    def test_cancel_does_not_write_ready_marker(self):
        self.manifest({'fake.exe':'0'*64})
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            bootstrap.setup('api', lambda _: None, cancel, consent=True)
        self.assertFalse((self.root / '.state/setup.json').exists())

    def test_success_verifies_publishers_before_local_imports(self):
        content = b'test fixture, not an executable'
        (self.root / '.runtime/fake').write_bytes(content)
        self.manifest({'fake':hashlib.sha256(content).hexdigest()})
        (self.root / 'VERSION').write_text('test')
        order = []
        with patch.object(bootstrap, 'verify_signature', side_effect=lambda *a:order.append('signature')), \
             patch.object(bootstrap, 'run_process', side_effect=lambda *a,**kw:order.append('imports')):
            bootstrap.setup('api', lambda _: None, threading.Event(), consent=True)
        self.assertEqual(order, ['signature','signature','imports'])
        self.assertTrue((self.root / '.state/setup.json').is_file())


if __name__ == '__main__':
    unittest.main()
