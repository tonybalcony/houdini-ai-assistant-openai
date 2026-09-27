"""Small, explicit Houdini tool surface. Call only on Houdini's main thread."""
import json
import hou
from tool_contracts import TOOLS as SDK_TOOLS


def node(path):
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('An absolute Houdini node path is required.')
    value = hou.node(path)
    if value is None:
        raise ValueError('Node does not exist: ' + path)
    return value


def summary(n):
    return {'path': n.path(), 'type': n.type().name(),
            'inputs': [i.path() if i else None for i in n.inputs()]}


def context():
    networks = []
    if hou.isUIAvailable():
        networks = [p.pwd().path() for p in hou.ui.paneTabs() if p.type() == hou.paneTabType.NetworkEditor]
    return {'file': hou.hipFile.path(), 'frame': hou.frame(), 'networks': networks,
            'selection': [summary(n) for n in hou.selectedNodes()],
            'solaris': [summary(n) for n in hou.node('/stage').children()][:100] if hou.node('/stage') else [],
            'objects': [summary(n) for n in hou.node('/obj').children()][:100]}


def inspect(path, parameter_filter=''):
    n = node(path)
    data = summary(n)
    data['children'] = [summary(c) for c in n.children()][:200]
    data['parameters'] = []
    matches = [p for p in n.parms() if parameter_filter.lower() in (p.name() + ' ' + p.description()).lower()]
    budget = 60_000
    for p in matches[:300]:
        try:
            value = p.rawValue()
        except hou.Error:
            value = '<unavailable>'
        text = str(value)[:min(6000, budget)]
        data['parameters'].append({'name': p.name(), 'label': p.description(), 'value': text,
                                   'value_truncated': len(str(value)) > len(text)})
        budget -= len(text)
        if budget <= 0:
            break
    data['parameters_truncated'] = len(matches) > len(data['parameters'])
    data['children_truncated'] = len(n.children()) > 200
    return data


def apply(operations):
    validate_operations(operations)
    results = []
    # Partial failures are reported accurately; the group remains user-undoable.
    with hou.undos.group('Astra: scene edit'):
        for op in operations:
            try:
                action = op['action']
                if action == 'create':
                    from workflow_policy import validate_creation
                    validate_creation(op['type'],op['parent'])
                    n = node(op['parent']).createNode(op['type'], op.get('name'),
                                                      run_init_scripts=False)
                    result = summary(n)
                elif action == 'set_parameters':
                    n = node(op['path'])
                    for entry in op['parameters']:
                        key, value = entry['name'], entry['value']
                        p = n.parmTuple(key) if isinstance(value, list) else n.parm(key)
                        if p is None:
                            raise ValueError('Unknown parameter: ' + key)
                        p.set(value)
                    result = summary(n)
                elif action == 'connect':
                    n = node(op['path'])
                    source = node(op['source']) if op.get('source') else None
                    n.setInput(int(op.get('input', 0)), source, int(op.get('output', 0)))
                    result = summary(n)
                elif action == 'display':
                    n = node(op['path'])
                    n.setDisplayFlag(True)
                    if hasattr(n, 'setRenderFlag'):
                        n.setRenderFlag(True)
                    result = summary(n)
                elif action == 'layout':
                    node(op['path']).layoutChildren()
                    result = {'path': op['path']}
                elif action == 'select':
                    n = node(op['path'])
                    n.setSelected(True, clear_all_selected=True)
                    result = summary(n)
                else:
                    raise ValueError('Unsupported action: ' + action)
                results.append({'ok': True, 'result': result})
            except Exception as exc:
                results.append({'ok': False, 'error': str(exc), 'operation': op,
                                'note': 'Earlier operations may have applied. Inspect before retrying; undo is available.'})
                break
    return results


