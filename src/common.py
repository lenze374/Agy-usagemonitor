#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared formatting, timestamp parsing, cross-platform process & LS RPC quota helpers."""

import ctypes
import json
import os
import re
import time
import unicodedata
import urllib.request
from datetime import datetime

from paths import SIDECAR_STATE_PATH

CANONICAL_POOL_ORDER = (
    "gemini_5h",
    "gemini_weekly",
    "gemini_argon_5h",
    "gemini_argon_weekly",
    "claude_gpt_5h",
    "claude_gpt_weekly",
)


def disp_width(s):
    """Display column width accounting for East Asian wide characters."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in str(s))


def pad_r(s, width):
    """Right-pad string to target display column width."""
    s = str(s)
    return s + " " * max(0, width - disp_width(s))


def pad_l(s, width):
    """Left-pad string to target display column width."""
    s = str(s)
    return " " * max(0, width - disp_width(s)) + s


def parse_iso_epoch(iso_str):
    """Parse ISO-8601 timestamp to Unix epoch seconds (Python 3.9+ compatible)."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    s = iso_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "." in s:
        tz_pos = max(s.rfind("+"), s.rfind("-", 10))
        if tz_pos > 0:
            main, tz = s[:tz_pos], s[tz_pos:]
        else:
            main, tz = s, ""
        head, frac = main.split(".", 1)
        frac = (frac + "000000")[:6]
        s = f"{head}.{frac}{tz}"
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def parse_local_naive(iso_str):
    """Parse ISO-8601 timestamp into local naive datetime."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    s = iso_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "." in s:
        tz_pos = max(s.rfind("+"), s.rfind("-", 10))
        if tz_pos > 0:
            main, tz = s[:tz_pos], s[tz_pos:]
        else:
            main, tz = s, ""
        head, frac = main.split(".", 1)
        frac = (frac + "000000")[:6]
        s = f"{head}.{frac}{tz}"
    try:
        return datetime.fromisoformat(s).astimezone().replace(tzinfo=None)
    except Exception:
        return None


def is_pid_alive(pid):
    """Cross-platform check whether process ID is alive."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False

    if os.name == "nt":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = None
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            code = ctypes.c_ulong(0)
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok and code.value == STILL_ACTIVE)
        except Exception:
            return False
        finally:
            if handle:
                try:
                    ctypes.windll.kernel32.CloseHandle(handle)
                except Exception:
                    pass

    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _extract_fraction(bucket):
    """Extract remainingFraction in [0.0, 1.0] from canonical or nested adapter fields."""
    if not isinstance(bucket, dict):
        return None
    raw = bucket.get("remainingFraction")
    if raw is None and isinstance(bucket.get("remaining"), dict):
        raw = bucket["remaining"].get("remainingFraction")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val:  # NaN
        return None
    return max(0.0, min(1.0, val))


def _classify_bucket(bucket_id, group_label="", explicit_window=None):
    """Map raw Antigravity bucketId into canonical key, family, and cadence."""
    bid = str(bucket_id or "").strip()
    low = bid.lower()
    grp_low = str(group_label or "").lower()

    cadence = ""
    if explicit_window in ("5h", "weekly"):
        cadence = explicit_window
    elif low.endswith("-5h") or low.endswith("_5h") or "-5h" in low:
        cadence = "5h"
    elif low.endswith("-weekly") or low.endswith("_weekly") or "weekly" in low:
        cadence = "weekly"
    else:
        cadence = "other"

    if "argon" in low or "argon" in grp_low:
        family = "argon"
        if cadence == "weekly":
            key = "gemini_argon_weekly"
        elif cadence == "5h":
            key = "gemini_argon_5h"
        else:
            key = re.sub(r"[^a-z0-9]+", "_", low).strip("_") or "gemini_argon"
        return key, family, cadence

    if "gemini-5h" in low or low == "gemini_5h":
        return "gemini_5h", "gemini", "5h"
    if "gemini-weekly" in low or low == "gemini_weekly":
        return "gemini_weekly", "gemini", "weekly"
    if "3p-5h" in low or low == "claude_gpt_5h":
        return "claude_gpt_5h", "claude_gpt", "5h"
    if "3p-weekly" in low or low == "claude_gpt_weekly":
        return "claude_gpt_weekly", "claude_gpt", "weekly"

    if "3p" in low or "claude" in low or "gpt" in low or "claude" in grp_low:
        family = "claude_gpt"
    elif "gemini" in low or "gemini" in grp_low or "carbon" in low or "neon" in low or "hydrogen" in low:
        family = "gemini"
    else:
        family = re.sub(r"[^a-z0-9]+", "_", grp_low or low).strip("_") or "other"

    clean_key = re.sub(r"[^a-z0-9]+", "_", low).strip("_") or f"{family}_{cadence}"
    return clean_key, family, cadence


def _order_pool_keys(pool_keys):
    seen = set()
    ordered = []
    for k in CANONICAL_POOL_ORDER:
        if k in pool_keys and k not in seen:
            ordered.append(k)
            seen.add(k)
    for k in sorted(pool_keys):
        if k not in seen:
            ordered.append(k)
            seen.add(k)
    return ordered


