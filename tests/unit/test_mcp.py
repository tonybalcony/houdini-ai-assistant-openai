"""Offline checks for subscription isolation, readiness, and MCP event handling."""
import unittest

from codex_worker import CodexBridge
from mcp_config import instructions_with_mcp, thread_config
from tool_contracts import INSTRUCTIONS


class McpTests(unittest.TestCase):
    def setUp(self):
        self.events, self.rpc = [], []
        self.bridge = CodexBridge(self.events.append, self.rpc.append, mcp_port=19999)

    def test_thread_configuration_is_local_and_scoped(self):
        self.bridge.new_thread()
        params = self.rpc[-1]['params']
        config = params['config']['mcp_servers.houdini']
        self.assertEqual(config['env']['HOUDINI_ASTRA_MCP_PORT'], '19999')
        self.assertNotIn('url', config)
        self.assertEqual(params['sandbox'], 'read-only')
        self.assertIn('summarize_response', config['disabled_tools'])
        self.assertIn('houdini_apex_keyframes', params['developerInstructions'])
        self.assertNotIn('Do not use shell, other apps, MCP tools', params['developerInstructions'])

    def test_ready_waits_for_real_mcp_scene_read(self):
        self.bridge.thread_ready({'thread': {'id': 't'}}, False)
        self.assertFalse(self.bridge.ready)
        request = self.rpc[-1]
        self.assertEqual(request['method'], 'mcpServer/tool/call')
        self.assertEqual(request['params']['tool'], 'get_scene_info')
        self.bridge.receive({'id': request['id'], 'result': {'structuredContent': {'status': 'success'}}})
        self.assertTrue(self.bridge.ready)
        self.assertTrue(self.events[-1]['mcp'])

    def test_failed_scene_connection_is_not_reported_ready(self):
        self.bridge.mcp_ready({'structuredContent': {'status': 'error'}}, False)
        self.assertTrue(self.bridge.closed)
        self.assertFalse(self.bridge.ready)

    def test_native_mcp_events_reach_panel_without_large_payload(self):
        self.bridge.thread_id, self.bridge.run_id = 't', 'r'
        self.bridge.receive({'method': 'item/completed', 'params': {'threadId': 't',
            'item': {'type': 'mcpToolCall', 'server': 'houdini', 'tool': 'get_node_info',
                     'status': 'completed', 'result': {'image_base64': 'do-not-forward'}}}})
        self.assertEqual(self.events[-1]['event'], 'mcp_tool')
        self.assertNotIn('result', self.events[-1])
        self.bridge.receive({'method': 'item/completed', 'params': {'threadId': 'stale',
            'item': {'type': 'mcpToolCall', 'server': 'houdini'}}})
        self.assertEqual(len(self.events), 1)

    def test_original_api_instructions_remain_narrow(self):
        self.assertIn('You cannot execute arbitrary Python', INSTRUCTIONS)
        extended = instructions_with_mcp(INSTRUCTIONS)
        self.assertNotIn('You cannot execute arbitrary Python', extended)
        self.assertIn('Never upload characters', extended)

    def test_invalid_port_rejected(self):
        for port in [0, 65536, 'invalid']:
            with self.assertRaises(ValueError):
                thread_config(port)


if __name__ == '__main__':
    unittest.main()
