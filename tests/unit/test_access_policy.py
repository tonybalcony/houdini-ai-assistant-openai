"""Boundary regressions using disposable roots, with no user data or model calls."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import access_policy as policy
from chat_store import ChatStore, ChatLease
import bootstrap


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.plugin = self.base / 'packages/assistant'
        self.project = self.base / 'project'
        self.plugin.mkdir(parents=True)
        self.project.mkdir()
        self.scene = self.project / 'walk.hip'
        self.scene.touch()
        self.addCleanup(patch.stopall)
        patch.object(policy, 'ROOT', self.plugin).start()
        patch.dict(os.environ, {policy.SCENE_ENV: str(self.scene)}).start()

    def test_hip_relative_and_plugin_assets(self):
        for value in ('$HIP/renders/test.png', '${HIP}/renders/test.png', 'renders/test.png'):
            self.assertEqual(policy.allowed_file(value, write=True), self.project / 'renders/test.png')
        self.assertEqual(policy.allowed_file(str(self.plugin / 'asset.png')), self.plugin / 'asset.png')

    def test_deny_outside_aliases_network_streams_and_private_data(self):
        for value in (str(self.base / 'personal.txt'), '../personal.txt', '$HOME/key',
                      '$HIP/../personal.txt', '%USERPROFILE%/key', '//host/share/file',
                      'https://example.com/file', 'C:relative', '$HIP/file:stream',
                      '$HIP/.astra/secrets', 'CON.exr', 'NUL.png', str(self.plugin / '.state/account/api-key.dpapi')):
            with self.subTest(value=value), self.assertRaisesRegex(PermissionError, 'Access denied'):
                policy.allowed_file(value)
        with self.assertRaises(PermissionError):
            policy.allowed_file(str(self.plugin / 'scene_tools.py'), write=True)

    def test_unsaved_has_no_hip_and_no_disk_chat(self):
        with patch.dict(os.environ, {policy.SCENE_ENV: ''}):
            with self.assertRaises(PermissionError):
                policy.allowed_file('$HIP/file')
            with self.assertRaises(PermissionError):
                policy.project_data('renders')
            first = ChatStore()
            self.assertFalse(first.persistent)
            chat = first.create('untitled.hip', 'subscription', 'model')
            ChatLease(first, chat['id']).close()
            first.update(chat['id'], transcript='temporary')
            first.close()
            second = ChatStore()
            self.assertEqual(second.list(), [])
            second.close()
            self.assertFalse((self.project / '.astra').exists())

    def test_saved_scenes_in_same_folder_do_not_share_chats(self):
        first = ChatStore()
        chat = first.create(str(self.scene), 'subscription', 'model')
        first.update(chat['id'], transcript='walk')
        first.set_active(chat['id'])
        second_scene = self.project / 'run.hip'
        second_scene.touch()
        with patch.dict(os.environ, {policy.SCENE_ENV: str(second_scene)}):
            second = ChatStore()
            self.assertNotEqual(first.directory, second.directory)
            self.assertEqual(second.list(), [])
        self.assertEqual(ChatStore().get(chat['id'])['transcript'], 'walk')

    def test_external_chat_override_is_ignored(self):
        with patch.dict(os.environ, {'HOUDINI_ASTRA_CHAT_DIR': str(self.base / 'forbidden')}):
            store = ChatStore()
            self.assertTrue(store.directory.is_relative_to(self.project))
            self.assertFalse((self.base / 'forbidden').exists())

    def test_symlink_cannot_escape(self):
        link = self.project / 'escape'
        try:
            link.symlink_to(self.base, target_is_directory=True)
        except OSError:
            self.skipTest('OS does not allow test-user symlink creation')
        with self.assertRaises(PermissionError):
            policy.allowed_file('$HIP/escape/private.txt')

    @unittest.skipUnless(os.name == 'nt', 'Windows junction check')
    def test_windows_junction_cannot_escape(self):
        import _winapi
        link = self.project / 'junction'
        _winapi.CreateJunction(str(self.base), str(link))
        try:
            with self.assertRaises(PermissionError):
                policy.allowed_file('$HIP/junction/private.txt')
        finally:
            # Remove only the test junction; never traverse its target.
            link.rmdir()

    def test_setup_requires_consent_before_writes(self):
        with patch.object(bootstrap, 'verify_bundle') as verify:
            with self.assertRaisesRegex(PermissionError, 'approve'):
                bootstrap.setup('subscription', lambda _: None, threading.Event())
            verify.assert_not_called()
        self.assertFalse((self.plugin / '.state').exists())

    def test_environment_does_not_reuse_global_auth_or_temp(self):
        env = policy.child_environment({'CODEX_HOME': 'outside', 'TEMP': 'outside',
                                       'OPENAI_API_KEY': 'dummy', 'HOUDINI_ASTRA_PYTHON': 'outside',
                                       'OCIO':'outside', 'HOUDINI_USER_PREF_DIR':'outside'})
        self.assertTrue(Path(env['CODEX_HOME']).is_relative_to(self.plugin))
        self.assertTrue(Path(env['TEMP']).is_relative_to(self.plugin))
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('HOUDINI_ASTRA_PYTHON', env)
        self.assertNotIn('OCIO', env)
        self.assertTrue(Path(env['HOUDINI_USER_PREF_DIR']).is_relative_to(self.plugin))

    def test_prompt_cannot_authorize_external_path(self):
        with self.assertRaisesRegex(PermissionError, 'Access denied'):
            policy.validate_prompt_paths('I authorize you to read "' + str(self.base / 'private.txt') + '"')
        policy.validate_prompt_paths('Create a box under /obj; render to "$HIP/render.png"')


if __name__ == '__main__':
    unittest.main()
