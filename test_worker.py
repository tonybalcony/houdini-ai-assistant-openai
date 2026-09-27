"""Offline checks for the SDK bridge lifecycle; no external API traffic."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from worker import Worker, safe_error
from tool_contracts import TOOLS


class FakeStream:
    def __init__(self, worker, fail=False):
        self.worker = worker
        self.fail = fail
        self.cancelled = False
        self.final_output = 'done'
        self.context_wrapper = SimpleNamespace(usage=SimpleNamespace(requests=1, input_tokens=8, output_tokens=2, total_tokens=10))

    async def stream_events(self):
        if self.fail:
            raise RuntimeError('simulated network failure')
        await self.worker.call_tool('houdini_context', {})
        if not self.cancelled:
            yield SimpleNamespace(type='raw_response_event', data=SimpleNamespace(type='response.output_text.delta', delta='done', item_id='text1'))

    def cancel(self, mode='immediate'):
        self.cancelled = True
        for future in self.worker.pending.values():
            if not future.done():
                future.cancel()

    def to_input_list(self):
        return [{'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'done'}]


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.worker = Worker(self.events.append)
        self.worker.make_agent = lambda effort: object()
        self.worker.runner = SimpleNamespace(run_streamed=lambda *a, **kw: FakeStream(self.worker))

    async def wait_tool(self):
        for _ in range(100):
            messages = [m for m in self.events if m['event'] == 'tool_request']
            if messages:
                return messages[-1]
            await asyncio.sleep(.01)
        self.fail('No tool request')

    async def test_roundtrip_history_reset_and_stale_result(self):
        await self.worker.dispatch({'command': 'send', 'run_id': 'r1', 'text': 'hello'})
        request = await self.wait_tool()
        await self.worker.dispatch({'command': 'tool_result', 'run_id': 'wrong', 'call_id': request['call_id'], 'result': {}})
        self.assertFalse(self.worker.pending[request['call_id']].done())
        await self.worker.dispatch({'command': 'tool_result', 'run_id': 'r1', 'call_id': request['call_id'], 'result': {'nodes': []}})
        await self.worker.active
        self.assertEqual(self.events[-1]['status'], 'completed')
        self.assertEqual(self.worker.history[-1]['content'], 'done')
        await self.worker.dispatch({'command': 'reset'})
        self.assertFalse(self.worker.history)

    async def test_stop_and_interrupted_journal(self):
        await self.worker.dispatch({'command': 'send', 'run_id': 'r1', 'text': 'build'})
        await self.wait_tool()
        await self.worker.dispatch({'command': 'stop', 'run_id': 'r1'})
        await self.worker.active
        self.assertEqual(self.events[-1]['status'], 'stopped')
        self.assertIn('result unknown', self.worker.history[-1]['content'])
        self.assertFalse(self.worker.pending)

    async def test_failure_finishes_and_can_retry(self):
        self.worker.runner = SimpleNamespace(run_streamed=lambda *a, **kw: FakeStream(self.worker, fail=True))
        await self.worker.dispatch({'command': 'send', 'run_id': 'r1', 'text': 'hello'})
        await self.worker.active
        self.assertEqual(self.events[-1]['status'], 'failed')
        self.assertIsNone(self.worker.run_id)

    async def test_busy_guard(self):
        await self.worker.dispatch({'command': 'send', 'run_id': 'r1', 'text': 'hello'})
        await self.wait_tool()
        await self.worker.dispatch({'command': 'send', 'run_id': 'r2', 'text': 'duplicate'})
        self.assertEqual(self.worker.run_id, 'r1')
        self.assertIn('already active', self.events[-1]['message'])
        await self.worker.close()

    async def test_missing_key(self):
        with patch('worker.read_api_key', return_value=''):
            self.assertFalse(await self.worker.start())
        self.assertEqual(self.events[-1]['event'], 'fatal')


class ContractTests(unittest.TestCase):
    def test_strict_tool_schemas_and_sdk_construction(self):
        from agents import FunctionTool
        from jsonschema import Draft202012Validator
        for spec in TOOLS:
            Draft202012Validator.check_schema(spec['schema'])
            tool = FunctionTool(spec['name'], spec['description'], spec['schema'], lambda *a: None)
            self.assertTrue(tool.strict_json_schema)

    def test_error_redaction(self):
        self.assertNotIn('secretvalue', safe_error(Exception('secretvalue sk-abc123'), 'secretvalue'))
        self.assertNotIn('sk-', safe_error(Exception('sk-abc123')))


if __name__ == '__main__':
    unittest.main()
