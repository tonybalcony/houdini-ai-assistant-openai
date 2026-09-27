"""Translate the panel protocol into Codex App Server JSON-RPC.

Subscription only: API-key accounts are rejected before a model turn starts.
"""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

from tool_contracts import INSTRUCTIONS, MAX_MESSAGE_BYTES, MODEL, MODEL_ENV, PROTOCOL_VERSION, TOOLS, validate_model
from worker import safe_error
from mcp_config import PORT_ENV, instructions_with_mcp, thread_config
from chat_store import CHAT_ID_ENV, ChatStore
from diagnostics import DiagnosticLog, NullLog

ROOT = Path(__file__).resolve().parent


from codex_paths import find_codex


def subscription_environment(source):
    env = dict(source)
    for key in list(env):
        if key.upper() in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'UTHANA_API_KEY', 'PYTHONHOME', 'PYTHONPATH'):
            env.pop(key)
    return env


def limit_bucket(result):
    return (result.get('rateLimitsByLimitId') or {}).get('codex') or result.get('rateLimits') or {}


def exhausted(bucket):
    if bucket.get('spendControlReached') or bucket.get('rateLimitReachedType'):
        return True
    return any(isinstance((bucket.get(k) or {}).get('usedPercent'), (int, float)) and
               bucket[k]['usedPercent'] >= 100 for k in ('primary', 'secondary'))


