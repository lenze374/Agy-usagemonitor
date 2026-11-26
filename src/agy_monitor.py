#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1-Minute Quota Monitor & Multi-Pass Denoiser for Antigravity.
- Triggered every 60s by the Sidecar daemon (zero LLM token cost).
- Records global pool snapshots (`monitor.jsonl`) and optional extra pools (`extraPools`).
- Denoises transient upward server pulses/rollbacks, pairs pre-reservations via invariant,
  aligns weekly rises to active spans, and filters stale pre-reset replica flaps.
- Compatible with Python 3.9+ across macOS, Linux, and Windows (stdlib only).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

SRC_DIR = os.path.dirname(os.path.realpath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from common import (
    disp_width,
    ensure_utf8_stdio,
    fetch_quota_best,
    pad_l,
    pad_r,
    parse_iso_epoch,
    read_sidecar_state,
)
from paths import BRAIN_DIR, DATA_DIR, MONITOR_LOG


def get_local_idle_seconds(now_ts):
    """
    Pure read-only check of local Antigravity transcript modification times.
    Returns (idle_seconds, active_65s_count).
    """
    if not os.path.isdir(BRAIN_DIR):
        return None, 0
    latest_mtime = 0.0
    active_65s = 0
    try:
        for entry in os.scandir(BRAIN_DIR):
            if not entry.is_dir():
                continue
            tp = os.path.join(entry.path, ".system_generated", "logs", "transcript.jsonl")
            try:
                mt = os.stat(tp).st_mtime
                if mt > latest_mtime:
                    latest_mtime = mt
                if (now_ts - mt) <= 65.0:
                    active_65s += 1
            except OSError:
                continue
    except OSError:
        return None, 0

    if latest_mtime <= 0.0:
        return None, 0
    return round(max(0.0, now_ts - latest_mtime), 1), active_65s


def is_valid_ok_record(obj):
    """Ignore early v0 records where hyphenated IDs were unmapped (all 0.0 and empty resets)."""
    if obj.get("billingMode") == "paygo" or obj.get("extraPools"):
        return True
    resets = obj.get("resets") or {}
    if any(resets.values()):
        return True
    return any(float(obj.get(k) or 0.0) > 0.0 for k in ("g5", "gw", "c5", "cw"))


def read_last_ok_record(monitor_log=MONITOR_LOG):
    """O(1) tail read of monitor.jsonl to find the most recent ok=True snapshot."""
    if not os.path.isfile(monitor_log):
        return None
    try:
        size = os.path.getsize(monitor_log)
        if size <= 0:
            return None
        read_len = min(size, 16384)
        with open(monitor_log, "rb") as f:
            f.seek(size - read_len)
            chunk = f.read(read_len).decode("utf-8", errors="replace")
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        for ln in reversed(lines):
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict) and obj.get("ok") is True and is_valid_ok_record(obj):
                    return obj
            except Exception:
                continue
    except Exception:
        return None
    return None


def probe_antigravity_quota():
    """Probe local Antigravity quota via LS RPC -> Sidecar bridge."""
    try:
        snap, ms = fetch_quota_best(timeout_sec=6.0)
        if not snap:
            return False, "quota_unavailable", None, ms
        billing_mode = snap.get("billingMode") or ""
        pools = snap.get("pools") or {}
        if billing_mode == "paygo":
            return True, "", {"__billingMode__": "paygo"}, ms
        if not isinstance(pools, dict) or not pools:
            return False, "empty_rate_windows", None, ms
        windows = {}
        for k, v in pools.items():
            if isinstance(v, dict) and v.get("usedPercent") is not None:
                windows[k] = {
                    "used": round(float(v.get("usedPercent", 0.0)), 6),
                    "resetsAt": str(v.get("resetsAt") or ""),
                }
        if not windows:
            return False, "empty_rate_windows", None, ms
        return True, "", windows, ms
    except Exception as e:
        return False, str(e)[:80], None, 0


