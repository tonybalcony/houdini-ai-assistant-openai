import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from render_jobs import validate_launch_state, write_state
import access_policy


class RenderPolicyTests(unittest.TestCase):
    def test_brief_windows_reader_lock_does_not_fail_the_render(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            original = Path.replace
            attempts = []
            def replace(source, target):
                attempts.append(target)
                if len(attempts) < 3:
                    raise PermissionError('simulated Windows sharing violation')
                return original(source, target)
            with patch.object(Path, 'replace', replace), patch('render_jobs.time.sleep'):
                write_state(directory, {'status':'running'})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(json.loads((directory/'state.json').read_text())['status'], 'running')

    def test_persisted_render_state_is_rechecked_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / 'project'
            job = project / '.astra/scene/renders/job'
            job.mkdir(parents=True)
            snapshot = job / 'scene.usdc'
            snapshot.touch()
            installation = root / 'host'
            husk = installation / 'bin/husk.exe'
            husk.parent.mkdir(parents=True)
            husk.touch()
            state = {'output':str(job/'render.png'), 'snapshot':str(snapshot), 'husk':str(husk),
                     'quality':'working', 'frame':1, 'settings':'/Render/settings'}
            with patch.dict(os.environ, {'HFS':str(installation)}), \
                 patch.object(access_policy, 'scene_path', return_value=project/'scene.hip'):
                self.assertEqual(validate_launch_state(job,state),job/'render.png')
                for key,value in [('output',str(root/'personal.png')), ('snapshot',str(root/'scene.usdc')),
                                  ('husk',str(root/'untrusted.exe'))]:
                    with self.subTest(key=key), self.assertRaises(PermissionError):
                        validate_launch_state(job,{**state,key:value})


if __name__ == '__main__':
    unittest.main()
