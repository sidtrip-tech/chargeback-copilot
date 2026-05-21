import json
import mimetypes
import os
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from chargeback_copilot.auth import SESSION_COOKIE
from chargeback_copilot import api


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200, extra_headers=None):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text, status=200, content_type="text/plain", extra_headers=None):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle_error(self, exc):
        status = 401 if isinstance(exc, PermissionError) else 400
        self._send_json({"error": str(exc)}, status=status)

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")

    def _session_token(self):
        header = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        jar.load(header)
        morsel = jar.get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def _current_user_id(self):
        return api.current_user(self._session_token())["id"]

    def _session_cookie_header(self, token):
        return f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=1209600"

    def _clear_cookie_header(self):
        return f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self._send_json(api.health())
                return
            if path == "/api/auth/me":
                self._send_json({"user": api.current_user(self._session_token())})
                return
            if path == "/api/disputes":
                self._send_json(api.list_cases(self._current_user_id()))
                return
            if path == "/api/audit-logs":
                self._send_json(api.audit_log(self._current_user_id()))
                return
            if path.startswith("/api/disputes/") and path.endswith("/export"):
                dispute_id = path.split("/")[3]
                self._send_text(api.export_packet(dispute_id, self._current_user_id()), content_type="text/html")
                return
            if path.startswith("/api/disputes/"):
                dispute_id = path.split("/")[3]
                self._send_json(api.detail(dispute_id, self._current_user_id()))
                return
            self._serve_static(path)
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/auth/demo":
                payload = api.demo_login()
                self._send_json(payload, extra_headers={"Set-Cookie": self._session_cookie_header(payload["token"])})
                return
            if path == "/api/auth/logout":
                api.logout(self._session_token())
                self._send_json({"ok": True}, extra_headers={"Set-Cookie": self._clear_cookie_header()})
                return
            if path == "/api/disputes":
                self._send_json(api.create_dispute(body, self._current_user_id()))
                return
            if path.startswith("/api/disputes/") and path.endswith("/evidence"):
                dispute_id = path.split("/")[3]
                self._send_json(api.add_evidence(dispute_id, body, self._current_user_id()))
                return
            if path.startswith("/api/disputes/") and path.endswith("/generate"):
                dispute_id = path.split("/")[3]
                self._send_json(api.generate_packet(dispute_id, self._current_user_id()))
                return
            if path.startswith("/api/disputes/") and path.endswith("/outcome"):
                dispute_id = path.split("/")[3]
                self._send_json(api.save_outcome_feedback(dispute_id, body, self._current_user_id()))
                return
            self._send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._handle_error(exc)

    def _serve_static(self, path):
        target = FRONTEND / ("index.html" if path == "/" else path.lstrip("/"))
        if not target.exists() or not target.is_file():
            self._send_json({"error": "Not found"}, status=404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    api.boot()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8010"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Chargeback Copilot running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
