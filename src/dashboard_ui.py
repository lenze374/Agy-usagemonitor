#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-contained bilingual (zh-CN / en) HTML/CSS/JS Web UI for Antigravity Usage Monitor."""

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>UsageMonitor</title>
  <script src="/preload.js"></script>
  <style>
    :root {
      --um-bg: var(--background, #ffffff);
      --um-fg: var(--foreground, #111827);
      --um-fg-2: color-mix(in srgb, var(--foreground, #111827) 84%, var(--background, #ffffff));
      --um-muted: var(--muted-foreground, color-mix(in srgb, var(--foreground, #111827) 66%, var(--background, #ffffff)));
      --um-surface: var(--card, color-mix(in srgb, var(--foreground, #111827) 4%, var(--background, #ffffff)));
      --um-surface-2: color-mix(in srgb, var(--foreground, #111827) 6%, var(--background, #ffffff));
      --um-surface-hover: color-mix(in srgb, var(--foreground, #111827) 11%, var(--background, #ffffff));
      --um-active-bg: var(--background, #ffffff);
      --um-border: var(--border, color-mix(in srgb, var(--foreground, #111827) 14%, transparent));
      --um-border-strong: color-mix(in srgb, var(--foreground, #111827) 24%, transparent);
      --um-glass: var(--card, var(--background, #ffffff));
      --um-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.08);
      --um-shadow-md: 0 6px 20px rgba(0, 0, 0, 0.16);

      --um-local: #1d4ed8;
      --um-ext: #c2410c;
      --um-off: #6d28d9;
      --um-g5: #047857;
      --um-cg: #be185d;
      --um-warn: #b45309;
      --um-danger: #b91c1c;
      --um-ok: #047857;
      --um-idle-band: color-mix(in srgb, var(--foreground, #111827) 7%, transparent);
      --um-sleep-band: color-mix(in srgb, var(--um-off) 11%, transparent);
      --um-grid-line: color-mix(in srgb, var(--foreground, #111827) 16%, transparent);
      --um-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --um-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    }

    html[data-theme="dark"] {
      --um-bg: var(--background, #141414);
      --um-fg: var(--foreground, #ebebeb);
      --um-fg-2: color-mix(in srgb, var(--foreground, #ebebeb) 86%, var(--background, #141414));
      --um-muted: var(--muted-foreground, color-mix(in srgb, var(--foreground, #ebebeb) 68%, var(--background, #141414)));
      --um-surface: var(--card, color-mix(in srgb, var(--foreground, #ebebeb) 5%, var(--background, #141414)));
      --um-surface-2: color-mix(in srgb, var(--foreground, #ebebeb) 8%, var(--background, #141414));
      --um-surface-hover: color-mix(in srgb, var(--foreground, #ebebeb) 13%, var(--background, #141414));
      --um-active-bg: color-mix(in srgb, var(--foreground, #ebebeb) 14%, var(--background, #141414));
      --um-border: var(--border, color-mix(in srgb, var(--foreground, #ebebeb) 14%, transparent));
      --um-border-strong: color-mix(in srgb, var(--foreground, #ebebeb) 26%, transparent);
      --um-glass: var(--card, var(--background, #1c1f26));
      --um-shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.28);
      --um-shadow-md: 0 10px 26px rgba(0, 0, 0, 0.48);

      --um-local: #93c5fd;
      --um-ext: #fdba74;
      --um-off: #d8b4fe;
      --um-g5: #6ee7b7;
      --um-cg: #f9a8d4;
      --um-warn: #fcd34d;
      --um-danger: #fca5a5;
      --um-ok: #6ee7b7;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      padding: 0;
      background: var(--um-bg);
      color: var(--um-fg);
      font-family: var(--um-sans);
      font-size: 12.5px;
      line-height: 1.45;
      font-variant-numeric: tabular-nums;
      -webkit-font-smoothing: antialiased;
    }

    .app-shell {
      padding: 0 14px 22px;
      min-height: 100vh;
      color: var(--um-fg);
    }

    .header-sticky {
      position: sticky;
      top: 0;
      z-index: 20;
      background: var(--um-bg);
      padding: 10px 14px 8px;
      margin: 0 -14px 10px;
      border-bottom: 1px solid var(--um-border);
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 7px;
      min-width: 0;
    }

    .brand-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--um-ok);
      box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.18);
      flex-shrink: 0;
    }
    .brand-dot.offline {
      background: var(--um-muted);
      box-shadow: none;
    }

    .brand-title {
      font-size: 14px;
      font-weight: 700;
      letter-spacing: -0.015em;
    }

    .meta-pill {
      font-size: 10.5px;
      color: var(--um-fg-2);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-family: var(--um-mono);
    }

    .top-actions {
      display: flex;
      align-items: center;
      gap: 5px;
      flex-shrink: 0;
    }

    .seg-tabs {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 3px;
      background: var(--um-surface-2);
      border: 1px solid var(--um-border);
      border-radius: 9px;
      padding: 3px;
    }

    .tab {
      background: transparent;
      border: 1px solid transparent;
      border-radius: 6px;
      color: var(--um-fg-2);
      padding: 5px 3px;
      font-size: 11.5px;
      font-weight: 500;
      cursor: pointer;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      transition: background 0.15s, color 0.15s, box-shadow 0.15s, border-color 0.15s;
    }
    .tab:hover { color: var(--um-fg); background: var(--um-surface-hover); }
    .tab.active {
      background: var(--um-active-bg);
      color: var(--um-fg);
      border-color: var(--um-border-strong);
      font-weight: 700;
      box-shadow: var(--um-shadow-sm);
    }

    .pane { display: none; }
    .pane.active { display: block; }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      background: var(--um-surface);
      color: var(--um-fg);
      border: 1px solid var(--um-border);
      border-radius: 7px;
      padding: 4px 10px;
      font-size: 11.5px;
      font-weight: 500;
      cursor: pointer;
      white-space: nowrap;
      transition: border-color 0.15s, background 0.15s, opacity 0.15s;
    }
    .btn:hover { border-color: var(--um-border-strong); background: var(--um-surface-hover); }
    .btn:disabled { opacity: 0.5; cursor: default; }
    .btn-primary {
      border-color: var(--um-local);
      color: var(--um-local);
      font-weight: 600;
    }
    .btn-icon {
      padding: 4px 7px;
      font-size: 11.5px;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 1px 7px;
      border-radius: 99px;
      font-size: 10.5px;
      font-weight: 600;
      border: 1px solid var(--um-border);
      color: var(--um-fg-2);
      background: var(--um-surface-2);
      white-space: nowrap;
    }
    .pill.ok { color: var(--um-ok); border-color: rgba(4, 120, 87, 0.38); background: rgba(16, 185, 129, 0.14); }
    .pill.warn { color: var(--um-warn); border-color: rgba(180, 83, 9, 0.42); background: rgba(245, 158, 11, 0.15); }
    .pill.danger { color: var(--um-danger); border-color: rgba(185, 28, 28, 0.44); background: rgba(239, 68, 68, 0.15); }
    .pill.local { color: var(--um-local); border-color: rgba(29, 78, 216, 0.38); background: rgba(59, 130, 246, 0.14); }
    .pill.ext { color: var(--um-ext); border-color: rgba(194, 65, 12, 0.42); background: rgba(249, 115, 22, 0.15); }
    .pill.off { color: var(--um-off); border-color: rgba(109, 40, 217, 0.42); background: rgba(139, 92, 246, 0.15); }

    .sec-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin: 14px 0 8px;
      flex-wrap: wrap;
    }
    .sec-head:first-child { margin-top: 2px; }
    .sec-title {
      font-size: 12px;
      font-weight: 700;
      color: var(--um-fg);
      letter-spacing: -0.01em;
    }
    .sec-sub {
      font-size: 11px;
      color: var(--um-muted);
      font-family: var(--um-mono);
    }

    .card {
      background: var(--um-surface);
      border: 1px solid var(--um-border);
      border-radius: 11px;
      padding: 11px 12px;
      box-shadow: var(--um-shadow-sm);
    }

    .grid-2 {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    @media (max-width: 340px) {
      .grid-2 { grid-template-columns: 1fr; }
    }

    .pool-card {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 10px 11px;
    }
    .pool-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 4px;
    }
    .pool-name {
      font-size: 12px;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pool-hero {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: 2px 6px;
    }
    .pool-pct {
      font-family: var(--um-mono);
      font-size: 16.5px;
      font-weight: 700;
      letter-spacing: -0.02em;
      white-space: nowrap;
    }
    .pool-rem {
      font-size: 11px;
      color: var(--um-muted);
      font-family: var(--um-mono);
      white-space: nowrap;
    }
    .dual-bar {
      display: flex;
      width: 100%;
      height: 7px;
      border-radius: 99px;
      background: var(--um-surface-2);
      overflow: hidden;
      border: 1px solid var(--um-border);
    }
    .dual-seg { height: 100%; transition: width 0.3s ease; }
    .pool-foot {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 10.5px;
      color: var(--um-muted);
      gap: 6px;
    }

    .rec-block { margin-bottom: 12px; }
    .rec-block:last-of-type { margin-bottom: 8px; }
    .rec-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
      flex-wrap: wrap;
    }
    .rec-title { font-weight: 600; font-size: 12.5px; }
    .rec-split {
      display: flex;
      align-items: center;
      gap: 5px;
      font-family: var(--um-mono);
      font-size: 11px;
    }
    .rec-bar {
      display: flex;
      height: 11px;
      width: 100%;
      border-radius: 99px;
      background: var(--um-surface-2);
      overflow: hidden;
      border: 1px solid var(--um-border);
      margin-bottom: 6px;
    }
    .rec-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 12px;
      font-size: 11px;
      color: var(--um-muted);
    }
    .chip-item {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-family: var(--um-mono);
    }
    .swatch {
      width: 8px;
      height: 8px;
      border-radius: 2px;
      flex-shrink: 0;
    }
    .rec-note {
      padding-top: 8px;
      border-top: 1px dashed var(--um-border);
      font-size: 11px;
      color: var(--um-muted);
    }

    .burst-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .burst-item {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 6px 10px;
      align-items: center;
      padding: 8px 10px;
      border-radius: 9px;
      background: var(--um-surface);
      border: 1px solid var(--um-border);
    }
    .burst-main {
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-width: 0;
    }
    .burst-time {
      font-family: var(--um-mono);
      font-size: 11.5px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .burst-sub {
      font-size: 10.5px;
      color: var(--um-muted);
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .burst-val {
      text-align: right;
      font-family: var(--um-mono);
      font-size: 11.5px;
      font-weight: 700;
    }

    .table-wrap {
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--um-border);
      border-radius: 10px;
      background: var(--um-surface);
      box-shadow: var(--um-shadow-sm);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11.5px;
    }
    th, td {
      padding: 7px 9px;
      text-align: left;
      border-bottom: 1px solid var(--um-border);
      white-space: nowrap;
    }
    tr:last-child td { border-bottom: none; }
    th {
      font-weight: 600;
      color: var(--um-fg-2);
      font-size: 10.5px;
      background: var(--um-surface-2);
    }
    tbody tr:hover td { background: var(--um-surface-hover); }
    td.num, th.num { text-align: right; font-family: var(--um-mono); }
    tr.row-warn td { background: rgba(245, 158, 11, 0.08); }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .toolbar-lbl {
      font-size: 11px;
      color: var(--um-fg-2);
      margin-right: 4px;
    }
    .seg-mini {
      display: inline-flex;
      gap: 2px;
      background: var(--um-surface-2);
      border: 1px solid var(--um-border);
      border-radius: 7px;
      padding: 2px;
    }
    .seg-mini button {
      background: transparent;
      border: 1px solid transparent;
      border-radius: 5px;
      color: var(--um-fg-2);
      padding: 3px 8px;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
    }
    .seg-mini button:hover {
      color: var(--um-fg);
      background: var(--um-surface-hover);
    }
    .seg-mini button.active {
      background: var(--um-active-bg);
      color: var(--um-fg);
      border-color: var(--um-border-strong);
      font-weight: 700;
      box-shadow: var(--um-shadow-sm);
    }
    .toggle-chk {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      color: var(--um-fg-2);
      cursor: pointer;
      user-select: none;
    }

    .chart-card {
      position: relative;
      padding: 10px 10px 8px;
      margin-bottom: 10px;
    }
    .chart-legend {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 12px;
      font-size: 11px;
      color: var(--um-muted);
      margin-bottom: 6px;
    }
    .leg-item {
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .leg-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .svg-host {
      position: relative;
      width: 100%;
      min-height: 170px;
    }
    .svg-host svg {
      display: block;
      width: 100%;
      height: auto;
      overflow: visible;
    }
    .chart-tooltip {
      position: absolute;
      top: 8px;
      left: 8px;
      z-index: 15;
      pointer-events: none;
      background: var(--um-glass);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      border: 1px solid var(--um-border-strong);
      border-radius: 8px;
      padding: 6px 9px;
      box-shadow: var(--um-shadow-md);
      font-size: 11px;
      line-height: 1.45;
      min-width: 165px;
      max-width: 245px;
      opacity: 0;
      transition: opacity 0.1s ease;
    }
    .chart-tooltip.show { opacity: 1; }
    .tt-time {
      font-family: var(--um-mono);
      font-weight: 700;
      font-size: 11px;
      margin-bottom: 3px;
      display: flex;
      justify-content: space-between;
      gap: 8px;
    }
    .tt-row {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      font-family: var(--um-mono);
      font-size: 10.5px;
    }

    .model-bars {
      display: flex;
      flex-direction: column;
      gap: 7px;
      margin-bottom: 10px;
    }
    .mbar-row {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 8px 10px;
      border-radius: 9px;
      background: var(--um-surface);
      border: 1px solid var(--um-border);
    }
    .mbar-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      font-size: 11.5px;
    }
    .mbar-name {
      font-weight: 600;
      font-family: var(--um-mono);
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .mbar-track {
      height: 6px;
      width: 100%;
      border-radius: 99px;
      background: var(--um-surface-2);
      overflow: hidden;
    }
    .mbar-fill {
      height: 100%;
      border-radius: 99px;
      background: linear-gradient(90deg, var(--um-local), var(--um-g5));
    }
    .mbar-sub {
      display: flex;
      justify-content: space-between;
      font-size: 10.5px;
      color: var(--um-muted);
      font-family: var(--um-mono);
      flex-wrap: wrap;
      gap: 4px;
    }

    .ops-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 7px;
      margin-bottom: 8px;
    }
    .toast {
      font-size: 11.5px;
      color: var(--um-local);
      min-height: 18px;
      margin-bottom: 8px;
      font-family: var(--um-mono);
    }
    .diag-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 10px;
      padding: 5px 0;
      border-bottom: 1px solid var(--um-border);
      font-size: 11.5px;
    }
    .diag-row:last-child { border-bottom: none; }
    .diag-k { color: var(--um-muted); flex-shrink: 0; }
    .diag-v {
      font-family: var(--um-mono);
      text-align: right;
      word-break: break-all;
      color: var(--um-fg);
    }
    select {
      background: var(--um-surface);
      color: var(--um-fg);
      border: 1px solid var(--um-border);
      border-radius: 7px;
      padding: 4px 9px;
      font-size: 12px;
      font-family: var(--um-mono);
    }
    pre.daily-pre {
      margin: 8px 0 0;
      padding: 10px;
      background: var(--um-surface);
      border: 1px solid var(--um-border);
      border-radius: 10px;
      font-family: var(--um-mono);
      font-size: 11px;
      line-height: 1.5;
      overflow-x: auto;
      max-height: 280px;
      white-space: pre;
    }
    .empty {
      color: var(--um-muted);
      padding: 14px 10px;
      text-align: center;
      font-size: 11.5px;
    }
  </style>
</head>
<body>
  <div class="app-shell">
  <div class="header-sticky">
    <div class="topbar">
      <div class="brand">
        <span id="liveDot" class="brand-dot offline"></span>
        <span class="brand-title">UsageMonitor</span>
        <span id="liveSourceTag" class="meta-pill" title="-">-</span>
      </div>
      <div class="top-actions">
        <span id="hookBadge" class="pill">-</span>
        <button id="langToggleBtn" class="btn btn-icon" title="Switch language">中/EN</button>
        <button id="refreshBtn" class="btn btn-icon" title="Refresh">↻</button>
      </div>
    </div>
    <div class="seg-tabs">
      <button class="tab active" data-tab="overview" id="tabOverview">总览</button>
      <button class="tab" data-tab="monitor" id="tabMonitor">趋势与分账</button>
      <button class="tab" data-tab="ledger" id="tabLedger">我的用量</button>
      <button class="tab" data-tab="settings" id="tabSettings">设置与诊断</button>
    </div>
  </div>

  <!-- TAB 1: OVERVIEW -->
  <div id="pane-overview" class="pane active">
    <div class="sec-head">
      <span class="sec-title" id="secRemTitle">当前剩余额度</span>
      <span id="metaLine" class="sec-sub">-</span>
    </div>
    <div id="poolsGrid" class="grid-2"></div>

    <div class="sec-head">
      <span class="sec-title" id="secWhoTitle">这周谁用了多少？</span>
      <span id="weekSinceTag" class="sec-sub"></span>
    </div>
    <div id="reconcileCard" class="card"></div>

    <div class="sec-head">
      <span class="sec-title" id="secExtTitle">最近别人啥时候在用</span>
      <div class="seg-mini" id="overviewBurstGroup">
        <button class="active" data-obw="24h" id="btnObw24h">近24小时</button>
        <button data-obw="7d" id="btnObw7d">近7天</button>
      </div>
    </div>
    <div id="burstsFeed" class="burst-list"></div>

    <div class="sec-head">
      <span class="sec-title" id="secBillTitle">我的简明账单 (Gemini 周额度)</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th id="thPeriod">时间</th>
            <th class="num" id="thTurnsSteps">对话/步数</th>
            <th class="num" id="thTokens">Token</th>
            <th class="num" id="thMine">我用的</th>
            <th class="num" id="thOther">别人用的</th>
            <th class="num" id="thPoolTot">账号共用</th>
          </tr>
        </thead>
        <tbody id="periodBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 2: MONITOR CHARTS & EVENTS -->
  <div id="pane-monitor" class="pane">
    <div class="toolbar">
      <div style="display:flex;align-items:center;gap:4px;">
        <span class="toolbar-lbl" id="lblWin">看最近:</span>
        <div class="seg-mini" id="winGroup">
          <button data-win="today" id="btnWinToday">今天</button>
          <button class="active" data-win="24h" id="btnWin24h">近24小时</button>
          <button data-win="7d" id="btnWin7d">近7天</button>
        </div>
      </div>
      <div class="seg-mini" id="poolGroup">
        <button class="active" data-pool="gemini" id="btnPoolGem">Gemini</button>
        <button data-pool="cg" id="btnPoolCg">Claude/GPT</button>
        <button data-pool="both" id="btnPoolBoth">全部</button>
      </div>
      <label class="toggle-chk" id="lblRawNoise">
        <input type="checkbox" id="chkRawNoise" />
        <span id="txtRawNoise">对比原始数据</span>
      </label>
    </div>

    <div class="card chart-card">
      <div class="sec-head" style="margin:0 0 6px;">
        <span class="sec-title" id="chartLineTitle">额度剩余走势</span>
        <span id="chgMeta" class="sec-sub">-</span>
      </div>
      <div class="chart-legend" id="lineLegend"></div>
      <div class="svg-host" id="lineChartHost">
        <div id="lineTooltip" class="chart-tooltip"></div>
      </div>
    </div>

    <div class="card chart-card">
      <div class="sec-head" style="margin:0 0 6px;">
        <span class="sec-title" id="barTitle">每小时谁用了多少</span>
        <div class="seg-mini" id="barPoolGroup">
          <button class="active" data-bpool="gw" id="btnBarGw">Gemini 这周</button>
          <button data-bpool="cw" id="btnBarCw">Claude/GPT 这周</button>
        </div>
      </div>
      <div class="chart-legend">
        <span class="leg-item"><i class="leg-dot" style="background:var(--um-local)"></i><span id="legMine">我用的</span></span>
        <span class="leg-item"><i class="leg-dot" style="background:var(--um-ext)"></i><span id="legExt">别人用的</span></span>
        <span class="leg-item"><i class="leg-dot" style="background:var(--um-off)"></i><span id="legSleep">电脑休眠期间</span></span>
      </div>
      <div class="svg-host" id="barChartHost">
        <div id="barTooltip" class="chart-tooltip"></div>
      </div>
    </div>

    <div class="sec-head">
      <span class="sec-title" id="secChangesTitle">每次扣额记录</span>
      <div class="seg-mini" id="chgFilterGroup">
        <button class="active" data-cfilter="all" id="btnChgAll">全部</button>
        <button data-cfilter="ext" id="btnChgExt">仅他人消耗</button>
        <button data-cfilter="reset" id="btnChgReset">重置</button>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th id="thChgTime">时间</th>
            <th class="num" id="thChgG5">Gem 5h 剩</th>
            <th class="num" id="thChgGw">Gem 这周 剩</th>
            <th class="num" id="thChgCw">C/G 这周 剩</th>
            <th id="thChgTag">当时情况</th>
          </tr>
        </thead>
        <tbody id="changesBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 3: LEDGER & MODELS -->
  <div id="pane-ledger" class="pane">
    <div class="sec-head">
      <span class="sec-title" id="secModelsTitle">我最常用哪些模型</span>
      <span class="sec-sub">In:Cache:Out = 1:0.05:5</span>
    </div>
    <div id="modelBars" class="model-bars"></div>

    <div class="sec-head">
      <span class="sec-title" id="secRecentTurnsTitle">我最近的对话记录 (最近 25 组)</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th id="thRecTime">时间</th>
            <th id="thRecWs">项目</th>
            <th id="thRecModel">模型</th>
            <th class="num" id="thRecSteps">步数</th>
            <th class="num" id="thRecMine">我用的</th>
            <th class="num" id="thRecObs">接口测得</th>
            <th id="thRecNote">说明</th>
          </tr>
        </thead>
        <tbody id="recentBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 4: SETTINGS & DIAGNOSTICS -->
  <div id="pane-settings" class="pane">
    <div class="sec-head">
      <span class="sec-title" id="secControlsTitle">控制与操作</span>
      <select id="langSelect">
        <option value="auto">Auto (System)</option>
        <option value="zh-CN">简体中文</option>
        <option value="en">English</option>
      </select>
    </div>
    <div class="ops-grid">
      <button class="btn" id="btnToggleHook">开/关自动记账</button>
      <button class="btn" id="btnBackfill">补录缺失 Token</button>
      <button class="btn btn-primary" id="btnCopySummary">复制文本摘要</button>
      <button class="btn" id="btnDownloadSummary">下载 .txt 摘要</button>
    </div>
    <div id="opsToast" class="toast"></div>

    <div class="sec-head">
      <span class="sec-title" id="secDiagTitle">运行诊断</span>
    </div>
    <div id="diagCard" class="card"></div>

    <pre id="summaryPreview" class="daily-pre" style="display:none;"></pre>
  </div>
  </div>

  <script>
    const params = new URLSearchParams(window.location.search);
    const uiToken = params.get('token') || '';
    let activeTab = 'overview';
    let currentWindow = '24h';
    let overviewBurstWindow = '24h';
    let linePoolMode = 'gemini';
    let barPoolMode = 'gw';
    let chgFilter = 'all';
    let showRawNoise = false;
    let latestData = null;
    let bootUiVersion = '';
    let langPref = localStorage.getItem('um_lang') || 'auto';

    const I18N = {
      'zh-CN': {
        tabOverview: '总览',
        tabMonitor: '趋势与分账',
        tabLedger: '我的用量',
        tabSettings: '设置与诊断',
        liveOnline: '实时已连',
        liveOffline: '离线',
        liveOfflineTip: '本地接口离线',
        hookOn: '自动记账 开',
        hookOff: '自动记账 关',
        refreshTip: '立即刷新',
        secRem: '当前剩余额度',
        secWho: '这周谁用了多少？',
        secExt: '最近别人啥时候在用',
        secBill: '我的简明账单 (Gemini 周额度)',
        winToday: '今天',
        win24h: '近24小时',
        win7d: '近7天',
        allPools: '全部',
        thPeriod: '时间',
        thTurnsSteps: '对话/步数',
        thMine: '我用的',
        thOther: '别人用的',
        thPoolTot: '账号共用',
        rowToday: '今天',
        rowWeek: '这周',
        healthy: '充裕',
        tight: '偏紧',
        low: '告急',
        exhausted: '已用完',
        disabled: '已停用',
        usedWord: '已用',
        resetWord: '重置',
        remWord: '剩',
        totUsedWord: '共耗',
        rolling5h: '5小时滚动额度',
        weeklyPool: '周额度池',
        poolSplitHint: (l, e) => `我 ${l} · 别人 ${e}`,
        noLivePools: '暂无实时额度数据',
        paygoNotice: '当前账号为按量付费模式 (Pay-As-You-Go)，无周期性共享额度池；「我的用量」中的本地 Token 记账仍正常工作。',
        weekSince: s => `本周期自 ${s} 起`,
        myShare: p => `我占 ${p}%`,
        extShare: p => `别人占 ${p}%`,
        chipMine: '我用的',
        chipExtOn: '别人用的(电脑开着时)',
        chipExtOff: '电脑休眠期间',
        recNote: '按你电脑的 Token 记录算「我用的」，其余扣额计入「别人用的 / 休眠期间」。',
        gemWeekTitle: 'Gemini 这周',
        cgWeekTitle: 'Claude/GPT 这周',
        pillIdle: '我没用电脑时',
        pillSleep: '电脑休眠期间',
        pillConc: '与你同时用',
        pillMixedConc: '含与你同时用',
        pillDual: '双池',
        durApprox: d => `持续约 ${d}`,
        sub5hPool: s => `5小时池 ${s}`,
        subConc: s => `含并发 ${s}`,
        weeklyUnit: '周额度',
        fiveHUnit: '5小时',
        noExtBursts: '这段时间没人偷偷用你的额度',
        lookRecent: '看最近:',
        compareRaw: '对比原始数据',
        compareRawTip: '叠加官方未过滤跳变的原始曲线',
        lineTitle: '额度剩余走势',
        filteredNoise: n => `已自动过滤 ${n} 次系统误报跳变`,
        noLineData: '这段时间记录太少，暂时画不出曲线',
        noBarData: '这段时间暂无数据',
        barDayGem: '每天谁用了多少 (Gemini)',
        barDayCg: '每天谁用了多少 (Claude/GPT)',
        barHourGem: '每小时谁用了多少 (Gemini)',
        barHourCg: '每小时谁用了多少 (Claude/GPT)',
        chartSleep: '休眠',
        stSleepWake: '休眠刚醒',
        stIdle: '我没用电脑',
        stActive: '你正在用',
        barTotal: v => `共 ${v}`,
        secChanges: '每次扣额记录',
        filterExt: '仅他人消耗',
        filterReset: '重置',
        thChgTime: '时间',
        thChgG5: 'Gem 5h 剩',
        thChgGw: 'Gem 这周 剩',
        thChgCw: 'C/G 这周 剩',
        thChgTag: '当时情况',
        noChanges: '当前筛选下没有扣额记录',
        secModels: '我最常用哪些模型',
        pendingCal: '待采集',
        estSibling: '* 参考同系',
        modelSub: (t, s, hit) => `${t} 次对话 / ${s} 步 · 缓存命中 ${hit}%`,
        ratePer1M: r => `每1M耗额 ${r}`,
        noModels: '暂无模型用量记录',
        secRecent: '我最近的对话记录 (最近 25 组)',
        thRecTime: '时间',
        thRecWs: '项目',
        thRecModel: '模型',
        thRecSteps: '步数',
        thRecObs: '接口测得',
        thRecNote: '说明',
        contamPill: '撞车偏高',
        contamTip: '你发消息时刚好有别人在用或系统抖动，请以「我用的」为准',
        normalPill: '正常',
        noTurns: '暂无对话记录',
        secControls: '控制与操作',
        btnToggleHook: '开/关自动记账',
        btnBackfill: '补录缺失 Token',
        btnCopySummary: '复制文本摘要',
        btnDownloadSummary: '下载 .txt 摘要',
        secDiag: '运行诊断',
        running: '执行中...',
        done: '已完成',
        opFailed: m => `操作失败: ${m}`,
        copiedSummary: '已复制当前摘要到剪贴板',
        copyFailed: '复制失败',
        downloadedSummary: f => `已下载 ${f}`,
        diagVer: '插件版本',
        diagBill: '计费模式',
        diagRatioGem: 'Gemini 5h:周 比例',
        diagRatioCg: 'C/G 5h:周 比例',
        diagCal: (r, n, ok) => ok ? `${r}:1 (已校准 n=${n})` : `${r}:1 (默认兜底 n=${n})`,
        diagPools: '识别到的额度池',
        diagCounts: '本地账本 / 监控采样',
        diagDir: '数据存储目录',
        diagEnv: '运行环境',
        updatedAt: t => `更新于 ${t}`,
        refreshFail: m => `刷新失败: ${m}`,
        tagReset: '额度重置',
        tagSleep: d => `休眠期间(${d})`,
        tagExtIdle: d => `别人用了(闲置${d})`,
        tagExt: '别人用了',
        tagActive: '你正在用',
        tagJustNow: s => `你刚用完(${s}秒前)`,
      },
      'en': {
        tabOverview: 'Overview',
        tabMonitor: 'Trends & Split',
        tabLedger: 'My Usage',
        tabSettings: 'Settings & Diag',
        liveOnline: 'Live',
        liveOffline: 'Offline',
        liveOfflineTip: 'Local LS bridge offline',
        hookOn: 'Hook ON',
        hookOff: 'Hook OFF',
        refreshTip: 'Refresh now',
        secRem: 'Remaining Quota',
        secWho: 'Weekly Attribution',
        secExt: 'Recent External Usage',
        secBill: 'My Ledger Summary (Gemini Weekly)',
        winToday: 'Today',
        win24h: '24h',
        win7d: '7d',
        allPools: 'All',
        thPeriod: 'Period',
        thTurnsSteps: 'Turns/Steps',
        thMine: 'Mine',
        thOther: 'External',
        thPoolTot: 'Pool Total',
        rowToday: 'Today',
        rowWeek: 'This Week',
        healthy: 'Healthy',
        tight: 'Tight',
        low: 'Low',
        exhausted: 'Exhausted',
        disabled: 'Disabled',
        usedWord: 'Used',
        resetWord: 'resets',
        remWord: 'Left',
        totUsedWord: 'Total',
        rolling5h: '5h rolling quota',
        weeklyPool: 'Weekly quota pool',
        poolSplitHint: (l, e) => `Mine ${l} · Ext ${e}`,
        noLivePools: 'No live quota pools available',
        paygoNotice: 'Account uses Pay-As-You-Go billing with no periodic quota pools. Local token tracking in "My Usage" remains active.',
        weekSince: s => `Cycle since ${s}`,
        myShare: p => `Mine ${p}%`,
        extShare: p => `Ext ${p}%`,
        chipMine: 'Mine',
        chipExtOn: 'External (while awake)',
        chipExtOff: 'During sleep',
        recNote: '"Mine" is derived from local token usage; remaining pool deductions count as external / sleep.',
        gemWeekTitle: 'Gemini Weekly',
        cgWeekTitle: 'Claude/GPT Weekly',
        pillIdle: 'While idle',
        pillSleep: 'During sleep',
        pillConc: 'Concurrent',
        pillMixedConc: 'Incl. concurrent',
        pillDual: 'Both pools',
        durApprox: d => `~${d}`,
        sub5hPool: s => `5h pool ${s}`,
        subConc: s => `concurrent ${s}`,
        weeklyUnit: 'Weekly',
        fiveHUnit: '5h',
        noExtBursts: 'No external pool consumption detected in this window',
        lookRecent: 'Range:',
        compareRaw: 'Raw overlay',
        compareRawTip: 'Overlay unfiltered raw quota series with server noise spikes',
        lineTitle: 'Remaining Quota Trend',
        filteredNoise: n => `Filtered ${n} server rollback/spike noise ticks`,
        noLineData: 'Not enough monitor samples to plot trend yet',
        noBarData: 'No bucket data in this range',
        barDayGem: 'Daily Split (Gemini)',
        barDayCg: 'Daily Split (Claude/GPT)',
        barHourGem: 'Hourly Split (Gemini)',
        barHourCg: 'Hourly Split (Claude/GPT)',
        chartSleep: 'Sleep',
        stSleepWake: 'Wake after sleep',
        stIdle: 'Idle',
        stActive: 'Active',
        barTotal: v => `Total ${v}`,
        secChanges: 'Deduction Log',
        filterExt: 'External only',
        filterReset: 'Resets',
        thChgTime: 'Time',
        thChgG5: 'Gem 5h Left',
        thChgGw: 'Gem Wk Left',
        thChgCw: 'C/G Wk Left',
        thChgTag: 'Context',
        noChanges: 'No matching deduction events',
        secModels: 'Calibrated Model Usage',
        pendingCal: 'pending',
        estSibling: '* family fallback',
        modelSub: (t, s, hit) => `${t} turns / ${s} steps · Cache hit ${hit}%`,
        ratePer1M: r => `${r} / 1M EqIn`,
        noModels: 'No model usage recorded yet',
        secRecent: 'Recent Conversations (Last 25)',
        thRecTime: 'Time',
        thRecWs: 'Workspace',
        thRecModel: 'Model',
        thRecSteps: 'Steps',
        thRecObs: 'Measured',
        thRecNote: 'Status',
        contamPill: 'Concurrent/Spike',
        contamTip: 'Measured delta exceeded local theoretical spend (concurrent user or spike)',
        normalPill: 'OK',
        noTurns: 'No conversations recorded yet',
        secControls: 'Controls & Actions',
        btnToggleHook: 'Toggle Hook',
        btnBackfill: 'Backfill Tokens',
        btnCopySummary: 'Copy Text Summary',
        btnDownloadSummary: 'Download .txt Summary',
        secDiag: 'Diagnostics',
        running: 'Running...',
        done: 'Done',
        opFailed: m => `Action failed: ${m}`,
        copiedSummary: 'Summary copied to clipboard',
        copyFailed: 'Copy failed',
        downloadedSummary: f => `Downloaded ${f}`,
        diagVer: 'Plugin Version',
        diagBill: 'Billing Mode',
        diagRatioGem: 'Gemini 5h:Weekly Ratio',
        diagRatioCg: 'C/G 5h:Weekly Ratio',
        diagCal: (r, n, ok) => ok ? `${r}:1 (calibrated n=${n})` : `${r}:1 (default n=${n})`,
        diagPools: 'Detected Pools',
        diagCounts: 'Ledger / Monitor Rows',
        diagDir: 'Runtime Data Dir',
        diagEnv: 'Platform / Python',
        updatedAt: t => `Updated ${t}`,
        refreshFail: m => `Refresh failed: ${m}`,
        tagReset: 'Quota Reset',
        tagSleep: d => `Sleep (${d})`,
        tagExtIdle: d => `External (idle ${d})`,
        tagExt: 'External',
        tagActive: 'Active',
        tagJustNow: s => `Recent (${s}s ago)`,
      },
    };

    function effLang() {
      if (langPref === 'en' || langPref === 'zh-CN') return langPref;
      return String(navigator.language || '').toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
    }
    function T() {
      return I18N[effLang()] || I18N['en'];
    }

    function applyStaticI18n() {
      const t = T();
      document.documentElement.lang = effLang();
      document.getElementById('tabOverview').textContent = t.tabOverview;
      document.getElementById('tabMonitor').textContent = t.tabMonitor;
      document.getElementById('tabLedger').textContent = t.tabLedger;
      document.getElementById('tabSettings').textContent = t.tabSettings;
      document.getElementById('refreshBtn').title = t.refreshTip;
      document.getElementById('langToggleBtn').textContent = effLang() === 'zh-CN' ? 'EN' : '中文';
      document.getElementById('langSelect').value = langPref;

      document.getElementById('secRemTitle').textContent = t.secRem;
      document.getElementById('secWhoTitle').textContent = t.secWho;
      document.getElementById('secExtTitle').textContent = t.secExt;
      document.getElementById('secBillTitle').textContent = t.secBill;
      document.getElementById('btnObw24h').textContent = t.win24h;
      document.getElementById('btnObw7d').textContent = t.win7d;
      document.getElementById('thPeriod').textContent = t.thPeriod;
      document.getElementById('thTurnsSteps').textContent = t.thTurnsSteps;
      document.getElementById('thMine').textContent = t.thMine;
      document.getElementById('thOther').textContent = t.thOther;
      document.getElementById('thPoolTot').textContent = t.thPoolTot;

      document.getElementById('lblWin').textContent = t.lookRecent;
      document.getElementById('btnWinToday').textContent = t.winToday;
      document.getElementById('btnWin24h').textContent = t.win24h;
      document.getElementById('btnWin7d').textContent = t.win7d;
      document.getElementById('btnPoolBoth').textContent = t.allPools;
      document.getElementById('lblRawNoise').title = t.compareRawTip;
      document.getElementById('txtRawNoise').textContent = t.compareRaw;
      document.getElementById('chartLineTitle').textContent = t.lineTitle;
      document.getElementById('btnBarGw').textContent = t.gemWeekTitle;
      document.getElementById('btnBarCw').textContent = t.cgWeekTitle;
      document.getElementById('legMine').textContent = t.chipMine;
      document.getElementById('legExt').textContent = t.pillConc === 'Concurrent' ? 'External' : '别人用的';
      document.getElementById('legSleep').textContent = t.chipExtOff;
      document.getElementById('secChangesTitle').textContent = t.secChanges;
      document.getElementById('btnChgAll').textContent = t.allPools;
      document.getElementById('btnChgExt').textContent = t.filterExt;
      document.getElementById('btnChgReset').textContent = t.filterReset;
      document.getElementById('thChgTime').textContent = t.thChgTime;
      document.getElementById('thChgG5').textContent = t.thChgG5;
      document.getElementById('thChgGw').textContent = t.thChgGw;
      document.getElementById('thChgCw').textContent = t.thChgCw;
      document.getElementById('thChgTag').textContent = t.thChgTag;

      document.getElementById('secModelsTitle').textContent = t.secModels;
      document.getElementById('secRecentTurnsTitle').textContent = t.secRecent;
      document.getElementById('thRecTime').textContent = t.thRecTime;
      document.getElementById('thRecWs').textContent = t.thRecWs;
      document.getElementById('thRecModel').textContent = t.thRecModel;
      document.getElementById('thRecSteps').textContent = t.thRecSteps;
      document.getElementById('thRecMine').textContent = t.thMine;
      document.getElementById('thRecObs').textContent = t.thRecObs;
      document.getElementById('thRecNote').textContent = t.thRecNote;

      document.getElementById('secControlsTitle').textContent = t.secControls;
      document.getElementById('btnToggleHook').textContent = t.btnToggleHook;
      document.getElementById('btnBackfill').textContent = t.btnBackfill;
      document.getElementById('btnCopySummary').textContent = t.btnCopySummary;
      document.getElementById('btnDownloadSummary').textContent = t.btnDownloadSummary;
      document.getElementById('secDiagTitle').textContent = t.secDiag;
    }

    const _themeCanvas = document.createElement('canvas');
    _themeCanvas.width = 1;
    _themeCanvas.height = 1;
    const _themeCtx = _themeCanvas.getContext('2d');

    function _colorToRgba(str) {
      if (!str) return null;
      const raw = String(str).trim();
      if (!raw || raw === 'transparent' || raw === 'none') return { r: 0, g: 0, b: 0, a: 0 };
      if (_themeCtx) {
        try {
          _themeCtx.clearRect(0, 0, 1, 1);
          _themeCtx.fillStyle = '#010203';
          _themeCtx.fillStyle = raw;
          _themeCtx.fillRect(0, 0, 1, 1);
          const d = _themeCtx.getImageData(0, 0, 1, 1).data;
          return { r: d[0], g: d[1], b: d[2], a: d[3] / 255 };
        } catch (_e) {
          // fallback below
        }
      }
      const m = raw.match(/rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+))?/i);
      if (m) {
        return { r: Number(m[1]), g: Number(m[2]), b: Number(m[3]), a: m[4] !== undefined ? Number(m[4]) : 1 };
      }
      return null;
    }

    function syncThemeFromHost() {
      let isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      const rootStyle = getComputedStyle(document.documentElement);
      const bodyStyle = document.body ? getComputedStyle(document.body) : null;
      const hostBgVar = rootStyle.getPropertyValue('--background').trim();
      const hostFgVar = rootStyle.getPropertyValue('--foreground').trim();
      const bg = _colorToRgba(hostBgVar || (bodyStyle && bodyStyle.backgroundColor));
      const fg = _colorToRgba(hostFgVar || (bodyStyle && bodyStyle.color));
      if (bg && bg.a > 0.1) {
        const bgLum = (0.299 * bg.r + 0.587 * bg.g + 0.114 * bg.b) / 255;
        isDark = bgLum < 0.5;
      } else if (fg && fg.a > 0.1) {
        const fgLum = (0.299 * fg.r + 0.587 * fg.g + 0.114 * fg.b) / 255;
        isDark = fgLum > 0.5;
      }
      document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    }
    syncThemeFromHost();
    document.addEventListener('DOMContentLoaded', syncThemeFromHost);
    setTimeout(syncThemeFromHost, 50);
    setTimeout(syncThemeFromHost, 250);
    window.addEventListener('message', ev => {
      if (ev.data && ev.data.type === 'theme-change') setTimeout(syncThemeFromHost, 20);
    });
    if (typeof MutationObserver !== 'undefined') {
      new MutationObserver(syncThemeFromHost).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['style', 'class'],
      });
    }
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', syncThemeFromHost);
    }

    function esc(s) {
      return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function fmtTok(n) {
      n = Number(n || 0);
      if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
      if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
      return String(Math.round(n));
    }
    function fmtSpend(v, digits = 2, suffix = '') {
      if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
      const n = Number(v);
      if (Math.abs(n) <= 1e-5) return (0).toFixed(digits) + '%' + suffix;
      return `-${Math.abs(n).toFixed(digits)}%${suffix}`;
    }
    function fmtNegDelta(v) {
      const n = Number(v || 0);
      const abs = Math.abs(n);
      if (abs < 0.0005) return '';
      const digits = abs < 0.01 ? 3 : 2;
      return n > 0 ? ` (-${abs.toFixed(digits)}%)` : ` (+${abs.toFixed(digits)}%)`;
    }
    function fmtSpendStr(str) {
      const s = String(str ?? '').trim();
      if (!s || !s.includes('%')) return s || '-';
      const m = s.match(/^([+-]?[\d.]+)%(.*)$/);
      if (!m) return s;
      const n = Number(m[1]);
      if (Number.isNaN(n) || Math.abs(n) <= 1e-5) return s;
      return `-${Math.abs(n).toFixed(4)}%${m[2]}`;
    }
    function fmtDuration(mins) {
      mins = Number(mins || 0);
      if (mins >= 60) {
        const h = Math.floor(mins / 60);
        const m = mins % 60;
        return m > 0 ? `${h}h${m}m` : `${h}h`;
      }
      return `${mins}m`;
    }
    function fmtGapSec(sec) {
      const mins = Math.max(1, Math.round(Number(sec || 0) / 60));
      return fmtDuration(mins);
    }

    function localizePoolLabel(key, rawLabel) {
      const isZh = effLang() === 'zh-CN';
      const zhMap = {
        gemini_5h: 'Gemini 5小时',
        gemini_weekly: 'Gemini 这周',
        gemini_argon_5h: 'Argon 5小时',
        gemini_argon_weekly: 'Argon 这周',
        claude_gpt_5h: 'Claude/GPT 5小时',
        claude_gpt_weekly: 'Claude/GPT 这周',
      };
      const enMap = {
        gemini_5h: 'Gemini 5h',
        gemini_weekly: 'Gemini Weekly',
        gemini_argon_5h: 'Argon 5h',
        gemini_argon_weekly: 'Argon Weekly',
        claude_gpt_5h: 'Claude/GPT 5h',
        claude_gpt_weekly: 'Claude/GPT Weekly',
      };
      return (isZh ? zhMap[key] : enMap[key]) || rawLabel || key;
    }

    function localizeChangeTag(r) {
      const t = T();
      if (r.kind === 'offline') return t.tagSleep(fmtGapSec(r.gapSec));
      if (r.kind === 'reset') return t.tagReset;
      if (r.kind === 'idle') {
        return r.idleSec !== null && r.idleSec !== undefined
          ? t.tagExtIdle(fmtGapSec(r.idleSec))
          : t.tagExt;
      }
      const act = Number(r.localActive || 0);
      if (act > 0 || (r.idleSec !== null && r.idleSec !== undefined && Number(r.idleSec) <= 65)) {
        return t.tagActive;
      }
      if (r.idleSec !== null && r.idleSec !== undefined) {
        return t.tagJustNow(Math.round(Number(r.idleSec)));
      }
      return t.tagActive;
    }

    function localizeTurnStatus(st) {
      if (effLang() === 'zh-CN') return st;
      return String(st || 'OK')
        .replace('正常', 'OK')
        .replace('跨休眠剔除', 'Sleep skipped')
        .replace('假重置已剔除', 'Rollback skipped')
        .replace('跨周重置', 'Cycle reset')
        .replace('并发重叠', 'Overlapping')
        .replace('含并发/脉冲', 'Concurrent/Spike')
        .replace('含压缩', 'Compacted')
        .replace(/含Pro规划\((\d+)步\)/g, 'Pro plan ($1 steps)')
        .replace(/混合\((\d+)模型\)/g, 'Mixed ($1 models)')
        .replace(/子代理波次\((\d+)\)/g, 'Subagent wave ($1)');
    }

    async function postApi(path, body = {}) {
      const headers = { 'Content-Type': 'application/json' };
      if (uiToken) headers['x-sidecar-token'] = uiToken;
      const res = await fetch(path, { method: 'POST', headers, body: JSON.stringify(body) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    }

    function renderBurstsFeed(d) {
      const t = T();
      const m = d.monitor || {};
      const bursts = overviewBurstWindow === '7d'
        ? (m.externalBursts7d || m.externalBursts || [])
        : (m.externalBursts24h || m.externalBursts || []);
      document.getElementById('burstsFeed').innerHTML = bursts.length ? bursts.slice(0, 6).map(b => {
        const isOff = b.kind === 'offline';
        let kindPill = `<span class="pill ext">${esc(t.pillIdle)}</span>`;
        if (isOff) {
          kindPill = `<span class="pill off">${esc(t.pillSleep)}</span>`;
        } else if (b.hasConcurrent && !b.hasIdleOnline) {
          kindPill = `<span class="pill warn">${esc(t.pillConc)}</span>`;
        } else if (b.hasConcurrent && b.hasIdleOnline) {
          kindPill = `<span class="pill ext">${esc(t.pillMixedConc)}</span>`;
        }
        const poolPill = b.pool === 'claude_gpt'
          ? '<span class="pill warn">Claude/GPT</span>'
          : (b.pool === 'both' ? `<span class="pill danger">${esc(t.pillDual)}</span>` : '<span class="pill local">Gemini</span>');
        const valParts = [];
        if (b.gwDelta > 0) valParts.push(`-${b.gwDelta.toFixed(2)}% (${t.weeklyUnit})`);
        else if (b.g5Delta > 0) valParts.push(`-${b.g5Delta.toFixed(2)}% (${t.fiveHUnit})`);
        if (b.cwDelta > 0) valParts.push(`C/G -${b.cwDelta.toFixed(2)}%`);
        const sShort = b.startIso.slice(5, 16);
        const eShort = b.endIso.slice(5, 16);
        let tRange = sShort;
        if (sShort !== eShort) {
          tRange = isOff ? `${sShort} → ${eShort}` : `${sShort}–${b.endIso.slice(11, 16)}`;
        }
        return `
          <div class="burst-item">
            <div class="burst-main">
              <div class="burst-time">
                <span>${esc(tRange)}</span>
                ${kindPill}
                ${poolPill}
              </div>
              <div class="burst-sub">
                <span>${esc(t.durApprox(fmtDuration(b.durationMin)))}</span>
                ${b.g5Delta > 0 && b.gwDelta > 0 ? `<span>${esc(t.sub5hPool(`-${b.g5Delta.toFixed(2)}%`))}</span>` : ''}
                ${b.hasConcurrent && b.concurrentGwDelta > 0.01 ? `<span>${esc(t.subConc(`-${b.concurrentGwDelta.toFixed(2)}%`))}</span>` : ''}
              </div>
            </div>
            <div class="burst-val" style="color:${isOff ? 'var(--um-off)' : 'var(--um-ext)'}">
              ${esc(valParts.join(' · ') || '-')}
            </div>
          </div>
        `;
      }).join('') : `<div class="card empty">${esc(t.noExtBursts)}</div>`;
    }

    function renderOverview(d) {
      const t = T();
      const live = d.live || {};
      const pools = live.pools || {};
      const poolOrder = live.poolOrder || Object.keys(pools);
      const isOnline = Boolean(live.source && live.source !== 'offline');
      document.getElementById('liveDot').className = 'brand-dot' + (isOnline ? '' : ' offline');
      const liveTagEl = document.getElementById('liveSourceTag');
      liveTagEl.textContent = isOnline ? t.liveOnline : t.liveOffline;
      liveTagEl.title = isOnline ? `${live.source} · ${live.ms}ms` : t.liveOfflineTip;

      const hb = document.getElementById('hookBadge');
      hb.textContent = d.hookEnabled ? t.hookOn : t.hookOff;
      hb.className = 'pill ' + (d.hookEnabled ? 'ok' : 'danger');

      const recWk = (d.reconciliation || {}).week || {};
      const gemRec = recWk.gemini || {};
      const cgRec = recWk.claude_gpt || {};

      const grid = document.getElementById('poolsGrid');
      if (live.billingMode === 'paygo' && !poolOrder.length) {
        grid.innerHTML = `<div class="card empty" style="grid-column:1 / -1;">${esc(t.paygoNotice)}</div>`;
      } else {
        const cards = [];
        for (const k of poolOrder) {
          const p = pools[k];
          if (!p) continue;
          const used = Math.max(0, Math.min(100, Number(p.used || 0)));
          const rem = (p.remaining !== undefined && p.remaining !== null)
            ? Math.max(0, Math.min(100, Number(p.remaining)))
            : Math.max(0, 100 - used);
          let badge = `<span class="pill ok">${esc(t.healthy)}</span>`;
          let remColor = 'var(--um-fg)';
          let barColor = 'var(--um-ok)';
          if (p.disabled) {
            badge = `<span class="pill">${esc(t.disabled)}</span>`;
            remColor = 'var(--um-muted)';
            barColor = 'var(--um-muted)';
          } else if (rem <= 0.1) {
            badge = `<span class="pill danger">${esc(t.exhausted)}</span>`;
            remColor = 'var(--um-danger)';
            barColor = 'var(--um-danger)';
          } else if (rem < 15) {
            badge = `<span class="pill danger">${esc(t.low)}</span>`;
            remColor = 'var(--um-danger)';
            barColor = 'var(--um-danger)';
          } else if (rem < 40) {
            badge = `<span class="pill warn">${esc(t.tight)}</span>`;
            remColor = 'var(--um-warn)';
            barColor = 'var(--um-warn)';
          }

          const barHtml = `<div class="dual-seg" style="width:${rem.toFixed(2)}%;background:${barColor}"></div>`;
          let splitHint = `<span>${esc(p.cadence === '5h' ? t.rolling5h : t.weeklyPool)}</span>`;
          const wkRec = k === 'gemini_weekly' ? gemRec : (k === 'claude_gpt_weekly' ? cgRec : null);
          if (wkRec) {
            const loc = Math.min(used, Number(wkRec.localEst || 0));
            const ext = Math.max(0, used - loc);
            splitHint = `<span>${esc(t.poolSplitHint(fmtSpend(loc, 1), fmtSpend(ext, 1)))}</span>`;
          }

          cards.push(`
            <div class="card pool-card">
              <div class="pool-top">
                <span class="pool-name" title="${esc(p.bucketId || k)}">${esc(localizePoolLabel(k, p.label))}</span>
                ${badge}
              </div>
              <div class="pool-hero">
                <span class="pool-pct" style="color:${remColor}">${rem.toFixed(3)}%</span>
                <span class="pool-rem">${esc(t.usedWord)} ${fmtSpend(used, 3)}</span>
              </div>
              <div class="dual-bar">${barHtml}</div>
              <div class="pool-foot">
                ${splitHint}
                <span>${esc(p.resetShort)} ${esc(t.resetWord)}</span>
              </div>
            </div>
          `);
        }
        grid.innerHTML = cards.length ? cards.join('') : `<div class="empty" style="grid-column:1 / -1;">${esc(t.noLivePools)}</div>`;
      }

      document.getElementById('weekSinceTag').textContent =
        recWk.geminiSince ? t.weekSince(recWk.geminiSince.slice(5, 16)) : '';

      const renderRecBlock = (title, rec, liveUsedFallback, hasFb) => {
        const tot = Math.max(Number(rec.poolTotal || 0), Number(liveUsedFallback || 0));
        const rem = Math.max(0, 100 - tot);
        const loc = Number(rec.localEst || 0);
        const off = Number(rec.monOffline || 0);
        const extTotal = Math.max(0, tot - loc);
        const extOff = Math.min(extTotal, off);
        const extOn = Math.max(0, extTotal - extOff);
        const denom = Math.max(tot, loc + extTotal, 1e-6);
        const wLoc = Math.min(100, (loc / denom) * 100);
        const wExtOn = Math.min(100 - wLoc, (extOn / denom) * 100);
        const wExtOff = Math.min(100 - wLoc - wExtOn, (extOff / denom) * 100);
        const locPct = tot > 1e-5 ? Math.min(100, (loc / tot) * 100) : 0;
        const extPct = tot > 1e-5 ? Math.max(0, 100 - locPct) : 0;

        return `
          <div class="rec-block">
            <div class="rec-head">
              <span class="rec-title">${esc(title)} · ${esc(t.remWord)} ${rem.toFixed(1)}% <span style="color:var(--um-muted);font-weight:500">(${esc(t.totUsedWord)} ${fmtSpend(tot, 1)})</span></span>
              <div class="rec-split">
                <span class="pill local">${esc(t.myShare(locPct.toFixed(0)))}</span>
                <span class="pill ext">${esc(t.extShare(extPct.toFixed(0)))}</span>
              </div>
            </div>
            <div class="rec-bar">
              <div class="dual-seg" style="width:${wLoc.toFixed(2)}%;background:var(--um-local)"></div>
              <div class="dual-seg" style="width:${wExtOn.toFixed(2)}%;background:var(--um-ext)"></div>
              <div class="dual-seg" style="width:${wExtOff.toFixed(2)}%;background:var(--um-off)"></div>
            </div>
            <div class="rec-chips">
              <span class="chip-item"><i class="swatch" style="background:var(--um-local)"></i>${esc(t.chipMine)} ${fmtSpend(loc, 2, hasFb ? '*' : '')}</span>
              <span class="chip-item"><i class="swatch" style="background:var(--um-ext)"></i>${esc(t.chipExtOn)} ${fmtSpend(extOn, 2)}</span>
              <span class="chip-item"><i class="swatch" style="background:var(--um-off)"></i>${esc(t.chipExtOff)} ${fmtSpend(extOff, 2)}</span>
            </div>
          </div>
        `;
      };

      document.getElementById('reconcileCard').innerHTML =
        renderRecBlock(t.gemWeekTitle, gemRec, (pools.gemini_weekly || {}).used, recWk.hasFallbackEst) +
        renderRecBlock(t.cgWeekTitle, cgRec, (pools.claude_gpt_weekly || {}).used, false) +
        `<div class="rec-note">${esc(t.recNote)}</div>`;

      renderBurstsFeed(d);

      const recToday = ((d.reconciliation || {}).today || {}).gemini || {};
      const rows = [
        [t.rowToday, d.periods.today, recToday],
        [t.rowWeek, d.periods.week, gemRec],
      ];
      document.getElementById('periodBody').innerHTML = rows.map(([name, s, r]) => {
        const tok = (s.inTok + s.crTok + s.outTok) > 0
          ? `${fmtTok(s.inTok)}/${fmtTok(s.crTok)}/${fmtTok(s.outTok)}` : '-';
        const ext = Number(r.externalTotal || 0);
        const tot = Number(r.poolTotal || s.span || 0);
        return `
          <tr>
            <td><strong>${esc(name)}</strong></td>
            <td class="num">${s.turns}/${s.steps}</td>
            <td class="num">${esc(tok)}</td>
            <td class="num">${fmtSpend(s.localEst, 4, s.hasFallbackEst ? '*' : '')}</td>
            <td class="num" style="color:${ext > 0.05 ? 'var(--um-ext)' : 'inherit'}">${fmtSpend(ext, 2)}</td>
            <td class="num">${fmtSpend(tot, 2)}</td>
          </tr>
        `;
      }).join('');
    }

    function niceMax(val) {
      if (val <= 5) return 5;
      if (val <= 10) return 10;
      if (val <= 20) return 20;
      if (val <= 25) return 25;
      if (val <= 40) return 40;
      if (val <= 50) return 50;
      if (val <= 75) return 75;
      return 100;
    }

    function renderLineChart(series) {
      const t = T();
      const host = document.getElementById('lineChartHost');
      const tip = document.getElementById('lineTooltip');
      Array.from(host.querySelectorAll('svg, .empty')).forEach(el => el.remove());

      if (!series || series.length < 2) {
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = t.noLineData;
        host.appendChild(empty);
        tip.classList.remove('show');
        return;
      }

      const showGem = linePoolMode === 'gemini' || linePoolMode === 'both';
      const showCg = linePoolMode === 'cg' || linePoolMode === 'both';

      const legItems = [];
      if (showGem) {
        legItems.push(`<span class="leg-item"><i class="leg-dot" style="background:var(--um-local)"></i>${esc(t.gemWeekTitle)}</span>`);
        legItems.push(`<span class="leg-item"><i class="leg-dot" style="background:var(--um-g5)"></i>${esc(localizePoolLabel('gemini_5h', 'Gemini 5h'))}</span>`);
      }
      if (showCg) {
        legItems.push(`<span class="leg-item"><i class="leg-dot" style="background:var(--um-cg)"></i>${esc(t.cgWeekTitle)}</span>`);
      }
      legItems.push(`<span class="leg-item"><i class="leg-dot" style="background:var(--um-muted);opacity:0.45"></i>${esc(t.pillIdle)}</span>`);
      legItems.push(`<span class="leg-item"><i class="leg-dot" style="background:var(--um-off);opacity:0.55"></i>${esc(t.chartSleep)}</span>`);
      document.getElementById('lineLegend').innerHTML = legItems.join('');

      const W = Math.max(300, Math.floor(host.clientWidth || 440));
      const H = 215;
      const padL = 38, padR = 10, padT = 12, padB = 24;
      const plotW = W - padL - padR;
      const plotH = H - padT - padB;

      const remOf = v => Math.max(0, Math.min(100, 100 - Number(v || 0)));
      series = series.map(p => Object.assign({}, p, {
        gw: remOf(p.gw),
        g5: remOf(p.g5),
        cw: remOf(p.cw),
        rawGw: remOf(p.rawGw),
        rawG5: remOf(p.rawG5),
        rawCw: remOf(p.rawCw)
      }));
      const tMin = series[0].ts;
      const tMax = Math.max(tMin + 60, series[series.length - 1].ts);
      let minRem = 100;
      for (const p of series) {
        if (showGem) minRem = Math.min(minRem, p.gw, p.g5, showRawNoise ? Math.min(p.rawGw, p.rawG5) : 100);
        if (showCg) minRem = Math.min(minRem, p.cw, showRawNoise ? p.rawCw : 100);
      }
      const yMin = minRem >= 50 ? Math.max(0, Math.floor((minRem - 5) / 10) * 10) : 0;
      const yMax = 100;
      const ySpan = Math.max(10, yMax - yMin);
      const xOf = ts => padL + ((ts - tMin) / (tMax - tMin)) * plotW;
      const yOf = v => padT + plotH - (Math.max(0, Math.min(ySpan, v - yMin)) / ySpan) * plotH;

      let bandsSvg = '';
      let bStart = null;
      for (let i = 0; i < series.length; i++) {
        const p = series[i];
        if (i > 0 && p.gapBeforeSec > 300) {
          if (bStart !== null) {
            const x1 = xOf(bStart), x2 = xOf(series[i - 1].ts);
            if (x2 > x1) bandsSvg += `<rect x="${x1.toFixed(1)}" y="${padT}" width="${(x2 - x1).toFixed(1)}" height="${plotH}" fill="var(--um-idle-band)" />`;
            bStart = null;
          }
          const gx1 = xOf(series[i - 1].ts), gx2 = xOf(p.ts);
          const gw = Math.max(2, gx2 - gx1);
          bandsSvg += `<rect x="${gx1.toFixed(1)}" y="${padT}" width="${gw.toFixed(1)}" height="${plotH}" fill="url(#sleepHatch)" />`;
          if (gw > 28) {
            bandsSvg += `<text x="${(gx1 + gw / 2).toFixed(1)}" y="${(padT + 13).toFixed(1)}" text-anchor="middle" font-size="9" fill="var(--um-off)" opacity="0.9">${esc(t.chartSleep)}</text>`;
          }
          continue;
        }
        if (p.idle && bStart === null) bStart = p.ts;
        if (!p.idle && bStart !== null) {
          const x1 = xOf(bStart), x2 = xOf(p.ts);
          if (x2 > x1) bandsSvg += `<rect x="${x1.toFixed(1)}" y="${padT}" width="${(x2 - x1).toFixed(1)}" height="${plotH}" fill="var(--um-idle-band)" />`;
          bStart = null;
        }
      }
      if (bStart !== null) {
        const x1 = xOf(bStart), x2 = xOf(series[series.length - 1].ts);
        if (x2 > x1) bandsSvg += `<rect x="${x1.toFixed(1)}" y="${padT}" width="${(x2 - x1).toFixed(1)}" height="${plotH}" fill="var(--um-idle-band)" />`;
      }

      let resetsSvg = '';
      for (let i = 1; i < series.length; i++) {
        const p = series[i];
        if (p.resetGw || p.resetCw) {
          const rx = xOf(p.ts).toFixed(1);
          resetsSvg += `<line x1="${rx}" y1="${padT}" x2="${rx}" y2="${padT + plotH}" stroke="var(--um-danger)" stroke-width="1" stroke-dasharray="3,3" opacity="0.65" />`;
        }
      }

      function buildPaths(key, resetFlagKey, withArea) {
        let lineD = '';
        let bridgeD = '';
        let areaD = '';
        let segPts = [];
        const flushSeg = () => {
          if (segPts.length === 0) return;
          lineD += segPts.map((pt, idx) => `${idx === 0 ? 'M' : 'L'}${pt[0].toFixed(1)},${pt[1].toFixed(1)}`).join(' ') + ' ';
          if (withArea && segPts.length >= 2) {
            const baseY = (padT + plotH).toFixed(1);
            areaD += `M${segPts[0][0].toFixed(1)},${baseY} ` +
              segPts.map(pt => `L${pt[0].toFixed(1)},${pt[1].toFixed(1)}`).join(' ') +
              ` L${segPts[segPts.length - 1][0].toFixed(1)},${baseY} Z `;
          }
        };
        for (let i = 0; i < series.length; i++) {
          const p = series[i];
          const x = xOf(p.ts);
          const y = yOf(p[key]);
          const breakGap = i > 0 && p.gapBeforeSec > 300;
          const breakRst = i > 0 && resetFlagKey && p[resetFlagKey];
          if (breakGap || breakRst) {
            flushSeg();
            if (breakGap) {
              const px = xOf(series[i - 1].ts), py = yOf(series[i - 1][key]);
              bridgeD += `M${px.toFixed(1)},${py.toFixed(1)} L${x.toFixed(1)},${y.toFixed(1)} `;
            }
            segPts = [[x, y]];
          } else {
            segPts.push([x, y]);
          }
        }
        flushSeg();
        return { lineD, bridgeD, areaD };
      }

      const yGrid = [0, 0.25, 0.5, 0.75, 1].map(f => {
        const v = yMin + ySpan * f;
        const y = yOf(v);
        return `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" stroke="var(--um-grid-line)" stroke-dasharray="${f === 0 ? '' : '2,3'}" />
                <text x="${padL - 5}" y="${(y + 3).toFixed(1)}" text-anchor="end" font-size="9.5" font-family="var(--um-mono)" fill="var(--um-muted)">${Math.round(v)}%</text>`;
      }).join('');

      const xLabels = [0, 0.5, 1].map(f => {
        const idx = Math.min(series.length - 1, Math.round(f * (series.length - 1)));
        const p = series[idx];
        const lbl = currentWindow === '7d' ? p.iso.slice(5, 10) : p.iso.slice(11, 16);
        const x = xOf(p.ts);
        const anchor = f === 0 ? 'start' : (f === 1 ? 'end' : 'middle');
        return `<text x="${x.toFixed(1)}" y="${H - 6}" text-anchor="${anchor}" font-size="9.5" font-family="var(--um-mono)" fill="var(--um-muted)">${esc(lbl)}</text>`;
      }).join('');

      let pathsSvg = '';
      if (showRawNoise) {
        if (showGem) {
          const rgw = buildPaths('rawGw', null, false);
          pathsSvg += `<path d="${rgw.lineD}" fill="none" stroke="var(--um-local)" stroke-width="1" stroke-dasharray="2,2" opacity="0.40" />`;
        }
        if (showCg) {
          const rcw = buildPaths('rawCw', null, false);
          pathsSvg += `<path d="${rcw.lineD}" fill="none" stroke="var(--um-cg)" stroke-width="1" stroke-dasharray="2,2" opacity="0.40" />`;
        }
      }
      if (showCg) {
        const cwP = buildPaths('cw', 'resetCw', !showGem);
        if (cwP.areaD) pathsSvg += `<path d="${cwP.areaD}" fill="url(#gradCg)" />`;
        if (cwP.bridgeD) pathsSvg += `<path d="${cwP.bridgeD}" fill="none" stroke="var(--um-cg)" stroke-width="1.2" stroke-dasharray="2,4" opacity="0.55" />`;
        pathsSvg += `<path d="${cwP.lineD}" fill="none" stroke="var(--um-cg)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />`;
      }
      if (showGem) {
        const g5P = buildPaths('g5', 'resetG5', false);
        const gwP = buildPaths('gw', 'resetGw', true);
        if (gwP.areaD) pathsSvg += `<path d="${gwP.areaD}" fill="url(#gradGem)" />`;
        if (g5P.bridgeD) pathsSvg += `<path d="${g5P.bridgeD}" fill="none" stroke="var(--um-g5)" stroke-width="1.1" stroke-dasharray="2,4" opacity="0.50" />`;
        if (gwP.bridgeD) pathsSvg += `<path d="${gwP.bridgeD}" fill="none" stroke="var(--um-local)" stroke-width="1.3" stroke-dasharray="2,4" opacity="0.60" />`;
        pathsSvg += `<path d="${g5P.lineD}" fill="none" stroke="var(--um-g5)" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round" opacity="0.9" />`;
        pathsSvg += `<path d="${gwP.lineD}" fill="none" stroke="var(--um-local)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" />`;
      }

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svg.setAttribute('width', String(W));
      svg.setAttribute('height', String(H));
      svg.innerHTML = `
        <defs>
          <linearGradient id="gradGem" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--um-local)" stop-opacity="0.22" />
            <stop offset="100%" stop-color="var(--um-local)" stop-opacity="0.01" />
          </linearGradient>
          <linearGradient id="gradCg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--um-cg)" stop-opacity="0.20" />
            <stop offset="100%" stop-color="var(--um-cg)" stop-opacity="0.01" />
          </linearGradient>
          <pattern id="sleepHatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="var(--um-sleep-band)" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--um-off)" stroke-width="1" opacity="0.22" />
          </pattern>
        </defs>
        ${bandsSvg}
        ${yGrid}
        ${resetsSvg}
        ${pathsSvg}
        <line id="lineCross" x1="0" y1="${padT}" x2="0" y2="${padT + plotH}" stroke="var(--um-fg)" stroke-width="1" stroke-dasharray="2,2" opacity="0.5" visibility="hidden" />
        <circle id="dotGw" r="3.8" fill="var(--um-local)" stroke="var(--um-bg)" stroke-width="1.5" visibility="hidden" />
        <circle id="dotG5" r="3.2" fill="var(--um-g5)" stroke="var(--um-bg)" stroke-width="1.3" visibility="hidden" />
        <circle id="dotCw" r="3.6" fill="var(--um-cg)" stroke="var(--um-bg)" stroke-width="1.5" visibility="hidden" />
        ${xLabels}
      `;
      host.insertBefore(svg, tip);

      const cross = svg.getElementById('lineCross');
      const dGw = svg.getElementById('dotGw');
      const dG5 = svg.getElementById('dotG5');
      const dCw = svg.getElementById('dotCw');

      const handleMove = clientX => {
        const rect = svg.getBoundingClientRect();
        const relX = ((clientX - rect.left) / rect.width) * W;
        const ratio = Math.max(0, Math.min(1, (relX - padL) / plotW));
        const targetTs = tMin + ratio * (tMax - tMin);
        let best = series[0], bestDist = Infinity;
        for (const p of series) {
          const dist = Math.abs(p.ts - targetTs);
          if (dist < bestDist) { bestDist = dist; best = p; }
        }
        const cx = xOf(best.ts);
        cross.setAttribute('x1', cx.toFixed(1));
        cross.setAttribute('x2', cx.toFixed(1));
        cross.setAttribute('visibility', 'visible');

        if (showGem) {
          dGw.setAttribute('cx', cx.toFixed(1)); dGw.setAttribute('cy', yOf(best.gw).toFixed(1)); dGw.setAttribute('visibility', 'visible');
          dG5.setAttribute('cx', cx.toFixed(1)); dG5.setAttribute('cy', yOf(best.g5).toFixed(1)); dG5.setAttribute('visibility', 'visible');
        } else {
          dGw.setAttribute('visibility', 'hidden'); dG5.setAttribute('visibility', 'hidden');
        }
        if (showCg) {
          dCw.setAttribute('cx', cx.toFixed(1)); dCw.setAttribute('cy', yOf(best.cw).toFixed(1)); dCw.setAttribute('visibility', 'visible');
        } else {
          dCw.setAttribute('visibility', 'hidden');
        }

        const st = best.offlineGap ? t.stSleepWake : (best.idle ? t.stIdle : t.stActive);
        tip.innerHTML = `
          <div class="tt-time"><span>${esc(best.iso.slice(5, 19))}</span><span style="color:var(--um-muted)">${esc(st)}</span></div>
          ${showGem ? `<div class="tt-row"><span style="color:var(--um-local)">Gem Wk</span><span>${esc(t.remWord)} ${best.gw.toFixed(2)}%${esc(fmtNegDelta(best.dgw))}</span></div>` : ''}
          ${showGem ? `<div class="tt-row"><span style="color:var(--um-g5)">Gem 5h</span><span>${esc(t.remWord)} ${best.g5.toFixed(2)}%${esc(fmtNegDelta(best.dg5))}</span></div>` : ''}
          ${showCg ? `<div class="tt-row"><span style="color:var(--um-cg)">C/G Wk</span><span>${esc(t.remWord)} ${best.cw.toFixed(2)}%${esc(fmtNegDelta(best.dcw))}</span></div>` : ''}
        `;
        tip.classList.add('show');
        const tipW = tip.offsetWidth || 180;
        const leftPx = (cx / W) * rect.width;
        const clamped = leftPx + 12 + tipW > rect.width ? Math.max(4, leftPx - tipW - 10) : Math.min(rect.width - tipW - 4, leftPx + 10);
        tip.style.left = `${clamped.toFixed(0)}px`;
        tip.style.top = '8px';
      };

      svg.addEventListener('mousemove', e => handleMove(e.clientX));
      svg.addEventListener('touchmove', e => {
        if (e.touches && e.touches[0]) handleMove(e.touches[0].clientX);
      }, { passive: true });
      svg.addEventListener('mouseleave', () => {
        cross.setAttribute('visibility', 'hidden');
        dGw.setAttribute('visibility', 'hidden');
        dG5.setAttribute('visibility', 'hidden');
        dCw.setAttribute('visibility', 'hidden');
        tip.classList.remove('show');
      });
    }

    function renderBarChart(buckets) {
      const t = T();
      const host = document.getElementById('barChartHost');
      const tip = document.getElementById('barTooltip');
      Array.from(host.querySelectorAll('svg, .empty')).forEach(el => el.remove());

      const isGw = barPoolMode === 'gw';
      document.getElementById('barTitle').textContent = currentWindow === '7d'
        ? (isGw ? t.barDayGem : t.barDayCg)
        : (isGw ? t.barHourGem : t.barHourCg);

      if (!buckets || !buckets.length) {
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = t.noBarData;
        host.appendChild(empty);
        tip.classList.remove('show');
        return;
      }

      const kLoc = isGw ? 'gwLocal' : 'cwLocal';
      const kOn = isGw ? 'gwExtOnline' : 'cwExtOnline';
      const kOff = isGw ? 'gwExtOffline' : 'cwExtOffline';
      const kTot = isGw ? 'gwTotal' : 'cwTotal';

      const W = Math.max(300, Math.floor(host.clientWidth || 440));
      const H = 175;
      const padL = 38, padR = 10, padT = 10, padB = 22;
      const plotW = W - padL - padR;
      const plotH = H - padT - padB;

      let maxTot = 1;
      for (const b of buckets) maxTot = Math.max(maxTot, Number(b[kTot] || 0));
      const yMax = niceMax(maxTot * 1.12);
      const yOf = v => padT + plotH - (Math.max(0, Math.min(yMax, v)) / yMax) * plotH;

      const yGrid = [0, 0.5, 1].map(f => {
        const v = yMax * f;
        const y = yOf(v);
        const yLbl = v === 0 ? '0%' : `-${v >= 10 ? Math.round(v) : v.toFixed(1)}%`;
        return `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" stroke="var(--um-grid-line)" stroke-dasharray="${f === 0 ? '' : '2,3'}" />
                <text x="${padL - 5}" y="${(y + 3).toFixed(1)}" text-anchor="end" font-size="9.5" font-family="var(--um-mono)" fill="var(--um-muted)">${yLbl}</text>`;
      }).join('');

      const n = buckets.length;
      const slotW = plotW / n;
      const barW = Math.max(4, Math.min(24, slotW * 0.62));
      const stride = n > 14 ? Math.ceil(n / 6) : (n > 8 ? 2 : 1);

      let barsSvg = '';
      let xLbls = '';
      buckets.forEach((b, i) => {
        const cx = padL + (i + 0.5) * slotW;
        const x = cx - barW / 2;
        const vLoc = Number(b[kLoc] || 0);
        const vOn = Number(b[kOn] || 0);
        const vOff = Number(b[kOff] || 0);

        const y0 = yOf(0);
        const y1 = yOf(vLoc);
        const y2 = yOf(vLoc + vOn);
        const y3 = yOf(vLoc + vOn + vOff);

        barsSvg += `<rect class="bar-hit" data-bi="${i}" x="${(padL + i * slotW).toFixed(1)}" y="${padT}" width="${slotW.toFixed(1)}" height="${plotH}" fill="transparent" />`;
        if (vLoc > 1e-4) barsSvg += `<rect x="${x.toFixed(1)}" y="${y1.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1.5, y0 - y1).toFixed(1)}" rx="1.5" fill="var(--um-local)" pointer-events="none" />`;
        if (vOn > 1e-4) barsSvg += `<rect x="${x.toFixed(1)}" y="${y2.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1.5, y1 - y2).toFixed(1)}" rx="1.5" fill="var(--um-ext)" pointer-events="none" />`;
        if (vOff > 1e-4) barsSvg += `<rect x="${x.toFixed(1)}" y="${y3.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1.5, y2 - y3).toFixed(1)}" rx="1.5" fill="var(--um-off)" pointer-events="none" />`;

        if (i % stride === 0 || i === n - 1) {
          xLbls += `<text x="${cx.toFixed(1)}" y="${H - 5}" text-anchor="middle" font-size="9.5" font-family="var(--um-mono)" fill="var(--um-muted)">${esc(b.label)}</text>`;
        }
      });

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svg.setAttribute('width', String(W));
      svg.setAttribute('height', String(H));
      svg.innerHTML = `${yGrid}${barsSvg}${xLbls}`;
      host.insertBefore(svg, tip);

      svg.addEventListener('mousemove', e => {
        const rect = svg.getBoundingClientRect();
        const relX = ((e.clientX - rect.left) / rect.width) * W;
        const idx = Math.max(0, Math.min(n - 1, Math.floor((relX - padL) / slotW)));
        const b = buckets[idx];
        if (!b) return;
        tip.innerHTML = `
          <div class="tt-time"><span>${esc(b.key)}</span><span>${esc(t.barTotal(fmtSpend(b[kTot], 2)))}</span></div>
          <div class="tt-row"><span style="color:var(--um-local)">${esc(t.chipMine)}</span><span>${fmtSpend(b[kLoc], 2)}</span></div>
          <div class="tt-row"><span style="color:var(--um-ext)">${esc(t.thOther)}</span><span>${fmtSpend(b[kOn], 2)}</span></div>
          <div class="tt-row"><span style="color:var(--um-off)">${esc(t.chipExtOff)}</span><span>${fmtSpend(b[kOff], 2)}</span></div>
        `;
        tip.classList.add('show');
        const tipW = tip.offsetWidth || 165;
        const cxPx = ((padL + (idx + 0.5) * slotW) / W) * rect.width;
        const left = cxPx + 10 + tipW > rect.width ? Math.max(4, cxPx - tipW - 8) : Math.min(rect.width - tipW - 4, cxPx + 8);
        tip.style.left = `${left.toFixed(0)}px`;
        tip.style.top = '6px';
      });
      svg.addEventListener('mouseleave', () => tip.classList.remove('show'));
    }

    function renderChangesTable(d) {
      const t = T();
      const m = d.monitor || {};
      const chgs = m.recentChanges || [];
      const filtered = chgs.filter(r => {
        if (chgFilter === 'ext') return r.kind === 'idle' || r.kind === 'offline';
        if (chgFilter === 'reset') return r.kind === 'reset';
        return true;
      });
      document.getElementById('changesBody').innerHTML = filtered.length ? filtered.map(r => {
        const badgeCls = r.kind === 'offline' ? 'off' : (r.kind === 'idle' ? 'ext' : (r.kind === 'reset' ? 'danger' : 'local'));
        const g5Rem = Math.max(0, 100 - Number(r.g5 || 0));
        const gwRem = Math.max(0, 100 - Number(r.gw || 0));
        const cwRem = Math.max(0, 100 - Number(r.cw || 0));
        return `
          <tr>
            <td>${esc(r.iso.slice(5, 19))}</td>
            <td class="num">${g5Rem.toFixed(1)}%${esc(fmtNegDelta(r.dg5))}</td>
            <td class="num">${gwRem.toFixed(1)}%${esc(fmtNegDelta(r.dgw))}</td>
            <td class="num">${cwRem.toFixed(1)}%${esc(fmtNegDelta(r.dcw))}</td>
            <td><span class="pill ${badgeCls}">${esc(localizeChangeTag(r))}</span></td>
          </tr>
        `;
      }).join('') : `<tr><td colspan="5" class="empty">${esc(t.noChanges)}</td></tr>`;
    }

    function renderMonitor(d) {
      const t = T();
      const m = d.monitor || {};
      document.getElementById('chgMeta').textContent = t.filteredNoise(m.rollbackCountWin || 0);
      renderLineChart(m.series || []);
      renderBarChart(m.buckets || []);
      renderChangesTable(d);
    }

    function renderLedger(d) {
      const t = T();
      const models = d.models || [];
      document.getElementById('modelBars').innerHTML = models.length ? models.map(m => {
        const rateTxt = m.rateWeekly !== null
          ? `${fmtSpend(m.rateWeekly, 4)}${m.estimated ? t.estSibling : ''}`
          : t.pendingCal;
        const estTxt = m.estGw !== null ? `${fmtSpend(m.estGw, 4)}${m.estimated ? '*' : ''}` : '-';
        const wPct = Math.max(0, Math.min(100, Number(m.sharePct || 0)));
        return `
          <div class="mbar-row">
            <div class="mbar-top">
              <span class="mbar-name">${esc(m.model)}</span>
              <span style="font-family:var(--um-mono);font-weight:700">${esc(estTxt)} <span style="color:var(--um-muted);font-weight:400">(${wPct.toFixed(1)}%)</span></span>
            </div>
            <div class="mbar-track"><div class="mbar-fill" style="width:${wPct.toFixed(1)}%"></div></div>
            <div class="mbar-sub">
              <span>${esc(t.modelSub(m.turns, m.steps, m.hitPct.toFixed(1)))}</span>
              <span>${esc(t.ratePer1M(rateTxt))}</span>
            </div>
          </div>
        `;
      }).join('') : `<div class="card empty">${esc(t.noModels)}</div>`;

      const turns = d.recentTurns || [];
      document.getElementById('recentBody').innerHTML = turns.length ? turns.map(turn => {
        const rowCls = turn.contaminated ? 'row-warn' : '';
        const stLocal = localizeTurnStatus(turn.status);
        let stPill = `<span class="pill">${esc(stLocal)}</span>`;
        if (turn.contaminated) {
          stPill = `<span class="pill warn" title="${esc(t.contamTip)}">${esc(t.contamPill)}</span>`;
        } else if (turn.status === '正常') {
          stPill = `<span class="pill ok">${esc(t.normalPill)}</span>`;
        }
        return `
          <tr class="${rowCls}">
            <td>${esc(turn.endIso.slice(5, 16))}</td>
            <td>${esc(turn.workspace.slice(0, 12))}</td>
            <td>${esc(turn.model)}</td>
            <td class="num">${turn.steps}</td>
            <td class="num">${esc(fmtSpendStr(turn.est))}</td>
            <td class="num">${esc(fmtSpendStr(turn.obs))}</td>
            <td>${stPill}</td>
          </tr>
        `;
      }).join('') : `<tr><td colspan="7" class="empty">${esc(t.noTurns)}</td></tr>`;
    }

    function renderSettingsDiag(d) {
      const t = T();
      const diag = d.diagnostics || {};
      const gR = diag.geminiRatio || { ratio: 4.0, samples: 0, calibrated: false };
      const cR = diag.cgRatio || { ratio: 4.0, samples: 0, calibrated: false };
      const poolsTxt = (diag.poolKeys && diag.poolKeys.length) ? diag.poolKeys.join(', ') : '-';
      const rows = [
        [t.diagVer, `v${diag.version || '0.1.0'}`],
        [t.diagBill, `${diag.billingMode || '-'}${diag.plan ? ' (' + diag.plan + ')' : ''}`],
        [t.diagRatioGem, t.diagCal(Number(gR.ratio || 4).toFixed(2), gR.samples || 0, gR.calibrated)],
        [t.diagRatioCg, t.diagCal(Number(cR.ratio || 4).toFixed(2), cR.samples || 0, cR.calibrated)],
        [t.diagPools, poolsTxt],
        [t.diagCounts, `${diag.ledgerCount || 0} / ${diag.monitorCount || 0}`],
        [t.diagEnv, `${diag.platform || '-'} · Python ${diag.pythonVersion || '-'}`],
        [t.diagDir, diag.dataDir || '-'],
      ];
      document.getElementById('diagCard').innerHTML = rows.map(([k, v]) => `
        <div class="diag-row">
          <span class="diag-k">${esc(k)}</span>
          <span class="diag-v">${esc(v)}</span>
        </div>
      `).join('');
    }

    function renderAllFromLatest() {
      if (!latestData) return;
      const t = T();
      document.getElementById('metaLine').textContent = t.updatedAt(latestData.generatedAt.slice(11, 19));
      renderOverview(latestData);
      renderMonitor(latestData);
      renderLedger(latestData);
      renderSettingsDiag(latestData);
    }

    async function refreshAll() {
      const t = T();
      const btn = document.getElementById('refreshBtn');
      btn.disabled = true;
      try {
        const data = await postApi('/api/dashboard', { window: currentWindow, recent: 25 });
        if (data.uiVersion) {
          if (!bootUiVersion) bootUiVersion = data.uiVersion;
          else if (data.uiVersion !== bootUiVersion) {
            window.location.reload();
            return;
          }
        }
        latestData = data;
        renderAllFromLatest();
      } catch (err) {
        document.getElementById('metaLine').textContent = t.refreshFail(err.message);
      } finally {
        btn.disabled = false;
      }
    }

    async function triggerAction(action, bodyParams = {}) {
      const t = T();
      const toast = document.getElementById('opsToast');
      toast.textContent = t.running;
      try {
        const res = await postApi('/api/action', { action, ...bodyParams });
        toast.textContent = res.message || (res.ok ? t.done : res.error);
        await refreshAll();
      } catch (err) {
        toast.textContent = t.opFailed(err.message);
      }
    }

    async function exportSummary(downloadFile) {
      const t = T();
      const toast = document.getElementById('opsToast');
      const pre = document.getElementById('summaryPreview');
      toast.textContent = t.running;
      try {
        const res = await postApi('/api/action', { action: 'export_summary', lang: effLang() });
        const content = res.content || '';
        pre.style.display = 'block';
        pre.textContent = content;
        if (downloadFile) {
          const fname = res.filename || 'agy-usage-summary.txt';
          const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = fname;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
          toast.textContent = t.downloadedSummary(fname);
        } else {
          try {
            await navigator.clipboard.writeText(content);
            toast.textContent = t.copiedSummary;
          } catch (_e) {
            toast.textContent = t.copyFailed;
          }
        }
      } catch (err) {
        toast.textContent = t.opFailed(err.message);
      }
    }

    document.querySelectorAll('.tab').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(tb => tb.classList.remove('active'));
        document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
        el.classList.add('active');
        activeTab = el.dataset.tab;
        document.getElementById('pane-' + activeTab).classList.add('active');
        if (activeTab === 'monitor' && latestData) renderMonitor(latestData);
      });
    });

    document.querySelectorAll('#overviewBurstGroup button').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('#overviewBurstGroup button').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
        overviewBurstWindow = el.dataset.obw;
        if (latestData) renderBurstsFeed(latestData);
      });
    });

    document.querySelectorAll('#winGroup button').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('#winGroup button').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
        currentWindow = el.dataset.win;
        refreshAll();
      });
    });

    document.querySelectorAll('#poolGroup button').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('#poolGroup button').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
        linePoolMode = el.dataset.pool;
        if (latestData) renderLineChart((latestData.monitor || {}).series || []);
      });
    });

    document.querySelectorAll('#barPoolGroup button').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('#barPoolGroup button').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
        barPoolMode = el.dataset.bpool;
        if (latestData) renderBarChart((latestData.monitor || {}).buckets || []);
      });
    });

    document.querySelectorAll('#chgFilterGroup button').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('#chgFilterGroup button').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
        chgFilter = el.dataset.cfilter;
        if (latestData) renderChangesTable(latestData);
      });
    });

    document.getElementById('chkRawNoise').addEventListener('change', e => {
      showRawNoise = Boolean(e.target.checked);
      if (latestData) renderLineChart((latestData.monitor || {}).series || []);
    });

    document.getElementById('langToggleBtn').addEventListener('click', () => {
      langPref = effLang() === 'zh-CN' ? 'en' : 'zh-CN';
      localStorage.setItem('um_lang', langPref);
      applyStaticI18n();
      renderAllFromLatest();
    });

    document.getElementById('langSelect').addEventListener('change', e => {
      langPref = e.target.value || 'auto';
      localStorage.setItem('um_lang', langPref);
      applyStaticI18n();
      renderAllFromLatest();
    });

    document.getElementById('refreshBtn').addEventListener('click', refreshAll);
    document.getElementById('btnToggleHook').addEventListener('click', () => triggerAction('toggle_hook'));
    document.getElementById('btnBackfill').addEventListener('click', () => triggerAction('backfill'));
    document.getElementById('btnCopySummary').addEventListener('click', () => exportSummary(false));
    document.getElementById('btnDownloadSummary').addEventListener('click', () => exportSummary(true));

    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => {
        if (activeTab === 'monitor' && latestData) renderMonitor(latestData);
      });
      ro.observe(document.getElementById('pane-monitor'));
    }

    applyStaticI18n();
    refreshAll();
    setInterval(() => {
      if (!document.hidden) refreshAll();
    }, 30000);
  </script>
</body>
</html>
"""
