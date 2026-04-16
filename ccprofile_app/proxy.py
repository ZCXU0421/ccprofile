"""HTTP 代理服务器：将 Claude Code 请求路由到不同的 API 提供商。

此文件作为独立进程运行，不能依赖 ccprofile_app 模块。
"""

import argparse
import atexit
import datetime
import http.client
import json
import os
import signal
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

# ── 本地常量（不依赖其他模块）──

# 虚拟模型前缀（主路径）
_DEFAULT_VIRTUAL_MODEL_PREFIX = "ccprofile"

# Claude Code 模型槽位的默认前缀（仅作为 fallback）
# 代理从 proxy_config.json 读取前缀配置，此字典仅作为后备。
_DEFAULT_LEGACY_MODEL_SLOT_PREFIXES = {
    "opus": ("claude-opus",),
    "sonnet": ("claude-sonnet",),
    "haiku": (
        "claude-haiku",
        "claude-3-haiku",
        "claude-3-5-haiku",
    ),
}

# 默认配置文件路径
DEFAULT_CONFIG_PATH = Path.home() / ".ccprofile" / "proxy_config.json"
DEFAULT_UPSTREAM_TIMEOUT = 600
UPSTREAM_TIMEOUT_ENV = "CCPROFILE_PROXY_TIMEOUT"
SSL_VERIFY_ENV = "CCPROFILE_PROXY_SSL_VERIFY"
SSL_CERT_FILE_ENVS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
MESSAGES_PATH = "/v1/messages"
_cleanup_config_path: Optional[Path] = None

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

AUTH_HEADERS = {
    "authorization",
    "x-api-key",
}


class ProxyHTTPServer(ThreadingHTTPServer):
    """线程化 HTTP 服务器，避免并发请求互相阻塞。"""

    daemon_threads = True
    allow_reuse_address = True