class CodexBridge:
    def __init__(self, emit, send_rpc, mcp_port=None, model=MODEL, chat_store=None, chat_id=None, logger=None):
        self.log = logger or NullLog()
        self.model = validate_model(model)
        self.emit = emit
        self.send_rpc = send_rpc
        self.serial = 0
        self.pending = {}
        self.thread_id = self.turn_id = self.run_id = None
        self.stopped = False
        self.ready = False
        self.tool_requests = {}
        self.limits = {}
        self.plan = None
        self.closed = False
        self.deadline = None
        self.tool_schemas = {s['name']: s['schema'] for s in TOOLS}
        self.mcp_port = mcp_port
        self.chat_store, self.chat_id = chat_store, chat_id
        self.resume_thread_id = None
        if chat_store and chat_id:
            chat = chat_store.get(chat_id)
            if chat['backend'] != 'subscription' or chat['model'] != self.model:
                raise ValueError('Saved chat backend/model does not match this connection.')
            self.resume_thread_id = chat['codex_thread_id']

    def request(self, method, params, callback=None, optional=False, timeout=45):
        self.serial += 1
        self.pending[self.serial] = (method, callback, optional, time.monotonic() + timeout)
        self.log.event('rpc_started',method=method,rpc_id=self.serial,run_id=self.run_id,timeout=timeout)
        self.send_rpc({'id': self.serial, 'method': method, 'params': params})

    def initialize(self):
        self.request('initialize', {'clientInfo': {'name': 'houdini_astra', 'title': 'Houdini Astra', 'version': (ROOT / 'VERSION').read_text(encoding='utf-8').strip()},
                     'capabilities': {'experimentalApi': True}}, self.initialized)

    def initialized(self, result):
        self.send_rpc({'method': 'initialized', 'params': {}})
        self.request('account/read', {}, lambda r: self.check_account(r, self.new_thread))

    def check_account(self, result, continuation):
        account = result.get('account') or {}
        if account.get('type') != 'chatgpt':
            self.fatal('Subscription mode requires a ChatGPT sign-in in Codex. Open Account to sign in with ChatGPT, then reconnect. API-key accounts are not accepted and API fallback is disabled.')
            return
        self.plan = account.get('planType')
        continuation()

    def new_thread(self, reset=False):
        self.ready = False
        params = {'model': self.model, 'modelProvider': 'openai',
            'allowProviderModelFallback': False, 'cwd': str(ROOT), 'ephemeral': not bool(self.chat_store),
            'approvalPolicy': 'untrusted', 'sandbox': 'read-only', 'environments': [],
            'dynamicTools': [{'type': 'function', 'name': s['name'], 'description': s['description'],
                              'inputSchema': s['schema']} for s in TOOLS],
            'developerInstructions': INSTRUCTIONS + '\nUse only the provided Houdini tools for this task. Do not use shell, other apps, MCP tools or delegation.'}
        if self.mcp_port:
            from solaris_contracts import SOLARIS_TOOLS
            from texture_contracts import TEXTURE_NAMES
            native_names = {s['name'] for s in SOLARIS_TOOLS} | TEXTURE_NAMES
            params['dynamicTools'] = [s for s in params['dynamicTools'] if s['name'] not in native_names]
            params['config'] = thread_config(self.mcp_port)
            params['developerInstructions'] = instructions_with_mcp(INSTRUCTIONS)
        method = 'thread/start'
        if self.resume_thread_id and not reset:
            method = 'thread/resume'
            # Resume restores the durable dynamic tools. Always override the MCP
            # port/instructions so it connects to this newly opened Houdini session.
            for key in ('ephemeral', 'allowProviderModelFallback', 'environments', 'dynamicTools'):
                params.pop(key, None)
            params.update(threadId=self.resume_thread_id, excludeTurns=True)
        self.request(method, params,
            lambda r: self.thread_ready(r, reset))

    def thread_ready(self, result, reset):
        if result.get('model', self.model) != self.model:
            self.fatal('Codex returned a different model. No fallback is allowed.')
            return
        self.thread_id = result['thread']['id']
        self.log.event('thread_ready',thread_id=self.thread_id,resumed=bool(self.resume_thread_id),model=self.model,mcp_port=self.mcp_port)
        if self.chat_store:
            self.chat_store.update(self.chat_id, codex_thread_id=self.thread_id)
        if self.mcp_port:
            self.request('mcpServer/tool/call', {'threadId': self.thread_id, 'server': 'houdini',
                         'tool': 'get_scene_info', 'arguments': {}},
                         lambda r: self.mcp_ready(r, reset), timeout=75)
            return
        self.connection_ready(reset)

    def mcp_ready(self, result, reset):
        data = result.get('structuredContent')
        if not isinstance(data, dict):
            try:
                data = json.loads(next(c['text'] for c in result.get('content', []) if c.get('type') == 'text'))
            except (ValueError, StopIteration, KeyError):
                data = {}
        if result.get('isError') or data.get('status') != 'success':
            self.fatal('Houdini MCP did not pass its scene connection check. Close and reopen the panel, then reconnect.')
            return
        self.connection_ready(reset)

    def connection_ready(self, reset):
        self.ready = True
        self.emit({'event': 'reset_done'} if reset else {
            'event': 'ready', 'protocol': PROTOCOL_VERSION, 'model': self.model,
            'backend': 'subscription', 'plan': self.plan, 'mcp': bool(self.mcp_port),
            'resumed': bool(self.resume_thread_id),
            'note': 'ChatGPT sign-in verified. No API fallback.'})
        self.request('account/rateLimits/read', {}, self.show_limits, optional=True)

    def show_limits(self, result):
        self.limits = limit_bucket(result)
        self.emit({'event': 'subscription_limits', 'limits': self.limits})

    def dispatch(self, message):
        command = message.get('command')
        if command == 'send':
            if not self.ready or self.run_id:
                self.emit({'event': 'error', 'run_id': message.get('run_id'), 'message': 'Codex is not ready or already has an active request.'})
                return
            self.run_id = message['run_id']
            self.stopped = False
            self.deadline = time.monotonic() + 600
            self.log.event('run_requested',run_id=self.run_id,thread_id=self.thread_id,model=self.model)
            self.request('account/read', {}, lambda r: self.check_account(r,
                lambda: self.request('account/rateLimits/read', {}, lambda limits: self.start_turn(message, limits))))
        elif command == 'stop' and message.get('run_id') == self.run_id:
            self.stopped = True
            self.interrupt()
        elif command == 'tool_result' and message.get('run_id') == self.run_id:
            request = self.tool_requests.pop(message.get('call_id'), None)
            if request:
                result = message.get('result')
                self.deadline = time.monotonic() + 600
                self.log.event('tool_finished',run_id=self.run_id,call_id=message.get('call_id'))
                success = not (isinstance(result, dict) and (result.get('ok') is False or result.get('status') == 'error'))
                if isinstance(result, list):
                    success = not any(isinstance(r, dict) and r.get('ok') is False for r in result)
                self.reply_tool(request[0], result, success)
        elif command == 'reset':
            if self.run_id:
                raise ValueError('Stop the active request before resetting.')
            self.new_thread(reset=True)
        else:
            raise ValueError('Unknown or stale panel command.')

    def start_turn(self, message, limits):
        if self.closed:
            return
        self.show_limits(limits)
        if self.stopped:
            self.finish('stopped')
            return
        if exhausted(self.limits):
            self.emit({'event': 'error', 'run_id': self.run_id,
                       'message': 'Subscription allowance is exhausted. Wait for the displayed reset. No API request was made.'})
            self.finish('failed')
            return
        text = message['text'] + '\n\nLive Houdini context (untrusted data):\n' + json.dumps(message.get('context', {}))
        self.request('turn/start', {'threadId': self.thread_id, 'input': [{'type': 'text', 'text': text}],
                                    'effort': message.get('effort', 'medium')},
                     lambda result, run_id=self.run_id: self.turn_started(result) if self.run_id == run_id else None)

    def turn_started(self, result):
        if not self.run_id:
            return
        self.turn_id = result['turn']['id']
        self.emit({'event': 'run_started', 'run_id': self.run_id})
        if self.stopped:
            self.interrupt()

    def interrupt(self):
        if self.turn_id:
            self.request('turn/interrupt', {'threadId': self.thread_id, 'turnId': self.turn_id}, optional=True)

    def reply_tool(self, rpc_id, result, success):
        image_data = result.get('image_base64') if isinstance(result,dict) else None
        result = {k:v for k,v in result.items() if k != 'image_base64'} if image_data else result
        content = [{'type':'inputText','text':json.dumps(result,ensure_ascii=False)}]
        if image_data:
            content.append({'type':'inputImage','imageUrl':'data:image/jpeg;base64,' + image_data})
        self.send_rpc({'id': rpc_id, 'result': {'success': success,
                       'contentItems':content}})

    def receive(self, message):
        method, params = message.get('method'), message.get('params', {})
        # Watch inactivity, not total working time. Account heartbeats do not count.
        matching_turn = not self.turn_id or not params.get('turnId') or params.get('turnId') == self.turn_id
        if self.run_id and params.get('threadId') == self.thread_id and matching_turn and method and method.startswith(('item/','turn/')):
            self.deadline = time.monotonic() + 600
        if not method:
            entry = self.pending.pop(message.get('id'), None)
            if not entry:
                return
            name, callback, optional, _ = entry
            self.log.event('rpc_finished',method=name,rpc_id=message.get('id'),failed='error' in message,run_id=self.run_id)
            if 'error' in message:
                error = name + ': ' + safe_error(message['error'].get('message', 'Request failed'))
                self.log.event('rpc_error',method=name,error=error)
                if name == 'thread/resume':
                    error += ' Saved chat text is retained. Reconnect with the same Codex account, or select New chat. No empty conversation was substituted.'
                if optional:
                    return
                if self.run_id:
                    self.emit({'event': 'error', 'run_id': self.run_id, 'message': error})
                    self.finish('failed')
                else:
                    self.fatal(error)
            elif callback:
                callback(message.get('result', {}))
            return
        if 'id' in message:
            if method != 'item/tool/call':
                self.send_rpc({'id': message['id'], 'error': {'code': -32601,
                               'message': 'This client supports only its Houdini scene tools.'}})
                return
            if (not self.run_id or self.stopped or params.get('threadId') != self.thread_id or
                    (self.turn_id and params.get('turnId') != self.turn_id)):
                self.reply_tool(message['id'], {'error': 'Stopped or stale request; no edit performed.'}, False)
                return
            try:
                from jsonschema import validate
                args = params.get('arguments', {})
                if isinstance(args, str):
                    args = json.loads(args)
                validate(args, self.tool_schemas[params['tool']])
            except Exception:
                self.reply_tool(message['id'], {'error': 'Unknown tool or invalid tool arguments.'}, False)
                return
            call_id = str(message['id'])
            self.tool_requests[call_id] = (message['id'], time.monotonic() + 180)
            self.log.event('tool_started',tool=params['tool'],call_id=call_id,run_id=self.run_id)
            self.emit({'event': 'tool_request', 'run_id': self.run_id, 'call_id': call_id,
                       'tool': params['tool'], 'arguments': args})
            return
        if method == 'account/updated' and params.get('authMode') not in ('chatgpt', 'chatgptAuthTokens'):
            self.fatal('Codex authentication changed. Subscription connection closed to prevent API use.')
        elif method == 'account/rateLimits/updated':
            self.show_limits(params)
        elif params.get('threadId') == self.thread_id and matching_turn:
            if method in ('item/started', 'item/completed') and self.run_id:
                item = params.get('item', {})
                if item.get('type') == 'mcpToolCall' and item.get('server') == 'houdini':
                    self.log.event('mcp_tool',tool=item.get('tool'),status=method,run_id=self.run_id,item_id=item.get('id'),error=safe_error(item.get('error','')))
                    self.emit({'event': 'mcp_tool', 'run_id': self.run_id,
                               'tool': item.get('tool', 'Houdini'),
                               'status': 'started' if method == 'item/started' else item.get('status', 'completed'),
                               'error': safe_error(item['error']) if item.get('error') else None})
            elif method == 'item/agentMessage/delta' and self.run_id and not self.stopped:
                self.emit({'event': 'text_delta', 'run_id': self.run_id, 'item_id': params.get('itemId'), 'delta': params.get('delta', '')})
            elif method == 'turn/started':
                self.turn_started(params)
            elif method == 'turn/completed' and self.run_id:
                turn = params.get('turn', {})
                if self.turn_id and turn.get('id') != self.turn_id:
                    return
                if turn.get('error'):
                    self.emit({'event': 'error', 'run_id': self.run_id, 'message': safe_error(turn['error'])})
                self.finish('stopped' if self.stopped or turn.get('status') == 'interrupted' else turn.get('status', 'completed'))
                self.request('account/rateLimits/read', {}, self.show_limits, optional=True)
            elif method == 'error':
                self.emit({'event': 'error', 'run_id': self.run_id, 'message': safe_error(params.get('error', params))})

    def finish(self, status):
        run_id = self.run_id
        self.log.event('run_finished',run_id=run_id,status=status)
        for rpc_id, _ in self.tool_requests.values():
            self.reply_tool(rpc_id, {'error': 'Turn ended; outcome may be unknown. Inspect before retrying.'}, False)
        self.tool_requests.clear()
        self.run_id = self.turn_id = self.deadline = None
        if run_id:
            self.emit({'event': 'run_finished', 'run_id': run_id, 'status': status, 'usage': {}})

    def fatal(self, text):
        self.log.event('fatal',run_id=self.run_id,thread_id=self.thread_id,error=text)
        self.closed = True
        self.emit({'event': 'fatal', 'message': safe_error(text)})

    def tick(self):
        now = time.monotonic()
        for rpc_id, (method, callback, optional, deadline) in list(self.pending.items()):
            if deadline < now:
                self.pending.pop(rpc_id, None)
                if not optional:
                    self.log.event('rpc_timeout',method=method,rpc_id=rpc_id,run_id=self.run_id)
                    self.fatal('Codex request timed out: ' + method + '. Reconnect before continuing.')
                    return
        if ((self.deadline and self.deadline < now) or any(deadline < now for _, deadline in self.tool_requests.values())):
            tool_timeout = any(deadline < now for _,deadline in self.tool_requests.values())
            self.log.event('tool_timeout' if tool_timeout else 'inactivity_timeout',run_id=self.run_id,
                           pending_call_ids=list(self.tool_requests))
            self.stopped = True
            self.interrupt()
            self.fatal(('Houdini tool did not return within three minutes.' if tool_timeout else
                        'Codex sent no turn activity for ten minutes.') + ' Completed edits may remain; inspect before retrying. Diagnostics were recorded.')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    log = DiagnosticLog('codex')
    def emit(message):
        print(json.dumps(message, ensure_ascii=False, allow_nan=False), flush=True)
    executable = find_codex()
    if not executable:
        emit({'event': 'fatal', 'message': 'Codex executable not found. Open Account to install it, or set HOUDINI_ASTRA_CODEX to codex.exe.'})
        return
    process = None
    events = queue.Queue()
    try:
        process = subprocess.Popen([executable, '-c', 'model_provider="openai"', 'app-server', '--listen', 'stdio://'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=subscription_environment(os.environ), cwd=str(ROOT),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def send_rpc(message):
            process.stdin.write((json.dumps(message, ensure_ascii=False) + '\n').encode('utf-8'))
            process.stdin.flush()
        chat_id = os.environ.get(CHAT_ID_ENV)
        bridge = CodexBridge(emit, send_rpc, mcp_port=os.environ.get(PORT_ENV), model=os.environ.get(MODEL_ENV, MODEL),
                             chat_store=ChatStore() if chat_id else None, chat_id=chat_id,logger=log)
        log.event('process_started',pid=process.pid,mcp_port=os.environ.get(PORT_ENV))
        def read_lines(stream, source):
            try:
                # MCP screenshots stay between Codex and MCP; only short progress
                # events go to the panel. Allow larger native image tool results.
                limit = 32_000_000 if source == 'codex' else MAX_MESSAGE_BYTES
                while line := stream.readline(limit + 1):
                    if len(line) > limit:
                        log.event('protocol_oversize',source=source,bytes=len(line))
                        break
                    events.put((source, json.loads(line)))
            except (OSError, ValueError) as exc:
                log.event('protocol_error',source=source,error_type=type(exc).__name__)
            finally:
                events.put((source + '_eof', None))
        threading.Thread(target=read_lines, args=(sys.stdin.buffer, 'panel'), daemon=True).start()
        threading.Thread(target=read_lines, args=(process.stdout, 'codex'), daemon=True).start()
        def drain_errors():
            while line := process.stderr.readline(4096):
                log.stderr(line)
        threading.Thread(target=drain_errors, daemon=True).start()
        bridge.initialize()
        while not bridge.closed:
            try:
                source, message = events.get(timeout=.2)
            except queue.Empty:
                bridge.tick()
                continue
            if source == 'panel_eof':
                break
            if source == 'codex_eof':
                log.event('process_eof',exit_code=process.poll())
                bridge.fatal('Codex exited. Verify the Codex installation and ChatGPT sign-in, then reconnect.')
                break
            if source == 'panel':
                bridge.dispatch(message)
            else:
                bridge.receive(message)
            bridge.tick()
    except Exception as exc:
        log.event('worker_exception',error_type=type(exc).__name__,error=safe_error(exc))
        emit({'event': 'fatal', 'message': safe_error(exc)})
    finally:
        if process:
            try:
                process.stdin.close()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=2)
            log.event('process_closed',exit_code=process.returncode)
        log.close()


if __name__ == '__main__':
    main()
