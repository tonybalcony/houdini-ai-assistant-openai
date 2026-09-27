"""Subscription authentication, billing separation and protocol lifecycle checks."""
import unittest
from codex_worker import CodexBridge, subscription_environment, exhausted


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.events, self.rpc = [], []
        self.bridge = CodexBridge(self.events.append, self.rpc.append)

    def reply(self, result):
        self.bridge.receive({'id': self.rpc[-1]['id'], 'result': result})

    def make_ready(self):
        self.bridge.thread_id = 'thread1'
        self.bridge.ready = True

    def test_api_credentials_are_removed(self):
        source = {'OPENAI_API_KEY': 'fake-secret', 'CODEX_API_KEY': 'fake', 'openai_base_url': 'fake', 'UTHANA_API_KEY': 'fake-uthana', 'PATH': 'kept'}
        self.assertEqual(subscription_environment(source), {'PATH': 'kept'})
        self.assertIn('OPENAI_API_KEY', source)

    def test_api_key_auth_never_starts_thread(self):
        self.bridge.initialize()
        self.reply({})
        self.reply({'account': {'type': 'apiKey'}})
        self.assertTrue(self.bridge.closed)
        self.assertFalse(any(r.get('method') == 'thread/start' for r in self.rpc))

    def test_subscription_handshake_and_exact_model(self):
        self.bridge.initialize()
        self.reply({})
        self.reply({'account': {'type': 'chatgpt', 'planType': 'plus'}})
        request = self.rpc[-1]
        self.assertEqual(request['method'], 'thread/start')
        self.assertEqual(request['params']['model'], 'gpt-6-astra')
        self.assertFalse(request['params']['allowProviderModelFallback'])
        self.reply({'thread': {'id': 'thread1'}, 'model': 'gpt-6-astra'})
        self.assertTrue(self.bridge.ready)
        self.assertEqual(self.events[-1]['backend'], 'subscription')

    def test_exhausted_subscription_does_not_start_turn(self):
        self.make_ready()
        self.bridge.dispatch({'command': 'send', 'run_id': 'run1', 'text': 'hi'})
        self.reply({'account': {'type': 'chatgpt'}})
        self.reply({'rateLimits': {'primary': {'usedPercent': 100}}})
        self.assertFalse(any(r.get('method') == 'turn/start' for r in self.rpc))
        self.assertEqual(self.events[-1]['status'], 'failed')

    def test_stop_before_preflight_completes(self):
        self.make_ready()
        self.bridge.dispatch({'command': 'send', 'run_id': 'run1', 'text': 'hi'})
        self.bridge.dispatch({'command': 'stop', 'run_id': 'run1'})
        self.reply({'account': {'type': 'chatgpt'}})
        self.reply({'rateLimits': {'primary': {'usedPercent': 10}}})
        self.assertFalse(any(r.get('method') == 'turn/start' for r in self.rpc))
        self.assertEqual(self.events[-1]['status'], 'stopped')

    def test_late_turn_start_reply_is_ignored(self):
        self.make_ready()
        self.bridge.run_id = 'old'
        self.bridge.start_turn({'text': 'hi'}, {})
        old_id = self.rpc[-1]['id']
        self.bridge.finish('completed')
        self.bridge.run_id = 'new'
        self.bridge.receive({'id': old_id, 'result': {'turn': {'id': 'old-turn'}}})
        self.assertIsNone(self.bridge.turn_id)

    def test_dynamic_tool_roundtrip_and_stopped_rejection(self):
        self.make_ready()
        self.bridge.run_id = 'run1'
        self.bridge.turn_id = 'turn1'
        message = {'method': 'item/tool/call', 'id': 'server1', 'params': {
            'threadId': 'thread1', 'turnId': 'turn1', 'tool': 'houdini_context', 'arguments': {}}}
        self.bridge.receive(message)
        self.assertEqual(self.events[-1]['event'], 'tool_request')
        self.bridge.dispatch({'command': 'tool_result', 'run_id': 'run1', 'call_id': 'server1', 'result': {'objects': []}})
        self.assertTrue(self.rpc[-1]['result']['success'])
        self.bridge.stopped = True
        message['id'] = 'server2'
        self.bridge.receive(message)
        self.assertFalse(self.rpc[-1]['result']['success'])

    def test_unknown_tool_rejected(self):
        self.make_ready()
        self.bridge.run_id = 'run1'
        self.bridge.receive({'method': 'item/tool/call', 'id': 80,
            'params': {'threadId': 'thread1', 'tool': 'shell', 'arguments': {}}})
        self.assertFalse(self.rpc[-1]['result']['success'])

    def test_auth_change_disconnects(self):
        self.bridge.receive({'method': 'account/updated', 'params': {'authMode': 'apikey'}})
        self.assertTrue(self.bridge.closed)

    def test_limit_selection(self):
        self.assertTrue(exhausted({'secondary': {'usedPercent': 100}}))
        self.assertFalse(exhausted({'primary': {'usedPercent': 99}}))
        self.assertFalse(exhausted({}))


if __name__ == '__main__':
    unittest.main()
