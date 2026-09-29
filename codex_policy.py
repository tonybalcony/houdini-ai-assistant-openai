"""Plugin-owned Codex profile: no ambient apps, shell, file tools or MCP."""
import json
from access_policy import plugin_path, child_environment

CONFIG = {
    'model_provider': 'openai',
    'cli_auth_credentials_store': 'file',
    'features.shell_tool': False,
    'features.unified_exec': False,
    'features.shell_snapshot': False,
    'check_for_update_on_startup': False,
    'features.apply_patch_freeform': False,
    'features.multi_agent': False,
    'agents.enabled': False,
    'features.apps': False,
    'features.browser_use': False,
    'features.browser_use_external': False,
    'features.computer_use': False,
    'features.workspace_dependencies': False,
    'features.daemon_auto_start': False,
    'features.tool_suggest': False,
    'features.skill_search': False,
    'features.skip_host_skill_discovery': True,
    'features.view_image': False,
    'features.hooks': False,
    'features.memories': False,
    'features.remote_plugin': False,
    'features.skill_mcp_dependency_install': False,
    'features.code_mode.enabled': False,
    'web_search': 'disabled',
    'history.persistence': 'none',
    'project_doc_max_bytes': 0,
    'mcp_servers': {},
    'plugins': {},
    'analytics.enabled': False,
}


def arguments(executable):
    args = [str(executable)]
    for key, value in CONFIG.items():
        args += ['-c', key + '=' + ('{}' if value == {} else json.dumps(value))]
    return args + ['app-server', '--listen', 'stdio://']


def environment(source=None):
    env = child_environment(source)
    for key in list(env):
        if key.upper().endswith(('_API_KEY', '_TOKEN')):
            env.pop(key)
    directory = plugin_path('.state/codex')
    directory.mkdir(parents=True, exist_ok=True)
    plugin_path('.state/workspace').mkdir(parents=True, exist_ok=True)
    return env
