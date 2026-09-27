"""Texture asset tools run outside Houdini; paths and writes are explicitly scoped."""
from solaris_contracts import obj,S,V
TEXTURE_TOOLS = [
    {'name':'texture_library_search','description':'Search locally downloaded Megascans/Fab textures and Astra texture cache by folder/filename words. Empty query lists available assets. Returns paths and inferred map roles; inspect filenames before binding. Does not contact Epic or read credentials.',
     'schema':obj(query=S)},
    {'name':'texture_download','description':'Download a texture image or texture ZIP from an HTTPS download URL into Astra texture cache. Name is a new simple filename with its extension. No uploads, login-password submission, purchases or overwrites. Supports image files and bounded image-only ZIP extraction. Fab product-page URLs are not file URLs; use an authorized download link or the local library.',
     'schema':obj(url=S,name=S)},
    {'name':'texture_write','description':'Write a procedural PNG texture in Astra cache: solid, checker, gradient or seeded noise. Colors are RGB values 0–1. Output name must be a new simple .png filename. Use modest resolution (typically 512) for working lookdev. No arbitrary code or filesystem writes.',
     'schema':obj(name=S,pattern={'type':'string','enum':['solid','checker','gradient','noise']},
                  size={'type':'integer','minimum':16,'maximum':2048},color_a=V,color_b=V,
                  scale={'type':'integer','minimum':1,'maximum':128},seed={'type':'integer','minimum':0,'maximum':2147483647})},
]
TEXTURE_NAMES = {s['name'] for s in TEXTURE_TOOLS}
TEXTURE_RULES = '''
The user authorizes texture downloads and writing generated textures for Houdini lookdev.
Use texture_library_search first for assets in the configured local library and texture cache.
Use texture_download for authorized HTTPS file URLs and texture_write for procedural PNGs.
These tools run outside Houdini and write only to the project's texture_cache. They are an
explicit exception to the generic no-file/no-network rules. Never say texture writing is
unavailable. Connect maps with houdini_materialx_textures, using Raw for data maps and the
appropriate color space for base color. Preserve original library assets and use 1K/2K
textures for working lookdev where available. Never read or send Epic passwords, login
documents, browser cookies or tokens to the model. Fab credentials are not a texture API
key; product pages require authorized download through Fab/Launcher. If a new Fab asset
requires sign-in or purchase, explain that step; do not invent a download or buy it.
'''
