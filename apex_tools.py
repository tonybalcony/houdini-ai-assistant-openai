"""Bounded APEX animation authoring on the Houdini main thread.

Uses the Scene/ChannelPrimBindings API shipped with Houdini 22. All edits are
prepared in a private scene; the only live mutation is one animation-parm write.
"""
import math
import re

import hou


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _value(value):
    if type(value) is bool or _number(value):
        return value
    if isinstance(value, (hou.Vector2, hou.Vector3, hou.Vector4)):
        return list(value)
    return None


def _load(path):
    import apex
    from scene_tools import node
    n = node(path)
    if not isinstance(n, hou.SopNode) or n.type().name().split('::')[:2] != ['apex', 'sceneanimate']:
        raise ValueError('Choose an APEX Scene Animate SOP (apex::sceneanimate).')
    if not n.inputs() or n.inputs()[0] is None:
        raise ValueError('Connect a rigged APEX scene to Scene Animate input 0 first.')
    from scene_policy import validate_apex_input
    validate_apex_input(n)
    geo = n.geometry()
    if n.errors():
        raise ValueError('Scene Animate cannot cook: ' + '; '.join(n.errors()))
    scene = apex.Scene()
    scene.loadFromGeometry(geo)
    scene.initializeAnimStack()
    return n, scene


def _rig(scene, rig_path):
    import apex
    rigs = sorted(p for p in scene.dataPaths() if p.endswith('.rig')
                  and isinstance(scene.getData(p), apex.SceneGraph))
    if not rig_path and len(rigs) == 1:
        rig_path = rigs[0]
    if rig_path not in rigs:
        raise ValueError('Select an exact rig_path from houdini_apex_inspect. Available: ' + ', '.join(rigs[:50]))
    return scene.getData(rig_path), rig_path


def inspect(path, rig_path='', parameter_filter='', frame=1, offset=0):
    if not _number(frame) or type(offset) is not int or offset < 0:
        raise ValueError('Use a finite frame and a nonnegative integer offset.')
    if not isinstance(parameter_filter, str):
        raise ValueError('parameter_filter must be text.')
    n, scene = _load(path)
    rigs = sorted(p for p in scene.dataPaths() if p.endswith('.rig'))
    layers = scene.layers()
    result = {'path': n.path(), 'rigs': rigs[:100], 'rigs_truncated': len(rigs) > 100,
              'skeletons': sorted(p for p in scene.dataPaths() if p.endswith('.skel'))[:100],
              'active_clip': scene.getActiveClipPath(), 'frame': frame, 'fps': hou.fps(),
              'layers': [{'name': k, 'locked': v.isLocked(), 'inherited': v.isInherited(),
                          'muted': v.isMuted(), 'additive': v.isAdditive(), 'weight': v.weight(scene, frame)}
                         for k, v in list(layers.items())[:100]],
              'warnings': list(n.warnings())}
    if not rig_path and len(rigs) != 1:
        result['note'] = 'Supply one rig_path to inspect controls.' if rigs else 'No APEX rigs found in the input scene.'
        return result
    rig, rig_path = _rig(scene, rig_path)
    scene.updateEvaluationParms(frame)
    scene.evaluateTrackedRigData()
    values = {k: _value(v) for k, v in rig.graph_parms.items() if _value(v) is not None
              and parameter_filter.lower() in k.lower()}
    names = sorted(values)[offset:offset + 100]
    result.update({'rig_path': rig_path, 'parameters': [
        {'name': k, 'value': values[k], 'components': len(values[k]) if isinstance(values[k], list) else 1}
        for k in names], 'total_parameters': len(values),
        'next_offset': offset + 100 if len(values) > offset + 100 else None,
        'channels': []})
    binding = scene.getData(rig_path + '/animbinding')
    if binding:
        mapping = binding.getChannelNamesForParms(scene, names)
        wanted = {c for channels in mapping.values() for c in channels}
        budget = 1500
        for layer in layers:
            if not binding.hasLayer(layer):
                continue
            geo = scene.getData(binding.layerGeoPath(layer))
            if geo is None:
                continue
            for channel in geo.prims():
                if not isinstance(channel, hou.ChannelPrim) or channel.attribValue('name') not in wanted:
                    continue
                frames = channel.keyFrames()
                kept = frames[:min(60, budget)]
                result['channels'].append({'layer': layer, 'name': channel.attribValue('name'),
                    'value': channel.eval(frame), 'key_count': len(frames),
                    'keys': [{'frame': f, 'value': channel.eval(f)} for f in kept],
                    'keys_truncated': len(kept) < len(frames)})
                budget -= len(kept)
                if budget <= 0 or len(result['channels']) >= 200:
                    result['channels_truncated'] = True
                    return result
    return result


