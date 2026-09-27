"""Run with .mcp-venv Python. Offline texture IO and download validation checks."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from PIL import Image
import texture_assets as textures
from texture_paths import allowed_texture


class TextureTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache=Path(directory.name)
        self.patch=patch.object(textures,'CACHE',self.cache)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_write_and_preserve_existing_texture(self):
        result=textures.write('checker.png','checker',32,[0,0,0],[1,1,1],4,5)
        with Image.open(result['path']) as im:
            self.assertEqual(im.getpixel((0,0)),(0,0,0))
            self.assertEqual(im.getpixel((8,0)),(255,255,255))
        with self.assertRaises(ValueError):
            textures.write('checker.png','solid',32,[1,0,0],[0,0,0],4,5)

    def test_paths_and_credentials_cannot_be_texture_files(self):
        for name in ('../secret.png','C:/file.png','../.secrets/epic_games_login.md'):
            with self.assertRaises(ValueError):
                textures.destination(name)
        with self.assertRaises(ValueError):
            allowed_texture(str(Path(__file__).parent/'.secrets/epic_games_login.md'))

    def test_private_url_rejected_before_request(self):
        with patch('texture_assets.socket.getaddrinfo',return_value=[(None,None,None,None,('127.0.0.1',443))]):
            with self.assertRaises(ValueError):
                textures.validate_url('https://localhost/file.png')

    def test_https_download_is_validated_and_recorded_without_token(self):
        data=io.BytesIO()
        Image.new('RGB',(16,16),(255,0,0)).save(data,format='PNG')
        transport=httpx.MockTransport(lambda request:httpx.Response(200,content=data.getvalue()))
        client=httpx.Client(transport=transport)
        with patch('texture_assets.httpx.Client',return_value=client),patch('texture_assets.validate_url'):
            result=textures.download('https://example.org/red.png?token=secret','red.png')
        self.assertTrue(Path(result['files'][0]).is_file())
        self.assertNotIn('token=secret',(self.cache/'red.png.source.json').read_text())

    def test_html_response_is_not_saved_as_texture(self):
        client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'<html>sign in</html>')))
        with patch('texture_assets.httpx.Client',return_value=client),patch('texture_assets.validate_url'):
            with self.assertRaises(Exception):
                textures.download('https://example.org/file.png','login.png')
        self.assertFalse((self.cache/'login.png').exists())


if __name__=='__main__':
    unittest.main()
