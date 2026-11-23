# Changelog

## v0.1.0 (2026-11-23)

Initial public cross-platform release of **Antigravity Usage Monitor** (`usage-monitor`).

### Highlights
- **Closed-loop shared-pool reconciliation**: Separates local machine spend (`Mine`, calibrated from local token usage) from external/groupmate spend (`While idle`, `During sleep`, and `Concurrent` excess), bridging suffix-min clamped plateaus cleanly.
- **2-pass monitor denoiser**: Filters backward `resetsAt` stale-replica flaps, repairs isolated 1–2 tick downward dips, and erases transient server pre-reservation pulses/rollbacks via per-window suffix minimum.
- **Quiet-window golden calibration & Pass-2 mixed-turn solver**: Automatically calibrates per-model burn rates (`% per 1M Equivalent Input` at `In:Cache:Out = 1:0.05:5`), excludes `search_web`/error turns from Pass 1, captures per-step `model` metadata, and provides lossless `--backfill`.
- **Multi-subscription & multi-tier adaptation**: Dynamically renders all returned quota buckets (including `Argon` weekly pools and unknown future buckets), detects `Pay-As-You-Go` accounts via `GetUserStatus`, and dynamically estimates the account's `5h : Weekly` ratio instead of hardcoding a single tier.
- **Bilingual Sidecar Web UI (`zh-CN` / `en`)**: Host-theme adaptive (`--um-*` namespace), remaining-first 3-decimal hero cards (`XXX.XXX%`), `-X%` spending convention, responsive SVG trend & hourly/daily attribution charts, clean deduction log, and Settings & Diagnostics tab with in-memory `.txt` summary export (zero background disk exports).
- **Zero-dependency cross-platform packaging**: Python 3.9+ stdlib only, self-contained installers (`install.sh` / `install.ps1` / `install.bat`), optional CLI (`agy-usage`), Agent skill, and macOS/Linux/Windows CI.
