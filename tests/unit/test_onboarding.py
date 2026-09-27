"""First-run isolation, credential protection and bootstrap failure boundaries.

Uses dummy credentials only. No model calls, network access or real account changes.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

import account_worker
import bootstrap
import codex_paths
import user_account


class OnboardingTests(unittest.TestCase):
    def test_preferences_survive_new_read_and_reject_unknown_backend(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'HOUDINI_ASTRA_USER_DIR':folder}):
            self.assertEqual(user_account.preferences(),{})
            user_account.remember_backend('api')
            self.assertEqual(user_account.preferences(),{'backend':'api','onboarding_complete':True})
            with self.assertRaises(ValueError):
                user_account.remember_backend('automatic')
            self.assertEqual(user_account.preferences()['backend'],'api')
            (Path(folder)/'preferences.json').write_text('invalid')
            self.assertEqual(user_account.preferences(),{})

    @unittest.skipUnless(os.name=='nt','Windows DPAPI')
    def test_api_key_roundtrip_is_encrypted_and_can_be_removed(self):
        dummy='dummy-onboarding-value-not-a-real-key'
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'HOUDINI_ASTRA_USER_DIR':folder}):
            user_account.save_api_key(dummy)
            encrypted=(Path(folder)/'api-key.dpapi').read_bytes()
            self.assertNotIn(dummy.encode(),encrypted)
            self.assertEqual(user_account.load_api_key(),dummy)
            self.assertFalse((Path(folder)/'api-key.tmp').exists())
            user_account.forget_api_key()
            self.assertEqual(user_account.load_api_key(),'')

    def test_failed_api_verification_never_saves_key(self):
        with patch.object(sys,'argv',['account_worker.py','api']), patch.object(sys,'stdin',io.StringIO('{"key":"dummy"}\n')), \
             patch.object(account_worker,'validate_api_key',side_effect=ValueError('Rejected')), \
             patch.object(account_worker,'save_api_key') as save, patch.object(account_worker,'emit') as emit:
            account_worker.main()
            save.assert_not_called()
            emit.assert_called_once_with('error',message='Rejected')

    def test_api_validation_disables_redirects_and_does_not_echo_response(self):
        error=urllib.error.HTTPError('https://api.openai.com/v1/models',401,'private-body',{},None)
        with patch.object(account_worker.urllib.request,'build_opener') as build:
            build.return_value.open.side_effect=error
            with self.assertRaisesRegex(ValueError,'rejected') as caught:
                account_worker.validate_api_key('dummy')
            self.assertNotIn('private-body',str(caught.exception))
            self.assertIsNone(build.call_args.args[0].redirect_request(None,None,None,None,None,None))
            request=build.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.openai.com/v1/models')
            self.assertEqual(request.method if hasattr(request,'method') else request.get_method(),'GET')

    def test_child_environment_does_not_inherit_api_keys_or_embedded_python(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'dummy','CODEX_API_KEY':'dummy','UTHANA_API_KEY':'dummy',
                                   'PYTHONHOME':'embedded','PYTHONPATH':'embedded','KEEP_ME':'yes'},clear=True):
            self.assertEqual(bootstrap.clean_environment(),{'KEEP_ME':'yes'})

    def test_bad_download_never_publishes_file_and_retry_is_possible(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'runtime.zip'
            response=io.BytesIO(b'broken')
            response.headers={}
            with patch.object(bootstrap.urllib.request,'urlopen',return_value=response):
                with self.assertRaisesRegex(ValueError,'verification failed'):
                    bootstrap.download('https://example.invalid/file',target,'0'*64,lambda _:None,threading.Event())
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_signature_check_ignores_inherited_powershell_module_path(self):
        with patch.dict(os.environ,{'PSMODULEPATH':'incompatible-parent-modules'}), \
             patch.object(bootstrap,'run_process') as run:
            bootstrap.verify_signature(Path('dummy.exe'),'Publisher')
            env=run.call_args.kwargs['env']
            self.assertNotIn('incompatible-parent-modules',env.values())
            self.assertTrue(env['PSModulePath'].endswith('Modules'))
            self.assertIn("$ErrorActionPreference='Stop'",run.call_args.args[0][-1])

    def test_cancelled_download_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as folder:
            response=io.BytesIO(b'dummy')
            response.headers={}
            cancel=threading.Event()
            cancel.set()
            with patch.object(bootstrap.urllib.request,'urlopen',return_value=response):
                with self.assertRaisesRegex(RuntimeError,'cancelled'):
                    bootstrap.download('https://example.invalid/file',Path(folder)/'file','0'*64,lambda _:None,cancel)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_ready_requires_complete_matching_install(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bootstrap,'ROOT',Path(folder)):
            root=Path(folder)
            self.assertFalse(bootstrap.ready())
            for name in ('requirements-lock.txt','requirements-mcp-lock.txt','install_mcp_source.py'):
                (root/name).write_text('test')
            for name in ('.venv/Scripts/python.exe','.mcp-venv/Scripts/python.exe',
                         'vendor/houdini-mcp-7e5cd7a2484b899a6e9251c6f7b90228c2ec7990/pyproject.toml'):
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('test')
            (root/'.local').mkdir()
            (root/'.local/setup.json').write_text(json.dumps({'fingerprint':bootstrap.fingerprint()}))
            self.assertTrue(bootstrap.ready())
            (root/'requirements-lock.txt').write_text('changed')
            self.assertFalse(bootstrap.ready())

    def test_unsafe_codex_zip_cannot_escape_install_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bootstrap,'ROOT',Path(folder)), \
             patch.object(codex_paths,'find_codex',return_value=''), patch.object(bootstrap,'download'), \
             patch.object(bootstrap,'verify_signature') as verify:
            archive=Path(folder)/'.local/downloads/codex-0.157.1.zip'
            archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive,'w') as zipped:
                zipped.writestr('../escaped.exe',b'dummy')
            with self.assertRaisesRegex(ValueError,'archive path'):
                bootstrap.ensure_codex(lambda _:None,threading.Event())
            self.assertFalse((Path(folder)/'.local/escaped.exe').exists())
            verify.assert_not_called()

    def test_failed_setup_does_not_mark_install_ready_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bootstrap,'ROOT',Path(folder)), \
             patch.object(bootstrap,'ensure_python',return_value=Path(sys.executable)), \
             patch.object(bootstrap,'run_process',side_effect=RuntimeError('step failed')):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError,'step failed'):
                    bootstrap.setup('api',lambda _:None,threading.Event())
            self.assertFalse((Path(folder)/'.local/setup.json').exists())

    def test_codex_login_protocol_existing_and_browser_accounts(self):
        # A child process behaves like app-server. No user's native sign-in is read.
        fake='''import json,sys
logged_in=STARTED
for line in sys.stdin:
    msg=json.loads(line)
    method=msg.get('method')
    if method=='initialized': continue
    result={}
    if method=='account/read': result={'account':{'type':'chatgpt'} if logged_in else None}
    if method=='account/login/start': result={'loginId':'test','authUrl':'https://auth.openai.com/test'}
    print(json.dumps({'id':msg['id'],'result':result}),flush=True)
    if method=='account/login/start':
        logged_in=True
        print(json.dumps({'method':'account/login/completed','params':{'success':True}}),flush=True)
'''
        real_popen=subprocess.Popen
        for existing in (True,False):
            events=[]
            class Commands:
                def __init__(self):
                    self.login=threading.Event()
                    self.done=threading.Event()
                    self.sent=False
                    self.cancelled=False
                def readline(self,*args):
                    if not existing and not self.sent:
                        self.login.wait(5)
                        self.sent=True
                        return '{"command":"login"}\n'
                    self.done.wait(5)
                    if self.cancelled:
                        return ''
                    self.cancelled=True
                    return '{"command":"cancel"}\n'
            commands=Commands()
            def emit(event,**fields):
                events.append(event)
                if event=='needs_login': commands.login.set()
                if event=='signed_in': commands.done.set()
            def popen(*args,**kwargs):
                return real_popen([sys.executable,'-u','-c',fake.replace('STARTED',str(existing))],**kwargs)
            with patch.object(account_worker,'find_codex',return_value='fake'), \
                 patch.object(account_worker.subprocess,'Popen',side_effect=popen), \
                 patch.object(account_worker.sys,'stdin',commands), patch.object(account_worker,'emit',side_effect=emit):
                account_worker.codex_login()
            self.assertEqual(events,['signed_in'] if existing else ['needs_login','open_browser','signed_in'])


if __name__=='__main__':
    unittest.main()
