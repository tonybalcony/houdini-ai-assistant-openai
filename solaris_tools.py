"""Native procedural Solaris authoring and background Karma XPU rendering."""
import json
from pathlib import Path
import re
import hou
from pxr import Sdf, Usd, UsdShade, UsdLux, UsdRender, UsdGeom
from solaris_contracts import validate_arguments


def node(path):
    n = hou.node(path) if path.startswith('/') else None
    if n is None:
        raise ValueError('Node not found: ' + path)
    return n


def lop(path):
    n = node(path)
    if n.type().category() != hou.lopNodeTypeCategory():
        raise ValueError('A Solaris LOP node is required.')
    return n


def prim_path(value):
    path = Sdf.Path(value)
    if not path.IsAbsolutePath() or not path.IsPrimPath() or value == '/':
        raise ValueError('An absolute USD primitive path is required.')
    return value


def inspect(path, root_prim):
    n = lop(path)
    from scene_policy import validate_cook
    validate_cook(n)
    stage = n.stage()
    if stage is None or n.errors():
        raise ValueError('Solaris cook failed: ' + '; '.join(n.errors()))
    root = stage.GetPseudoRoot() if root_prim == '/' else stage.GetPrimAtPath(prim_path(root_prim))
    if not root:
        raise ValueError('USD primitive not found: ' + root_prim)
    prims = []
    for p in Usd.PrimRange(root):
        if len(prims) >= 150:
            return {'status':'success','path':path,'prims':prims,'truncated':True}
        entry = {'path':str(p.GetPath()),'type':p.GetTypeName()}
        binding = p.GetRelationship('material:binding')
        if binding:
            entry['material_binding'] = [str(t) for t in binding.GetTargets()]
        if p.IsA(UsdShade.Shader):
            entry['shader_id'] = str(p.GetAttribute('info:id').Get())
        if p.IsA(UsdRender.Settings):
            entry['camera'] = [str(t) for t in p.GetRelationship('camera').GetTargets()]
            entry['resolution'] = list(p.GetAttribute('resolution').Get() or [])
        if p.HasAPI(UsdLux.LightAPI):
            entry['intensity'] = p.GetAttribute('inputs:intensity').Get()
        prims.append(entry)
    return {'status':'success','path':path,'prims':prims,'truncated':False,'warnings':list(n.warnings())}


