"""Restart, independent writer and model-state checks; no model traffic."""
import tempfile
import unittest
from unittest.mock import patch

from chat_store import ChatLease, ChatStore
from codex_worker import CodexBridge
from worker import Worker
from tool_contracts import MODEL


class SavedChatTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ChatStore(self.directory.name)
        self.chat = self.store.create('C:/scenes/walk.hip', 'subscription', MODEL)
        self.chat_id = self.chat['id']

    def test_reopen_and_independent_worker_panel_updates(self):
        worker_store = ChatStore(self.directory.name)
        self.store.update(self.chat_id, transcript='You: walk\nAstra: done', draft='now turn left')
        worker_store.update(self.chat_id, codex_thread_id='saved-thread')
        self.store.set_active(self.chat_id)
        reopened = ChatStore(self.directory.name)
        record = reopened.get(self.chat_id)
        self.assertEqual(record['draft'], 'now turn left')
        self.assertEqual(record['codex_thread_id'], 'saved-thread')
        self.assertIn('Astra: done', record['transcript'])
        other = reopened.create('C:/scenes/run.hip', 'subscription', MODEL)
        reopened.set_active(other['id'])
        self.assertEqual(reopened.preferred('C:/scenes/walk.hip'), self.chat_id)
        self.assertEqual(reopened.preferred('C:/scenes/unknown.hip'), other['id'])

    def test_two_panels_cannot_own_same_chat(self):
        lease = ChatLease(self.store, self.chat_id)
        try:
            with self.assertRaisesRegex(RuntimeError, 'another panel'):
                ChatLease(self.store, self.chat_id)
        finally:
            lease.close()
        reopened = ChatLease(self.store, self.chat_id)
        reopened.close()

    def test_unused_connection_does_not_leave_a_resume_id(self):
        events, rpc = [], []
        bridge = CodexBridge(events.append, rpc.append, chat_store=self.store, chat_id=self.chat_id)
        bridge.new_thread()
        request = rpc[-1]
        self.assertEqual(request['method'], 'thread/start')
        self.assertFalse(request['params']['ephemeral'])
        bridge.receive({'id': request['id'], 'result': {'thread': {'id': 'durable-thread'}, 'model': MODEL}})
        self.assertIsNone(self.store.get(self.chat_id)['codex_thread_id'])
        self.assertTrue(bridge.ready)
        reopened = CodexBridge(events.append, rpc.append, chat_store=self.store, chat_id=self.chat_id)
        reopened.new_thread()
        self.assertEqual(rpc[-1]['method'], 'thread/start')
        self.assertFalse(any(r.get('method') == 'turn/start' for r in rpc))

    def test_first_user_turn_records_thread_before_submission(self):
        events, rpc = [], []
        bridge = CodexBridge(events.append, rpc.append, chat_store=self.store, chat_id=self.chat_id)
        bridge.thread_id = 'durable-thread'
        bridge.run_id = 'first-turn'
        bridge.start_turn({'text': 'inspect the scene'}, {})
        self.assertEqual(rpc[-1]['method'], 'turn/start')
        self.assertEqual(self.store.get(self.chat_id)['codex_thread_id'], 'durable-thread')
        resumed = CodexBridge(events.append, rpc.append, chat_store=self.store, chat_id=self.chat_id)
        self.assertEqual(resumed.resume_thread_id, 'durable-thread')

    def test_explicit_reset_does_not_restore_previous_thread_on_reopen(self):
        self.store.update(self.chat_id, codex_thread_id='previous-thread')
        events, rpc = [], []
        bridge = CodexBridge(events.append, rpc.append, chat_store=self.store, chat_id=self.chat_id)
        bridge.new_thread(reset=True)
        bridge.receive({'id': rpc[-1]['id'], 'result': {'thread': {'id': 'new-unused-thread'}, 'model': MODEL}})
        self.assertTrue(bridge.ready)
        self.assertIsNone(self.store.get(self.chat_id)['codex_thread_id'])
        self.assertIsNone(bridge.resume_thread_id)

    def test_codex_resume_restores_id_and_refreshes_mcp_port(self):
        self.store.update(self.chat_id, codex_thread_id='durable-thread')
        events, rpc = [], []
        bridge = CodexBridge(events.append, rpc.append, mcp_port=43219,
                             chat_store=self.store, chat_id=self.chat_id)
        bridge.new_thread()
        request = rpc[-1]
        self.assertEqual(request['method'], 'thread/resume')
        self.assertEqual(request['params']['threadId'], 'durable-thread')
        self.assertIn('43219', str(request['params']['config']))
        self.assertNotIn('dynamicTools', request['params'])
        self.assertNotIn('ephemeral', request['params'])
        bridge.receive({'id': request['id'], 'error': {'message': 'thread not found'}})
        self.assertTrue(bridge.closed)
        self.assertEqual(self.store.get(self.chat_id)['codex_thread_id'], 'durable-thread')
        self.assertFalse(any(r.get('method') == 'thread/start' for r in rpc))
        self.assertEqual(events[-1]['code'], 'chat_resume_unavailable')

    def test_missing_rollout_preserves_draft_and_does_not_replay(self):
        self.store.update(self.chat_id, codex_thread_id='other-pc-thread',
                          draft='Do not automatically send this', transcript='Previous conversation')
        events, rpc = [], []
        bridge = CodexBridge(events.append, rpc.append, chat_store=self.store, chat_id=self.chat_id)
        bridge.new_thread()
        bridge.receive({'id': rpc[-1]['id'], 'error': {'message': 'no rollout found for thread id other-pc-thread'}})
        record = self.store.get(self.chat_id)
        self.assertEqual(record['draft'], 'Do not automatically send this')
        self.assertEqual(record['transcript'], 'Previous conversation')
        self.assertEqual(record['codex_thread_id'], 'other-pc-thread')
        self.assertEqual(events[-1]['code'], 'chat_resume_unavailable')
        self.assertEqual([r['method'] for r in rpc], ['thread/resume'])

    def test_api_recovers_full_tool_history_without_replaying(self):
        chat = self.store.create('scene.hip', 'api', MODEL)
        history = [{'role': 'user', 'content': 'make a box'},
                   {'type': 'function_call', 'call_id': 'c1', 'name': 'houdini_context', 'arguments': '{}'},
                   {'type': 'function_call_output', 'call_id': 'c1', 'output': '{"frame":24}'},
                   {'role': 'assistant', 'content': 'done'}]
        self.store.update(chat['id'], api_history=history,
                          pending_input={'role': 'user', 'content': 'now generate motion'})
        events = []
        worker = Worker(events.append, chat_store=self.store, chat_id=chat['id'])
        self.assertEqual(worker.history[:4], history)
        self.assertIn('Do not replay', worker.history[-1]['content'])
        self.assertIsNone(self.store.get(chat['id'])['pending_input'])
        self.assertFalse(events)
        again = Worker(events.append, chat_store=self.store, chat_id=chat['id'])
        self.assertEqual(again.history, worker.history)
        with self.assertRaisesRegex(ValueError, 'backend/model'):
            CodexBridge(events.append, events.append, chat_store=self.store, chat_id=chat['id'])


class CheckpointFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_disk_failure_finishes_turn_without_starting_a_model(self):
        events = []
        worker = Worker(events.append)
        worker.run_id = 'test'
        with patch.object(worker, 'checkpoint', side_effect=OSError('disk full')):
            await worker.run_turn({'text': 'hello'})
        self.assertIsNone(worker.run_id)
        self.assertEqual(events[-1]['event'], 'run_finished')
        self.assertEqual(events[-1]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
