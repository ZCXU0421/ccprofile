import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ccprofile_app.webdav import WebDAVAuthError, WebDAVClient, WebDAVError


class WebDAVClientTest(unittest.TestCase):
    def test_ensure_directory_ignores_existing_directory_statuses(self):
        client = WebDAVClient("https://example.com/dav", "user", "pass")

        for status_code in (301, 405):
            with self.subTest(status_code=status_code):
                success_resp = SimpleNamespace(status=200, close=lambda: None)
                with patch.object(
                    client,
                    "_make_request",
                    side_effect=[
                        WebDAVError(f"HTTP {status_code}", status_code=status_code),
                        success_resp,
                    ],
                ):
                    client.ensure_directory("remote")

    def test_ensure_directory_raises_for_other_http_errors(self):
        client = WebDAVClient("https://example.com/dav", "user", "pass")

        with patch.object(
            client,
            "_make_request",
            side_effect=WebDAVError("HTTP 409", status_code=409),
        ):
            with self.assertRaises(WebDAVError):
                client.ensure_directory("remote")

    def test_test_connection_propagates_auth_errors(self):
        client = WebDAVClient("https://example.com/dav", "user", "pass")

        with patch.object(
            client,
            "_make_request",
            side_effect=WebDAVAuthError("Authentication failed"),
        ):
            with self.assertRaises(WebDAVAuthError):
                client.test_connection()

    def test_make_request_uses_client_timeout(self):
        client = WebDAVClient("https://example.com/dav", "user", "pass", timeout=12)

        with patch.object(client.opener, "open", return_value=SimpleNamespace(close=lambda: None)) as open_mock:
            client._make_request("HEAD", "remote")

        self.assertEqual(open_mock.call_args.kwargs["timeout"], 12)


if __name__ == "__main__":
    unittest.main()
