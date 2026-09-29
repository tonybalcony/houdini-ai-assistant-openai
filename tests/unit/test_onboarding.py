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
        with tempfile.TemporaryDirectory() as folder, patch.object(user_account,'user_dir',return_value=Path(folder)):
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
        with tempfile.TemporaryDirectory() as folder, patch.object(user_account,'user_dir',return_value=Path(folder)):
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
            env=bootstrap.clean_environment()
            self.assertEqual(env['KEEP_ME'],'yes')
            self.assertTrue(set(env).isdisjoint({'OPENAI_API_KEY','CODEX_API_KEY','UTHANA_API_KEY','PYTHONHOME','PYTHONPATH'}))


    def test_signature_check_ignores_inherited_powershell_module_path(self):
        with patch.dict(os.environ,{'PSMODULEPATH':'incompatible-parent-modules'}), \
             patch.object(bootstrap,'run_process') as run:
            bootstrap.verify_signature(Path('dummy.exe'),'Publisher')
            env=run.call_args.kwargs['env']
            self.assertNotIn('incompatible-parent-modules',env.values())
            self.assertTrue(env['PSModulePath'].endswith('Modules'))
            self.assertIn("$ErrorActionPreference='Stop'",run.call_args.args[0][-1])





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