def create(parent, input_path, name, config):
    network = node(parent)
    if network.childTypeCategory() != hou.lopNodeTypeCategory():
        raise ValueError('Create Solaris nodes in a LOP network, normally /stage.')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
        raise ValueError('Use a node name containing letters, digits and underscores.')
    source = lop(input_path) if input_path else None
    from scene_policy import validate_cook, validate_factory, validate_network, preferred_factory
    validate_network(network)
    if source:
        validate_cook(source)
    if source and source.parent() != network:
        raise ValueError('Input must belong to the same Solaris network.')
    kind = config['kind']
    if kind == 'import_sop':
        validate_cook(node(config['source_path']))
        if not isinstance(node(config['source_path']), hou.SopNode):
            raise ValueError('Import requires a SOP output node.')
        prim_path(config['prim_path'])
    if kind == 'karma':
        prim_path(config['camera_prim'])
    if kind == 'material' and (not config['prim_pattern'].startswith('/') or '`' in config['prim_pattern']):
        raise ValueError('Supply a USD geometry primitive path/pattern.')
    types = {'import_sop':'sopimport','material':'materiallibrary','camera':'camera',
             'karma':'karmarendersettings','light':'domelight' if config.get('light_type')=='dome' else 'light'}
    created = None
    factory = preferred_factory(network, types[kind])
    with hou.undos.group('Astra: scene edit'):
        try:
            created = network.createNode(factory, name, run_init_scripts=False, exact_type_name=True)
            n = created
            if source:
                n.setInput(0, source)
            result = {'status':'success','path':n.path(),'kind':kind}
            if kind == 'import_sop':
                n.setParms({'soppath':config['source_path'],'primpath':config['prim_path'],
                            'pathprefix':config['prim_path'],'enable_pathprefix':1,
                            'enable_prefixabsolutepaths':1,'prefixabsolutepaths':1})
                result['prim_path'] = config['prim_path']
            elif kind == 'material':
                # Check factory definitions before SideFX's builder helper resolves
                # its standard node names. Custom replacements are not supported.
                for typename in ('subnet', 'subinput', 'mtlxstandard_surface', 'mtlxdisplacement', 'subnetconnector'):
                    preferred_factory(n, typename)
                import voptoolutils
                builder = voptoolutils._setupMtlXBuilderSubnet(destination_node=n, name=name,
                    mask=voptoolutils.MTLX_TAB_MASK, render_context='mtlx')
                # Freeze the helper's spare Python/HScript inheritance defaults to
                # explicit values. They are not trusted native type parameters.
                builder.parm('shader_referencetype').deleteAllKeyframes()
                builder.parm('shader_referencetype').set('inherit')
                builder.parm('shader_baseprimpath').set('/__class_mtl__/' + builder.name())
                shader = builder.node('mtlxstandard_surface')
                shader.parmTuple('base_color').set(config['base_color'])
                shader.setParms({'specular_roughness':config['roughness'],'metalness':config['metalness']})
                material = '/materials/' + builder.name()
                n.setParms({'matpathprefix':'','matnode1':builder.name(),'matpath1':material,
                            'assign1':1,'geopath1':config['prim_pattern']})
                result.update(material_path=material, builder_path=builder.path(), shader_path=shader.path())
            elif kind in ('light','camera'):
                n.parmTuple('t').set(config['position'])
                n.parmTuple('r').set(config['rotation'])
                path = ('/lights/' if kind == 'light' else '/cameras/') + n.name()
                n.parm('primpath').set(path)
                result['prim_path'] = path
                if kind == 'camera':
                    n.parm('focalLength').set(config['focal_length'])
                else:
                    if config['light_type'] != 'dome':
                        n.parm('lighttype').set({'rect':'UsdLuxRectLight','disk':'UsdLuxDiskLight',
                            'sphere':'UsdLuxSphereLight','distant':'UsdLuxDistantLight'}[config['light_type']])
                    n.parm('xn__inputsintensity_i0a').set(config['intensity'])
                    n.parm('xn__inputsexposure_vya').set(config['exposure'])
                    n.parmTuple('xn__inputscolor_zta').set(config['color'])
            elif kind == 'karma':
                n.parm('res_mode').set('manual')
                n.parm('res_mode').pressButton()  # Run Houdini's resolution-mode callback.
                n.setParms({'engine':'xpu','camera':config['camera_prim'],
                            'resolutionx':config['resolution'][0],'resolutiony':config['resolution'][1],
                            'pathtracedsamples':config['samples'],'primpath':'/Render/' + n.name()})
                if n.parm('engine').evalAsString() != 'xpu':
                    raise ValueError('Karma XPU selection could not be verified.')
                result.update(engine='xpu',render_settings='/Render/' + n.name())
            validate_cook(n)
            n.moveToGoodPosition()
            n.setDisplayFlag(True)
            return result
        except Exception as exc:
            return {'status':'error','error':str(exc),'partial_path':created.path() if created else None,
                    'note':'Inspect the retained branch before retrying; Undo is available.'}


