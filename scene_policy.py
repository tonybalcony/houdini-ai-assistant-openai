"""Restricted scene edits. Host/third-party HDA execution is not an OS sandbox."""
import re
from access_policy import allowed_file

# Deliberately small native authoring surface; there is no unrestricted override.
NATIVE_TYPES = {
    'Object': {'geo', 'subnet', 'null'},
    'Sop': {'box', 'sphere', 'grid', 'tube', 'circle', 'torus', 'null', 'merge', 'xform',
            'transform', 'copytopoints', 'copy', 'polyextrude', 'polybevel', 'subdivide',
            'normal', 'color', 'mountain', 'noise', 'scatter', 'resample', 'blast',
            'groupcreate', 'group', 'groupexpression', 'sort', 'switch', 'fuse', 'reverse',
            'uvproject', 'uvunwrap', 'uvlayout', 'matchsize', 'bound',
            'attribcreate', 'attribdelete', 'attribrename',
            'attribpromote', 'timeshift', 'timeblend', 'apex::sceneanimate',
            'testgeometry_electra'},
    'Lop': {'null', 'merge', 'sopimport', 'materiallibrary', 'assignmaterial', 'light',
            'domelight', 'camera', 'karmarendersettings', 'karmarenderproperties', 'xform'},
    'Vop': {'subnet', 'subnetconnector', 'subinput', 'suboutput', 'mtlxstandard_surface',
            'mtlxconstant', 'mtlxmultiply', 'mtlxadd', 'mtlxmix', 'mtlxnoise3d', 'mtlxposition',
            'mtlxnormal', 'mtlxdisplacement', 'mtlxsurface', 'mtlxsurfacematerial'},
}

# These factory computations are part of Houdini itself, not model-authored code.
# Accept only the exact value/expression from the installed native type template,
# after its HDA definition has passed validate_factory. Never trust spare templates.
FACTORY_COMPUTED = {
    'light': {'sample_f1', 'sample_f2', 'sample_f3', 'primpattern', 'primpath', 'primtype',
              'treatAsPoint_control', 'treatAsPoint', 'xn__houdiniguidescale_s3a'},
    'domelight': {'sample_f1', 'sample_f2', 'sample_f3', 'primpattern', 'primpath',
                 'xn__houdiniguidescale_s3a'},
    'camera': {'sample_f1', 'sample_f2', 'sample_f3', 'primpattern', 'primpath',
               'xn__houdiniguidescale_s3a', 'focalLengthConverted', 'horizontalAperture_control',
               'horizontalApertureConverted', 'verticalAperture_control', 'verticalApertureSwitch',
               'verticalApertureConverted', 'horizontalApertureOffsetConverted',
               'verticalApertureOffsetConverted'},
    'karmarendersettings': {'sample_f1', 'sample_f2', 'sample_f3', 'primpath',
                           'renderproductsparentprimpath', 'rendervarsparentprimpath', 'dcmvars'},
    'sopimport': {'primpath', 'pathprefix'},
    'testgeometry_electra': {'ragdollcharname'},
    'apex::sceneanimate': {'frame'},
    'kinefx::fbxanimimport': {'time', 'animationstarttime', 'animationendtime', 'playbackstarttime',
                           'frame', 'animationstartframe', 'animationendframe', 'playbackstartframe'},
}
for _kind in ('light', 'camera'):
    FACTORY_COMPUTED[_kind].update('lookatprim' + part + axis for part in ('pos', 'rot') for axis in 'xyz')