class ProxyConfig:
    """代理配置加载器。"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config = None
        self._virtual_model_prefix = _DEFAULT_VIRTUAL_MODEL_PREFIX
        self._legacy_model_slot_prefixes = dict(_DEFAULT_LEGACY_MODEL_SLOT_PREFIXES)
        self._ssl_context: Optional[ssl.SSLContext] = None
        self._ssl_context_key: Optional[Tuple[bool, Optional[str]]] = None
        self._ssl_context_lock = threading.Lock()
        self._load_config()

    def _load_config(self):
        """从 proxy_config.json 加载配置。"""
        if not self.config_path.exists():
            print(f"错误: 代理配置文件不存在: {self.config_path}", file=sys.stderr)
            sys.exit(1)

        try:
            self.config = json.loads(self.config_path.read_text("utf-8"))
        except json.JSONDecodeError as e:
            print(f"错误: 代理配置文件格式错误: {e}", file=sys.stderr)
            sys.exit(1)

        # 读取虚拟模型前缀（主路径）
        self._virtual_model_prefix = self.config.get(
            "virtual_model_prefix",
            self._virtual_model_prefix,
        )

        # 读取 legacy 前缀配置（fallback）
        if "legacy_model_slot_prefixes" in self.config:
            self._legacy_model_slot_prefixes = self.config["legacy_model_slot_prefixes"]
        elif "model_slot_prefixes" in self.config:
            # 兼容旧版 proxy_config.json
            self._legacy_model_slot_prefixes = {
                slot: (prefix,)
                for slot, prefix in self.config["model_slot_prefixes"].items()
            }

    def get_model_target(self, model: str) -> Optional[Dict[str, Any]]:
        """根据模型名称获取目标提供商和模型。

        Args:
            model: Claude Code 请求中的 model 字段，如 "ccprofile-opus"

        Returns:
            包含 provider, model, base_url, api_key 的字典，或 None
        """
        if not self.config:
            return None

        model_mapping = self.config.get("model_mapping", {})

        # 主路径：匹配虚拟模型名 ccprofile-{slot}
        virtual_prefix = f"{self._virtual_model_prefix}-"
        if model.startswith(virtual_prefix):
            slot = model[len(virtual_prefix):]
            if slot in model_mapping:
                return model_mapping.get(slot)

        # Fallback：匹配旧的 Claude 模型名前缀
        for slot, prefixes in self._legacy_model_slot_prefixes.items():
            if isinstance(prefixes, str):
                prefixes = (prefixes,)
            if any(model.startswith(prefix) for prefix in prefixes):
                return model_mapping.get(slot)

        return None

    @property
    def port(self) -> int:
        return self.config.get("port", 18888)

    @property
    def upstream_timeout(self) -> Optional[float]:
        configured = os.environ.get(
            UPSTREAM_TIMEOUT_ENV,
            self.config.get("upstream_timeout", DEFAULT_UPSTREAM_TIMEOUT),
        )
        try:
            timeout = float(configured)
        except (TypeError, ValueError):
            return DEFAULT_UPSTREAM_TIMEOUT
        if timeout <= 0:
            return None
        return timeout

    @property
    def ssl_verify(self) -> bool:
        """Whether HTTPS upstream certificates should be verified."""
        configured = os.environ.get(
            SSL_VERIFY_ENV,
            self.config.get("ssl_verify", True),
        )
        if isinstance(configured, bool):
            return configured
        return str(configured).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
            "disable",
            "disabled",
        }

    @property
    def ssl_ca_bundle(self) -> Optional[str]:
        """Return the CA bundle path for HTTPS upstream verification."""
        for env_name in SSL_CERT_FILE_ENVS:
            value = os.environ.get(env_name)
            if value:
                return value

        configured = self.config.get("ssl_ca_bundle")
        if configured:
            return configured

        try:
            import certifi
        except ImportError:
            return None
        return certifi.where()

    def _build_ssl_context(
        self, ssl_verify: bool, ca_bundle: Optional[str]
    ) -> ssl.SSLContext:
        """Build the SSL context used for HTTPS upstream connections."""
        if not ssl_verify:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context

        if ca_bundle:
            return ssl.create_default_context(cafile=ca_bundle)
        return ssl.create_default_context()

    def create_ssl_context(self) -> ssl.SSLContext:
        """Create or reuse the SSL context used for HTTPS upstream connections."""
        ssl_verify = self.ssl_verify
        ca_bundle = self.ssl_ca_bundle if ssl_verify else None
        context_key = (ssl_verify, ca_bundle)

        with self._ssl_context_lock:
            if self._ssl_context is None or self._ssl_context_key != context_key:
                self._ssl_context = self._build_ssl_context(ssl_verify, ca_bundle)
                self._ssl_context_key = context_key
            return self._ssl_context


class ProxyHandler(BaseHTTPRequestHandler):
    """处理 Anthropic Messages API 请求的代理处理器。"""

    protocol_version = "HTTP/1.1"

    # 类变量，由主进程设置
    proxy_config: Optional[ProxyConfig] = None

    def log_message(self, format: str, *args):  # noqa: A002
        """将日志写入 stderr，主进程会重定向到 proxy.log。"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {format % args}", file=sys.stderr, flush=True)

    def _log_request(self, model: str, target_provider: str, target_model: str,
                     streaming: bool, status_code: Optional[int] = None):
        """记录单个请求的路由信息。"""
        stream_tag = "stream" if streaming else "sync"
        status_part = f" -> {status_code}" if status_code is not None else ""
        self.log_message(
            "%s %s -> %s/%s [%s]%s",
            self.command, model, target_provider, target_model,
            stream_tag, status_part,
        )

    def _anthropic_error(self, error_type: str, message: str) -> Dict[str, Any]:
        return {
            "type": "error",
            "error": {
                "type": error_type,
                "message": message,
            },
        }

    def _send_error_response(self, status_code: int, error_type: str, message: str):
        """发送 Anthropic 格式的错误响应。"""
        response_body = json.dumps(
            self._anthropic_error(error_type, message)
        ).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _send_streaming_error_response(
        self, status_code: int, error_type: str, message: str
    ):
        """发送 Anthropic SSE error 事件。"""
        self.send_response(status_code)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        event = self._format_sse_event(
            "error",
            self._anthropic_error(error_type, message),
        )
        self._write_chunk(event)
        self._finish_chunked_response()

    def _format_sse_event(self, event_type: str, data: Dict[str, Any]) -> bytes:
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event_type}\ndata: {payload}\n\n".encode("utf-8")

    def _write_chunk(self, chunk: bytes):
        if not chunk:
            return
        self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
        self.wfile.write(chunk)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _finish_chunked_response(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _copy_response_headers(
        self,
        response_headers,
        *,
        skip_content_length: bool,
    ) -> bool:
        """复制安全的端到端响应头，返回是否已写 Content-Type。"""
        sent_content_type = False
        skip_headers = HOP_BY_HOP_HEADERS | {"server", "date"}
        if skip_content_length:
            skip_headers.add("content-length")

        for key, value in response_headers:
            lower_key = key.lower()
            if lower_key in skip_headers:
                continue
            self.send_header(key, value)
            if lower_key == "content-type":
                sent_content_type = True
        return sent_content_type

    def _open_upstream_response(
        self, target_url: str, headers: Dict[str, str], body: bytes
    ):
        """打开到上游的连接并返回 (connection, response)。"""
        parsed = urlsplit(target_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"无效的 API 端点地址: {target_url}")

        path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        timeout = (
            self.proxy_config.upstream_timeout
            if self.proxy_config
            else DEFAULT_UPSTREAM_TIMEOUT
        )
        if parsed.scheme == "https":
            context = (
                self.proxy_config.create_ssl_context()
                if self.proxy_config
                else ssl.create_default_context()
            )
            connection = http.client.HTTPSConnection(
                parsed.netloc,
                timeout=timeout,
                context=context,
            )
        else:
            connection = http.client.HTTPConnection(parsed.netloc, timeout=timeout)

        upstream_headers = {}
        skip_headers = HOP_BY_HOP_HEADERS | {"host", "content-length", "accept-encoding"}
        for key, value in headers.items():
            if key.lower() not in skip_headers:
                upstream_headers[key] = value
        upstream_headers["Content-Length"] = str(len(body))
        upstream_headers["Accept-Encoding"] = "identity"

        connection.request("POST", path, body=body, headers=upstream_headers)
        return connection, connection.getresponse()

    def _build_target_url(self, target_url: str) -> str:
        """合并客户端请求 query 到目标 provider URL。"""
        parsed = urlsplit(target_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"无效的 API 端点地址: {target_url}")

        path = parsed.path.rstrip("/")
        if not path:
            path = MESSAGES_PATH
        elif path.endswith("/v1"):
            path = f"{path}/messages"
        elif not path.endswith("/messages"):
            path = f"{path}{MESSAGES_PATH}"

        incoming = urlsplit(self.path)
        query_parts = [part for part in (parsed.query, incoming.query) if part]
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                path,
                "&".join(query_parts),
                parsed.fragment,
            )
        )

    def _build_upstream_headers(self, target: Dict[str, Any]) -> Dict[str, str]:
        """复制客户端端到端请求头，并替换 provider 认证信息。"""
        skip_headers = HOP_BY_HOP_HEADERS | {"host", "content-length"} | AUTH_HEADERS
        upstream_headers = {}

        for key, value in self.headers.items():
            if key.lower() in skip_headers:
                continue
            upstream_headers[key] = value

        if not any(key.lower() == "content-type" for key in upstream_headers):
            upstream_headers["Content-Type"] = "application/json"

        if not any(key.lower() == "anthropic-version" for key in upstream_headers):
            upstream_headers["anthropic-version"] = "2023-06-01"

        api_key = target.get("api_key", "")
        if api_key:
            # Anthropic 官方使用 x-api-key；许多兼容服务使用 Bearer。
            # 同时提供两个头，避免把 provider 的认证方式固化死。
            upstream_headers["x-api-key"] = api_key
            upstream_headers["Authorization"] = f"Bearer {api_key}"

        return upstream_headers

    def _forward_request(
        self, target_url: str, headers: Dict[str, str], body: bytes
    ) -> Tuple[int, list, bytes]:
        """转发请求到目标提供商。

        Returns:
            (status_code, response_headers, response_body)
        """
        connection = None
        try:
            connection, resp = self._open_upstream_response(target_url, headers, body)
            response_headers = resp.getheaders()
            response_body = resp.read()
            return resp.status, response_headers, response_body
        except (OSError, http.client.HTTPException, ValueError) as e:
            error_response = json.dumps({
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"无法连接到提供商: {str(e)}",
                },
            }).encode("utf-8")
            return 502, [("Content-Type", "application/json")], error_response
        except Exception as e:
            error_response = json.dumps({
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"代理服务器错误: {str(e)}",
                },
            }).encode("utf-8")
            return 500, [("Content-Type", "application/json")], error_response
        finally:
            if connection:
                connection.close()

    def _forward_streaming_request(
        self, target_url: str, headers: Dict[str, str], body: bytes
    ):
        """转发流式请求到目标提供商，逐块回传 SSE。"""
        headers_sent = False
        connection = None

        try:
            connection, resp = self._open_upstream_response(target_url, headers, body)

            if resp.status >= 400:
                response_body = resp.read()
                self.send_response(resp.status)
                self._copy_response_headers(
                    resp.getheaders(),
                    skip_content_length=True,
                )
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
                return

            response_headers = resp.getheaders()
            self.send_response(resp.status)
            sent_content_type = self._copy_response_headers(
                response_headers,
                skip_content_length=True,
            )
            if not sent_content_type:
                self.send_header("Content-Type", "text/event-stream")
            if not any(key.lower() == "cache-control" for key, _ in response_headers):
                self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            headers_sent = True

            while True:
                chunk = resp.readline()
                if not chunk:
                    break
                self._write_chunk(chunk)
            self._finish_chunked_response()

        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, http.client.HTTPException, ValueError) as e:
            try:
                if not headers_sent:
                    self._send_streaming_error_response(
                        502,
                        "api_error",
                        f"代理错误: {str(e)}",
                    )
                else:
                    self._write_chunk(
                        self._format_sse_event(
                            "error",
                            self._anthropic_error("api_error", f"代理错误: {str(e)}"),
                        )
                    )
                    self._finish_chunked_response()
            except Exception:
                pass
        finally:
            if connection:
                connection.close()

    def do_POST(self):  # noqa: N802
        """处理 POST 请求。"""
        request_path = urlsplit(self.path).path
        if request_path != MESSAGES_PATH:
            self._send_error_response(404, "not_found_error", f"未知的路径: {self.path}")
            return

        if not self.proxy_config:
            self._send_error_response(500, "internal_error", "代理配置未加载")
            return

        # 读取请求体
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_error_response(400, "invalid_request_error", "请求体为空")
            return

        body = self.rfile.read(content_length)

        # 解析请求体
        try:
            request_data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_error_response(400, "invalid_request_error", "请求体不是有效的 JSON")
            return

        # 获取模型名称
        model = request_data.get("model", "")
        if not model:
            self._send_error_response(400, "invalid_request_error", "缺少 model 字段")
            return

        # 查找目标提供商
        target = self.proxy_config.get_model_target(model)
        if not target:
            self._send_error_response(
                400,
                "invalid_request_error",
                f"未找到模型 '{model}' 的映射配置。请检查 proxy_config.json。"
            )
            return

        # 更新请求体中的 model 字段
        target_model = target.get("model", "")
        if not target_model:
            self._send_error_response(400, "invalid_request_error", "目标模型配置为空")
            return

        request_data["model"] = target_model
        new_body = json.dumps(
            request_data,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        try:
            target_url = self._build_target_url(target.get("base_url", ""))
        except ValueError as e:
            self._send_error_response(400, "invalid_request_error", str(e))
            return

        # 构建新的请求头：除 hop-by-hop / Host / 长度 / 客户端认证外尽量原样转发。
        new_headers = self._build_upstream_headers(target)

        # 检查是否是流式请求
        is_streaming = request_data.get("stream", False)

        if is_streaming:
            self._forward_streaming_request(target_url, new_headers, new_body)
        else:
            status, resp_headers, resp_body = self._forward_request(
                target_url, new_headers, new_body
            )
            self.send_response(status)
            self._copy_response_headers(
                resp_headers,
                skip_content_length=True,
            )
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)


