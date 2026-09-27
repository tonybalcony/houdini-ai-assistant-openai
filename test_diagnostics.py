import json
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from diagnostics import DiagnosticLog,redact
from codex_worker import CodexBridge


class DiagnosticsTests(unittest.TestCase):
    def test_sensitive_fields_and_stderr_payloads_are_not_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            log=DiagnosticLog('test',directory=directory,session='test-session')
            log.event('failed',prompt='private prompt',arguments={'key':'private'},code='private code',
                      error='Authorization: Bearer sk-testsecret url=https://example.org/file?token=secret')
            log.stderr(b'ERROR mcp: private prompt and secret credential')
            log.close()
            text=log.path.read_text(encoding='utf-8')
            self.assertNotIn('private',text)
            self.assertNotIn('testsecret',text)
            self.assertNotIn('token=secret',text)
            self.assertIn('stderr_observed',text)
            self.assertIn('mcp',text)

    def test_log_rotation_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            log=DiagnosticLog('test',directory=directory)
            log.logger.handlers[0].maxBytes=300
            for i in range(20):
                log.event('tick',count=i)
            log.close()
            self.assertLessEqual(len(list(Path(directory).glob('*'))),3)


class InactivityTests(unittest.TestCase):
    def setUp(self):
        self.events=[]
        self.bridge=CodexBridge(self.events.append,lambda _:None)
        self.bridge.thread_id='thread'
        self.bridge.turn_id='turn'
        self.bridge.run_id='run'
        self.bridge.deadline=100

    def test_active_run_is_not_cut_off_at_ten_minutes(self):
        with patch('codex_worker.time.monotonic',return_value=90):
            self.bridge.receive({'method':'item/reasoning/summaryTextDelta','params':{'threadId':'thread','turnId':'turn'}})
        with patch('codex_worker.time.monotonic',return_value=110):
            self.bridge.tick()
        self.assertFalse(self.bridge.closed)
        self.assertEqual(self.bridge.deadline,690)

    def test_stale_turn_and_account_events_do_not_mask_a_stall(self):
        with patch('codex_worker.time.monotonic',return_value=90):
            self.bridge.receive({'method':'item/agentMessage/delta','params':{'threadId':'thread','turnId':'old','delta':'stale'}})
            self.bridge.receive({'method':'account/rateLimits/updated','params':{}})
        self.assertEqual(self.bridge.deadline,100)
        with patch('codex_worker.time.monotonic',return_value=101):
            self.bridge.tick()
        self.assertTrue(self.bridge.closed)
        self.assertIn('no turn activity',self.events[-1]['message'])

    def test_hung_scene_tool_still_has_a_deadline(self):
        self.bridge.deadline=1000
        self.bridge.tool_requests['call']=(1,99)
        with patch('codex_worker.time.monotonic',return_value=100):
            self.bridge.tick()
        self.assertTrue(self.bridge.closed)
        self.assertIn('three minutes',self.events[-1]['message'])

    def test_dynamic_image_result_is_an_image_not_base64_text(self):
        sent=[]
        self.bridge.send_rpc=sent.append
        self.bridge.reply_tool(1,{'status':'success','image_base64':'abc'},True)
        content=sent[-1]['result']['contentItems']
        self.assertEqual(content[1]['type'],'inputImage')
        self.assertNotIn('image_base64',content[0]['text'])


if __name__=='__main__':
    unittest.main()
