"""First-run Qt wizard: background installation, native Codex login and protected API key."""
import json
import threading
from pathlib import Path
from PySide6 import QtCore,QtGui,QtWidgets
import bootstrap
from user_account import preferences,remember_backend

ROOT=Path(__file__).resolve().parent


class SetupThread(QtCore.QThread):
    progress=QtCore.Signal(str)
    def __init__(self,backend,parent):
        super().__init__(parent)
        self.backend=backend
        self.cancelled=threading.Event()
        self.result=(False,'Setup did not finish.')
    def run(self):
        try:
            bootstrap.setup(self.backend,self.progress.emit,self.cancelled,consent=True)
            self.result=(True,'')
        except Exception as exc:
            self.result=(False,str(exc))


class SetupDialog(QtWidgets.QDialog):
    ready=QtCore.Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Set up Houdini AI Assistant')
        self.resize(570,430)
        self.setStyleSheet('''
            QDialog { background: #202327; }
            QWidget { color: #e3e8ec; font-family: "Segoe UI"; font-size: 13px; }
            QLabel { background: transparent; }
            QComboBox, QLineEdit, QPushButton { background: #30363e; border: 1px solid #4a535f; border-radius: 5px; padding: 9px; }
            QLineEdit { background: #171a1e; }
            QPushButton:hover { background: #404953; }
            QPushButton:disabled { color: #747e88; }
            QPushButton#continue:enabled { background: #3d7060; border-color: #6a9e8d; }
            QProgressBar { border: 0; background: #171a1e; max-height: 5px; }
            QProgressBar::chunk { background: #6a9e8d; }
        ''')
        self.thread=None
        self.process=None
        self.buffer=b''
        self.verified=False
        self.closing=False
        layout=QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24,24,24,24)
        layout.setSpacing(12)
        heading=QtWidgets.QLabel('Your assistant, your account')
        heading.setStyleSheet('font-size: 21px; font-weight: 600;')
        layout.addWidget(heading)
        intro=QtWidgets.QLabel('Choose how to connect. Software is bundled in this plugin.\nReview and approve local setup below before signing in.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.backend=QtWidgets.QComboBox()
        self.backend.addItem('Use my ChatGPT subscription (Codex)','subscription')
        self.backend.addItem('Use my OpenAI API key (separate billing)','api')
        self.backend.setCurrentIndex(1 if preferences().get('backend')=='api' else 0)
        layout.addWidget(self.backend)
        self.info=QtWidgets.QLabel('')
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.consent=QtWidgets.QCheckBox('I approve this local setup and the selected service connection.')
        self.consent.setChecked(False)
        layout.addWidget(self.consent)
        self.plan=QtWidgets.QLabel('Included: portable Python, Codex and assistant libraries. No pip, downloads, registry changes or system installation.\nWrites: private account/settings/logs inside this plugin; chats and scene outputs beside your saved $HIP.\nNetwork: browser sign-in and the selected AI service. Optional Uthana receives only motion descriptions.\nWindows/Houdini still use their own system files.')
        self.plan.setWordWrap(True)
        layout.addWidget(self.plan)
        self.key=QtWidgets.QLineEdit()
        self.key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Paste your API key')
        layout.addWidget(self.key)
        self.status=QtWidgets.QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress=QtWidgets.QProgressBar()
        self.progress.setRange(0,0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.primary=QtWidgets.QPushButton('Continue')
        self.primary.setObjectName('continue')
        self.primary.clicked.connect(self.advance)
        layout.addWidget(self.primary)
        self.browser=QtWidgets.QPushButton('Open sign-in page again')
        self.browser.hide()
        self.browser.clicked.connect(lambda:self.open_browser(self.auth_url))
        layout.addWidget(self.browser)
        self.logs=QtWidgets.QPushButton('Open setup log')
        self.logs.clicked.connect(lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(ROOT/'.state/setup.log'))))
        layout.addWidget(self.logs)
        self.cancel=QtWidgets.QPushButton('Not now')
        self.cancel.clicked.connect(self.reject)
        layout.addWidget(self.cancel)
        self.backend.currentIndexChanged.connect(self.choice_changed)
        self.choice_changed()

    def choice_changed(self):
        self.stop_account()
        self.verified=False
        api=self.backend.currentData()=='api'
        self.key.setVisible(api)
        self.key.clear()
        self.info.setText('Your key is verified without generating a response, then encrypted for this Windows user. API usage is billed separately.' if api else
            'Sign in securely in your browser. This plugin has a separate sign-in, stored inside its folder. Subscription limits still apply.')
        self.status.setText('Setup verifies bundled files. Nothing is downloaded. No model request is sent during setup.')
        self.primary.setText('Continue')
        self.primary.setEnabled(True)
        self.browser.hide()

    def advance(self):
        if not self.consent.isChecked():
            self.status.setText('Review the setup plan and tick the consent box to continue.')
            return
        if self.verified:
            backend=self.backend.currentData()
            try:
                remember_backend(backend)
            except OSError:
                self.status.setText('Windows could not save your preference. Check access to your user data folder and retry.')
                return
            self.stop_account()
            self.ready.emit(backend)
            self.accept()
            return
        if self.process and self.backend.currentData()=='subscription':
            self.process.write((json.dumps({'command':'login'})+'\n').encode())
            self.primary.setEnabled(False)
            self.status.setText('Complete sign-in in your browser. This window will update automatically.')
            return
        if self.backend.currentData()=='api' and not self.key.text().strip():
            self.status.setText('Enter your own OpenAI API key to continue.')
            self.key.setFocus()
            return
        self.primary.setEnabled(False)
        self.backend.setEnabled(False)
        self.progress.show()
        self.cancel.setText('Cancel setup')
        self.thread=SetupThread(self.backend.currentData(),self)
        self.thread.progress.connect(self.status.setText)
        self.thread.finished.connect(self.install_finished)
        self.thread.start()

    def install_finished(self):
        thread=self.thread
        self.thread=None
        result=thread.result
        thread.deleteLater()
        self.prepared(*result)

    def prepared(self,success,message):
        self.progress.hide()
        self.backend.setEnabled(True)
        self.cancel.setText('Not now')
        if self.closing:
            self.reject()
            return
        if not success:
            self.status.setText(message)
            self.primary.setEnabled(True)
            self.primary.setText('Retry setup')
            return
        self.status.setText('Checking your account...')
        self.start_account()

    def start_account(self):
        self.stop_account()
        self.buffer=b''
        self.process=QtCore.QProcess(self)
        env=QtCore.QProcessEnvironment()
        for key,value in bootstrap.clean_environment().items():
            env.insert(key,value)
        env.insert('PYTHONUTF8','1')
        self.process.setProcessEnvironment(env)
        self.process.setProgram(str(ROOT/'.runtime/python/python.exe'))
        mode='api' if self.backend.currentData()=='api' else 'codex'
        self.process.setArguments(['-u',str(ROOT/'account_worker.py'),mode])
        self.process.setWorkingDirectory(str(ROOT))
        self.process.readyReadStandardOutput.connect(self.read_account)
        self.process.readyReadStandardError.connect(lambda:self.process and self.process.readAllStandardError())
        self.process.errorOccurred.connect(lambda *_:self.account_error('Account helper could not start. Retry setup.'))
        self.process.finished.connect(self.account_finished)
        if mode=='api':
            def send_key():
                payload=json.dumps({'key':self.key.text().strip()})+'\n'
                self.process.write(payload.encode())
                self.process.closeWriteChannel()
                self.key.clear()
            self.process.started.connect(send_key)
        self.process.start()

    def account_finished(self,*args):
        self.read_account()
        if not self.verified and self.process:
            self.account_error('Account setup ended before sign-in completed. Try again.')

    def read_account(self):
        if not self.process:
            return
        self.buffer+=bytes(self.process.readAllStandardOutput())
        if len(self.buffer)>2_000_000:
            self.account_error('Unexpected account response. Retry setup.')
            return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:
                self.account_event(json.loads(line))
            except (ValueError,KeyError):
                self.account_error('Unexpected account response. Retry setup.')
                return

    def account_event(self,message):
        event=message.get('event')
        if event=='signed_in':
            self.verified=True
            self.status.setText('Connected. Your sign-in will be reused next time.')
            self.primary.setText('Open assistant')
            self.primary.setEnabled(True)
            self.browser.hide()
        elif event=='needs_login':
            self.status.setText('Ready to sign in with your ChatGPT account.')
            self.primary.setText('Sign in with ChatGPT')
            self.primary.setEnabled(True)
        elif event=='open_browser':
            self.auth_url=message['url']
            self.open_browser(self.auth_url)
            self.browser.show()
        elif event=='error':
            self.account_error(message.get('message','Account setup failed.'))

    def open_browser(self,url):
        parsed=QtCore.QUrl(url)
        if parsed.scheme()!='https' or parsed.host() not in ('auth.openai.com','chatgpt.com','auth0.openai.com'):
            self.account_error('Codex returned an unexpected sign-in address. Update Codex and retry.')
            return
        QtGui.QDesktopServices.openUrl(parsed)

    def account_error(self,message):
        self.verified=False
        self.stop_account()
        self.browser.hide()
        self.status.setText(message)
        self.primary.setText('Retry')
        self.primary.setEnabled(True)
        self.backend.setEnabled(True)

    def stop_account(self):
        process=self.process
        self.process=None
        if process:
            process.blockSignals(True)
            if process.state()!=QtCore.QProcess.ProcessState.NotRunning:
                process.write(b'{"command":"cancel"}\n')
                process.closeWriteChannel()
                if not process.waitForFinished(4000):
                    process.terminate()
                    process.waitForFinished(1000)
            process.deleteLater()

    def reject(self):
        if self.thread and self.thread.isRunning():
            self.closing=True
            self.thread.cancelled.set()
            self.status.setText('Cancelling after the current installation step finishes...')
            self.cancel.setEnabled(False)
            return
        self.stop_account()
        self.key.clear()
        super().reject()

    def closeEvent(self,event):
        if self.thread and self.thread.isRunning():
            event.ignore()
            self.reject()
        else:
            self.stop_account()
            self.key.clear()
            event.accept()
