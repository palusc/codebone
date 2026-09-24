"""The live graph page served at /codebone/graph/ui: one self-contained HTML document (canvas rendering,
force layout, inspector drawer). The page is a plain template; only the port is substituted."""

_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>codebone — Semantic Code Graph</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  :root {
    --bg-dark: #0a0d14;
    --panel-bg: rgba(16, 21, 32, 0.84);
    --panel-border: rgba(255, 255, 255, 0.08);
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --color-domain: #8b5cf6;
    --color-file: #10b981;
    --color-route: #0ea5e9;
    --color-table: #f59e0b;
    --color-event: #f43f5e;
  }

  body {
    background: var(--bg-dark);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    overflow: hidden;
    height: 100vh;
    width: 100vw;
    -webkit-font-smoothing: antialiased;
    user-select: none;
  }

  #canvas {
    display: block;
    width: 100%;
    height: 100%;
    cursor: grab;
    background: radial-gradient(ellipse at 50% 30%, #151d2f 0%, #0a0d14 100%);
  }
  #canvas:active { cursor: grabbing; }

  /* Top Navigation & Telemetry HUD */
  #hud-top {
    position: fixed;
    top: 16px;
    left: 16px;
    z-index: 20;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 580px;
  }

  .glass-card {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border-radius: 12px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4), 0 1px 1px rgba(255, 255, 255, 0.05);
  }

  .hud-main {
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .brand-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .brand-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    letter-spacing: -0.3px;
  }

  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 500;
    padding: 3px 8px;
    border-radius: 9999px;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: #34d399;
  }
  .status-badge.sniffing {
    background: rgba(14, 165, 233, 0.12);
    border-color: rgba(14, 165, 233, 0.25);
    color: #38bdf8;
  }
  .pulse-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 6px currentColor;
    animation: pulse 2s infinite ease-in-out;
  }
  @keyframes pulse {
    0%, 100% { transform: scale(0.9); opacity: 0.7; }
    50% { transform: scale(1.3); opacity: 1; }
  }

  .project-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-secondary);
  }
  .project-name {
    font-weight: 600;
    color: #f8fafc;
    background: rgba(255, 255, 255, 0.06);
    padding: 2px 7px;
    border-radius: 5px;
    max-width: 240px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Stats Metric Bar */
  .metrics-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    padding-top: 4px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
  }

  .stat-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.05);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .stat-pill:hover, .stat-pill.active {
    background: rgba(255, 255, 255, 0.09);
    border-color: rgba(255, 255, 255, 0.18);
    color: #fff;
    transform: translateY(-1px);
  }
  .stat-val {
    font-weight: 700;
    color: #f1f5f9;
  }

  /* Search & Controls */
  .search-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .search-box {
    position: relative;
    flex: 1;
  }
  .search-input {
    width: 100%;
    padding: 7px 12px 7px 30px;
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    color: #fff;
    font-size: 12px;
    outline: none;
    transition: all 0.18s ease;
  }
  .search-input:focus {
    border-color: #6366f1;
    background: rgba(0, 0, 0, 0.55);
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
  }
  .search-icon {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    width: 13px;
    height: 13px;
    color: var(--text-muted);
    pointer-events: none;
  }

  .action-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    border-radius: 8px;
    background: #1e293b;
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #f1f5f9;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
  }
  .action-btn:hover {
    background: #2d3748;
    border-color: rgba(255, 255, 255, 0.22);
    transform: translateY(-1px);
  }
  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  /* Bottom Controls & Legend */
  #legend {
    position: fixed;
    bottom: 20px;
    left: 20px;
    z-index: 20;
    display: flex;
    gap: 8px;
    padding: 8px 12px;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11.5px;
    font-weight: 500;
    color: var(--text-secondary);
    padding: 3px 8px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .legend-item:hover {
    background: rgba(255, 255, 255, 0.05);
    color: #fff;
  }
  .legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  /* Viewport Controls */
  #viewport-controls {
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 20;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .vp-btn {
    width: 34px;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    backdrop-filter: blur(16px);
    border-radius: 8px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .vp-btn:hover {
    background: rgba(255, 255, 255, 0.12);
    color: #fff;
    transform: scale(1.05);
  }

  /* MCP Setup Ping Card & Pulse Beacon */
  .mcp-ping-card {
    padding: 10px 14px;
    background: linear-gradient(135deg, rgba(30, 41, 59, 0.92) 0%, rgba(15, 23, 42, 0.95) 100%);
    border: 1px solid rgba(129, 140, 248, 0.35);
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    box-shadow: 0 4px 20px rgba(99, 102, 241, 0.15), 0 1px 3px rgba(0, 0, 0, 0.4);
  }
  .mcp-ping-card:hover {
    transform: translateY(-1px);
    border-color: rgba(129, 140, 248, 0.65);
    background: linear-gradient(135deg, rgba(39, 51, 75, 0.96) 0%, rgba(17, 27, 50, 0.98) 100%);
    box-shadow: 0 6px 24px rgba(99, 102, 241, 0.25);
  }
  .mcp-ping-content {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .mcp-ping-beacon {
    position: relative;
    width: 14px;
    height: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .mcp-ping-core {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #818cf8;
    box-shadow: 0 0 8px #818cf8;
  }
  .mcp-ping-ring {
    position: absolute;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 2px solid #818cf8;
    opacity: 0.8;
    animation: beacon-ping 1.8s cubic-bezier(0, 0, 0.2, 1) infinite;
  }
  @keyframes beacon-ping {
    0% { transform: scale(0.6); opacity: 1; }
    80%, 100% { transform: scale(2.2); opacity: 0; }
  }
  .mcp-ping-text {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .mcp-ping-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -0.2px;
  }
  .mcp-ping-sub {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 1px 6px;
    border-radius: 4px;
    background: rgba(129, 140, 248, 0.16);
    color: #a5b4fc;
    border: 1px solid rgba(129, 140, 248, 0.25);
  }
  .mcp-ping-desc {
    font-size: 11px;
    color: #94a3b8;
    line-height: 1.3;
  }
  .mcp-ping-close {
    background: none;
    border: none;
    color: #64748b;
    font-size: 14px;
    cursor: pointer;
    padding: 4px 6px;
    border-radius: 4px;
    transition: color 0.15s;
    line-height: 1;
  }
  .mcp-ping-close:hover {
    color: #f1f5f9;
    background: rgba(255, 255, 255, 0.08);
  }
  /* Hover Tooltip */
  #tooltip {
    position: fixed;
    z-index: 30;
    pointer-events: none;
    opacity: 0;
    transform: translateY(4px);
    transition: opacity 0.12s ease, transform 0.12s ease;
    padding: 8px 12px;
    max-width: 280px;
    font-size: 11px;
    line-height: 1.4;
  }
  #tooltip.visible {
    opacity: 1;
    transform: translateY(0);
  }
  .tt-title {
    font-weight: 700;
    color: #fff;
    margin-bottom: 2px;
  }
  .tt-type {
    display: inline-block;
    font-size: 9.5px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 4px;
    margin-bottom: 4px;
    text-transform: uppercase;
  }
  .tt-summary {
    color: var(--text-secondary);
  }

  /* Node Inspector Drawer */
  #sidebar {
    position: fixed;
    top: 16px;
    right: 16px;
    bottom: 16px;
    width: 380px;
    z-index: 40;
    display: flex;
    flex-direction: column;
    transform: translateX(calc(100% + 32px));
    transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
    overflow: hidden;
  }
  #sidebar.open {
    transform: translateX(0);
  }

  .sb-header {
    padding: 18px 20px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    display: flex;
    flex-direction: column;
    gap: 6px;
    position: relative;
  }

  .sb-close {
    position: absolute;
    top: 16px;
    right: 16px;
    width: 26px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .sb-close:hover {
    background: rgba(255, 255, 255, 0.12);
    color: #fff;
  }

  .sb-body {
    padding: 18px 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
    flex: 1;
  }

  .sb-section-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--text-muted);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .summary-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 12px 14px;
    font-size: 12.5px;
    line-height: 1.55;
    color: #e2e8f0;
  }

  .entity-chip-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .entity-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 500;
    padding: 4px 8px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: #f1f5f9;
  }
  .entity-chip.table { border-color: rgba(245, 158, 11, 0.3); color: #fbbf24; }
  .entity-chip.route { border-color: rgba(14, 165, 233, 0.3); color: #38bdf8; }
  .entity-chip.event { border-color: rgba(244, 63, 94, 0.3); color: #fb7185; }
  .entity-chip.domain { border-color: rgba(139, 92, 246, 0.3); color: #a78bfa; }

  .connection-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .connection-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 7px 10px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 6px;
    font-size: 11.5px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .connection-item:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.15);
    transform: translateX(3px);
  }

  /* Loading Overlay */
  #loading {
    position: fixed;
    inset: 0;
    background: var(--bg-dark);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    flex-direction: column;
    gap: 16px;
  }
  .loader-spinner {
    width: 36px;
    height: 36px;
    border: 3px solid rgba(255, 255, 255, 0.08);
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Feedback & Bug Report Modal */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.65);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    z-index: 150;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s ease;
  }
  .modal-backdrop.active {
    opacity: 1;
    pointer-events: auto;
  }
  .feedback-modal {
    width: 480px;
    max-width: 95vw;
    background: rgba(16, 21, 32, 0.94);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    transform: scale(0.95) translateY(10px);
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .modal-backdrop.active .feedback-modal {
    transform: scale(1) translateY(0);
  }
  .fb-header {
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .fb-title {
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .fb-tabs {
    display: flex;
    gap: 6px;
    padding: 14px 20px 0;
  }
  .fb-tab {
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 11.5px;
    font-weight: 600;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .fb-tab:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
  }
  .fb-tab.active {
    background: rgba(99, 102, 241, 0.18);
    border-color: rgba(99, 102, 241, 0.45);
    color: #818cf8;
  }
  .fb-body {
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .fb-field {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .fb-field label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .fb-field input, .fb-field textarea {
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 8px 12px;
    color: #fff;
    font-size: 12.5px;
    font-family: inherit;
    outline: none;
    transition: all 0.15s ease;
  }
  .fb-field input:focus, .fb-field textarea:focus {
    border-color: #6366f1;
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
  }
  .fb-diag-box {
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 6px;
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.4;
  }
  .fb-footer {
    padding: 14px 20px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    background: rgba(0, 0, 0, 0.2);
  }
  .fb-submit-btn {
    background: #4f46e5;
    border-color: rgba(99, 102, 241, 0.5);
  }
  .fb-submit-btn:hover {
    background: #4338ca;
  }
  .fb-result-banner {
    padding: 12px 14px;
    border-radius: 8px;
    font-size: 12px;
    line-height: 1.5;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: #34d399;
  }
</style>
</head>
<body>

<div id="loading">
  <div class="loader-spinner" id="loading-spinner"></div>
  <div id="loading-msg" style="color:var(--text-secondary);font-size:13px;font-weight:500;max-width:420px;text-align:center;">Loading architecture&hellip;</div>
  <button class="action-btn" id="loading-retry" onclick="location.reload()" style="display:none;">Retry</button>
</div>

<canvas id="canvas"></canvas>

<!-- Top Telemetry HUD -->
<div id="hud-top">
  <div class="glass-card hud-main">
    <div class="brand-row">
      <div class="brand-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#818cf8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
        codebone
        <span style="font-weight:400;color:var(--text-muted);font-size:12px;">Architecture</span>
      </div>
      <div class="status-badge" id="status-indicator">
        <div class="pulse-dot"></div>
        <span id="status-text">Watching</span>
      </div>
    </div>

    <div class="project-meta">
      <span>Project:</span>
      <span class="project-name" id="project-name-display">—</span>
      <span style="color:var(--text-muted);">•</span>
      <span id="model-display" style="font-size:11px;color:var(--text-muted);">Local Metal AI</span>
    </div>

    <!-- Metrics Bar -->
    <div class="metrics-bar" id="metrics-bar">
      <div class="stat-pill active" data-filter="all" onclick="setFilter('all')">All <span class="stat-val" id="count-all">0</span></div>
      <div class="stat-pill" data-filter="domain" onclick="setFilter('domain')">Domains <span class="stat-val" id="count-domains" style="color:var(--color-domain)">0</span></div>
      <div class="stat-pill" data-filter="file" onclick="setFilter('file')">Files <span class="stat-val" id="count-files" style="color:var(--color-file)">0</span></div>
      <div class="stat-pill" data-filter="table" onclick="setFilter('table')">Tables <span class="stat-val" id="count-tables" style="color:var(--color-table)">0</span></div>
      <div class="stat-pill" data-filter="route" onclick="setFilter('route')">Routes <span class="stat-val" id="count-routes" style="color:var(--color-route)">0</span></div>
      <div class="stat-pill" data-filter="event" onclick="setFilter('event')">Events <span class="stat-val" id="count-events" style="color:var(--color-event)">0</span></div>
      <div class="stat-pill" onclick="fitView()">Edges <span class="stat-val" id="count-edges">0</span></div>
    </div>

    <!-- Search & Actions -->
    <div class="search-row">
      <div class="search-box">
        <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input type="text" id="search-input" class="search-input" placeholder="Search architecture, models, routes... (Press /)" autocomplete="off">
      </div>
      <button class="action-btn" id="rescan-btn" onclick="triggerRescan()">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
        Scan Project
      </button>
      <button class="action-btn" id="feedback-btn" onclick="openFeedbackModal()" title="Report bug or submit feedback">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        Feedback
      </button>
    </div>
  </div>

  <!-- MCP Setup Ping Banner (First Days / Setup Reminder) -->
  <div id="mcp-ping-banner" class="glass-card mcp-ping-card" style="display:none;" onclick="openMcpGuide()">
    <div class="mcp-ping-content">
      <div class="mcp-ping-beacon">
        <span class="mcp-ping-ring"></span>
        <span class="mcp-ping-core"></span>
      </div>
      <div class="mcp-ping-text">
        <div class="mcp-ping-title">
          <span>⚡ Connect AI Assistant (MCP)</span>
          <span class="mcp-ping-sub">Claude · Cursor · Gemini</span>
        </div>
        <div class="mcp-ping-desc">codebone serves live architecture to your AI. Click to view auto-setup guide.</div>
      </div>
      <button class="mcp-ping-close" onclick="dismissMcpPing(event)" title="Dismiss for now">✕</button>
    </div>
  </div>
</div>

<!-- Legend Bar -->
<div id="legend" class="glass-card">
  <div class="legend-item" onclick="setFilter('domain')"><div class="legend-dot" style="background:var(--color-domain);"></div>Domain</div>
  <div class="legend-item" onclick="setFilter('file')"><div class="legend-dot" style="background:var(--color-file);"></div>File</div>
  <div class="legend-item" onclick="setFilter('route')"><div class="legend-dot" style="background:var(--color-route);"></div>Route</div>
  <div class="legend-item" onclick="setFilter('table')"><div class="legend-dot" style="background:var(--color-table);"></div>Table</div>
  <div class="legend-item" onclick="setFilter('event')"><div class="legend-dot" style="background:var(--color-event);"></div>Event</div>
</div>

<!-- Viewport Controls -->
<div id="viewport-controls">
  <button class="vp-btn" onclick="zoomIn()" title="Zoom In">+</button>
  <button class="vp-btn" onclick="zoomOut()" title="Zoom Out">−</button>
  <button class="vp-btn" onclick="fitView()" title="Fit View">⛶</button>
  <button class="vp-btn" onclick="resetPan()" title="Center">◎</button>
</div>

<!-- Hover Tooltip -->
<div id="tooltip" class="glass-card">
  <div class="tt-type" id="tt-type">File</div>
  <div class="tt-title" id="tt-title">Filename</div>
  <div class="tt-summary" id="tt-summary">Summary</div>
</div>

<!-- Node Inspector Drawer -->
<div id="sidebar" class="glass-card">
  <div class="sb-header">
    <button class="sb-close" onclick="closeSidebar()">✕</button>
    <div style="display:flex;align-items:center;gap:6px;">
      <span class="tt-type" id="sb-type-pill" style="margin-bottom:0;">File</span>
      <span id="sb-metrics-badge" style="font-size:11px;color:var(--text-muted);"></span>
    </div>
    <div style="font-size:16px;font-weight:700;color:#fff;overflow:hidden;text-overflow:ellipsis;" id="sb-title">Node Title</div>
    <div style="font-size:11px;color:var(--text-muted);word-break:break-all;" id="sb-path">/path/to/file</div>
  </div>

  <div class="sb-body">
    <div>
      <div class="sb-section-title">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 14h-2v-2h2zm0-4h-2V7h2z"/></svg>
        Architectural Purpose
      </div>
      <div class="summary-card" id="sb-summary">
        No semantic summary available.
      </div>
    </div>

    <div id="sb-entities-group">
      <div class="sb-section-title">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
        Discovered Entities
      </div>
      <div class="entity-chip-grid" id="sb-entities"></div>
    </div>

    <div>
      <div class="sb-section-title">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
        Connections (<span id="sb-conn-count">0</span>)
      </div>
      <ul class="connection-list" id="sb-connections"></ul>
    </div>
  </div>
</div>

<!-- Feedback Modal -->
<div id="feedback-modal-backdrop" class="modal-backdrop" onclick="if(event.target===this)closeFeedbackModal()">
  <div class="feedback-modal">
    <div class="fb-header">
      <div class="fb-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#818cf8" stroke-width="2.2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <span>Feedback & Bug Report</span>
      </div>
      <button class="sb-close" onclick="closeFeedbackModal()" style="position:static;">✕</button>
    </div>

    <div class="fb-tabs" id="fb-tabs">
      <button class="fb-tab active" data-type="bug" onclick="selectFeedbackType('bug')">🐞 Bug Report</button>
      <button class="fb-tab" data-type="feature" onclick="selectFeedbackType('feature')">✨ Feature Request</button>
      <button class="fb-tab" data-type="feedback" onclick="selectFeedbackType('feedback')">💬 Feedback</button>
    </div>

    <div class="fb-body" id="fb-form-body">
      <div class="fb-field">
        <label for="fb-input-title">Summary</label>
        <input type="text" id="fb-input-title" placeholder="Brief summary of issue or idea...">
      </div>

      <div class="fb-field">
        <label for="fb-input-desc">Details & Behavior</label>
        <textarea id="fb-input-desc" rows="4" placeholder="What happened, steps to reproduce, or feature idea..."></textarea>
      </div>

      <div class="fb-diag-box">
        <label style="display:flex;align-items:flex-start;gap:7px;cursor:pointer;color:var(--text-secondary);">
          <input type="checkbox" id="fb-include-logs" checked style="margin-top:2px;">
          <span>Automatically attach system diagnostics & sanitized logs (saved locally to <code>feedback.jsonl</code>)</span>
        </label>
      </div>

      <div id="fb-result-container" style="display:none;"></div>
    </div>

    <div class="fb-footer" id="fb-footer">
      <button class="action-btn" onclick="closeFeedbackModal()">Cancel</button>
      <button class="action-btn fb-submit-btn" id="fb-submit-action" onclick="submitFeedback()">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="20 6 9 17 4 12"/></svg>
        Submit Report
      </button>
    </div>
  </div>
</div>

<script>
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const $ = id => document.getElementById(id);

let nodes = [], edges = [], nodeById = Object.create(null);
let dragging = null, dragOffX = 0, dragOffY = 0;
let pan = { x: 0, y: 0 }, zoom = 1, isPanning = false, lastMouse = null;
let hoveredNode = null, selectedNode = null;
let activeFilter = 'all', searchQuery = '';
let lastRevision = null, scanning = false, loadedOnce = false;

const COLOR_MAP = {
  domain: { fill: '#8b5cf6', stroke: '#a78bfa', aura: 'rgba(139, 92, 246, 0.22)', radius: 18 },
  file:   { fill: '#10b981', stroke: '#34d399', aura: 'rgba(16, 185, 129, 0.18)', radius: 11 },
};
const CHIP_ICON = { table: '\u{1F5C4}️', route: '⚡', event: '\u{1F4E1}', domain: '\u{1F310}' };

// ── rendering: draw only when something changed, never a 60 fps idle loop ──
let drawQueued = false;
function requestDraw() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => { drawQueued = false; draw(); });
}

function resize() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = window.innerWidth * dpr;
  canvas.height = window.innerHeight * dpr;
  canvas.style.width = window.innerWidth + 'px';
  canvas.style.height = window.innerHeight + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  requestDraw();
}
window.addEventListener('resize', resize);
resize();

// ── data ──
async function fetchJSON(path, opts, timeoutMs) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs || 10000);
  try {
    const res = await fetch(path, Object.assign({ signal: ctl.signal }, opts || {}));
    if (!res.ok) throw new Error('HTTP ' + res.status + ' for ' + path);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

function showLoadError(err) {
  $('loading').style.display = 'flex';
  $('loading-spinner').style.display = 'none';
  $('loading-msg').textContent = 'Could not connect to codebone: ' + (err && err.message ? err.message : err);
  $('loading-retry').style.display = 'inline-flex';
}

function showEmpty(text) {
  $('loading').style.display = 'flex';
  $('loading-spinner').style.display = 'none';
  $('loading-msg').textContent = text;
  $('loading-retry').style.display = 'none';
}

async function loadAll() {
  try {
    const [graph, status] = await Promise.all([fetchJSON('/codebone/graph'), fetchJSON('/codebone/status')]);
    updateHud(status, graph);
    if (!status.configured) { showEmpty('No project selected. Pick a folder from the codebone menu bar icon.'); loadedOnce = true; return; }
    if (!graph.nodes.length) { showEmpty(status.scanning || status.sniffing ? 'Indexing your project, files appear here as they are analysed...' : 'No indexable files found in this project.'); lastRevision = status.revision; return; }
    buildGraph(graph, !loadedOnce);
    lastRevision = status.revision;
    loadedOnce = true;
    $('loading').style.display = 'none';
  } catch (err) {
    console.error('Failed to load graph data:', err);
    if (!loadedOnce) showLoadError(err);
  }
}

function updateHud(status, graph) {
  const name = status.project ? status.project.split('/').filter(Boolean).pop() : 'No Project Selected';
  $('project-name-display').textContent = name;
  $('project-name-display').title = status.project || '';
  $('model-display').textContent = status.brain_provider === 'builtin'
    ? (status.brain_available ? 'Local Apple Silicon Metal (Qwen2.5)' : 'Local model not ready, using heuristics')
    : (status.brain_provider || 'Local AI');

  const badge = $('status-indicator');
  let label = 'Active & Watching';
  badge.className = 'status-badge';
  scanning = !!(status.scanning || status.sniffing);
  if (status.model_status) { label = 'Preparing model: ' + status.model_status; badge.className = 'status-badge sniffing'; }
  else if (status.scan_progress) { label = 'Indexing ' + status.scan_progress.pct + '%'; badge.className = 'status-badge sniffing'; }
  else if (scanning) { label = 'Sniffing & Indexing...'; badge.className = 'status-badge sniffing'; }
  $('status-text').textContent = label;
  checkMcpPing(status);
}

const MCP_GUIDE_URL = 'https://github.com/palusc/codebone#mcp-setup';
function openMcpGuide() { window.open(MCP_GUIDE_URL, '_blank', 'noopener,noreferrer'); }
function safeStorage(fn) { try { return fn(); } catch (_) { return null; } }
function dismissMcpPing(e) {
  if (e) e.stopPropagation();
  $('mcp-ping-banner').style.display = 'none';
  safeStorage(() => localStorage.setItem('codebone_mcp_ping_dismissed', String(Date.now())));
}
function checkMcpPing(status) {
  const banner = $('mcp-ping-banner');
  const dismissedAt = safeStorage(() => localStorage.getItem('codebone_mcp_ping_dismissed'));
  if (dismissedAt && (Date.now() - Number(dismissedAt) < 24 * 3600 * 1000)) { banner.style.display = 'none'; return; }
  const firstDays = (status && status.is_first_days !== undefined) ? status.is_first_days : true;
  banner.style.display = firstDays ? 'block' : 'none';
}

// ── graph model ──
function buildGraph(graph, fit) {
  const previous = nodeById;
  const files = graph.files || {};
  const cx = window.innerWidth / 2, cy = window.innerHeight / 2;
  const tables = new Set(), routes = new Set(), events = new Set();
  for (const path of graph.nodes) {
    const f = Object.prototype.hasOwnProperty.call(files, path) ? files[path] : {};
    (f.tables || []).forEach(t => tables.add(t));
    (f.routes || []).forEach(r => routes.add(r));
    (f.events || []).forEach(e => events.add(e));
  }

  // Hub nodes come from server-side modularity clustering over the shared-entity graph
  // (Storage.communities()), not a fixed bucket per domain keyword: files land in the same
  // cluster because the graph actually connects them, directly or through a chain of shared
  // tables/routes/events/domains. A community of exactly one file is just a regular node —
  // no hub for something with nothing to be a hub of.
  const communities = (graph.communities || []).filter(c => c.files.length > 1);

  const map = Object.create(null);
  communities.forEach((c, i) => {
    const id = 'domain:' + c.id, old = previous[id];
    const angle = (2 * Math.PI * i) / (communities.length || 1), r = Math.min(cx, cy) * 0.35;
    map[id] = {
      id, label: c.label, type: 'domain', radius: COLOR_MAP.domain.radius, vx: 0, vy: 0,
      x: old ? old.x : cx + Math.cos(angle) * r, y: old ? old.y : cy + Math.sin(angle) * r,
      data: { domains: [c.label], summary: 'Cluster of ' + c.files.length + ' files around ' + c.label + '.' },
    };
  });
  graph.nodes.forEach((path, i) => {
    const id = 'file:' + path, old = previous[id];
    const angle = (2 * Math.PI * i) / (graph.nodes.length || 1), r = Math.min(cx, cy) * 0.65;
    map[id] = {
      id, label: path.split('/').pop(), path, type: 'file', radius: COLOR_MAP.file.radius, vx: 0, vy: 0,
      x: old ? old.x : cx + Math.cos(angle) * r + (Math.random() - 0.5) * 60,
      y: old ? old.y : cy + Math.sin(angle) * r + (Math.random() - 0.5) * 60,
      data: Object.prototype.hasOwnProperty.call(files, path) ? files[path] : {},
    };
  });
  nodes = Object.values(map);
  nodeById = map;

  const list = [];
  const push = (from, to, type, entity) => {
    const a = map[from], b = map[to];
    if (a && b) list.push({ a, b, from, to, type, entity });
  };
  (graph.edges || []).forEach(e => push('file:' + e.from, 'file:' + e.to, e.type, e.entity));
  communities.forEach(c => c.files.forEach(p => push('domain:' + c.id, 'file:' + p, 'domain', c.label)));
  edges = list;

  $('count-all').textContent = nodes.length;
  $('count-files').textContent = graph.nodes.length;
  $('count-domains').textContent = communities.length;
  $('count-tables').textContent = tables.size;
  $('count-routes').textContent = routes.size;
  $('count-events').textContent = events.size;
  $('count-edges').textContent = edges.length;

  const fresh = nodes.filter(n => !previous[n.id]).length;
  if (fit || fresh > nodes.length / 2) {
    runForceLayout(nodes.length > 2500 ? 12 : nodes.length > 1200 ? 20 : nodes.length > 600 ? 40 : nodes.length > 300 ? 70 : 110);
    fitView();
  } else if (fresh) {
    runForceLayout(25);  // settle only the new nodes' neighbourhood; keep the user's view
  }
  if (selectedNode && nodeById[selectedNode.id]) selectNode(nodeById[selectedNode.id], true); else if (selectedNode) closeSidebar();
  hoveredNode = null;
  requestDraw();
}

// Repulsion uses a spatial grid (neighbouring cells only), so a tick costs O(N) instead of O(N^2).
function runForceLayout(ticks) {
  const CELL = 350;
  for (let t = 0; t < ticks; t++) {
    const grid = new Map();
    for (const n of nodes) {
      const key = Math.floor(n.x / CELL) + ',' + Math.floor(n.y / CELL);
      (grid.get(key) || grid.set(key, []).get(key)).push(n);
    }
    for (const a of nodes) {
      const gx = Math.floor(a.x / CELL), gy = Math.floor(a.y / CELL);
      for (let ox = -1; ox <= 1; ox++) for (let oy = -1; oy <= 1; oy++) {
        const cell = grid.get((gx + ox) + ',' + (gy + oy));
        if (!cell) continue;
        for (const b of cell) {
          if (a === b) continue;
          const dx = a.x - b.x, dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist > CELL) continue;
          const f = 1900 / (dist * dist);
          a.vx += (dx / dist) * f;
          a.vy += (dy / dist) * f;
        }
      }
      // weak pull to the centre keeps unconnected clusters from drifting apart
      a.vx += (window.innerWidth / 2 - a.x) * 0.004;
      a.vy += (window.innerHeight / 2 - a.y) * 0.004;
      a.vx *= 0.82;
      a.vy *= 0.82;
    }
    for (const e of edges) {
      const a = e.a, b = e.b;
      const dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = (dist - (e.type === 'domain' ? 120 : 85)) * 0.055;
      a.vx += (dx / dist) * f; a.vy += (dy / dist) * f;
      b.vx -= (dx / dist) * f; b.vy -= (dy / dist) * f;
    }
    for (const n of nodes) { n.x += n.vx; n.y += n.vy; }
  }
}

// ── drawing ──
function nodeMatches(n) {
  if (activeFilter !== 'all') {
    if (activeFilter === 'domain' || activeFilter === 'file') { if (n.type !== activeFilter) return false; }
    else { const list = n.data && n.data[activeFilter + 's']; if (n.type !== 'file' || !list || !list.length) return false; }
  }
  if (!searchQuery) return true;
  const d = n.data || {};
  const hay = [n.label, n.path || '', d.summary || '', (d.tables || []).join(' '), (d.routes || []).join(' '), (d.events || []).join(' ')].join(' ').toLowerCase();
  return hay.includes(searchQuery);
}

function draw() {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);
  drawGrid();

  const vx0 = -pan.x / zoom - 40, vy0 = -pan.y / zoom - 40;
  const vx1 = (window.innerWidth - pan.x) / zoom + 40, vy1 = (window.innerHeight - pan.y) / zoom + 40;
  const inView = n => n.x >= vx0 && n.x <= vx1 && n.y >= vy0 && n.y <= vy1;

  for (const e of edges) {
    const a = e.a, b = e.b;
    if (!inView(a) && !inView(b)) continue;
    const hot = (hoveredNode && (a === hoveredNode || b === hoveredNode)) || (selectedNode && (a === selectedNode || b === selectedNode));
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    if (e.type === 'domain') {
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = hot ? 'rgba(139, 92, 246, 0.85)' : 'rgba(139, 92, 246, 0.18)';
      ctx.lineWidth = hot ? 2 : 1;
    } else {
      ctx.setLineDash([]);
      ctx.strokeStyle = hot ? 'rgba(56, 189, 248, 0.8)' : 'rgba(100, 116, 139, 0.22)';
      ctx.lineWidth = hot ? 2 : 1.2;
    }
    ctx.stroke();
  }
  ctx.setLineDash([]);

  for (const n of nodes) {
    if (!inView(n)) continue;
    const cfg = COLOR_MAP[n.type] || COLOR_MAP.file;
    const isHovered = hoveredNode === n, isSelected = selectedNode === n;
    ctx.save();
    ctx.globalAlpha = nodeMatches(n) ? 1.0 : 0.12;
    if (isHovered || isSelected) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius + 8, 0, Math.PI * 2);
      ctx.fillStyle = cfg.aura;
      ctx.fill();
    }
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
    ctx.fillStyle = cfg.fill;
    ctx.fill();
    ctx.lineWidth = isSelected ? 2.5 : 1.5;
    ctx.strokeStyle = isSelected ? '#ffffff' : cfg.stroke;
    ctx.stroke();

    if (zoom > 0.4 || isHovered || isSelected) {
      const fontSize = Math.max(9, Math.min(12, 11 / zoom));
      ctx.font = '600 ' + fontSize + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      const text = n.label.length > 20 ? n.label.slice(0, 18) + '…' : n.label;
      const width = ctx.measureText(text).width;
      const pillY = n.y + n.radius + 6;
      ctx.fillStyle = 'rgba(10, 13, 20, 0.78)';
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(n.x - width / 2 - 4, pillY, width + 8, fontSize + 4, 4); else ctx.rect(n.x - width / 2 - 4, pillY, width + 8, fontSize + 4);
      ctx.fill();
      ctx.fillStyle = isSelected ? '#ffffff' : (isHovered ? '#38bdf8' : '#e2e8f0');
      ctx.fillText(text, n.x, pillY + fontSize - 1);
    }
    ctx.restore();
  }
  ctx.restore();
}

