"""No-network tests for billing deduplication, credentials and cache boundaries."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import uthana_client as uc


class UthanaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = patch.object(uc, 'CACHE', Path(self.temp.name))
        self.cache.start()
        self.client = uc.Client('test-secret')

    def tearDown(self):
        self.cache.stop()
        self.temp.cleanup()

    def create(self):
        return self.client.generate('A relaxed person waves.', 4, 'quality', 0)

    def test_generation_sends_text_settings_and_builtin_character_only(self):
        with patch.object(self.client, 'graphql', return_value={'create_text_to_motion_job': {'job': {'id': 'job1', 'status': 'READY'}}}) as request:
            first = self.create()
            second = self.client.generate('A relaxed person waves.', 4.0, 'quality', 0)
        self.assertEqual(first, second)
        self.assertEqual(request.call_count, 1)
        query, variables = request.call_args.args
        self.assertEqual(set(variables), {'prompt', 'length', 'character'})
        self.assertEqual(variables['character'], uc.CHARACTER)
        self.assertNotIn('test-secret', json.dumps(first))
        self.assertNotIn('upload', query.lower())

    def test_uncertain_submission_is_not_repeated(self):
        with patch.object(self.client, 'graphql', side_effect=RuntimeError('Timed out')) as request:
            self.assertEqual(self.create()['status'], 'UNKNOWN')
            self.assertEqual(self.create()['status'], 'UNKNOWN')
        self.assertEqual(request.call_count, 1)

    def test_invalid_generation_does_not_submit(self):
        with patch.object(self.client, 'graphql') as request:
            for values in [('', 4, 'quality', 0), ('walk', 99, 'quality', 0),
                           ('walk', 4.5, 'quality', 0), ('walk', 4, 'bad', 0), ('walk', 4, 'quality', -1)]:
                with self.assertRaises(ValueError):
                    self.client.generate(*values)
        request.assert_not_called()

    def test_completed_job_can_be_recovered(self):
        with patch.object(self.client, 'graphql', return_value={'create_text_to_motion_job': {'job': {'id': 'job1', 'status': 'READY'}}}):
            first = self.create()
        with patch.object(self.client, 'graphql', return_value={'job': {'status': 'FINISHED', 'result': {'result': {'id': 'motion1'}}}}):
            result = self.client.status(first['asset_id'])
        self.assertEqual(result['motion_id'], 'motion1')
        self.assertEqual(uc.read_asset(first['asset_id'])['status'], 'FINISHED')

    def test_download_cached_and_redirect_auth_stripped(self):
        asset = {'asset_id': 'a' * 24, 'status': 'FINISHED', 'motion_id': 'motion1'}
        uc.save_asset(asset)
        requests = []
        def response(request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise urllib.error.HTTPError(request.full_url, 302, 'redirect',
                    {'Location': 'https://test-bucket.s3.amazonaws.com/motion.fbx'}, None)
            return io.BytesIO(b'Kaydara FBX Binary  ' + b'0' * 128)
        with patch.object(self.client.opener, 'open', side_effect=response):
            self.client.download(asset['asset_id'], 24, False)
            self.client.download(asset['asset_id'], 24, False)
        self.assertEqual(len(requests), 2)
        self.assertIn('Authorization', dict(requests[0].header_items()))
        self.assertNotIn('Authorization', dict(requests[1].header_items()))
        self.assertIn('no_mesh=true', requests[0].full_url)
        self.assertTrue((uc.cache_dir(asset['asset_id']) / 'motion_24_0.fbx').is_file())

    def test_graphql_error_redacts_key(self):
        with patch.object(self.client, '_open', return_value=io.BytesIO(json.dumps({'errors': [{'message': 'invalid test-secret'}]}).encode())):
            with self.assertRaisesRegex(ValueError, r'\[redacted\]') as error:
                self.client.graphql('{__typename}')
        self.assertNotIn('test-secret', str(error.exception))

    def test_cache_traversal_and_credential_destination_rejected(self):
        for value in ('../key', '/tmp/secret', 'a' * 23, ''):
            with self.assertRaises(ValueError):
                uc.cache_dir(value)
        with self.assertRaises(ValueError):
            self.client._open('https://example.com/file')
        with self.assertRaises(ValueError):
            self.client._open('http://uthana.com/file')


if __name__ == '__main__':
    unittest.main()
