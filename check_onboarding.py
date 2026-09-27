"""Real Houdini Qt setup checks. No network, credentials or model calls.

With HOUDINI_ASTRA_CHECK_PACKAGE=1, also require native package/shelf discovery.
"""
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import hou
from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid
import launch_ui
import setup_ui
from astra_panel import AstraPanel
from chat_store import ChatStore
from user_account import remember_backend

ROOT=Path(__file__).resolve().parent
app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def spin_until(predicate,timeout=5):
    deadline=time.monotonic()+timeout
    while not predicate():
        app.processEvents()
        time.sleep(.01)
        assert time.monotonic()<deadline,'UI did not complete in time'


with tempfile.TemporaryDirectory(prefix='astra-setup-ui-') as directory, \
     patch.dict(os.environ,{'HOUDINI_ASTRA_USER_DIR':directory}):
    dialog=setup_ui.SetupDialog()
    dialog.show()
    app.processEvents()
    assert dialog.backend.currentData()=='subscription'
    assert not dialog.key.isVisible()
    preview=ROOT/'.local/setup_preview.png'
    preview.parent.mkdir(exist_ok=True)
    assert dialog.grab().save(str(preview))
    dialog.backend.setCurrentIndex(1)
    assert dialog.key.isVisible()
    assert dialog.key.echoMode()==QtWidgets.QLineEdit.EchoMode.Password
    dialog.advance()
    assert 'Enter your own' in dialog.status.text()

    # First installer error must leave a retryable dialog and no running thread.
    dialog.key.setText('dummy-ui-value')
    with patch.object(setup_ui.bootstrap,'setup',side_effect=RuntimeError('test installation failure')):
        dialog.advance()
        spin_until(lambda:dialog.thread is None)
    assert dialog.primary.isEnabled()
    assert dialog.primary.text()=='Retry setup'

    # Successful retry goes to account verification, not automatic model use.
    with patch.object(setup_ui.bootstrap,'setup'), patch.object(dialog,'start_account') as account:
        dialog.advance()
        spin_until(lambda:dialog.thread is None)
        account.assert_called_once()
    dialog.account_event({'event':'signed_in'})
    assert dialog.primary.text()=='Open assistant'
    received=[]
    dialog.ready.connect(received.append)
    dialog.advance()
    assert received==['api']

    with patch.object(launch_ui.bootstrap,'ready',return_value=True), \
         patch.object(launch_ui,'show_panel') as show, patch.object(launch_ui,'account_setup') as setup:
        launch_ui.launch()
        show.assert_called_once()
        setup.assert_not_called()

    # Auto-connect restores the chosen backend; constructing tests alone never connects.
    panel=AstraPanel(chat_store=ChatStore(Path(directory)/'chats'))
    with patch.object(panel,'connect_worker') as connect:
        assert not panel.connected
        panel.start_saved_connection()
        app.processEvents()
        connect.assert_called_once()
        assert panel.backend.currentData()=='api'
    panel.connected=True
    with patch.object(launch_ui,'account_setup') as setup:
        panel.open_account_setup()
        assert not panel.connected
        assert panel.connect_button.isEnabled()
        setup.assert_called_once()
    panel.input.setPlainText('Keep this API draft')
    panel.save_chat()
    old_chat=panel.chat['id']
    remember_backend('subscription')
    with patch.object(panel,'connect_worker'):
        panel.start_saved_connection()
        app.processEvents()
        assert panel.backend.currentData()=='api'  # Ordinary saved-chat resume.
        panel.start_saved_connection('subscription')
        app.processEvents()
        assert panel.backend.currentData()=='subscription'
        assert panel.chat is None
        assert panel.chat_store.get(old_chat)['draft']=='Keep this API draft'
    panel.shutdown()

    # Cancellation waits for the installer thread before allowing dialog destruction.
    dialog=setup_ui.SetupDialog()
    dialog.backend.setCurrentIndex(0)
    def cancellable(backend,progress,cancel):
        cancel.wait(3)
        raise RuntimeError('cancelled')
    with patch.object(setup_ui.bootstrap,'setup',side_effect=cancellable):
        dialog.show()
        dialog.advance()
        dialog.reject()
        spin_until(lambda:not isValid(dialog) or dialog.thread is None)
        app.processEvents()
    assert not isValid(dialog) or not dialog.isVisible()

if os.environ.get('HOUDINI_ASTRA_CHECK_PACKAGE')=='1':
    assert Path(hou.getenv('HOUDINI_ASTRA_ROOT')).resolve()==ROOT
    assert 'houdini_astra_shelf' in hou.shelves.shelves()
    assert 'houdini_astra_open' in hou.shelves.tools()
    print('PASS: native package discovery and shelf registration')

print('PASS: setup UI, retry, cancellation, masked key, remembered backend and saved launch')
