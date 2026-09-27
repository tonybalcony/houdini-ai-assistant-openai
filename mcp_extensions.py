"""Add Astra's Solaris tools to the pinned server without changing upstream files."""
import asyncio
import json
import time
from fastmcp.tools import Tool, ToolResult
from mcp.types import ImageContent, TextContent
from solaris_contracts import SOLARIS_TOOLS,validate_arguments
from diagnostics import DiagnosticLog
from texture_contracts import TEXTURE_TOOLS,TEXTURE_NAMES
from fastmcp.server.middleware import Middleware


def install(server, port):
    from houdini_mcp.connection import ensure_connected,get_connection
    from mcp_config import DISABLED_TOOLS
    log = DiagnosticLog('mcp')

    class ToolAudit(Middleware):
        async def on_call_tool(self,context,call_next):
            name = context.message.name
            started=time.monotonic()
            log.event('mcp_call_started',tool=name,port=port)
            try:
                if name=='create_node':
                    args=context.message.arguments or {}
                    def check():
                        ensure_connected('127.0.0.1',port)
                        get_connection().modules.workflow_policy.validate_creation(args.get('node_type',''),args.get('parent_path','/obj'))
                    await asyncio.to_thread(check)
                result=await call_next(context)
                data=getattr(result,'structured_content',None)
                log.event('mcp_call_finished',tool=name,elapsed_ms=round((time.monotonic()-started)*1000),
                          status=data.get('status') if isinstance(data,dict) else None,
                          error=str(data.get('error',''))[:1000] if isinstance(data,dict) else None)
                return result
            except Exception as exc:
                log.event('mcp_call_failed',tool=name,elapsed_ms=round((time.monotonic()-started)*1000),
                          error_type=type(exc).__name__,error=str(exc))
                raise
    server.add_middleware(ToolAudit())

    class SolarisTool(Tool):
        async def run(self, arguments):
            if self.name not in TEXTURE_NAMES:
                validate_arguments(self.name,arguments)
            started = time.monotonic()
            log.event('tool_started',tool=self.name,port=port)
            def invoke():
                from asset_worker import RENDER_NAMES
                if self.name in TEXTURE_NAMES | RENDER_NAMES:
                    import asset_worker
                    return asset_worker.call(self.name,arguments)
                ensure_connected('127.0.0.1',port)
                conn = get_connection()
                return json.loads(conn.modules.solaris_tools.dispatch_json(json.dumps({'name':self.name,'arguments':arguments})))
            try:
                result = await asyncio.to_thread(invoke)
                encoded = result.pop('image_base64',None)
                content = [TextContent(type='text',text=json.dumps(result))]
                if encoded:
                    content.append(ImageContent(type='image',data=encoded,mimeType='image/jpeg'))
                log.event('tool_finished',tool=self.name,status=result.get('status'),job_id=result.get('job_id'),elapsed_ms=round((time.monotonic()-started)*1000))
                return ToolResult(content=content, structured_content=result,is_error=result.get('status')=='error')
            except Exception as exc:
                log.event('tool_failed',tool=self.name,error_type=type(exc).__name__,error=str(exc),elapsed_ms=round((time.monotonic()-started)*1000))
                raise

    for spec in SOLARIS_TOOLS + TEXTURE_TOOLS:
        server.add_tool(SolarisTool(name=spec['name'],description=spec['description'],parameters=spec['schema']))
    server.disable(names=set(DISABLED_TOOLS),components={'tool'})
    log.event('tools_installed',count=len(SOLARIS_TOOLS+TEXTURE_TOOLS),port=port)
