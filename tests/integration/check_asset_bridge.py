"""API worker local asset/image routing without starting the API client or a model."""
from tests.support import ARTIFACTS
import asyncio
import json
from pathlib import Path
from worker import Worker

async def main():
    report=json.loads((ARTIFACTS / 'validation-solaris-render.json').read_text(encoding='utf-8'))
    job_id=report['job_id']
    events=[]
    worker=Worker(events.append)
    worker.run_id='offline-assets'
    status=json.loads(await worker.call_tool('houdini_solaris_render_status',{'job_id':job_id,'wait_seconds':0}))
    assert status['preview_available']
    result=await worker.call_tool('houdini_solaris_render_preview',{'job_id':job_id})
    assert isinstance(result,list) and result[1].type=='image'
    assert result[1].image_url.startswith('data:image/jpeg;base64,')
    assert worker.client is None
    print('PASS: API worker returns actual render image content; no API request')

if __name__=='__main__':
    asyncio.run(main())