function drawGrid() {
  const size = 32;
  const startX = Math.floor((-pan.x / zoom) / size) * size;
  const endX = startX + (window.innerWidth / zoom) + size;
  const startY = Math.floor((-pan.y / zoom) / size) * size;
  const endY = startY + (window.innerHeight / zoom) + size;
  ctx.fillStyle = 'rgba(255, 255, 255, 0.035)';
  for (let x = startX; x < endX; x += size) for (let y = startY; y < endY; y += size) ctx.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
}

function screenToWorld(sx, sy) { return { x: (sx - pan.x) / zoom, y: (sy - pan.y) / zoom }; }
function hitTest(w) {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i];
    if (Math.hypot(n.x - w.x, n.y - w.y) < n.radius + 6) return n;
  }
  return null;
}

// ── interaction ──
canvas.addEventListener('mousedown', e => {
  const w = screenToWorld(e.clientX, e.clientY);
  const hit = hitTest(w);
  if (hit) {
    dragging = hit; dragOffX = hit.x - w.x; dragOffY = hit.y - w.y;
    selectNode(hit);
  } else {
    isPanning = true;
    lastMouse = { x: e.clientX, y: e.clientY };
  }
});

canvas.addEventListener('mousemove', e => {
  const w = screenToWorld(e.clientX, e.clientY);
  if (dragging) {
    dragging.x = w.x + dragOffX; dragging.y = w.y + dragOffY;
    requestDraw();
  } else if (isPanning && lastMouse) {
    pan.x += e.clientX - lastMouse.x; pan.y += e.clientY - lastMouse.y;
    lastMouse = { x: e.clientX, y: e.clientY };
    requestDraw();
  } else {
    const hit = hitTest(w);
    if (hit !== hoveredNode) { hoveredNode = hit; updateTooltip(e.clientX, e.clientY, hit); requestDraw(); }
    else if (hit) updateTooltip(e.clientX, e.clientY, hit);
  }
});

