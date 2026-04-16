import http.client
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ccprofile_app.proxy import ProxyConfig, ProxyHandler, ProxyHTTPServer


class RecordingUpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests = []

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        self.__class__.requests.append(
            {
                "path": self.path,
                "body": json.loads(body.decode("utf-8")),
            }
        )
        response = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def start_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class ProxyTest(unittest.TestCase):
    def setUp(self):
        RecordingUpstreamHandler.requests = []
        self.servers = []

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()

    def make_server(self, server_cls, handler_cls):
        server = server_cls(("localhost", 0), handler_cls)
        self.servers.append(server)
        start_server(server)
        return server

    def make_proxy(self, base_url):
        config = {
            "port": 0,
            "virtual_model_prefix": "ccprofile",
            "model_mapping": {
                "opus": {
                    "provider": "test",
                    "model": "real-opus",
                    "base_url": base_url,
                    "api_key": "test-key",
                }
            },
        }
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        config_path = Path(tmpdir.name) / "proxy_config.json"
        config_path.write_text(json.dumps(config), "utf-8")
        ProxyHandler.proxy_config = ProxyConfig(config_path)
        return self.make_server(ProxyHTTPServer, ProxyHandler)

    def post_json(self, port, path, payload):
        conn = http.client.HTTPConnection("localhost", port, timeout=5)
        body = json.dumps(payload).encode("utf-8")
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = conn.getresponse()
        response_body = response.read()
        conn.close()
        return response, response_body

    def test_count_tokens_is_forwarded_with_model_mapping(self):
        upstream = self.make_server(ThreadingHTTPServer, RecordingUpstreamHandler)
        proxy = self.make_proxy(f"http://localhost:{upstream.server_address[1]}/api/anthropic")

        response, response_body = self.post_json(
            proxy.server_address[1],
            "/v1/messages/count_tokens?beta=true",
            {
                "model": "ccprofile-opus",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response_body.decode("utf-8")), {"ok": True})
        self.assertEqual(len(RecordingUpstreamHandler.requests), 1)
        forwarded = RecordingUpstreamHandler.requests[0]
        self.assertEqual(forwarded["path"], "/api/anthropic/v1/messages/count_tokens?beta=true")
        self.assertEqual(forwarded["body"]["model"], "real-opus")

    def test_unknown_post_path_drains_body_and_returns_json(self):
        upstream = self.make_server(ThreadingHTTPServer, RecordingUpstreamHandler)
        proxy = self.make_proxy(f"http://localhost:{upstream.server_address[1]}/api/anthropic")

        response, response_body = self.post_json(
            proxy.server_address[1],
            "/v1/unknown",
            {
                "model": "ccprofile-opus",
                "messages": [{"role": "user", "content": "leftover body must be drained"}],
            },
        )

        self.assertEqual(response.status, 404)
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertNotIn(b"Bad request syntax", response_body)
        self.assertEqual(json.loads(response_body.decode("utf-8"))["type"], "error")
        self.assertEqual(RecordingUpstreamHandler.requests, [])


if __name__ == "__main__":
    unittest.main()