def _parse_ls_quota_response(data):
    """
    Normalize RetrieveUserQuotaSummary JSON into dynamic multi-subscription pools.
    Preserves canonical 4-pool keys plus Argon and any extra quota buckets returned by LS.
    """
    if not isinstance(data, dict):
        return None
    resp = data.get("response") if isinstance(data.get("response"), dict) else data
    groups = resp.get("groups")
    if not isinstance(groups, list):
        return None

    pools = {}
    for grp in groups:
        if not isinstance(grp, dict):
            continue
        grp_label = str(grp.get("displayName") or grp.get("name") or grp.get("id") or "")
        for b in grp.get("buckets") or []:
            if not isinstance(b, dict):
                continue
            bid = str(b.get("bucketId") or "")
            rem = _extract_fraction(b)
            if not bid or rem is None:
                continue
            key, family, cadence = _classify_bucket(bid, grp_label, b.get("window"))
            used_pct = round(max(0.0, min(100.0, (1.0 - rem) * 100.0)), 6)
            rem_pct = round(max(0.0, min(100.0, rem * 100.0)), 6)
            pools[key] = {
                "bucketId": bid,
                "groupLabel": grp_label,
                "family": family,
                "cadence": cadence,
                "usedPercent": used_pct,
                "remainingPercent": rem_pct,
                "resetsAt": str(b.get("resetTime") or ""),
                "description": str(b.get("description") or ""),
                "disabled": bool(b.get("disabled") is True),
            }

    return {
        "source": "ls_rpc",
        "billingMode": "subscription" if pools else "unknown",
        "plan": "",
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pools": pools,
        "poolOrder": _order_pool_keys(pools.keys()),
    }


def _ls_post_json(addr, csrf, method, body_bytes, timeout_sec):
    url = f"http://{addr}/exa.language_server_pb.LanguageServerService/{method}"
    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "x-codeium-csrf-token": csrf,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        if resp.status != 200:
            return None
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def fetch_ls_quota(ls_addr=None, csrf_token=None, timeout_sec=4.0, force_refresh=True):
    """Query local Antigravity Language Server RPC RetrieveUserQuotaSummary (+ GetUserStatus if empty)."""
    addr = ls_addr or os.environ.get("ANTIGRAVITY_LS_ADDRESS")
    csrf = csrf_token or os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    if not addr or not csrf:
        return None
    attempts = (
        [(b'{"forceRefresh":true}', timeout_sec), (b"{}", min(1.0, timeout_sec))]
        if force_refresh
        else [(b"{}", timeout_sec)]
    )
    empty_parsed = None
    for body, req_timeout in attempts:
        try:
            payload = _ls_post_json(addr, csrf, "RetrieveUserQuotaSummary", body, req_timeout)
            parsed = _parse_ls_quota_response(payload)
            if parsed and parsed.get("pools"):
                return parsed
            if parsed is not None:
                empty_parsed = parsed
        except Exception:
            continue

    if empty_parsed is not None:
        try:
            st_payload = _ls_post_json(addr, csrf, "GetUserStatus", b"{}", min(2.0, timeout_sec))
            if isinstance(st_payload, dict):
                tier_id = (
                    ((st_payload.get("userStatus") or {}).get("userTier") or {}).get("id") or ""
                )
                if tier_id == "agy-business-paygo-tier":
                    empty_parsed["billingMode"] = "paygo"
                    empty_parsed["plan"] = str(tier_id)
                elif tier_id:
                    empty_parsed["plan"] = str(tier_id)
        except Exception:
            pass
        return empty_parsed
    return None


def read_sidecar_state(state_path=SIDECAR_STATE_PATH):
    """Return active sidecar runtime info dict if its PID is alive, else None."""
    if not os.path.isfile(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        pid = int(info.get("pid") or 0)
        port = int(info.get("port") or 0)
        if pid <= 0 or port <= 0:
            return None
        if not is_pid_alive(pid):
            return None
        return info
    except Exception:
        return None


def fetch_sidecar_quota(timeout_sec=2.5, state_path=SIDECAR_STATE_PATH):
    """Fetch live quota from the local UsageMonitor sidecar HTTP bridge."""
    info = read_sidecar_state(state_path=state_path)
    if not info:
        return None
    url = f"http://127.0.0.1:{int(info['port'])}/quota"
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        if isinstance(data, dict) and (
            (isinstance(data.get("pools"), dict) and data["pools"])
            or data.get("billingMode") == "paygo"
        ):
            return data
    except Exception:
        return None
    return None


def fetch_quota_best(timeout_sec=4.0):
    """
    Resolve live Antigravity quota with minimal latency and zero external dependency:
      1. Direct local LS RPC (when ANTIGRAVITY_LS_ADDRESS + CSRF are in env)
      2. Local UsageMonitor sidecar HTTP bridge (http://127.0.0.1:<port>/quota)
    Returns (snap_dict_or_None, elapsed_ms).
    """
    t0 = time.time()
    for fn in (
        lambda: fetch_ls_quota(timeout_sec=min(4.0, timeout_sec)),
        lambda: fetch_sidecar_quota(timeout_sec=min(4.5, timeout_sec)),
    ):
        snap = fn()
        if snap and (snap.get("pools") or snap.get("billingMode") == "paygo"):
            return snap, int(round((time.time() - t0) * 1000))
    return None, int(round((time.time() - t0) * 1000))


def atomic_write_text(path, content):
    """Atomically write UTF-8 text via a temporary sibling file and os.replace."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp_path = os.path.join(parent, f".{os.path.basename(path)}.tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise
