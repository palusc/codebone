"""Tests for codebone native in-app auto-updater."""
import unittest
from unittest.mock import MagicMock, patch

from src.updater import parse_version, check_for_updates


class TestUpdater(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("1.2.0"), (1, 2, 0))
        self.assertEqual(parse_version("v1.2.0"), (1, 2, 0))
        self.assertEqual(parse_version("V2.0.1"), (2, 0, 1))
        self.assertEqual(parse_version("1.3"), (1, 3, 0))
        self.assertEqual(parse_version("1.2.0-beta.1"), (1, 2, 0))
        self.assertTrue(parse_version("1.2.1") > parse_version("1.2.0"))
        self.assertTrue(parse_version("2.0.0") > parse_version("1.9.9"))
        self.assertFalse(parse_version("1.2.0") > parse_version("1.2.0"))

    @patch("urllib.request.urlopen")
    def test_check_for_updates_found(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"""{
            "tag_name": "v1.3.0",
            "name": "codebone v1.3.0",
            "body": "Exciting new features",
            "assets": [
                {
                    "name": "codebone-macos-arm64.zip",
                    "size": 45000000,
                    "browser_download_url": "https://github.com/palusc/codebone/releases/download/v1.3.0/codebone-macos-arm64.zip"
                }
            ],
            "html_url": "https://github.com/palusc/codebone/releases/tag/v1.3.0"
        }"""
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = check_for_updates(current_version="1.2.0")
        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "1.3.0")
        self.assertEqual(result["download_url"], "https://github.com/palusc/codebone/releases/download/v1.3.0/codebone-macos-arm64.zip")
        self.assertEqual(result["asset_size"], 45000000)

    @patch("urllib.request.urlopen")
    def test_check_for_updates_already_latest(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"""{
            "tag_name": "v1.2.0",
            "name": "codebone v1.2.0",
            "body": "Latest release",
            "assets": []
        }"""
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = check_for_updates(current_version="1.2.0")
        self.assertFalse(result["update_available"])
    @patch("urllib.request.urlopen")
    def test_download_and_install_invalid_package(self, mock_urlopen):
        import io
        import zipfile
        from src.updater import download_and_install_update

        # Create an in-memory zip file without codebone.app
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "not an app")
        buf.seek(0)

        mock_resp = MagicMock()
        mock_resp.read = buf.read
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with self.assertRaises(RuntimeError):
            download_and_install_update("https://dummy/url.zip", target_app_path="/tmp/dummy_test.app")


if __name__ == "__main__":
    unittest.main()
