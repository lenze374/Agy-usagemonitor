#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Viewer, Backfiller & Model Calibrator for Antigravity Local Quota + Token Tracker.
- Default mode (`agy-usage`) is 100% offline (reads local ledger.jsonl & monitor.jsonl only).
- Dynamically estimates the account's 5h:Weekly pool ratio (e.g. 4:1 on Ultra) instead of
  hardcoding a single tier, and supports weekly-only buckets (e.g. Argon).
- Compatible with Python 3.9+ across macOS, Linux, and Windows (stdlib only).
"""

import argparse
import bisect
import json
import os
import shutil
import statistics
import sys
from datetime import datetime, timedelta

SRC_DIR = os.path.dirname(os.path.realpath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from common import (
    atomic_write_text,
    disp_width,
    fetch_quota_best,
    pad_l,
    pad_r,
    parse_iso_epoch,
    parse_local_naive,
)
from paths import (
    BRAIN_DIR,
    CONFIG_PATH,
    HOOKS_JSON_PATH,
    HOOK_KEY,
    LEDGER_PATH,
)

POOL_KEYS = ("gemini_5h", "gemini_weekly", "claude_gpt_5h", "claude_gpt_weekly")

# Empirical Gemini relative token weights:
# uncached input = 1.0, cache_read = 0.05 (95% discount), output (incl. thinking) = 5.0
W_INPUT = 1.0
W_CACHE = 0.05
W_OUTPUT = 5.0
DEFAULT_FIVE_H_RATIO = 4.0
FIVE_H_TO_WEEKLY = 1.0 / DEFAULT_FIVE_H_RATIO

VALID_RATE_PRESETS = ("none", "ultra_5x", "ultra_20x")
# Empirical cold-start Weekly % per 1M Equivalent Input rates for Google AI Ultra 5x.
# NOTE: Ultra presets do NOT apply to Google AI Pro or Free tiers (different pool capacities
# and separate Argon buckets). `gemini-4-argon-*` is intentionally omitted here because no
# verified Ultra empirical samples exist yet; it auto-calibrates on the first clean turn.
ULTRA_5X_FAMILY_PRIORS = (
    (("gemini-4-carbon", "gemini-pro-orchestrator"), 1.0),
    (("gemini-4-neon",), 0.5),
    (("gemini-4-hydrogen", "gemini-flash-worker-agy"), 0.25),
)
# Ultra 20x pool capacity is 4x Ultra 5x -> Weekly % per 1M Equivalent Input is divided by 4.
PRESET_SCALE = {"ultra_5x": 1.0, "ultra_20x": 0.25}


def fmt_tok(n):
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def short_model(model_name):
    m = str(model_name or "-").strip()
    for prefix in ("gemini-4-", "gemini-"):
        if m.startswith(prefix):
            m = m[len(prefix) :]
            break
    m = (
        m.replace("pro-orchestrator", "pro-orchestr")
        .replace("flash-worker-agy", "flash-worker")
        .replace("-medium", "-med")
        .replace("-high", "-hi")
        .replace("-low", "-lo")
        .replace("-tiered", "-tier")
    )
    return m[:16]


def is_third_party_model(model_name):
    ml = str(model_name or "").lower()
    return any(tok in ml for tok in ("claude", "gpt", "o1", "o3", "o4"))


def split_orchestrator_hybrid_steps(r):
    """
    Detect legacy Orchestrator handoffs (`gemini-pro-orchestrator` -> `gemini-flash-worker-agy`)
    via the >15k non-compaction prompt drop when per-step `model` metadata is absent.
    """
    if str(r.get("model") or "") != "gemini-flash-worker-agy":
        return None, None
    tsteps = r.get("tokenSteps") or []
    if len(tsteps) < 2:
        return None, None
    for k in range(1, len(tsteps)):
        prev_s = tsteps[k - 1]
        cur_s = tsteps[k]
        if prev_s.get("type") == "CHECKPOINT" or cur_s.get("type") == "CHECKPOINT":
            continue
        prev_prompt = int(prev_s.get("in") or 0) + int(prev_s.get("cache") or 0)
        cur_prompt = int(cur_s.get("in") or 0) + int(cur_s.get("cache") or 0)
        if (prev_prompt - cur_prompt) > 15000:
            return tsteps[:k], tsteps[k:]
    return None, None


def sum_step_list_tokens(step_list):
    in_t = sum(int(s.get("in") or 0) for s in step_list)
    cr_t = sum(int(s.get("cache") or 0) for s in step_list)
    out_t = sum(int(s.get("out") or 0) for s in step_list)
    comp = sum(1 for s in step_list if s.get("type") == "CHECKPOINT")
    return {"input": in_t, "cacheRead": cr_t, "output": out_t, "compactions": comp, "count": len(step_list)}


def split_turn_steps_by_model(r):
    """
    Split a ledger turn's `tokenSteps` by per-step model when a turn spans multiple models
    (or when step models differ from the Stop hook's `r["model"]`).
    """
    tsteps = r.get("tokenSteps") or []
    hook_m = str(r.get("model") or "auto").strip()
    if any(isinstance(s, dict) and str(s.get("model") or "").strip() for s in tsteps):
        groups = {}
        for s in tsteps:
            if not isinstance(s, dict):
                continue
            sm = str(s.get("model") or hook_m or "auto").strip()
            groups.setdefault(sm, []).append(s)
        if len(groups) >= 2 or (len(groups) == 1 and next(iter(groups.keys())) != hook_m):
            return {m_k: sum_step_list_tokens(s_list) for m_k, s_list in groups.items()}
        return None

    p_steps, w_steps = split_orchestrator_hybrid_steps(r)
    if p_steps is not None and w_steps is not None:
        return {
            "gemini-pro-orchestrator": sum_step_list_tokens(p_steps),
            "gemini-flash-worker-agy": sum_step_list_tokens(w_steps),
        }
    return None


def eq_input_1m(tokens_dict):
    if not tokens_dict:
        return 0.0
    in_t = float(tokens_dict.get("input") or 0)
    cr_t = float(tokens_dict.get("cacheRead") or 0)
    out_t = float(tokens_dict.get("output") or 0)
    return (W_INPUT * in_t + W_CACHE * cr_t + W_OUTPUT * out_t) / 1_000_000.0


def load_user_config(config_path=None):
    """Read-only JSON loader for user preferences (`config.json`); fail-open with defaults."""
    path = config_path or CONFIG_PATH
    cfg = {"ratePreset": "none"}
    if not path or not os.path.isfile(path):
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            cfg.update(raw)
    except Exception:
        return {"ratePreset": "none"}
    if cfg.get("ratePreset") not in VALID_RATE_PRESETS:
        cfg["ratePreset"] = "none"
    return cfg


def get_rate_preset(config_path=None):
    """Return active cold-start rate preset (`none`, `ultra_5x`, or `ultra_20x`)."""
    return load_user_config(config_path=config_path).get("ratePreset", "none")


def set_rate_preset(preset, config_path=None):
    """Persist validated cold-start rate preset atomically to `config.json`."""
    p = str(preset or "none").strip()
    if p not in VALID_RATE_PRESETS:
        raise ValueError(f"Invalid rate preset: {preset!r} (expected one of {VALID_RATE_PRESETS})")
    path = config_path or CONFIG_PATH
    cfg = load_user_config(config_path=path)
    cfg["ratePreset"] = p
    atomic_write_text(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    return p


def lookup_preset_model_rate(model_name, rate_preset="none"):
    """Return cold-start Weekly % per 1M Equivalent Input for `model_name` under `rate_preset`, or None."""
    scale = PRESET_SCALE.get(str(rate_preset or "none"))
    if scale is None:
        return None
    ml = str(model_name or "").strip().lower()
    if not ml:
        return None
    for prefixes, base_rate in ULTRA_5X_FAMILY_PRIORS:
        for pref in prefixes:
            if ml == pref or ml.startswith(pref + "-"):
                return round(base_rate * scale, 6)
    return None


def resolve_model_rate(model_name, weekly_rates, rate_preset="none"):
    """
    Resolve Weekly % per 1M Equivalent Input rate for `model_name`:
      1. Exact locally calibrated model rate
      2. Same-family locally calibrated sibling fallback
      3. Optional cold-start preset (Ultra 5x / Ultra 20x only)
    """
    m = str(model_name or "auto").strip()
    if m in weekly_rates:
        return weekly_rates[m], False, m

    parts = m.split("-")
    if len(parts) >= 3:
        fam_prefix = "-".join(parts[:3]) + "-"
        for tier in ("high", "medium", "xhigh", "low", "lite"):
            cand = fam_prefix + tier
            if cand in weekly_rates:
                return weekly_rates[cand], True, cand
        for k in sorted(weekly_rates.keys()):
            if k.startswith(fam_prefix):
                return weekly_rates[k], True, k

    prior = lookup_preset_model_rate(m, rate_preset=rate_preset)
    if prior is not None:
        return prior, True, f"preset:{rate_preset}"

    return None, False, ""


def row_theoretical_weekly_info(r, weekly_rates, rate_preset="none"):
    """Return `(theoretical_weekly_pct, is_estimated, source_model)` for a ledger turn."""
    by_m = split_turn_steps_by_model(r)
    if by_m:
        total_val = 0.0
        any_est = False
        for m_i, tok_m in by_m.items():
            w_rate, is_est, _ = resolve_model_rate(m_i, weekly_rates, rate_preset=rate_preset)
            if w_rate is None:
                return None, False, ""
            total_val += eq_input_1m(tok_m) * w_rate
            any_est = any_est or is_est
        keys_set = set(by_m.keys())
        src = (
            "pro+flash"
            if keys_set == {"gemini-pro-orchestrator", "gemini-flash-worker-agy"}
            else "+".join(short_model(k) for k in sorted(keys_set))
        )
        return total_val, any_est, src

    m = str(r.get("model") or "auto")
    w_rate, is_est, src_m = resolve_model_rate(m, weekly_rates, rate_preset=rate_preset)
    if w_rate is None:
        return None, False, ""
    return eq_input_1m(r.get("tokens") or {}) * w_rate, is_est, src_m


def row_theoretical_weekly(r, weekly_rates, rate_preset="none"):
    val, _, _ = row_theoretical_weekly_info(r, weekly_rates, rate_preset=rate_preset)
    return val


def get_hook_enabled(hooks_json_path=HOOKS_JSON_PATH):
    if not os.path.exists(hooks_json_path):
        return False
    try:
        with open(hooks_json_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        hk = cfg.get(HOOK_KEY)
        if not isinstance(hk, dict):
            return False
        return hk.get("enabled", True) is not False
    except Exception:
        return False


def set_hook_enabled(enable, hooks_json_path=HOOKS_JSON_PATH):
    if not os.path.exists(hooks_json_path):
        print(f"配置文件不存在: {hooks_json_path}")
        return
    with open(hooks_json_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if HOOK_KEY not in cfg:
        print(f"未在 {hooks_json_path} 中找到 {HOOK_KEY}")
        return
    cfg[HOOK_KEY]["enabled"] = bool(enable)
    with open(hooks_json_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    state_str = "已启用 (ON)" if enable else "已暂停 (OFF)"
    print(f"全局额度追踪 Hook 状态: {state_str}")


def print_live_quota():
    try:
        snap, ms = fetch_quota_best(timeout_sec=5.0)
        if not snap:
            print("未能读取到 Antigravity 实时状态（请确认桌面端与 usage-monitor Sidecar 已打开）。\n")
            return
        print(f"=== 当前共享池实时水位 (--live, {ms}ms) ===")
        plan = snap.get("plan") or "-"
        mode = snap.get("billingMode") or "-"
        print(f"来源: {snap.get('source', '-')} | 模式: {mode} | 档位: {plan}")
        if mode == "paygo":
            print("  - 按量付费账号 (Pay-As-You-Go)：无周期性共享额度池，仅记录本地 Token。\n")
            return
        pools = snap.get("pools") or {}
        if not pools:
            print("  - 暂无额度池数据。\n")
            return
        order = snap.get("poolOrder") or list(pools.keys())
        for key in order:
            win = pools.get(key)
            if not isinstance(win, dict):
                continue
            used = float(win.get("usedPercent", 0.0))
            rem = max(0.0, 100.0 - used)
            desc = win.get("description") or f"Resets at {win.get('resetsAt', '-')}"
            print(f"  - {key:<20}: 剩余 {rem:7.3f}% | 已用 {used:7.3f}%  ({desc})")
        print()
    except Exception as e:
        print(f"实时读取失败: {e}\n")


def print_last_snapshot_banner(rows):
    if not rows:
        return
    last = rows[-1]
    end_str = (last.get("endIso") or "")[:19].replace("T", " ")
    pools = last.get("pools") or {}
    g5 = pools.get("gemini_5h") or {}
    gw = pools.get("gemini_weekly") or {}
    c5 = pools.get("claude_gpt_5h") or {}
    cw = pools.get("claude_gpt_weekly") or {}

    def fmt_reset(p_obj):
        dt = parse_local_naive(p_obj.get("resetsAt"))
        return dt.strftime("%m-%d %H:%M") if dt else "-"

    g5_end = float(g5.get("end") or 0.0)
    gw_end = float(gw.get("end") or 0.0)
    c5_end = float(c5.get("end") or 0.0)
    cw_end = float(cw.get("end") or 0.0)
    print(
        f"最新账本共享池水位 (截至 {end_str}):\n"
        f"  • Gemini 池    : 周已用 {gw_end:7.4f}% (重置 {fmt_reset(gw)}) | "
        f"5h 已用 {g5_end:7.4f}% (重置 {fmt_reset(g5)})\n"
        f"  • Claude/GPT 池: 周已用 {cw_end:7.4f}% (重置 {fmt_reset(cw)}) | "
        f"5h 已用 {c5_end:7.4f}% (重置 {fmt_reset(c5)})"
    )


def load_entries(ledger_path=LEDGER_PATH):
    if not os.path.exists(ledger_path):
        return []
    rows = []
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def extract_tokens_by_window(transcript_path, start_epoch, end_epoch):
    if not transcript_path or not os.path.isfile(transcript_path):
        return None, []
    min_ep = float(start_epoch) - 2.5
    max_ep = float(end_epoch) + 1.5
    token_steps = []
    seen = set()
    search_web_calls = 0
    error_steps = 0
    subagent_calls = 0
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
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
                if step_idx in seen:
                    continue
                c_ep = parse_iso_epoch(obj.get("created_at"))
                if c_ep is None or c_ep < min_ep or c_ep > max_ep:
                    continue
                seen.add(step_idx)

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
        return None, []

    if not token_steps:
        return None, []

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


def enrich_turn_steps_from_transcript(transcript_path, existing_steps, step_start, step_end):
    """Backfill per-step `model` onto `tokenSteps` and collect tool/error markers losslessly."""
    if not transcript_path or not os.path.isfile(transcript_path):
        models_list = sorted({s["model"] for s in (existing_steps or []) if isinstance(s, dict) and s.get("model")})
        return False, models_list, 0, 0, 0

    s_min = int(step_start) if step_start is not None else None
    s_max = int(step_end) if step_end is not None else None
    if (s_min is None or s_max is None) and existing_steps:
        step_nums = [int(s["step"]) for s in existing_steps if isinstance(s, dict) and s.get("step") is not None]
        if step_nums:
            if s_min is None:
                s_min = min(step_nums)
            if s_max is None:
                s_max = max(step_nums)
    if s_min is None or s_max is None:
        models_list = sorted({s["model"] for s in (existing_steps or []) if isinstance(s, dict) and s.get("model")})
        return False, models_list, 0, 0, 0

    model_by_step = {}
    seen = set()
    search_web_calls = 0
    error_steps = 0
    subagent_calls = 0
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
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
                if step_idx < s_min or step_idx > s_max or step_idx in seen:
                    continue
                seen.add(step_idx)

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

                sm = str(obj.get("model") or "").strip()
                if sm:
                    model_by_step[step_idx] = sm
    except Exception:
        models_list = sorted({s["model"] for s in (existing_steps or []) if isinstance(s, dict) and s.get("model")})
        return False, models_list, 0, 0, 0

    changed = False
    for s in existing_steps or []:
        if not isinstance(s, dict):
            continue
        si = s.get("step")
        if si is not None and int(si) in model_by_step and not s.get("model"):
            s["model"] = model_by_step[int(si)]
            changed = True

    models_list = sorted({s["model"] for s in (existing_steps or []) if isinstance(s, dict) and s.get("model")})
    return changed, models_list, search_web_calls, error_steps, subagent_calls


def run_backfill():
    if not os.path.exists(LEDGER_PATH):
        print("账本文件尚不存在，无需回填。")
        return

    brain_map = {}
    uuid_path_map = {}
    if os.path.isdir(BRAIN_DIR):
        for name in os.listdir(BRAIN_DIR):
            tp = os.path.join(BRAIN_DIR, name, ".system_generated", "logs", "transcript.jsonl")
            if os.path.isfile(tp):
                uuid_path_map[name] = tp
                brain_map.setdefault(name[:8], []).append((name, tp))

    rows = load_entries()
    updated = 0
    enriched = 0
    already = 0
    unmatched = 0

    for r in rows:
        tok = r.get("tokens")
        if isinstance(tok, dict) and int(tok.get("billedSteps") or 0) > 0:
            already += 1
            tsteps = r.get("tokenSteps") or []
            needs_enrich = ("searchWebCalls" not in tok) or (
                any(isinstance(s, dict) and not s.get("model") for s in tsteps) and tok.get("models") is None
            )
            if needs_enrich:
                short_id = str(r.get("conversationId") or "")[:8]
                full_uuid = str(r.get("conversationUuid") or "")
                tp_cand = uuid_path_map.get(full_uuid)
                if not tp_cand:
                    cands = brain_map.get(short_id, [])
                    for cand_uuid, cand_tp in cands:
                        tp_cand = cand_tp
                        if not full_uuid:
                            full_uuid = cand_uuid
                        break
                if tp_cand:
                    _ch, models_list, sw_calls, err_steps, sub_calls = enrich_turn_steps_from_transcript(
                        tp_cand, tsteps, tok.get("stepStart"), tok.get("stepEnd")
                    )
                    tok["models"] = models_list
                    tok["searchWebCalls"] = sw_calls
                    tok["errorSteps"] = err_steps
                    tok["subagentCalls"] = sub_calls
                    if full_uuid and not r.get("conversationUuid"):
                        r["conversationUuid"] = full_uuid
                    enriched += 1
            continue

        short_id = str(r.get("conversationId") or "")[:8]
        start_ep = r.get("startTs") or parse_iso_epoch(r.get("startIso"))
        end_ep = r.get("ts") or parse_iso_epoch(r.get("endIso"))
        if not short_id or start_ep is None or end_ep is None:
            unmatched += 1
            continue

        candidates = brain_map.get(short_id, [])
        matched_summary = None
        matched_steps = []
        matched_uuid = ""
        for full_uuid, tp in candidates:
            s_obj, st_list = extract_tokens_by_window(tp, start_ep, end_ep)
            if s_obj and s_obj["billedSteps"] > 0:
                matched_summary = s_obj
                matched_steps = st_list
                matched_uuid = full_uuid
                break

        if matched_summary:
            r["startTs"] = round(float(start_ep), 3)
            r["conversationUuid"] = matched_uuid
            r["tokens"] = matched_summary
            r["tokenSteps"] = matched_steps
            updated += 1
        else:
            unmatched += 1

    if updated == 0 and enriched == 0:
        print(f"回填检查完成：已有 Token 明细 {already} 条，新增回填 0 条，补充标记 0 条（未匹配 {unmatched} 条）。")
        return

    bak_path = LEDGER_PATH + ".bak"
    shutil.copy2(LEDGER_PATH, bak_path)
    tmp_path = LEDGER_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp_path, LEDGER_PATH)
    print(
        f"历史回填成功：新增回填 {updated} 条，补充逐 step 模型与工具标记 {enriched} 条，原有 {already} 条，未匹配 {unmatched} 条。\n"
        f"（原账本已自动备份至 {bak_path}）"
    )


def annotate_pool_anomalies(rows):
    """Classify turn-level resets vs rollbacks across chronological turns."""
    ordered = []
    for idx, r in enumerate(rows):
        s_ep = r.get("startTs") or parse_iso_epoch(r.get("startIso")) or 0.0
        e_ep = r.get("ts") or parse_iso_epoch(r.get("endIso")) or s_ep
        ordered.append((float(e_ep), float(s_ep), idx, r))
    ordered.sort(key=lambda x: (x[0], x[1], x[2]))

    cur_resets_at = {}
    high_water = {}
    win_epoch = {pk: 0 for pk in POOL_KEYS}
    prev_end_ep = {}

    for e_ep, s_ep, _idx, r in ordered:
        pools = r.get("pools") or {}
        any_mid_reset = False
        any_false_reset = False

        for pk in POOL_KEYS:
            p = pools.get(pk)
            if not isinstance(p, dict) or p.get("start") is None or p.get("end") is None:
                continue
            s_val = float(p["start"])
            e_val = float(p["end"])
            r_at = str(p.get("resetsAt") or "")
            raw_reset = bool(p.get("reset"))

            prev_r_at = cur_resets_at.get(pk)
            prev_hw = high_water.get(pk)
            last_ep = prev_end_ep.get(pk)
            r_changed = bool(
                prev_r_at
                and r_at
                and (r_at != prev_r_at)
                and not ((prev_hw or 0.0) <= 1e-6 and s_val <= 1e-6 and e_val <= 1e-6)
            )

            between_reset = False
            mid_reset = False
            false_reset = False

            if raw_reset:
                if r_changed or ((not prev_r_at or not r_at) and e_val < 3.0 and (s_val - e_val) > 3.0):
                    mid_reset = True
                else:
                    false_reset = True
            else:
                if r_changed:
                    between_reset = True
                elif (not prev_r_at or not r_at) and (prev_hw is not None) and s_val < 1.0 and prev_hw > 3.0:
                    between_reset = True

            idle_reconciled = (
                (not between_reset)
                and (not mid_reset)
                and (not false_reset)
                and (not r_at)
                and (prev_hw is not None)
                and (last_ep is not None)
                and ((s_ep - last_ep) > 1800.0)
                and ((prev_hw - s_val) > 0.35)
            )

            if between_reset or mid_reset:
                win_epoch[pk] += 1
                cur_resets_at[pk] = r_at or prev_r_at
                prev_hw = None
            elif idle_reconciled:
                prev_hw = s_val
            elif r_at and not prev_r_at:
                cur_resets_at[pk] = r_at

            stale_start = (
                (not between_reset)
                and (not mid_reset)
                and (not false_reset)
                and (prev_hw is not None)
                and (s_val < prev_hw - 1e-5)
            )

            p["_between_reset"] = between_reset
            p["_mid_reset"] = mid_reset
            p["_false_reset"] = false_reset
            p["_stale_start"] = stale_start
            p["_win_epoch"] = win_epoch[pk]

            if mid_reset:
                high_water[pk] = e_val
                any_mid_reset = True
            elif false_reset:
                if prev_hw is not None:
                    high_water[pk] = max(prev_hw, e_val)
                else:
                    high_water[pk] = e_val
                any_false_reset = True
            else:
                base_hw = prev_hw if prev_hw is not None else s_val
                high_water[pk] = e_val if r.get("status") == "long_gap" else max(base_hw, e_val)

            prev_end_ep[pk] = e_ep

        r["_any_mid_reset"] = any_mid_reset
        r["_any_false_reset"] = any_false_reset


def build_overlap_clusters(rows):
    """Group rows whose [start, end] intervals overlap by >2.0s into connected clusters."""
    intervals = []
    for idx, r in enumerate(rows):
        s_ep = r.get("startTs") or parse_iso_epoch(r.get("startIso"))
        e_ep = r.get("ts") or parse_iso_epoch(r.get("endIso"))
        if s_ep is not None and e_ep is not None:
            intervals.append((float(s_ep), float(e_ep), idx, r))

    overlapping = set()
    n = len(intervals)
    for i in range(n):
        s1, e1, idx1, _ = intervals[i]
        for j in range(i + 1, n):
            s2, e2, idx2, _ = intervals[j]
            if min(e1, e2) - max(s1, s2) > 2.0:
                overlapping.add(idx1)
                overlapping.add(idx2)

    intervals.sort(key=lambda x: (x[0], x[1], x[2]))
    clusters = []
    for s_ep, e_ep, idx, r in intervals:
        if not clusters:
            clusters.append([s_ep, e_ep, [(idx, r)]])
        else:
            prev_s, prev_e, prev_items = clusters[-1]
            if prev_e - s_ep > 2.0:
                if e_ep > prev_e:
                    clusters[-1][1] = e_ep
                prev_items.append((idx, r))
            else:
                clusters.append([s_ep, e_ep, [(idx, r)]])
    return overlapping, clusters


def _robust_median(vals):
    if not vals:
        return None
    med = statistics.median(vals)
    if len(vals) < 4:
        return med
    mad = statistics.median(abs(v - med) for v in vals)
    if mad <= 1e-9:
        return med
    tol = max(3.5 * mad, 0.02 * abs(med))
    inliers = [v for v in vals if abs(v - med) <= tol]
    return statistics.median(inliers) if inliers else med


def estimate_five_h_ratio(rows, monitor_rows=None, pool="gemini", default_ratio=DEFAULT_FIVE_H_RATIO):
    """
    Dynamically estimate `Δ5h / ΔWeekly` (e.g. 4.0 on Google AI Ultra) from clean
    non-reset ledger turns and denoised monitor ticks.
    Returns `(ratio, sample_count, calibrated_bool)`.
    """
    samples = []
    is_3p = pool in ("claude_gpt", "3p", "cg")
    pk5 = "claude_gpt_5h" if is_3p else "gemini_5h"
    pkw = "claude_gpt_weekly" if is_3p else "gemini_weekly"

    for r in rows or []:
        if r.get("status") != "ok" or r.get("_any_mid_reset") or r.get("_any_false_reset"):
            continue
        m_name = str(r.get("model") or "")
        if is_third_party_model(m_name) != is_3p:
            continue
        pools = r.get("pools") or {}
        p5 = pools.get(pk5) or {}
        pw = pools.get(pkw) or {}
        if p5.get("_mid_reset") or p5.get("_false_reset") or pw.get("_mid_reset") or pw.get("_false_reset"):
            continue
        if p5.get("start") is None or pw.get("start") is None:
            continue
        d5 = float(p5.get("delta") or 0.0)
        dw = float(pw.get("delta") or 0.0)
        if dw >= 0.01 and d5 >= 0.02:
            ratio = d5 / dw
            if 0.5 <= ratio <= 20.0:
                samples.append(ratio)

    if monitor_rows:
        import agy_monitor

        clean_rows = agy_monitor.clean_monitor_timeline(monitor_rows)
        dk5, dkw = ("dc5", "dcw") if is_3p else ("dg5", "dgw")
        rk5, rkw = ("c5", "cw") if is_3p else ("g5", "gw")
        for c in clean_rows:
            if c["window_resets"][rk5] or c["window_resets"][rkw]:
                continue
            if c["reset_flags"][rk5] or c["reset_flags"][rkw]:
                continue
            d5 = float(c.get(dk5) or 0.0)
            dw = float(c.get(dkw) or 0.0)
            if dw >= 0.01 and d5 >= 0.02:
                ratio = d5 / dw
                if 0.5 <= ratio <= 20.0:
                    samples.append(ratio)

    if len(samples) >= 3:
        med = _robust_median(samples)
        if med is not None and 0.5 <= med <= 20.0:
            return round(float(med), 6), len(samples), True
    return float(default_ratio), len(samples), False


def _is_quiet_golden_interval(
    s_ts, e_ts, s_gw, e_gw, s_g5, e_g5, mon_ts, mon_ok, is_3p=False, window_sec=150.0, weekly_only=False
):
    if not mon_ts or s_ts is None or e_ts is None:
        return False
    if s_gw is None or e_gw is None:
        return False
    if (not weekly_only) and (s_g5 is None or e_g5 is None):
        return False
    k5, kw = ("c5", "cw") if is_3p else ("g5", "gw")
    i0 = bisect.bisect_left(mon_ts, float(s_ts) - window_sec)
    i1 = bisect.bisect_right(mon_ts, float(s_ts) - 1.0)
    pre = mon_ok[i0:i1]
    j0 = bisect.bisect_left(mon_ts, float(e_ts) + 1.0)
    j1 = bisect.bisect_right(mon_ts, float(e_ts) + window_sec)
    post = mon_ok[j0:j1]
    if len(pre) < 2 or len(post) < 2:
        return False
    if any(m.get(kw) is None for m in pre) or any(m.get(kw) is None for m in post):
        return False
    pre_w = [float(m[kw]) for m in pre]
    post_w = [float(m[kw]) for m in post]
    if (max(pre_w) - min(pre_w)) >= 1e-4 or (max(post_w) - min(post_w)) >= 1e-4:
        return False
    if abs(pre_w[-1] - float(s_gw)) >= 1e-4 or abs(post_w[0] - float(e_gw)) >= 1e-4:
        return False

    if not weekly_only:
        if any(m.get(k5) is None for m in pre) or any(m.get(k5) is None for m in post):
            return False
        pre_5 = [float(m[k5]) for m in pre]
        post_5 = [float(m[k5]) for m in post]
        if (max(pre_5) - min(pre_5)) >= 1e-4 or (max(post_5) - min(post_5)) >= 1e-4:
            return False
        if abs(pre_5[-1] - float(s_g5)) >= 1e-4 or abs(post_5[0] - float(e_g5)) >= 1e-4:
            return False
    return True


def calibrate_weekly_model_rates(rows, overlapping_indices, all_clusters, monitor_rows=None):
    """
    Calibrate Weekly % per 1M Equivalent Input per model:
      - Uses dynamically inferred 5h:Weekly ratio (`estimate_five_h_ratio`) when 5h pool exists,
        preserving 4x precision while generalizing beyond AI Ultra (4:1).
      - Falls back cleanly to weekly-only delta when 5h pool is absent.
      - Prefers quiet-window golden samples (`monitor_rows`) + MAD outlier filtering +
        Pass-2 residual solver for clean mixed-model turns.
    """
    gem_ratio, _, _ = estimate_five_h_ratio(rows, monitor_rows=monitor_rows, pool="gemini")
    gem_5h_to_w = 1.0 / gem_ratio

    mon_ok = []
    mon_ts = []
    if monitor_rows:
        mon_ok = sorted(
            (
                m
                for m in monitor_rows
                if m.get("ok")
                and m.get("billingMode") != "paygo"
                and m.get("gw") is not None
                and m.get("ts") is not None
            ),
            key=lambda x: float(x["ts"]),
        )
        mon_ts = [float(m["ts"]) for m in mon_ok]

    regular_samples = {}
    golden_samples = {}
    pass2_candidates = []

    for idx, r in enumerate(rows):
        if idx in overlapping_indices or r.get("status") != "ok":
            continue
        if r.get("_any_mid_reset"):
            continue
        tok = r.get("tokens") or {}
        if int(tok.get("searchWebCalls") or 0) > 0 or int(tok.get("errorSteps") or 0) > 0:
            continue
        eq1m = eq_input_1m(tok)
        if eq1m < 0.003:
            continue
        by_m = split_turn_steps_by_model(r)
        if by_m is not None and len(by_m) >= 2:
            pass2_candidates.append((r, by_m))
            continue

        m = next(iter(by_m.keys())) if (by_m and len(by_m) == 1) else str(r.get("model") or "auto")
        pools = r.get("pools") or {}
        s_ep = r.get("startTs") or parse_iso_epoch(r.get("startIso"))
        e_ep = r.get("ts") or parse_iso_epoch(r.get("endIso"))

        if is_third_party_model(m):
            p5 = pools.get("claude_gpt_5h") or {}
            pw = pools.get("claude_gpt_weekly") or {}
            if pw.get("_mid_reset") or pw.get("_false_reset") or pw.get("start") is None:
                continue
            dw = float(pw.get("delta") or 0.0)
            if dw < 0.0:
                continue
            val = dw / eq1m
            regular_samples.setdefault(m, []).append(val)
            weekly_only = p5.get("start") is None
            if _is_quiet_golden_interval(
                s_ep, e_ep, pw.get("start"), pw.get("end"), p5.get("start"), p5.get("end"),
                mon_ts, mon_ok, is_3p=True, weekly_only=weekly_only
            ):
                golden_samples.setdefault(m, []).append(val)
        else:
            p5 = pools.get("gemini_5h") or {}
            pw = pools.get("gemini_weekly") or {}
            if p5.get("_mid_reset") or p5.get("_false_reset") or pw.get("_false_reset"):
                continue
            if pw.get("start") is None:
                continue
            dw = float(pw.get("delta") or 0.0)
            has_5h = p5.get("start") is not None and p5.get("end") is not None
            if has_5h:
                d5 = float(p5.get("delta") or 0.0)
                if d5 < 0.0 or dw < 0.0:
                    continue
                if d5 == 0.0 and dw != 0.0:
                    continue
                if dw > 0.0 and abs((d5 / dw) - gem_ratio) / gem_ratio > 0.05:
                    continue
                val = (d5 * gem_5h_to_w) / eq1m
                regular_samples.setdefault(m, []).append(val)
                if (dw <= 0.0 or abs((d5 / dw) - gem_ratio) / gem_ratio <= 0.015) and _is_quiet_golden_interval(
                    s_ep, e_ep, pw.get("start"), pw.get("end"), p5.get("start"), p5.get("end"),
                    mon_ts, mon_ok, is_3p=False, weekly_only=False
                ):
                    golden_samples.setdefault(m, []).append(val)
            else:
                if dw < 0.0:
                    continue
                val = dw / eq1m
                regular_samples.setdefault(m, []).append(val)
                if _is_quiet_golden_interval(
                    s_ep, e_ep, pw.get("start"), pw.get("end"), None, None,
                    mon_ts, mon_ok, is_3p=False, weekly_only=True
                ):
                    golden_samples.setdefault(m, []).append(val)

    for s_ep, e_ep, items in all_clusters:
        if len(items) < 2:
            continue
        cluster_rows = [r for _, r in items]
        if any(
            r.get("status") != "ok"
            or r.get("_any_false_reset")
            or r.get("_any_mid_reset")
            or int((r.get("tokens") or {}).get("billedSteps") or 0) <= 0
            or int((r.get("tokens") or {}).get("searchWebCalls") or 0) > 0
            or int((r.get("tokens") or {}).get("errorSteps") or 0) > 0
            for r in cluster_rows
        ):
            continue

        row_models = set()
        has_mixed = False
        for r in cluster_rows:
            bm = split_turn_steps_by_model(r)
            if bm is not None and len(bm) >= 2:
                has_mixed = True
                break
            eff_m = next(iter(bm.keys())) if (bm and len(bm) == 1) else str(r.get("model") or "auto")
            row_models.add(eff_m)
        if has_mixed or len(row_models) != 1:
            continue
        m = next(iter(row_models))

        cluster_eq1m = sum(eq_input_1m(r.get("tokens") or {}) for r in cluster_rows)
        if cluster_eq1m < 0.005:
            continue

        is_3p_m = is_third_party_model(m)
        pk5 = "claude_gpt_5h" if is_3p_m else "gemini_5h"
        pkw = "claude_gpt_weekly" if is_3p_m else "gemini_weekly"

        s5_list, e5_list, sw_list, ew_list = [], [], [], []
        epochs_5h = set()
        for r in cluster_rows:
            p5 = (r.get("pools") or {}).get(pk5) or {}
            pw = (r.get("pools") or {}).get(pkw) or {}
            epochs_5h.add(p5.get("_win_epoch", 0))
            if p5.get("start") is not None and p5.get("end") is not None:
                s5_list.append(float(p5["start"]))
                e5_list.append(float(p5["end"]))
            if pw.get("start") is not None and pw.get("end") is not None:
                sw_list.append(float(pw["start"]))
                ew_list.append(float(pw["end"]))

        if not sw_list:
            continue

        s_wk, e_wk = min(sw_list), max(ew_list)
        c_dw = e_wk - s_wk
        if c_dw < -1e-6:
            continue
        c_dw = max(0.0, c_dw)

        has_5h = (len(epochs_5h) == 1 and len(s5_list) == len(cluster_rows))
        if has_5h:
            s_5h, e_5h = min(s5_list), max(e5_list)
            c_d5 = e_5h - s_5h
            if c_d5 < -1e-6:
                continue
            c_d5 = max(0.0, c_d5)
        else:
            s_5h = e_5h = None
            c_d5 = None

        if is_3p_m:
            val = c_dw / cluster_eq1m
            regular_samples.setdefault(m, []).append(val)
            if _is_quiet_golden_interval(
                s_ep, e_ep, s_wk, e_wk, s_5h, e_5h, mon_ts, mon_ok, is_3p=True, weekly_only=(not has_5h)
            ):
                golden_samples.setdefault(m, []).append(val)
        elif has_5h:
            if c_d5 == 0.0 and c_dw != 0.0:
                continue
            if c_d5 > 0.0 and (c_dw <= 0.0 or abs((c_d5 / c_dw) - gem_ratio) / gem_ratio > 0.05):
                continue
            val = (c_d5 * gem_5h_to_w) / cluster_eq1m
            regular_samples.setdefault(m, []).append(val)
            if (c_dw <= 0.0 or abs((c_d5 / c_dw) - gem_ratio) / gem_ratio <= 0.015) and _is_quiet_golden_interval(
                s_ep, e_ep, s_wk, e_wk, s_5h, e_5h, mon_ts, mon_ok, is_3p=False, weekly_only=False
            ):
                golden_samples.setdefault(m, []).append(val)
        else:
            val = c_dw / cluster_eq1m
            regular_samples.setdefault(m, []).append(val)
            if _is_quiet_golden_interval(
                s_ep, e_ep, s_wk, e_wk, None, None, mon_ts, mon_ok, is_3p=False, weekly_only=True
            ):
                golden_samples.setdefault(m, []).append(val)

    rates_weekly = {}
    selected_samples = {}
    for m in sorted(set(regular_samples.keys()) | set(golden_samples.keys())):
        g_vals = golden_samples.get(m, [])
        r_vals = regular_samples.get(m, [])
        chosen = g_vals if (len(g_vals) >= 2 or (len(g_vals) == 1 and len(r_vals) <= 2)) else r_vals
        if chosen:
            selected_samples[m] = chosen
            rates_weekly[m] = _robust_median(chosen)

    # Pass 2: residual solver for clean mixed turns
    pass2_regular = {}
    pass2_golden = {}
    for r, by_m in pass2_candidates:
        unknown = [mk for mk in by_m if mk not in rates_weekly]
        if len(unknown) != 1:
            continue
        mu = unknown[0]
        eq_u = eq_input_1m(by_m[mu])
        if eq_u < 0.02:
            continue
        known_est = sum(eq_input_1m(by_m[mk]) * rates_weekly[mk] for mk in by_m if mk != mu)

        pools = r.get("pools") or {}
        s_ep = r.get("startTs") or parse_iso_epoch(r.get("startIso"))
        e_ep = r.get("ts") or parse_iso_epoch(r.get("endIso"))
        if is_third_party_model(mu):
            p5 = pools.get("claude_gpt_5h") or {}
            pw = pools.get("claude_gpt_weekly") or {}
            if pw.get("_mid_reset") or pw.get("_false_reset") or pw.get("start") is None:
                continue
            obs_w = float(pw.get("delta") or 0.0)
            if obs_w <= 0.0:
                continue
            resid = obs_w - known_est
            if resid >= 0.0:
                val = resid / eq_u
                pass2_regular.setdefault(mu, []).append(val)
                if _is_quiet_golden_interval(
                    s_ep, e_ep, pw.get("start"), pw.get("end"), p5.get("start"), p5.get("end"),
                    mon_ts, mon_ok, is_3p=True, weekly_only=(p5.get("start") is None)
                ):
                    pass2_golden.setdefault(mu, []).append(val)
        else:
            p5 = pools.get("gemini_5h") or {}
            pw = pools.get("gemini_weekly") or {}
            if p5.get("_mid_reset") or p5.get("_false_reset") or pw.get("_false_reset"):
                continue
            if pw.get("start") is None:
                continue
            dw = float(pw.get("delta") or 0.0)
            has_5h = p5.get("start") is not None and p5.get("end") is not None
            if has_5h:
                d5 = float(p5.get("delta") or 0.0)
                if d5 < 0.0 or dw <= 0.0 or abs((d5 / dw) - gem_ratio) / gem_ratio > 0.05:
                    continue
                resid = (d5 * gem_5h_to_w) - known_est
                if resid >= 0.0:
                    val = resid / eq_u
                    pass2_regular.setdefault(mu, []).append(val)
                    if abs((d5 / dw) - gem_ratio) / gem_ratio <= 0.015 and _is_quiet_golden_interval(
                        s_ep, e_ep, pw.get("start"), pw.get("end"), p5.get("start"), p5.get("end"),
                        mon_ts, mon_ok, is_3p=False, weekly_only=False
                    ):
                        pass2_golden.setdefault(mu, []).append(val)
            else:
                if dw <= 0.0:
                    continue
                resid = dw - known_est
                if resid >= 0.0:
                    val = resid / eq_u
                    pass2_regular.setdefault(mu, []).append(val)
                    if _is_quiet_golden_interval(
                        s_ep, e_ep, pw.get("start"), pw.get("end"), None, None,
                        mon_ts, mon_ok, is_3p=False, weekly_only=True
                    ):
                        pass2_golden.setdefault(mu, []).append(val)

    for mu in sorted(set(pass2_regular.keys()) | set(pass2_golden.keys())):
        if mu in rates_weekly:
            continue
        g_vals = pass2_golden.get(mu, [])
        r_vals = pass2_regular.get(mu, [])
        chosen = g_vals if (len(g_vals) >= 2 or (len(g_vals) == 1 and len(r_vals) <= 2)) else r_vals
        if chosen:
            selected_samples[mu] = chosen
            rates_weekly[mu] = _robust_median(chosen)

    return rates_weekly, selected_samples


def turn_measured_weekly_delta(r, five_h_to_weekly=FIVE_H_TO_WEEKLY):
    """Compute single-turn measured Weekly % delta using `five_h_to_weekly`."""
    m = str(r.get("model") or "auto")
    pools = r.get("pools") or {}
    if is_third_party_model(m):
        pw = pools.get("claude_gpt_weekly") or {}
        if pw.get("_false_reset"):
            return None, "false_reset"
        if pw.get("_mid_reset"):
            return max(0.0, float(pw.get("end") or 0.0)), "mid_reset"
        return max(0.0, float(pw.get("delta") or 0.0)), "ok"

    p5 = pools.get("gemini_5h") or {}
    pw = pools.get("gemini_weekly") or {}
    if pw.get("_false_reset"):
        if not p5.get("_mid_reset") and not p5.get("_false_reset") and p5.get("start") is not None:
            return max(0.0, float(p5.get("delta") or 0.0)) * five_h_to_weekly, "ok_from_5h"
        return None, "false_reset"
    if p5.get("_false_reset") and float(pw.get("delta") or 0.0) <= 0.0:
        return None, "false_reset"
    if pw.get("_mid_reset"):
        return max(0.0, float(pw.get("end") or 0.0)), "mid_reset"

    dw = max(0.0, float(pw.get("delta") or 0.0))
    if not p5.get("_mid_reset") and not p5.get("_false_reset") and p5.get("start") is not None:
        d5_w = max(0.0, float(p5.get("delta") or 0.0)) * five_h_to_weekly
        if abs(d5_w - dw) <= 0.002:
            return d5_w, "ok"
    return dw, ("5h_reset_ok" if p5.get("_mid_reset") else "ok")


def _compute_pool_active_and_span(
    valid_items, pool_key, weekly_rates, model_filter=None, five_h_to_weekly=FIVE_H_TO_WEEKLY, rate_preset="none"
):
    """Compute `(active_delta, span_delta)` for a weekly pool (`gemini_weekly` or `claude_gpt_weekly`)."""
    win_bounds = {}
    win_order = []
    for _s_dt, _e_dt, r in valid_items:
        pw = (r.get("pools") or {}).get(pool_key) or {}
        if pw.get("start") is None or pw.get("end") is None:
            continue
        s_val = float(pw["start"])
        e_val = float(pw["end"])
        ep_key = pw.get("_win_epoch", 0)
        if ep_key not in win_bounds:
            win_order.append(ep_key)
            if pw.get("_mid_reset") or (pw.get("_between_reset") and len(win_order) > 1):
                base = 0.0
            elif pw.get("_false_reset"):
                base = e_val
            else:
                base = s_val
            win_bounds[ep_key] = [base, max(base, e_val)]
        else:
            win_bounds[ep_key][1] = max(win_bounds[ep_key][1], e_val)
    span_val = sum(max(0.0, win_bounds[k][1] - win_bounds[k][0]) for k in win_order)

    clusters = []
    for s_dt, e_dt, r in valid_items:
        if model_filter is not None and not model_filter(r):
            continue
        if not clusters:
            clusters.append([s_dt, e_dt, [r]])
        else:
            prev_s, prev_e, prev_list = clusters[-1]
            if (prev_e - s_dt).total_seconds() > 2.0:
                if e_dt > prev_e:
                    clusters[-1][1] = e_dt
                prev_list.append(r)
            else:
                clusters.append([s_dt, e_dt, [r]])

    active_val = 0.0
    cur_ep = None
    hw_val = None
    is_gemini = pool_key == "gemini_weekly"
    pk_5h = "gemini_5h" if is_gemini else "claude_gpt_5h"

    for _c_s, _c_e, c_rows in clusters:
        clean_starts = []
        ends = []
        mid_reset = False
        false_reset = False
        c_est = 0.0
        latest_ep = cur_ep
        s5_clean, e5_clean, ep5_set = [], [], set()

        for r in c_rows:
            r_est = row_theoretical_weekly(r, weekly_rates, rate_preset=rate_preset)
            if r_est is not None:
                c_est += r_est

            pw = (r.get("pools") or {}).get(pool_key) or {}
            p5 = (r.get("pools") or {}).get(pk_5h) or {}
            if pw.get("start") is not None and pw.get("end") is not None:
                s_val = float(pw["start"])
                e_val = float(pw["end"])
                row_ep = pw.get("_win_epoch", 0)
                if cur_ep is not None and row_ep != cur_ep and not pw.get("_mid_reset"):
                    hw_val = None
                latest_ep = row_ep
                if pw.get("_mid_reset"):
                    mid_reset = True
                elif pw.get("_false_reset"):
                    false_reset = True
                else:
                    clean_starts.append(s_val)
                ends.append(e_val)

            if (
                is_gemini
                and p5.get("start") is not None
                and p5.get("end") is not None
                and not p5.get("_mid_reset")
                and not p5.get("_false_reset")
                and not p5.get("_stale_start")
            ):
                ep5_set.add(p5.get("_win_epoch", 0))
                s5_clean.append(float(p5["start"]))
                e5_clean.append(float(p5["end"]))

        if not ends:
            continue

        max_end = max(ends)
        if mid_reset:
            active_val += max(0.0, max_end)
            hw_val = max_end
            cur_ep = latest_ep
            continue

        cur_ep = latest_ep
        raw_clean = 0.0
        used_stale_clamp = False
        if clean_starts:
            eff_s = min(clean_starts)
            if hw_val is not None and eff_s < hw_val:
                eff_s = hw_val
                used_stale_clamp = True
            raw_clean = max(0.0, max_end - eff_s)

        if false_reset:
            if is_gemini and len(ep5_set) == 1 and len(s5_clean) == len(c_rows):
                active_val += max(0.0, max(e5_clean) - min(s5_clean)) * five_h_to_weekly
            else:
                cap_from_prev = max(0.0, max_end - hw_val) if hw_val is not None else c_est
                active_val += max(raw_clean, min(cap_from_prev, c_est))
        else:
            if is_gemini and not used_stale_clamp and len(ep5_set) == 1 and len(s5_clean) == len(c_rows):
                d5_gw = max(0.0, max(e5_clean) - min(s5_clean)) * five_h_to_weekly
                if abs(d5_gw - raw_clean) <= 0.002:
                    raw_clean = d5_gw
            active_val += raw_clean

        hw_val = max(hw_val, max_end) if hw_val is not None else max_end

    return active_val, span_val


def summarize_period(rows, since_dt, weekly_rates, until_dt=None, five_h_to_weekly=FIVE_H_TO_WEEKLY, rate_preset="none"):
    turns = 0
    steps = 0
    cg_turns = 0
    cg_steps = 0
    long_gap_count = 0
    false_reset_count = 0
    in_tok = 0
    cr_tok = 0
    out_tok = 0
    local_est_gw = 0.0
    local_est_cw = 0.0
    has_fallback_est = False
    valid_items = []

    for r in rows:
        end_dt = parse_local_naive(r.get("endIso"))
        start_dt = parse_local_naive(r.get("startIso") or r.get("endIso"))
        if not end_dt or not start_dt or end_dt < since_dt:
            continue
        if until_dt is not None and end_dt >= until_dt:
            continue

        if r.get("status") == "long_gap":
            long_gap_count += 1
            continue

        if r.get("_any_false_reset"):
            false_reset_count += 1

        is_3p = is_third_party_model(r.get("model"))
        turns += 1
        step_cnt = int(r.get("invocations", 1))
        steps += step_cnt
        if is_3p:
            cg_turns += 1
            cg_steps += step_cnt

        tok = r.get("tokens") or {}
        in_tok += int(tok.get("input") or 0)
        cr_tok += int(tok.get("cacheRead") or 0)
        out_tok += int(tok.get("output") or 0)

        r_est, is_est_fb, _ = row_theoretical_weekly_info(r, weekly_rates, rate_preset=rate_preset)
        if r_est is not None:
            if is_est_fb:
                has_fallback_est = True
            if is_3p:
                local_est_cw += r_est
            else:
                local_est_gw += r_est

        valid_items.append((start_dt, end_dt, r))

    valid_items.sort(key=lambda x: (x[0], x[1]))

    active_gw, span_gw = _compute_pool_active_and_span(
        valid_items,
        "gemini_weekly",
        weekly_rates,
        model_filter=lambda r: not is_third_party_model(r.get("model")),
        five_h_to_weekly=five_h_to_weekly,
        rate_preset=rate_preset,
    )
    active_cw, span_cw = _compute_pool_active_and_span(
        valid_items,
        "claude_gpt_weekly",
        weekly_rates,
        model_filter=lambda r: is_third_party_model(r.get("model")),
        five_h_to_weekly=five_h_to_weekly,
        rate_preset=rate_preset,
    )

    return {
        "turns": turns,
        "steps": steps,
        "cg_turns": cg_turns,
        "cg_steps": cg_steps,
        "in_tok": in_tok,
        "cr_tok": cr_tok,
        "out_tok": out_tok,
        "local_est_gw": local_est_gw,
        "local_est_cw": local_est_cw,
        "has_fallback_est": has_fallback_est,
        "active_gw": active_gw,
        "span_gw": span_gw,
        "active_cw": active_cw,
        "span_cw": span_cw,
        "long_gap_count": long_gap_count,
        "false_reset_count": false_reset_count,
    }


def print_model_table(rows, weekly_rates, model_samples, rate_preset="none"):
    by_model = {}
    for r in rows:
        if r.get("status") == "long_gap":
            continue
        hook_m = str(r.get("model") or "auto")
        by_m = split_turn_steps_by_model(r)
        if by_m:
            turn_target = hook_m if hook_m in by_m else sorted(by_m.keys())[0]
            for m_k, tok_m in by_m.items():
                gm = by_model.setdefault(
                    m_k,
                    {"turns": 0, "steps": 0, "in": 0, "cr": 0, "out": 0, "compactions": 0},
                )
                if m_k == turn_target:
                    gm["turns"] += 1
                gm["steps"] += tok_m["count"]
                gm["in"] += tok_m["input"]
                gm["cr"] += tok_m["cacheRead"]
                gm["out"] += tok_m["output"]
                gm["compactions"] += tok_m["compactions"]
            continue

        g = by_model.setdefault(
            hook_m,
            {"turns": 0, "steps": 0, "in": 0, "cr": 0, "out": 0, "compactions": 0},
        )
        g["turns"] += 1
        g["steps"] += int(r.get("invocations", 1))
        tok = r.get("tokens") or {}
        g["in"] += int(tok.get("input") or 0)
        g["cr"] += int(tok.get("cacheRead") or 0)
        g["out"] += int(tok.get("output") or 0)
        g["compactions"] += int(tok.get("compactions") or 0)

    if not by_model:
        return

    print("\n=== 模型单价校准与累计消耗 (权重 In:Cache:Out = 1 : 0.05 : 5) ===")
    hdr = (
        f"{pad_r('模型', 24)} | {pad_l('轮/步', 8)} | {pad_l('未缓存 In', 9)} | "
        f"{pad_l('缓存 Cache (命中率)', 19)} | {pad_l('输出 Out', 8)} | "
        f"{pad_l('单价 / 1M等效', 16)} | {pad_l('本机理论合计', 12)}"
    )
    print(hdr)
    print("-" * disp_width(hdr))

    tot_turns = 0
    tot_steps = 0
    tot_in = 0
    tot_cr = 0
    tot_out = 0
    tot_gw = 0.0

    for m in sorted(by_model.keys()):
        g = by_model[m]
        tot_turns += g["turns"]
        tot_steps += g["steps"]
        tot_in += g["in"]
        tot_cr += g["cr"]
        tot_out += g["out"]

        tot_prompt = g["in"] + g["cr"]
        hit_pct = (100.0 * g["cr"] / tot_prompt) if tot_prompt > 0 else 0.0
        cache_str = f"{fmt_tok(g['cr'])} ({hit_pct:4.1f}%)" if tot_prompt > 0 else "-"
        w_rate, is_est_fb, _src_m = resolve_model_rate(m, weekly_rates, rate_preset=rate_preset)
        n_clean = len(model_samples.get(m, []))
        if w_rate is not None and str(_src_m).startswith("preset:"):
            rate_str = f"{w_rate:6.4f}%* (预设)"
        elif w_rate is not None and is_est_fb:
            rate_str = f"{w_rate:6.4f}%* (估)"
        elif w_rate is not None:
            rate_str = f"{w_rate:6.4f}% (n={n_clean})"
        else:
            rate_str = "待采集"
        eq_m = (W_INPUT * g["in"] + W_CACHE * g["cr"] + W_OUTPUT * g["out"]) / 1_000_000.0

        if w_rate is not None and (tot_prompt + g["out"]) > 0:
            m_gw = eq_m * w_rate
            if not is_third_party_model(m):
                tot_gw += m_gw
            est_gw = f"{m_gw:10.4f}%*" if is_est_fb else f"{m_gw:11.4f}%"
        else:
            est_gw = "-"

        ts_str = f"{g['turns']}/{g['steps']}"
        print(
            f"{pad_r(m[:24], 24)} | {pad_l(ts_str, 8)} | {pad_l(fmt_tok(g['in']), 9)} | "
            f"{pad_l(cache_str, 19)} | {pad_l(fmt_tok(g['out']), 8)} | "
            f"{pad_l(rate_str, 16)} | {pad_l(est_gw, 12)}"
        )

    print("-" * disp_width(hdr))
    all_prompt = tot_in + tot_cr
    all_hit = (100.0 * tot_cr / all_prompt) if all_prompt > 0 else 0.0
    all_cache_str = f"{fmt_tok(tot_cr)} ({all_hit:4.1f}%)" if all_prompt > 0 else "-"
    all_ts = f"{tot_turns}/{tot_steps}"
    print(
        f"{pad_r('合计 (账本本机总计)', 24)} | {pad_l(all_ts, 8)} | {pad_l(fmt_tok(tot_in), 9)} | "
        f"{pad_l(all_cache_str, 19)} | {pad_l(fmt_tok(tot_out), 8)} | "
        f"{pad_l('-', 16)} | {pad_l(f'{tot_gw:11.4f}%', 12)}"
    )


def build_recent_display_items(rows, expand_subagents):
    """Collapse consecutive subagent waves within 60s into a single summary row."""
    items = []
    for idx, r in enumerate(rows):
        is_sub = (r.get("terminationReason") == "TERMINAL_STEP_TYPE") and (r.get("status") == "ok")
        s_ep = r.get("startTs") or parse_iso_epoch(r.get("startIso")) or 0.0
        e_ep = r.get("ts") or parse_iso_epoch(r.get("endIso")) or s_ep

        if (
            not expand_subagents
            and is_sub
            and items
            and items[-1]["is_wave_candidate"]
            and items[-1]["workspace"] == (r.get("workspace") or "-")
            and items[-1]["model"] == str(r.get("model") or "auto")
            and (float(s_ep) - items[-1]["max_e_ep"]) <= 60.0
        ):
            grp = items[-1]
            grp["rows"].append((idx, r))
            grp["min_s_ep"] = min(grp["min_s_ep"], float(s_ep))
            grp["max_e_ep"] = max(grp["max_e_ep"], float(e_ep))
            grp["endIso"] = r.get("endIso") or grp["endIso"]
        else:
            items.append(
                {
                    "is_wave_candidate": is_sub,
                    "workspace": r.get("workspace") or "-",
                    "model": str(r.get("model") or "auto"),
                    "min_s_ep": float(s_ep),
                    "max_e_ep": float(e_ep),
                    "endIso": r.get("endIso") or "",
                    "rows": [(idx, r)],
                }
            )
    return items


def compute_display_item_metrics(item, overlapping, weekly_rates, five_h_to_weekly=FIVE_H_TO_WEEKLY, rate_preset="none"):
    """Compute display metrics (model label, tokens, theoretical %, measured %, status) for a group."""
    grp_rows = item["rows"]
    m_full = item["model"]
    m_base = short_model(m_full)
    if len(grp_rows) > 1:
        suffix = f" x{len(grp_rows)}"
        m_disp = m_base[: max(1, 18 - len(suffix))] + suffix
    else:
        m_disp = m_base[:18]

    steps = sum(int(r.get("invocations", 1)) for _, r in grp_rows)
    in_t = sum(int((r.get("tokens") or {}).get("input") or 0) for _, r in grp_rows)
    cr_t = sum(int((r.get("tokens") or {}).get("cacheRead") or 0) for _, r in grp_rows)
    out_t = sum(int((r.get("tokens") or {}).get("output") or 0) for _, r in grp_rows)
    billed = sum(int((r.get("tokens") or {}).get("billedSteps") or 0) for _, r in grp_rows)
    compactions = sum(int((r.get("tokens") or {}).get("compactions") or 0) for _, r in grp_rows)

    tok_str = f"{fmt_tok(in_t)}/{fmt_tok(cr_t)}/{fmt_tok(out_t)}" if billed > 0 else "-"
    est_val = None
    est_estimated = False
    if len(grp_rows) == 1:
        single_est, is_est_fb, _ = row_theoretical_weekly_info(grp_rows[0][1], weekly_rates, rate_preset=rate_preset)
        if billed > 0 and single_est is not None:
            est_val = single_est
            est_estimated = is_est_fb
            est_str = f"{single_est:8.4f}%*" if is_est_fb else f"{single_est:9.4f}%"
        else:
            est_str = "-"
    else:
        w_rate, is_est_fb, _ = resolve_model_rate(m_full, weekly_rates, rate_preset=rate_preset)
        eq_m = (W_INPUT * in_t + W_CACHE * cr_t + W_OUTPUT * out_t) / 1_000_000.0
        if billed > 0 and w_rate is not None:
            est_val = eq_m * w_rate
            est_estimated = is_est_fb
            est_str = f"{est_val:8.4f}%*" if is_est_fb else f"{est_val:9.4f}%"
        else:
            est_str = "-"

    contaminated = False
    if len(grp_rows) == 1:
        abs_idx, r = grp_rows[0]
        by_m = split_turn_steps_by_model(r)
        st = r.get("status") or "ok"
        flags = []
        if by_m and len(by_m) >= 2:
            if set(by_m.keys()) == {"gemini-pro-orchestrator", "gemini-flash-worker-agy"}:
                m_disp = "pro+flash-worker"[:18]
                flags.append(f"含Pro规划({by_m['gemini-pro-orchestrator']['count']}步)")
            else:
                m_disp = "+".join(short_model(k)[:8] for k in sorted(by_m))[:18]
                flags.append(f"混合({len(by_m)}模型)")
        if st == "long_gap":
            obs_str = "  跨休眠  "
            flags.append("跨休眠剔除")
        else:
            obs_val, obs_kind = turn_measured_weekly_delta(r, five_h_to_weekly=five_h_to_weekly)
            if obs_kind == "false_reset":
                obs_str = " 水位回退 "
                flags.append("假重置已剔除")
            else:
                obs_str = f"{obs_val:9.4f}%"
                if obs_kind == "mid_reset":
                    flags.append("跨周重置")
                if abs_idx in overlapping:
                    flags.append("并发重叠")
                if (
                    obs_val is not None
                    and est_val is not None
                    and est_val > 0
                    and (obs_val - est_val) > max(0.25, est_val * 1.5)
                    and "并发重叠" not in flags
                    and "跨周重置" not in flags
                ):
                    flags.append("含并发/脉冲")
                    contaminated = True
        if compactions > 0:
            flags.append("含压缩")
        st_label = "+".join(flags) if flags else "正常"
    else:
        is_3p = is_third_party_model(m_full)
        pk5 = "claude_gpt_5h" if is_3p else "gemini_5h"
        pkw = "claude_gpt_weekly" if is_3p else "gemini_weekly"
        sw_vals, ew_vals, s5_vals, e5_vals, ep5_set = [], [], [], [], set()
        for _, r in grp_rows:
            pw = (r.get("pools") or {}).get(pkw) or {}
            p5 = (r.get("pools") or {}).get(pk5) or {}
            if pw.get("start") is not None and pw.get("end") is not None and not pw.get("_false_reset"):
                sw_vals.append(float(pw["start"]))
                ew_vals.append(float(pw["end"]))
            if (
                not is_3p
                and p5.get("start") is not None
                and p5.get("end") is not None
                and not p5.get("_false_reset")
                and not p5.get("_mid_reset")
            ):
                ep5_set.add(p5.get("_win_epoch", 0))
                s5_vals.append(float(p5["start"]))
                e5_vals.append(float(p5["end"]))

        wave_gw = max(0.0, max(ew_vals) - min(sw_vals)) if (sw_vals and ew_vals) else 0.0
        if not is_3p and len(ep5_set) == 1 and len(s5_vals) == len(grp_rows):
            wave_5h_gw = max(0.0, max(e5_vals) - min(s5_vals)) * five_h_to_weekly
            if abs(wave_5h_gw - wave_gw) <= 0.002:
                wave_gw = wave_5h_gw
        obs_str = f"{wave_gw:9.4f}%"
        flags = [f"子代理波次({len(grp_rows)})"]
        if est_val is not None and est_val > 0 and (wave_gw - est_val) > max(0.25, est_val * 1.5):
            flags.append("含并发/脉冲")
            contaminated = True
        if compactions > 0:
            flags.append("含压缩")
        st_label = "+".join(flags)

    return {
        "m_disp": m_disp,
        "steps": steps,
        "tok_str": tok_str,
        "est_str": est_str,
        "obs_str": obs_str,
        "st_label": st_label,
        "contaminated": contaminated,
        "est_estimated": est_estimated,
    }


def print_recent_table(rows, overlapping, weekly_rates, recent_n, expand_subagents, five_h_to_weekly=FIVE_H_TO_WEEKLY, rate_preset="none"):
    display_items = build_recent_display_items(rows, expand_subagents)
    shown = display_items[-recent_n:] if recent_n > 0 else []
    if not shown:
        return

    mode_note = "逐条展开" if expand_subagents else "子代理波次自动折叠"
    print(f"\n=== 最近 {len(shown)} 组对话明细（{mode_note}）===")
    r_hdr = (
        f"{pad_r('结束时间', 19)} | {pad_r('项目', 10)} | {pad_r('模型', 18)} | "
        f"{pad_l('步', 4)} | {pad_l('Token (In/Cache/Out)', 22)} | "
        f"{pad_l('本机理论', 10)} | {pad_l('对话实测', 10)} | 状态"
    )
    print(r_hdr)
    print("-" * disp_width(r_hdr))

    for item in shown:
        end_str = (item["endIso"] or "")[:19].replace("T", " ")
        ws = item["workspace"][:10]
        met = compute_display_item_metrics(item, overlapping, weekly_rates, five_h_to_weekly=five_h_to_weekly, rate_preset=rate_preset)
        print(
            f"{pad_r(end_str, 19)} | {pad_r(ws, 10)} | {pad_r(met['m_disp'], 18)} | "
            f"{pad_l(met['steps'], 4)} | {pad_l(met['tok_str'], 22)} | "
            f"{pad_l(met['est_str'], 10)} | {pad_l(met['obs_str'], 10)} | {met['st_label']}"
        )


def print_step_details(rows, n_turns):
    target = rows[-n_turns:] if n_turns > 0 else []
    if not target:
        return
    print(f"\n=== 最近 {len(target)} 轮逐步骤 Token 明细 (--steps) ===")
    for r in target:
        end_str = (r.get("endIso") or "")[:19].replace("T", " ")
        ws = r.get("workspace") or "-"
        m = short_model(r.get("model"))
        tsteps = r.get("tokenSteps") or []
        print(f"[{end_str}] {ws} ({m}, conv={r.get('conversationId')}):")
        if not tsteps:
            print("  (暂无逐步骤 Token 明细，可运行 `agy-usage --backfill` 回填)")
            continue
        for s in tsteps:
            at_str = (s.get("at") or "")[11:19]
            stype = s.get("type") or "-"
            sm_str = f" [{short_model(s['model'])}]" if s.get("model") else ""
            print(
                f"  step #{s.get('step'):<4} {at_str:<8} {stype:<17} | "
                f"in={s.get('in', 0):>7,}  cache={s.get('cache', 0):>7,}  out={s.get('out', 0):>6,}{sm_str}"
            )


def detect_quota_week_start(rows, fallback_dt, monitor_rows=None, pool_key="gemini_weekly"):
    mon_key = "gw" if pool_key == "gemini_weekly" else "cw"
    best_row_ts = -1.0
    best_reset_dt = None

    for r in reversed(rows or []):
        pw = (r.get("pools") or {}).get(pool_key) or {}
        reset_dt = parse_local_naive(pw.get("resetsAt"))
        if reset_dt is not None:
            r_ts = float(r.get("ts") or parse_iso_epoch(r.get("endIso")) or 0.0)
            best_row_ts = r_ts
            best_reset_dt = reset_dt
            break

    if monitor_rows:
        for r in reversed(monitor_rows):
            if not r.get("ok"):
                continue
            res_s = (r.get("resets") or {}).get(mon_key)
            reset_dt = parse_local_naive(res_s)
            if reset_dt is not None:
                m_ts = float(r.get("ts") or parse_iso_epoch(r.get("iso")) or 0.0)
                if best_reset_dt is None or m_ts >= best_row_ts or reset_dt > best_reset_dt:
                    best_reset_dt = reset_dt
                break

    if best_reset_dt is not None:
        return best_reset_dt - timedelta(days=7)
    return fallback_dt


def reconcile_shared_pools(
    ledger_rows,
    monitor_rows,
    weekly_rates,
    since_dt,
    until_dt=None,
    live_snap=None,
    mon_summary=None,
    five_h_to_weekly=None,
    rate_preset="none",
):
    """Compute closed-loop shared-pool reconciliation (`localEst` vs `external/groupmates`)."""
    import agy_monitor

    if five_h_to_weekly is None:
        gem_ratio, _, _ = estimate_five_h_ratio(ledger_rows or [], monitor_rows=monitor_rows, pool="gemini")
        five_h_to_weekly = 1.0 / gem_ratio

    s_ts = since_dt.timestamp()
    u_ts = until_dt.timestamp() if until_dt is not None else None
    if mon_summary is None:
        mon_summary = agy_monitor.summarize_monitor_rows(
            monitor_rows or [],
            all_rows=monitor_rows or [],
            since_ts=s_ts,
            until_ts=u_ts,
        )

    period_sum = summarize_period(
        ledger_rows or [],
        since_dt,
        weekly_rates,
        until_dt=until_dt,
        five_h_to_weekly=five_h_to_weekly,
        rate_preset=rate_preset,
    )
    has_mon = len(mon_summary.get("clean_rows") or []) > 0
    live_pools = (live_snap or {}).get("pools") or {}

    def _build_one(mon_key, live_key, local_est, span_fallback):
        mon_total = float(mon_summary["pool_up"].get(mon_key) or 0.0)
        if has_mon:
            pool_total = mon_total
        else:
            live_used = (live_pools.get(live_key) or {}).get("usedPercent")
            if until_dt is None and live_used is not None:
                pool_total = float(live_used)
            else:
                pool_total = float(span_fallback or 0.0)

        mon_active = float(mon_summary.get(f"active_{mon_key}_up") or 0.0)
        mon_idle_on = float(mon_summary.get(f"online_idle_{mon_key}_up") or 0.0)
        mon_offline = float(mon_summary.get(f"offline_{mon_key}_up") or 0.0)

        ext_concurrent = max(0.0, mon_active - local_est)
        ext_total = max(0.0, pool_total - local_est)
        denom = pool_total if pool_total > 1e-6 else local_est
        local_share = (100.0 * min(local_est, denom) / denom) if denom > 1e-6 else 0.0
        ext_share = (100.0 * ext_total / denom) if denom > 1e-6 else 0.0

        return {
            "poolTotal": round(pool_total, 4),
            "localEst": round(local_est, 4),
            "monActive": round(mon_active, 4),
            "monIdleOnline": round(mon_idle_on, 4),
            "monOffline": round(mon_offline, 4),
            "externalConcurrent": round(ext_concurrent, 4),
            "externalTotal": round(ext_total, 4),
            "localSharePct": round(local_share, 1),
            "externalSharePct": round(ext_share, 1),
            "startClean": round(float((mon_summary.get("start_clean") or {}).get(mon_key) or 0.0), 4),
            "endClean": round(float((mon_summary.get("end_clean") or {}).get(mon_key) or 0.0), 4),
        }

    return {
        "sinceIso": since_dt.strftime("%Y-%m-%d %H:%M"),
        "hasMonitor": has_mon,
        "hasFallbackEst": bool(period_sum["has_fallback_est"]),
        "period": period_sum,
        "gemini": _build_one("gw", "gemini_weekly", period_sum["local_est_gw"], period_sum["span_gw"]),
        "claude_gpt": _build_one("cw", "claude_gpt_weekly", period_sum["local_est_cw"], period_sum["span_cw"]),
    }


def print_shared_pool_reconciliation(rec_gem, rec_cg):
    print("\n=== 共享池周对账（已去噪: 本机 vs 外部/群友）===")
    hdr = (
        f"{pad_r('共享池 (周周期)', 18)} | {pad_l('全池总耗', 10)} | "
        f"{pad_l('本机估算', 10)} | {pad_l('外部/群友', 10)} | "
        f"{pad_l('静置 / 离线 / 并发', 26)} | {pad_l('外部占比', 8)}"
    )
    print(hdr)
    print("-" * disp_width(hdr))
    for label, d, fb in (
        ("Gemini 周", rec_gem["gemini"], rec_gem["hasFallbackEst"]),
        ("Claude/GPT 周", rec_cg["claude_gpt"], False),
    ):
        est_s = f"{d['localEst']:8.4f}%*" if fb else f"{d['localEst']:9.4f}%"
        tot_s = f"{d['poolTotal']:.4f}%"
        ext_s = f"{d['externalTotal']:.4f}%"
        share_s = f"{d['externalSharePct']:.1f}%"
        bd = f"{d['monIdleOnline']:.2f}% / {d['monOffline']:.2f}% / {d['externalConcurrent']:.2f}%"
        print(
            f"{pad_r(label, 18)} | {pad_l(tot_s, 10)} | "
            f"{pad_l(est_s, 10)} | {pad_l(ext_s, 10)} | "
            f"{pad_l(bd, 26)} | {pad_l(share_s, 8)}"
        )


def print_footer_hint():
    print(
        "\nMore commands: `agy-usage --help`  "
        "(--live | --models | --steps N | --monitor | --expand-subagents)"
    )


def build_arg_parser():
    epilog_text = (
        "Examples:\n"
        "  agy-usage                     Show offline summary & calibrated model rates\n"
        "  agy-usage --live              Query live pool quota via LS RPC / Sidecar\n"
        "  agy-usage -n 25               Show recent 25 conversation groups\n"
        "  agy-usage --expand-subagents  Expand subagent waves instead of collapsing\n"
        "  agy-usage --steps 3           Show per-step tokens for the latest 3 turns\n"
        "  agy-usage --monitor           Show 1-minute monitor status & recent samples\n"
        "  agy-usage --monitor-changes   Show only monitor ticks with quota changes\n"
        "  agy-usage --monitor-watch     Follow monitor.jsonl live in terminal\n"
        "  agy-usage --on / --off        Toggle conversation hook tracking\n"
        "  agy-usage --preset ultra_5x   Set cold-start model rate preset (Ultra 5x/20x only)\n"
        "  agy-usage --backfill          Backfill missing tokens/step models from transcripts\n"
    )
    parser = argparse.ArgumentParser(
        prog="agy-usage",
        description="Antigravity local quota reconciliation & token ledger analyzer",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    g_view = parser.add_argument_group("View Options")
    g_view.add_argument("-n", "--recent", type=int, default=12, metavar="N", help="Recent conversation groups (default 12)")
    g_view.add_argument("--expand-subagents", action="store_true", help="Expand consecutive subagent rows")
    g_view.add_argument("--live", action="store_true", help="Query live pool quota via LS RPC / Sidecar")
    g_view.add_argument("--models", action="store_true", help="Show summary and calibrated models only")
    g_view.add_argument("--steps", type=int, default=0, metavar="N", help="Show per-step tokens for latest N turns")

    g_mon = parser.add_argument_group("1-Minute Monitor (monitor.jsonl)")
    g_mon.add_argument("--monitor", action="store_true", help="Show monitor status and recent samples")
    g_mon.add_argument("--monitor-changes", action="store_true", help="Show only ticks with quota changes")
    g_mon.add_argument("--monitor-watch", action="store_true", help="Stream new monitor ticks in terminal")

    g_maint = parser.add_argument_group("Hook & Ledger Maintenance")
    g_maint.add_argument("--on", action="store_true", help="Enable conversation hook tracking")
    g_maint.add_argument("--off", action="store_true", help="Pause conversation hook tracking")
    g_maint.add_argument(
        "--preset",
        choices=VALID_RATE_PRESETS,
        default=None,
        help="Set cold-start model rate preset (Ultra 5x/20x only; not for Pro/Free)",
    )
    g_maint.add_argument("--status", action="store_true", help="Show hook status and storage paths")
    g_maint.add_argument("--backfill", action="store_true", help="Backfill missing tokens from local transcripts")
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.monitor_watch or args.monitor or args.monitor_changes:
        import agy_monitor

        if args.monitor_watch:
            agy_monitor.watch_live()
            return
        rec_n = args.recent if ("-n" in sys.argv or "--recent" in sys.argv) else 20
        agy_monitor.print_status_and_log(recent_n=rec_n, changes_only=args.monitor_changes)
        print_footer_hint()
        return

    if args.on:
        set_hook_enabled(True)
        return
    if args.off:
        set_hook_enabled(False)
        return
    if args.preset is not None:
        chosen = set_rate_preset(args.preset)
        print(f"冷启动模型单价预设已更新: {chosen} ({CONFIG_PATH})")
        return
    if args.status:
        print(f"插件 Hook 当前状态: {'已启用 (ON)' if get_hook_enabled() else '已暂停 (OFF)'}")
        print(f"冷启动单价预设    : {get_rate_preset()}")
        print(f"Hook 配置文件位置 : {HOOKS_JSON_PATH}")
        print(f"偏好配置文件位置  : {CONFIG_PATH}")
        print(f"账本文件位置      : {LEDGER_PATH}")
        return
    if args.backfill:
        run_backfill()
        print()

    if args.live:
        print_live_quota()

    hook_on = get_hook_enabled()
    rate_preset = get_rate_preset()
    print(f"=== Antigravity 用量与 Token 账本 (默认口径: 周额度% | Hook: {'ON' if hook_on else 'OFF'}) ===")

    rows = load_entries()
    if not rows:
        print("暂无已记录的完整对话轮次（发送下一条消息并等待回复结束后即会自动入账）。")
        print(f"账本路径: {LEDGER_PATH}")
        print_footer_hint()
        return

    import agy_monitor

    monitor_rows = agy_monitor.load_monitor_rows()
    annotate_pool_anomalies(rows)
    overlapping, all_clusters = build_overlap_clusters(rows)
    gem_ratio, gem_n, gem_cal = estimate_five_h_ratio(rows, monitor_rows=monitor_rows, pool="gemini")
    five_h_to_w = 1.0 / gem_ratio
    weekly_rates, model_samples = calibrate_weekly_model_rates(
        rows, overlapping, all_clusters, monitor_rows=monitor_rows
    )

    if not args.live:
        print_last_snapshot_banner(rows)

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days7_start = now - timedelta(days=7)
    quota_wk_start = detect_quota_week_start(rows, days7_start, monitor_rows=monitor_rows, pool_key="gemini_weekly")
    cg_wk_start = detect_quota_week_start(rows, days7_start, monitor_rows=monitor_rows, pool_key="claude_gpt_weekly")

    periods = [
        ("今日 (Today)", today_start),
        ("当前周 (Current Wk)", quota_wk_start),
    ]

    hdr = (
        f"{pad_r('统计周期', 20)} | {pad_l('轮/步', 7)} | "
        f"{pad_l('本机 Token (In/Cache/Out)', 25)} | "
        f"{pad_l('本机理论', 10)} | {pad_l('对话实测', 10)} | {pad_l('全池总增', 10)}"
    )
    print("\n" + hdr)
    print("-" * disp_width(hdr))

    total_long_gaps = 0
    total_false_resets = 0
    has_fb_any = False
    for label, dt_start in periods:
        s = summarize_period(rows, dt_start, weekly_rates, five_h_to_weekly=five_h_to_w, rate_preset=rate_preset)
        if label == "当前周 (Current Wk)":
            total_long_gaps = s["long_gap_count"]
            total_false_resets = s["false_reset_count"]
        if s.get("has_fallback_est"):
            has_fb_any = True

        has_tok = (s["in_tok"] + s["cr_tok"] + s["out_tok"]) > 0
        tok_str = f"{fmt_tok(s['in_tok'])}/{fmt_tok(s['cr_tok'])}/{fmt_tok(s['out_tok'])}" if has_tok else "-"
        if has_tok:
            est_str = f"{s['local_est_gw']:8.4f}%*" if s.get("has_fallback_est") else f"{s['local_est_gw']:9.4f}%"
        else:
            est_str = "-"
        ts_str = f"{s['turns']}/{s['steps']}"
        act_str = f"{s['active_gw']:9.4f}%"
        spn_str = f"{s['span_gw']:9.4f}%"
        print(
            f"{pad_r(label, 20)} | {pad_l(ts_str, 7)} | "
            f"{pad_l(tok_str, 25)} | "
            f"{pad_l(est_str, 10)} | {pad_l(act_str, 10)} | {pad_l(spn_str, 10)}"
        )

    notes = []
    if rate_preset != "none":
        notes.append(f"冷启动单价预设: {rate_preset}（有本地实测时自动覆盖）")
    if gem_cal:
        notes.append(f"Gemini 5h:周 动态比例 {gem_ratio:.2f}:1 (n={gem_n})")
    if total_false_resets > 0:
        notes.append(f"{total_false_resets} 条服务端瞬时水位回退（假重置）已自动纠偏")
    if total_long_gaps > 0:
        notes.append(f"{total_long_gaps} 条跨休眠记录已自动剔除")
    if has_fb_any:
        notes.append("标 * 为同系列兜底或冷启动预设估算（待洁净样本校准）")
    if notes:
        print("* 注：" + "；".join(notes) + "。")

    if monitor_rows:
        rec_gem = reconcile_shared_pools(
            rows, monitor_rows, weekly_rates, quota_wk_start, five_h_to_weekly=five_h_to_w, rate_preset=rate_preset
        )
        rec_cg = (
            rec_gem
            if cg_wk_start == quota_wk_start
            else reconcile_shared_pools(
                rows, monitor_rows, weekly_rates, cg_wk_start, five_h_to_weekly=five_h_to_w, rate_preset=rate_preset
            )
        )
        print_shared_pool_reconciliation(rec_gem, rec_cg)

    print_model_table(rows, weekly_rates, model_samples, rate_preset=rate_preset)

    if args.models and args.recent == 12 and "--recent" not in sys.argv and "-n" not in sys.argv:
        pass
    elif args.recent > 0:
        print_recent_table(
            rows, overlapping, weekly_rates, args.recent, args.expand_subagents, five_h_to_weekly=five_h_to_w, rate_preset=rate_preset
        )

    if args.steps > 0:
        print_step_details(rows, args.steps)

    missing_tok = sum(1 for r in rows if not (r.get("tokens") or {}).get("billedSteps"))
    if missing_tok > 0:
        print(f"\n提示：账本中有 {missing_tok} 条旧记录尚未绑定本地 Token，可执行 `agy-usage --backfill` 回填。")

    print_footer_hint()


if __name__ == "__main__":
    main()
