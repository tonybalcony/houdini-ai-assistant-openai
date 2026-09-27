"""Small rotating local diagnostic logs. Never pass prompts, code or tool payloads."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import time
import uuid

LOG_DIR_ENV = 'HOUDINI_ASTRA_LOG_DIR'
SESSION_ENV = 'HOUDINI_ASTRA_LOG_SESSION'
DEFAULT_DIRECTORY = Path(__file__).resolve().parent / '.logs'


def redact(value):
    text = str(value)
    text = re.sub(r'(?i)(bearer\s+)[^\s,;]+', r'\1[redacted]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[redacted]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|authorization|secret)[\s\"\x27:=]+)[^\s,;\"\x27}]+',
                  r'\1[redacted]', text)
    text = re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[redacted]', text)
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'UTHANA_API_KEY'):
        secret = os.environ.get(key)
        if secret:
            text = text.replace(secret, '[redacted]')
    return text[:1600]


class NullLog:
    def event(self, *args, **kwargs):
        pass

    def stderr(self, *args):
        pass


class DiagnosticLog:
    def __init__(self, component, directory=None, session=None):
        self.directory = Path(directory or os.environ.get(LOG_DIR_ENV) or DEFAULT_DIRECTORY).resolve()
        self.session = session or os.environ.get(SESSION_ENV) or uuid.uuid4().hex
        self.session = re.sub('[^a-zA-Z0-9_-]', '', self.session)[:64] or uuid.uuid4().hex
        self.path = self.directory / f'{self.session}-{component}-{os.getpid()}.jsonl'
        self.logger = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            # Only our rotated diagnostic files; leave the latest 30 sessions' files.
            files = sorted(self.directory.glob('*-*.jsonl*'), key=lambda p:p.stat().st_mtime, reverse=True)
            for old in files[120:]:
                if old.is_file() and old.resolve().parent == self.directory and time.time()-old.stat().st_mtime > 86400:
                    try:
                        old.unlink()
                    except OSError:
                        pass
            logger = logging.getLogger('astra.' + str(self.path))
            logger.setLevel(logging.INFO)
            logger.propagate = False
            if not logger.handlers:
                handler = RotatingFileHandler(self.path, maxBytes=2_000_000, backupCount=2, encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(message)s'))
                logger.addHandler(handler)
            self.logger = logger
        except OSError:
            pass  # Diagnostic failures must never disconnect the assistant.
        self.event('log_started', component=component, pid=os.getpid())

    def event(self, event, **fields):
        if self.logger:
            try:
                forbidden = {'prompt','arguments','code','result','content','context','transcript','environment','api_key'}
                data = {key: redact(value) if isinstance(value, str) else value
                        for key,value in fields.items() if key not in forbidden}
                self.logger.info(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                                             'event':event,'session':self.session, **data}, ensure_ascii=False))
            except Exception:
                pass

    def stderr(self, data):
        """Retain error categories, not raw SDK output that may contain request data."""
        text = data.decode('utf-8', errors='replace') if isinstance(data, bytes) else str(data)
        categories = [key for key in ('timeout','timed out','connection','broken pipe','eof','mcp',
                                      'unauthorized','401','429','rate limit','panic','error','warning') if key in text.lower()]
        self.event('stderr_observed', categories=categories or ['unclassified'], bytes=len(data))

    def close(self):
        if self.logger:
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)
