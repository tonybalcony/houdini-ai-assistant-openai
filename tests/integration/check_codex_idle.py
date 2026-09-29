"""Initialize bundled Codex with an empty test profile; no account read or model turn."""
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
from unittest.mock import patch
import access_policy
import codex_policy
from codex_paths import find_codex


def main():
    executable = find_codex()
    checks = Path(__file__).resolve().parents[2] / '.local/checks'
    checks.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='codex-profile-', dir=checks) as directory:
        with patch.object(access_policy, 'ROOT', Path(directory)):
            env = codex_policy.environment()
        process = subprocess.Popen(codex_policy.arguments(executable), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
            cwd=directory, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        messages, errors = queue.Queue(), []
        def read():
            for line in process.stdout:
                messages.put(json.loads(line))
        reader = threading.Thread(target=read, daemon=True)
        stderr = threading.Thread(target=lambda: errors.extend(process.stderr), daemon=True)
        reader.start()
        stderr.start()
        try:
            request = {'id':1, 'method':'initialize', 'params':{
                'clientInfo':{'name':'astra_offline_check','version':'0.6.0'},
                'capabilities':{'experimentalApi':True}}}
            process.stdin.write(json.dumps(request)+'\n')
            process.stdin.flush()
            response = messages.get(timeout=30)
            assert response.get('id') == 1 and 'result' in response, response
            actual = Path(response['result']['codexHome']).resolve()
            assert actual == Path(env['CODEX_HOME']).resolve(), 'Codex ignored private profile'
            assert not (actual / 'auth.json').exists(), 'No sign-in should have occurred'
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
            reader.join(timeout=2)
            stderr.join(timeout=2)
            process.stdout.close()
            process.stderr.close()
        unknown = [line for line in errors if 'unknown' in line.lower() or 'unrecognized' in line.lower()]
        assert not unknown, unknown
        print('PASS: bundled Codex initialized with private empty profile; no login, account read or model request')


if __name__ == '__main__':
    main()
