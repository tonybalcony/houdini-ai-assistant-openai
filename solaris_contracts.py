"""Shared Solaris tool schemas for native MCP and the API worker."""
def obj(**properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}

S = {'type':'string'}
N = {'type':'number'}
V = {'type':'array','items':N,'minItems':3,'maxItems':3}
UNIT = {'type':'number','minimum':0,'maximum':1}
def op(kind, **fields):
    return obj(kind={'type':'string','enum':[kind]}, **fields)

SOLARIS_TOOLS = [
    {'name':'houdini_materialx_textures','description':'Connect existing texture files from the configured Megascans library or Astra cache to a MaterialX Standard Surface in a Solaris MaterialX Builder. Empty paths leave inputs unchanged. Uses sRGB texture color for base color and Raw for roughness, metalness, normals and displacement. Normal maps must use OpenGL +Y convention. Displacement scale is explicit and is disabled in working render snapshots. Inspect UVs and the material before use; this does not create UVs.',
     'schema':obj(shader_path=S,base_color_file=S,roughness_file=S,metalness_file=S,normal_file=S,displacement_file=S,displacement_scale={'type':'number','minimum':0,'maximum':10})},
    {'name':'houdini_solaris_inspect','description':'Cook and inspect a Solaris LOP USD stage: prim types, material bindings, cameras, lights and render settings. Results are bounded; root_prim narrows to a USD subtree. Use / for the whole stage. Large stages may take time.',
     'schema':obj(path=S, root_prim=S)},
    {'name':'houdini_solaris_create','description':'''Create one procedural Solaris operation under a LOP network (normally /stage). input_path is the preceding LOP or null for an empty stage. Return actual node and USD paths before chaining. import_sop imports a SOP; material creates a MaterialX Builder in a Material Library and binds it to prim_pattern; light creates a USD light; camera creates a USD camera (rotation degrees; looks along local -Z); karma creates Karma XPU render settings. Original nodes remain. Adjust parameters later with houdini_edit; verify with houdini_solaris_inspect. No render is launched.''',
     'schema':obj(parent=S,input_path={'type':['string','null']},name=S,config={'anyOf':[
        op('import_sop',source_path=S,prim_path=S),
        op('material',prim_pattern=S,base_color=V,roughness=UNIT,metalness=UNIT),
        op('light',light_type={'type':'string','enum':['rect','disk','sphere','distant','dome']},position=V,rotation=V,color=V,intensity={'type':'number','minimum':0},exposure=N),
        op('camera',position=V,rotation=V,focal_length={'type':'number','minimum':1,'maximum':1000}),
        op('karma',camera_prim=S,resolution={'type':'array','items':{'type':'integer','minimum':16,'maximum':8192},'minItems':2,'maxItems':2},samples={'type':'integer','minimum':1,'maximum':4096}),
     ]})},
    {'name':'houdini_solaris_render_start','description':'''Render ONE frame from a Solaris Karma XPU settings node in a separate local husk process. path must have engine=xpu; other engines are rejected. output_file is an absolute .exr/.png path that does not exist, or empty for a unique cached working PNG or final EXR. Exports a current-frame USD snapshot locally; no uploads. Returns job_id, not a finished render. Poll status; never blindly restart an unknown result. Large USD export can block Houdini; external dependencies must remain accessible.''',
     'schema':obj(path=S,frame={'type':'integer'},output_file=S,quality={'type':'string','enum':['working','final'],'description':'Use working unless the user asks for a final. Working disables displacement/DOF/motion blur, caps 960 pixels and 32 samples, and lowers ray bounces in the exported snapshot.'})},
    {'name':'houdini_solaris_render_status','description':'Read durable background Karma XPU job state. Empty job_id lists recent jobs after reconnecting. Complete means husk exited successfully and produced an image. Stale running jobs report unknown; do not automatically resubmit.',
     'schema':obj(job_id=S,wait_seconds={'type':'integer','minimum':0,'maximum':10,'description':'Use 10 while waiting; returns early when a new preview appears or rendering ends. Use 0 to list jobs.'})},
    {'name':'houdini_solaris_render_cancel','description':'Request cancellation of a background Karma XPU job. Check status separately; partial files and scene nodes remain.',
     'schema':obj(job_id=S)},
    {'name':'houdini_solaris_render_preview','description':'Return the latest actual WIP image from an existing render, even while it is running. If unavailable, wait and check again. Use this to judge composition, lighting and materials without waiting for final convergence. Cancel an unhelpful render before changing the scene and starting a revised preview.',
     'schema':obj(job_id=S)},
]