window.addEventListener('mouseup', () => { dragging = null; isPanning = false; });
canvas.addEventListener('mouseleave', () => { if (hoveredNode) { hoveredNode = null; updateTooltip(0, 0, null); requestDraw(); } });

canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.12 : 0.89;
  const next = Math.max(0.12, Math.min(4.5, zoom * factor));
  const applied = next / zoom;
  pan.x = e.clientX + (pan.x - e.clientX) * applied;
  pan.y = e.clientY + (pan.y - e.clientY) * applied;
  zoom = next;
  requestDraw();
}, { passive: false });

const tooltipEl = $('tooltip');
function updateTooltip(sx, sy, node) {
  if (!node) { tooltipEl.classList.remove('visible'); return; }
  const cfg = COLOR_MAP[node.type] || COLOR_MAP.file;
  const type = $('tt-type');
  type.textContent = node.type;
  type.style.background = cfg.aura;
  type.style.color = cfg.stroke;
  $('tt-title').textContent = node.label;
  const summary = (node.data && node.data.summary) || 'No summary available.';
  $('tt-summary').textContent = summary.length > 90 ? summary.slice(0, 88) + '…' : summary;
  tooltipEl.style.left = Math.min(window.innerWidth - 300, sx + 14) + 'px';
  tooltipEl.style.top = Math.min(window.innerHeight - 100, sy + 14) + 'px';
  tooltipEl.classList.add('visible');
}

