"""Optional read-only localhost UI — stdlib HTTP server, no extra dependencies."""

from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any

from world_cup_bot.config import Settings
from world_cup_bot.shadow_checklist import ready_payload
from world_cup_bot.ui_data import (
    advisor_context_payload,
    calendar_payload,
    conviction_summary_payload,
    markets_payload,
    meta_payload,
    plan_payload,
    pnl_payload,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"


def _index_bytes() -> bytes:
    if _INDEX_HTML.is_file():
        return _INDEX_HTML.read_bytes()
    # Installed wheel fallback
    try:
        ref = resources.files("world_cup_bot").joinpath("static/index.html")
        return ref.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, TypeError):
        return b"<html><body><h1>UI static files missing</h1></body></html>"


class UiHandler(BaseHTTPRequestHandler):
    settings_factory: Callable[[], Settings] = staticmethod(Settings.from_env)  # type: ignore[assignment]

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[ui] {self.log_date_time_string()} {fmt % args}\n")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_api(self, path: str) -> None:
        settings = self.settings_factory()
        try:
            if path == "/api/health":
                self._send_json(200, {"ok": True, "read_only": True})
                return
            if path == "/api/meta":
                self._send_json(200, meta_payload(settings))
                return
            if path == "/api/markets":
                self._send_json(200, markets_payload(settings))
                return
            if path == "/api/plan":
                self._send_json(200, plan_payload(settings))
                return
            if path == "/api/calendar":
                self._send_json(200, calendar_payload(settings))
                return
            if path == "/api/pnl":
                self._send_json(200, pnl_payload(settings))
                return
            if path == "/api/advisor/context":
                self._send_json(200, advisor_context_payload(settings))
                return
            if path == "/api/ready":
                self._send_json(200, ready_payload(settings, test_auth=False))
                return
            if path == "/api/conviction/summary":
                self._send_json(200, conviction_summary_payload(settings))
                return
            self._send_json(404, {"error": "not_found", "path": path})
        except Exception as exc:
            hint = "Gamma/network unreachable? Check connection or try CLI: world-cup-bot scan"
            if "403" in str(exc) and "Forbidden" in str(exc):
                hint = (
                    "HTTP 403 from Gamma is usually Cloudflare blocking bare Python clients — "
                    "upgrade to latest world-cup-bot (User-Agent fix). "
                    "US IP blocks order POST, not public Gamma reads."
                )
            if "No such file" in str(exc) or "not found" in str(exc).lower():
                hint = (
                    "Config file missing — pip install -e . from the world-cup-bot repo, "
                    "or set CONVICTION_CONFIG / LOGIC_VERSION_CONFIG to absolute paths."
                )
            self._send_json(
                502,
                {
                    "error": "upstream_failed",
                    "detail": str(exc),
                    "hint": hint,
                    "trace": traceback.format_exc(limit=3),
                },
            )

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in {"/", "/index.html"}:
            self._send_html(_index_bytes())
            return
        if path.startswith("/api/"):
            self._handle_api(path)
            return
        self._send_json(404, {"error": "not_found", "path": path})

    def do_POST(self) -> None:
        self._send_json(405, {"error": "method_not_allowed", "hint": "UI is read-only"})


def run_ui_server(*, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        sys.stderr.write(
            f"warning: binding to {host} exposes read-only API on your LAN — prefer 127.0.0.1\n"
        )
    server = ThreadingHTTPServer((host, port), UiHandler)
    display_host = "localhost" if host in {"127.0.0.1", "::1"} else host
    url = f"http://{display_host}:{port}/"
    sys.stderr.write(f"World Cup Bot UI (read-only) → {url}\n")
    sys.stderr.write("Ctrl+C to stop. No orders are posted from the UI.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nUI stopped.\n")
    finally:
        server.server_close()