def render_start(path, frame, output_file, quality):
    import render_jobs
    from access_policy import project_data, allowed_file
    project_data('renders')  # Fail before any cook/export for an unsaved scene.
    if output_file:
        allowed_file(output_file, write=True)
    n = lop(path)
    from scene_policy import validate_cook
    validate_cook(n)
    if n.type().name().split('::')[0] not in ('karmarendersettings','karmarenderproperties','karma') or not n.parm('engine') or n.parm('engine').evalAsString() != 'xpu':
        raise ValueError('Render requires a Solaris Karma settings node with engine=xpu. No fallback is permitted.')
    husk = Path(hou.expandString('$HFS')) / 'bin/husk.exe'
    if not husk.is_file():
        raise ValueError('Houdini husk renderer was not found.')
    previous = hou.frame()
    try:
        hou.setFrame(frame)
        stage = n.stage()
        if stage is None or n.errors():
            raise ValueError('Solaris cook failed: ' + '; '.join(n.errors()))
        settings = n.parm('primpath').evalAsString()
        camera = stage.GetPrimAtPath(n.parm('camera').evalAsString())
        if not camera or camera.GetTypeName() != 'Camera':
            raise ValueError('Karma render camera does not exist in the USD stage.')
        directory, manifest = render_jobs.prepare(output_file, frame, path, quality)
        snapshot = directory / 'scene.usdc'
        snapshot_stage = Usd.Stage.Open(stage.Flatten())
        # No external USD/image/geometry dependencies may reach husk. A flattened
        # snapshot still retains asset-valued attributes unless checked explicitly.
        for prim in snapshot_stage.Traverse():
            for attribute in prim.GetAttributes():
                if attribute.GetTypeName() in (Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray):
                    values = attribute.Get()
                    values = values if attribute.GetTypeName() == Sdf.ValueTypeNames.AssetArray else [values]
                    for value in values or []:
                        if value and value.path:
                            allowed_file(value.resolvedPath or value.path)
        if quality == 'working':
            optimize_working_stage(snapshot_stage, settings)
        snapshot_stage.GetRootLayer().Export(str(snapshot))
        return render_jobs.launch(directory,manifest,husk,snapshot,settings)
    finally:
        hou.setFrame(previous)


def call(name, args):
    validate_arguments(name,args)
    if name == 'houdini_solaris_create':
        return create(**args)
    if name == 'houdini_solaris_inspect':
        return inspect(**args)
    if name == 'houdini_solaris_render_start':
        return render_start(**args)
    import render_jobs
    if name == 'houdini_solaris_render_status':
        return render_jobs.status(**args)
    if name == 'houdini_solaris_render_cancel':
        return render_jobs.cancel(**args)
    if name == 'houdini_solaris_render_preview':
        return render_jobs.preview(**args)
    raise ValueError('Unknown Solaris tool.')


def dispatch_json(payload):
    """RPC entry point; marshal scene work onto the interactive Houdini main thread."""
    message = json.loads(payload)
    def invoke():
        try:
            return json.dumps(call(message['name'],message['arguments']),allow_nan=False)
        except Exception as exc:
            return json.dumps({'status':'error','error':str(exc)})
    if hou.isUIAvailable():
        import hdefereval
        return hdefereval.executeInMainThreadWithResult(invoke)
    return invoke()


def optimize_working_stage(stage, settings_path):
    """Override only the exported snapshot, leaving the artist's scene intact."""
    settings = stage.GetPrimAtPath(settings_path)
    resolution = settings.GetAttribute('resolution')
    size = resolution.Get()
    scale = min(1,960/max(size))
    from pxr import Gf
    resolution.Set(Gf.Vec2i(max(16,int(size[0]*scale)), max(16,int(size[1]*scale))))
    for name, value in {'karma:global:pathtracedsamples':32}.items():
        attr = settings.GetAttribute(name)
        if attr and attr.Get() is not None:
            value = min(value,attr.Get())
        settings.CreateAttribute(name,Sdf.ValueTypeNames.Int).Set(value)
    def cap_rays(p):
        for name,value in {'karma:object:diffuselimit':1.,'karma:object:reflectlimit':2.,
                           'karma:object:refractlimit':2.,'karma:object:volumelimit':0.,
                           'karma:object:ssslimit':0.}.items():
            attr=p.GetAttribute(name)
            if attr and attr.Get() is not None:
                value=min(value,float(attr.Get()))
            attr=attr or p.CreateAttribute(name,Sdf.ValueTypeNames.Float)
            attr.Clear()
            attr.Set(value)
    cap_rays(settings)
    for p in stage.Traverse():
        if p.IsA(UsdGeom.Gprim):
            cap_rays(p)
        if p.IsA(UsdShade.Material):
            for attr in p.GetAttributes():
                if attr.GetName().startswith('outputs:') and attr.GetName().endswith(':displacement'):
                    attr.SetConnections([])
        if p.GetTypeName()=='Camera':
            p.GetAttribute('fStop').Clear()
            p.CreateAttribute('fStop',Sdf.ValueTypeNames.Float).Set(0)