// Built with DOM APIs and textContent only: names, paths and summaries come from analysed source files and
// must never be interpreted as HTML or script.
function mk(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

function selectNode(n, keepView) {
  selectedNode = n;
  $('sb-title').textContent = n.label;
  $('sb-path').textContent = n.path || n.id;
  const cfg = COLOR_MAP[n.type] || COLOR_MAP.file;
  const pill = $('sb-type-pill');
  pill.textContent = n.type;
  pill.style.background = cfg.aura;
  pill.style.color = cfg.stroke;
  $('sb-summary').textContent = (n.data && n.data.summary) || 'No architectural summary indexed for this module.';

  const chips = $('sb-entities');
  chips.replaceChildren();
  const d = n.data || {};
  let count = 0;
  for (const kind of ['table', 'route', 'event', 'domain']) {
    for (const name of (d[kind + 's'] || [])) {
      chips.appendChild(mk('span', 'entity-chip ' + kind, CHIP_ICON[kind] + ' ' + name));
      count++;
    }
  }
  if (!count) {
    const none = mk('span', '', 'No distinct sub-entities detected.');
    none.style.cssText = 'font-size:11px;color:var(--text-muted);';
    chips.appendChild(none);
  }

  const list = $('sb-connections');
  list.replaceChildren();
  const conn = edges.filter(e => e.a === n || e.b === n);
  $('sb-conn-count').textContent = conn.length;
  if (conn.length) {
    for (const e of conn.slice(0, 200)) {
      const other = e.a === n ? e.b : e.a;
      const li = mk('li', 'connection-item');
      li.appendChild(mk('span', '', other.label)).style.cssText = 'font-weight:600;color:#f8fafc;';
      const meta = mk('span', '', e.type + ': ' + e.entity);
      meta.style.cssText = 'font-size:10px;color:var(--text-muted);';
      li.appendChild(meta);
      li.addEventListener('click', () => focusNode(other.id));
      list.appendChild(li);
    }
  } else {
    const li = mk('li', '', 'No active connections.');
    li.style.cssText = 'font-size:11px;color:var(--text-muted);padding:4px 0;';
    list.appendChild(li);
  }
  $('sidebar').classList.add('open');
  requestDraw();
}

function closeSidebar() {
  $('sidebar').classList.remove('open');
  selectedNode = null;
  requestDraw();
}

function focusNode(id) {
  const target = nodeById[id];
  if (!target) return;
  selectNode(target);
  pan.x = (window.innerWidth / 2) - target.x * zoom;
  pan.y = (window.innerHeight / 2) - target.y * zoom;
  requestDraw();
}

function zoomIn() { zoom = Math.min(4.5, zoom * 1.25); requestDraw(); }
function zoomOut() { zoom = Math.max(0.12, zoom / 1.25); requestDraw(); }
function resetPan() { pan.x = window.innerWidth / 2; pan.y = window.innerHeight / 2; zoom = 1; requestDraw(); }
function fitView() {
  if (!nodes.length) return;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of nodes) { minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x); minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y); }
  const width = Math.max(100, maxX - minX + 160), height = Math.max(100, maxY - minY + 160);
  zoom = Math.max(0.12, Math.min(window.innerWidth / width, window.innerHeight / height, 1.2));
  pan.x = (window.innerWidth / 2) - ((minX + maxX) / 2) * zoom;
  pan.y = (window.innerHeight / 2) - ((minY + maxY) / 2) * zoom;
  requestDraw();
}

