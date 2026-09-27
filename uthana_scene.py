"""Import cached Uthana motion and retarget it with local Houdini SOPs."""
import re
import hou
from scene_tools import node
from uthana_client import read_asset, cache_dir


def _identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_ -]{0,63}', name):
        raise ValueError('Use a short name starting with a letter, with letters, numbers, spaces, _ or -.')
    return name.replace(' ', '_').replace('-', '_')


def _cached_file(asset_id):
    asset = read_asset(asset_id)
    download = asset.get('download') or {}
    filename = download.get('filename', '')
    if not re.fullmatch(r'motion_(24|30|60)_[01]\.fbx', filename):
        raise ValueError('Download this motion with uthana_download first.')
    path = cache_dir(asset_id) / filename
    if not path.is_file():
        raise ValueError('The cached FBX is missing. Download the existing motion again.')
    return asset, path


def _geometry(n):
    geo = n.geometry()
    if n.errors():
        raise ValueError(n.name() + ': ' + '; '.join(n.errors()))
    if geo is None or not geo.findPointAttrib('name') or not geo.points():
        raise ValueError(n.name() + ': no named skeleton joints were produced.')
    return geo


def _range(geo, source=None):
    info = geo.attribValue('clipinfo') if geo.findGlobalAttrib('clipinfo') else {}
    times = info.get('range')
    if not times or len(times) != 2:
        raise ValueError('Imported motion has no clip time range.')
    frames = tuple(int(round(hou.timeToFrame(t))) for t in times)
    # FBX Import retains the source clipinfo range when playback is offset.
    if source is not None and source.parm('useplaybackstarttime').eval():
        start = int(round(hou.timeToFrame(source.parm('playbackstarttime').eval())))
        frames = (start, start + frames[1] - frames[0])
    if frames[1] < frames[0] or frames[1] - frames[0] > 600:
        raise ValueError('Local APEX baking is limited to 601 frames. Reduce the clip length or scene frame rate.')
    return frames


def import_motion(asset_id, parent, name, start_frame):
    if type(start_frame) is not int or not -100_000 <= start_frame <= 100_000:
        raise ValueError('Use an integer start_frame between -100000 and 100000.')
    name = _identifier(name)
    _, filename = _cached_file(asset_id)
    network = node(parent)
    if network.childTypeCategory() != hou.sopNodeTypeCategory():
        raise ValueError('Import inside a SOP network, for example the target character geometry object.')
    with hou.undos.group('Astra: scene edit'):
        imported = network.createNode('kinefx::fbxanimimport', name, run_init_scripts=False)
        imported.parm('fbxfile').set(filename.as_posix())
        imported.parm('convertunits').set(True)
        imported.parm('convertaxis').set(True)
        imported.parm('axissystem').set('yupright')
        imported.parm('timeshiftmethod').set('bytime')
        imported.parm('useplaybackstarttime').set(True)
        imported.parm('playbackstarttime').deleteAllKeyframes()
        imported.parm('playbackstarttime').set(hou.frameToTime(start_frame))
        imported.setUserData('astra_uthana_asset', asset_id)
        imported.moveToGoodPosition()
        try:
            geo = _geometry(imported)
            frames = _range(geo, imported)
        except Exception as exc:
            return {'ok': False, 'source_path': imported.path(), 'error': str(exc),
                    'note': 'Import node retained for inspection. Undo last edit removes this batch.'}
    return {'ok': True, 'asset_id': asset_id, 'source_path': imported.path(),
            'joints': list(geo.pointStringAttribValues('name'))[:200], 'frame_range': list(frames),
            'fps': hou.fps(), 'warnings': list(imported.warnings()),
            'note': 'Animated source skeleton imported locally. Retarget it to the APEX character next.'}


