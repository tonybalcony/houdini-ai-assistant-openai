"""Disposable native scene/Qt check; no model or account calls. Run in hython only."""
from pathlib import Path
import tempfile
import hou
from PySide6 import QtWidgets
from access_policy import allowed_file
from astra_panel import AstraPanel
from tests.support import ARTIFACTS

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
with tempfile.TemporaryDirectory(prefix='scene-scope-', dir=ARTIFACTS) as folder:
    root = Path(folder)
    hou.hipFile.clear(suppress_save_prompt=True)
    panel = AstraPanel()
    try:
        assert not panel.chat_store.persistent
        panel.ensure_chat()
        panel.transcript.setPlainText('Temporary conversation')
        panel.input.setPlainText('Unsent draft')
        panel.save_chat()
        first = root / 'first.hipnc'
        hou.hipFile.save(str(first))
        assert panel.chat_store.persistent
        assert 'Temporary conversation' in panel.transcript.toPlainText()
        assert panel.input.toPlainText() == 'Unsent draft'
        first_id = panel.chat['id']
        panel.save_chat()
        assert allowed_file('$HIP/output.txt') == root / 'output.txt'
        try:
            allowed_file(str(ARTIFACTS.parents[2] / 'outside-scope-test.txt'))
        except PermissionError:
            pass
        else:
            raise AssertionError('Outside path was allowed')
        second = root / 'second.hipnc'
        hou.hipFile.save(str(second))
        assert panel.chat_store.persistent and not panel.chat_store.list()
        assert not panel.chat and 'Temporary conversation' not in panel.transcript.toPlainText()
        panel.ensure_chat()
        panel.transcript.setPlainText('Second scene only')
        panel.save_chat()
        hou.hipFile.load(str(first), suppress_save_prompt=True)
        assert panel.chat['id'] == first_id
        assert 'Temporary conversation' in panel.transcript.toPlainText()
        assert 'Second scene only' not in panel.transcript.toPlainText()
        hou.hipFile.clear(suppress_save_prompt=True)
        assert not panel.chat_store.persistent and not panel.chat_store.list()
    finally:
        panel.shutdown()
    reopened = AstraPanel()
    assert not reopened.chat_store.list(), 'Untitled chat must not survive panel restart'
    reopened.shutdown()
print('PASS: native first save, Save As, reopen, untitled discard and outside-path rejection')