function setFilter(type) {
  activeFilter = type;
  document.querySelectorAll('.stat-pill[data-filter]').forEach(el => el.classList.toggle('active', el.dataset.filter === type));
  requestDraw();
}

const searchInput = $('search-input');
searchInput.addEventListener('input', e => { searchQuery = e.target.value.toLowerCase().trim(); requestDraw(); });
window.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement !== searchInput && document.activeElement.tagName !== 'TEXTAREA' && document.activeElement.tagName !== 'INPUT') {
    e.preventDefault();
    searchInput.focus();
  }
  if (e.key === 'Escape') { closeSidebar(); closeFeedbackModal(); searchInput.blur(); }
});

// ── live updates: poll the cheap status endpoint, reload the graph only when the index revision changed ──
let pollTimer = null;
async function poll() {
  pollTimer = null;
  if (document.visibilityState === 'visible' && loadedOnce !== 'error') {
    try {
      const status = await fetchJSON('/codebone/status', null, 5000);
      if (status.revision !== lastRevision) await loadAll(); else updateHud(status);
    } catch (_) { /* server busy or restarting: try again on the next tick */ }
  }
  pollTimer = setTimeout(poll, scanning ? 1500 : 5000);
}
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && pollTimer) { clearTimeout(pollTimer); poll(); }
});

