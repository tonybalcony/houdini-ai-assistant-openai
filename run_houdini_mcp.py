"""Run the pinned upstream MCP server with stdio and a panel-owned local target."""
import os

from mcp_config import PORT_ENV


def main():
    port = int(os.environ[PORT_ENV])
    if not 1 <= port <= 65535:
        raise ValueError('Invalid local Houdini port.')
    for name in list(os.environ):
        if name.upper() in {'OPENAI_API_KEY', 'CODEX_API_KEY', 'UTHANA_API_KEY',
                            'ANTHROPIC_API_KEY', 'OPENAI_BASE_URL', 'CLAUDE_PROXY_URL'}:
            os.environ.pop(name)
    os.environ.update({
        'HOUDINI_HOST': '127.0.0.1', 'HOUDINI_PORT': str(port),
        'MCP_TRANSPORT': 'stdio', 'SUMMARIZATION_ENABLED': 'false',
        'HOUDINI_MCP_ALLOW_BYPASS': 'false', 'LOG_LEVEL': 'WARNING',
    })
    from houdini_mcp.server import run_server, mcp
    from mcp_extensions import install
    install(mcp,port)
    run_server(transport='stdio')


if __name__ == '__main__':
    main()
