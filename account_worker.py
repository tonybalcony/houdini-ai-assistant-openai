"""Account checks/login over private pipes. Never print credentials or OAuth URLs to logs."""
import json
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from bootstrap import clean_environment, ROOT
from codex_paths import find_codex
from user_account import save_api_key


def emit(event, **fields):
    print(json.dumps({'event':event,**fields}),flush=True)


def validate_api_key(key):
    if not key or len(key)>4096 or any(c.isspace() for c in key):
        raise ValueError('Enter a valid API key without spaces.')
    request=urllib.request.Request('https://api.openai.com/v1/models',
        headers={'Authorization':'Bearer '+key,'User-Agent':'Houdini-Astra-Setup'})
    # Do not forward credentials through redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
            if response.status!=200:
                raise ValueError('API key could not be verified.')
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403):
            raise ValueError('The API key was rejected or cannot list models. Check its permissions and try again.') from None
        raise ValueError('OpenAI could not verify the key right now. Try again later.') from None
    except OSError:
        raise ValueError('Could not reach OpenAI. Check your connection and try again.') from None


def codex_login():
    executable=find_codex()
    if not executable:
        raise RuntimeError('Codex was not found. Run setup again.')
    from codex_policy import arguments, environment
    process=subprocess.Popen(arguments(executable),
        cwd=ROOT,env=environment(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,text=True,encoding='utf-8',
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    messages=queue.Queue()
    def reader(stream,source):
        try:
            while True:
                line=stream.readline(2_000_001)
                if not line or len(line)>2_000_000:
                    break
                messages.put((source,json.loads(line)))
        except (OSError,ValueError):
            pass
        messages.put((source,None))
    codex_reader=threading.Thread(target=reader,args=(process.stdout,'codex'),daemon=True)
    codex_reader.start()
    threading.Thread(target=reader,args=(sys.stdin,'ui'),daemon=True).start()
    serial=0
    pending={}
    login_id=None
    deadline=time.monotonic()+60
    def request(method,params):
        nonlocal serial
        serial+=1
        pending[serial]=method
        process.stdin.write(json.dumps({'id':serial,'method':method,'params':params})+'\n')
        process.stdin.flush()
    try:
        request('initialize',{'clientInfo':{'name':'houdini_astra_setup','version':(ROOT/'VERSION').read_text().strip()}})
        while time.monotonic()<deadline:
            try:
                source,message=messages.get(timeout=.2)
            except queue.Empty:
                continue
            if message is None:
                if source=='ui':
                    return
                raise RuntimeError('Codex closed during sign-in. Retry setup.')
            if source=='ui':
                if message.get('command')=='login':
                    deadline=time.monotonic()+600
                    request('account/login/start',{'type':'chatgpt'})
                elif message.get('command')=='cancel':
                    if login_id:
                        request('account/login/cancel',{'loginId':login_id})
                    return
                continue
            method=pending.pop(message.get('id'),None)
            if 'error' in message:
                raise RuntimeError('Codex could not complete the account request. Update Codex or retry.')
            result=message.get('result') or {}
            if method=='initialize':
                process.stdin.write(json.dumps({'method':'initialized','params':{}})+'\n')
                process.stdin.flush()
                request('account/read',{})
            elif method=='account/read':
                account=result.get('account') or {}
                emit('signed_in' if account.get('type')=='chatgpt' else 'needs_login')
                deadline=time.monotonic()+600
            elif method=='account/login/start':
                login_id=result.get('loginId')
                emit('open_browser',url=result.get('authUrl',''))
            elif message.get('method')=='account/login/completed':
                if (message.get('params') or {}).get('success'):
                    request('account/read',{})
                else:
                    emit('error',message='Sign-in was cancelled or did not complete. Try again.')
        raise RuntimeError('Sign-in timed out. Try again.')
    finally:
        if process.poll() is None:
            process.stdin.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)
        codex_reader.join(timeout=1)
        process.stdout.close()
        process.stdin.close()


def main():
    try:
        if sys.argv[1]=='codex':
            codex_login()
        elif sys.argv[1]=='api':
            value=json.loads(sys.stdin.readline(10_000))
            key=value.get('key','').strip()
            validate_api_key(key)
            save_api_key(key)
            emit('signed_in')
        else:
            raise ValueError('Unknown account action.')
    except Exception as exc:
        # Only our controlled errors are presented; never echo request/response bodies.
        message=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Account setup failed. Please retry.'
        emit('error',message=message)


if __name__=='__main__':
    main()
