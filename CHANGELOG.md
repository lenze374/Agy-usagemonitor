# Changelog

## v0.2.0 (2026-11-26)

### Improved & Fixed
- **Multi-Pass Monitor Denoiser (Pass 1.5 & Pass 3)**:
  - Added **Pass 1.5** invariant pre-reservation pairing (`inv = gw - ratio * g5`): pairs exact 1-tick replica bounces, LIFO transient returns (`<= 30m`), LIFO short active closes (`<= 5m`), and FIFO TTL expirations (`<= 6h`) with an idle-teleport guard, restoring real settled spend to its true origin tick while automatically skipping weekly-only accounts.
  - Added **Pass 3** active-aware anchor alignment for weekly pools so clamped local active rises never teleport backward onto a preceding idle spike.
  - Added Pass-1 multi-tick plateau lookahead and empty-`resetsAt` stale-replica retirement (`retired_ep` + 15-minute post-reset bounce guard + clean cycle week-start detection).
- **Post-Usage Local-Token Correction (`Rule A` + `Rule B`)**:
  - **Rule B**: Strips stacked live-tail un-settled Gemini pre-reservations interleaved with `5h`-only offsets using local token floors (`gw_before + local_since`), displaying a transparent pending pre-reservation note in the Overview card and `.txt` summary without overriding adjusted weekly totals.
  - **Rule A**: Re-attributes idle/clamped pre-reservation spikes preceding or overlapping local sessions back to local consumption when completed turns show `localEst > monActive`, enforcing exact conservation (`externalTotal = monIdleOnline + monOffline + externalConcurrent`).
- **Automatic Transcript Recovery & Hook First-Step Fix**:
  - Sidecar background loop (`600s` interval) and `--backfill` now recover untracked settled local turns (`transcript_only`) such as subagent waves, interrupted turns, or Hook-OFF sessions with step-index + time-window deduplication (excluded cleanly from model-rate calibration).
  - Fixed `hook.py` ignoring 0-token placeholder steps before `PreInvocation`, tightened `seen_steps` deduplication, added empty-`resetsAt` mid-turn reset detection, and added optional `fcntl.flock` ledger append locking on POSIX platforms.
- **Cross-Platform CLI & CI Stability**:
  - Added `ensure_utf8_stdio()` and `safe_print()` so Windows narrow consoles (`cp1252`) never fail with `UnicodeEncodeError` when printing Chinese CLI summaries.
  - Updated GitHub Actions matrix (`ubuntu-latest` `3.11`/`3.12`, `macos-latest` & `windows-latest` `3.9`/`3.12`).

## v0.1.1 (2026-11-23)

### Added
- **Optional Cold-Start Model Rate Presets (`none` / `ultra_5x` / `ultra_20x`)**:
  - Defaults to `none` (pure local self-calibration — recommended for Google AI Pro and Free tiers, which have different pool capacities and bucket structures).
  - Pre-seeds verified Ultra 5x priors (`carbon`: `1.0000%`, `neon`: `0.5000%`, `hydrogen`: `0.2500%` Weekly % per 1M Equivalent Input at `In:Cache:Out = 1:0.05:5`) and `÷ 4` scaled Ultra 20x priors (`0.2500%`, `0.1250%`, `0.0625%`) when selected.
  - Leaves `gemini-4-argon-*` intentionally un-seeded so it self-calibrates cleanly from the user's first clean turn.
  - Locally calibrated rates (and same-family calibrated siblings) always override preset priors automatically.
  - Configurable via Extensions Sidecar UI (**Settings & Diag**) and CLI (`agy-usage --preset {none,ultra_5x,ultra_20x}`), persisted in `<DATA_DIR>/config.json`.

## v0.1.0 (2026-11-23)

Initial public cross-platform release of **Antigravity Usage Monitor** (`usage-monitor`).

### Highlights
- **Closed-loop shared-pool reconciliation**: Separates local machine spend (`Mine`, calibrated from local token usage) from external/groupmate spend (`While idle`, `During sleep`, and `Concurrent` excess), bridging suffix-min clamped plateaus cleanly.
- **2-pass monitor denoiser**: Filters backward `resetsAt` stale-replica flaps, repairs isolated 1–2 tick downward dips, and erases transient server pre-reservation pulses/rollbacks via per-window suffix minimum.
- **Quiet-window golden calibration & Pass-2 mixed-turn solver**: Automatically calibrates per-model burn rates (`% per 1M Equivalent Input` at `In:Cache:Out = 1:0.05:5`), excludes `search_web`/error turns from Pass 1, captures per-step `model` metadata, and provides lossless `--backfill`.
- **Multi-subscription & multi-tier adaptation**: Dynamically renders all returned quota buckets (including `Argon` weekly pools and unknown future buckets), detects `Pay-As-You-Go` accounts via `GetUserStatus`, and dynamically estimates the account's `5h : Weekly` ratio instead of hardcoding a single tier.
- **Bilingual Sidecar Web UI (`zh-CN` / `en`)**: Host-theme adaptive (`--um-*` namespace), remaining-first 3-decimal hero cards (`XXX.XXX%`), `-X%` spending convention, responsive SVG trend & hourly/daily attribution charts, clean deduction log, and Settings & Diagnostics tab with in-memory `.txt` summary export (zero background disk exports).
- **Zero-dependency cross-platform packaging**: Python 3.9+ stdlib only, self-contained installers (`install.sh` / `install.ps1` / `install.bat`), optional CLI (`agy-usage`), Agent skill, and macOS/Linux/Windows CI.
