"""Text-only Uthana API adapter. No upload API or arbitrary remote URL support."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'motion_cache'
CHARACTER = 'cXi2eAP19XwQ'  # Uthana's built-in Tar; never a user's uploaded rig.
API = 'https://uthana.com/graphql'
REMOTE_TOOLS = {'uthana_generate', 'uthana_status', 'uthana_download', 'uthana_cached_motions'}


def api_key():
    key = os.environ.get('UTHANA_API_KEY', '').strip()
    if not key:
        try:
            key = (ROOT / '.secrets/uthana_api_key').read_text(encoding='utf-8-sig').strip()
        except OSError:
            pass
    if not key or not re.fullmatch(r'[A-Za-z0-9_\-]+', key):
        raise ValueError('Set UTHANA_API_KEY or put the plain key in .secrets/uthana_api_key.')
    return key


def cache_dir(asset_id):
    if not isinstance(asset_id, str) or not re.fullmatch(r'[a-f0-9]{24}', asset_id):
        raise ValueError('Use an asset_id returned by the Uthana tools.')
    return CACHE / asset_id


def read_asset(asset_id):
    try:
        return json.loads((cache_dir(asset_id) / 'asset.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ValueError('Cached motion not found. Use uthana_cached_motions.') from None


def save_asset(asset):
    folder = cache_dir(asset['asset_id'])
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'asset.json'
    temporary = folder / ('.asset-' + str(os.getpid()) + '.json')
    temporary.write_text(json.dumps(asset, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(target)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never forward the API key to a download redirect target.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, key=None):
        self.key = key if key is not None else api_key()
        self.opener = urllib.request.build_opener(NoRedirect())

    def _open(self, url, data=None, authenticate=True, timeout=120):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password:
            raise ValueError('Only HTTPS downloads are accepted.')
        headers = {'User-Agent': 'Houdini-Astra-Uthana/1.0'}
        if authenticate:
            if parsed.netloc != 'uthana.com':
                raise ValueError('Credentials may only be sent to uthana.com.')
            headers['Authorization'] = 'Basic ' + base64.b64encode((self.key + ':').encode()).decode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
        return self.opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=timeout)

    def graphql(self, query, variables=None, timeout=120):
        try:
            with self._open(API, json.dumps({'query': query, 'variables': variables or {}}).encode(), timeout=timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('Uthana returned an oversized response.')
            data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Uthana HTTP {exc.code}; check account access, credits and API key.') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError('Uthana connection failed or timed out. A submitted generation may still be running; do not submit a replacement automatically.') from None
        if data.get('errors'):
            message = '; '.join(str(e.get('message', 'Uthana error')) for e in data['errors'])
            raise ValueError(message.replace(self.key, '[redacted]')[:800])
        return data['data']

    def generate(self, prompt, seconds, model, variant):
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1600:
            raise ValueError('Provide a motion description of 1 to 1600 characters.')
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 4 <= seconds <= 10:
            raise ValueError('Generate 4 to 10 seconds at a time.')
        if model not in ('quality', 'standard') or type(variant) is not int or not 0 <= variant <= 999:
            raise ValueError('Choose quality or standard, and a variant from 0 to 999.')
        if model == 'quality' and seconds != int(seconds):
            raise ValueError('Quality mode requires a whole number of seconds.')
        seconds = int(seconds) if seconds == int(seconds) else float(seconds)
        spec = {'prompt': prompt.strip(), 'seconds': seconds, 'model': model, 'variant': variant}
        asset_id = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:24]
        folder = cache_dir(asset_id)
        folder.mkdir(parents=True, exist_ok=True)
        # A persistent reservation also prevents concurrent panels from billing twice.
        try:
            with (folder / 'submission.lock').open('x'):
                pass
        except FileExistsError:
            if (folder / 'asset.json').exists():
                return read_asset(asset_id)
            return {'asset_id': asset_id, 'status': 'UNKNOWN', 'note': 'Submission reserved; do not automatically resubmit.'}
        asset = {'asset_id': asset_id, **spec, 'character_id': CHARACTER,
                 'status': 'SUBMITTING', 'created_at': time.time()}
        save_asset(asset)
        try:
            if model == 'quality':
                result = self.graphql('''mutation($prompt:String!, $length:Float!, $character:String!) {
                    create_text_to_motion_job(prompt:$prompt, length:$length, character_id:$character,
                        model:"text-to-motion-3.0", rewrite_prompt:true) { job { id status } } }''',
                    {'prompt': prompt.strip(), 'length': float(seconds), 'character': CHARACTER})
                job = result['create_text_to_motion_job']['job']
                asset.update(job_id=job['id'], status=job['status'])
            else:
                result = self.graphql('''mutation($prompt:String!, $length:Float!, $seed:Int!, $character:String!) {
                    create_text_to_motion(prompt:$prompt, length:$length, character_id:$character,
                        model:"text-to-motion-bucmd", seed:$seed, steps:50,
                        foot_ik:true, retargeting_ik:true) { motion { id name } } }''',
                    {'prompt': prompt.strip(), 'length': float(seconds), 'seed': variant + 1, 'character': CHARACTER})
                asset.update(motion_id=result['create_text_to_motion']['motion']['id'], status='FINISHED')
        except Exception as exc:
            asset.update(status='FAILED' if isinstance(exc, ValueError) else 'UNKNOWN', error=str(exc)[:800])
        save_asset(asset)
        return asset

    def status(self, asset_id, wait_seconds=0):
        if type(wait_seconds) is not int or not 0 <= wait_seconds <= 20:
            raise ValueError('Wait for 0 to 20 seconds.')
        asset = read_asset(asset_id)
        if not asset.get('job_id') or asset['status'] in ('FINISHED', 'FAILED'):
            return asset
        deadline = time.monotonic() + wait_seconds
        while True:
            result = self.graphql('query($id:String!) { job(job_id:$id) { id status result } }', {'id': asset['job_id']}, timeout=30)
            job = result['job']
            asset['status'] = job['status']
            if asset['status'] == 'FINISHED':
                payload = job.get('result') or {}
                if isinstance(payload, str):
                    payload = json.loads(payload)
                motion_id = (payload.get('result') or {}).get('id')
                if not motion_id:
                    raise ValueError('Finished Uthana job did not include a motion ID.')
                asset['motion_id'] = motion_id
            if asset['status'] == 'FAILED':
                asset['error'] = 'Uthana reported that generation failed. No automatic resubmission.'
            save_asset(asset)
            if asset['status'] in ('FINISHED', 'FAILED') or time.monotonic() >= deadline:
                return asset
            time.sleep(min(5, max(0, deadline - time.monotonic())))

    def download(self, asset_id, fps, in_place):
        if type(fps) is not int or fps not in (24, 30, 60) or type(in_place) is not bool:
            raise ValueError('Use 24, 30 or 60 FPS and a boolean in_place.')
        asset = self.status(asset_id)
        if asset['status'] != 'FINISHED' or not asset.get('motion_id'):
            raise ValueError('Wait for a finished motion before downloading.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', asset['motion_id']):
            raise ValueError('Invalid motion ID returned by Uthana.')
        filename = f'motion_{fps}_{int(in_place)}.fbx'
        path = cache_dir(asset_id) / filename
        if not path.exists():
            url = f'https://uthana.com/motion/file/motion_viewer/{CHARACTER}/{asset["motion_id"]}/fbx/motion.fbx?fps={fps}&no_mesh=true&in_place={str(in_place).lower()}'
            authenticate = True
            for _ in range(4):
                try:
                    response = self._open(url, authenticate=authenticate)
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code not in (301, 302, 303, 307, 308) or not exc.headers.get('Location'):
                        raise RuntimeError(f'Uthana download HTTP {exc.code}; account downloads may be restricted.') from None
                    url = urllib.parse.urljoin(url, exc.headers['Location'])
                    host = urllib.parse.urlsplit(url).hostname or ''
                    if not (host == 'uthana.com' or host.endswith(('.amazonaws.com', '.cloudfront.net', '.uthana.com', '.googleapis.com'))):
                        raise ValueError('Uthana redirected to an unrecognized download host.')
                    authenticate = host == 'uthana.com'
            else:
                raise ValueError('Too many Uthana download redirects.')
            temp = path.with_suffix('.part')
            total = 0
            try:
                with response, temp.open('wb') as target:
                    while chunk := response.read(256 * 1024):
                        total += len(chunk)
                        if total > 100_000_000:
                            raise ValueError('Motion download exceeds the 100 MB limit.')
                        target.write(chunk)
                with temp.open('rb') as handle:
                    signature = handle.read(100)
                if not (signature.startswith(b'Kaydara FBX Binary') or b'FBX' in signature):
                    raise ValueError('Download is not an FBX motion file.')
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
        asset.update(download={'filename': filename, 'fps': fps, 'in_place': in_place, 'bytes': path.stat().st_size})
        save_asset(asset)
        return asset


def cached_motions():
    result = []
    for path in sorted(CACHE.glob('*/asset.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        asset = read_asset(path.parent.name)
        result.append({k: asset[k] for k in ('asset_id', 'prompt', 'status', 'model', 'seconds', 'download', 'job_id', 'error') if k in asset})
    return {'motions': result}


def call(name, args):
    if name == 'uthana_cached_motions':
        return cached_motions()
    client = Client()
    if name == 'uthana_generate':
        return client.generate(**args)
    if name == 'uthana_status':
        return client.status(**args)
    if name == 'uthana_download':
        return client.download(**args)
    raise ValueError('Unknown Uthana action.')
