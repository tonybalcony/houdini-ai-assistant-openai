"""Project-local configuration for the optional Houdini MCP integration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVISION = '7e5cd7a2484b899a6e9251c6f7b90228c2ec7990'
REPOSITORY = ROOT / 'vendor' / ('houdini-mcp-' + REVISION)
MCP_PYTHON = ROOT / '.mcp-venv/Scripts/python.exe'
PORT_ENV = 'HOUDINI_ASTRA_MCP_PORT'
DISABLED_TOOLS = ['summarize_response', 'get_summarization_status', 'render_viewport',
                  'render_quad_view', 'create_render_node', 'set_render_settings',
                  'create_material', 'assign_material']


def thread_config(port):
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError('Invalid local Houdini MCP port.')
    return {'mcp_servers.houdini': {
        'command': str(MCP_PYTHON),
        'args': ['-u', str(ROOT / 'run_houdini_mcp.py')],
        'cwd': str(ROOT),
        'env': {PORT_ENV: str(port)},
        'enabled': True,
        'startup_timeout_sec': 45,
        'tool_timeout_sec': 120,
        'default_tools_approval_mode': 'approve',
        'disabled_tools': DISABLED_TOOLS,
    }}


MCP_INSTRUCTIONS = '''
The connected MCP server named houdini (oculairmedia/houdini-mcp) supplies additional
tools for the SAME live Houdini session. Use its scene inspection, node operations,
wiring, help and execute_code tools when useful. Our Solaris tools replace the legacy
render/material helpers: always use Solaris + Karma XPU + MaterialX. You may use
Python through houdini.execute_code for Houdini work; hou is already provided there.
Use its normal policy with allow_dangerous=false and allow_heavy_geometry=false.
Do not claim Python execution is unavailable when this MCP connection is ready.
Prefer the existing dedicated APEX keyframe and Uthana generate/download/import/retarget
tools for their workflows. Uthana still receives only motion text and settings.
Only use our supplied dynamic Houdini/Uthana tools and the MCP server named houdini.
Do not use a shell, other apps, other MCP servers, delegation, or external summarizers.
Scene file saves/loads, deletions and simulations are available through MCP only when
the user's request calls for them. Preserve original work and never clear or replace
the current scene merely to simplify a task. Do not read credentials or send scene
data/files to external services. Upstream MCP safety checks must remain enabled.
Use short sequential operations. Inspect results; do not blindly retry a timed-out
mutation. Stop cannot forcibly terminate Houdini code that has already begun running.
MCP edits may use Houdini's normal Undo rather than the panel's Undo last edit button.
Only claim to see a screenshot if an actual image is available, never from metadata
or an unviewed base64 string. Report unavailable tools or rendering errors honestly.
'''


def instructions_with_mcp(base):
    # The original narrow tool boundary remains intact for API/non-MCP sessions.
    base = base.replace(
        'Uthana requests are the explicit exception to the no-file-operations rule: only the supplied tools may\n'
        'download motion files to their private cache and import those generated files into Houdini.',
        'Only the supplied Uthana tools may download generated motion to their cache and import it.')
    base = base.replace(
        'You cannot execute arbitrary Python, shell commands, file operations, buttons, deletion, or simulations.\n'
        'Do not evade these limits via expressions, Python SOPs, callbacks, scripts or side-effecting node types.',
        'Use the connected Houdini MCP tools for capabilities beyond the dedicated tools, within the user request.')
    base = base.replace('Do not add destructive actions.', 'Do not add unrequested destructive actions.')
    return base + '\n' + MCP_INSTRUCTIONS
