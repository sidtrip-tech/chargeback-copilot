import cgi
import json
import mimetypes
import os
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from urllib.parse import urlparse

from chargeback_copilot.auth import CSRF_COOKIE, SESSION_COOKIE, new_csrf_token
from chargeback_copilot import api
from chargeback_copilot.observability import exception_summary, log_event, new_request_id, now_ms, safe_error_payload
from chargeback_copilot.scanning import UnsafeUpload
from chargeback_copilot.security import (
    OriginNotAllowed,
    PayloadTooLarge,
    RateLimitExceeded,
    check_json_body_size,
    check_origin,
    check_rate_limit,
)
from chargeback_copilot.uploads import MAX_UPLOAD_BYTES


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200, extra_headers=None):
        data = json.dumps(payload).encode("utf-8")
        self._last_response_status = status
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self._request_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text, status=200, content_type="text/plain", extra_headers=None):
        data = text.encode("utf-8")
        self._last_response_status = status
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self._request_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _send_binary(self, data, status=200, content_type="application/octet-stream", extra_headers=None):
        self._last_response_status = status
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self._request_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _request_id(self):
        if not hasattr(self, "request_id"):
            self.request_id = self.headers.get("X-Request-ID") or new_request_id()
        return self.request_id

    def _request_headers(self):
        self.send_header("X-Request-ID", self._request_id())

    def _log_request_started(self, method, path):
        self.request_started_at = now_ms()
        log_event(
            "request.started",
            request_id=self._request_id(),
            method=method,
            path=path,
            client_ip=self._client_key(),
        )

    def _log_request_completed(self, method, path, status):
        duration_ms = now_ms() - getattr(self, "request_started_at", now_ms())
        log_event(
            "request.completed",
            request_id=self._request_id(),
            method=method,
            path=path,
            status=status,
            duration_ms=duration_ms,
        )

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        check_json_body_size(length)
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _read_multipart(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES + 65536:
            raise PayloadTooLarge(f"Upload request is too large. File limit is {MAX_UPLOAD_BYTES} bytes.")
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": str(length),
            },
        )
        required = {"type", "title", "occurred_at", "summary", "file"}
        missing = [field for field in required if field not in form]
        if missing:
            raise ValueError(f"Missing upload fields: {', '.join(missing)}")
        fields = {
            key: form[key].value
            for key in ("type", "title", "source", "occurred_at", "summary", "relevance")
            if key in form
        }
        file_item = form["file"]
        file_data = file_item.file.read()
        return fields, {
            "filename": file_item.filename or "evidence-upload",
            "content_type": file_item.type or "application/octet-stream",
            "data": file_data,
        }

    def _handle_error(self, exc):
        if isinstance(exc, PermissionError):
            status = 401
        elif isinstance(exc, RateLimitExceeded):
            status = 429
        elif isinstance(exc, PayloadTooLarge):
            status = 413
        elif isinstance(exc, OriginNotAllowed):
            status = 403
        elif isinstance(exc, UnsafeUpload):
            status = 422
        else:
            status = 400
        log_event(
            "request.error",
            request_id=self._request_id(),
            status=status,
            path=urlparse(self.path).path,
            method=getattr(self, "command", ""),
            **exception_summary(exc),
        )
        self._send_json(safe_error_payload(exc, self._request_id()), status=status)

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )

    def _session_token(self):
        return self._cookie_value(SESSION_COOKIE)

    def _csrf_cookie(self):
        return self._cookie_value(CSRF_COOKIE)

    def _cookie_value(self, name):
        header = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        jar.load(header)
        morsel = jar.get(name)
        return morsel.value if morsel else ""

    def _current_user_id(self):
        return api.current_user(self._session_token())["id"]

    def _client_key(self):
        forwarded_for = self.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        return self.client_address[0]

    def _scheme(self):
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "")
        if forwarded_proto:
            return forwarded_proto.split(",", 1)[0].strip()
        return "https" if os.environ.get("APP_ENV") == "production" else "http"

    def _validate_origin(self):
        check_origin(self.headers.get("Origin", ""), self.headers.get("Host", ""), self._scheme())

    def _session_cookie_header(self, token):
        secure = "; Secure" if os.environ.get("APP_ENV") == "production" else ""
        return f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=1209600{secure}"

    def _csrf_cookie_header(self, token):
        secure = "; Secure" if os.environ.get("APP_ENV") == "production" else ""
        return f"{CSRF_COOKIE}={token}; SameSite=Lax; Path=/; Max-Age=1209600{secure}"

    def _clear_cookie_header(self):
        secure = "; Secure" if os.environ.get("APP_ENV") == "production" else ""
        return f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0{secure}"

    def _clear_csrf_cookie_header(self):
        secure = "; Secure" if os.environ.get("APP_ENV") == "production" else ""
        return f"{CSRF_COOKIE}=; SameSite=Lax; Path=/; Max-Age=0{secure}"

    def _send_auth_json(self, payload):
        csrf_token = new_csrf_token()
        headers = [
            ("Set-Cookie", self._session_cookie_header(payload["token"])),
            ("Set-Cookie", self._csrf_cookie_header(csrf_token)),
        ]
        self._send_json_with_headers(payload, headers)

    def _send_json_with_headers(self, payload, headers, status=200):
        data = json.dumps(payload).encode("utf-8")
        self._last_response_status = status
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self._request_headers()
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _validate_csrf(self, path):
        if path in {
            "/api/auth/demo",
            "/api/auth/signup",
            "/api/auth/login",
            "/api/auth/verify-email",
            "/api/auth/request-password-reset",
            "/api/auth/reset-password",
        }:
            return
        cookie_token = self._csrf_cookie()
        header_token = self.headers.get("X-CSRF-Token", "")
        if not cookie_token or not header_token or cookie_token != header_token:
            raise PermissionError("Invalid CSRF token.")

    def do_GET(self):
        path = urlparse(self.path).path
        self._log_request_started("GET", path)
        try:
            if path == "/api/health":
                self._send_json(api.health())
                return
            if path == "/api/readiness":
                self._send_json(api.readiness())
                return
            if path == "/api/jobs/run":
                self._send_json(api.run_jobs())
                return
            if path == "/api/auth/me":
                self._send_json({"user": api.current_user(self._session_token())})
                return
            if path == "/api/jobs":
                self._send_json(api.job_status(self._current_user_id()))
                return
            if path == "/api/account/export":
                self._send_json(api.export_account_data(self._current_user_id()))
                return
            if path == "/api/disputes":
                self._send_json(api.list_cases(self._current_user_id()))
                return
            if path == "/api/audit-logs":
                self._send_json(api.audit_log(self._current_user_id()))
                return
            if path.startswith("/api/evidence-files/") and path.endswith("/download"):
                file_id = path.split("/")[3]
                payload = api.download_evidence_file(file_id, self._current_user_id())
                file = payload["file"]
                filename = quote(file["original_filename"])
                self._send_binary(
                    payload["data"],
                    content_type=file["content_type"],
                    extra_headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
                )
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
        finally:
            self._log_request_completed("GET", path, getattr(self, "_last_response_status", 200))

    def do_DELETE(self):
        path = urlparse(self.path).path
        self._log_request_started("DELETE", path)
        try:
            self._validate_origin()
            self._validate_csrf(path)
            if path.startswith("/api/evidence-files/"):
                file_id = path.split("/")[3]
                self._send_json(api.delete_uploaded_evidence_file(file_id, self._current_user_id()))
                return
            self._send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._handle_error(exc)
        finally:
            self._log_request_completed("DELETE", path, getattr(self, "_last_response_status", 200))

    def do_POST(self):
        path = urlparse(self.path).path
        self._log_request_started("POST", path)
        try:
            self._validate_origin()
            self._validate_csrf(path)
            if path == "/api/auth/demo":
                body = self._read_json()
                check_rate_limit(self._client_key(), "auth")
                payload = api.demo_login()
                self._send_auth_json(payload)
                return
            if path == "/api/auth/signup":
                body = self._read_json()
                check_rate_limit(self._client_key(), "auth")
                payload = api.signup(body)
                self._send_auth_json(payload)
                return
            if path == "/api/auth/login":
                body = self._read_json()
                check_rate_limit(self._client_key(), "auth")
                payload = api.login(body)
                self._send_auth_json(payload)
                return
            if path == "/api/auth/logout":
                self._read_json()
                api.logout(self._session_token())
                self._send_json_with_headers(
                    {"ok": True},
                    [
                        ("Set-Cookie", self._clear_cookie_header()),
                        ("Set-Cookie", self._clear_csrf_cookie_header()),
                    ],
                )
                return
            if path == "/api/auth/request-email-verification":
                self._read_json()
                self._send_json(api.request_email_verification(self._current_user_id()))
                return
            if path == "/api/auth/test-email":
                self._read_json()
                self._send_json(api.send_account_test_email(self._current_user_id()))
                return
            if path == "/api/auth/verify-email":
                body = self._read_json()
                self._send_json(api.verify_email(body))
                return
            if path == "/api/auth/request-password-reset":
                body = self._read_json()
                check_rate_limit(self._client_key(), "auth")
                self._send_json(api.request_password_reset(body))
                return
            if path == "/api/auth/reset-password":
                body = self._read_json()
                check_rate_limit(self._client_key(), "auth")
                self._send_json(api.reset_password(body))
                return
            if path == "/api/account/delete":
                body = self._read_json()
                api.delete_account_data(self._current_user_id(), body)
                self._send_json_with_headers(
                    {"ok": True},
                    [
                        ("Set-Cookie", self._clear_cookie_header()),
                        ("Set-Cookie", self._clear_csrf_cookie_header()),
                    ],
                )
                return
            if path == "/api/disputes":
                body = self._read_json()
                self._send_json(api.create_dispute(body, self._current_user_id()))
                return
            if path.startswith("/api/disputes/") and path.endswith("/evidence-file"):
                dispute_id = path.split("/")[3]
                fields, file_payload = self._read_multipart()
                self._send_json(api.add_evidence_upload(dispute_id, fields, file_payload, self._current_user_id()))
                return
            if path.startswith("/api/disputes/") and path.endswith("/evidence"):
                dispute_id = path.split("/")[3]
                body = self._read_json()
                self._send_json(api.add_evidence(dispute_id, body, self._current_user_id()))
                return
            if path.startswith("/api/disputes/") and path.endswith("/generate"):
                dispute_id = path.split("/")[3]
                self._read_json()
                self._send_json(api.generate_packet(dispute_id, self._current_user_id()))
                return
            if path.startswith("/api/disputes/") and path.endswith("/outcome"):
                dispute_id = path.split("/")[3]
                body = self._read_json()
                self._send_json(api.save_outcome_feedback(dispute_id, body, self._current_user_id()))
                return
            self._send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._handle_error(exc)
        finally:
            self._log_request_completed("POST", path, getattr(self, "_last_response_status", 200))

    def _serve_static(self, path):
        target = FRONTEND / ("index.html" if path == "/" else path.lstrip("/"))
        if not target.exists() or not target.is_file():
            self._send_json({"error": "Not found"}, status=404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self._last_response_status = 200
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self._request_headers()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


def main():
    api.boot()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8010"))
    server = ThreadingHTTPServer((host, port), Handler)
    log_event("server.started", host=host, port=port)
    server.serve_forever()


if __name__ == "__main__":
    main()
