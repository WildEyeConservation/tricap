#!/usr/bin/env python3
"""Temporary port-80 forwarder for the Flask application."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEFAULT_FLASK_HOST = "127.0.0.1"
DEFAULT_FLASK_PORT = 5000
PROXY_TIMEOUT_SECONDS = 20
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


class Handler(BaseHTTPRequestHandler):
    server_version = "SkySeekerForwarder/2.0"

    def log_message(self, _format, *_args):
        return

    def _request_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else None

    def _client_ip(self):
        return self.client_address[0]

    def _send_error(self, detail):
        payload = json.dumps({
            "msg": "Flask is not reachable",
            "detail": str(detail),
        }).encode("utf-8")
        self.send_response(502)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _proxy(self):
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        headers.update({
            "Host": f"{self.server.flask_host}:{self.server.flask_port}",
            "X-Forwarded-Host": self.headers.get("Host", "control.skyseeker"),
            "X-Forwarded-Proto": "http",
            "X-SkySeeker-Client-IP": self._client_ip(),
        })
        connection = http.client.HTTPConnection(
            self.server.flask_host,
            self.server.flask_port,
            timeout=PROXY_TIMEOUT_SECONDS,
        )
        try:
            connection.request(
                self.command,
                self.path,
                body=self._request_body(),
                headers=headers,
            )
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                while chunk := response.read(64 * 1024):
                    self.wfile.write(chunk)
        except (ConnectionError, OSError, TimeoutError, socket.timeout) as error:
            self._send_error(error)
        finally:
            connection.close()

    do_GET = _proxy
    do_HEAD = _proxy
    do_POST = _proxy


class PortalServer(ThreadingHTTPServer):
    request_queue_size = 50
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, handler, flask_host, flask_port):
        super().__init__(address, handler)
        self.flask_host = flask_host
        self.flask_port = flask_port


def main():
    parser = argparse.ArgumentParser(description="Forward port 80 to SkySeeker Flask")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--tricap-host", dest="flask_host", default=DEFAULT_FLASK_HOST)
    parser.add_argument("--tricap-port", dest="flask_port", type=int, default=DEFAULT_FLASK_PORT)
    args = parser.parse_args()
    server = PortalServer(
        (args.host, args.port),
        Handler,
        args.flask_host,
        args.flask_port,
    )
    print(
        "SkySeeker forwarding http://%s:%d to Flask at http://%s:%d"
        % (args.host, args.port, args.flask_host, args.flask_port)
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
