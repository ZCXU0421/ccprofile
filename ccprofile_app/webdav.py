"""WebDAV client for remote file operations."""

import base64
import json
import ssl
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 30


class WebDAVError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class WebDAVConnectionError(WebDAVError):
    pass


class WebDAVAuthError(WebDAVError):
    pass


class WebDAVNotFoundError(WebDAVError):
    pass


class WebDAVServerError(WebDAVError):
    pass


class WebDAVClient:
    def __init__(self, base_url, username, password, verify_ssl=True, timeout=DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._auth_header = f"Basic {credentials}"

        if verify_ssl:
            ssl_context = ssl.create_default_context()
        else:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        https_handler = urllib.request.HTTPSHandler(context=ssl_context)
        self.opener = urllib.request.build_opener(https_handler)

    def _build_url(self, remote_path):
        return f"{self.base_url}/{remote_path.lstrip('/')}"

    def _make_request(self, method, remote_path, data=None, headers=None):
        headers = dict(headers) if headers else {}
        headers["Authorization"] = self._auth_header

        url = self._build_url(remote_path)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            resp = self.opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise WebDAVAuthError("Authentication failed") from e
            if e.code == 404:
                raise WebDAVNotFoundError(f"Not found: {remote_path}") from e
            if 500 <= e.code < 600:
                raise WebDAVServerError(f"Server error {e.code}") from e
            raise WebDAVError(f"HTTP {e.code}: {e.reason}", status_code=e.code) from e
        except urllib.error.URLError as e:
            raise WebDAVConnectionError(f"Connection failed: {e.reason}") from e
        except ssl.SSLError as e:
            raise WebDAVConnectionError(f"SSL error: {e}") from e

        return resp

    def test_connection(self):
        headers = {"Depth": "0"}
        try:
            resp = self._make_request("PROPFIND", "", data=b"", headers=headers)
            ok = resp.status in (200, 207)
            resp.close()
            return ok
        except WebDAVAuthError:
            raise
        except WebDAVError:
            return False

    def exists(self, remote_path):
        try:
            resp = self._make_request("HEAD", remote_path)
            ok = resp.status == 200
            resp.close()
            return ok
        except WebDAVNotFoundError:
            return False
        except WebDAVError:
            return False

    def download(self, remote_path):
        resp = self._make_request("GET", remote_path)
        try:
            return resp.read()
        finally:
            resp.close()

    def download_json(self, remote_path):
        data = self.download(remote_path)
        return json.loads(data.decode("utf-8"))

    def upload(self, remote_path, data, content_type="application/octet-stream"):
        if isinstance(data, str):
            data = data.encode("utf-8")
        headers = {"Content-Type": content_type}
        resp = self._make_request("PUT", remote_path, data=data, headers=headers)
        resp.close()

    def delete(self, remote_path):
        try:
            resp = self._make_request("DELETE", remote_path)
            resp.close()
        except WebDAVNotFoundError:
            pass

    def get_etag(self, remote_path):
        try:
            resp = self._make_request("HEAD", remote_path)
            etag = resp.headers.get("ETag", "")
            resp.close()
            return etag.strip('"') or None
        except WebDAVError:
            return None

    def ensure_directory(self, remote_path):
        try:
            resp = self._make_request("MKCOL", remote_path)
            resp.close()
        except WebDAVError as e:
            if e.status_code in (301, 405):
                pass
            else:
                raise