async function triggerRescan() {
  const btn = $('rescan-btn');
  btn.disabled = true;
  btn.lastChild.textContent = ' Scanning...';
  try {
    await fetchJSON('/codebone/rescan', { method: 'POST' });
    scanning = true;
    if (pollTimer) { clearTimeout(pollTimer); poll(); }
  } catch (err) {
    console.error('Rescan trigger failed:', err);
  }
  setTimeout(() => { btn.disabled = false; btn.lastChild.textContent = ' Scan Project'; }, 3000);
}

// ── feedback ──
let currentFeedbackType = 'bug';
function openFeedbackModal() {
  $('feedback-modal-backdrop').classList.add('active');
  setTimeout(() => $('fb-input-title').focus(), 100);
}
function closeFeedbackModal() { $('feedback-modal-backdrop').classList.remove('active'); }
function selectFeedbackType(type) {
  currentFeedbackType = type;
  document.querySelectorAll('.fb-tab').forEach(t => t.classList.toggle('active', t.getAttribute('data-type') === type));
  $('fb-input-title').placeholder = type === 'bug' ? 'e.g. Server failed to bind port or watcher stalled'
    : type === 'feature' ? 'e.g. Export graph to SVG or Neo4j' : "e.g. Loving the live HUD, here's a thought...";
}