def run_tick():
    os.makedirs(DATA_DIR, exist_ok=True)
    now_ts = time.time()
    iso_now = datetime.fromtimestamp(now_ts).astimezone().isoformat(timespec="seconds")
    idle_sec, active_cnt = get_local_idle_seconds(now_ts)
    ok, err, wins, probe_ms = probe_antigravity_quota()

    if not ok:
        rec = {
            "ts": round(now_ts, 3),
            "iso": iso_now,
            "ok": False,
            "err": err,
            "probeMs": probe_ms,
            "idleSec": idle_sec,
            "localActive": active_cnt,
        }
    elif wins and wins.get("__billingMode__") == "paygo":
        rec = {
            "ts": round(now_ts, 3),
            "iso": iso_now,
            "ok": True,
            "billingMode": "paygo",
            "probeMs": probe_ms,
            "idleSec": idle_sec,
            "localActive": active_cnt,
            "changed": False,
            "g5": 0.0,
            "gw": 0.0,
            "c5": 0.0,
            "cw": 0.0,
            "dg5": 0.0,
            "dgw": 0.0,
            "dc5": 0.0,
            "dcw": 0.0,
            "events": [],
            "resets": {"g5": "", "gw": "", "c5": "", "cw": ""},
        }
    else:
        g5 = (wins.get("gemini_5h") or {}).get("used", 0.0)
        gw = (wins.get("gemini_weekly") or {}).get("used", 0.0)
        c5 = (wins.get("claude_gpt_5h") or {}).get("used", 0.0)
        cw = (wins.get("claude_gpt_weekly") or {}).get("used", 0.0)
        resets = {
            "g5": (wins.get("gemini_5h") or {}).get("resetsAt", ""),
            "gw": (wins.get("gemini_weekly") or {}).get("resetsAt", ""),
            "c5": (wins.get("claude_gpt_5h") or {}).get("resetsAt", ""),
            "cw": (wins.get("claude_gpt_weekly") or {}).get("resetsAt", ""),
        }
        core_keys = {"gemini_5h", "gemini_weekly", "claude_gpt_5h", "claude_gpt_weekly"}
        extra_pools = {
            k: {"used": v["used"], "resetsAt": v.get("resetsAt", "")}
            for k, v in wins.items()
            if k not in core_keys
        }

        prev = read_last_ok_record()
        dg5 = dgw = dc5 = dcw = 0.0
        events = []
        changed = False

        if prev is not None:
            p_resets = prev.get("resets") or {}
            vals_cur = {"g5": g5, "gw": gw, "c5": c5, "cw": cw}
            vals_prev = {
                "g5": float(prev.get("g5") or 0.0),
                "gw": float(prev.get("gw") or 0.0),
                "c5": float(prev.get("c5") or 0.0),
                "cw": float(prev.get("cw") or 0.0),
            }
            recent_ok_tail = []
            if any((not p_resets.get(k)) and vals_prev[k] < 1.0 and resets[k] for k in ("g5", "gw", "c5", "cw")):
                try:
                    recent_ok_tail = [
                        r for r in load_monitor_rows()[-25:]
                        if isinstance(r, dict) and r.get("ok") and is_valid_ok_record(r)
                    ]
                except Exception:
                    recent_ok_tail = []

            deltas = {}
            for k in ("g5", "gw", "c5", "cw"):
                raw_d = round(vals_cur[k] - vals_prev[k], 6)
                cur_r_ep = parse_iso_epoch(resets[k]) if resets[k] else None
                prev_r_ep = parse_iso_epoch(p_resets.get(k)) if p_resets.get(k) else None

                # Check if an earlier tick already retired `cur_r_ep` via an empty-resetsAt reset
                is_retired_flap = False
                if cur_r_ep is not None and prev_r_ep is None and vals_prev[k] < 1.0 and recent_ok_tail:
                    max_recent_ep = None
                    retired_seen = False
                    for rr in recent_ok_tail:
                        rr_res = (rr.get("resets") or {}).get(k) or ""
                        rr_ep = parse_iso_epoch(rr_res) if rr_res else None
                        rr_v = float(rr.get(k) or 0.0)
                        if rr_ep is not None:
                            if max_recent_ep is None or rr_ep > max_recent_ep:
                                max_recent_ep = rr_ep
                        elif rr_v < 1.0 and max_recent_ep is not None and abs(cur_r_ep - max_recent_ep) <= 120.0:
                            retired_seen = True
                    if retired_seen:
                        is_retired_flap = True

                # Detect backward resetsAt flap to a stale pre-reset backend replica
                is_stale_flap = is_retired_flap or bool(
                    cur_r_ep is not None
                    and prev_r_ep is not None
                    and cur_r_ep < prev_r_ep - 120.0
                )
                is_empty_reset = bool(
                    vals_prev[k] > 3.0
                    and vals_cur[k] < 1.0
                    and p_resets.get(k)
                    and not resets[k]
                )
                r_changed = bool(
                    resets[k]
                    and p_resets.get(k)
                    and resets[k] != p_resets.get(k)
                    and not is_stale_flap
                    and (vals_prev[k] > 1e-6 or vals_cur[k] > 1e-6)
                )
                if is_stale_flap:
                    events.append(f"stale_replica:{k}")
                    deltas[k] = 0.0
                elif r_changed or is_empty_reset:
                    events.append(f"reset:{k}")
                    deltas[k] = round(vals_cur[k], 6)
                else:
                    if raw_d < -1e-6:
                        events.append(f"rollback:{k}({raw_d:+.4f}%)")
                    deltas[k] = raw_d
                if not is_stale_flap and (abs(raw_d) > 1e-6 or r_changed or is_empty_reset):
                    changed = True
            dg5, dgw, dc5, dcw = deltas["g5"], deltas["gw"], deltas["c5"], deltas["cw"]

        rec = {
            "ts": round(now_ts, 3),
            "iso": iso_now,
            "ok": True,
            "probeMs": probe_ms,
            "idleSec": idle_sec,
            "localActive": active_cnt,
            "changed": changed,
            "g5": g5,
            "gw": gw,
            "c5": c5,
            "cw": cw,
            "dg5": dg5,
            "dgw": dgw,
            "dc5": dc5,
            "dcw": dcw,
            "events": events,
            "resets": resets,
        }
        if extra_pools:
            rec["extraPools"] = extra_pools

    line = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(MONITOR_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    return rec


def load_monitor_rows(monitor_log=MONITOR_LOG):
    if not os.path.isfile(monitor_log):
        return []
    rows = []
    with open(monitor_log, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and obj.get("ok") is True and not is_valid_ok_record(obj):
                    continue
                rows.append(obj)
            except Exception:
                continue
    return rows


def is_monitor_change_row(r):
    """Return True if an ok=True monitor row recorded any pool delta or non-zero reset."""
    if any(abs(float(r.get(dk) or 0.0)) > 1e-6 for dk in ("dg5", "dgw", "dc5", "dcw")):
        return True
    return any(
        str(e).startswith("reset:") and float(r.get(str(e).split(":", 1)[1]) or 0.0) > 1e-6
        for e in (r.get("events") or [])
        if ":" in str(e)
    )


def _row_ts(r):
    ts_val = r.get("ts")
    if ts_val is not None:
        try:
            return float(ts_val)
        except (TypeError, ValueError):
            pass
    ep = parse_iso_epoch(r.get("iso"))
    return float(ep) if ep is not None else 0.0


def _fmt_gap_duration(gap_sec):
    mins = max(1, int(round(float(gap_sec or 0.0) / 60.0)))
    if mins >= 60:
        h, m = divmod(mins, 60)
        return f"{h}h{m}m" if m else f"{h}h"
    return f"{mins}m"


def _is_row_pure_idle(orig_r):
    """Return True when monitor row shows zero local activity and >180s idle."""
    idle_s = orig_r.get("idleSec")
    return (int(orig_r.get("localActive") or 0) == 0) and (
        idle_s is not None and float(idle_s) > 180.0
    )


def _pair_gemini_prereservations(ok_rows, win_data, five_h_to_weekly=0.25):
    """
    Pass 1.5: Pair Gemini pre-reservation opens (`dinv > 0`) with their delayed
    rollbacks (`dinv < 0`) using `inv = gw - ratio * g5` inside contiguous joint
    `(g5, gw)` windows. Skips weekly-only segments automatically. Mutates
    `win_data['g5']` / `win_data['gw']` v1 arrays in place and returns
    `(paired_flags, unmatched_open_gw, unmatched_refund_gw)`.
    """
    ratio = float(five_h_to_weekly or 0.25)
    pre_unit = max(0.05, 1.0 - ratio)
    n_rows = len(ok_rows)
    paired_flags = [False] * n_rows
    unmatched_open_gw = [0.0] * n_rows
    unmatched_refund_gw = [0.0] * n_rows

    g5_map = {}
    gw_map = {}
    for wi, (w, v1) in enumerate(win_data.get("g5") or []):
        for pos, item in enumerate(w):
            g5_map[item[0]] = (wi, pos, v1[pos], item[1])
    for wi, (w, v1) in enumerate(win_data.get("gw") or []):
        for pos, item in enumerate(w):
            gw_map[item[0]] = (wi, pos, v1[pos], item[1])

    joint_segs = []
    cur_seg = []
    cur_key = None
    for idx in range(n_rows):
        if idx in g5_map and idx in gw_map:
            key = (g5_map[idx][0], gw_map[idx][0])
            if key != cur_key:
                if cur_seg:
                    joint_segs.append(cur_seg)
                cur_seg = [idx]
                cur_key = key
            else:
                cur_seg.append(idx)
    if cur_seg:
        joint_segs.append(cur_seg)

    for seg_idxs in joint_segs:
        m = len(seg_idxs)
        if m < 2:
            continue
        g5_arr = [g5_map[idx][2] for idx in seg_idxs]
        gw_arr = [gw_map[idx][2] for idx in seg_idxs]
        ts_arr = [gw_map[idx][3] for idx in seg_idxs]
        is_idle_arr = [_is_row_pure_idle(ok_rows[idx]) for idx in seg_idxs]

        # Pass 1.5a: erase 1-tick exact replica bounce where both g5 & gw return
        for i in range(1, m - 1):
            if abs(gw_arr[i + 1] - gw_arr[i - 1]) < 1e-4 and abs(g5_arr[i + 1] - g5_arr[i - 1]) < 1e-4:
                if abs(gw_arr[i] - gw_arr[i - 1]) > 0.01 or abs(g5_arr[i] - g5_arr[i - 1]) > 0.01:
                    gw_arr[i] = gw_arr[i - 1]
                    g5_arr[i] = g5_arr[i - 1]

        has_5h = any(
            g5_arr[k] > 1e-6 or bool((ok_rows[seg_idxs[k]].get("resets") or {}).get("g5"))
            for k in range(m)
        )
        if (not has_5h) or ratio >= 0.90:
            for pos, idx in enumerate(seg_idxs):
                wi5, p5, _, _ = g5_map[idx]
                wiw, pw, _, _ = gw_map[idx]
                win_data["g5"][wi5][1][p5] = g5_arr[pos]
                win_data["gw"][wiw][1][pw] = gw_arr[pos]
            continue

        # Pass 1.5b: invariant open/close pairing
        open_slots = []
        for i in range(1, m):
            dg5 = g5_arr[i] - g5_arr[i - 1]
            dgw = gw_arr[i] - gw_arr[i - 1]
            dinv = dgw - ratio * dg5

            if 0.01 < dinv <= 2.5 and dgw > 0.05 and dg5 > -0.05:
                open_slots.append(
                    {
                        "pos": i,
                        "ts": ts_arr[i],
                        "dinv": dinv,
                        "dgw": dgw,
                        "dg5": dg5,
                        "open_idle": is_idle_arr[i],
                        "matched": False,
                    }
                )
            elif -2.5 <= dinv < -0.005 and dgw < -0.005:
                ref_gw = -dgw
                ref_g5 = max(0.0, -dg5)
                best = None

                # Priority 1a: LIFO within 30m, exact transient gw return
                for s in reversed(open_slots):
                    if s["matched"]:
                        continue
                    dt = ts_arr[i] - s["ts"]
                    if dt <= 0.0 or dt > 1800.0:
                        continue
                    dsum = s["dinv"] + dinv
                    is_q_mult = abs((dsum / ratio) - round(dsum / ratio)) <= 0.03
                    if (
                        abs(s["dgw"] - ref_gw) <= 0.005
                        and ref_g5 <= max(0.0, s["dg5"]) + 0.02
                        and is_q_mult
                    ):
                        best = s
                        break

                # Priority 1b: LIFO within 5m, short-lived active reservation close
                if best is None:
                    for s in reversed(open_slots):
                        if s["matched"] or s["open_idle"]:
                            continue
                        dt = ts_arr[i] - s["ts"]
                        if dt <= 0.0 or dt > 300.0:
                            continue
                        if (
                            abs(s["dinv"] + dinv) <= 0.006
                            and ref_gw <= s["dgw"] + 0.01
                            and ref_g5 <= max(0.0, s["dg5"]) + 0.02
                        ):
                            best = s
                            break

                # Priority 2: FIFO within 6h, TTL expiration
                if best is None:
                    for s in open_slots:
                        if s["matched"]:
                            continue
                        dt = ts_arr[i] - s["ts"]
                        if dt <= 0.0 or dt > 6.0 * 3600.0:
                            continue
                        if not (
                            abs(s["dinv"] + dinv) <= 0.006
                            and ref_gw <= s["dgw"] + 0.01
                            and ref_g5 <= max(0.0, s["dg5"]) + 0.02
                        ):
                            continue
                        # Idle-teleport guard: leave pure pre-turn idle spikes whose
                        # close drops below gw[open] across an active tick to Pass 2/3.
                        if (
                            s["open_idle"]
                            and gw_arr[i] < gw_arr[s["pos"]] - 0.01
                            and abs(s["dgw"] - ref_gw) > 0.005
                            and any(not is_idle_arr[k] for k in range(s["pos"], i + 1))
                        ):
                            continue
                        best = s
                        break

                if best is not None:
                    o_pos = best["pos"]
                    floor_ok = all(
                        (gw_arr[k] - ref_gw) >= gw_arr[o_pos - 1] - 0.01
                        for k in range(o_pos, i)
                    )
                    if floor_ok:
                        best["matched"] = True
                        paired_flags[seg_idxs[o_pos]] = True
                        for k in range(o_pos, i):
                            gw_arr[k] = round(gw_arr[k] - ref_gw, 6)
                            g5_arr[k] = round(max(0.0, g5_arr[k] - ref_g5), 6)
                    else:
                        unmatched_refund_gw[seg_idxs[i]] = round(ref_gw, 6)
                else:
                    unmatched_refund_gw[seg_idxs[i]] = round(ref_gw, 6)

        for s in open_slots:
            if s["matched"]:
                continue
            if (pre_unit - 0.10) <= s["dinv"] <= (pre_unit + 0.10):
                pre_w = 1.0
            elif s["dinv"] > (pre_unit + 0.10):
                pre_w = max(1.0, round(s["dinv"] / pre_unit) * 1.0)
            else:
                pre_w = min(1.0, s["dgw"])
            unmatched_open_gw[seg_idxs[s["pos"]]] = round(pre_w, 6)

        for pos, idx in enumerate(seg_idxs):
            wi5, p5, _, _ = g5_map[idx]
            wiw, pw, _, _ = gw_map[idx]
            win_data["g5"][wi5][1][p5] = g5_arr[pos]
            win_data["gw"][wiw][1][pw] = gw_arr[pos]

    return paired_flags, unmatched_open_gw, unmatched_refund_gw


def clean_monitor_timeline(rows, five_h_to_weekly=0.25):
    """
    Build a multi-pass denoised, cross-day continuous monitor timeline over valid `ok=True` rows:
      - Filters stale pre-reset replica reads whose `resetsAt` jumped backward (> 120s).
      - Segments each pool (`g5`, `gw`, `c5`, `cw`) into genuine quota reset windows.
      - Pass 1: repairs isolated 1-2 tick downward stale-replica dips within each window.
      - Pass 1.5: pairs Gemini `(g5, gw)` pre-reservation opens with delayed rollbacks via
        `inv = gw - ratio * g5` so settled real spend is restored to its true origin tick.
      - Pass 2 & 3: applies suffix minimum and active-aware anchor alignment within each window.
    """
    ok_rows = [
        r
        for r in rows
        if isinstance(r, dict)
        and r.get("ok")
        and r.get("billingMode") != "paygo"
        and is_valid_ok_record(r)
    ]
    if not ok_rows:
        return []

    n_rows = len(ok_rows)
    pool_keys = ("g5", "gw", "c5", "cw")
    per_pool_data = {pk: [None] * n_rows for pk in pool_keys}
    win_data = {}

    # Stage A: stale-replica filtering, window splitting, and Pass-1 dip repair
    for pk in pool_keys:
        win_thresh = 86400.0 if pk in ("gw", "cw") else 1800.0
        max_ep = None
        retired_ep = None
        kept = []  # (row_idx, ts, val, reset_ep, raw_reset_flag, res_s)
        prev_raw_v = None

        for idx, r in enumerate(ok_rows):
            res_s = (r.get("resets") or {}).get(pk) or ""
            ep = parse_iso_epoch(res_s) if res_s else None
            cur_v = float(r.get(pk) or 0.0)
            if ep is not None:
                if (max_ep is not None and ep < max_ep - 120.0) or (
                    retired_ep is not None and ep <= retired_ep + 120.0
                ):
                    continue
                if max_ep is None or ep > max_ep:
                    max_ep = ep
                if retired_ep is not None and ep > retired_ep + 120.0:
                    retired_ep = None
            else:
                if prev_raw_v is not None and prev_raw_v > 3.0 and cur_v < 1.0 and max_ep is not None:
                    retired_ep = max_ep

            ev = [str(e) for e in (r.get("events") or [])]
            ev_reset = (f"reset:{pk}" in ev) and (cur_v > 1e-6 or (prev_raw_v is not None and prev_raw_v > 1e-6))
            kept.append((idx, _row_ts(r), cur_v, ep, ev_reset, res_s))
            prev_raw_v = cur_v

        if not kept:
            win_data[pk] = []
            continue

        windows = []
        cur_win = []
        prev_ep = None
        prev_v = None
        for item in kept:
            idx, ts_val, v, ep, ev_reset, res_s = item
            is_win_reset = False
            is_stale_bounce_drop = False
            if cur_win:
                if ep is not None and prev_ep is not None:
                    if (ep - prev_ep) > win_thresh and (prev_v > 1e-6 and v < prev_v - 1e-6):
                        is_win_reset = True
                elif ep is None and prev_v is not None and (
                    (prev_v > 3.0 and v < 1.0)
                    or (pk in ("g5", "c5") and ev_reset and prev_v > 0.1 and v < 0.1)
                ):
                    if prev_v > 3.0 and v < 1.0:
                        # Guard against brief post-reset stale-replica bounces (0 -> >=3.0 -> <1.0 within 15m)
                        high_tail_start = None
                        for b_i in range(len(cur_win) - 1, -1, -1):
                            if cur_win[b_i][2] >= 3.0:
                                high_tail_start = b_i
                            elif cur_win[b_i][2] < 1.0:
                                break
                            else:
                                high_tail_start = None
                                break
                        if (
                            high_tail_start is not None
                            and high_tail_start > 0
                            and cur_win[high_tail_start - 1][2] < 1.0
                            and (len(cur_win) - high_tail_start) <= 5
                            and (ts_val - cur_win[high_tail_start][1]) <= 900.0
                        ):
                            is_stale_bounce_drop = True
                            del cur_win[high_tail_start:]
                        else:
                            is_win_reset = True
                    else:
                        is_win_reset = True
            if is_stale_bounce_drop:
                cur_win.append(item)
                prev_v = v
                continue
            if is_win_reset:
                windows.append(cur_win)
                cur_win = [item]
            else:
                cur_win.append(item)
            if ep is not None:
                prev_ep = ep
            prev_v = v
        if cur_win:
            windows.append(cur_win)

        v1_windows = []
        for w in windows:
            # Pass 1: isolated 1-2 tick downward dip repair (skip if rebound is itself an un-settled spike)
            v1 = [x[2] for x in w]
            wn = len(v1)
            i = 1
            while i < wn:
                is_upward_bounce_return = (
                    i >= 2
                    and v1[i - 1] > v1[i - 2] + 0.01
                    and abs(v1[i] - v1[i - 2]) <= 1e-4
                )
                if (not is_upward_bounce_return) and v1[i] < v1[i - 1] - 1e-5:
                    rebound = False
                    for k in (1, 2):
                        if i + k < wn and v1[i + k] >= v1[i - 1] - 1e-5:
                            p_next = i + k + 1
                            while p_next < wn and (p_next - (i + k)) <= 5 and abs(v1[p_next] - v1[i + k]) < 0.02:
                                p_next += 1
                            is_pre_rollback_spike = (
                                p_next < wn and v1[p_next] < v1[i + k] - 0.05
                            )
                            if is_pre_rollback_spike:
                                break
                            for j in range(i, i + k):
                                v1[j] = v1[i - 1]
                            i += k
                            rebound = True
                            break
                    if rebound:
                        continue
                i += 1
            v1_windows.append((w, v1))
        win_data[pk] = v1_windows

    # Stage B: Pass 1.5 joint Gemini invariant pairing
    preres_paired_flags, unmatched_preres_open_gw, unmatched_preres_refund_gw = (
        _pair_gemini_prereservations(ok_rows, win_data, five_h_to_weekly=five_h_to_weekly)
    )

    # Stage C: Pass 2 suffix minimum and Pass 3 active-aware anchor alignment
    for pk in pool_keys:
        v1_windows = win_data.get(pk) or []
        if not v1_windows:
            continue

        last_clean_v = 0.0
        last_ts = None
        for wi, (w, v1) in enumerate(v1_windows):
            wn = len(v1)

            # Pass 2: suffix minimum within window
            smin = [0.0] * wn
            m_val = v1[-1]
            for i in range(wn - 1, -1, -1):
                if v1[i] < m_val:
                    m_val = v1[i]
                smin[i] = m_val

            # Pass 3: active-aware anchor alignment for weekly pools so clamped rises
            # never teleport backward from a local-active span onto a preceding idle spike.
            aligned = list(smin)
            if pk in ("gw", "cw") and wn >= 3:
                is_idle_list = [_is_row_pure_idle(ok_rows[x[0]]) for x in w]
                anchors = [k for k in range(wn) if v1[k] <= smin[k] + 1e-4]
                if not anchors or anchors[0] != 0:
                    anchors.insert(0, 0)
                if anchors[-1] != wn - 1:
                    anchors.append(wn - 1)
                for ai in range(len(anchors) - 1):
                    a = anchors[ai]
                    b = anchors[ai + 1]
                    if b <= a + 1:
                        continue
                    va = smin[a]
                    vb = smin[b]
                    if vb <= va + 1e-5 or not is_idle_list[a + 1]:
                        continue
                    first_act = next((k for k in range(a + 1, b + 1) if not is_idle_list[k]), None)
                    if first_act is not None:
                        for k in range(a + 1, first_act):
                            aligned[k] = va
                        for k in range(first_act, b + 1):
                            aligned[k] = max(va, min(aligned[k], vb))

            for i, (orig_idx, ts_val, _raw_v, _ep, ev_reset, res_s) in enumerate(w):
                cv = aligned[i]
                is_win_reset = wi > 0 and i == 0
                if wi == 0 and i == 0:
                    cd = 0.0
                    gap_sec = 0.0
                elif is_win_reset:
                    cd = max(0.0, cv)
                    gap_sec = max(0.0, ts_val - last_ts) if last_ts is not None else 0.0
                else:
                    cd = max(0.0, cv - last_clean_v)
                    gap_sec = max(0.0, ts_val - last_ts) if last_ts is not None else 0.0

                reset_flag = is_win_reset or ev_reset
                per_pool_data[pk][orig_idx] = (cv, cd, gap_sec, is_win_reset, reset_flag, res_s)
                last_clean_v = cv
                last_ts = ts_val

        last_carry = 0.0
        last_res_s = ""
        for idx in range(n_rows):
            if per_pool_data[pk][idx] is None:
                per_pool_data[pk][idx] = (last_carry, 0.0, 0.0, False, False, last_res_s)
            else:
                last_carry = per_pool_data[pk][idx][0]
                last_res_s = per_pool_data[pk][idx][5]

    timeline = []
    for idx, r in enumerate(ok_rows):
        ts_val = _row_ts(r)
        idle_s = r.get("idleSec")
        is_pure_idle = _is_row_pure_idle(r)
        g5_t, gw_t, c5_t, cw_t = (per_pool_data[pk][idx] for pk in pool_keys)
        max_gap = max(g5_t[2], gw_t[2], c5_t[2], cw_t[2])
        clean_resets = dict(r.get("resets") or {})
        clean_resets["g5"] = g5_t[5]
        clean_resets["gw"] = gw_t[5]
        clean_resets["c5"] = c5_t[5]
        clean_resets["cw"] = cw_t[5]
        timeline.append(
            {
                "ts": ts_val,
                "iso": r.get("iso") or "",
                "g5": round(g5_t[0], 6),
                "gw": round(gw_t[0], 6),
                "c5": round(c5_t[0], 6),
                "cw": round(cw_t[0], 6),
                "dg5": round(g5_t[1], 6),
                "dgw": round(gw_t[1], 6),
                "dc5": round(c5_t[1], 6),
                "dcw": round(cw_t[1], 6),
                "raw_g5": float(r.get("g5") or 0.0),
                "raw_gw": float(r.get("gw") or 0.0),
                "raw_c5": float(r.get("c5") or 0.0),
                "raw_cw": float(r.get("cw") or 0.0),
                "gap_sec": round(max_gap, 1),
                "offline_gap": max_gap > 300.0,
                "pool_gaps": {
                    "g5": g5_t[2],
                    "gw": gw_t[2],
                    "c5": c5_t[2],
                    "cw": cw_t[2],
                },
                "window_resets": {
                    "g5": g5_t[3],
                    "gw": gw_t[3],
                    "c5": c5_t[3],
                    "cw": cw_t[3],
                },
                "reset_flags": {
                    "g5": g5_t[4],
                    "gw": gw_t[4],
                    "c5": c5_t[4],
                    "cw": cw_t[4],
                },
                "preres_paired": bool(preres_paired_flags[idx]),
                "unmatched_preres_open_gw": float(unmatched_preres_open_gw[idx]),
                "unmatched_preres_refund_gw": float(unmatched_preres_refund_gw[idx]),
                "idle": is_pure_idle,
                "idleSec": idle_s,
                "localActive": int(r.get("localActive") or 0),
                "events": list(r.get("events") or []),
                "resets": clean_resets,
                "orig_row": r,
            }
        )
    return timeline


def summarize_clean_rows(raw_rows, full_timeline, since_ts=None, until_ts=None):
    """Aggregate attribution totals, resets, and corrections from a pre-cleaned timeline."""
    ok_rows = [r for r in raw_rows if isinstance(r, dict) and r.get("ok") and is_valid_ok_record(r)]
    chg_rows = [r for r in ok_rows if is_monitor_change_row(r)]
    rollbacks = [r for r in ok_rows if any(str(e).startswith("rollback:") for e in (r.get("events") or []))]

    sliced = []
    for item in full_timeline or []:
        t = item["ts"]
        if since_ts is not None and t < float(since_ts):
            continue
        if until_ts is not None and t >= float(until_ts):
            continue
        sliced.append(item)

    reset_counts = {"g5": 0, "gw": 0, "c5": 0, "cw": 0}
    pool_up = {"g5": 0.0, "gw": 0.0, "c5": 0.0, "cw": 0.0}
    active_gw_up = 0.0
    online_idle_gw_up = 0.0
    offline_gw_up = 0.0
    active_cw_up = 0.0
    online_idle_cw_up = 0.0
    offline_cw_up = 0.0
    token_corrected_gw = 0.0

    for item in sliced:
        for pk in ("g5", "gw", "c5", "cw"):
            if item["reset_flags"][pk]:
                reset_counts[pk] += 1
            pool_up[pk] += item[f"d{pk}"]

        token_corrected_gw += float(item.get("token_corrected_gw") or 0.0)
        if "dgw_active" in item and "dgw_idle_on" in item and "dgw_offline" in item:
            active_gw_up += float(item["dgw_active"] or 0.0)
            online_idle_gw_up += float(item["dgw_idle_on"] or 0.0)
            offline_gw_up += float(item["dgw_offline"] or 0.0)
        else:
            dgw = item["dgw"]
            if dgw > 0:
                if item["pool_gaps"]["gw"] > 300.0 and item["idle"]:
                    offline_gw_up += dgw
                elif item["idle"]:
                    online_idle_gw_up += dgw
                else:
                    active_gw_up += dgw

        dcw = item["dcw"]
        if dcw > 0:
            if item["pool_gaps"]["cw"] > 300.0 and item["idle"]:
                offline_cw_up += dcw
            elif item["idle"]:
                online_idle_cw_up += dcw
            else:
                active_cw_up += dcw

    start_clean = (
        {pk: sliced[0][pk] for pk in ("g5", "gw", "c5", "cw")}
        if sliced
        else {"g5": 0.0, "gw": 0.0, "c5": 0.0, "cw": 0.0}
    )
    end_clean = (
        {pk: sliced[-1][pk] for pk in ("g5", "gw", "c5", "cw")}
        if sliced
        else {"g5": 0.0, "gw": 0.0, "c5": 0.0, "cw": 0.0}
    )
    pending_preres_gw = float(sliced[-1].get("pending_preres_gw") or 0.0) if sliced else 0.0

    return {
        "total_rows": len(raw_rows),
        "ok_rows": ok_rows,
        "chg_rows": chg_rows,
        "rollbacks": rollbacks,
        "reset_counts": reset_counts,
        "pool_up": pool_up,
        "active_gw_up": active_gw_up,
        "online_idle_gw_up": online_idle_gw_up,
        "offline_gw_up": offline_gw_up,
        "idle_gw_up": online_idle_gw_up + offline_gw_up,
        "active_cw_up": active_cw_up,
        "online_idle_cw_up": online_idle_cw_up,
        "offline_cw_up": offline_cw_up,
        "idle_cw_up": online_idle_cw_up + offline_cw_up,
        "token_corrected_gw": round(token_corrected_gw, 6),
        "pending_preres_gw": round(pending_preres_gw, 4),
        "clean_rows": sliced,
        "start_clean": start_clean,
        "end_clean": end_clean,
    }


def summarize_monitor_rows(rows, all_rows=None, since_ts=None, until_ts=None, five_h_to_weekly=0.25):
    """
    Compute denoised attribution totals, change rows, and rollback/reset counts over monitor rows.
    """
    source_rows = all_rows if all_rows is not None else rows
    full_timeline = clean_monitor_timeline(source_rows, five_h_to_weekly=five_h_to_weekly)
    return summarize_clean_rows(rows, full_timeline, since_ts=since_ts, until_ts=until_ts)


def fmt_idle_tag(r):
    if not r.get("ok"):
        return f"离线({r.get('err', '-')})"
    ev = r.get("events") or []
    prefix = ("[" + ",".join(ev) + "] ") if ev else ""
    act = int(r.get("localActive") or 0)
    idle_s = r.get("idleSec")
    if act > 0 or (idle_s is not None and idle_s <= 65.0):
        return prefix + "本机活跃"
    if idle_s is not None and idle_s <= 180.0:
        return prefix + f"刚停({int(idle_s)}s)"
    if idle_s is not None:
        mins = int(idle_s // 60)
        return prefix + f"本机静置({mins}m)"
    return prefix + "未知"


def fmt_signed(val):
    v = float(val or 0.0)
    if abs(v) <= 1e-6:
        return "      -   "
    return f"{v:+9.4f}%"


def print_status_and_log(recent_n=20, changes_only=False):
    sc_info = read_sidecar_state()
    rows = load_monitor_rows()
    summary = summarize_monitor_rows(rows)
    ok_rows = summary["ok_rows"]
    chg_rows = summary["chg_rows"]
    rollbacks = summary["rollbacks"]
    cw_total = summary["active_cw_up"] + summary["idle_cw_up"]
    off_gw = summary["offline_gw_up"]
    off_cw = summary["offline_cw_up"]

    mode_str = (
        f"Sidecar: 运行中 ON (PID {sc_info.get('pid')}, 127.0.0.1:{sc_info.get('port')})"
        if sc_info
        else "未启动 OFF"
    )
    off_suffix = (
        f" | 离线休眠 Gem+{off_gw:.4f}% / C/G+{off_cw:.4f}%" if (off_gw + off_cw) > 1e-6 else ""
    )
    print(
        f"=== 每分钟独立额度监控 ({mode_str}) ===\n"
        f"日志文件: {MONITOR_LOG}\n"
        f"累计采样: 共 {len(rows)} 分钟 (有效 {len(ok_rows)} 条 | 水位变动 {len(chg_rows)} 分钟 | 捕获服务端回退 {len(rollbacks)} 次)\n"
        f"归因统计(已去噪): 本机活跃 Gemini周+{summary['active_gw_up']:.4f}% | "
        f"在线静置 Gemini周+{summary['online_idle_gw_up']:.4f}% | "
        f"Claude/GPT周+{cw_total:.4f}%{off_suffix}"
    )

    if not sc_info:
        print("\n提示: 当前 Sidecar 未运行，请在 Antigravity Plugins 面板启用 usage-monitor 插件。")

    target_pool = chg_rows if changes_only else rows
    if not target_pool or recent_n <= 0:
        return

    shown = target_pool[-recent_n:]
    title_mode = "仅显示水位变动分钟" if changes_only else f"最近 {len(shown)} 分钟全量打点"
    print(f"\n--- {title_mode} ---")
    hdr = (
        f"{pad_r('采样时间', 19)} | {pad_l('Gem 5h', 8)} | {pad_l('1m增5h', 10)} | "
        f"{pad_l('Gem 周', 8)} | {pad_l('1m增周', 10)} | "
        f"{pad_l('C/G 周', 8)} | {pad_l('1m增C/G', 10)} | 本机状态"
    )
    print(hdr)
    print("-" * disp_width(hdr))

    for r in shown:
        t_str = (r.get("iso") or "")[:19].replace("T", " ")
        if not r.get("ok"):
            print(
                f"{pad_r(t_str, 19)} | {pad_l('-', 8)} | {pad_l('-', 10)} | "
                f"{pad_l('-', 8)} | {pad_l('-', 10)} | "
                f"{pad_l('-', 8)} | {pad_l('-', 10)} | {fmt_idle_tag(r)}"
            )
            continue
        g5_s = f"{float(r.get('g5') or 0.0):7.4f}%"
        gw_s = f"{float(r.get('gw') or 0.0):7.4f}%"
        cw_s = f"{float(r.get('cw') or 0.0):7.4f}%"
        print(
            f"{pad_r(t_str, 19)} | {pad_l(g5_s, 8)} | {pad_l(fmt_signed(r.get('dg5')), 10)} | "
            f"{pad_l(gw_s, 8)} | {pad_l(fmt_signed(r.get('dgw')), 10)} | "
            f"{pad_l(cw_s, 8)} | {pad_l(fmt_signed(r.get('dcw')), 10)} | {fmt_idle_tag(r)}"
        )


def watch_live():
    print_status_and_log(recent_n=10, changes_only=False)
    print("\n[实时跟随模式] 正在监听 monitor.jsonl 新采样点（按 Ctrl+C 退出界面）...")
    last_size = os.path.getsize(MONITOR_LOG) if os.path.isfile(MONITOR_LOG) else 0
    try:
        while True:
            time.sleep(2.0)
            if not os.path.isfile(MONITOR_LOG):
                continue
            cur_size = os.path.getsize(MONITOR_LOG)
            if cur_size < last_size:
                last_size = 0
            if cur_size > last_size:
                with open(MONITOR_LOG, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last_size)
                    new_text = f.read()
                last_size = cur_size
                for ln in new_text.splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        r = json.loads(ln)
                    except Exception:
                        continue
                    t_str = (r.get("iso") or "")[:19].replace("T", " ")
                    if not r.get("ok"):
                        print(f"[{t_str}] 采样离线: {r.get('err')}")
                    else:
                        print(
                            f"[{t_str}] Gem5h={float(r.get('g5') or 0):.4f}% ({fmt_signed(r.get('dg5')).strip()}) | "
                            f"Gem周={float(r.get('gw') or 0):.4f}% ({fmt_signed(r.get('dgw')).strip()}) | "
                            f"C/G周={float(r.get('cw') or 0):.4f}% ({fmt_signed(r.get('dcw')).strip()}) | "
                            f"{fmt_idle_tag(r)}"
                        )
    except KeyboardInterrupt:
        print("\n已退出实时查看。")


def main():
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Antigravity 1-minute quota monitor")
    parser.add_argument("--tick", action="store_true", help="Sample once and append to monitor.jsonl")
    parser.add_argument("--status", action="store_true", help="Print monitor status and recent ticks")
    parser.add_argument("--changes", action="store_true", help="Show only ticks with quota changes")
    parser.add_argument("--watch", action="store_true", help="Watch monitor.jsonl in real time")
    parser.add_argument("-n", "--recent", type=int, default=20, help="Show last N ticks (default 20)")
    args = parser.parse_args()

    if args.tick:
        run_tick()
        return
    if args.watch:
        watch_live()
        return
    print_status_and_log(recent_n=args.recent, changes_only=args.changes)


if __name__ == "__main__":
    main()