class ProxyServer:
    """代理服务器管理器。"""

    def __init__(self, port: int):
        self.port = port
        self.httpd: Optional[ProxyHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

    def start(self, config: ProxyConfig, ready_file: Optional[Path] = None):
        """启动代理服务器。"""
        # 设置类变量
        ProxyHandler.proxy_config = config

        # 创建服务器
        self.httpd = ProxyHTTPServer(("localhost", self.port), ProxyHandler)
        self.port = self.httpd.server_address[1]
        if ready_file:
            ready_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_ready_file = ready_file.with_suffix(ready_file.suffix + ".tmp")
            tmp_ready_file.write_text(
                json.dumps({"pid": os.getpid(), "port": self.port}),
                "utf-8",
            )
            tmp_ready_file.replace(ready_file)

        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # 在独立线程中运行服务器
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()

        ssl_verify = config.ssl_verify
        ssl_status = "开启" if ssl_verify else "关闭"
        ca_bundle = (config.ssl_ca_bundle or "系统默认") if ssl_verify else "未使用"
        print(f"代理服务器已启动，监听端口: {self.port}", flush=True)
        print(f"上游 TLS 校验: {ssl_status}, CA: {ca_bundle}", flush=True)

    def _run_server(self):
        """运行服务器主循环。"""
        if self.httpd:
            self.httpd.serve_forever(poll_interval=0.5)

    def _signal_handler(self, signum, frame):
        """信号处理器，用于优雅关闭。"""
        self._shutdown_event.set()
        if self.httpd:
            self.httpd.shutdown()
        sys.exit(0)

    def stop(self):
        """停止代理服务器。"""
        self._shutdown_event.set()
        if self.httpd:
            self.httpd.shutdown()
        if self.server_thread:
            self.server_thread.join(timeout=2)
        if self.httpd:
            self.httpd.server_close()


def _cleanup_on_exit():
    """清理代理运行时文件（config 含明文 API key）。"""
    if not _cleanup_config_path:
        return
    try:
        if _cleanup_config_path.exists():
            _cleanup_config_path.unlink()
    except OSError:
        pass


atexit.register(_cleanup_on_exit)


def main():
    """主入口函数。"""
    parser = argparse.ArgumentParser(description="Claude Code 混合提供商代理服务器")
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="代理配置文件路径"
    )
    parser.add_argument(
        "--ready-file",
        type=Path,
        help="内部启动握手文件路径"
    )
    args = parser.parse_args()

    # 加载配置
    config = ProxyConfig(args.config)
    global _cleanup_config_path
    _cleanup_config_path = args.config
    port = config.port

    server = ProxyServer(port)
    server.start(config, args.ready_file)

    # 保持主线程运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
