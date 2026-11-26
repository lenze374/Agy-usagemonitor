#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Sidecar daemon + Extensions Web UI server for Antigravity Usage Monitor.
- Queries local Language Server RPC (`RetrieveUserQuotaSummary` + `GetUserStatus`) directly.
- Runs a wall-clock-aware 60s monitor loop (`agy_monitor.run_tick()`) that recovers cleanly after sleep/wake.
- Hosts the Extensions auxiliary-pane Web UI on `ANTIGRAVITY_SIDECAR_WEB_PORT`
  with `ANTIGRAVITY_SIDECAR_UI_TOKEN` enforcement on POST endpoints.
- Compatible with Python 3.9+ across macOS, Linux, and Windows (stdlib only).
"""

import importlib
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SRC_DIR = os.path.dirname(os.path.realpath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import agy_monitor
import agy_usage
import common
import dashboard_data
import dashboard_ui
from paths import DATA_DIR, PRELOAD_CANDIDATES, SIDECAR_STATE_PATH

TICK_INTERVAL_SEC = 60.0
TRANSCRIPT_SYNC_INTERVAL_SEC = 600.0

_WEB_RELOAD_LOCK = threading.Lock()
_WEB_MTIMES = {}
_LAST_RELOAD_CHECK = 0.0
_BACKEND_RELOAD_CHAIN = ("common", "agy_monitor", "agy_usage", "dashboard_data")
_RELOAD_MODULES = {
    "common": common,
    "agy_monitor": agy_monitor,
    "agy_usage": agy_usage,
    "dashboard_data": dashboard_data,
    "dashboard_ui": dashboard_ui,
}


def _maybe_reload_web_modules(force=False):
    """Fail-open mtime-based hot-reload with upstream-to-downstream cascade."""
    global _LAST_RELOAD_CHECK
    now = time.time()
    if (not force) and (now - _LAST_RELOAD_CHECK) < 2.0:
        return
    with _WEB_RELOAD_LOCK:
        now = time.time()
        if (not force) and (now - _LAST_RELOAD_CHECK) < 2.0:
            return
        _LAST_RELOAD_CHECK = now

        dirty_idx = None
        current_mtimes = {}
        for idx, mod_name in enumerate(_BACKEND_RELOAD_CHAIN):
            mod_obj = _RELOAD_MODULES.get(mod_name)
            try:
                fpath = getattr(mod_obj, "__file__", None)
                if not fpath:
                    continue
                mt = os.stat(fpath).st_mtime
                current_mtimes[mod_name] = mt
                prev = _WEB_MTIMES.get(mod_name)
                if prev is None:
                    _WEB_MTIMES[mod_name] = mt
                elif mt > prev and dirty_idx is None:
                    dirty_idx = idx
            except Exception:
                continue

        if dirty_idx is not None:
            for mod_name in _BACKEND_RELOAD_CHAIN[dirty_idx:]:
                mod_obj = _RELOAD_MODULES.get(mod_name)
                if mod_obj is None:
                    continue
                try:
                    reloaded = importlib.reload(mod_obj)
                    _RELOAD_MODULES[mod_name] = reloaded
                    if mod_name in current_mtimes:
                        _WEB_MTIMES[mod_name] = current_mtimes[mod_name]
                    else:
                        fpath = getattr(reloaded, "__file__", None)
                        if fpath:
                            _WEB_MTIMES[mod_name] = os.stat(fpath).st_mtime
                except Exception:
                    continue

        try:
            ui_obj = _RELOAD_MODULES.get("dashboard_ui")
            fpath = getattr(ui_obj, "__file__", None)
            if fpath:
                mt = os.stat(fpath).st_mtime
                prev = _WEB_MTIMES.get("dashboard_ui")
                if prev is None:
                    _WEB_MTIMES["dashboard_ui"] = mt
                elif mt > prev:
                    _RELOAD_MODULES["dashboard_ui"] = importlib.reload(ui_obj)
                    _WEB_MTIMES["dashboard_ui"] = mt
        except Exception:
            pass


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class _DaemonState:
    def __init__(self):
        self.stop_event = threading.Event()
        self.last_tick_ts = 0.0
        self.last_tick_iso = ""
        self.last_transcript_sync_ts = 0.0
        self.port = 0
        self.ui_token = ""
        self.preload_js = b"// preload unavailable\n"


STATE = _DaemonState()


def _load_preload_js():
    for path in PRELOAD_CANDIDATES:
        if os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    return f.read()
            except OSError:
                continue
    return b"// preload unavailable\n"


class SidecarRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send_bytes(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, payload):
        body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self._send_bytes(code, body, "application/json; charset=utf-8")

    def _validate_token(self, parsed_url):
        if not STATE.ui_token:
            return True
        header_tok = self.headers.get("x-sidecar-token") or ""
        query_tok = (parse_qs(parsed_url.query).get("token") or [""])[0]
        return (header_tok or query_tok) == STATE.ui_token

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 1024 * 1024))
        if not raw:
            return {}
        try:
            obj = json.loads(raw.decode("utf-8", errors="replace"))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html", "/ui.html"):
            _maybe_reload_web_modules()
            self._send_bytes(200, dashboard_ui.DASHBOARD_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/preload.js":
            self._send_bytes(200, STATE.preload_js, "application/javascript; charset=utf-8")
            return
        if path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "pid": os.getpid(),
                    "port": STATE.port,
                    "lastTickIso": STATE.last_tick_iso,
                    "webUi": True,
                },
            )
            return
        if path == "/quota":
            snap = common.fetch_ls_quota(timeout_sec=4.0)
            if not snap:
                self._send_json(503, {"ok": False, "error": "ls_quota_unavailable"})
                return
            self._send_json(200, snap)
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._validate_token(parsed):
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        data = self._read_json_body()
        _maybe_reload_web_modules()
        try:
            if path == "/api/dashboard":
                window = str(data.get("window") or "24h")
                recent = int(data.get("recent") or 25)
                payload = dashboard_data.build_dashboard_payload(window=window, recent_n=recent, live=True)
                self._send_json(200, payload)
                return
            if path == "/api/action":
                action = str(data.get("action") or "")
                self._send_json(200, dashboard_data.perform_action(action, data))
                return
            self._send_json(404, {"ok": False, "error": "not_found"})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})


def _write_runtime_state(port, state_path=SIDECAR_STATE_PATH):
    os.makedirs(DATA_DIR, exist_ok=True)
    info = {
        "pid": os.getpid(),
        "port": int(port),
        "webUi": True,
        "startedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    common.atomic_write_text(state_path, json.dumps(info, indent=2, ensure_ascii=False) + "\n")


def _cleanup_runtime_state(state_path=SIDECAR_STATE_PATH):
    try:
        if not os.path.isfile(state_path):
            return
        with open(state_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        if int(info.get("pid") or 0) == os.getpid():
            os.unlink(state_path)
    except Exception:
        pass


def _ticker_loop():
    while not STATE.stop_event.is_set():
        now = time.time()
        if STATE.last_tick_ts <= 0.0 or (now - STATE.last_tick_ts) >= TICK_INTERVAL_SEC:
            try:
                rec = agy_monitor.run_tick()
                STATE.last_tick_ts = time.time()
                STATE.last_tick_iso = str((rec or {}).get("iso") or "")
            except Exception:
                STATE.last_tick_ts = time.time()
        if (
            STATE.last_transcript_sync_ts <= 0.0
            or (now - STATE.last_transcript_sync_ts) >= TRANSCRIPT_SYNC_INTERVAL_SEC
        ):
            try:
                agy_usage.sync_untracked_transcripts()
            except Exception:
                pass
            STATE.last_transcript_sync_ts = time.time()
        STATE.stop_event.wait(2.0)


def main():
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)

    STATE.ui_token = (os.environ.get("ANTIGRAVITY_SIDECAR_UI_TOKEN") or "").strip()
    STATE.preload_js = _load_preload_js()

    port_env = (os.environ.get("ANTIGRAVITY_SIDECAR_WEB_PORT") or "").strip()
    bind_port = int(port_env) if port_env.isdigit() else 0

    server = ReusableThreadingHTTPServer(("127.0.0.1", bind_port), SidecarRequestHandler)
    STATE.port = int(server.server_address[1])
    _write_runtime_state(STATE.port)

    try:
        sys.stdout.write(f"[sidecar] listening on 127.0.0.1:{STATE.port}\n")
        sys.stdout.flush()
    except OSError:
        pass

    def _handle_stop(signum, frame):
        STATE.stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _handle_stop)
            except Exception:
                pass

    worker = threading.Thread(target=_ticker_loop, name="agy-monitor-ticker", daemon=True)
    worker.start()

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        STATE.stop_event.set()
        try:
            server.server_close()
        except Exception:
            pass
        _cleanup_runtime_state()


if __name__ == "__main__":
    main()
