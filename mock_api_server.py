#!/usr/bin/env python3
# coding: utf-8

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

API_PATH = "/v1/chat/completion"
CONTROL_PATH = "/control"
MODE_API_PATH = "/mock/mode"

DEFAULT_TOKEN = "aeris-local-mock-token"


class ServerState:
    def __init__(self):
        self._lock = threading.Lock()
        self._xml_mode = False

    def set_xml_mode(self, enabled):
        with self._lock:
            self._xml_mode = bool(enabled)

    def get_xml_mode(self):
        with self._lock:
            return self._xml_mode


STATE = ServerState()


def normalize_model_name(raw):
    value = (raw or "").strip()
    if not value:
        return "deepseek-r1:70b"

    # Supports accidental pasted list separated by tab/newline/comma/semicolon/pipe/backslash
    parts = []
    for chunk in value.replace("\\", "\n").splitlines():
        for item in chunk.replace("\t", "\n").replace(",", "\n").replace(";", "\n").replace("|", "\n").splitlines():
            cleaned = item.strip()
            if cleaned:
                parts.append(cleaned)

    return parts[0] if parts else "deepseek-r1:70b"


def build_xml_reply():
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<requirements>\n"
        "  <requirement id=\"Sr_1\" name=\"发动机总体指标\" text=\"\">\n"
        "    <requirement id=\"Sr_1.1\" name=\"性能需求\" text=\"\">\n"
        "      <requirement id=\"Sr_1.1.1\" name=\"真空推力\" text=\"设计数值为1200，单位kN，额定工况下测得。\" />\n"
        "    </requirement>\n"
        "  </requirement>\n"
        "</requirements>"
    )


def build_chat_completion_response(model, content):
    now_ts = int(time.time())
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "model": model,
        "object": "chat.completion",
        "created": now_ts,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_token": 4,
            "completion_tokens": 16,
            "total_tokens": 20,
        },
    }


class MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code, html_text):
        body = html_text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _is_authorized(self):
        auth = self.headers.get("Authorization", "").strip()
        if not auth.lower().startswith("bearer "):
            return False
        token = auth[7:].strip()
        return token == self.server.token

    def _control_html(self):
        xml_mode = STATE.get_xml_mode()
        status = "true (XML)" if xml_mode else "false (normal greeting)"
        checked_true = "checked" if xml_mode else ""
        checked_false = "checked" if not xml_mode else ""
        return f"""
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Mock API Control</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; }}
    .card {{ max-width: 640px; border: 1px solid #ddd; border-radius: 8px; padding: 16px; }}
    .row {{ margin: 12px 0; }}
    .btn {{ background: #0078d7; color: #fff; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; }}
    code {{ background: #f6f8fa; padding: 2px 6px; border-radius: 4px; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h2>Mock API Control Panel</h2>
    <div class=\"row\">Current mode: <b>{status}</b></div>
    <form method=\"post\" action=\"{CONTROL_PATH}\">
      <div class=\"row\">
        <label><input type=\"radio\" name=\"xml_mode\" value=\"true\" {checked_true}> true (return XML content)</label><br>
        <label><input type=\"radio\" name=\"xml_mode\" value=\"false\" {checked_false}> false (return greeting)</label>
      </div>
      <button class=\"btn\" type=\"submit\">Apply</button>
    </form>
    <hr>
    <div class=\"row\">API endpoint: <code>{API_PATH}</code></div>
    <div class=\"row\">Token: <code>Authorization: Bearer {self.server.token}</code></div>
  </div>
</body>
</html>
"""

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", CONTROL_PATH):
            self._send_html(200, self._control_html())
            return

        if path == MODE_API_PATH:
            self._send_json(200, {"xml_mode": STATE.get_xml_mode()})
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == CONTROL_PATH:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            form = parse_qs(body)
            xml_mode_value = (form.get("xml_mode", ["false"])[0] or "false").lower()
            STATE.set_xml_mode(xml_mode_value == "true")
            self._send_html(200, self._control_html())
            return

        if path == MODE_API_PATH:
            payload = self._read_json_body()
            if payload is None:
                self._send_json(400, {"error": "invalid json"})
                return
            STATE.set_xml_mode(bool(payload.get("xml_mode", False)))
            self._send_json(200, {"xml_mode": STATE.get_xml_mode()})
            return

        if path != API_PATH:
            self._send_json(404, {"error": "not found"})
            return

        if not self._is_authorized():
            self._send_json(401, {"error": "unauthorized: expected Authorization: Bearer <token>"})
            return

        payload = self._read_json_body()
        if payload is None:
            self._send_json(400, {"error": "invalid json body"})
            return

        model_name = normalize_model_name(payload.get("model"))
        xml_mode = STATE.get_xml_mode()

        if xml_mode:
            content = build_xml_reply()
        else:
            content = "<think>debug(if have)</think>\n\nHello! How can I assist you today?"

        response = build_chat_completion_response(model_name, content)
        self._send_json(200, response)

    def log_message(self, fmt, *args):
        print("[MOCK]", fmt % args)


class MockServer(ThreadingHTTPServer):
    def __init__(self, server_address, token):
        super().__init__(server_address, MockHandler)
        self.token = token


def main():
    parser = argparse.ArgumentParser(description="Mock chat completion server for internal API testing")
    parser.add_argument("--host", default="0.0.0.0", help="bind host, default: 0.0.0.0")
    parser.add_argument("--port", type=int, default=7870, help="bind port, default: 7870")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Bearer token expected by server")
    parser.add_argument("--xml-mode", action="store_true", help="start with xml mode enabled")
    args = parser.parse_args()

    STATE.set_xml_mode(args.xml_mode)
    server = MockServer((args.host, args.port), token=args.token)

    print("=" * 68)
    print("Mock API server started")
    print(f"Base URL: http://{args.host}:{args.port}{API_PATH}")
    print(f"Control panel: http://{args.host}:{args.port}{CONTROL_PATH}")
    print(f"Expected Authorization: Bearer {args.token}")
    print(f"Initial xml_mode: {STATE.get_xml_mode()}")
    print("=" * 68)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping mock server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