SOLARIS_RULES = '''
User's standing workflow rules apply to every model and saved conversation:
All rendering MUST use Karma XPU in Solaris (LOPs/USD). Never use Mantra, Karma CPU,
OpenGL scene renders or legacy /out render setups. Never fall back to another renderer.
All lighting must be authored in Solaris with USD lights. All authored materials must
use MaterialX networks in Solaris Material Libraries, with proper USD material bindings.
Preserve existing legacy nodes; inspect and branch into Solaris rather than deleting them.
Use houdini_solaris_create/inspect for import, MaterialX, lighting, cameras and Karma XPU.
These tools may be supplied by the houdini MCP server when resuming an older chat.
Use houdini_solaris_render_start/status/cancel for background renders. Started is not
completed. Poll at reasonable intervals; list existing jobs after interruption.
If XPU cannot run, report its error and keep the setup; do not switch rendering engines.
Use existing Houdini node tools for additional Solaris parameters and MaterialX wiring.
Viewport screenshots and node-network captures are inspection, not scene rendering.
The supplied Solaris render tools may write local USD snapshots and requested images
and run Houdini's renderer. This is an explicit exception to the general file/button limits.
For look development and working renders ALWAYS select quality=working: this caps the
longest image edge at 960 and path-traced samples at 32, disables displacement, motion blur
and depth of field, and reduces secondary rays in the exported snapshot. Original scene
settings remain unchanged. Only select quality=final when the user asks for a final render.
Call houdini_solaris_render_preview as soon as a WIP image is available; do not wait for
final convergence to judge framing, broad lighting and material appearance. Be explicit
about unfinished noise and disabled features. Never claim visual judgment from status text.
If a working preview reveals a problem, cancel it, improve the scene, and render another
working preview. Keep ray limits high enough for the effect being evaluated; explain when
an optimized preview cannot judge displacement, motion blur, depth of field or deep glass.
'''

def validate_arguments(name, arguments):
    """Validate the small schema subset used here without extra Houdini packages."""
    import math
    def check(value, schema):
        if 'anyOf' in schema:
            for alternative in schema['anyOf']:
                try:
                    check(value, alternative)
                    return
                except ValueError:
                    pass
            raise ValueError('Invalid Solaris operation settings.')
        types = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
        valid = {'object':type(value) is dict, 'array':type(value) is list,
                 'string':isinstance(value,str), 'integer':type(value) is int,
                 'number':type(value) in (int,float), 'null':value is None}
        if not any(valid.get(t,False) for t in types):
            raise ValueError('Invalid Solaris argument type.')
        if 'enum' in schema and value not in schema['enum']:
            raise ValueError('Unsupported Solaris operation.')
        if isinstance(value,dict):
            if set(value) != set(schema['properties']):
                raise ValueError('Missing or unexpected Solaris arguments.')
            for key,item in value.items():
                check(item,schema['properties'][key])
        elif isinstance(value,list):
            if not schema.get('minItems',0) <= len(value) <= schema.get('maxItems',999):
                raise ValueError('Invalid Solaris vector size.')
            for item in value:
                check(item,schema['items'])
        elif type(value) in (int,float):
            if not math.isfinite(value) or not schema.get('minimum',-1e100) <= value <= schema.get('maximum',1e100):
                raise ValueError('Solaris numeric setting is out of range.')
        elif isinstance(value,str) and len(value) > 4096:
            raise ValueError('Solaris text argument is too large.')
    spec = next((s for s in SOLARIS_TOOLS if s['name']==name), None)
    if spec is None:
        raise ValueError('Unknown Solaris tool.')
    check(arguments, spec['schema'])
