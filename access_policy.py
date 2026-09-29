"""Filesystem policy for assistant-owned data and model-supplied file paths.

This is application enforcement, not a sandbox around the Houdini host/Windows.
Never use a model argument to set roots. The panel supplies the saved scene.
"""
import hashlib
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SCENE_ENV = 'HOUDINI_ASTRA_SCENE'
PRIVATE_NAMES = {'.state', '.secrets', '.git', '.codex', '.agents', '.chat_history',
                 '.astra', 'auth.json', 'api-key.dpapi'}


def scene_path():
    try:
        import hou
        if hou.hipFile.isNewFile():
            return None
        value = hou.hipFile.path()
    except ImportError:
        value = os.environ.get(SCENE_ENV, '')
    if not value:
        return None
    path = Path(value).resolve()
    if path.suffix.lower() not in ('.hip', '.hipnc', '.hiplc') or not path.is_file():
        return None
    return path


def scene_directory(scene):
    """One sidecar per filename, portable when the whole project moves."""
    path = Path(scene).resolve()
    name = path.name.casefold()
    identifier = hashlib.sha256(name.encode('utf-8')).hexdigest()[:20]
    return contained(path.parent / '.astra' / identifier, path.parent)


def contained(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise PermissionError('Access denied: path is outside the allowed folder.')
    return path


def plugin_path(relative):
    return contained(ROOT / relative, ROOT)


def project_data(kind):
    scene = scene_path()
    if scene is None:
        raise PermissionError('Access denied: save the Houdini scene before writing project files.')
    return contained(scene_directory(scene) / kind, scene.parent)


def allowed_file(value, *, write=False, scene=None):
    """Resolve only literal paths/$HIP. Reject aliases, expansion and link escapes."""
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise PermissionError('Access denied: a literal project file path is required.')
    value = value.replace('\\', '/')
    scene = Path(scene).resolve() if scene else scene_path()
    hip = scene.parent if scene else None
    if value == '$HIP' or value.startswith('$HIP/'):
        if hip is None:
            raise PermissionError('Access denied: $HIP is unavailable until the scene is saved.')
        value = str(hip) + value[4:]
    elif value == '${HIP}' or value.startswith('${HIP}/'):
        if hip is None:
            raise PermissionError('Access denied: $HIP is unavailable until the scene is saved.')
        value = str(hip) + value[6:]
    if any(char in value for char in ('$', '%', '`', '~')) or '://' in value or value.startswith('//'):
        raise PermissionError('Access denied: environment aliases, expressions and network paths are disabled.')
    # Reject Windows drive-relative paths, alternate streams and device names.
    if re.match(r'^[A-Za-z]:[^/\\]', value) or ':' in re.sub(r'^[A-Za-z]:', '', value):
        raise PermissionError('Access denied: invalid file path.')
    path = Path(value)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} | {f'{prefix}{i}' for prefix in ('COM', 'LPT') for i in range(1, 10)}
    if any(part.split('.')[0].upper() in reserved or part.endswith((' ', '.')) for part in path.parts if part not in ('.', '..')):
        raise PermissionError('Access denied: Windows device and ambiguous file names are disabled.')
    if not path.is_absolute():
        if hip is None:
            raise PermissionError('Access denied: relative files require a saved $HIP.')
        path = hip / path
    path = path.resolve()
    roots = [ROOT.resolve()] + ([hip] if hip else [])
    if not any(path.is_relative_to(root) for root in roots):
        raise PermissionError('Access denied: only the plugin folder and current saved $HIP are accessible.')
    if any(part.casefold() in PRIVATE_NAMES or part.casefold().startswith('.env') for part in path.parts):
        raise PermissionError('Access denied: private account and chat storage is not a scene asset.')
    if write and path.is_relative_to(ROOT.resolve()):
        raise PermissionError('Access denied: assistant output belongs in $HIP, not plugin program files.')
    return path


def child_environment(source=None):
    """Use package-local data/temp roots; never inherit another Codex profile."""
    env = dict(os.environ if source is None else source)
    for key in list(env):
        if key.upper() in {'PYTHONHOME', 'PYTHONPATH', 'OPENAI_API_KEY', 'CODEX_API_KEY',
                'OPENAI_BASE_URL', 'CODEX_HOME', 'HOUDINI_ASTRA_CODEX',
                'HOUDINI_ASTRA_PYTHON', 'HOUDINI_ASTRA_USER_DIR', 'HOUDINI_ASTRA_CHAT_DIR',
                'HOUDINI_ASTRA_LOG_DIR', 'HOUDINI_ASTRA_MCP_PORT', 'OCIO',
                'HOUDINI_PATH', 'HOUDINI_PACKAGE_DIR', 'HOUDINI_OTLSCAN_PATH',
                'HOUDINI_DSO_PATH', 'HOUDINI_PYTHON_PANEL_PATH', 'HOUDINI_SCRIPT_PATH',
                'HOUDINI_USER_PREF_DIR', 'HOUDINI_TEMP_DIR'}:
            env.pop(key)
    state = plugin_path('.state')
    temporary = plugin_path('.state/tmp')
    temporary.mkdir(parents=True, exist_ok=True)
    env.update(CODEX_HOME=str(state / 'codex'), TEMP=str(temporary), TMP=str(temporary),
               TMPDIR=str(temporary), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
               HOUDINI_USER_PREF_DIR=str(plugin_path('.state/houdini__HVER__')),
               HOUDINI_TEMP_DIR=str(temporary))
    scene = scene_path()
    env[SCENE_ENV] = str(scene) if scene else ''
    return env


def validate_prompt_paths(text):
    """Immediate feedback for explicit external paths; tool checks remain authoritative."""
    candidates = re.findall(r'(?i)(?:[A-Z]:[\\/]|\\\\)[^\r\n"<>|?*]+', text)
    candidates += re.findall(r'\$\{?HIP\}?(?:[/\\][^\r\n"<>|?*]+)?', text)
    for quoted in re.findall(r'["\']([^"\']+)["\']', text):
        if quoted.startswith(('/', '~', '%', '../', '..\\')) and not quoted.startswith(('/obj', '/stage', '/mat', '/out', '/World')):
            candidates.append(quoted)
    for candidate in candidates:
        allowed_file(candidate.strip().rstrip('.,;'))
