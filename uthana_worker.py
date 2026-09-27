"""One bounded Uthana call in a separate process; stdout contains one JSON result."""
import json
import sys
import uthana_client


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        message = json.loads(sys.stdin.buffer.readline(100_000))
        result = uthana_client.call(message['tool'], message['arguments'])
        if result.get('status') in ('FAILED', 'UNKNOWN', 'SUBMITTING'):
            result = {**result, 'ok': False}
    except Exception as exc:
        # Avoid URL credentials, tokens or server response bodies in generic errors.
        text = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Uthana connection or local cache operation failed.'
        try:
            text = text.replace(uthana_client.api_key(), '[redacted]')
        except ValueError:
            pass
        result = {'ok': False, 'error': text[:1000]}
    print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
