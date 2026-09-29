"""Preflight rejects executable parameters and arbitrary file paths without evaluating them."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import access_policy
import scene_policy


class Template:
    def __init__(self, file=False):
        self.file = file
    def stringType(self):
        return 'file' if self.file else 'plain'


class Parm:
    def __init__(self, name, file=False):
        self.key = name
        self.template = Template(file)
    def name(self):
        return self.key
    def parmTemplate(self):
        return self.template


class ScenePolicyTests(unittest.TestCase):
    def test_script_and_unknown_node_types_are_disabled(self):
        for category, typename in [('Sop','python'),('Sop','attribwrangle'),('Lop','pythonscript'),
                                    ('Sop','file'),('Sop','object_merge'),('Object','my_custom_asset')]:
            with self.subTest(typename=typename), self.assertRaisesRegex(PermissionError, 'Access denied'):
                scene_policy.validate_type(typename, category)
        scene_policy.validate_type('box', 'Sop')

    def test_code_and_outside_file_parameters_are_rejected(self):
        fake = SimpleNamespace(StringParmTemplate=Template, stringParmType=SimpleNamespace(FileReference='file'))
        with tempfile.TemporaryDirectory() as directory, patch.dict('sys.modules', {'hou':fake}), \
             patch.object(access_policy,'scene_path',return_value=Path(directory)/'scene.hip'):
            for parm, value in [(Parm('snippet'), 'remove geometry'), (Parm('label'), '`python("x")`'),
                                (Parm('file',True), str(Path(directory).parent/'private.txt'))]:
                with self.assertRaisesRegex(PermissionError, 'Access denied'):
                    scene_policy.validate_parameter(parm,value)
            scene_policy.validate_parameter(Parm('file',True), '$HIP/asset.bgeo')
            scene_policy.validate_parameter(Parm('tx'), 2.0)


if __name__ == '__main__':
    unittest.main()