def factory_computation(node, parm, value):
    if parm.name() not in FACTORY_COMPUTED.get(simple_type(node.type().name()), set()):
        return False
    template = node.type().parmTemplateGroup().find(parm.tuple().name())
    if template is None:
        return False
    import hou
    keys = parm.keyframes()
    if len(keys) > 1:
        return False  # Never exempt later, potentially different expressions.
    if keys:
        expressions = template.defaultExpression()
        languages = template.defaultExpressionLanguage()
        expressions = expressions if isinstance(expressions, (tuple, list)) else [expressions]
        languages = languages if isinstance(languages, (tuple, list)) else [languages]
        mapping = {hou.scriptLanguage.Hscript: hou.exprLanguage.Hscript,
                   hou.scriptLanguage.Python: hou.exprLanguage.Python}
        expected = [(expression, mapping.get(language)) for expression, language in zip(expressions, languages)]
        try:
            if (keys[0].expression(), keys[0].expressionLanguage()) not in expected:
                return False
        except Exception:
            return False
    defaults = []
    for item in (template.defaultValue(), template.defaultExpression()):
        defaults.extend(item if isinstance(item, (tuple, list)) else [item])
    return value in defaults


def validate_asset_parameter(parm, value):
    # Resolve only harmless Houdini filename tokens, never eval()/expandString().
    # Remaining aliases still fail in allowed_file, including HOME and JOB.
    import hou
    from access_policy import scene_path
    scene = scene_path()
    if '$OS' in value:
        value = value.replace('$OS', parm.node().name())
    if scene:
        value = value.replace('$HIPNAME', scene.stem)
    if re.search(r'\$F(?:[1-9])?(?![A-Za-z0-9_])', value):
        value = re.sub(r'\$F(?:[1-9])?(?![A-Za-z0-9_])', str(int(hou.frame())), value)
    allowed_file(value)


def simple_type(name):
    parts = name.split('::')
    return '::'.join(p for p in parts if not re.fullmatch(r'\d+(?:\.\d+)*', p))


def validate_type(node_type, category):
    if simple_type(node_type) not in NATIVE_TYPES.get(category, set()):
        raise PermissionError('Access denied: this node type is not supported by the checked tools: ' + node_type)


def validate_factory(parent, typename):
    """Never invoke a third-party HDA that replaces an allowed factory node name."""
    import hou
    from pathlib import Path
    value = hou.nodeType(parent.childTypeCategory(), typename)
    if value is None:
        raise PermissionError('Access denied: use an exact installed native node type.')
    definition = value.definition()
    if definition and not Path(definition.libraryFilePath()).resolve().is_relative_to(Path(hou.getenv('HFS')).resolve()):
        raise PermissionError('Access denied: third-party or scene-embedded HDA execution is not supported.')


def preferred_factory(parent, typename):
    """Resolve Houdini's preferred version, then verify before any node is created."""
    import hou
    resolved = hou.preferredNodeType(parent.childTypeCategory().name() + '/' + typename, parent)
    if resolved is None:
        raise PermissionError('Access denied: required native node type is unavailable.')
    validate_factory(parent, resolved.name())
    return resolved.name()


def validate_parameter(parm, value):
    import hou
    template = parm.parmTemplate()
    values = value if isinstance(value, list) else [value]
    name = parm.name().casefold()
    is_file = ((isinstance(template, hou.StringParmTemplate) and
                template.stringType() == hou.stringParmType.FileReference) or
               name in {'productname', 'savepath', 'picture', 'dcmfilename'})
    if any(word in name for word in ('snippet', 'script', 'python', 'command', 'expression', 'code',
                                     'plugin', 'procedural', 'shaderid', 'shaderpath', 'otllibrary')):
        raise PermissionError('Access denied: executable parameters are disabled.')
    if is_file:
        for item in values:
            if item:
                validate_asset_parameter(parm, str(item))
        return
    for item in values:
        if isinstance(item, str) and ('`' in item or '\x00' in item):
            raise PermissionError('Access denied: expressions/code are disabled in restricted parameters.')
        if isinstance(item, str) and ('$' in item or '%' in item or item.startswith('~')):
            # $HIP is the sole filesystem alias. HScript substitutions such as
            # ${HOME} must never be evaluated later by a cook.
            allowed_file(item)
        if isinstance(item, str) and (re.match(r'^[A-Za-z]:', item) or item.startswith(('$HIP', '${HIP}', '\\\\', '//'))):
            allowed_file(item)


