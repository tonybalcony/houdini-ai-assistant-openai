"""Check exact model routing without spending API or subscription tokens."""
import unittest
from codex_worker import CodexBridge
from worker import Worker
from tool_contracts import MODELS, MODEL


class ModelTests(unittest.TestCase):
    def test_codex_routes_all_models_and_disables_ambient_mcp(self):
        for model in MODELS:
            with self.subTest(model=model):
                events, rpc = [], []
                bridge = CodexBridge(events.append, rpc.append, model=model)
                bridge.new_thread()
                self.assertEqual(rpc[-1]['params']['model'], model)
                self.assertEqual(rpc[-1]['params']['config']['mcp_servers'], {})
                self.assertFalse(rpc[-1]['params']['allowProviderModelFallback'])
                bridge.thread_ready({'thread': {'id': 't'}, 'model': model}, False)
                self.assertEqual(events[-1]['model'], model)

    def test_api_agent_uses_selected_model_and_same_tools(self):
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key='test-not-a-real-key')
        for model in MODELS:
            agent = Worker(lambda _: None, client=client, model=model).make_agent('medium')
            self.assertEqual(agent.model.model, model)
            self.assertIn('houdini_apex_keyframes', [tool.name for tool in agent.tools])
            self.assertIn('uthana_generate', [tool.name for tool in agent.tools])

    def test_rejects_silent_fallback(self):
        events = []
        bridge = CodexBridge(events.append, lambda _: None, model='gpt-5.6-terra')
        bridge.thread_ready({'thread': {'id': 't'}, 'model': MODEL}, False)
        self.assertTrue(bridge.closed)
        self.assertFalse(bridge.ready)

    def test_unknown_models_rejected(self):
        with self.assertRaises(ValueError):
            Worker(lambda _: None, model='unknown')
        with self.assertRaises(ValueError):
            CodexBridge(lambda _: None, lambda _: None, model='unknown')


if __name__ == '__main__':
    unittest.main()
