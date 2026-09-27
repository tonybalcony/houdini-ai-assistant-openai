"""Houdini Qt UI and main-thread scene tool dispatcher."""
import json
import os
from pathlib import Path
import uuid
from datetime import datetime
from PySide6 import QtCore, QtGui, QtWidgets
import hou
import scene_tools
from tool_contracts import MAX_MESSAGE_BYTES, MODEL, MODELS, MODEL_ENV, PROTOCOL_VERSION
from mcp_config import PORT_ENV
from mcp_session import HoudiniMcpSession
from chat_store import CHAT_DIR_ENV, CHAT_ID_ENV, ChatLease, ChatStore, same_scene
from diagnostics import DiagnosticLog, SESSION_ENV, LOG_DIR_ENV

ROOT = Path(__file__).resolve().parent


class PromptEditor(QtWidgets.QPlainTextEdit):
    """Explicitly reacquire keyboard focus after Houdini changes the active pane."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setCursorWidth(2)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # Houdini can leave Qt's focus widget set while deactivating its caret.
            # A fresh focus transition restarts the editor on the first click.
            self.clearFocus()
            self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.ensureCursorVisible()
        self.viewport().update()


class AstraPanel(QtWidgets.QWidget):
    def __init__(self, chat_store=None):
        super().__init__()
        self.log = DiagnosticLog('panel',session=uuid.uuid4().hex)
        self.chat_store = chat_store or ChatStore()
        self.chat = self.chat_lease = None
        self.restoring_chat = False
        self.reopened_chat = False
        self.process = None
        self.mcp_session = HoudiniMcpSession(logger=self.log)
        self.buffer = b''
        self.connected = self.busy = self.cancelled = self.pending_reset = False
        self.run_id = self.stream_id = self.last_run_status = self.scene_file = None
        self.tool_results = {}
        self.remote_calls = {}
        self.last_tool_results = []
        self.errors = []
        self.generation = self.run_generation = 0
        self._hip_callback = self.on_hip_event
        hou.hipFile.addEventCallback(self._hip_callback)
        self._closed = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QtWidgets.QLabel('ASTRA  /  Houdini assistant')
        title.setObjectName('title')
        layout.addWidget(title)
        self.status = QtWidgets.QLabel('Disconnected · GPT-6 Astra')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.mcp_status = QtWidgets.QLabel('Houdini MCP · starts with Subscription mode')
        self.mcp_status.setToolTip('Diagnostic logs: ' + str(self.log.directory))
        layout.addWidget(self.mcp_status)
        history_row = QtWidgets.QHBoxLayout()
        history_row.addWidget(QtWidgets.QLabel('Saved chats'))
        self.chats = QtWidgets.QComboBox()
        self.chats.setMinimumContentsLength(15)
        self.chats.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.chats.currentIndexChanged.connect(self.chat_selected)
        history_row.addWidget(self.chats, 1)
        self.logs_button=QtWidgets.QPushButton('Logs')
        self.logs_button.setToolTip('Open local connection and tool diagnostics')
        self.logs_button.clicked.connect(lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.log.directory))))
        history_row.addWidget(self.logs_button)
        layout.addLayout(history_row)
        self.transcript = QtWidgets.QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        layout.addWidget(self.transcript, 1)
        self.input = PromptEditor(self)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setFocusProxy(self.input)
        self.input.setPlaceholderText('Describe what to build, or ask about selected nodes…')
        self.input.setMaximumHeight(105)
        layout.addWidget(self.input)
        options = QtWidgets.QHBoxLayout()
        self.backend = QtWidgets.QComboBox()
        self.backend.addItem('Subscription · Codex', 'subscription')
        self.backend.addItem('API · billed by tokens', 'api')
        self.backend.currentIndexChanged.connect(self.backend_changed)
        options.addWidget(self.backend)
        self.model = QtWidgets.QComboBox()
        for model_id, label in MODELS.items():
            self.model.addItem(label, model_id)
        self.model.setToolTip('Changing model starts a new conversation after you click Connect.')
        self.model.currentIndexChanged.connect(self.model_changed)
        layout.addWidget(self.model)
        self.effort = QtWidgets.QComboBox()
        for label, value in [('Quick', 'low'), ('Balanced', 'medium'), ('Thorough', 'high')]:
            self.effort.addItem(label, value)
        self.effort.setCurrentIndex(1)
        self.usage = QtWidgets.QLabel('Subscription allowance appears after connecting')
        self.usage.setWordWrap(True)
        options.addWidget(self.effort)
        options.addWidget(self.usage, 1)
        layout.addLayout(options)
        actions = QtWidgets.QHBoxLayout()
        self.connect_button = QtWidgets.QPushButton('Connect')
        self.send_button = QtWidgets.QPushButton('Send')
        self.send_button.setObjectName('send')
        self.stop_button = QtWidgets.QPushButton('Stop')
        self.undo_button = QtWidgets.QPushButton('Undo last edit')
        self.new_button = QtWidgets.QPushButton('New chat')
        self.account_button = QtWidgets.QPushButton('Account')
        for button in (self.connect_button, self.send_button, self.stop_button, self.undo_button, self.new_button, self.account_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.connect_button.clicked.connect(self.connect_worker)
        self.send_button.clicked.connect(self.send)
        self.stop_button.clicked.connect(self.stop)
        self.undo_button.clicked.connect(self.undo)
        self.new_button.clicked.connect(self.new_chat)
        self.account_button.clicked.connect(self.open_account_setup)
        self.shortcut = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+Return'), self)
        self.shortcut.activated.connect(self.send)
        self.start_timer = QtCore.QTimer(self)
        self.start_timer.setSingleShot(True)
        self.start_timer.timeout.connect(lambda: self.fail('Assistant connection timed out. Reconnect to retry.'))
        self.stop_timer = QtCore.QTimer(self)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(lambda: self.fail('Worker did not stop promptly and was closed. Completed edits remain; reconnect to resume the saved conversation.'))
        self.save_timer = QtCore.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save_chat)
        self.transcript.textChanged.connect(self.schedule_save)
        self.input.textChanged.connect(self.schedule_save)
        self.setStyleSheet('''
            QWidget { background: #202327; color: #e3e8ec; font-family: "Segoe UI"; font-size: 12px; }
            QLabel#title { font-size: 19px; font-weight: 600; color: #b8e3d3; padding-bottom: 3px; }
            QTextBrowser, QPlainTextEdit { background: #171a1e; border: 1px solid #3b424b; border-radius: 5px; padding: 9px; }
            QPushButton, QComboBox { background: #30363e; border: 1px solid #4a535f; border-radius: 4px; padding: 7px; }
            QPushButton:hover { background: #404953; }
            QPushButton:disabled { color: #747e88; border-color: #353c43; }
            QPushButton#send:enabled { background: #3d7060; border-color: #6a9e8d; }
        ''')
        self.update_controls()
        self.note('Subscription mode uses your ChatGPT sign-in through Codex. API mode is available only when you explicitly select it; there is no automatic fallback. Scene context is sent to the selected service. Ctrl+Enter sends.')
        self.refresh_chats()
        preferred = self.chat_store.preferred(hou.hipFile.path())
        if preferred:
            self.load_chat(preferred)

    def start_saved_connection(self, backend=None):
        """Only the real shelf/panel entry calls this; tests don't auto-connect."""
        from user_account import preferences
        saved = preferences()
        if not saved.get('onboarding_complete'):
            return
        # An explicit setup choice wins and preserves the older chat separately.
        # Ordinary reopening still resumes that chat's original billing mode.
        if backend is not None or not self.chat:
            self.backend.setCurrentIndex(1 if (backend or saved.get('backend')) == 'api' else 0)
        QtCore.QTimer.singleShot(0, self.connect_worker)

    def open_account_setup(self):
        if self.busy:
            self.note('Stop the current request before changing accounts.')
            return
        self.shutdown_process()
        self.start_timer.stop()
        self.stop_timer.stop()
        self.connected = self.pending_reset = False
        self.status.setText('Account setup')
        self.update_controls()
        from launch_ui import account_setup
        def ready(backend):
            if self._closed:
                return
            self.backend.setCurrentIndex(1 if backend == 'api' else 0)
            self.connect_worker()
        account_setup(self, ready)

    def schedule_save(self):
        if not self.restoring_chat and not self._closed:
            self.save_timer.start()

    def ensure_chat(self):
        if self.chat is None:
            self.chat = self.chat_store.create(hou.hipFile.path(), self.backend.currentData(), self.model.currentData())
            self.chat_lease = ChatLease(self.chat_store, self.chat['id'])
            self.chat_store.set_active(self.chat['id'])
            self.refresh_chats()

    def save_chat(self):
        if self.restoring_chat:
            return
        try:
            if self.chat is None and self.input.toPlainText().strip():
                self.ensure_chat()
            if self.chat:
                self.chat_store.update(self.chat['id'], transcript=self.transcript.toPlainText(),
                                       draft=self.input.toPlainText())
        except Exception as exc:
            self.status.setText('Chat could not be saved: ' + str(exc))

    def refresh_chats(self):
        self.chats.blockSignals(True)
        self.chats.clear()
        self.chats.addItem('New chat', None)
        for chat in self.chat_store.list():
            label = chat['title'] + ' · ' + Path(chat['scene']).name
            self.chats.addItem(label, chat['id'])
        self.chats.setCurrentIndex(max(0, self.chats.findData(self.chat['id'] if self.chat else None)))
        self.chats.blockSignals(False)

    def chat_selected(self):
        chat_id = self.chats.currentData()
        if chat_id:
            self.load_chat(chat_id)
        else:
            self.new_chat()

    def load_chat(self, chat_id):
        if self.busy or (self.chat and self.chat['id'] == chat_id):
            return
        try:
            chat = self.chat_store.get(chat_id)
            if self.backend.findData(chat['backend']) < 0 or self.model.findData(chat['model']) < 0:
                raise ValueError('This saved chat uses a backend or model unavailable in this panel.')
            lease = ChatLease(self.chat_store, chat_id)
        except Exception as exc:
            self.note(str(exc))
            self.refresh_chats()
            return
        self.save_chat()
        self.shutdown_process()
        if self.chat_lease:
            self.chat_lease.close()
        self.chat, self.chat_lease = chat, lease
        self.connected = self.pending_reset = False
        self.cancelled = True
        self.run_id = None
        self.start_timer.stop()
        self.stop_timer.stop()
        self.restoring_chat = True
        for selector, value in ((self.backend, chat['backend']), (self.model, chat['model'])):
            selector.blockSignals(True)
            selector.setCurrentIndex(selector.findData(value))
            selector.blockSignals(False)
        self.transcript.setPlainText(chat['transcript'])
        self.input.setPlainText(chat['draft'])
        self.restoring_chat = False
        self.reopened_chat = True
        self.chat_store.set_active(chat_id)
        self.refresh_chats()
        self.status.setText('Saved chat restored · ' + self.model.currentText() + ' · click Connect')
        self.note('Saved conversation restored. Connect to continue with fresh scene context.')
        self.update_controls()

    def model_changed(self):
        self.backend_changed()
        self.status.setText('Disconnected · ' + self.model.currentText())
        self.note('Model selected: ' + self.model.currentText() + '. Click Connect to start a fresh conversation.')

    def backend_changed(self):
        self.save_chat()
        self.shutdown_process()
        if self.chat_lease:
            self.chat_lease.close()
        self.chat = self.chat_lease = None
        self.reopened_chat = False
        self.restoring_chat = True
        self.transcript.clear()
        self.input.clear()
        self.restoring_chat = False
        self.refresh_chats()
        self.start_timer.stop()
        self.stop_timer.stop()
        self.connected = self.pending_reset = False
        self.run_id = None
        self.cancelled = True
        self.status.setText('Disconnected · ' + self.backend.currentText())
        self.usage.setText('Subscription allowance after connecting' if self.backend.currentData() == 'subscription' else 'API mode: requests are billed by tokens')
        self.note('Backend changed. Click Connect to begin a new conversation; scene edits remain.')
        self.update_controls()

    def note(self, text):
        self.append_text('\n' + text + '\n')

    def append_text(self, text):
        cursor = self.transcript.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def update_controls(self):
        self.send_button.setEnabled(self.connected and not self.busy and not self.pending_reset)
        self.stop_button.setEnabled(self.busy and not self.cancelled)
        self.undo_button.setEnabled(not self.busy)
        self.new_button.setEnabled(not self.busy and not self.pending_reset)
        self.connect_button.setEnabled(not self.connected and not self.busy)
        self.effort.setEnabled(not self.busy)
        self.backend.setEnabled(not self.busy)
        self.model.setEnabled(not self.busy and not (self.process and not self.connected))
        self.chats.setEnabled(not self.busy and not (self.process and not self.connected))

    def write(self, message):
        if not self.process or self.process.state() != QtCore.QProcess.ProcessState.Running:
            return False
        payload = (json.dumps(message, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        if len(payload) > MAX_MESSAGE_BYTES:
            raise ValueError('Scene message is too large. Narrow your selection or request.')
        return self.process.write(payload) >= 0

    def connect_worker(self):
        try:
            self.ensure_chat()
            self.save_chat()
        except Exception as exc:
            self.note('Unable to open saved chat: ' + str(exc))
            return
        self.shutdown_process()
        python = Path(os.environ.get('HOUDINI_ASTRA_PYTHON', str(ROOT / '.venv/Scripts/python.exe')))
        if not python.is_file():
            self.fail('Assistant software is missing. Open Account to prepare it again.')
            return
        self.buffer = b''
        self.connected = self.pending_reset = False
        if self.backend.currentData() == 'subscription':
            try:
                mcp_port = self.mcp_session.start()
            except Exception as exc:
                self.fail(str(exc))
                return
            self.mcp_status.setText('Houdini MCP · connecting to this scene…')
        else:
            mcp_port = None
            self.mcp_status.setText('Houdini MCP · available in Subscription mode')
        self.process = QtCore.QProcess(self)
        env = QtCore.QProcessEnvironment.systemEnvironment()
        for key in ('PYTHONHOME', 'PYTHONPATH', 'UTHANA_API_KEY'):
            env.remove(key)
        if self.backend.currentData() == 'subscription':
            for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL'):
                env.remove(key)
        env.insert('PYTHONUTF8', '1')
        env.insert('PYTHONUNBUFFERED', '1')
        env.insert(MODEL_ENV, self.model.currentData())
        env.insert(CHAT_DIR_ENV, str(self.chat_store.directory))
        env.insert(CHAT_ID_ENV, self.chat['id'])
        env.insert(SESSION_ENV,self.log.session)
        env.insert(LOG_DIR_ENV,str(self.log.directory))
        env.remove(PORT_ENV)
        if mcp_port:
            env.insert(PORT_ENV, str(mcp_port))
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.setProgram(str(python))
        worker_name = 'codex_worker.py' if self.backend.currentData() == 'subscription' else 'worker.py'
        self.process.setArguments(['-u', str(ROOT / worker_name)])
        self.process.readyReadStandardOutput.connect(self.read_output)
        # Only worker-sanitized API errors are exposed; raw SDK stderr can include request data.
        self.process.readyReadStandardError.connect(lambda: self.process and self.log.stderr(bytes(self.process.readAllStandardError())))
        self.process.errorOccurred.connect(self.process_error)
        self.process.finished.connect(self.process_finished)
        self.log.event('connection_started',backend=self.backend.currentData(),model=self.model.currentData(),mcp_port=mcp_port,chat_id=self.chat['id'])
        self.status.setText('Connecting · ' + self.backend.currentText())
        self.connect_button.setEnabled(False)
        self.model.setEnabled(False)
        self.chats.setEnabled(False)
        if not same_scene(self.chat['scene'], hou.hipFile.path()):
            self.note('This chat was started in ' + Path(self.chat['scene']).name +
                      '. The current scene is ' + Path(hou.hipFile.path()).name + '; it will be inspected before edits.')
        self.start_timer.start(90_000)
        self.process.start()

    def read_output(self):
        if not self.process:
            return
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > MAX_MESSAGE_BYTES and b'\n' not in self.buffer:
            self.fail('Assistant sent an oversized message.')
            return
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                if len(line) > MAX_MESSAGE_BYTES:
                    raise ValueError('Oversized message')
                if line.strip():
                    self.receive(json.loads(line))
            except Exception:
                self.fail('Assistant protocol error. Reconnect before continuing.')
                return

    def receive(self, message):
        event = message.get('event')
        if event != 'text_delta':
            self.log.event('panel_event',kind=event,run_id=message.get('run_id'),call_id=message.get('call_id'),
                           tool=message.get('tool'),status=message.get('status'),error=message.get('message') if event in ('fatal','error') else None)
        if event == 'ready':
            if message.get('protocol') != PROTOCOL_VERSION or message.get('model') != self.model.currentData():
                self.fail('Assistant protocol or model mismatch.')
                return
            self.start_timer.stop()
            self.connected = True
            if message.get('resumed'):
                self.note('Model conversation resumed; previous messages and tool context are available.')
            if message.get('mcp'):
                self.mcp_status.setText('Houdini MCP · connected')
            self.status.setText('Ready · ' + self.model.currentText() + ' · ' + ('ChatGPT subscription verified' if self.backend.currentData() == 'subscription' else 'API access checked on first message'))
            self.update_controls()
            self.save_chat()
            return
        if event == 'fatal':
            self.fail(message.get('message', 'Worker initialization failed.'))
            return
        if event == 'subscription_limits':
            limits = message.get('limits') or {}
            parts = []
            for key, label in [('primary', 'Current window'), ('secondary', 'Longer window')]:
                window = limits.get(key) or {}
                used = window.get('usedPercent')
                if isinstance(used, (int, float)):
                    text = f'{label}: {max(0, min(100, 100-used)):g}% left'
                    if window.get('resetsAt'):
                        text += ' · resets ' + datetime.fromtimestamp(window['resetsAt']).strftime('%d %b %H:%M')
                    parts.append(text)
            self.usage.setText('\n'.join(parts) or 'Subscription limits currently unavailable')
            return
        if event == 'reset_done':
            self.pending_reset = False
            self.status.setText('Ready · ' + self.model.currentText() + ' · new conversation')
            self.update_controls()
            return
        if message.get('run_id') != self.run_id:
            return
        if event == 'text_delta' and not self.cancelled:
            if self.stream_id != message.get('item_id'):
                self.note('Astra:')
                self.stream_id = message.get('item_id')
            self.append_text(message.get('delta', ''))
        elif event == 'tool_request':
            QtCore.QTimer.singleShot(0, lambda m=message: self.handle_tool(m))
        elif event in ('mcp_tool','asset_tool'):
            state = message.get('status', 'completed')
            label='Houdini MCP · ' if event=='mcp_tool' else 'Render · ' if message['tool'].startswith('houdini_solaris_render_') else 'Textures · '
            self.note(label + message['tool'] + ('…' if state == 'started' else ' · ' + state))
            if state != 'started':
                self.last_tool_results.append({'tool': 'mcp:' + message['tool'], 'result': {'status': state}})
            if message.get('error'):
                self.note(message['error'])
        elif event == 'error':
            self.errors.append(message.get('message', 'Unknown error'))
            self.note('Error: ' + self.errors[-1])
        elif event == 'run_finished':
            self.stop_timer.stop()
            self.last_run_status = message.get('status')
            self.busy = False
            self.run_id = None
            self.status.setText(self.model.currentText() + ' · ' + str(self.last_run_status))
            usage = message.get('usage', {})
            if usage:
                self.usage.setText(f"Last request: {usage.get('input_tokens', 0):,} input / {usage.get('output_tokens', 0):,} output tokens")
            elif self.cancelled and self.backend.currentData() == 'api':
                self.usage.setText('Stopped request: final API usage may be incomplete')
            if self.pending_reset:
                self.write({'command': 'reset'})
            self.update_controls()
            self.save_chat()
            self.refresh_chats()

    def handle_tool(self, message):
        call_id = message['call_id']
        if call_id in self.tool_results:
            result = self.tool_results[call_id]
        else:
            try:
                if (not self.busy or self.cancelled or message['run_id'] != self.run_id or
                        self.run_generation != self.generation or self.scene_file != hou.hipFile.path()):
                    raise RuntimeError('Request is stale, stopped, or belongs to a different scene. No action performed.')
                from uthana_client import REMOTE_TOOLS
                if message['tool'] in REMOTE_TOOLS:
                    key = (message['run_id'], call_id)
                    if key not in self.remote_calls:
                        from uthana_qt import UthanaCall
                        task = UthanaCall(self)
                        self.remote_calls[key] = task
                        task.finished.connect(lambda result, m=message: self.finish_remote(m, result))
                        self.note('Uthana · ' + message['tool'].removeprefix('uthana_') + '…')
                        task.start(message)
                    return
                result = scene_tools.call(message['tool'], message['arguments'])
                self.last_tool_results.append({'tool': message['tool'], 'result': result})
                partial = ((isinstance(result, dict) and result.get('ok') is False) or
                           (isinstance(result, list) and any(isinstance(r, dict) and r.get('ok') is False for r in result)))
                label = 'Partial edit — inspect before retrying' if partial else ('Scene updated' if message['tool'] in ('houdini_edit', 'houdini_apex_keyframes', 'houdini_uthana_import', 'houdini_uthana_retarget') else 'Scene inspected')
                self.note(label + ' · ' + message['tool'].removeprefix('houdini_'))
            except Exception as exc:
                result = {'error': str(exc), 'ok': False}
                self.note('Scene tool: ' + str(exc))
            self.tool_results[call_id] = result
        try:
            self.write({'command': 'tool_result', 'run_id': message['run_id'], 'call_id': call_id, 'result': result})
        except Exception as exc:
            self.stop()
            self.note('Could not return scene results: ' + str(exc))

    def finish_remote(self, message, result):
        self.remote_calls.pop((message['run_id'], message['call_id']), None)
        if self._closed:
            return
        if (not self.busy or self.cancelled or message['run_id'] != self.run_id
                or self.run_generation != self.generation or self.scene_file != hou.hipFile.path()):
            self.note('Uthana request ended after Stop or a scene change. Check cached motions to recover its result.')
            return
        self.tool_results[message['call_id']] = result
        self.last_tool_results.append({'tool': message['tool'], 'result': result})
        self.note('Uthana · ' + str(result.get('status', result.get('error', 'ready'))))
        try:
            self.write({'command': 'tool_result', 'run_id': message['run_id'], 'call_id': message['call_id'], 'result': result})
        except Exception:
            self.stop()
            self.note('Could not return Uthana result. Check cached motions before generating again.')

    def send(self):
        text = self.input.toPlainText().strip()
        if not text or not self.connected or self.busy or self.pending_reset:
            return
        try:
            context = scene_tools.context()
            context['chat_recovery'] = {
                'reopened_conversation': self.reopened_chat,
                'original_scene': self.chat['scene'] if self.chat else None,
                'different_scene': bool(self.chat and not same_scene(self.chat['scene'], hou.hipFile.path())),
                'instruction': 'Use this live scene state; re-inspect old node references before edits. Do not replay old requests.',
            }
            run_id = uuid.uuid4().hex
            message = {'command': 'send', 'run_id': run_id, 'text': text,
                       'context': context, 'effort': self.effort.currentData()}
            if not self.write(message):
                raise RuntimeError('Worker is unavailable. Reconnect.')
        except Exception as exc:
            self.note(str(exc))
            return
        self.run_id = run_id
        self.log.event('prompt_sent',run_id=run_id,chat_id=self.chat['id'] if self.chat else None,model=self.model.currentData())
        self.scene_file = hou.hipFile.path()
        self.run_generation = self.generation
        self.busy = True
        self.cancelled = False
        self.stream_id = self.last_run_status = None
        self.tool_results.clear()
        self.last_tool_results = []
        self.errors = []
        self.input.clear()
        self.note('You: ' + text)
        if self.chat and self.chat['title'] == 'New chat':
            self.chat['title'] = ' '.join(text.split())[:70]
            self.chat_store.update(self.chat['id'], title=self.chat['title'])
            self.refresh_chats()
        self.save_chat()
        self.status.setText('Astra is working…')
        self.update_controls()
        self.input.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)

    def stop(self):
        if not self.busy:
            return
        self.cancelled = True
        self.write({'command': 'stop', 'run_id': self.run_id})
        self.status.setText('Stopping… completed edits remain undoable')
        self.stop_timer.start(10_000)
        self.update_controls()

    def new_chat(self):
        if self.busy:
            return
        reconnect = self.connected
        self.start_timer.stop()
        self.stop_timer.stop()
        self.save_timer.stop()
        self.save_chat()
        self.shutdown_process()
        if self.chat_lease:
            self.chat_lease.close()
        self.chat = self.chat_lease = None
        self.chat_store.set_active(None)
        self.connected = self.pending_reset = False
        self.run_id = None
        self.reopened_chat = False
        self.restoring_chat = True
        self.transcript.clear()
        self.input.clear()
        self.restoring_chat = False
        self.refresh_chats()
        self.status.setText('New chat · ' + self.model.currentText())
        self.note('New conversation. Previous chats are saved; scene edits remain.')
        self.update_controls()
        if reconnect:
            self.connect_worker()

    def on_hip_event(self, event):
        if event in (hou.hipFileEventType.BeforeClear, hou.hipFileEventType.BeforeLoad):
            self.generation += 1
            self.save_chat()
            self.fail('Scene changed. Chat saved; reconnect after the new scene loads.')
        elif event in (hou.hipFileEventType.AfterLoad, hou.hipFileEventType.AfterClear):
            preferred = self.chat_store.preferred(hou.hipFile.path())
            if preferred:
                self.load_chat(preferred)
        elif event == hou.hipFileEventType.AfterSave and self.chat:
            self.chat['scene'] = hou.hipFile.path()
            self.chat_store.update(self.chat['id'], scene=self.chat['scene'])
            self.refresh_chats()

    def undo(self):
        if self.busy:
            return
        labels = hou.undos.undoLabels()
        if labels and labels[0] == 'Astra: scene edit':
            hou.undos.performUndo()
            self.note('Undid the last Astra edit group. The next request will read fresh scene context.')
        else:
            self.note('Use Houdini Undo for MCP edits or intervening edits. This button only undoes a dedicated Astra edit group.')

    def fail(self, text):
        self.log.event('panel_disconnected',run_id=self.run_id,error=text)
        self.start_timer.stop()
        self.stop_timer.stop()
        self.shutdown_process()
        self.connected = self.busy = self.pending_reset = False
        self.cancelled = True
        self.reopened_chat = bool(self.chat)
        self.run_id = None
        self.errors.append(text)
        self.status.setText('Disconnected')
        self.note(text)
        self.update_controls()
        self.save_chat()

    def shutdown_process(self):
        self.log.event('connection_closing',run_id=self.run_id)
        self.mcp_session.stop()
        self.mcp_status.setText('Houdini MCP · disconnected')
        if self.process:
            self.process.blockSignals(True)
            self.process.closeWriteChannel()
            if not self.process.waitForFinished(2500):
                self.process.kill()
                self.process.waitForFinished(1000)
            self.process.deleteLater()
            self.process = None

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self.save_timer.stop()
        self.save_chat()
        for task in list(self.remote_calls.values()):
            task.shutdown()
        self.remote_calls.clear()
        self.start_timer.stop()
        self.stop_timer.stop()
        self.cancelled = True
        self.shutdown_process()
        if self.chat_lease:
            self.chat_lease.close()
            self.chat_lease = None
        try:
            hou.hipFile.removeEventCallback(self._hip_callback)
        except hou.Error:
            pass
        self.log.event('panel_closed')
        self.log.close()

    def process_error(self, error):
        # Capture Qt's Windows error before fail() disposes of the process.
        detail = self.process.errorString() if self.process else 'Worker process unavailable'
        program = self.process.program() if self.process else ''
        self.log.event('worker_process_error', error=str(error), detail=detail,
                       program=program, run_id=self.run_id)
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            message = 'Windows could not start the assistant worker: ' + detail
            if program:
                message += '\nProgram: ' + program
        else:
            message = 'Unable to communicate with the assistant worker: ' + detail
        self.fail(message + '\nDiagnostics recorded in ' + str(self.log.directory))

    def process_finished(self, exit_code, exit_status):
        self.log.event('worker_process_exit',exit_code=exit_code,exit_status=str(exit_status),run_id=self.run_id)
        self.fail('Assistant worker closed. Reconnect to resume the saved conversation. Diagnostics recorded in ' + str(self.log.directory))

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
