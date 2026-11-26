---
name: agy-usage
description: Inspect Antigravity shared-pool quota reconciliation, 1-minute denoised global pool telemetry, calibrated per-model weekly burn rates, and local conversation token ledgers. Use when the user asks to check Antigravity quota usage, shared-pool attribution, external/concurrent usage bursts, or model rate calibration.
---

# Antigravity Usage Monitor (`agy-usage`)

Zero-dependency local telemetry & shared-pool accounting plugin for Google Antigravity (`v0.2.0`).

## Where Data Lives

Runtime state is stored strictly outside the workspace and Antigravity plugin config:
- **macOS / Linux**: `~/.local/share/agy-usage/` (or `$XDG_DATA_HOME/agy-usage/`)
  - `ledger.jsonl`: per-turn Hook token + quota snapshot records
  - `monitor.jsonl`: 1-minute global quota snapshots sampled by Sidecar
  - `config.json`: optional user preferences (such as cold-start `ratePreset`: `none`, `ultra_5x`, `ultra_20x`)
  - `sidecar_runtime.json`: live local Sidecar PID & HTTP port
- **Windows**: `%LOCALAPPDATA%\agy-usage\`
- Override via `AGY_USAGE_DATA_DIR`.

## Sidecar Web UI

Open the **UsageMonitor** panel from Antigravity's Extensions / Plugins sidebar (`has_web_ui: true`).
All percentages highlight **Remaining Quota %** (`3` decimals on hero cards), while deductions and spending are formatted as **`-X%`**. Supports English and Simplified Chinese (`zh-CN`).

## CLI Commands (Optional `--with-cli` install or direct Python invocation)

If installed with `--with-cli`, `agy-usage` is on `PATH`; otherwise run `python3 <plugin_dir>/sidecars/usage_monitor_daemon/agy_usage.py`:

- `agy-usage` — Offline summary, closed-loop shared-pool reconciliation (`Mine` vs `External` / `Sleep`), calibrated per-model rates, and recent conversation groups.
- `agy-usage --live` — Query live pools from local Language Server RPC / Sidecar alongside the ledger.
- `agy-usage --models` — Show calibrated model burn rates (`% per 1M Equivalent Input` at `In:Cache:Out = 1:0.05:5`).
- `agy-usage --steps N` — Inspect per-step token counts and model tags for the latest `N` turns.
- `agy-usage --monitor` / `--monitor-changes` — Inspect the 1-minute monitor timeline (`monitor.jsonl`).
- `agy-usage --backfill` — Backfill missing tokens and per-step model metadata from local `transcript.jsonl` files.
- `agy-usage --preset {none,ultra_5x,ultra_20x}` — Set optional cold-start model burn-rate preset (Google AI Ultra 5x/20x only; keep `none` for Pro/Free).
- `agy-usage --on` / `--off` / `--status` — Toggle or inspect conversation-level PreInvocation/Stop hooks and saved preferences.
