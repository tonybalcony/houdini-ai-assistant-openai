"""Nonblocking network helper for the Houdini panel, shared by both AI backends."""
import json
import os
from pathlib import Path
from PySide6 import QtCore

ROOT = Path(__file__).resolve().parent


class UthanaCall(QtCore.QObject):
    finished = QtCore.Signal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self.done = False
        self.output = bytearray()
        self.process = QtCore.QProcess(self)
        env = QtCore.QProcessEnvironment.systemEnvironment()
        for key in ('PYTHONHOME', 'PYTHONPATH', 'OPENAI_API_KEY', 'CODEX_API_KEY'):
            env.remove(key)
        env.insert('PYTHONUTF8', '1')
        self.process.setProcessEnvironment(env)
        python = os.environ.get('HOUDINI_ASTRA_PYTHON', str(ROOT / '.venv/Scripts/python.exe'))
        self.process.setProgram(python)
        self.process.setArguments(['-u', str(ROOT / 'uthana_worker.py')])
        self.process.setWorkingDirectory(str(ROOT))
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.finished.connect(self.complete)
        self.process.errorOccurred.connect(lambda *_: self.fail('Uthana helper could not start or exited unexpectedly. Check the cached motion list before retrying.'))
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.fail('Uthana request timed out. The remote job may continue; check cached motions before generating again.'))

    def start(self, message):
        payload = (json.dumps({'tool': message['tool'], 'arguments': message['arguments']}) + '\n').encode()
        def send():
            self.process.write(payload)
            self.process.closeWriteChannel()
        self.process.started.connect(send)
        self.timer.start(150_000)
        self.process.start()

    def read(self):
        self.output.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.output) > 100_000:
            self.fail('Uthana helper response was too large.')

    def complete(self, code, *_):
        if self.done:
            return
        self.read()
        if self.done:
            return
        try:
            if code:
                raise ValueError()
            result = json.loads(self.output)
        except (ValueError, UnicodeError):
            result = {'ok': False, 'error': 'Uthana helper stopped without a valid result. Check cached motions before retrying.'}
        self.done = True
        self.timer.stop()
        self.finished.emit(result)
        self.deleteLater()

    def fail(self, text):
        if not self.done:
            self.done = True
            self.timer.stop()
            self.process.kill()
            self.finished.emit({'ok': False, 'error': text})
            self.deleteLater()

    def shutdown(self):
        self.done = True
        self.timer.stop()
        self.process.blockSignals(True)
        self.process.kill()
        self.process.waitForFinished(500)
