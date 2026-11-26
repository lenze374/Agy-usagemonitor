#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Structured data aggregation, bilingual in-memory summary & control actions
for the Antigravity Usage Monitor Extensions Web UI.
Zero automatic disk report exports; zero external dependencies.
"""

import io
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta

SRC_DIR = os.path.dirname(os.path.realpath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from __init__ import __version__
import agy_monitor
import agy_usage
from common import CANONICAL_POOL_ORDER, fetch_quota_best, parse_iso_epoch, parse_local_naive
from paths import DATA_DIR, HOOKS_JSON_PATH, LEDGER_PATH, MONITOR_LOG

DEFAULT_POOL_LABELS = {
    "gemini_5h": "Gemini 5h",
    "gemini_weekly": "Gemini Weekly",
    "gemini_argon_5h": "Argon 5h",
    "gemini_argon_weekly": "Argon Weekly",
    "claude_gpt_5h": "Claude/GPT 5h",
    "claude_gpt_weekly": "Claude/GPT Weekly",
}


def _fmt_reset_short(iso_str):
    dt = parse_local_naive(iso_str)
    return dt.strftime("%m-%d %H:%M") if dt else "-"


def _build_model_rows(rows, weekly_rates, model_samples, rate_preset="none"):
    by_model = {}
    for r in rows:
        if r.get("status") == "long_gap":
            continue
        hook_m = str(r.get("model") or "auto")
        by_m = agy_usage.split_turn_steps_by_model(r)
        if by_m:
            turn_target = hook_m if hook_m in by_m else sorted(by_m.keys())[0]
            for m_k, tok_m in by_m.items():
                gm = by_model.setdefault(
                    m_k,
                    {"turns": 0, "steps": 0, "in": 0, "cr": 0, "out": 0},
                )
                if m_k == turn_target:
                    gm["turns"] += 1
                gm["steps"] += tok_m["count"]
                gm["in"] += tok_m["input"]
                gm["cr"] += tok_m["cacheRead"]
                gm["out"] += tok_m["output"]
            continue

        g = by_model.setdefault(hook_m, {"turns": 0, "steps": 0, "in": 0, "cr": 0, "out": 0})
        g["turns"] += 1
        g["steps"] += int(r.get("invocations", 1))
        tok = r.get("tokens") or {}
        g["in"] += int(tok.get("input") or 0)
        g["cr"] += int(tok.get("cacheRead") or 0)
        g["out"] += int(tok.get("output") or 0)

    out = []
    tot_est_all = 0.0
    for m in sorted(by_model.keys()):
        g = by_model[m]
        tot_prompt = g["in"] + g["cr"]
        hit_pct = round(100.0 * g["cr"] / tot_prompt, 1) if tot_prompt > 0 else 0.0
        w_rate, is_est_fb, src_m = agy_usage.resolve_model_rate(m, weekly_rates, rate_preset=rate_preset)
        n_clean = len(model_samples.get(m, []))
        eq_m = (
            agy_usage.W_INPUT * g["in"]
            + agy_usage.W_CACHE * g["cr"]
            + agy_usage.W_OUTPUT * g["out"]
        ) / 1_000_000.0
        est_gw = round(eq_m * w_rate, 4) if (w_rate is not None and (tot_prompt + g["out"]) > 0) else None
        if est_gw is not None:
            tot_est_all += est_gw
        if w_rate is None:
            rate_kind = "pending"
        elif str(src_m).startswith("preset:"):
            rate_kind = "preset"
        elif is_est_fb:
            rate_kind = "sibling"
        else:
            rate_kind = "calibrated"
        out.append(
            {
                "model": m,
                "turns": g["turns"],
                "steps": g["steps"],
                "inTok": g["in"],
                "crTok": g["cr"],
                "outTok": g["out"],
                "hitPct": hit_pct,
                "rateWeekly": round(w_rate, 4) if w_rate is not None else None,
                "estimated": is_est_fb,
                "rateKind": rate_kind,
                "rateSource": src_m,
                "samples": n_clean,
                "estGw": est_gw,
            }
        )
    for row in out:
        ev = row["estGw"]
        row["sharePct"] = round(100.0 * ev / tot_est_all, 1) if (ev is not None and tot_est_all > 1e-6) else 0.0
    out.sort(key=lambda x: (x["estGw"] is None, -(x["estGw"] or 0.0), -x["turns"]))
    return out


def _build_recent_rows(
    rows, overlapping, weekly_rates, recent_n=25, five_h_to_weekly=agy_usage.FIVE_H_TO_WEEKLY, rate_preset="none"
):
    items = agy_usage.build_recent_display_items(rows, expand_subagents=False)
    shown = items[-recent_n:] if recent_n > 0 else []
    result = []
    for item in reversed(shown):
        met = agy_usage.compute_display_item_metrics(
            item, overlapping, weekly_rates, five_h_to_weekly=five_h_to_weekly, rate_preset=rate_preset
        )
        result.append(
            {
                "endIso": (item["endIso"] or "")[:19].replace("T", " "),
                "workspace": item["workspace"],
                "model": met["m_disp"],
                "steps": met["steps"],
                "tokens": met["tok_str"],
                "est": met["est_str"].strip(),
                "obs": met["obs_str"].strip(),
                "status": met["st_label"],
                "contaminated": bool(met.get("contaminated")),
                "estEstimated": bool(met.get("est_estimated")),
            }
        )
    return result


def _downsample_clean_series(clean_rows, max_points=320):
    """Preserve all cleaned change points, resets, and offline gap endpoints up to max_points."""
    n = len(clean_rows)
    if n == 0:
        return []
    if n <= max_points:
        indices = list(range(n))
    else:
        step = max(1, n // max_points)
        idx_set = set(range(0, n, step))
        idx_set.add(n - 1)
        for i, c in enumerate(clean_rows):
            has_chg = any(c[k] > 1e-5 for k in ("dg5", "dgw", "dc5", "dcw"))
            has_rst = any(c["window_resets"].values()) or any(c["reset_flags"].values())
            if has_chg or has_rst or c["offline_gap"]:
                idx_set.add(i)
                if i > 0:
                    idx_set.add(i - 1)
        indices = sorted(idx_set)
        if len(indices) > max_points * 2:
            stride = max(1, len(indices) // (max_points * 2))
            kept = []
            for pos, orig_i in enumerate(indices):
                c = clean_rows[orig_i]
                if c["offline_gap"] or any(c["window_resets"].values()) or (pos % stride == 0):
                    kept.append(orig_i)
            if kept[-1] != n - 1:
                kept.append(n - 1)
            indices = kept

    pts = []
    for pos, i in enumerate(indices):
        c = clean_rows[i]
        gap_before = 0.0
        if pos > 0:
            gap_before = max(0.0, c["ts"] - clean_rows[indices[pos - 1]]["ts"])
        pts.append(
            {
                "ts": round(float(c["ts"]), 3),
                "iso": (c["iso"] or "")[:19].replace("T", " "),
                "g5": round(float(c["g5"]), 4),
                "gw": round(float(c["gw"]), 4),
                "c5": round(float(c["c5"]), 4),
                "cw": round(float(c["cw"]), 4),
                "rawG5": round(float(c["raw_g5"]), 4),
                "rawGw": round(float(c["raw_gw"]), 4),
                "rawCw": round(float(c["raw_cw"]), 4),
                "dg5": round(float(c["dg5"]), 4),
                "dgw": round(float(c["dgw"]), 4),
                "dcw": round(float(c["dcw"]), 4),
                "idle": bool(c["idle"]),
                "gapBeforeSec": round(gap_before, 1),
                "offlineGap": bool(c["offline_gap"]),
                "resetG5": bool(c["window_resets"]["g5"]),
                "resetGw": bool(c["window_resets"]["gw"]),
                "resetCw": bool(c["window_resets"]["cw"]),
                "events": [str(e) for e in (c["events"] or [])],
            }
        )
    return pts


def _build_attribution_buckets(
    window, now_dt, win_start_dt, ledger_rows, clean_rows, weekly_rates, rate_preset="none"
):
    """Build hourly (`today`/`24h`) or daily (`7d`) stacked attribution buckets."""
    buckets = []
    bmap = {}
    if window == "7d":
        start_day = win_start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        cur = start_day
        end_day = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        while cur <= end_day:
            key = cur.strftime("%Y-%m-%d")
            obj = {
                "key": key,
                "label": cur.strftime("%m-%d"),
                "gwLocal": 0.0,
                "gwMonActiveIdle": 0.0,
                "gwExtOffline": 0.0,
                "cwLocal": 0.0,
                "cwMonActiveIdle": 0.0,
                "cwExtOffline": 0.0,
            }
            buckets.append(obj)
            bmap[key] = obj
            cur += timedelta(days=1)
        key_fn = lambda dt: dt.strftime("%Y-%m-%d")
    else:
        cur = win_start_dt.replace(minute=0, second=0, microsecond=0)
        end_hr = now_dt.replace(minute=0, second=0, microsecond=0)
        while cur <= end_hr:
            key = cur.strftime("%Y-%m-%d %H")
            obj = {
                "key": key,
                "label": cur.strftime("%H:00"),
                "gwLocal": 0.0,
                "gwMonActiveIdle": 0.0,
                "gwExtOffline": 0.0,
                "cwLocal": 0.0,
                "cwMonActiveIdle": 0.0,
                "cwExtOffline": 0.0,
            }
            buckets.append(obj)
            bmap[key] = obj
            cur += timedelta(hours=1)
        key_fn = lambda dt: dt.strftime("%Y-%m-%d %H")

    for r in ledger_rows or []:
        if r.get("status") == "long_gap":
            continue
        end_dt = parse_local_naive(r.get("endIso") or r.get("startIso"))
        if not end_dt or end_dt < win_start_dt:
            continue
        b = bmap.get(key_fn(end_dt))
        if not b:
            continue
        est_v = agy_usage.row_theoretical_weekly(r, weekly_rates, rate_preset=rate_preset)
        if est_v is None:
            continue
        if agy_usage.is_third_party_model(r.get("model")):
            b["cwLocal"] += est_v
        else:
            b["gwLocal"] += est_v

    n_clean = len(clean_rows or [])
    for idx, c in enumerate(clean_rows or []):
        dt = parse_local_naive(c.get("iso"))
        if not dt:
            continue
        b = bmap.get(key_fn(dt))
        if not b:
            continue
        if c["dgw"] > 0:
            if "dgw_active" in c and "dgw_idle_on" in c and "dgw_offline" in c:
                b["gwExtOffline"] += float(c["dgw_offline"] or 0.0)
                active_plus_idle = float(c["dgw_active"] or 0.0) + float(c["dgw_idle_on"] or 0.0)
                b["gwMonActiveIdle"] += active_plus_idle
            elif c["pool_gaps"]["gw"] > 300.0 and c["idle"]:
                b["gwExtOffline"] += c["dgw"]
            else:
                distributed = False
                if c.get("raw_gw", c["gw"]) > c["gw"] + 0.01 and (idx + 1) < n_clean:
                    plat_val = c["gw"]
                    spanned_keys = []
                    seen_keys = set()
                    cur_key = b["key"]
                    spanned_keys.append(cur_key)
                    seen_keys.add(cur_key)
                    for j in range(idx + 1, n_clean):
                        cj = clean_rows[j]
                        if cj["pool_gaps"]["gw"] > 300.0 or (cj.get("window_resets") or {}).get("gw"):
                            break
                        if abs(cj["gw"] - plat_val) > 1e-4:
                            break
                        if cj.get("raw_gw", cj["gw"]) <= plat_val + 0.01:
                            break
                        dt_j = parse_local_naive(cj.get("iso"))
                        if dt_j:
                            kj = key_fn(dt_j)
                            if kj in bmap and kj not in seen_keys:
                                spanned_keys.append(kj)
                                seen_keys.add(kj)
                    if len(spanned_keys) >= 2:
                        sum_loc = sum(bmap[k]["gwLocal"] for k in spanned_keys)
                        if sum_loc > 1e-5:
                            to_spread = min(c["dgw"], sum_loc)
                            for k in spanned_keys:
                                bmap[k]["gwMonActiveIdle"] += to_spread * (bmap[k]["gwLocal"] / sum_loc)
                            rem = c["dgw"] - to_spread
                            if rem > 1e-6:
                                b["gwMonActiveIdle"] += rem
                            distributed = True
                if not distributed:
                    b["gwMonActiveIdle"] += c["dgw"]
        if c["dcw"] > 0:
            if c["pool_gaps"]["cw"] > 300.0 and c["idle"]:
                b["cwExtOffline"] += c["dcw"]
            else:
                b["cwMonActiveIdle"] += c["dcw"]

    out = []
    for b in buckets:
        gw_loc = round(b["gwLocal"], 4)
        gw_off = round(b["gwExtOffline"], 4)
        gw_ext_on = round(max(0.0, b["gwMonActiveIdle"] - b["gwLocal"]), 4)
        gw_tot = round(gw_loc + gw_ext_on + gw_off, 4)

        cw_loc = round(b["cwLocal"], 4)
        cw_off = round(b["cwExtOffline"], 4)
        cw_ext_on = round(max(0.0, b["cwMonActiveIdle"] - b["cwLocal"]), 4)
        cw_tot = round(cw_loc + cw_ext_on + cw_off, 4)

        out.append(
            {
                "key": b["key"],
                "label": b["label"],
                "gwLocal": gw_loc,
                "gwExtOnline": gw_ext_on,
                "gwExtOffline": gw_off,
                "gwTotal": gw_tot,
                "cwLocal": cw_loc,
                "cwExtOnline": cw_ext_on,
                "cwExtOffline": cw_off,
                "cwTotal": cw_tot,
            }
        )
    return out


def _build_external_bursts(
    clean_rows, ledger_rows, weekly_rates=None, max_bursts=8, five_h_ratio=4.0, rate_preset="none"
):
    """
    Group consecutive external consumption minutes (gap <= 20m) into readable event bursts.
    Bridges active clusters split across a constant suffix-min clamped plateau (`raw_gw > gw`).
    """
    weekly_rates = weekly_rates or {}
    five_h_to_w = 1.0 / max(0.5, float(five_h_ratio or 4.0))
    cg_intervals = []
    gem_turns = []
    for r in ledger_rows or []:
        if r.get("status") == "long_gap":
            continue
        s_ep = float(r.get("startTs") or parse_iso_epoch(r.get("startIso")) or 0.0)
        e_ep = float(r.get("ts") or parse_iso_epoch(r.get("endIso")) or s_ep)
        if e_ep <= 0:
            continue
        if agy_usage.is_third_party_model(r.get("model")):
            cg_intervals.append((s_ep - 60.0, e_ep + 120.0))
        else:
            est = agy_usage.row_theoretical_weekly(r, weekly_rates, rate_preset=rate_preset)
            if est is None:
                obs_v, _ = agy_usage.turn_measured_weekly_delta(r, five_h_to_weekly=five_h_to_w)
                est = float(obs_v or 0.0)
            gem_turns.append((s_ep, e_ep, float(est)))

    def _has_local_cg(ts_val):
        return any(a <= ts_val <= b for a, b in cg_intervals)

    conc_map = {}
    active_clusters = []
    cur_cl = None
    for idx, c in enumerate(clean_rows or []):
        is_active_tick = (not c["idle"]) and (c["pool_gaps"]["gw"] <= 300.0)
        if is_active_tick:
            if cur_cl is None or (c["ts"] - cur_cl["end"]) > 180.0:
                if cur_cl is not None:
                    active_clusters.append(cur_cl)
                cur_cl = {"start": c["ts"], "end": c["ts"], "indices": [idx]}
            else:
                cur_cl["end"] = c["ts"]
                cur_cl["indices"].append(idx)
        else:
            if cur_cl is not None:
                active_clusters.append(cur_cl)
                cur_cl = None
    if cur_cl is not None:
        active_clusters.append(cur_cl)

    def _can_bridge_clamped_plateau(prev_cl, next_cl):
        i0 = prev_cl["indices"][-1]
        i1 = next_cl["indices"][0]
        if i1 <= i0:
            return False
        plat = clean_rows[i0]["gw"]
        if clean_rows[i0].get("raw_gw", plat) <= plat + 1e-4:
            return False
        for k in range(i0 + 1, i1 + 1):
            ck = clean_rows[k]
            if ck["pool_gaps"]["gw"] > 300.0:
                return False
            if (ck.get("window_resets") or {}).get("gw"):
                return False
            if abs(ck["gw"] - plat) > 1e-4:
                return False
            if k < i1 and ck.get("raw_gw", ck["gw"]) <= plat + 1e-4:
                return False
        return True

    merged_clusters = []
    for cl in active_clusters:
        if merged_clusters and _can_bridge_clamped_plateau(merged_clusters[-1], cl):
            merged_clusters[-1]["end"] = cl["end"]
            merged_clusters[-1]["indices"].extend(cl["indices"])
        else:
            merged_clusters.append(cl)

    ratio_5h = float(five_h_ratio or 4.0)
    cluster_deficits = []
    for cl in merged_clusters:
        mon_gw = sum(clean_rows[i]["dgw"] for i in cl["indices"])
        local_gw = sum(
            est for s_ep, e_ep, est in gem_turns
            if e_ep >= (cl["start"] - 30.0) and s_ep <= (cl["end"] + 90.0)
        )
        excess = mon_gw - local_gw
        if mon_gw > 0.15 and excess > 0.15:
            for i in cl["indices"]:
                dgw_i = clean_rows[i]["dgw"]
                if dgw_i > 1e-4:
                    conc_gw = excess * (dgw_i / mon_gw)
                    conc_g5 = min(clean_rows[i]["dg5"], conc_gw * ratio_5h)
                    conc_map[i] = (conc_gw, conc_g5)
        elif (-excess) > 0.15:
            cluster_deficits.append({"start": cl["start"], "remainingDeficit": -excess})

    events = []
    for idx, c in enumerate(clean_rows or []):
        conc_gw, conc_g5 = conc_map.get(idx, (0.0, 0.0))
        has_token_corr = "dgw_idle_on" in c
        is_off_gem = bool(c["pool_gaps"]["gw"] > 300.0 and c["idle"])
        if has_token_corr:
            idle_gem_gw = float(c["dgw_offline"] if is_off_gem else c["dgw_idle_on"])
            idle_gem_g5 = (
                float(c["dg5"]) * (idle_gem_gw / float(c["dgw"]))
                if float(c.get("dgw") or 0.0) > 1e-6
                else (float(c["dg5"]) if c["idle"] and idle_gem_gw > 1e-4 else 0.0)
            )
            is_idle_or_off_gem = (
                idle_gem_gw > 1e-4 or (idle_gem_g5 > 0.01 and not c.get("token_corrected_gw"))
            ) and (c["idle"] or is_off_gem)
        else:
            idle_gem_gw = float(c["dgw"])
            idle_gem_g5 = float(c["dg5"])
            is_idle_or_off_gem = (c["dgw"] > 1e-4 or c["dg5"] > 0.01) and (c["idle"] or is_off_gem)

        is_conc_gem = conc_gw > 1e-4
        gem_gw_add = idle_gem_gw if is_idle_or_off_gem else conc_gw
        gem_g5_add = idle_gem_g5 if is_idle_or_off_gem else conc_g5

        # Fallback for direct callers without pre-applied `apply_local_token_correction`:
        if (
            not has_token_corr
            and is_idle_or_off_gem
            and c["idle"]
            and not is_off_gem
            and 0.98 <= c["dgw"] <= 1.05
            and 0.98 <= c["dg5"] <= 1.05
            and abs(c["dg5"] - c["dgw"]) <= 0.05
        ):
            for dcl in cluster_deficits:
                if dcl["remainingDeficit"] > 0.15 and 0.0 < (dcl["start"] - c["ts"]) <= 600.0:
                    absorbed = min(gem_gw_add, dcl["remainingDeficit"])
                    dcl["remainingDeficit"] -= absorbed
                    gem_gw_add = max(0.0, gem_gw_add - absorbed)
                    gem_g5_add = 0.0 if gem_gw_add < 0.02 else max(0.0, gem_g5_add - absorbed * ratio_5h)
                    break
            if gem_gw_add < 1e-4 and gem_g5_add < 0.01:
                is_idle_or_off_gem = False

        is_gem_ext = is_idle_or_off_gem or is_conc_gem
        is_cg_ext = (c["dcw"] > 1e-4 or c["dc5"] > 0.01) and (
            c["idle"] or c["pool_gaps"]["cw"] > 300.0 or not _has_local_cg(c["ts"])
        )
        if not (is_gem_ext or is_cg_ext):
            continue
        is_off = (is_idle_or_off_gem and is_off_gem) or (
            is_cg_ext and c["pool_gaps"]["cw"] > 300.0
        )
        events.append(
            (
                c,
                is_gem_ext,
                is_cg_ext,
                is_off,
                is_conc_gem,
                is_idle_or_off_gem and not is_off,
                gem_gw_add,
                gem_g5_add,
                conc_gw,
            )
        )

    bursts = []
    cur = None
    for c, is_gem, is_cg, is_off, is_conc, is_idle_on, gem_gw_add, gem_g5_add, conc_gw in events:
        kind = "offline" if is_off else "online"
        if (
            cur is not None
            and cur["kind"] == kind
            and not is_off
            and (c["ts"] - cur["endTs"]) <= 1200.0
        ):
            cur["endTs"] = c["ts"]
            cur["endIso"] = (c["iso"] or "")[:19].replace("T", " ")
            cur["gwDelta"] += gem_gw_add
            cur["g5Delta"] += gem_g5_add
            cur["cwDelta"] += c["dcw"] if is_cg else 0.0
            cur["concurrentGwDelta"] += conc_gw
            cur["tickCount"] += 1
            if is_gem:
                cur["hasGem"] = True
            if is_cg:
                cur["hasCg"] = True
            if is_conc:
                cur["hasConcurrent"] = True
            if is_idle_on:
                cur["hasIdleOnline"] = True
        else:
            if cur is not None:
                bursts.append(cur)
            start_ts = c["ts"] - c["gap_sec"] if is_off and c["gap_sec"] > 0 else c["ts"]
            start_iso = (
                datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S")
                if is_off and c["gap_sec"] > 0
                else (c["iso"] or "")[:19].replace("T", " ")
            )
            cur = {
                "startTs": start_ts,
                "endTs": c["ts"],
                "startIso": start_iso,
                "endIso": (c["iso"] or "")[:19].replace("T", " "),
                "kind": kind,
                "hasGem": is_gem,
                "hasCg": is_cg,
                "hasConcurrent": bool(is_conc),
                "hasIdleOnline": bool(is_idle_on),
                "gwDelta": gem_gw_add,
                "g5Delta": gem_g5_add,
                "cwDelta": c["dcw"] if is_cg else 0.0,
                "concurrentGwDelta": conc_gw,
                "tickCount": 1,
            }
    if cur is not None:
        bursts.append(cur)

    out = []
    for b in reversed(bursts):
        if b["gwDelta"] < 0.005 and b["cwDelta"] < 0.005 and b["g5Delta"] < 0.05:
            continue
        if b["hasGem"] and b["hasCg"]:
            pool = "both"
        elif b["hasCg"]:
            pool = "claude_gpt"
        else:
            pool = "gemini"
        dur_min = max(1, int(round((b["endTs"] - b["startTs"]) / 60.0)))
        out.append(
            {
                "startIso": b["startIso"],
                "endIso": b["endIso"],
                "durationMin": dur_min,
                "kind": b["kind"],
                "pool": pool,
                "hasConcurrent": bool(b["hasConcurrent"]),
                "hasIdleOnline": bool(b["hasIdleOnline"]),
                "concurrentGwDelta": round(b["concurrentGwDelta"], 4),
                "gwDelta": round(b["gwDelta"], 4),
                "g5Delta": round(b["g5Delta"], 4),
                "cwDelta": round(b["cwDelta"], 4),
                "tickCount": b["tickCount"],
            }
        )
        if len(out) >= max_bursts:
            break
    return out


def _fmt_human_change_tag(r, c_item, kind):
    if kind == "offline" and c_item:
        return f"休眠期间({agy_monitor._fmt_gap_duration(c_item['gap_sec'])})"
    if kind == "reset":
        return "额度重置"
    idle_s = r.get("idleSec")
    if kind == "idle":
        if idle_s is not None:
            return f"别人用了(闲置{agy_monitor._fmt_gap_duration(float(idle_s))})"
        return "别人用了"
    act = int(r.get("localActive") or 0)
    if act > 0 or (idle_s is not None and float(idle_s) <= 65.0):
        return "你正在用"
    if idle_s is not None:
        return f"你刚用完({int(float(idle_s))}秒前)"
    return "你在使用"


def _order_pool_keys(keys):
    seen = set()
    ordered = []
    for k in CANONICAL_POOL_ORDER:
        if k in keys and k not in seen:
            ordered.append(k)
            seen.add(k)
    for k in sorted(keys):
        if k not in seen:
            ordered.append(k)
            seen.add(k)
    return ordered


def build_dashboard_payload(window="24h", recent_n=25, live=True):
    """Build complete JSON payload for the Extensions sidebar dashboard."""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rate_preset = agy_usage.get_rate_preset()

    live_snap = None
    live_ms = 0
    if live:
        live_snap, live_ms = fetch_quota_best(timeout_sec=5.0)

    mon_all = agy_monitor.load_monitor_rows(MONITOR_LOG)
    ledger_rows = agy_usage.load_entries(LEDGER_PATH)
    weekly_rates = {}
    model_samples = {}
    days7_start = now - timedelta(days=7)
    quota_wk_start = agy_usage.detect_quota_week_start(
        ledger_rows, days7_start, monitor_rows=mon_all, pool_key="gemini_weekly"
    )
    cg_wk_start = agy_usage.detect_quota_week_start(
        ledger_rows, days7_start, monitor_rows=mon_all, pool_key="claude_gpt_weekly"
    )

    if ledger_rows:
        agy_usage.annotate_pool_anomalies(ledger_rows)
        overlapping, all_clusters = agy_usage.build_overlap_clusters(ledger_rows)
        gem_ratio, gem_n, gem_cal = agy_usage.estimate_five_h_ratio(
            ledger_rows, monitor_rows=mon_all, pool="gemini"
        )
        cg_ratio, cg_n, cg_cal = agy_usage.estimate_five_h_ratio(
            ledger_rows, monitor_rows=mon_all, pool="claude_gpt"
        )
        five_h_to_w = 1.0 / gem_ratio
        weekly_rates, model_samples = agy_usage.calibrate_weekly_model_rates(
            ledger_rows, overlapping, all_clusters, monitor_rows=mon_all
        )
        today_sum = agy_usage.summarize_period(
            ledger_rows, today_start, weekly_rates, five_h_to_weekly=five_h_to_w, rate_preset=rate_preset
        )
        week_sum = agy_usage.summarize_period(
            ledger_rows, quota_wk_start, weekly_rates, five_h_to_weekly=five_h_to_w, rate_preset=rate_preset
        )
        model_rows = _build_model_rows(ledger_rows, weekly_rates, model_samples, rate_preset=rate_preset)
        recent_rows = _build_recent_rows(
            ledger_rows,
            overlapping,
            weekly_rates,
            recent_n=recent_n,
            five_h_to_weekly=five_h_to_w,
            rate_preset=rate_preset,
        )
        missing_tok = sum(1 for r in ledger_rows if not (r.get("tokens") or {}).get("billedSteps"))
    else:
        gem_ratio, gem_n, gem_cal = agy_usage.estimate_five_h_ratio(
            [], monitor_rows=mon_all, pool="gemini"
        )
        cg_ratio, cg_n, cg_cal = agy_usage.estimate_five_h_ratio(
            [], monitor_rows=mon_all, pool="claude_gpt"
        )
        five_h_to_w = 1.0 / gem_ratio
        today_sum = {
            "turns": 0, "steps": 0, "cg_turns": 0, "cg_steps": 0,
            "in_tok": 0, "cr_tok": 0, "out_tok": 0,
            "local_est_gw": 0.0, "local_est_cw": 0.0, "has_fallback_est": False,
            "active_gw": 0.0, "span_gw": 0.0, "active_cw": 0.0, "span_cw": 0.0,
            "long_gap_count": 0, "false_reset_count": 0,
        }
        week_sum = dict(today_sum)
        model_rows = []
        recent_rows = []
        missing_tok = 0

    # Dynamic multi-subscription pool rendering
    pools_out = {}
    live_pools = (live_snap or {}).get("pools") or {}
    raw_order = (live_snap or {}).get("poolOrder") or list(live_pools.keys())
    pool_order = _order_pool_keys(raw_order)
    for key in pool_order:
        p = live_pools.get(key)
        if not isinstance(p, dict) or p.get("usedPercent") is None:
            continue
        used = round(float(p["usedPercent"]), 4)
        rem = round(max(0.0, 100.0 - used), 4)
        label = DEFAULT_POOL_LABELS.get(key) or p.get("groupLabel") or p.get("bucketId") or key
        pools_out[key] = {
            "key": key,
            "label": label,
            "bucketId": p.get("bucketId") or key,
            "family": p.get("family") or "other",
            "cadence": p.get("cadence") or "other",
            "used": used,
            "remaining": rem,
            "resetsAt": p.get("resetsAt") or "",
            "resetShort": _fmt_reset_short(p.get("resetsAt")),
            "description": p.get("description") or "",
            "disabled": bool(p.get("disabled")),
        }
    pool_order = [k for k in pool_order if k in pools_out]
    billing_mode = (live_snap or {}).get("billingMode") or ("subscription" if pools_out else "offline")

    if window == "today":
        win_start_dt = today_start
    elif window == "7d":
        win_start_dt = now - timedelta(days=7)
    else:
        window = "24h"
        win_start_dt = now - timedelta(hours=24)

    cutoff_ts = win_start_dt.timestamp()
    mon_win = [r for r in mon_all if agy_monitor._row_ts(r) >= cutoff_ts]
    raw_clean_all = agy_monitor.clean_monitor_timeline(mon_all, five_h_to_weekly=five_h_to_w)
    clean_all, _corr_meta = agy_usage.apply_local_token_correction(
        raw_clean_all,
        ledger_rows,
        weekly_rates,
        five_h_to_weekly=five_h_to_w,
        rate_preset=rate_preset,
    )
    win_summary = agy_monitor.summarize_clean_rows(mon_win, clean_all, since_ts=cutoff_ts)
    all_summary = agy_monitor.summarize_clean_rows(mon_all, clean_all)
    today_mon_summary = agy_monitor.summarize_clean_rows(
        mon_all, clean_all, since_ts=today_start.timestamp()
    )
    wk_gem_summary = agy_monitor.summarize_clean_rows(
        mon_all, clean_all, since_ts=quota_wk_start.timestamp()
    )
    wk_cg_summary = (
        wk_gem_summary
        if cg_wk_start == quota_wk_start
        else agy_monitor.summarize_clean_rows(
            mon_all, clean_all, since_ts=cg_wk_start.timestamp()
        )
    )
    ts_24h = (now - timedelta(hours=24)).timestamp()
    ts_7d = (now - timedelta(days=7)).timestamp()
    clean_24h = [c for c in clean_all if c["ts"] >= ts_24h]
    clean_7d = [c for c in clean_all if c["ts"] >= ts_7d]

    rec_today = agy_usage.reconcile_shared_pools(
        ledger_rows, mon_all, weekly_rates, today_start,
        live_snap=live_snap, mon_summary=today_mon_summary,
        five_h_to_weekly=five_h_to_w, rate_preset=rate_preset,
    )
    rec_wk_gem = agy_usage.reconcile_shared_pools(
        ledger_rows, mon_all, weekly_rates, quota_wk_start,
        live_snap=live_snap, mon_summary=wk_gem_summary,
        five_h_to_weekly=five_h_to_w, rate_preset=rate_preset,
    )
    rec_wk_cg = (
        rec_wk_gem
        if cg_wk_start == quota_wk_start
        else agy_usage.reconcile_shared_pools(
            ledger_rows, mon_all, weekly_rates, cg_wk_start,
            live_snap=live_snap, mon_summary=wk_cg_summary,
            five_h_to_weekly=five_h_to_w, rate_preset=rate_preset,
        )
    )
    rec_win = agy_usage.reconcile_shared_pools(
        ledger_rows, mon_all, weekly_rates, win_start_dt,
        live_snap=live_snap, mon_summary=win_summary,
        five_h_to_weekly=five_h_to_w, rate_preset=rate_preset,
    )

    clean_win = win_summary.get("clean_rows") or []
    chg_candidates = []
    for c in clean_win:
        is_win_rst = any((c.get("window_resets") or {}).values())
        has_visible_delta = (
            c["dgw"] >= 0.0005
            or c["dcw"] >= 0.0005
            or c["dg5"] >= 0.005
        )
        if is_win_rst or has_visible_delta:
            chg_candidates.append((c["orig_row"], c, is_win_rst))

    recent_changes = []
    for r, c_item, is_win_rst in reversed(chg_candidates[-50:]):
        is_off = bool(c_item["offline_gap"])
        is_rst = bool(is_win_rst)
        is_idle = bool(c_item["idle"])
        if is_off:
            kind = "offline"
        elif is_rst:
            kind = "reset"
        elif is_idle:
            kind = "idle"
        else:
            kind = "active"

        recent_changes.append(
            {
                "iso": (r.get("iso") or "")[:19].replace("T", " "),
                "g5": round(c_item["g5"], 4),
                "dg5": round(c_item["dg5"], 4),
                "gw": round(c_item["gw"], 4),
                "dgw": round(c_item["dgw"], 4),
                "cw": round(c_item["cw"], 4),
                "dcw": round(c_item["dcw"], 4),
                "rawDg5": round(float(r.get("dg5") or 0.0), 4),
                "rawDgw": round(float(r.get("dgw") or 0.0), 4),
                "idleSec": r.get("idleSec"),
                "gapSec": c_item.get("gap_sec"),
                "localActive": int(r.get("localActive") or 0),
                "tag": agy_monitor.fmt_idle_tag(r),
                "tagHuman": _fmt_human_change_tag(r, c_item, kind),
                "kind": kind,
            }
        )

    ui_version = ""
    try:
        ui_version = str(int(os.stat(os.path.join(SRC_DIR, "dashboard_ui.py")).st_mtime))
    except OSError:
        pass

    recent_fail_streak = 0
    for r in reversed(mon_all):
        if r.get("ok"):
            break
        recent_fail_streak += 1
    transcript_sync_turns = sum(1 for r in ledger_rows if r.get("status") == "transcript_only")

    return {
        "ok": True,
        "uiVersion": ui_version,
        "generatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "hookEnabled": agy_usage.get_hook_enabled(HOOKS_JSON_PATH),
        "ratePreset": rate_preset,
        "live": {
            "source": (live_snap or {}).get("source") or "offline",
            "billingMode": billing_mode,
            "plan": (live_snap or {}).get("plan") or "",
            "ms": live_ms,
            "poolOrder": pool_order,
            "pools": pools_out,
        },
        "periods": {
            "today": {
                "turns": today_sum["turns"],
                "steps": today_sum["steps"],
                "inTok": today_sum["in_tok"],
                "crTok": today_sum["cr_tok"],
                "outTok": today_sum["out_tok"],
                "localEst": round(today_sum["local_est_gw"], 4),
                "localEstCg": round(today_sum["local_est_cw"], 4),
                "hasFallbackEst": bool(today_sum.get("has_fallback_est")),
                "active": round(today_sum["active_gw"], 4),
                "span": round(today_sum["span_gw"], 4),
            },
            "week": {
                "turns": week_sum["turns"],
                "steps": week_sum["steps"],
                "inTok": week_sum["in_tok"],
                "crTok": week_sum["cr_tok"],
                "outTok": week_sum["out_tok"],
                "localEst": round(week_sum["local_est_gw"], 4),
                "localEstCg": round(week_sum["local_est_cw"], 4),
                "hasFallbackEst": bool(week_sum.get("has_fallback_est")),
                "active": round(week_sum["active_gw"], 4),
                "span": round(week_sum["span_gw"], 4),
            },
        },
        "reconciliation": {
            "today": {
                "hasFallbackEst": rec_today["hasFallbackEst"],
                "gemini": rec_today["gemini"],
                "claude_gpt": rec_today["claude_gpt"],
            },
            "week": {
                "geminiSince": rec_wk_gem["sinceIso"],
                "claudeGptSince": rec_wk_cg["sinceIso"],
                "hasFallbackEst": rec_wk_gem["hasFallbackEst"],
                "gemini": rec_wk_gem["gemini"],
                "claude_gpt": rec_wk_cg["claude_gpt"],
            },
            "window": {
                "hasFallbackEst": rec_win["hasFallbackEst"],
                "gemini": rec_win["gemini"],
                "claude_gpt": rec_win["claude_gpt"],
            },
        },
        "monitor": {
            "window": window,
            "totalTicksAll": all_summary["total_rows"],
            "okTicksAll": len(all_summary["ok_rows"]),
            "totalTicksWin": win_summary["total_rows"],
            "okTicksWin": len(win_summary["ok_rows"]),
            "changeCountWin": len(win_summary["chg_rows"]),
            "rollbackCountWin": len(win_summary["rollbacks"]),
            "attributionWin": {
                "activeGw": round(win_summary["active_gw_up"], 4),
                "idleGw": round(win_summary["idle_gw_up"], 4),
                "onlineIdleGw": round(win_summary["online_idle_gw_up"], 4),
                "offlineGw": round(win_summary["offline_gw_up"], 4),
                "activeCw": round(win_summary["active_cw_up"], 4),
                "idleCw": round(win_summary["idle_cw_up"], 4),
                "onlineIdleCw": round(win_summary["online_idle_cw_up"], 4),
                "offlineCw": round(win_summary["offline_cw_up"], 4),
            },
            "attributionAll": {
                "activeGw": round(all_summary["active_gw_up"], 4),
                "idleGw": round(all_summary["idle_gw_up"], 4),
                "onlineIdleGw": round(all_summary["online_idle_gw_up"], 4),
                "offlineGw": round(all_summary["offline_gw_up"], 4),
                "activeCw": round(all_summary["active_cw_up"], 4),
                "idleCw": round(all_summary["idle_cw_up"], 4),
                "onlineIdleCw": round(all_summary["online_idle_cw_up"], 4),
                "offlineCw": round(all_summary["offline_cw_up"], 4),
            },
            "series": _downsample_clean_series(clean_win),
            "buckets": _build_attribution_buckets(
                window, now, win_start_dt, ledger_rows, clean_win, weekly_rates, rate_preset=rate_preset
            ),
            "externalBursts": _build_external_bursts(
                clean_win, ledger_rows, weekly_rates, five_h_ratio=gem_ratio, rate_preset=rate_preset
            ),
            "externalBursts24h": _build_external_bursts(
                clean_24h, ledger_rows, weekly_rates, five_h_ratio=gem_ratio, rate_preset=rate_preset
            ),
            "externalBursts7d": _build_external_bursts(
                clean_7d, ledger_rows, weekly_rates, five_h_ratio=gem_ratio, rate_preset=rate_preset
            ),
            "recentChanges": recent_changes,
        },
        "models": model_rows,
        "recentTurns": recent_rows,
        "missingTokens": missing_tok,
        "diagnostics": {
            "version": __version__,
            "dataDir": DATA_DIR,
            "platform": sys.platform,
            "pythonVersion": sys.version.split()[0],
            "billingMode": billing_mode,
            "plan": (live_snap or {}).get("plan") or "",
            "ratePreset": rate_preset,
            "poolKeys": pool_order,
            "geminiRatio": {"ratio": round(gem_ratio, 4), "samples": gem_n, "calibrated": gem_cal},
            "cgRatio": {"ratio": round(cg_ratio, 4), "samples": cg_n, "calibrated": cg_cal},
            "ledgerCount": len(ledger_rows),
            "transcriptSyncTurns": transcript_sync_turns,
            "monitorCount": len(mon_all),
            "consecutiveMonFailures": recent_fail_streak,
        },
    }


def _render_in_memory_summary(lang="zh-CN"):
    """Build a crisp plain-text summary strictly in memory (zero disk writes)."""
    payload = build_dashboard_payload(window="24h", recent_n=10, live=False)
    is_en = str(lang or "").lower().startswith("en")
    diag = payload["diagnostics"]
    rec_wk = payload["reconciliation"]["week"]
    gem = rec_wk["gemini"]
    cg = rec_wk["claude_gpt"]
    today_p = payload["periods"]["today"]
    week_p = payload["periods"]["week"]

    lines = []
    if is_en:
        lines.append(f"Antigravity Usage Monitor Summary ({payload['generatedAt']})")
        lines.append(
            f"Version: v{diag['version']} | Billing: {diag['billingMode']} | Preset: {diag.get('ratePreset', 'none')} | Gemini 5h:Weekly = {diag['geminiRatio']['ratio']:.2f}:1"
        )
        lines.append("")
        lines.append(f"[Today] Turns/Steps: {today_p['turns']}/{today_p['steps']} | Tokens: {today_p['inTok']:,}/{today_p['crTok']:,}/{today_p['outTok']:,} | Local Est: -{today_p['localEst']:.4f}%")
        lines.append(f"[This Week] Turns/Steps: {week_p['turns']}/{week_p['steps']} | Gemini Total: -{gem['poolTotal']:.3f}% (Local: -{gem['localEst']:.4f}%, External: -{gem['externalTotal']:.4f}%, Sleep: -{gem['monOffline']:.4f}%)")
        if float(gem.get("tokenCorrectedGw") or 0.0) > 0.01:
            lines.append(f"  * Adjusted {gem['tokenCorrectedGw']:.2f}% pre-reservation shift via local tokens")
        if float(gem.get("pendingPreReservation") or 0.0) > 0.05:
            lines.append(f"  * Tail includes ~{gem['pendingPreReservation']:.2f}% pending pre-reservation (stripped via local tokens)")
        lines.append(f"[Claude/GPT Week] Total: -{cg['poolTotal']:.3f}% (Local: -{cg['localEst']:.4f}%, External: -{cg['externalTotal']:.4f}%)")
        lines.append("")
        lines.append("[Calibrated Models]")
        for m in payload["models"][:15]:
            suffix = " (preset)" if m.get("rateKind") == "preset" else (" (est)" if m.get("estimated") else "")
            r_str = f"{m['rateWeekly']:.4f}%/1M EqIn{suffix}" if m["rateWeekly"] is not None else "pending"
            lines.append(f"  - {m['model']}: {m['turns']}t/{m['steps']}s, hit={m['hitPct']:.1f}%, rate={r_str}")
    else:
        lines.append(f"Antigravity Usage Monitor 用量摘要 ({payload['generatedAt']})")
        lines.append(
            f"版本: v{diag['version']} | 计费模式: {diag['billingMode']} | 单价预设: {diag.get('ratePreset', 'none')} | Gemini 5h:周 比例 = {diag['geminiRatio']['ratio']:.2f}:1"
        )
        lines.append("")
        lines.append(f"[今日] 对话/步数: {today_p['turns']}/{today_p['steps']} | Token(In/Cache/Out): {today_p['inTok']:,}/{today_p['crTok']:,}/{today_p['outTok']:,} | 本机理论: -{today_p['localEst']:.4f}%")
        lines.append(f"[本周] 对话/步数: {week_p['turns']}/{week_p['steps']} | Gemini 全池: -{gem['poolTotal']:.3f}% (本机: -{gem['localEst']:.4f}%, 他人: -{gem['externalTotal']:.4f}%, 休眠: -{gem['monOffline']:.4f}%)")
        if float(gem.get("tokenCorrectedGw") or 0.0) > 0.01:
            lines.append(f"  * 已按本机 Token 修正预扣错位 {gem['tokenCorrectedGw']:.2f}%")
        if float(gem.get("pendingPreReservation") or 0.0) > 0.05:
            lines.append(f"  * 当前尾部含未结算预扣约 {gem['pendingPreReservation']:.2f}%（已按 Token 暂扣除）")
        lines.append(f"[Claude/GPT 本周] 全池: -{cg['poolTotal']:.3f}% (本机: -{cg['localEst']:.4f}%, 他人: -{cg['externalTotal']:.4f}%)")
        lines.append("")
        lines.append("[已校准模型]")
        for m in payload["models"][:15]:
            suffix = " (预设)" if m.get("rateKind") == "preset" else (" (估)" if m.get("estimated") else "")
            r_str = f"{m['rateWeekly']:.4f}%/1M等效{suffix}" if m["rateWeekly"] is not None else "待采集"
            lines.append(f"  - {m['model']}: {m['turns']}轮/{m['steps']}步, 命中={m['hitPct']:.1f}%, 单价={r_str}")

    return "\n".join(lines) + "\n"


def perform_action(action, params=None):
    """Execute safe maintenance actions triggered from the sidebar UI."""
    params = params or {}
    if action == "export_summary":
        lang = str(params.get("lang") or "zh-CN")
        today_str = datetime.now().strftime("%Y-%m-%d")
        return {
            "ok": True,
            "action": action,
            "filename": f"agy-usage-summary-{today_str}.txt",
            "content": _render_in_memory_summary(lang=lang),
        }
    if action == "backfill":
        buf = io.StringIO()
        with redirect_stdout(buf):
            agy_usage.run_backfill()
        msg = buf.getvalue().strip() or "Backfill check finished"
        return {"ok": True, "action": action, "message": msg}
    if action == "toggle_hook":
        cur = agy_usage.get_hook_enabled(HOOKS_JSON_PATH)
        target = params.get("enabled")
        new_val = (not cur) if target is None else bool(target)
        buf = io.StringIO()
        with redirect_stdout(buf):
            agy_usage.set_hook_enabled(new_val, HOOKS_JSON_PATH)
        return {
            "ok": True,
            "action": action,
            "hookEnabled": agy_usage.get_hook_enabled(HOOKS_JSON_PATH),
            "message": buf.getvalue().strip() or ("Enabled (ON)" if new_val else "Paused (OFF)"),
        }
    if action == "set_preset":
        preset = str(params.get("preset") or "none").strip()
        if preset not in agy_usage.VALID_RATE_PRESETS:
            return {"ok": False, "error": f"invalid_preset:{preset}"}
        chosen = agy_usage.set_rate_preset(preset)
        return {
            "ok": True,
            "action": action,
            "ratePreset": chosen,
            "message": f"Rate preset updated: {chosen}",
        }
    return {"ok": False, "error": f"unknown_action:{action}"}
