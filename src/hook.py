#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Local Quota & Token Delta Hook (Fail-open, Event-driven).
Records both shared-pool quota deltas (via LS RPC / Sidecar bridge) and exact local
per-step token usage strictly between PreInvocation (turn start) and Stop (turn end).
Zero third-party dependencies; compatible with macOS, Linux, and Windows.
"""

import json
import os
import sys
import time
from datetime import datetime

SRC_DIR = os.path.dirname(os.path.realpath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from common import fetch_quota_best, parse_iso_epoch
from paths import ACTIVE_DIR, BRAIN_DIR, DATA_DIR, LEDGER_PATH

# Turns longer than 15 minutes with >5 min avg step likely involved sleep / hibernate
LONG_GAP_SECONDS = 900
# Orphaned active state older than 45 minutes is refreshed on next PreInvocation
STALE_ACTIVE_SECONDS = 2700


def prefer_compact_transcript(path):
    """Prefer compact transcript.jsonl over untruncated transcript_full.jsonl for faster scanning."""
    if not path:
        return ""
    if path.endswith("transcript_full.jsonl"):
        compact = path[: -len("transcript_full.jsonl")] + "transcript.jsonl"
        if os.path.isfile(compact):
            return compact
    return path


def resolve_transcript_path(payload, conv_id):
    """Locate local compact transcript.jsonl for this conversation."""
    candidates = []
    tp = payload.get("transcriptPath")
    if tp:
        tp_exp = os.path.expanduser(str(tp))
        if tp_exp.endswith("transcript_full.jsonl"):
            candidates.append(tp_exp[: -len("transcript_full.jsonl")] + "transcript.jsonl")
        candidates.append(tp_exp)
    adp = payload.get("artifactDirectoryPath")
    if adp:
        candidates.append(
            os.path.join(os.path.expanduser(str(adp)), ".system_generated", "logs", "transcript.jsonl")
        )
    if conv_id and conv_id != "default":
        candidates.append(
            os.path.join(BRAIN_DIR, conv_id, ".system_generated", "logs", "transcript.jsonl")
        )
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return candidates[0] if candidates else ""


def get_transcript_max_step(path):
    """Return highest step_index currently present in transcript.jsonl, or -1 if absent/empty."""
    if not path or not os.path.isfile(path):
        return -1
    max_step = -1
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and obj.get("step_index") is not None:
                        idx = int(obj["step_index"])
                        if idx > max_step:
                            max_step = idx
                except Exception:
                    continue
    except Exception:
        return -1
    return max_step


def collect_turn_tokens(path, start_step_index=None, start_ts=None, end_ts=None):
    """Collect exact server-reported token counts across all billed steps in this turn."""
    empty = {
        "input": 0,
        "cacheRead": 0,
        "output": 0,
        "total": 0,
        "billedSteps": 0,
        "compactions": 0,
        "stepStart": None,
        "stepEnd": None,
        "models": [],
        "searchWebCalls": 0,
        "errorSteps": 0,
        "subagentCalls": 0,
    }
    if not path or not os.path.isfile(path):
        return empty, []

    use_step_idx = start_step_index is not None
    min_step = int(start_step_index) if use_step_idx else -1
    min_epoch = (float(start_ts) - 2.5) if start_ts is not None else None
    max_epoch = (float(end_ts) + 2.5) if end_ts is not None else None

    token_steps = []
    seen_steps = set()
    search_web_calls = 0
    error_steps = 0
    subagent_calls = 0

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue

                step_idx = obj.get("step_index")
                if step_idx is None:
                    continue
                step_idx = int(step_idx)
                if step_idx in seen_steps:
                    continue

                if use_step_idx:
                    if step_idx <= min_step:
                        continue
                else:
                    c_epoch = parse_iso_epoch(obj.get("created_at"))
                    if c_epoch is None:
                        continue
                    if min_epoch is not None and c_epoch < min_epoch:
                        continue
                    if max_epoch is not None and c_epoch > max_epoch:
                        continue

                seen_steps.add(step_idx)

                if str(obj.get("status") or "").upper() == "ERROR" or bool(obj.get("error")):
                    error_steps += 1
                for tc in obj.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    tname = str(tc.get("name") or tc.get("tool") or "").strip().lower()
                    if tname == "search_web":
                        search_web_calls += 1
                    elif tname == "invoke_subagent":
                        subagent_calls += 1

                in_t = int(obj.get("input_tokens") or 0)
                cr_t = int(obj.get("cache_read_tokens") or 0)
                out_t = int(obj.get("output_tokens") or 0)
                if in_t <= 0 and cr_t <= 0 and out_t <= 0:
                    continue

                step_rec = {
                    "step": step_idx,
                    "at": str(obj.get("created_at") or ""),
                    "type": str(obj.get("type") or ""),
                    "in": in_t,
                    "cache": cr_t,
                    "out": out_t,
                }
                step_model = str(obj.get("model") or "").strip()
                if step_model:
                    step_rec["model"] = step_model
                token_steps.append(step_rec)
    except Exception:
        return empty, []

    if not token_steps:
        out_empty = dict(empty)
        out_empty["searchWebCalls"] = search_web_calls
        out_empty["errorSteps"] = error_steps
        out_empty["subagentCalls"] = subagent_calls
        return out_empty, []

    token_steps.sort(key=lambda x: x["step"])
    total_in = sum(s["in"] for s in token_steps)
    total_cr = sum(s["cache"] for s in token_steps)
    total_out = sum(s["out"] for s in token_steps)

    summary = {
        "input": total_in,
        "cacheRead": total_cr,
        "output": total_out,
        "total": total_in + total_cr + total_out,
        "billedSteps": len(token_steps),
        "compactions": sum(1 for s in token_steps if s["type"] == "CHECKPOINT"),
        "stepStart": token_steps[0]["step"],
        "stepEnd": token_steps[-1]["step"],
        "models": sorted({s["model"] for s in token_steps if s.get("model")}),
        "searchWebCalls": search_web_calls,
        "errorSteps": error_steps,
        "subagentCalls": subagent_calls,
    }
    return summary, token_steps


def fetch_antigravity_quota(timeout_sec=4.5):
    """Query local Antigravity quota (direct LS RPC -> Sidecar bridge)."""
    snap, _ms = fetch_quota_best(timeout_sec=timeout_sec)
    return snap


def safe_conv_filename(conv_id):
    cleaned = "".join(c for c in (conv_id or "default") if c.isalnum() or c in ("-", "_"))
    return (cleaned or "default") + ".json"


def handle_pre_invocation(payload):
    os.makedirs(ACTIVE_DIR, exist_ok=True)
    conv_id = payload.get("conversationId") or "default"
    active_file = os.path.join(ACTIVE_DIR, safe_conv_filename(conv_id))
    tp = resolve_transcript_path(payload, conv_id)

    now = time.time()
    if os.path.exists(active_file):
        try:
            with open(active_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if now - float(existing.get("startTs", 0)) < STALE_ACTIVE_SECONDS:
                existing["invocations"] = int(existing.get("invocations", 1)) + 1
                if payload.get("modelName") and payload.get("modelName") != "auto":
                    existing["modelName"] = payload.get("modelName")
                if tp and not existing.get("transcriptPath"):
                    existing["transcriptPath"] = tp
                with open(active_file, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False)
                return
        except Exception:
            pass

    snap = fetch_antigravity_quota()
    if not snap:
        snap = {"source": "offline", "billingMode": "unknown", "plan": "", "pools": {}}

    workspaces = payload.get("workspacePaths") or []
    ws_path = str(workspaces[0] if workspaces else (payload.get("cwd") or "")).rstrip("/\\")
    ws_name = os.path.basename(ws_path) if ws_path else "-"
    start_step_idx = get_transcript_max_step(tp)

    record = {
        "conversationId": conv_id,
        "workspace": ws_name or "-",
        "workspacePath": ws_path,
        "modelName": payload.get("modelName") or "auto",
        "transcriptPath": tp,
        "startStepIndex": start_step_idx,
        "startTs": now,
        "startIso": datetime.now().astimezone().isoformat(timespec="seconds"),
        "invocations": 1,
        "startQuota": snap,
    }
    with open(active_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)


def compute_pool_delta(start_pool, end_pool):
    if not start_pool or not end_pool:
        return {"start": None, "end": None, "delta": 0.0, "reset": False, "resetsAt": ""}

    s_val = float(start_pool.get("usedPercent", 0.0))
    e_val = float(end_pool.get("usedPercent", 0.0))
    s_reset = start_pool.get("resetsAt") or ""
    e_reset = end_pool.get("resetsAt") or ""

    if s_val > 1e-5 and ((s_reset and e_reset and s_reset != e_reset) or (e_val < s_val - 1e-5)):
        return {
            "start": round(s_val, 6),
            "end": round(e_val, 6),
            "delta": round(max(0.0, e_val), 6),
            "reset": True,
            "resetsAt": e_reset,
        }

    return {
        "start": round(s_val, 6),
        "end": round(e_val, 6),
        "delta": round(max(0.0, e_val - s_val), 6),
        "reset": False,
        "resetsAt": e_reset,
    }


def handle_stop(payload):
    conv_id = payload.get("conversationId") or "default"
    active_file = os.path.join(ACTIVE_DIR, safe_conv_filename(conv_id))
    if not os.path.exists(active_file):
        return

    try:
        with open(active_file, "r", encoding="utf-8") as f:
            start_rec = json.load(f)
    finally:
        try:
            os.remove(active_file)
        except OSError:
            pass

    time.sleep(1.2)

    end_snap = fetch_antigravity_quota() or {}
    end_ts = time.time()
    start_ts_val = float(start_rec.get("startTs", end_ts))
    duration_sec = max(0.0, end_ts - start_ts_val)

    invocations = int(start_rec.get("invocations", 1))
    term_reason = payload.get("terminationReason") or "NO_TOOL_CALL"

    tp = prefer_compact_transcript(
        start_rec.get("transcriptPath") or resolve_transcript_path(payload, conv_id)
    )
    start_step_idx = start_rec.get("startStepIndex")
    tokens_summary, token_steps = collect_turn_tokens(
        tp,
        start_step_index=start_step_idx,
        start_ts=start_ts_val,
    )
    if tokens_summary["billedSteps"] < invocations and term_reason == "NO_TOOL_CALL":
        time.sleep(0.4)
        tokens_summary, token_steps = collect_turn_tokens(
            tp,
            start_step_index=start_step_idx,
            start_ts=start_ts_val,
        )

    s_quota = start_rec.get("startQuota") or {}
    s_pools = s_quota.get("pools") or {}
    e_pools = end_snap.get("pools") or {}

    base_keys = {"gemini_5h", "gemini_weekly", "claude_gpt_5h", "claude_gpt_weekly"}
    all_keys = sorted(base_keys | set(s_pools.keys()) | set(e_pools.keys()))

    deltas = {}
    any_reset = False
    for key in all_keys:
        d = compute_pool_delta(s_pools.get(key), e_pools.get(key))
        deltas[key] = d
        if d.get("reset"):
            any_reset = True

    avg_step_sec = duration_sec / max(1, invocations)
    status = "ok"
    if duration_sec > LONG_GAP_SECONDS and avg_step_sec > 300:
        status = "long_gap"
    elif any_reset:
        status = "window_reset"

    model_name = payload.get("modelName") or start_rec.get("modelName") or "auto"
    workspaces = payload.get("workspacePaths") or []
    ws_path = start_rec.get("workspacePath") or (
        str(workspaces[0]).rstrip("/\\") if workspaces else ""
    )

    entry = {
        "ts": end_ts,
        "startTs": round(start_ts_val, 3),
        "startIso": start_rec.get("startIso"),
        "endIso": datetime.now().astimezone().isoformat(timespec="seconds"),
        "durationSec": round(duration_sec, 2),
        "conversationId": conv_id[:8],
        "conversationUuid": conv_id,
        "workspace": start_rec.get("workspace") or "-",
        "workspacePath": ws_path,
        "model": model_name,
        "plan": end_snap.get("plan") or s_quota.get("plan") or "",
        "billingMode": end_snap.get("billingMode") or s_quota.get("billingMode") or "",
        "invocations": invocations,
        "terminationReason": term_reason,
        "status": status,
        "tokens": tokens_summary,
        "tokenSteps": token_steps,
        "pools": deltas,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    event_name = ""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        event_name = payload.get("hookEventName") or ""

        if event_name == "PreInvocation":
            handle_pre_invocation(payload)
        elif event_name == "Stop":
            handle_stop(payload)
    except Exception:
        # Strict fail-open: never disrupt user's conversation
        pass

    if event_name == "Stop":
        sys.stdout.write(json.dumps({"decision": "stop"}) + "\n")
    else:
        sys.stdout.write("{}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
