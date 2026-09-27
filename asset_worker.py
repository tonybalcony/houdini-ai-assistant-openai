"""One bounded local texture/render-status request, away from Houdini's UI thread."""
import json
import sys
from diagnostics import redact
from texture_contracts import TEXTURE_NAMES
RENDER_NAMES={'houdini_solaris_render_status','houdini_solaris_render_preview','houdini_solaris_render_cancel'}

def call(name,arguments):
    if name in TEXTURE_NAMES:
        import texture_assets
        return texture_assets.call(name,arguments)
    if name in RENDER_NAMES:
        from solaris_contracts import validate_arguments
        import render_jobs
        validate_arguments(name,arguments)
        return {'houdini_solaris_render_status':render_jobs.status,
                'houdini_solaris_render_preview':render_jobs.preview,
                'houdini_solaris_render_cancel':render_jobs.cancel}[name](**arguments)
    raise ValueError('Unknown local asset tool.')

if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.readline())
        print(json.dumps(call(request['name'],request['arguments'])))
    except Exception as exc:
        print(json.dumps({'status':'error','error':redact(exc)}))