def validate_node(node, *, cached_motion=None):
    if cached_motion is None:
        validate_type(node.type().name(), node.type().category().name())
    elif node.type().name() != 'kinefx::fbxanimimport':
        raise PermissionError('Access denied: expected the checked motion importer.')
    validate_factory(node.parent(), node.type().name())
    if node.eventCallbacks():
        raise PermissionError('Access denied: this node has Python event callbacks.')
    if node.type().definition() and not node.matchesCurrentDefinition():
        raise PermissionError('Access denied: modified/unlocked digital assets cannot be checked.')
    for parm in node.parms():
        # rawValue does not evaluate Python/HScript or cook a file.
        value = parm.rawValue()
        if factory_computation(node, parm, value):
            continue
        if parm.keyframes():
            # Numeric animation keys are fine; code-bearing expressions are not.
            for key in parm.keyframes():
                try:
                    expression = key.expression()
                except Exception:
                    expression = ''
                if expression and expression not in ('linear()', 'bezier()', 'cubic()', 'constant()', 'qlinear()'):
                    raise PermissionError('Access denied: scripted parameter expressions are disabled. Parameter: ' + node.path() + '/' + parm.name())
        if cached_motion is not None and parm.name() == 'fbxfile':
            from pathlib import Path
            if value != Path(cached_motion).as_posix() or parm.keyframes():
                raise PermissionError('Access denied: the motion importer file was modified.')
            continue
        if isinstance(value, str):
            if value:
                try:
                    validate_parameter(parm, value)
                except PermissionError as exc:
                    raise PermissionError(str(exc) + ' Parameter: ' + node.path() + '/' + parm.name()) from None


def validate_network(network):
    """Check authoring parents too: creating a child can trigger parent callbacks."""
    if network.path() in ('/obj', '/stage', '/mat'):
        if network.eventCallbacks():
            raise PermissionError('Access denied: the network has Python event callbacks.')
        return
    validate_node(network)
    if network.type().definition():
        raise PermissionError('Access denied: authoring inside a digital asset is disabled.')


def validate_cook(node):
    """Inspect connected native nodes before a requested generic geometry cook."""
    pending, seen = [node], set()
    while pending:
        current = pending.pop()
        if current.path() in seen:
            continue
        seen.add(current.path())
        if len(seen) > 500:
            raise PermissionError('Access denied: network exceeds restricted inspection limits.')
        validate_node(current)
        pending.extend(n for n in current.inputs() if n is not None)
        # Factory-locked HDA internals are trusted Houdini runtime implementation.
        if not (current.type().definition() and current.isLockedHDA()):
            pending.extend(current.children())
        # These SOP/LOP links are node paths, not filesystem paths; still validate
        # their source graph before an indirect geometry cook.
        for name in ('soppath',):
            parm = current.parm(name)
            if parm:
                source = parm.rawValue()
                if source:
                    if not isinstance(source, str) or not source.startswith('/') or any(c in source for c in '`$'):
                        raise PermissionError('Access denied: a literal SOP source node is required.')
                    import hou
                    target = hou.node(source)
                    if target is None:
                        raise ValueError('SOP source does not exist.')
                    pending.append(target)


def validate_apex_input(node):
    """Permit factory rigs only until arbitrary APEX graphs can be audited safely."""
    validate_cook(node)
    pending, seen = [node], set()
    while pending:
        current = pending.pop()
        if current.path() in seen:
            continue
        seen.add(current.path())
        typename = simple_type(current.type().name())
        if typename not in ('apex::sceneanimate', 'testgeometry_electra', 'null'):
            raise PermissionError('Access denied: this custom APEX rig cannot be verified within the folder policy. Use a supported factory rig; unrestricted evaluation is disabled.')
        pending.extend(n for n in current.inputs() if n is not None)
