"""Enforce rendering conventions on the generic node creation tool."""
def validate_creation(node_type,parent_path):
    import hou
    base=node_type.split('::')[0].lower()
    if base in ('ifd','mantra','opengl','principledshader','classicshader','v_matte','v_plastic'):
        raise ValueError('Use Solaris, Karma XPU and MaterialX for this assistant.')
    parent=hou.node(parent_path)
    if parent and parent.childTypeCategory()==hou.objNodeTypeCategory() and 'light' in base:
        raise ValueError('Author lighting in Solaris with USD light LOPs.')
    if parent and parent.childTypeCategory()==hou.ropNodeTypeCategory() and base=='karma':
        raise ValueError('Use Solaris Karma XPU settings, not an /out Karma ROP.')
