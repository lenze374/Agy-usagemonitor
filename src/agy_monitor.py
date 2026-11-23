#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1-Minute Quota Monitor & 2-Pass Denoiser for Antigravity.
- Triggered every 60s by the Sidecar daemon (zero LLM token cost).
- Records global pool snapshots (`monitor.jsonl`) and optional extra pools (`extraPools`).
- Denoises transient upward server pulses/rollbacks and stale pre-reset replica flaps.
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

from common import disp_width, fetch_quota_best, pad_l, pad_r, parse_iso_epoch, read_sidecar_state
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
            deltas = {}
            for k in ("g5", "gw", "c5", "cw"):
                raw_d = round(vals_cur[k] - vals_prev[k], 6)
                cur_r_ep = parse_iso_epoch(resets[k]) if resets[k] else None
                prev_r_ep = parse_iso_epoch(p_resets.get(k)) if p_resets.get(k) else None
                is_stale_flap = bool(
                    cur_r_ep is not None
                    and prev_r_ep is not None
                    and cur_r_ep < prev_r_ep - 120.0
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
                elif r_changed:
                    events.append(f"reset:{k}")
                    deltas[k] = round(vals_cur[k], 6)
                else:
                    if raw_d < -1e-6:
                        events.append(f"rollback:{k}({raw_d:+.4f}%)")
                    deltas[k] = raw_d
                if not is_stale_flap and (abs(raw_d) > 1e-6 or r_changed):
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


def clean_monitor_timeline(rows):
    """
    Build a 2-pass denoised, cross-day continuous monitor timeline over valid `ok=True` rows:
      - Filters stale pre-reset replica reads whose `resetsAt` jumped backward (> 120s).
      - Segments each pool (`g5`, `gw`, `c5`, `cw`) into genuine quota reset windows.
      - Pass 1: repairs isolated 1-2 tick downward stale-replica dips within each window.
      - Pass 2: applies suffix minimum within each window so phantom pulses and
        transient upward spikes that later roll back are completely erased without locking
        the high-water mark.
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

    for pk in pool_keys:
        win_thresh = 86400.0 if pk in ("gw", "cw") else 1800.0
        max_ep = None
        kept = []
        prev_raw_v = None

        for idx, r in enumerate(ok_rows):
            res_s = (r.get("resets") or {}).get(pk) or ""
            ep = parse_iso_epoch(res_s) if res_s else None
            if ep is not None and max_ep is not None and ep < max_ep - 120.0:
                continue
            if ep is not None and (max_ep is None or ep > max_ep):
                max_ep = ep
            cur_v = float(r.get(pk) or 0.0)
            ev = [str(e) for e in (r.get("events") or [])]
            ev_reset = (f"reset:{pk}" in ev) and (cur_v > 1e-6 or (prev_raw_v is not None and prev_raw_v > 1e-6))
            kept.append((idx, _row_ts(r), cur_v, ep, ev_reset))
            prev_raw_v = cur_v

        if not kept:
            continue

        windows = []
        cur_win = []
        prev_ep = None
        prev_v = None
        for item in kept:
            idx, ts_val, v, ep, ev_reset = item
            is_win_reset = False
            if cur_win:
                if ep is not None and prev_ep is not None:
                    if (ep - prev_ep) > win_thresh and (prev_v > 1e-6 and v < prev_v - 1e-6):
                        is_win_reset = True
                elif ep is None and prev_v is not None and prev_v > 3.0 and v < 1.0:
                    is_win_reset = True
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

        last_clean_v = 0.0
        last_ts = None
        for wi, w in enumerate(windows):
            vals = [x[2] for x in w]
            wn = len(vals)
            v1 = list(vals)
            i = 1
            while i < wn:
                if v1[i] < v1[i - 1] - 1e-5:
                    rebound = False
                    for k in (1, 2):
                        if i + k < wn and v1[i + k] >= v1[i - 1] - 1e-5:
                            for j in range(i, i + k):
                                v1[j] = v1[i - 1]
                            i += k
                            rebound = True
                            break
                    if rebound:
                        continue
                i += 1

            smin = [0.0] * wn
            m_val = v1[-1]
            for i in range(wn - 1, -1, -1):
                if v1[i] < m_val:
                    m_val = v1[i]
                smin[i] = m_val

            for i, (orig_idx, ts_val, _raw_v, _ep, ev_reset) in enumerate(w):
                cv = smin[i]
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
                per_pool_data[pk][orig_idx] = (cv, cd, gap_sec, is_win_reset, reset_flag)
                last_clean_v = cv
                last_ts = ts_val

        last_carry = 0.0
        for idx in range(n_rows):
            if per_pool_data[pk][idx] is None:
                per_pool_data[pk][idx] = (last_carry, 0.0, 0.0, False, False)
            else:
                last_carry = per_pool_data[pk][idx][0]

    timeline = []
    for idx, r in enumerate(ok_rows):
        ts_val = _row_ts(r)
        idle_s = r.get("idleSec")
        is_pure_idle = (int(r.get("localActive") or 0) == 0) and (
            idle_s is not None and float(idle_s) > 180.0
        )
        g5_t, gw_t, c5_t, cw_t = (per_pool_data[pk][idx] for pk in pool_keys)
        max_gap = max(g5_t[2], gw_t[2], c5_t[2], cw_t[2])
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
                "idle": is_pure_idle,
                "idleSec": idle_s,
                "localActive": int(r.get("localActive") or 0),
                "events": list(r.get("events") or []),
                "resets": dict(r.get("resets") or {}),
                "orig_row": r,
            }
        )
    return timeline


def summarize_monitor_rows(rows, all_rows=None, since_ts=None, until_ts=None):
    """
    Compute denoised attribution totals, change rows, and rollback/reset counts over monitor rows.
    """
    ok_rows = [r for r in rows if isinstance(r, dict) and r.get("ok") and is_valid_ok_record(r)]
    chg_rows = [r for r in ok_rows if is_monitor_change_row(r)]
    rollbacks = [r for r in ok_rows if any(str(e).startswith("rollback:") for e in (r.get("events") or []))]

    source_rows = all_rows if all_rows is not None else rows
    full_timeline = clean_monitor_timeline(source_rows)

    sliced = []
    for item in full_timeline:
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

    for item in sliced:
        for pk in ("g5", "gw", "c5", "cw"):
            if item["reset_flags"][pk]:
                reset_counts[pk] += 1
            pool_up[pk] += item[f"d{pk}"]

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

    return {
        "total_rows": len(rows),
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
        "clean_rows": sliced,
        "start_clean": start_clean,
        "end_clean": end_clean,
    }


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
