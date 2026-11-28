#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive cross-platform unit tests for Antigravity Usage Monitor (v0.2.1)."""

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from datetime import datetime
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
for _p in (SRC_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class AgyUsageMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data_runtime")
        self.plugin_dir = os.path.join(self.tmp.name, "plugin")
        self.hooks_path = os.path.join(self.plugin_dir, "hooks.json")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.plugin_dir, exist_ok=True)

        self._old_env = {
            k: os.environ.get(k)
            for k in (
                "AGY_USAGE_DATA_DIR",
                "AGY_USAGE_PLUGIN_DIR",
                "AGY_HOOKS_JSON_PATH",
                "AGY_BRAIN_DIR",
                "AGY_USAGE_PROJECT_ROOT",
            )
        }
        os.environ["AGY_USAGE_DATA_DIR"] = self.data_dir
        os.environ["AGY_USAGE_PLUGIN_DIR"] = self.plugin_dir
        os.environ["AGY_HOOKS_JSON_PATH"] = self.hooks_path
        os.environ["AGY_USAGE_PROJECT_ROOT"] = REPO_ROOT

        for mod_name in (
            "paths",
            "common",
            "agy_monitor",
            "agy_usage",
            "hook",
            "dashboard_data",
            "dashboard_ui",
            "sidecar_daemon",
        ):
            if mod_name in sys.modules:
                importlib.reload(sys.modules[mod_name])
            else:
                importlib.import_module(mod_name)

        self.paths = sys.modules["paths"]
        self.common = sys.modules["common"]
        self.agy_monitor = sys.modules["agy_monitor"]
        self.agy_usage = sys.modules["agy_usage"]
        self.dashboard_data = sys.modules["dashboard_data"]
        self.dashboard_ui = sys.modules["dashboard_ui"]

    def tearDown(self):
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def _seed_sample_logs(self):
        now_ts = time.time()
        t1_s = now_ts - 7200.0
        t1_e = now_ts - 7180.0
        t2_s = now_ts - 1800.0
        t2_e = now_ts - 1780.0
        ledger_rows = [
            {
                "ts": t1_e,
                "startTs": t1_s,
                "startIso": datetime.fromtimestamp(t1_s).astimezone().isoformat(timespec="seconds"),
                "endIso": datetime.fromtimestamp(t1_e).astimezone().isoformat(timespec="seconds"),
                "durationSec": 20.0,
                "conversationId": "conv1111",
                "workspace": "ProjA",
                "model": "gemini-4-hydrogen-high",
                "invocations": 2,
                "terminationReason": "NO_TOOL_CALL",
                "status": "ok",
                "tokens": {
                    "input": 10000,
                    "cacheRead": 50000,
                    "output": 1000,
                    "total": 61000,
                    "billedSteps": 2,
                    "compactions": 0,
                },
                "tokenSteps": [],
                "pools": {
                    "gemini_5h": {"start": 10.0, "end": 10.2, "delta": 0.2, "reset": False, "resetsAt": "2099-01-01T18:00:00Z"},
                    "gemini_weekly": {"start": 5.0, "end": 5.05, "delta": 0.05, "reset": False, "resetsAt": "2099-01-07T07:01:45Z"},
                    "claude_gpt_5h": {"start": 0.0, "end": 0.0, "delta": 0.0, "reset": False, "resetsAt": ""},
                    "claude_gpt_weekly": {"start": 1.0, "end": 1.0, "delta": 0.0, "reset": False, "resetsAt": ""},
                },
            },
            {
                "ts": t2_e,
                "startTs": t2_s,
                "startIso": datetime.fromtimestamp(t2_s).astimezone().isoformat(timespec="seconds"),
                "endIso": datetime.fromtimestamp(t2_e).astimezone().isoformat(timespec="seconds"),
                "durationSec": 20.0,
                "conversationId": "conv2222",
                "workspace": "ProjB",
                "model": "gemini-4-hydrogen-high",
                "invocations": 1,
                "terminationReason": "NO_TOOL_CALL",
                "status": "ok",
                "tokens": {
                    "input": 5000,
                    "cacheRead": 20000,
                    "output": 500,
                    "total": 25500,
                    "billedSteps": 1,
                    "compactions": 0,
                },
                "tokenSteps": [],
                "pools": {
                    "gemini_5h": {"start": 10.2, "end": 10.3, "delta": 0.1, "reset": False, "resetsAt": "2099-01-01T18:00:00Z"},
                    "gemini_weekly": {"start": 5.05, "end": 5.075, "delta": 0.025, "reset": False, "resetsAt": "2099-01-07T07:01:45Z"},
                    "claude_gpt_5h": {"start": 0.0, "end": 0.0, "delta": 0.0, "reset": False, "resetsAt": ""},
                    "claude_gpt_weekly": {"start": 1.0, "end": 1.0, "delta": 0.0, "reset": False, "resetsAt": ""},
                },
            },
        ]
        with open(self.paths.LEDGER_PATH, "w", encoding="utf-8") as f:
            for r in ledger_rows:
                f.write(json.dumps(r) + "\n")

        monitor_rows = [
            {
                "ts": t1_e - 10.0,
                "iso": datetime.fromtimestamp(t1_e - 10.0).astimezone().isoformat(timespec="seconds"),
                "ok": True,
                "idleSec": 5.0,
                "localActive": 1,
                "changed": True,
                "g5": 10.2, "gw": 5.05, "c5": 0.0, "cw": 1.0,
                "dg5": 0.2, "dgw": 0.05, "dc5": 0.0, "dcw": 0.0,
                "events": [],
                "resets": {"g5": "2099-01-01T18:00:00Z", "gw": "2099-01-07T07:01:45Z", "c5": "", "cw": ""},
            },
            {
                "ts": t2_e - 10.0,
                "iso": datetime.fromtimestamp(t2_e - 10.0).astimezone().isoformat(timespec="seconds"),
                "ok": True,
                "idleSec": 300.0,
                "localActive": 0,
                "changed": True,
                "g5": 10.3, "gw": 5.10, "c5": 0.0, "cw": 1.25,
                "dg5": 0.1, "dgw": 0.05, "dc5": 0.0, "dcw": 0.25,
                "events": [],
                "resets": {"g5": "2099-01-01T18:00:00Z", "gw": "2099-01-07T07:01:45Z", "c5": "", "cw": ""},
            },
        ]
        with open(self.paths.MONITOR_LOG, "w", encoding="utf-8") as f:
            for r in monitor_rows:
                f.write(json.dumps(r) + "\n")

    def test_atomic_write_cleans_tmp_on_replace_failure(self):
        orig_replace = os.replace

        def fail_replace(_src, _dst):
            raise PermissionError("simulated EPERM")

        os.replace = fail_replace
        try:
            target = os.path.join(self.data_dir, "fail.json")
            with self.assertRaises(PermissionError):
                self.common.atomic_write_text(target, "hello")
        finally:
            os.replace = orig_replace
        leftover = [n for n in os.listdir(self.data_dir) if ".tmp." in n]
        self.assertEqual(leftover, [])

    def test_dynamic_multi_pool_and_argon_and_paygo_parsing(self):
        import urllib.request

        sample = {
            "response": {
                "groups": [
                    {
                        "displayName": "Gemini",
                        "buckets": [
                            {"bucketId": "gemini-5h", "remainingFraction": 0.875, "resetTime": "2026-11-20T12:51:16Z"},
                            {"bucketId": "gemini-weekly", "remaining": {"remainingFraction": "0.9125"}, "resetTime": "2026-11-25T00:35:06Z"},
                        ],
                    },
                    {
                        "displayName": "Argon",
                        "buckets": [
                            {"bucketId": "gemini-argon-wtu-weekly", "remainingFraction": 0.6, "resetTime": "2026-11-25T00:35:06Z"},
                        ],
                    },
                    {
                        "displayName": "Claude / GPT",
                        "buckets": [
                            {"bucketId": "3p-weekly", "remainingFraction": 0.95, "resetTime": "2026-11-26T09:38:27Z"},
                            {"bucketId": "custom-bonus-daily", "window": "weekly", "remainingFraction": 0.5, "resetTime": ""},
                        ],
                    },
                ]
            }
        }
        parsed = self.common._parse_ls_quota_response(sample)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["billingMode"], "subscription")
        self.assertIn("gemini_argon_weekly", parsed["pools"])
        self.assertAlmostEqual(parsed["pools"]["gemini_argon_weekly"]["usedPercent"], 40.0, places=4)
        self.assertAlmostEqual(parsed["pools"]["gemini_weekly"]["usedPercent"], 8.75, places=4)
        self.assertIn("custom_bonus_daily", parsed["pools"])
        self.assertEqual(parsed["pools"]["custom_bonus_daily"]["cadence"], "weekly")
        self.assertNotIn("claude_gpt_5h", parsed["pools"])

        # Pay-As-You-Go detection via GetUserStatus fallback when groups == []
        calls = []

        class _Resp:
            def __init__(self, obj):
                self._b = json.dumps(obj).encode("utf-8")
                self.status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self._b

        def fake_urlopen(req, timeout=0):
            calls.append(req.full_url)
            if "GetUserStatus" in req.full_url:
                return _Resp({"userStatus": {"userTier": {"id": "agy-business-paygo-tier"}}})
            return _Resp({"response": {"groups": []}})

        with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            snap = self.common.fetch_ls_quota(ls_addr="127.0.0.1:9999", csrf_token="tok", timeout_sec=2.0)

        self.assertIsNotNone(snap)
        self.assertEqual(snap["billingMode"], "paygo")
        self.assertEqual(snap["pools"], {})
        self.assertTrue(any("GetUserStatus" in u for u in calls))

    def test_fetch_ls_quota_sends_force_refresh_and_fallbacks(self):
        import urllib.request

        seen_bodies = []
        sample_resp = {
            "response": {
                "groups": [
                    {"buckets": [{"bucketId": "gemini-weekly", "remainingFraction": 0.9, "resetTime": ""}]}
                ]
            }
        }

        class _FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(sample_resp).encode("utf-8")

        def fake_urlopen(req, timeout=0):
            seen_bodies.append(req.data)
            if len(seen_bodies) == 1:
                raise RuntimeError("simulated forceRefresh error")
            return _FakeResp()

        with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            snap = self.common.fetch_ls_quota(ls_addr="127.0.0.1:9999", csrf_token="tok", timeout_sec=2.0)

        self.assertIsNotNone(snap)
        self.assertEqual(seen_bodies, [b'{"forceRefresh":true}', b"{}"])
        self.assertAlmostEqual(snap["pools"]["gemini_weekly"]["usedPercent"], 10.0, places=5)

    def test_monitor_ignores_stale_backward_resets_at_flaps(self):
        rows = [
            {
                "iso": "2026-11-18T07:27:00+08:00",
                "ok": True,
                "idleSec": 1000.0,
                "localActive": 0,
                "g5": 0.0, "gw": 18.49, "c5": 0.0, "cw": 28.38,
                "events": [],
                "resets": {"g5": "2026-11-18T04:27:00Z", "gw": "2026-11-22T07:01:45Z", "c5": "2026-11-18T04:27:00Z", "cw": "2026-11-22T14:42:02Z"},
            },
            {
                "iso": "2026-11-18T07:28:00+08:00",
                "ok": True,
                "idleSec": 1060.0,
                "localActive": 0,
                "g5": 0.0, "gw": 0.0, "c5": 0.0, "cw": 0.0,
                "events": ["reset:gw", "reset:cw"],
                "resets": {"g5": "2026-11-18T04:28:00Z", "gw": "2026-11-24T23:28:00Z", "c5": "2026-11-18T04:28:00Z", "cw": "2026-11-24T23:28:00Z"},
            },
            {
                "iso": "2026-11-18T07:29:00+08:00",
                "ok": True,
                "idleSec": 1120.0,
                "localActive": 0,
                "g5": 0.0, "gw": 18.49, "c5": 0.0, "cw": 28.38,
                "events": ["reset:gw", "reset:cw"],
                "resets": {"g5": "2026-11-18T04:29:00Z", "gw": "2026-11-22T07:01:45Z", "c5": "2026-11-18T04:29:00Z", "cw": "2026-11-22T14:42:02Z"},
            },
            {
                "iso": "2026-11-18T08:35:00+08:00",
                "ok": True,
                "idleSec": 5000.0,
                "localActive": 0,
                "g5": 1.0, "gw": 1.0, "c5": 0.0, "cw": 0.0,
                "events": ["reset:g5", "reset:gw"],
                "resets": {"g5": "2026-11-18T05:35:00Z", "gw": "2026-11-25T00:35:00Z", "c5": "2026-11-18T05:35:00Z", "cw": "2026-11-25T00:35:00Z"},
            },
        ]
        s = self.agy_monitor.summarize_monitor_rows(rows)
        self.assertAlmostEqual(s["idle_gw_up"], 1.0, places=5)
        self.assertAlmostEqual(s["idle_cw_up"], 0.0, places=5)
        self.assertEqual(s["reset_counts"]["gw"], 2)
        self.assertEqual(s["reset_counts"]["cw"], 1)

    def test_denoiser_erases_phantom_pulse_and_rollback_without_stealing_local(self):
        rows = [
            {
                "ts": 1794958000.0, "iso": "2026-11-18T08:34:00+08:00", "ok": True, "idleSec": 40000.0, "localActive": 0,
                "g5": 0.0, "gw": 0.0, "c5": 0.0, "cw": 0.0, "events": [],
                "resets": {"g5": "2026-11-18T05:34:00Z", "gw": "2026-11-25T00:34:00Z", "c5": "", "cw": ""},
            },
            {
                "ts": 1794958060.0, "iso": "2026-11-18T08:35:00+08:00", "ok": True, "idleSec": 40060.0, "localActive": 0,
                "g5": 1.001334, "gw": 1.00033, "c5": 0.0, "cw": 0.0, "events": ["reset:g5", "reset:gw"],
                "resets": {"g5": "2026-11-18T05:35:06Z", "gw": "2026-11-25T00:35:06Z", "c5": "", "cw": ""},
            },
            {
                "ts": 1794958900.0, "iso": "2026-11-18T08:49:00+08:00", "ok": True, "idleSec": 40900.0, "localActive": 0,
                "g5": 2.00267, "gw": 2.00066, "c5": 0.0, "cw": 0.0, "events": [],
                "resets": {"g5": "2026-11-18T05:35:06Z", "gw": "2026-11-25T00:35:06Z", "c5": "", "cw": ""},
            },
            {
                "ts": 1794963120.0, "iso": "2026-11-18T09:59:00+08:00", "ok": True, "idleSec": 45120.0, "localActive": 0,
                "g5": 0.86611, "gw": 0.21653, "c5": 0.0, "cw": 0.0, "events": ["rollback:g5(-0.5081%)", "rollback:gw(-0.8770%)"],
                "resets": {"g5": "2026-11-18T05:35:06Z", "gw": "2026-11-25T00:35:06Z", "c5": "", "cw": ""},
            },
            {
                "ts": 1794972000.0, "iso": "2026-11-18T12:27:00+08:00", "ok": True, "idleSec": 5.0, "localActive": 1,
                "g5": 2.0, "gw": 0.50, "c5": 0.0, "cw": 0.0, "events": [],
                "resets": {"g5": "2026-11-18T05:35:06Z", "gw": "2026-11-25T00:35:06Z", "c5": "", "cw": ""},
            },
        ]
        s = self.agy_monitor.summarize_monitor_rows(rows)
        self.assertAlmostEqual(s["idle_gw_up"], 0.21653, places=5)
        self.assertAlmostEqual(s["active_gw_up"], 0.50 - 0.21653, places=5)
        self.assertAlmostEqual(s["pool_up"]["gw"], 0.50, places=5)

    def test_denoiser_repairs_isolated_downward_dip(self):
        base_ts = 1794900000.0
        vals = [10.0, 10.2, 9.5, 10.2, 10.3]
        rows = [
            {
                "ts": base_ts + i * 60.0,
                "iso": f"2026-11-18T01:0{i}:00+08:00",
                "ok": True,
                "idleSec": 5.0,
                "localActive": 1,
                "g5": v * 4.0, "gw": v, "c5": 0.0, "cw": 0.0,
                "events": [],
                "resets": {"g5": "2026-11-18T00:00:00Z", "gw": "2026-11-25T00:00:00Z", "c5": "", "cw": ""},
            }
            for i, v in enumerate(vals)
        ]
        s = self.agy_monitor.summarize_monitor_rows(rows)
        self.assertAlmostEqual(s["pool_up"]["gw"], 0.3, places=5)

    def test_cross_day_continuous_attribution_captures_sleep_offline(self):
        ts_21 = datetime(2026, 11, 21, 23, 1, 0).timestamp()
        ts_22 = datetime(2026, 11, 22, 16, 48, 0).timestamp()
        rows = [
            {
                "ts": ts_21, "iso": "2026-11-21T23:01:00+08:00", "ok": True, "idleSec": 15000.0, "localActive": 0,
                "g5": 28.53, "gw": 7.88, "c5": 0.0, "cw": 100.0, "events": [],
                "resets": {"g5": "2026-11-21T15:38:38Z", "gw": "2026-11-28T10:38:38Z", "c5": "", "cw": "2026-11-26T09:38:27Z"},
            },
            {
                "ts": ts_22, "iso": "2026-11-22T16:48:00+08:00", "ok": True, "idleSec": 79560.0, "localActive": 0,
                "g5": 15.87, "gw": 26.53, "c5": 0.0, "cw": 100.0, "events": [],
                "resets": {"g5": "2026-11-22T13:15:57Z", "gw": "2026-11-28T10:38:38Z", "c5": "", "cw": "2026-11-26T09:38:27Z"},
            },
        ]
        day22_start = datetime(2026, 11, 22, 0, 0, 0).timestamp()
        day22_end = datetime(2026, 11, 23, 0, 0, 0).timestamp()
        s22 = self.agy_monitor.summarize_monitor_rows(
            [rows[1]], all_rows=rows, since_ts=day22_start, until_ts=day22_end
        )
        self.assertAlmostEqual(s22["offline_gw_up"], 18.65, places=4)
        self.assertAlmostEqual(s22["idle_gw_up"], 18.65, places=4)

    def test_external_bursts_bridges_clamped_plateau_clusters(self):
        def _mk(ts, iso, g5, gw, raw_gw, dg5, dgw, idle=False):
            return {
                "ts": ts, "iso": iso, "g5": g5, "gw": gw, "raw_gw": raw_gw,
                "c5": 0.0, "cw": 0.0, "dg5": dg5, "dgw": dgw, "dc5": 0.0, "dcw": 0.0,
                "pool_gaps": {"gw": 60.0, "cw": 60.0},
                "window_resets": {"g5": False, "gw": False, "c5": False, "cw": False},
                "idle": idle, "gap_sec": 60.0,
            }

        clean_rows = [
            _mk(1000.0, "2026-11-23T12:54:00+08:00", 0.60, 34.19, 34.19, 0.60, 0.15, idle=False),
            _mk(1120.0, "2026-11-23T12:56:00+08:00", 1.00, 34.56, 35.04, 0.40, 0.37, idle=False),
            _mk(1240.0, "2026-11-23T12:58:00+08:00", 1.80, 34.56, 34.65, 0.00, 0.00, idle=True),
            _mk(1360.0, "2026-11-23T13:08:00+08:00", 1.96, 34.56, 34.65, 0.16, 0.00, idle=False),
            _mk(1420.0, "2026-11-23T13:09:00+08:00", 2.06, 34.56, 35.43, 0.10, 0.00, idle=False),
            _mk(1480.0, "2026-11-23T13:10:00+08:00", 2.06, 34.56, 34.56, 0.00, 0.00, idle=True),
        ]
        ledger_rows = [
            {
                "ts": 1110.0, "startTs": 1000.0, "model": "gemini-4-hydrogen-high", "status": "ok",
                "tokens": {"input": 112000, "cacheRead": 0, "output": 0, "billedSteps": 1},
            },
            {
                "ts": 1410.0, "startTs": 1360.0, "model": "gemini-4-hydrogen-high", "status": "ok",
                "tokens": {"input": 96000, "cacheRead": 0, "output": 0, "billedSteps": 1},
            },
        ]
        rates = {"gemini-4-hydrogen-high": 2.5}
        self.assertEqual(
            self.dashboard_data._build_external_bursts(clean_rows, ledger_rows, weekly_rates=rates),
            [],
        )

        unclamped = [dict(r) for r in clean_rows]
        unclamped[1]["raw_gw"] = unclamped[1]["gw"]
        bursts_unclamped = self.dashboard_data._build_external_bursts(unclamped, ledger_rows, weekly_rates=rates)
        self.assertEqual(len(bursts_unclamped), 1)
        self.assertTrue(bursts_unclamped[0]["hasConcurrent"])
        self.assertAlmostEqual(bursts_unclamped[0]["concurrentGwDelta"], 0.24, places=2)

    def test_dynamic_five_h_to_weekly_ratio_calibration(self):
        # Simulate a non-Ultra 5:1 subscription tier (5h delta = 5x weekly delta) + weekly-only pool
        rows_5to1 = []
        base_ts = 1795400000.0
        for i in range(4):
            s = base_ts + i * 300.0
            e = s + 20.0
            rows_5to1.append(
                {
                    "ts": e,
                    "startTs": s,
                    "startIso": datetime.fromtimestamp(s).astimezone().isoformat(timespec="seconds"),
                    "endIso": datetime.fromtimestamp(e).astimezone().isoformat(timespec="seconds"),
                    "model": "gemini-4-hydrogen-high",
                    "status": "ok",
                    "invocations": 1,
                    "tokens": {"input": 100000, "cacheRead": 0, "output": 0, "billedSteps": 1},
                    "pools": {
                        "gemini_5h": {"start": i * 0.5, "end": (i + 1) * 0.5, "delta": 0.5, "reset": False, "resetsAt": "2099-01-01T12:00:00Z"},
                        "gemini_weekly": {"start": i * 0.1, "end": (i + 1) * 0.1, "delta": 0.1, "reset": False, "resetsAt": "2099-01-07T00:00:00Z"},
                    },
                }
            )
        self.agy_usage.annotate_pool_anomalies(rows_5to1)
        ratio, n_s, cal_ok = self.agy_usage.estimate_five_h_ratio(rows_5to1, pool="gemini")
        self.assertTrue(cal_ok)
        self.assertEqual(n_s, 4)
        self.assertAlmostEqual(ratio, 5.0, places=3)

        ov, cl = self.agy_usage.build_overlap_clusters(rows_5to1)
        rates, _ = self.agy_usage.calibrate_weekly_model_rates(rows_5to1, ov, cl)
        # 0.5% 5h * (1/5) = 0.10% weekly per 0.1M eqIn -> 1.00% / 1M EqIn!
        self.assertAlmostEqual(rates["gemini-4-hydrogen-high"], 1.0, places=4)

        # Weekly-only turn (missing gemini_5h pool) calibrates directly from weekly delta
        weekly_only_row = {
            "ts": base_ts + 2000.0,
            "startTs": base_ts + 1980.0,
            "model": "gemini-4-neon-high",
            "status": "ok",
            "invocations": 1,
            "tokens": {"input": 200000, "cacheRead": 0, "output": 0, "billedSteps": 1},
            "pools": {
                "gemini_weekly": {"start": 1.0, "end": 1.4, "delta": 0.4, "reset": False, "resetsAt": "2099-01-07T00:00:00Z"},
            },
        }
        self.agy_usage.annotate_pool_anomalies([weekly_only_row])
        ov2, cl2 = self.agy_usage.build_overlap_clusters([weekly_only_row])
        rates2, _ = self.agy_usage.calibrate_weekly_model_rates([weekly_only_row], ov2, cl2)
        self.assertAlmostEqual(rates2["gemini-4-neon-high"], 2.0, places=4)

    def test_per_step_model_and_quiet_window_golden_calibration(self):
        tp = os.path.join(self.tmp.name, "transcript_hybrid.jsonl")
        entries = [
            {"step_index": 10, "type": "PLANNER_RESPONSE", "created_at": "2026-11-22T10:00:05Z", "model": "gemini-4-neon-xhigh", "input_tokens": 100000, "cache_read_tokens": 0, "output_tokens": 0},
            {"step_index": 11, "type": "PLANNER_RESPONSE", "created_at": "2026-11-22T10:00:15Z", "model": "gemini-4-hydrogen-high", "input_tokens": 200000, "cache_read_tokens": 0, "output_tokens": 0},
        ]
        with open(tp, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        hook_mod = sys.modules["hook"]
        summary, steps = hook_mod.collect_turn_tokens(tp, start_step_index=9)
        self.assertEqual(summary["models"], ["gemini-4-hydrogen-high", "gemini-4-neon-xhigh"])
        self.assertEqual(steps[0]["model"], "gemini-4-neon-xhigh")

        t0 = datetime(2026, 11, 22, 11, 0, 0).timestamp()
        t_mix_s = t0 + 900.0
        t_mix_e = t_mix_s + 20.0
        mon_rows = [
            {"ts": t0 - 120.0, "ok": True, "g5": 4.0, "gw": 1.0, "c5": 0.0, "cw": 0.0, "resets": {"g5": "r1", "gw": "w1"}},
            {"ts": t0 - 60.0, "ok": True, "g5": 4.0, "gw": 1.0, "c5": 0.0, "cw": 0.0, "resets": {"g5": "r1", "gw": "w1"}},
            {"ts": t0 + 60.0, "ok": True, "g5": 4.2, "gw": 1.05, "c5": 0.0, "cw": 0.0, "resets": {"g5": "r1", "gw": "w1"}},
            {"ts": t0 + 120.0, "ok": True, "g5": 4.2, "gw": 1.05, "c5": 0.0, "cw": 0.0, "resets": {"g5": "r1", "gw": "w1"}},
            {"ts": t_mix_s - 120.0, "ok": True, "g5": 4.2, "gw": 1.05, "c5": 0.0, "cw": 0.0, "resets": {"g5": "r1", "gw": "w1"}},
            {"ts": t_mix_s - 60.0, "ok": True, "g5": 4.2, "gw": 1.05, "c5": 0.0, "cw": 0.0, "resets": {"g5": "r1", "gw": "w1"}},
            {"ts": t_mix_e + 60.0, "ok": True, "g5": 4.8, "gw": 1.20, "c5": 0.0, "cw": 0.0, "resets": {"g5": "r1", "gw": "w1"}},
            {"ts": t_mix_e + 120.0, "ok": True, "g5": 4.8, "gw": 1.20, "c5": 0.0, "cw": 0.0, "resets": {"g5": "r1", "gw": "w1"}},
        ]
        solo_golden = {
            "ts": t0 + 20.0, "startTs": t0, "model": "gemini-4-hydrogen-high", "status": "ok",
            "tokens": {"input": 200000, "cacheRead": 0, "output": 0, "billedSteps": 1, "searchWebCalls": 0, "errorSteps": 0},
            "tokenSteps": [{"step": 1, "model": "gemini-4-hydrogen-high", "in": 200000, "cache": 0, "out": 0}],
            "pools": {
                "gemini_5h": {"start": 4.0, "end": 4.2, "delta": 0.2, "reset": False, "resetsAt": "r1"},
                "gemini_weekly": {"start": 1.0, "end": 1.05, "delta": 0.05, "reset": False, "resetsAt": "w1"},
            },
        }
        mixed_golden = {
            "ts": t_mix_e, "startTs": t_mix_s, "model": "gemini-4-hydrogen-high", "status": "ok",
            "tokens": {"input": 300000, "cacheRead": 0, "output": 0, "billedSteps": 2, "searchWebCalls": 0, "errorSteps": 0},
            "tokenSteps": [
                {"step": 10, "model": "gemini-4-neon-xhigh", "in": 200000, "cache": 0, "out": 0},
                {"step": 11, "model": "gemini-4-hydrogen-high", "in": 200000, "cache": 0, "out": 0},
            ],
            "pools": {
                "gemini_5h": {"start": 4.2, "end": 4.8, "delta": 0.6, "reset": False, "resetsAt": "r1"},
                "gemini_weekly": {"start": 1.05, "end": 1.20, "delta": 0.15, "reset": False, "resetsAt": "w1"},
            },
        }
        rows = [solo_golden, mixed_golden]
        self.agy_usage.annotate_pool_anomalies(rows)
        ov, cl = self.agy_usage.build_overlap_clusters(rows)
        rates, _ = self.agy_usage.calibrate_weekly_model_rates(rows, ov, cl, monitor_rows=mon_rows)
        self.assertAlmostEqual(rates["gemini-4-hydrogen-high"], 0.25, places=4)
        self.assertAlmostEqual(rates["gemini-4-neon-xhigh"], 0.50, places=4)

    def test_backfill_enriches_existing_steps_losslessly(self):
        brain_tmp = os.path.join(self.tmp.name, "brain")
        conv_dir = os.path.join(brain_tmp, "abcd1234-9999-0000-1111-222233334444", ".system_generated", "logs")
        os.makedirs(conv_dir, exist_ok=True)
        with open(os.path.join(conv_dir, "transcript.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"step_index": 10, "type": "PLANNER_RESPONSE", "status": "DONE", "model": "gemini-4-neon-xhigh", "tool_calls": [{"name": "search_web"}]}) + "\n")
            f.write(json.dumps({"step_index": 11, "type": "PLANNER_RESPONSE", "status": "DONE", "model": "gemini-4-hydrogen-high", "tool_calls": []}) + "\n")

        legacy_row = {
            "ts": 1795300000.0, "startTs": 1795299980.0, "conversationId": "abcd1234",
            "model": "gemini-4-hydrogen-high", "status": "ok",
            "tokens": {"input": 12345, "cacheRead": 67890, "output": 1111, "total": 81346, "billedSteps": 2, "stepStart": 10, "stepEnd": 12},
            "tokenSteps": [
                {"step": 10, "in": 10000, "cache": 50000, "out": 500},
                {"step": 11, "in": 2345, "cache": 17890, "out": 611},
            ],
            "pools": {},
        }
        with open(self.paths.LEDGER_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(legacy_row) + "\n")

        old_brain = self.agy_usage.BRAIN_DIR
        self.agy_usage.BRAIN_DIR = brain_tmp
        try:
            self.agy_usage.run_backfill()
        finally:
            self.agy_usage.BRAIN_DIR = old_brain

        loaded = self.agy_usage.load_entries()
        self.assertEqual(loaded[0]["tokens"]["input"], 12345)
        self.assertEqual(loaded[0]["tokens"]["models"], ["gemini-4-hydrogen-high", "gemini-4-neon-xhigh"])
        self.assertEqual(loaded[0]["tokens"]["searchWebCalls"], 1)
        self.assertEqual(loaded[0]["tokenSteps"][0]["model"], "gemini-4-neon-xhigh")

    def test_recent_changes_excludes_denoised_zero_noise_and_bilingual_ui(self):
        self._seed_sample_logs()
        now_ts = time.time()
        base_ts = now_ts - 600.0
        recs = [
            {
                "ts": base_ts, "iso": datetime.fromtimestamp(base_ts).astimezone().isoformat(timespec="seconds"),
                "ok": True, "idleSec": 10.0, "localActive": 1, "g5": 1.0, "gw": 10.0, "c5": 0.0, "cw": 5.0,
                "dg5": 0.0, "dgw": 0.0, "dc5": 0.0, "dcw": 0.0, "events": [],
                "resets": {"g5": "2099-01-01T00:00:00Z", "gw": "2099-01-07T00:00:00Z", "c5": "", "cw": ""},
            },
            {
                "ts": base_ts + 60.0, "iso": datetime.fromtimestamp(base_ts + 60.0).astimezone().isoformat(timespec="seconds"),
                "ok": True, "idleSec": 300.0, "localActive": 0, "g5": 1.75, "gw": 10.75, "c5": 0.0, "cw": 5.0,
                "dg5": 0.75, "dgw": 0.75, "dc5": 0.0, "dcw": 0.0, "events": [],
                "resets": {"g5": "2099-01-01T00:00:00Z", "gw": "2099-01-07T00:00:00Z", "c5": "", "cw": ""},
            },
            {
                "ts": base_ts + 120.0, "iso": datetime.fromtimestamp(base_ts + 120.0).astimezone().isoformat(timespec="seconds"),
                "ok": True, "idleSec": 360.0, "localActive": 0, "g5": 1.0, "gw": 10.0, "c5": 0.0, "cw": 5.0,
                "dg5": -0.75, "dgw": -0.75, "dc5": 0.0, "dcw": 0.0, "events": ["rollback:g5", "rollback:gw"],
                "resets": {"g5": "2099-01-01T00:00:00Z", "gw": "2099-01-07T00:00:00Z", "c5": "", "cw": ""},
            },
            {
                "ts": base_ts + 180.0, "iso": datetime.fromtimestamp(base_ts + 180.0).astimezone().isoformat(timespec="seconds"),
                "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 1.40, "gw": 10.10, "c5": 0.0, "cw": 5.0,
                "dg5": 0.40, "dgw": 0.10, "dc5": 0.0, "dcw": 0.0, "events": [],
                "resets": {"g5": "2099-01-01T00:00:00Z", "gw": "2099-01-07T00:00:00Z", "c5": "", "cw": ""},
            },
        ]
        with open(self.paths.MONITOR_LOG, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

        payload = self.dashboard_data.build_dashboard_payload(window="24h", recent_n=10, live=False)
        chgs = payload["monitor"]["recentChanges"]
        self.assertEqual(len(chgs), 1)
        self.assertAlmostEqual(chgs[0]["dgw"], 0.10, places=4)
        self.assertIn("diagnostics", payload)
        self.assertEqual(payload["diagnostics"]["version"], "0.2.1")

        # Verify in-memory summary generation writes zero files
        before_files = set(os.listdir(self.data_dir))
        for lang in ("zh-CN", "en"):
            res = self.dashboard_data.perform_action("export_summary", {"lang": lang})
            self.assertTrue(res["ok"])
            self.assertIn("0.2.1", res["content"])
        self.assertEqual(set(os.listdir(self.data_dir)), before_files)

        # Verify bilingual UI markers & zero host CSS regressions
        html = self.dashboard_ui.DASHBOARD_HTML
        self.assertNotIn("var(--muted)", html)
        self.assertNotIn('preserveAspectRatio="none"', html)
        for token in ("rem.toFixed(3)", "fmtNegDelta(r.dg5)", "Remaining Quota", "当前剩余额度", "paygoNotice"):
            self.assertIn(token, html)

    def test_sidecar_hot_reload_cascades_upstream_to_downstream(self):
        sidecar_daemon = sys.modules["sidecar_daemon"]
        sidecar_daemon._maybe_reload_web_modules(force=True)
        sidecar_daemon._WEB_MTIMES["agy_usage"] -= 10.0

        reloaded_names = []

        def _fake_reload(mod):
            reloaded_names.append(mod.__name__)
            return mod

        with mock.patch("sidecar_daemon.importlib.reload", side_effect=_fake_reload):
            sidecar_daemon._maybe_reload_web_modules(force=True)

        self.assertEqual(reloaded_names, ["agy_usage", "dashboard_data"])
        self.assertNotIn("dashboard_ui", reloaded_names)

    def test_manage_install_uninstall_and_package_roundtrip(self):
        import manage

        p_dir = os.path.join(self.tmp.name, "installed_plugin")
        cli_dst = os.path.join(self.tmp.name, "bin", "agy-usage")
        info = manage.install_plugin(plugin_dir=p_dir, with_cli=True, cli_path=cli_dst)

        self.assertTrue(os.path.isfile(os.path.join(p_dir, "plugin.json")))
        self.assertTrue(os.path.isfile(os.path.join(p_dir, "logo.svg")))
        self.assertTrue(os.path.isfile(os.path.join(p_dir, "hooks.json")))
        self.assertTrue(os.path.isfile(os.path.join(p_dir, "skills", "agy-usage", "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(p_dir, "sidecars", "usage_monitor_daemon", "sidecar.json")))
        self.assertTrue(os.path.isfile(os.path.join(p_dir, "sidecars", "usage_monitor_daemon", "sidecar_daemon.py")))
        self.assertTrue(os.path.isfile(info["cliPath"]))

        # Preserve hook disabled state across upgrade/reinstall
        with open(os.path.join(p_dir, "hooks.json"), "r", encoding="utf-8") as f:
            hcfg = json.load(f)
        hcfg["antigravity-quota-tracker"]["enabled"] = False
        with open(os.path.join(p_dir, "hooks.json"), "w", encoding="utf-8") as f:
            json.dump(hcfg, f)

        reinstall = manage.install_plugin(plugin_dir=p_dir, with_cli=False)
        self.assertFalse(reinstall["hookEnabled"])
        with open(os.path.join(p_dir, "hooks.json"), "r", encoding="utf-8") as f:
            self.assertFalse(json.load(f)["antigravity-quota-tracker"]["enabled"])

        # Test release packaging + sha256 verification
        pkg_dir = os.path.join(self.tmp.name, "dist_out")
        pkg = manage.package_release(out_dir=pkg_dir)
        self.assertTrue(os.path.isfile(pkg["zipPath"]))
        self.assertTrue(os.path.isfile(pkg["sha256Path"]))
        with zipfile.ZipFile(pkg["zipPath"], "r") as zf:
            names = set(zf.namelist())
            self.assertIn("agy-usagemonitor-0.2.1/src/sidecar_daemon.py", names)
            self.assertIn("agy-usagemonitor-0.2.1/scripts/manage.py", names)
            self.assertIn("agy-usagemonitor-0.2.1/plugin/plugin.json", names)

        h = hashlib.sha256()
        with open(pkg["zipPath"], "rb") as f:
            h.update(f.read())
        self.assertEqual(h.hexdigest(), pkg["sha256"])

        # Test uninstall removes plugin while preserving DATA_DIR
        self._seed_sample_logs()
        un = manage.uninstall_plugin(plugin_dir=p_dir, purge_data=False, cli_path=cli_dst)
        self.assertTrue(un["removedPlugin"])
        self.assertTrue(un["removedCli"])
        self.assertFalse(un["removedData"])
        self.assertFalse(os.path.exists(p_dir))
        self.assertTrue(os.path.isfile(self.paths.LEDGER_PATH))

    def test_cold_start_rate_presets_and_local_override(self):
        # 1. Default preset is 'none' (no hardcoded rates injected, read-only)
        self.assertEqual(self.agy_usage.get_rate_preset(), "none")
        self.assertFalse(os.path.exists(self.paths.CONFIG_PATH))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-carbon-medium", {}, "none"), (None, False, ""))

        # 2. Ultra 5x priors: carbon/neon/hydrogen only; argon & 3p remain None
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-carbon-medium", {}, "ultra_5x"), (1.0, True, "preset:ultra_5x"))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-pro-orchestrator", {}, "ultra_5x"), (1.0, True, "preset:ultra_5x"))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-neon-high", {}, "ultra_5x"), (0.5, True, "preset:ultra_5x"))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-hydrogen-high", {}, "ultra_5x"), (0.25, True, "preset:ultra_5x"))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-flash-worker-agy", {}, "ultra_5x"), (0.25, True, "preset:ultra_5x"))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-argon-high", {}, "ultra_5x"), (None, False, ""))
        self.assertEqual(self.agy_usage.resolve_model_rate("claude-4-sonnet", {}, "ultra_5x"), (None, False, ""))

        # 3. Ultra 20x scales weekly % per 1M EqIn by 0.25 (4x pool capacity)
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-carbon-medium", {}, "ultra_20x"), (0.25, True, "preset:ultra_20x"))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-neon-medium", {}, "ultra_20x"), (0.125, True, "preset:ultra_20x"))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-hydrogen-xhigh", {}, "ultra_20x"), (0.0625, True, "preset:ultra_20x"))
        self.assertEqual(self.agy_usage.resolve_model_rate("gemini-4-argon-medium", {}, "ultra_20x"), (None, False, ""))

        # 4. Local exact & same-family calibrated rates always override preset priors
        local_rates = {"gemini-4-hydrogen-high": 0.30, "gemini-4-neon-high": 0.55}
        self.assertEqual(
            self.agy_usage.resolve_model_rate("gemini-4-hydrogen-high", local_rates, "ultra_5x"),
            (0.30, False, "gemini-4-hydrogen-high"),
        )
        self.assertEqual(
            self.agy_usage.resolve_model_rate("gemini-4-neon-xhigh", local_rates, "ultra_5x"),
            (0.55, True, "gemini-4-neon-high"),
        )
        self.assertEqual(
            self.agy_usage.resolve_model_rate("gemini-4-carbon-medium", local_rates, "ultra_5x"),
            (1.0, True, "preset:ultra_5x"),
        )

        # 5. Dashboard action persists preset & reflects in payload + HTML
        bad_res = self.dashboard_data.perform_action("set_preset", {"preset": "pro_tier"})
        self.assertFalse(bad_res["ok"])

        self._seed_sample_logs()
        with open(self.paths.LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": time.time() - 600.0,
                        "startTs": time.time() - 620.0,
                        "startIso": datetime.fromtimestamp(time.time() - 620.0).astimezone().isoformat(timespec="seconds"),
                        "endIso": datetime.fromtimestamp(time.time() - 600.0).astimezone().isoformat(timespec="seconds"),
                        "model": "gemini-4-carbon-medium",
                        "status": "ok",
                        "invocations": 1,
                        "tokens": {"input": 100000, "cacheRead": 0, "output": 0, "billedSteps": 1},
                        "pools": {},
                    }
                )
                + "\n"
            )

        ok_res = self.dashboard_data.perform_action("set_preset", {"preset": "ultra_20x"})
        self.assertTrue(ok_res["ok"])
        self.assertEqual(self.agy_usage.get_rate_preset(), "ultra_20x")

        payload = self.dashboard_data.build_dashboard_payload(window="24h", recent_n=10, live=False)
        self.assertEqual(payload["ratePreset"], "ultra_20x")
        self.assertEqual(payload["diagnostics"]["ratePreset"], "ultra_20x")
        carbon_row = next(m for m in payload["models"] if m["model"] == "gemini-4-carbon-medium")
        self.assertEqual(carbon_row["rateKind"], "preset")
        self.assertAlmostEqual(carbon_row["rateWeekly"], 0.25, places=4)
        self.assertAlmostEqual(carbon_row["estGw"], 0.025, places=4)

        html = self.dashboard_ui.DASHBOARD_HTML
        self.assertIn("presetSelect", html)
        self.assertIn("set_preset", html)

    def test_pass15_gemini_prereservation_pairing_and_weekly_only_guard(self):
        # Delayed >2h rollback should restore settled real spend back to its active origin ticks,
        # erase 1-tick exact bounces, and skip weekly-only segments without a 5h pool.
        base_ts = 1795500000.0
        resets_ok = {"g5": "2099-01-01T14:00:00Z", "gw": "2099-01-07T07:00:00Z", "c5": "", "cw": ""}
        rows = [
            {"ts": base_ts + 0.0, "iso": "2026-11-26T09:20:00+08:00", "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 0.0, "gw": 1.0000, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            # 1-tick exact replica bounce
            {"ts": base_ts + 60.0, "iso": "2026-11-26T09:21:00+08:00", "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 0.4, "gw": 1.8000, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            {"ts": base_ts + 120.0, "iso": "2026-11-26T09:22:00+08:00", "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 0.0, "gw": 1.0000, "c5": 0.0, "cw": 0.0, "events": ["rollback:gw(-0.8000%)"], "resets": resets_ok},
            # Pre-reservation #1 (+1.0000%) + real active spend (+0.2211% gw, +0.8844% g5)
            {"ts": base_ts + 180.0, "iso": "2026-11-26T09:23:00+08:00", "ok": True, "idleSec": 10.0, "localActive": 1, "g5": 0.8844, "gw": 2.2211, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            # Pre-reservation #2 + real active spend (+0.1544% gw, +0.6176% g5)
            {"ts": base_ts + 2580.0, "iso": "2026-11-26T10:03:00+08:00", "ok": True, "idleSec": 10.0, "localActive": 1, "g5": 1.5020, "gw": 2.3755, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            # Delayed TTL refund of 1.0000%
            {"ts": base_ts + 9000.0, "iso": "2026-11-26T11:50:00+08:00", "ok": True, "idleSec": 300.0, "localActive": 0, "g5": 1.5020, "gw": 1.3755, "c5": 0.0, "cw": 0.0, "events": ["rollback:gw(-1.0000%)"], "resets": resets_ok},
        ]
        tl = self.agy_monitor.clean_monitor_timeline(rows, five_h_to_weekly=0.25)
        self.assertEqual(tl[1]["dgw"], 0.0)
        self.assertAlmostEqual(tl[3]["dgw"], 0.2211, places=4)
        self.assertTrue(tl[3]["preres_paired"])
        self.assertAlmostEqual(tl[4]["dgw"], 0.1544, places=4)
        self.assertAlmostEqual(tl[-1]["gw"], 1.3755, places=4)

        # Weekly-only guard: when g5 is empty/absent, Pass 1.5b must not mis-classify weekly ticks
        wk_resets = {"g5": "", "gw": "2099-01-07T07:00:00Z", "c5": "", "cw": ""}
        wk_rows = [
            {"ts": base_ts + 0.0, "iso": "2026-11-26T09:00:00+08:00", "ok": True, "idleSec": 10.0, "localActive": 1, "g5": 0.0, "gw": 1.0, "c5": 0.0, "cw": 0.0, "events": [], "resets": wk_resets},
            {"ts": base_ts + 60.0, "iso": "2026-11-26T09:01:00+08:00", "ok": True, "idleSec": 10.0, "localActive": 1, "g5": 0.0, "gw": 2.0, "c5": 0.0, "cw": 0.0, "events": [], "resets": wk_resets},
            {"ts": base_ts + 120.0, "iso": "2026-11-26T09:02:00+08:00", "ok": True, "idleSec": 10.0, "localActive": 1, "g5": 0.0, "gw": 2.0, "c5": 0.0, "cw": 0.0, "events": [], "resets": wk_resets},
        ]
        wk_tl = self.agy_monitor.clean_monitor_timeline(wk_rows, five_h_to_weekly=0.25)
        self.assertEqual(wk_tl[1]["unmatched_preres_open_gw"], 0.0)
        self.assertFalse(wk_tl[1]["preres_paired"])

    def test_pass3_active_aware_anchor_alignment_prevents_idle_teleport(self):
        base_ts = 1795600000.0
        resets_ok = {"g5": "2099-01-01T14:00:00Z", "gw": "2099-01-07T07:00:00Z", "c5": "", "cw": ""}
        rows = [
            {"ts": base_ts + 0.0, "iso": "2026-11-25T22:20:00+08:00", "ok": True, "idleSec": 400.0, "localActive": 0, "g5": 0.0, "gw": 5.00, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            # Idle pre-reservation spike before local active turn
            {"ts": base_ts + 60.0, "iso": "2026-11-25T22:21:00+08:00", "ok": True, "idleSec": 460.0, "localActive": 0, "g5": 1.0, "gw": 6.00, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            # Local active turn starts while raw_gw still elevated, later settles at 5.20
            {"ts": base_ts + 120.0, "iso": "2026-11-25T22:22:00+08:00", "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 1.8, "gw": 6.20, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            {"ts": base_ts + 180.0, "iso": "2026-11-25T22:23:00+08:00", "ok": True, "idleSec": 10.0, "localActive": 1, "g5": 0.8, "gw": 5.20, "c5": 0.0, "cw": 0.0, "events": ["rollback:gw(-1.0000%)"], "resets": resets_ok},
        ]
        tl = self.agy_monitor.clean_monitor_timeline(rows, five_h_to_weekly=0.25)
        self.assertAlmostEqual(tl[1]["dgw"], 0.0, places=5)
        self.assertAlmostEqual(tl[2]["dgw"], 0.20, places=5)

    def test_empty_resets_at_stale_replica_and_week_start_detection(self):
        base_ts = 1795700000.0
        rows = [
            {"ts": base_ts, "iso": "2026-11-25T00:34:00+08:00", "ok": True, "idleSec": 500.0, "localActive": 0, "g5": 0.0, "gw": 40.0, "c5": 0.0, "cw": 0.0, "events": [], "resets": {"g5": "", "gw": "2026-11-25T00:35:00Z", "c5": "", "cw": ""}},
            # Genuine reset where backend temporarily returns empty resetsAt
            {"ts": base_ts + 60.0, "iso": "2026-11-25T00:35:00+08:00", "ok": True, "idleSec": 560.0, "localActive": 0, "g5": 0.0, "gw": 0.0, "c5": 0.0, "cw": 0.0, "events": ["reset:gw"], "resets": {"g5": "", "gw": "", "c5": "", "cw": ""}},
            # Stale replica flaps back with old value and old resetsAt within 15m
            {"ts": base_ts + 120.0, "iso": "2026-11-25T00:36:00+08:00", "ok": True, "idleSec": 620.0, "localActive": 0, "g5": 0.0, "gw": 40.0, "c5": 0.0, "cw": 0.0, "events": [], "resets": {"g5": "", "gw": "2026-11-25T00:35:00Z", "c5": "", "cw": ""}},
            # Settled new cycle
            {"ts": base_ts + 240.0, "iso": "2026-11-25T00:38:00+08:00", "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 0.8, "gw": 0.2, "c5": 0.0, "cw": 0.0, "events": [], "resets": {"g5": "", "gw": "2026-12-02T00:38:00Z", "c5": "", "cw": ""}},
        ]
        s = self.agy_monitor.summarize_monitor_rows(rows)
        self.assertAlmostEqual(s["pool_up"]["gw"], 0.2, places=4)
        wk_start = self.agy_usage.detect_quota_week_start([], datetime(2026, 11, 20), monitor_rows=rows, pool_key="gemini_weekly")
        # 2026-12-02T00:38:00Z minus 7 days -> local naive November 25 UTC equivalent
        self.assertEqual(wk_start.day, 25)

    def test_local_token_correction_rule_a_and_multi_stacked_rule_b(self):
        base_ts = 1795800000.0
        resets_ok = {"g5": "2099-01-01T14:00:00Z", "gw": "2099-01-07T07:00:00Z", "c5": "", "cw": ""}
        rows = [
            {"ts": base_ts + 0.0, "iso": datetime.fromtimestamp(base_ts).astimezone().isoformat(timespec="seconds"), "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 0.0, "gw": 0.0, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            # Two stacked +1.0% pre-reservations interleaved with -0.25 g5-only offsets, plus 0.15% real local turn
            {"ts": base_ts + 60.0, "iso": datetime.fromtimestamp(base_ts + 60.0).astimezone().isoformat(timespec="seconds"), "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 1.0, "gw": 1.0, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            {"ts": base_ts + 120.0, "iso": datetime.fromtimestamp(base_ts + 120.0).astimezone().isoformat(timespec="seconds"), "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 1.4, "gw": 1.15, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
            {"ts": base_ts + 180.0, "iso": datetime.fromtimestamp(base_ts + 180.0).astimezone().isoformat(timespec="seconds"), "ok": True, "idleSec": 5.0, "localActive": 1, "g5": 2.4, "gw": 2.15, "c5": 0.0, "cw": 0.0, "events": [], "resets": resets_ok},
        ]
        # Ultra 5x preset gives 0.25%/1M EqIn for hydrogen; 600k uncached input -> 0.15% theoretical local
        ledger = [
            {
                "ts": base_ts + 125.0,
                "startTs": base_ts + 65.0,
                "startIso": datetime.fromtimestamp(base_ts + 65.0).astimezone().isoformat(timespec="seconds"),
                "endIso": datetime.fromtimestamp(base_ts + 125.0).astimezone().isoformat(timespec="seconds"),
                "model": "gemini-4-hydrogen-high",
                "status": "ok",
                "invocations": 1,
                "tokens": {"input": 600000, "cacheRead": 0, "output": 0, "billedSteps": 1},
                "pools": {
                    "gemini_5h": {"start": 1.0, "end": 1.4, "delta": 0.4, "reset": False, "resetsAt": resets_ok["g5"]},
                    "gemini_weekly": {"start": 1.0, "end": 1.15, "delta": 0.15, "reset": False, "resetsAt": resets_ok["gw"]},
                },
            }
        ]
        self.agy_usage.annotate_pool_anomalies(ledger)
        rec = self.agy_usage.reconcile_shared_pools(
            ledger,
            rows,
            {},
            datetime.fromtimestamp(base_ts - 60.0),
            five_h_to_weekly=0.25,
            rate_preset="ultra_5x",
        )
        gem = rec["gemini"]
        self.assertAlmostEqual(gem["localEst"], 0.15, places=3)
        self.assertAlmostEqual(gem["poolTotal"], 0.15, places=3)
        self.assertAlmostEqual(gem["externalTotal"], 0.0, places=3)
        self.assertGreater(gem["pendingPreReservation"], 1.9)
        self.assertAlmostEqual(
            gem["externalTotal"],
            gem["monIdleOnline"] + gem["monOffline"] + gem["externalConcurrent"],
            places=3,
        )

    def test_hook_placeholder_step_and_transcript_auto_sync(self):
        brain_tmp = os.path.join(self.tmp.name, "brain_sync")
        conv_uuid = "sync1234-aaaa-bbbb-cccc-ddddeeeeffff"
        conv_dir = os.path.join(brain_tmp, conv_uuid, ".system_generated", "logs")
        os.makedirs(conv_dir, exist_ok=True)
        tp = os.path.join(conv_dir, "transcript.jsonl")
        now_ep = time.time() - 300.0
        lines = [
            # Placeholder zero-token step must be ignored by get_transcript_max_step and seen_steps
            {"step_index": 0, "type": "USER_INPUT", "created_at": datetime.fromtimestamp(now_ep - 20).astimezone().isoformat(timespec="seconds")},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": datetime.fromtimestamp(now_ep - 10).astimezone().isoformat(timespec="seconds"), "model": "gemini-4-hydrogen-high", "input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0},
        ]
        with open(tp, "w", encoding="utf-8") as f:
            for item in lines:
                f.write(json.dumps(item) + "\n")

        hook_mod = sys.modules["hook"]
        self.assertEqual(hook_mod.get_transcript_max_step(tp), -1)

        # Append billed update to step 1 plus step 2 (untracked turn)
        with open(tp, "a", encoding="utf-8") as f:
            f.write(json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": datetime.fromtimestamp(now_ep - 8).astimezone().isoformat(timespec="seconds"), "model": "gemini-4-hydrogen-high", "input_tokens": 50000, "cache_read_tokens": 0, "output_tokens": 1000}) + "\n")
            f.write(json.dumps({"step_index": 2, "type": "PLANNER_RESPONSE", "created_at": datetime.fromtimestamp(now_ep).astimezone().isoformat(timespec="seconds"), "model": "gemini-4-neon-high", "input_tokens": 20000, "cache_read_tokens": 0, "output_tokens": 500}) + "\n")

        summary, steps = hook_mod.collect_turn_tokens(tp, start_step_index=-1)
        self.assertEqual(summary["billedSteps"], 2)
        self.assertEqual([s["step"] for s in steps], [1, 2])

        # Verify compute_pool_delta handles empty e_reset reset
        rst = hook_mod.compute_pool_delta(
            {"usedPercent": 42.0, "resetsAt": "2026-11-25T00:00:00Z"},
            {"usedPercent": 0.0, "resetsAt": ""},
        )
        self.assertTrue(rst["reset"])
        self.assertEqual(rst["delta"], 0.0)

        # Verify sync_untracked_transcripts adds transcript_only turn and dedups on second run
        old_mtime = time.time() - 180.0
        os.utime(tp, (old_mtime, old_mtime))
        res1 = self.agy_usage.sync_untracked_transcripts(
            ledger_path=self.paths.LEDGER_PATH,
            brain_dir=brain_tmp,
            active_dir=self.paths.ACTIVE_DIR,
            min_age_sec=90.0,
        )
        self.assertEqual(res1["addedTurns"], 1)
        self.assertEqual(res1["addedSteps"], 2)
        rows = self.agy_usage.load_entries(self.paths.LEDGER_PATH)
        self.assertEqual(rows[0]["status"], "transcript_only")
        res2 = self.agy_usage.sync_untracked_transcripts(
            ledger_path=self.paths.LEDGER_PATH,
            brain_dir=brain_tmp,
            active_dir=self.paths.ACTIVE_DIR,
            min_age_sec=90.0,
        )
        self.assertEqual(res2["addedTurns"], 0)

    def test_windows_cp1252_safe_print_backfill(self):
        import io

        buf = io.BytesIO()
        cp1252_stream = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
        old_stdout = sys.stdout
        sys.stdout = cp1252_stream
        try:
            self.agy_usage.run_backfill()
            cp1252_stream.flush()
        finally:
            sys.stdout = old_stdout
        self.assertTrue(len(buf.getvalue()) > 0)

    def test_paths_infer_agy_data_root_prefers_app_dir_with_brain(self):
        app_root = os.path.join(self.tmp.name, "agy_app_root")
        os.makedirs(os.path.join(app_root, "brain"), exist_ok=True)
        sidecar_exec_dir = os.path.join(self.tmp.name, "sidecar_data", "usage_monitor_daemon", "data")
        os.makedirs(sidecar_exec_dir, exist_ok=True)

        with mock.patch.dict(
            os.environ,
            {
                "ANTIGRAVITY_EXECUTABLE_DATA_DIR": sidecar_exec_dir,
                "ANTIGRAVITY_APP_DATA_DIR": app_root,
            },
            clear=False,
        ):
            self.assertEqual(self.paths._infer_agy_data_root(), app_root)

        env_no_app = {
            "ANTIGRAVITY_EXECUTABLE_DATA_DIR": sidecar_exec_dir,
            "ANTIGRAVITY_APP_DATA_DIR": "",
        }
        with mock.patch.dict(os.environ, env_no_app, clear=False):
            inferred = self.paths._infer_agy_data_root()
            self.assertNotEqual(inferred, sidecar_exec_dir)
            self.assertEqual(inferred, os.path.expanduser("~/.gemini/antigravity"))

    def test_dashboard_payload_deduplicates_and_caches_clean_timeline(self):
        self._seed_sample_logs()
        self.dashboard_data._clear_caches()

        with mock.patch.object(
            self.agy_monitor,
            "clean_monitor_timeline",
            wraps=self.agy_monitor.clean_monitor_timeline,
        ) as spy_clean:
            p1 = self.dashboard_data.build_dashboard_payload(window="24h", recent_n=10, live=False)
            self.assertEqual(spy_clean.call_count, 1)
            p2 = self.dashboard_data.build_dashboard_payload(window="24h", recent_n=10, live=False)
            self.assertEqual(spy_clean.call_count, 1)

        self.assertEqual(p1["reconciliation"], p2["reconciliation"])
        self.assertEqual(p1["diagnostics"], p2["diagnostics"])


if __name__ == "__main__":
    unittest.main()
