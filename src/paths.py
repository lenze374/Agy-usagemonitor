#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-platform path configuration for Antigravity Usage Monitor.
- Runtime ledger, monitor logs & Sidecar state live in DATA_DIR (XDG / AppData),
  completely separated from plugin source files.
- Compatible with Python 3.9+ on macOS, Linux, and Windows (stdlib only).
"""

import os


def _default_data_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "agy-usage")
    xdg_data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(xdg_data, "agy-usage")


def _infer_plugin_dir():
    env_dir = os.environ.get("AGY_USAGE_PLUGIN_DIR")
    if env_dir:
        return os.path.expanduser(env_dir)
    # When deployed inside <plugin_dir>/sidecars/usage_monitor_daemon/, infer <plugin_dir>
    cand = os.path.dirname(os.path.dirname(SRC_DIR))
    if os.path.isfile(os.path.join(cand, "plugin.json")):
        return cand
    return os.path.expanduser("~/.gemini/config/plugins/usage-monitor")


SRC_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.expanduser(
    os.environ.get("AGY_USAGE_PROJECT_ROOT") or os.path.dirname(SRC_DIR)
)

DATA_DIR = os.path.expanduser(os.environ.get("AGY_USAGE_DATA_DIR") or _default_data_dir())
ACTIVE_DIR = os.path.join(DATA_DIR, "active")
LEDGER_PATH = os.path.join(DATA_DIR, "ledger.jsonl")
MONITOR_LOG = os.path.join(DATA_DIR, "monitor.jsonl")
SIDECAR_STATE_PATH = os.path.join(DATA_DIR, "sidecar_runtime.json")

AGY_DATA_ROOT = os.path.expanduser(
    os.environ.get("ANTIGRAVITY_EXECUTABLE_DATA_DIR") or "~/.gemini/antigravity"
)
BRAIN_DIR = os.path.expanduser(
    os.environ.get("AGY_BRAIN_DIR") or os.path.join(AGY_DATA_ROOT, "brain")
)

_preload_raw = [
    os.path.join(AGY_DATA_ROOT, "lib", "node_modules", "sidecar_sdk", "preload.js"),
    os.path.expanduser("~/.gemini/antigravity/lib/node_modules/sidecar_sdk/preload.js"),
]
PRELOAD_CANDIDATES = []
for _p in _preload_raw:
    _norm = os.path.normpath(_p)
    if _norm not in PRELOAD_CANDIDATES:
        PRELOAD_CANDIDATES.append(_norm)

PLUGIN_DIR = _infer_plugin_dir()
HOOKS_JSON_PATH = os.path.expanduser(
    os.environ.get("AGY_HOOKS_JSON_PATH") or os.path.join(PLUGIN_DIR, "hooks.json")
)
HOOK_KEY = "antigravity-quota-tracker"
HOOK_SCRIPT_PATH = os.path.join(SRC_DIR, "hook.py")
