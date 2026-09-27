"""Own one upstream loopback RPC listener per Astra panel; no global startup edits."""
import sys
from types import SimpleNamespace

from mcp_config import MCP_PYTHON, REPOSITORY
from diagnostics import NullLog


class HoudiniMcpSession:
    def __init__(self, logger=None):
        self.log=logger or NullLog()
        self.listener = None
        self.port = None

    def start(self):
        if self.listener:
            return self.port
        if not MCP_PYTHON.is_file():
            raise RuntimeError('Houdini MCP environment is missing. Run setup_mcp.ps1.')
        plugin_path = REPOSITORY / 'houdini_plugin/python'
        if not plugin_path.is_dir():
            raise RuntimeError('The installed Houdini MCP source folder is missing.')
        if str(plugin_path) not in sys.path:
            sys.path.insert(0, str(plugin_path))
        from houdini_mcp_plugin.listener import ListenerConfig, RemoteListener
        import hrpyc
        import hou

        class BoundPortServer(hrpyc.ThreadedServer):
            # Houdini 22's bundled RPyC exposes the bound ephemeral port as
            # `port`; the upstream plugin expects `bound_port`.
            @property
            def bound_port(self):
                return self.port

        runtime = SimpleNamespace(ThreadedServer=BoundPortServer, SlaveService=hrpyc.SlaveService)
        listener = RemoteListener(hrpyc=runtime, hou=hou)
        # Port zero lets Windows allocate a port unique to this actual Houdini panel.
        # Explicit config ignores any broad-bind environment settings on the machine.
        result = listener.start(ListenerConfig(host='127.0.0.1', port=0))
        if not result.get('running'):
            listener.stop()
            raise RuntimeError('Houdini MCP could not connect: ' + result.get('message', 'listener failed'))
        self.listener = listener
        self.port = int(result['bound_port'])
        self.log.event('mcp_listener_started',port=self.port)
        return self.port

    def stop(self):
        if self.listener:
            self.log.event('mcp_listener_stopping',port=self.port)
            self.listener.stop()
            self.listener = None
        self.port = None
