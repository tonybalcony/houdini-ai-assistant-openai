"""Real Codex connect/reopen without any model turn, using temporary assistant chats.

Uses the current Codex ChatGPT sign-in. Creates only test-owned empty threads.
"""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from chat_store import ChatStore
from codex_worker import CodexBridge, find_codex, subscription_environment
from tool_contracts import MODEL


def connect(store, chat_id):
    process=subprocess.Popen([find_codex(),'-c','model_provider="openai"','app-server','--listen','stdio://'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        text=True,encoding='utf-8',env=subscription_environment(os.environ),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    messages=queue.Queue()
    def read():
        try:
            for line in process.stdout:
                messages.put(json.loads(line))
        finally:
            messages.put(None)
    reader=threading.Thread(target=read,daemon=True)
    reader.start()
    events=[]
    methods=[]
    def send(message):
        methods.append(message.get('method'))
        assert message.get('method')!='turn/start','No model requests allowed in this check'
        process.stdin.write(json.dumps(message)+'\n')
        process.stdin.flush()
    bridge=CodexBridge(events.append,send,chat_store=store,chat_id=chat_id)
    try:
        bridge.initialize()
        deadline=time.monotonic()+75
        while not bridge.ready and not bridge.closed:
            assert time.monotonic()<deadline,'Codex startup timed out'
            try:
                message=messages.get(timeout=.2)
            except queue.Empty:
                continue
            assert message is not None,'Codex exited during connection'
            bridge.receive(message)
        return bridge,events,methods
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        reader.join(timeout=2)
        process.stdout.close()


with tempfile.TemporaryDirectory(prefix='astra-idle-reconnect-') as directory:
    store=ChatStore(directory)
    chat=store.create('idle-test.hip','subscription',MODEL)
    store.update(chat['id'],draft='An unsent draft')
    first,events,methods=connect(store,chat['id'])
    assert first.ready,events
    assert store.get(chat['id'])['codex_thread_id'] is None
    second,events,methods=connect(ChatStore(directory),chat['id'])
    assert second.ready,events
    assert 'thread/start' in methods and 'thread/resume' not in methods
    assert store.get(chat['id'])['draft']=='An unsent draft'
    print('PASS: connect, close and reconnect without a prompt; draft preserved; no model turn')
    # Emulate the pre-0.5.2 catalogue, which saved the unused connection's ID.
    store.update(chat['id'],codex_thread_id=first.thread_id)
    legacy,events,methods=connect(store,chat['id'])
    if legacy.closed:
        assert events[-1].get('code')=='chat_resume_unavailable',events
        assert 'thread/start' not in methods
        print('REPRODUCED: previously saved idle thread has no available rollout; recovery is explicit')
    else:
        print('NOTE: this Codex version retained the idle rollout; missing-rollout handling is covered offline')