def call(name, args):
    from PySide6 import QtCore
    app = QtCore.QCoreApplication.instance()
    if app is not None and QtCore.QThread.currentThread() != app.thread():
        raise RuntimeError('Houdini tools must execute on the UI thread.')
    if name == 'houdini_context':
        return context()
    if name == 'houdini_inspect':
        return inspect(args['path'], args.get('parameter_filter', ''))
    if name == 'houdini_node_types':
        category = node(args['parent']).childTypeCategory()
        if category is None:
            return []
        query = args.get('query', '').lower()
        return [{'name': k, 'label': v.description()} for k, v in category.nodeTypes().items()
                if query in k.lower() or query in v.description().lower()][:100]
    if name == 'houdini_edit':
        return apply(args['operations'])
    if name.startswith('houdini_solaris_') or name == 'houdini_materialx_textures':
        import solaris_tools
        return solaris_tools.call(name, args)
    if name in ('houdini_uthana_import', 'houdini_uthana_retarget'):
        import uthana_scene
        return (uthana_scene.import_motion if name == 'houdini_uthana_import' else uthana_scene.retarget)(**args)
    if name in ('houdini_apex_inspect', 'houdini_apex_keyframes'):
        import apex_tools
        if name == 'houdini_apex_inspect':
            return apex_tools.inspect(**args)
        return apex_tools.keyframes(**args)
    if name == 'houdini_geometry':
        n = node(args['path'])
        if not isinstance(n, hou.SopNode):
            raise ValueError('Geometry inspection requires a SOP node.')
        geo = n.geometry()
        result = {'path': n.path(), 'errors': list(n.errors()), 'warnings': list(n.warnings())}
        if geo is not None:
            box = geo.boundingBox()
            result.update({'points': geo.intrinsicValue('pointcount'),
                           'primitives': geo.intrinsicValue('primitivecount'),
                           'bounds_min': list(box.minvec()), 'bounds_max': list(box.maxvec()),
                           'point_attributes': [a.name() for a in geo.pointAttribs()],
                           'primitive_attributes': [a.name() for a in geo.primAttribs()]})
        return result
    raise ValueError('Unknown tool: ' + name)


TOOLS = SDK_TOOLS


def validate_operations(operations):
    import math
    if not isinstance(operations, list) or not 1 <= len(operations) <= 25:
        raise ValueError('Provide 1 to 25 operations.')
    fields = {'create': {'parent', 'type', 'name'}, 'set_parameters': {'path', 'parameters'},
              'connect': {'path', 'source', 'input', 'output'},
              'display': {'path'}, 'layout': {'path'}, 'select': {'path'}}
    for op in operations:
        if not isinstance(op, dict) or op.get('action') not in fields:
            raise ValueError('Unsupported scene operation.')
        if set(op) != fields[op['action']] | {'action'}:
            raise ValueError('Unexpected or missing fields for ' + op['action'])
        for key in ('path', 'parent', 'source'):
            if key in op and not (key == 'source' and op[key] is None):
                if not isinstance(op[key], str) or not op[key].startswith('/'):
                    raise ValueError('Absolute node paths are required.')
        if op['action'] == 'create':
            if not all(isinstance(op[k], str) and op[k] for k in ('name', 'type')):
                raise ValueError('Node name and type must be nonempty strings.')
        if op['action'] == 'connect':
            if any(type(op[k]) is not int or op[k] < 0 for k in ('input', 'output')):
                raise ValueError('Connection indices must be nonnegative integers.')
        if op['action'] == 'set_parameters':
            params = op['parameters']
            if not isinstance(params, list) or not 1 <= len(params) <= 100:
                raise ValueError('Provide 1 to 100 parameter entries.')
            for item in params:
                if not isinstance(item, dict) or set(item) != {'name', 'value'} or not isinstance(item['name'], str):
                    raise ValueError('Invalid parameter entry.')
                values = item['value'] if isinstance(item['value'], list) else [item['value']]
                if not values or len(values) > 64:
                    raise ValueError('Invalid parameter tuple size.')
                for value in values:
                    if not isinstance(value, (str, int, float, bool)):
                        raise ValueError('Unsupported parameter value.')
                    if isinstance(value, float) and not math.isfinite(value):
                        raise ValueError('Parameter values must be finite.')