async function submitFeedback() {
  const title = $('fb-input-title').value.trim();
  const desc = $('fb-input-desc').value.trim();
  const btn = $('fb-submit-action');
  const result = $('fb-result-container');
  if (!title && !desc) { alert('Please enter a summary or details before submitting.'); return; }
  btn.disabled = true;
  btn.textContent = 'Submitting...';
  try {
    const data = await fetchJSON('/codebone/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: currentFeedbackType, title, description: desc, include_logs: $('fb-include-logs').checked }),
    });
    result.style.display = 'block';
    result.replaceChildren();
    const banner = mk('div', 'fb-result-banner');
    banner.appendChild(mk('div', '', '✓ Report Recorded Locally!')).style.cssText = 'font-weight:700;margin-bottom:4px;';
    banner.appendChild(mk('div', '', 'Saved to feedback.jsonl with system diagnostics and sanitized logs.')).style.cssText = 'font-size:11px;color:#e2e8f0;';
    if (data.github_url && /^https:\/\/github\.com\//.test(data.github_url)) {
      const link = mk('a', 'action-btn', 'Open Pre-filled GitHub Issue ↗');
      link.href = data.github_url; link.target = '_blank'; link.rel = 'noopener noreferrer';
      link.style.cssText = 'margin-top:10px;background:#10b981;border-color:rgba(16,185,129,0.4);display:inline-flex;text-decoration:none;font-weight:700;color:#fff;';
      banner.appendChild(link);
    }
    result.appendChild(banner);
    $('fb-input-title').value = '';
    $('fb-input-desc').value = '';
    btn.textContent = 'Submitted';
    setTimeout(() => { btn.disabled = false; btn.textContent = 'Submit Another'; }, 2000);
  } catch (err) {
    alert('Error submitting feedback: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Submit Report';
  }
}

loadAll().then(() => { pollTimer = setTimeout(poll, 3000); });
</script>
</body>
</html>"""


def build_live_graph_html(port: int) -> str:
    """Returns the self-contained graph page for the given local server port."""
    return _PAGE.replace("__PORT__", str(int(port)))
