"""Per-scene chat catalogue and API checkpoints; untitled scenes stay in memory."""
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager

CHAT_DIR_ENV = 'HOUDINI_ASTRA_CHAT_DIR'
CHAT_ID_ENV = 'HOUDINI_ASTRA_CHAT_ID'


class ChatStore:
    def __init__(self, directory=None):
        from access_policy import scene_path, scene_directory
        scene = scene_path()
        self.directory = Path(directory).resolve() if directory is not None else (scene_directory(scene) if scene else None)
        self.persistent = self.directory is not None
        self._memory = None
        if self.persistent:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.path = self.directory / 'chats.sqlite3'
        else:
            self.path = None
            self._memory = sqlite3.connect(':memory:')
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, scene TEXT NOT NULL,
                    backend TEXT NOT NULL, model TEXT NOT NULL,
                    transcript TEXT NOT NULL DEFAULT '', draft TEXT NOT NULL DEFAULT '',
                    codex_thread_id TEXT, api_history TEXT NOT NULL DEFAULT '[]',
                    pending_input TEXT, created REAL NOT NULL, updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT);
            ''')
            if directory is None and scene:
                db.execute('UPDATE chats SET scene=?', (str(scene),))

    @contextmanager
    def connection(self):
        db = self._memory or sqlite3.connect(str(self.path), timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            if self.persistent:
                db.close()

    def create(self, scene, backend, model):
        chat_id, now = uuid.uuid4().hex, time.time()
        with self.connection() as db:
            db.execute('INSERT INTO chats(id,title,scene,backend,model,created,updated) VALUES(?,?,?,?,?,?,?)',
                       (chat_id, 'New chat', scene, backend, model, now, now))
        return self.get(chat_id)

    def get(self, chat_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM chats WHERE id=?', (chat_id,)).fetchone()
        if row is None:
            raise ValueError('Saved chat was not found.')
        result = dict(row)
        result['api_history'] = json.loads(result['api_history'])
        result['pending_input'] = json.loads(result['pending_input']) if result['pending_input'] else None
        return result

    def list(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                'SELECT id,title,scene,backend,model,updated FROM chats ORDER BY updated DESC')]

    def update(self, chat_id, **fields):
        allowed = {'title', 'scene', 'transcript', 'draft', 'codex_thread_id', 'api_history', 'pending_input'}
        if not fields or not fields.keys() <= allowed:
            raise ValueError('Invalid chat update.')
        for key in ('api_history', 'pending_input'):
            if key in fields:
                fields[key] = json.dumps(fields[key], ensure_ascii=False, allow_nan=False) if fields[key] is not None else None
        fields['updated'] = time.time()
        with self.connection() as db:
            db.execute('UPDATE chats SET ' + ','.join(key+'=?' for key in fields) + ' WHERE id=?',
                       [*fields.values(), chat_id])

    def set_active(self, chat_id):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings(name,value) VALUES('active',?)", (chat_id,))

    def preferred(self, scene):
        with self.connection() as db:
            active = db.execute("SELECT value FROM settings WHERE name='active'").fetchone()
            if active and active['value']:
                row = db.execute('SELECT id,scene FROM chats WHERE id=?', (active['value'],)).fetchone()
                if row and same_scene(row['scene'], scene):
                    return row['id']
            for row in db.execute('SELECT id,scene FROM chats ORDER BY updated DESC'):
                if same_scene(row['scene'], scene):
                    return row['id']
            return None

    def close(self):
        if self._memory is not None:
            self._memory.close()
            self._memory = None


def same_scene(left, right):
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


class ChatLease:
    """An OS-released lock prevents two panels from writing the same conversation."""
    def __init__(self, store, chat_id):
        if len(chat_id) != 32 or any(c not in '0123456789abcdef' for c in chat_id):
            raise ValueError('Invalid chat identifier.')
        self.file = None
        if store.directory is None:
            return
        directory = store.directory / 'locks'
        directory.mkdir(exist_ok=True)
        self.file = (directory / (chat_id + '.lock')).open('a+b')
        if self.file.tell() == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('This chat is open in another panel. Close it there or choose another chat.')

    def close(self):
        if self.file is not None and not self.file.closed:
            self.file.close()
