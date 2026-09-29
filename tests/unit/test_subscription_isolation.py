import tempfile
import unittest
from chat_store import ChatStore
from codex_worker import CodexBridge
from tool_contracts import MODEL, TOOLS


class SubscriptionIsolationTests(unittest.TestCase):
    def test_all_scene_tools_use_panel_dispatch_and_no_native_history(self):
        rpc = []
        bridge = CodexBridge(lambda _: None, rpc.append)
        bridge.new_thread()
        params = rpc[-1]['params']
        self.assertTrue(params['ephemeral'])
        self.assertEqual(params['environments'], [])
        self.assertEqual(params['config']['mcp_servers'], {})
        self.assertFalse(params['config']['features.shell_tool'])
        self.assertFalse(params['config']['features.view_image'])
        self.assertFalse(params['config']['features.apps'])
        self.assertEqual({t['name'] for t in params['dynamicTools']}, {t['name'] for t in TOOLS})
        self.assertFalse(any('texture' in t['name'] for t in TOOLS))

    def test_restored_transcript_is_context_only_on_first_explicit_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatStore(directory)
            chat = store.create('saved.hip', 'subscription', MODEL)
            store.update(chat['id'], transcript='Earlier discussion', draft='Unsent request', codex_thread_id='old-native-id')
            rpc = []
            bridge = CodexBridge(lambda _:None, rpc.append, chat_store=store, chat_id=chat['id'])
            bridge.new_thread()
            self.assertEqual([r['method'] for r in rpc], ['thread/start'])
            self.assertIsNone(bridge.resume_thread_id)
            bridge.thread_id = 'ephemeral'
            bridge.run_id = 'user-turn'
            bridge.start_turn({'text':'My new request'}, {})
            first = rpc[-1]['params']['input'][0]['text']
            self.assertIn('Earlier discussion', first)
            self.assertNotIn('Unsent request', first)
            bridge.start_turn({'text':'Next request'}, {})
            self.assertNotIn('Earlier discussion', rpc[-1]['params']['input'][0]['text'])
            self.assertEqual(store.get(chat['id'])['draft'], 'Unsent request')


if __name__ == '__main__':
    unittest.main()
