import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from chargeback_copilot import api


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text, status=200, content_type="text/plain"):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle_error(self, exc):
        self._send_json({"error": str(exc)}, status=400)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/disputes":
                self._send_json(api.list_cases())
                return
            if path.startswith("/api/disputes/") and path.endswith("/export"):
                dispute_id = path.split("/")[3]
                self._send_text(api.export_packet(dispute_id), content_type="text/html")
                return
            if path.startswith("/api/disputes/"):
                dispute_id = path.split("/")[3]
                self._send_json(api.detail(dispute_id))
                return
            self._serve_static(path)
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/disputes":
                self._send_json(api.create_dispute(body))
                return
            if path.startswith("/api/disputes/") and path.endswith("/evidence"):
                dispute_id = path.split("/")[3]
                self._send_json(api.add_evidence(dispute_id, body))
                return
            if path.startswith("/api/disputes/") and path.endswith("/generate"):
                dispute_id = path.split("/")[3]
                self._send_json(api.generate_packet(dispute_id))
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
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    api.boot()
    server = ThreadingHTTPServer(("127.0.0.1", 8010), Handler)
    print("Chargeback Copilot running at http://127.0.0.1:8010")
    server.serve_forever()


if __name__ == "__main__":
    main()

