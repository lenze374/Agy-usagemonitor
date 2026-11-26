# Antigravity Usage Monitor (`usage-monitor`)

English | [简体中文](README.zh-CN.md)

**Zero-dependency, zero-CDP Antigravity Sidecar & Hook plugin** for **shared-pool quota reconciliation**, **1-minute denoised global pool monitoring**, **quiet-window per-model burn rate calibration**, and a **bilingual (`en` / `zh-CN`) Extensions sidebar dashboard**.

Designed specifically for users who share an Antigravity subscription across multiple devices or teammates—or want exact visibility into how server pre-reservation spikes, sleep gaps, and individual models affect their quota.

---

## Key Capabilities

- **Closed-Loop Shared-Pool Reconciliation**: Combines local Hook token telemetry (`PreInvocation` / `Stop` + `transcript.jsonl`, plus automatic background recovery of untracked subagent/interrupted transcripts) with 1-minute Language Server quota polling (`RetrieveUserQuotaSummary`) and post-usage local-token correction (`Rule A/B`) to separate **Mine** from **External (while awake)**, **Concurrent**, and **During sleep**.
- **Multi-Pass Watermark Denoiser**: Eliminates transient server pre-reservation pulses/rollbacks via **Pass 1.5** invariant pairing (`inv = gw - ratio * g5`), **Pass 3** active-aware anchor alignment, stale `resetsAt` replica retirement, and isolated 1–2 tick dip repair without locking artificial high-water marks.
- **Quiet-Window Golden Calibration**: Automatically infers each model's weekly burn rate (`% per 1M Equivalent Input` with `In:Cache:Out = 1:0.05:5`), excludes `search_web` / error steps from Pass 1, solves residual rates from clean mixed-model turns in Pass 2, and tracks per-step `model` usage (including subagents).
- **Multi-Subscription & Multi-Tier Support**:
  - Dynamically renders all quota buckets returned by the host (e.g. `Gemini 5h/Weekly`, `Argon Weekly`, `Claude/GPT 5h/Weekly`, and future buckets).
  - Detects Pay-As-You-Go accounts (`GetUserStatus`) cleanly while keeping local token tracking active.
  - Dynamically calibrates the `5h : Weekly` ratio from observed non-reset samples instead of hardcoding a single subscription tier.
- **Zero-CDP, Zero-Dependency Runtime**: Pure Python `3.9+` standard library. No Electron CDP flags, no launcher patching, no Node/pip install required.

---

## Installation

**Requirements**: Python `3.9+` and Google Antigravity Desktop (`2.32+`, verified on `2.34.0`).

### macOS / Linux

```bash
git clone https://github.com/lenze374/Agy-usagemonitor.git
cd Agy-usagemonitor
chmod +x install.sh uninstall.sh
sh install.sh --with-cli
```

*(Omit `--with-cli` if you only want the Antigravity Extensions sidebar plugin and Hooks without adding `agy-usage` to `~/.local/bin`.)*

### Windows (PowerShell or Double-Click)

```powershell
git clone https://github.com/lenze374/Agy-usagemonitor.git
cd Agy-usagemonitor
.\install.ps1 --with-cli
```

Or double-click `install.bat`.

### Activate in Antigravity

1. Open Antigravity → **Extensions / Plugins**.
2. Enable **`usage-monitor` (`Antigravity Usage Monitor`)**.
3. Open the **UsageMonitor** panel from the Extensions sidebar.

---

## Dashboard Overview

1. **Overview**:
   - **Remaining Quota** hero cards (`XXX.XXX%` 3-decimal precision, adaptive healthy/tight/low/exhausted colors, `-X.XXX%` used).
   - **Weekly Attribution**: Visual breakdown between `Mine`, `External (while awake)`, and `During sleep`.
   - **Recent External Usage** (`24h` / `7d`): Groups idle, sleep, and concurrent external bursts.
   - **My Ledger Summary**: Today vs Current Week comparison.
2. **Trends & Split**:
   - Interactive SVG **Remaining Quota Trend** with idle shading, sleep bridges, cycle resets, and optional raw-noise overlay.
   - Hourly (`Today`/`24h`) or daily (`7d`) stacked attribution chart.
   - Filtered **Deduction Log** (denoised rollbacks excluded).
3. **My Usage**:
   - Calibrated per-model burn rates (`%/1M EqIn`), cache hit rates, and recent 25 conversation groups (collapsing subagent bursts cleanly).
4. **Settings & Diagnostics**:
   - Toggle conversation Hook `ON/OFF`, backfill missing historical tokens/per-step models, choose an optional cold-start rate preset (`Off` / `Ultra 5x` / `Ultra 20x`), copy or download an in-memory `.txt` summary (zero automatic disk report exports), switch `Auto / 简体中文 / English`, and inspect runtime diagnostics.

---

## Cold-Start Model Rate Presets (Ultra 5x / 20x Only)

By default (`none` / Off), UsageMonitor learns every model's burn rate purely from your own clean local turns (`calibrate_weekly_model_rates`). Before you accumulate clean samples for a model family, you can optionally enable a cold-start prior from **Settings & Diag** or via `agy-usage --preset {none,ultra_5x,ultra_20x}`:

| Model Family | Ultra 5x (Weekly % / 1M EqIn) | Ultra 20x (Weekly % / 1M EqIn) | Notes |
| :--- | :--- | :--- | :--- |
| `gemini-4-carbon-*` / `gemini-pro-orchestrator` | `1.0000%` | `0.2500%` | Verified on Ultra 5x (`In:Cache:Out = 1:0.05:5`) |
| `gemini-4-neon-*` | `0.5000%` | `0.1250%` | Verified on Ultra 5x |
| `gemini-4-hydrogen-*` / `gemini-flash-worker-agy` | `0.2500%` | `0.0625%` | Verified on Ultra 5x |
| `gemini-4-argon-*` | Un-seeded (`pending`) | Un-seeded (`pending`) | Excluded intentionally; auto-calibrates on first local clean turn |

- **Pro & Free tiers**: Keep the preset **Off (`none`)** — Google AI Pro and Free accounts use different pool capacities and bucket structures, so Ultra presets do not apply.
- **Automatic override**: As soon as your local ledger collects clean samples for a model (or same-family sibling), locally measured rates automatically override the preset prior.

---

## Privacy & Local Storage

All data stays 100% on your machine. Credentials (`ANTIGRAVITY_CSRF_TOKEN`) are only read from host-injected environment variables in memory and are **never** written to disk or logged.

Runtime files live strictly in the OS user data directory (completely separated from plugin code):
- **macOS / Linux**: `~/.local/share/agy-usage/` (or `$XDG_DATA_HOME/agy-usage/`)
- **Windows**: `%LOCALAPPDATA%\agy-usage\`
- Override via `AGY_USAGE_DATA_DIR`.

---

## Uninstall

```bash
# macOS / Linux (keeps your ledger.jsonl & monitor.jsonl)
sh uninstall.sh

# Windows PowerShell
.\uninstall.ps1
```

Pass `--purge-data` if you also want to remove runtime ledger/monitor logs.

## License

[MIT](LICENSE)