def _validate(tracks, values, layer, interpolation):
    if not isinstance(layer, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_ -]{0,63}', layer):
        raise ValueError('Use a short layer name starting with a letter, with letters, numbers, spaces, _ or -.')
    if interpolation not in ('linear', 'constant', 'smooth'):
        raise ValueError('Interpolation must be linear, constant or smooth.')
    if not isinstance(tracks, list) or not 1 <= len(tracks) <= 64:
        raise ValueError('Provide 1 to 64 tracks.')
    seen, component_keys = set(), 0
    for track in tracks:
        if not isinstance(track, dict) or set(track) != {'parameter', 'keys'}:
            raise ValueError('Each track needs parameter and keys.')
        name = track['parameter']
        if not isinstance(name, str) or not re.fullmatch(r'[\w:./-]+', name) or name in seen:
            raise ValueError('Use unique exact parameter names without patterns.')
        seen.add(name)
        original = values.get(name)
        if original is None:
            raise ValueError('Unknown or unsupported numeric rig parameter: ' + name)
        keys = track['keys']
        if not isinstance(keys, list) or not 1 <= len(keys) <= 120:
            raise ValueError('Provide 1 to 120 keys per track.')
        frames = set()
        for key in keys:
            if not isinstance(key, dict) or set(key) != {'frame', 'value'} or not _number(key['frame']):
                raise ValueError('Each key needs a finite frame and a value.')
            if key['frame'] in frames:
                raise ValueError('Duplicate key frame in ' + name)
            frames.add(key['frame'])
            value = key['value']
            if isinstance(original, list):
                valid = isinstance(value, list) and len(value) == len(original) and all(_number(v) for v in value)
                count = len(original)
            elif type(original) is bool:
                valid = type(value) is bool or (type(value) is int and value in (0, 1))
                count = 1
            else:
                valid = _number(value) and (type(original) is not int or type(value) is int)
                count = 1
            if not valid:
                raise ValueError('Value type/component count does not match ' + name)
            component_keys += count
            if component_keys > 2000:
                raise ValueError('Limit each call to 2000 component keys.')
    return component_keys


def keyframes(path, rig_path, layer, interpolation, tracks):
    # APEX normalizes these characters when adding a layer. Normalize before
    # looking it up as well, so repeated writes do not silently create Layer2.
    if isinstance(layer, str):
        layer = layer.replace(' ', '_').replace('-', '_')
    n, scene = _load(path)
    rig, rig_path = _rig(scene, rig_path)
    originals = {k: v for k, v in rig.graph_parms.items() if _value(v) is not None}
    component_keys = _validate(tracks, {k: _value(v) for k, v in originals.items()}, layer, interpolation)
    if n.parm('animation').isLocked():
        raise ValueError('The Scene Animate animation parameter is locked.')
    if layer in scene.layers():
        existing = scene.layer(layer)
        if (not scene.isLayerEditable(layer) or existing.isLocked() or existing.isInherited()
                or existing.isMuted() or existing.isAdditive()):
            raise ValueError('Choose a new override layer; the requested layer is locked, inherited, muted or additive.')
        # The native API raises on a no-op activation in Houdini 22.
        if scene.activeLayer().name != layer:
            scene.setActiveLayer(layer)
    else:
        layer = scene.addLayer(layer, additive=False, activate=True)
    binding = scene.getData(rig_path + '/animbinding')
    if binding is None:
        _, binding_path = scene.createAnimBinding(rig_path)
        binding = scene.getData(binding_path)
    data_path = binding.constructLayer(scene, layer) if not binding.hasLayer(layer) else binding.layerGeoPath(layer)
    geo = hou.Geometry(scene.getData(data_path))
    scene.setData(data_path, geo)
    graph = scene.getData(rig_path + '/graph')
    for track in tracks:
        name = track['parameter']
        if not binding.hasParm(name, layer):
            _, graph_input = graph.signature().findInput(name)
            binding.createNewChannels(scene, geo, graph_input.type_name, name, layer)
            binding.setDefaultFromDict(scene, pattern=name, layer=layer)
        for key in sorted(track['keys'], key=lambda k: k['frame']):
            value = key['value']
            if isinstance(value, list):
                value = type(originals[name])(value)
            elif type(originals[name]) is bool:
                value = bool(value)
            rig.graph_parms[name] = value
            binding.setKeysFromDict(scene, key['frame'], True, pattern=name, force_key=True)

    # Limit tangent/interpolation changes to the keys explicitly requested.
    geo = scene.getData(data_path)
    channels = {p.attribValue('name'): p for p in geo.prims() if isinstance(p, hou.ChannelPrim)}
    mapping = binding.getChannelNamesForParms(scene, [t['parameter'] for t in tracks])
    segment = {'linear': hou.segmentType.Linear, 'constant': hou.segmentType.Constant,
               'smooth': hou.segmentType.Bezier}[interpolation]
    written = []
    for track in tracks:
        channel_names = mapping.get(track['parameter'], [])
        expected = len(_value(originals[track['parameter']])) if isinstance(_value(originals[track['parameter']]), list) else 1
        if len(channel_names) != expected:
            raise RuntimeError('APEX could not bind every component; no animation was committed.')
        for index, name in enumerate(channel_names):
            channel = channels[name]
            for key in track['keys']:
                frame = key['frame']
                value = key['value'][index] if isinstance(key['value'], list) else key['value']
                if not channel.hasKeyAtFrame(frame) or not math.isclose(channel.eval(frame), value, rel_tol=1e-5, abs_tol=1e-5):
                    raise RuntimeError('APEX key verification failed; no animation was committed.')
                channel.setSegmentType(frame, segment)
                if interpolation == 'smooth':
                    channel.setKeyAutoSlope(frame, True)
                    channel.smoothAutoSlopesForKeys(channel.keyIndex(frame))
            written.append(name)
    geo.incrementAllDataIds()
    # Match Scene Animate's partial-stash workflow: retain its non-animation data
    # and write animation differences relative to its upstream geometry.
    out = hou.Geometry(n.parm('animation').eval())
    scene.saveToGeometry(out, '/animation/**', n.inputGeometry(0))
    with hou.undos.group('Astra: scene edit'):
        n.parm('animation').set(out)
    return {'ok': True, 'path': n.path(), 'rig_path': rig_path, 'layer': layer,
            'active_clip': scene.getActiveClipPath(), 'channels': written,
            'component_keys_written': component_keys,
            'note': 'Native APEX keys stored on Scene Animate. Existing unsupplied keys remain. Undo last edit reverses this batch.'}
