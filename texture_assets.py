"""Texture search, bounded HTTPS downloads and procedural image writing."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import random
import re
import socket
from urllib.parse import urlsplit,urljoin
import zipfile
from PIL import Image,ImageDraw,ImageOps
import httpx
from diagnostics import redact
from texture_paths import CACHE,LIBRARIES,EXTENSIONS


def destination(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}',name) or '..' in name:
        raise ValueError('Use a simple filename, without folders or traversal.')
    CACHE.mkdir(parents=True,exist_ok=True)
    path = CACHE / name
    if path.exists():
        raise ValueError('Texture exists. Use another name; existing textures are preserved.')
    return path


def role(name):
    n = name.lower()
    for r,words in [('base_color',('albedo','basecolor','base_color','diffuse')),
                    ('roughness',('roughness','rough')),('normal',('normal',)),
                    ('metalness',('metallic','metalness')),('displacement',('displacement','height')),
                    ('opacity',('opacity',)),('occlusion',('occlusion','_ao'))]:
        if any(w in n for w in words):
            return r
    return 'unknown'


def search(query):
    terms = query.lower().split()
    groups, scanned = {},0
    for root in LIBRARIES:
        if not root.is_dir():
            continue
        for parent,dirs,files in os.walk(root,followlinks=False):
            dirs[:] = [d for d in sorted(dirs) if d.lower() not in ('.secrets','support','temp','.git')]
            for name in sorted(files):
                if Path(name).suffix.lower() not in EXTENSIONS:
                    continue
                scanned += 1
                path = Path(parent)/name
                if path.resolve().is_relative_to(root) and all(t in str(path.relative_to(root)).lower() for t in terms):
                    group = groups.setdefault(str(path.parent),[])
                    if len(group)<30:
                        group.append({'path':str(path),'map_role':role(name)})
                if len(groups)>=20 or scanned>=50000:
                    return {'status':'success','assets':[{'folder':k,'textures':v} for k,v in groups.items()],'truncated':True}
    return {'status':'success','assets':[{'folder':k,'textures':v} for k,v in groups.items()],'truncated':False,
            'libraries':[str(p) for p in LIBRARIES]}


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use an HTTPS asset URL without embedded login credentials.')
    for address in socket.getaddrinfo(parsed.hostname,parsed.port or 443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError('Texture downloads require a public HTTPS host.')


def validate_image(path):
    if path.suffix.lower()=='.exr':
        with path.open('rb') as stream:
            if stream.read(4)==bytes.fromhex('762f3101'):
                return
    with Image.open(path) as im:
        if im.width*im.height > 268435456:
            raise ValueError('Texture is too large.')
        im.verify()


def download(url,name):
    target = destination(name)
    if target.suffix.lower() not in EXTENSIONS|{'.zip'}:
        raise ValueError('Download must be a texture image or image ZIP.')
    temp = target.with_name(target.stem + '.part' + target.suffix)
    try:
        with httpx.Client(timeout=60,follow_redirects=False,trust_env=False) as client:
            current = url
            for _ in range(6):
                validate_url(current)
                with client.stream('GET',current) as response:
                    if response.is_redirect:
                        current = urljoin(current,response.headers['location'])
                        continue
                    if response.status_code!=200:
                        raise ValueError('Texture server returned HTTP ' + str(response.status_code))
                    size = 0
                    with temp.open('xb') as stream:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 256_000_000:
                                raise ValueError('Texture download exceeds 256 MB.')
                            stream.write(chunk)
                    break
            else:
                raise ValueError('Too many download redirects.')
        outputs = []
        if target.suffix.lower()=='.zip':
            directory = CACHE/(target.stem+'_textures')
            if directory.exists():
                raise ValueError('Texture extraction folder already exists.')
            with zipfile.ZipFile(temp) as archive:
                files = [f for f in archive.infolist() if Path(f.filename).suffix.lower() in EXTENSIONS and not f.is_dir()]
                if not files or len(files)>100 or sum(f.file_size for f in files)>512_000_000:
                    raise ValueError('ZIP must contain 1–100 textures, at most 512 MB unpacked.')
                # Flatten entry names; no archive-supplied paths are used for writes.
                names = [Path(f.filename.replace('\\','/')).name for f in files]
                if len(set(n.lower() for n in names))!=len(names):
                    raise ValueError('ZIP contains duplicate texture filenames.')
                directory.mkdir()
                for info,filename in zip(files,names):
                    p = directory/filename
                    p.write_bytes(archive.read(info))
                    validate_image(p)
                    outputs.append(str(p))
        else:
            validate_image(temp)
            outputs.append(str(target))
        # Windows rename refuses to overwrite an image created by a concurrent request.
        temp.rename(target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        target.with_name(target.name+'.source.json').write_text(json.dumps({'source':redact(url),
            'sha256':digest,'files':outputs},indent=2),encoding='utf-8')
        return {'status':'success','files':outputs,'sha256':digest}
    except Exception:
        if temp.exists():
            temp.unlink()
        raise


def write(name,pattern,size,color_a,color_b,scale,seed):
    target = destination(name)
    if target.suffix.lower()!='.png' or not 16<=size<=2048 or not 1<=scale<=128:
        raise ValueError('Use a PNG, size 16–2048 and scale 1–128.')
    if any(not 0<=v<=1 for c in (color_a,color_b) for v in c):
        raise ValueError('Texture colors must be between 0 and 1.')
    rng = random.Random(seed)
    mask=Image.new('L',(size,size),0)
    draw=ImageDraw.Draw(mask)
    if pattern=='checker':
        for y in range(scale):
            for x in range(scale):
                if (x+y)%2:
                    draw.rectangle((x*size//scale,y*size//scale,(x+1)*size//scale-1,(y+1)*size//scale-1),fill=255)
    elif pattern=='gradient':
        for x in range(size):
            draw.line((x,0,x,size-1),fill=round(255*x/(size-1)))
    elif pattern=='noise':
        mask=Image.frombytes('L',(scale,scale),rng.randbytes(scale*scale)).resize((size,size),Image.Resampling.BICUBIC)
    elif pattern!='solid':
        raise ValueError('Unsupported texture pattern.')
    im=ImageOps.colorize(mask,tuple(round(255*v) for v in color_a),tuple(round(255*v) for v in color_b))
    with target.open('xb') as stream:
        im.save(stream,format='PNG')
    return {'status':'success','path':str(target),'size':[size,size],'pattern':pattern}


def call(name,args):
    from jsonschema import validate
    from texture_contracts import TEXTURE_TOOLS
    spec = next(s for s in TEXTURE_TOOLS if s['name']==name)
    validate(args,spec['schema'])
    return {'texture_library_search':search,'texture_download':download,'texture_write':write}[name](**args)


if __name__=='__main__':
    import sys
    try:
        request = json.loads(sys.stdin.readline())
        print(json.dumps(call(request['name'],request['arguments'])))
    except Exception as exc:
        print(json.dumps({'status':'error','error':redact(exc)}))
