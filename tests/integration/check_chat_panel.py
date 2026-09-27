"""Exercise persistence in real Houdini Qt; isolated DB and no network calls."""
from tests.support import ARTIFACTS
import tempfile
from pathlib import Path
import hou
from PySide6 import QtWidgets
from astra_panel import AstraPanel
from chat_store import ChatStore

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
with tempfile.TemporaryDirectory(prefix='astra-panel-history-') as directory:
    store = ChatStore(directory)
    panel = AstraPanel(chat_store=store)
    panel.model.setCurrentIndex(2)
    panel.input.setPlainText('Make the character walk')
    panel.save_chat()
    first_id = panel.chat['id']
    panel.note('Astra: character ready')
    panel.input.setPlainText('Now turn left')
    panel.shutdown()
    restored = AstraPanel(chat_store=ChatStore(directory))
    assert restored.chat['id'] == first_id
    assert restored.model.currentData() == 'gpt-5.6-terra'
    assert restored.input.toPlainText() == 'Now turn left'
    assert 'character ready' in restored.transcript.toPlainText()
    assert not restored.connected
    restored.new_chat()
    assert restored.chat is None and not restored.input.toPlainText()
    restored.input.setPlainText('A different idea')
    restored.save_chat()
    second_id = restored.chat['id']
    restored.chats.setCurrentIndex(restored.chats.findData(first_id))
    assert restored.chat['id'] == first_id
    assert store.get(second_id)['draft'] == 'A different idea'
    assert restored.input.toPlainText() == 'Now turn left'
    sent = []
    restored.write = lambda message: sent.append(message) or True
    restored.connected = True
    restored.send()
    assert sent[-1]['context']['chat_recovery']['reopened_conversation']
    assert sent[-1]['context']['chat_recovery']['original_scene'] == hou.hipFile.path()
    assert store.get(first_id)['title'] == 'Now turn left'
    restored.receive({'event': 'run_finished', 'run_id': restored.run_id, 'status': 'completed'})
    restored.connected = False
    restored.model.setCurrentIndex(0)
    assert restored.chat is None
    assert 'You: Now turn left' in store.get(first_id)['transcript']
    restored.load_chat(first_id)
    restored.resize(780, 760)
    restored.grab().save(str(ARTIFACTS / 'panel_preview.png'))
    restored.shutdown()
print('PASS: reopen, transcript, draft, model, chat switching, fresh context and new chat preservation')