def retarget(source_path, target_path, rig_path, skeleton_path, clip_name, mapping_mode):
    import apex
    source, target = node(source_path), node(target_path)
    if not isinstance(target, hou.SopNode):
        raise ValueError('target_path must be an APEX scene SOP.')
    asset_id = source.userData('astra_uthana_asset')
    _, filename = _cached_file(asset_id)
    if source.type().name() != 'kinefx::fbxanimimport' or source.parm('fbxfile').evalAsString().replace('\\', '/') != filename.as_posix():
        raise ValueError('Use the unmodified FBX source_path returned by houdini_uthana_import.')
    if mapping_mode not in ('mappingproperty', 'matchbyxform'):
        raise ValueError('Choose mappingproperty or matchbyxform.')
    clip_name = _identifier(clip_name)
    frame_range = _range(_geometry(source), source)
    scene_geo = target.geometry()
    if target.errors():
        raise ValueError('Target scene errors: ' + '; '.join(target.errors()))
    scene = apex.Scene()
    scene.loadFromGeometry(scene_geo)
    if not isinstance(scene.getData(rig_path), apex.SceneGraph) or not isinstance(scene.getData(skeleton_path), hou.Geometry):
        raise ValueError('Use an existing APEX rig_path and skeleton_path from the target scene.')
    if not rig_path.endswith('.rig') or not skeleton_path.endswith('.skel'):
        raise ValueError('Expected packed APEX rig and skeleton paths.')
    parts = rig_path.strip('/').split('/')
    if len(parts) != 2 or not parts[0].endswith('.char') or skeleton_path.rsplit('/', 1)[0] != rig_path.rsplit('/', 1)[0]:
        raise ValueError('This retarget adapter needs one character with its rig and skeleton in the same .char folder.')
    # Always make a distinct clip so the original animation remains recoverable.
    used = set(scene.dataPaths())
    base, suffix = clip_name, 1
    while any(p.startswith('/animation/' + clip_name + '.clip') for p in used):
        suffix += 1
        clip_name = base + '_' + str(suffix)
    network = target.parent()
    created = []
    with hou.undos.group('Astra: scene edit'):
        branch = network.createNode('subnet', 'uthana_' + clip_name, run_init_scripts=False)
        branch.setInput(0, target)
        branch.setUserData('astra_uthana_asset', asset_id)
        branch.setComment('Local Uthana retarget. Original character enters input 0; no uploads. Generated clip: ' + clip_name)
        created.append(branch)
        def create(typename, name):
            n = branch.createNode(typename, name, run_init_scripts=False)
            created.append(n)
            return n
        try:
            unpack = create('apex::unpackcharacter', 'character_skeleton')
            unpack.setInput(0, branch.indirectInputs()[0])
            unpack.parm('charname').set(parts[0].removesuffix('.char'))
            unpack.parm('rigpath').set('/' + parts[1])
            unpack.parm('skelpath').set('/' + skeleton_path.rsplit('/', 1)[1])
            imported = create('object_merge', 'source_motion')
            imported.parm('objpath1').set(source.path())
            imported.parm('xformtype').set(0)
            src = create('kinefx::biped_setup', 'source_biped')
            src.setInput(0, imported)
            tgt = create('kinefx::biped_setup', 'target_biped')
            tgt.setInput(0, unpack, 2)
            tgt.parm('restmethod').set('timeshift')
            tgt.parm('restframe').deleteAllKeyframes()
            tgt.parm('restframe').set(frame_range[0])
            _geometry(src)
            _geometry(tgt)
            ret = create('kinefx::biped_retarget', 'retarget_motion')
            ret.setInput(0, tgt)
            ret.setInput(1, src)
            _geometry(ret)
            bake = create('apex::animationfromskeleton', 'motion_to_apex')
            bake.setInput(0, branch.indirectInputs()[0])
            bake.setInput(1, ret)
            bake.parm('rigpath').set(rig_path)
            bake.parm('skeletonpath').set(skeleton_path)
            bake.parm('mapusing').set(mapping_mode)
            bake.parm('framerangemode').set('range')
            for parm in bake.parmTuple('framerange'):
                parm.deleteAllKeyframes()
            bake.parmTuple('framerange').set(frame_range)
            bake.parm('clipname').set(clip_name)
            bake.parm('createnewlayer').set(True)
            bake.parm('newlayer').set('Uthana')
            bake.parm('replaceexistinganim').set(False)
            geo = bake.geometry()
            if bake.errors():
                raise ValueError('APEX conversion: ' + '; '.join(bake.errors()))
            cooked = apex.Scene()
            cooked.loadFromGeometry(geo)
            cooked.initializeAnimStack()
            channels, varying = 0, 0
            for path in cooked.dataPaths():
                if not path.startswith('/animation/' + clip_name + '.clip/'):
                    continue
                data = cooked.getData(path)
                if not isinstance(data, hou.Geometry):
                    continue
                for prim in data.prims():
                    if isinstance(prim, hou.ChannelPrim) and prim.keyFrames():
                        channels += 1
                        values = [prim.eval(f) for f in prim.keyFrames()]
                        varying += max(values) - min(values) > 1e-5
            if not channels:
                raise ValueError('No APEX control channels were produced. The rig needs control-to-joint mapping; inspect motion_to_apex and the rig mapping metadata.')
            output = create('apex::sceneanimate', 'ANIMATE_UTHANA')
            output.setInput(0, bake)
            output.setDisplayFlag(True)
            output.setRenderFlag(True)
            branch.setDisplayFlag(True)
            branch.setRenderFlag(True)
            branch.layoutChildren()
            branch.moveToGoodPosition()
            return {'ok': True, 'branch_path': branch.path(), 'animate_path': output.path(),
                    'rig_path': rig_path, 'skeleton_path': skeleton_path,
                    'clip_name': clip_name, 'active_clip': cooked.getActiveClipPath(),
                    'frame_range': list(frame_range), 'keyed_channels': channels, 'varying_channels': varying,
                    'warnings': [w for n in created for w in n.warnings()],
                    'note': 'Retargeted locally onto the character. Enter ANIMATE_UTHANA to review and edit. Source/target Biped Setup and Biped Retarget remain available for pose/foot adjustments.'}
        except Exception as exc:
            branch.layoutChildren()
            branch.moveToGoodPosition()
            return {'ok': False, 'branch_path': branch.path(), 'nodes': [n.path() for n in created],
                    'error': str(exc), 'note': 'Partial retarget branch retained; original scene connections remain. Inspect the failing native SOP; use Undo last edit to remove this batch.'}
