"""Interactive HTML5 Canvas Knowledge Graph UI for codebone.
Crafted with modern dark-mode glassmorphism aesthetics, rich inspection panels, and physics simulation.
"""

def build_live_graph_html(port: int) -> str:
    """Returns a self-contained modern HTML5 canvas graph with rich architectural telemetry."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>codebone — Semantic Code Graph</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
  :root {{
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
  }}

  body {{
    background: var(--bg-dark);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    overflow: hidden;
    height: 100vh;
    width: 100vw;
    -webkit-font-smoothing: antialiased;
    user-select: none;
  }}

  #canvas {{
    display: block;
    width: 100%;
    height: 100%;
    cursor: grab;
    background: radial-gradient(ellipse at 50% 30%, #151d2f 0%, #0a0d14 100%);
  }}
  #canvas:active {{ cursor: grabbing; }}

  /* Top Navigation & Telemetry HUD */
  #hud-top {{
    position: fixed;
    top: 16px;
    left: 16px;
    z-index: 20;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 580px;
  }}

  .glass-card {{
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border-radius: 12px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4), 0 1px 1px rgba(255, 255, 255, 0.05);
  }}

  .hud-main {{
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}

  .brand-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }}

  .brand-title {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    letter-spacing: -0.3px;
  }}

  .status-badge {{
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
  }}
  .status-badge.sniffing {{
    background: rgba(14, 165, 233, 0.12);
    border-color: rgba(14, 165, 233, 0.25);
    color: #38bdf8;
  }}
  .pulse-dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 6px currentColor;
    animation: pulse 2s infinite ease-in-out;
  }}
  @keyframes pulse {{
    0%, 100% {{ transform: scale(0.9); opacity: 0.7; }}
    50% {{ transform: scale(1.3); opacity: 1; }}
  }}

  .project-meta {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-secondary);
  }}
  .project-name {{
    font-weight: 600;
    color: #f8fafc;
    background: rgba(255, 255, 255, 0.06);
    padding: 2px 7px;
    border-radius: 5px;
    max-width: 240px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}

  /* Stats Metric Bar */
  .metrics-bar {{
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    padding-top: 4px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
  }}

  .stat-pill {{
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
  }}
  .stat-pill:hover, .stat-pill.active {{
    background: rgba(255, 255, 255, 0.09);
    border-color: rgba(255, 255, 255, 0.18);
    color: #fff;
    transform: translateY(-1px);
  }}
  .stat-val {{
    font-weight: 700;
    color: #f1f5f9;
  }}

  /* Search & Controls */
  .search-row {{
    display: flex;
    gap: 8px;
    align-items: center;
  }}

  .search-box {{
    position: relative;
    flex: 1;
  }}
  .search-input {{
    width: 100%;
    padding: 7px 12px 7px 30px;
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    color: #fff;
    font-size: 12px;
    outline: none;
    transition: all 0.18s ease;
  }}
  .search-input:focus {{
    border-color: #6366f1;
    background: rgba(0, 0, 0, 0.55);
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
  }}
  .search-icon {{
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    width: 13px;
    height: 13px;
    color: var(--text-muted);
    pointer-events: none;
  }}

  .action-btn {{
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
  }}
  .action-btn:hover {{
    background: #2d3748;
    border-color: rgba(255, 255, 255, 0.22);
    transform: translateY(-1px);
  }}
  .action-btn:disabled {{
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }}

  /* Bottom Controls & Legend */
  #legend {{
    position: fixed;
    bottom: 20px;
    left: 20px;
    z-index: 20;
    display: flex;
    gap: 8px;
    padding: 8px 12px;
  }}

  .legend-item {{
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
  }}
  .legend-item:hover {{
    background: rgba(255, 255, 255, 0.05);
    color: #fff;
  }}
  .legend-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }}

  /* Viewport Controls */
  #viewport-controls {{
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 20;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .vp-btn {{
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
  }}
  .vp-btn:hover {{
    background: rgba(255, 255, 255, 0.12);
    color: #fff;
    transform: scale(1.05);
  }}

  /* MCP Setup Ping Card & Pulse Beacon */
  .mcp-ping-card {{
    padding: 10px 14px;
    background: linear-gradient(135deg, rgba(30, 41, 59, 0.92) 0%, rgba(15, 23, 42, 0.95) 100%);
    border: 1px solid rgba(129, 140, 248, 0.35);
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    box-shadow: 0 4px 20px rgba(99, 102, 241, 0.15), 0 1px 3px rgba(0, 0, 0, 0.4);
  }}
  .mcp-ping-card:hover {{
    transform: translateY(-1px);
    border-color: rgba(129, 140, 248, 0.65);
    background: linear-gradient(135deg, rgba(39, 51, 75, 0.96) 0%, rgba(17, 27, 50, 0.98) 100%);
    box-shadow: 0 6px 24px rgba(99, 102, 241, 0.25);
  }}
  .mcp-ping-content {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .mcp-ping-beacon {{
    position: relative;
    width: 14px;
    height: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }}
  .mcp-ping-core {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #818cf8;
    box-shadow: 0 0 8px #818cf8;
  }}
  .mcp-ping-ring {{
    position: absolute;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 2px solid #818cf8;
    opacity: 0.8;
    animation: beacon-ping 1.8s cubic-bezier(0, 0, 0.2, 1) infinite;
  }}
  @keyframes beacon-ping {{
    0% {{ transform: scale(0.6); opacity: 1; }}
    80%, 100% {{ transform: scale(2.2); opacity: 0; }}
  }}
  .mcp-ping-text {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}
  .mcp-ping-title {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -0.2px;
  }}
  .mcp-ping-sub {{
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 1px 6px;
    border-radius: 4px;
    background: rgba(129, 140, 248, 0.16);
    color: #a5b4fc;
    border: 1px solid rgba(129, 140, 248, 0.25);
  }}
  .mcp-ping-desc {{
    font-size: 11px;
    color: #94a3b8;
    line-height: 1.3;
  }}
  .mcp-ping-close {{
    background: none;
    border: none;
    color: #64748b;
    font-size: 14px;
    cursor: pointer;
    padding: 4px 6px;
    border-radius: 4px;
    transition: color 0.15s;
    line-height: 1;
  }}
  .mcp-ping-close:hover {{
    color: #f1f5f9;
    background: rgba(255, 255, 255, 0.08);
  }}
  /* Hover Tooltip */
  #tooltip {{
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
  }}
  #tooltip.visible {{
    opacity: 1;
    transform: translateY(0);
  }}
  .tt-title {{
    font-weight: 700;
    color: #fff;
    margin-bottom: 2px;
  }}
  .tt-type {{
    display: inline-block;
    font-size: 9.5px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 4px;
    margin-bottom: 4px;
    text-transform: uppercase;
  }}
  .tt-summary {{
    color: var(--text-secondary);
  }}

  /* Node Inspector Drawer */
  #sidebar {{
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
  }}
  #sidebar.open {{
    transform: translateX(0);
  }}

  .sb-header {{
    padding: 18px 20px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    display: flex;
    flex-direction: column;
    gap: 6px;
    position: relative;
  }}

  .sb-close {{
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
  }}
  .sb-close:hover {{
    background: rgba(255, 255, 255, 0.12);
    color: #fff;
  }}

  .sb-body {{
    padding: 18px 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
    flex: 1;
  }}

  .sb-section-title {{
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--text-muted);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .summary-card {{
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 12px 14px;
    font-size: 12.5px;
    line-height: 1.55;
    color: #e2e8f0;
  }}

  .entity-chip-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }}

  .entity-chip {{
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
  }}
  .entity-chip.table {{ border-color: rgba(245, 158, 11, 0.3); color: #fbbf24; }}
  .entity-chip.route {{ border-color: rgba(14, 165, 233, 0.3); color: #38bdf8; }}
  .entity-chip.event {{ border-color: rgba(244, 63, 94, 0.3); color: #fb7185; }}
  .entity-chip.domain {{ border-color: rgba(139, 92, 246, 0.3); color: #a78bfa; }}

  .connection-list {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}

  .connection-item {{
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
  }}
  .connection-item:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.15);
    transform: translateX(3px);
  }}

  /* Loading Overlay */
  #loading {{
    position: fixed;
    inset: 0;
    background: var(--bg-dark);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    flex-direction: column;
    gap: 16px;
  }}
  .loader-spinner {{
    width: 36px;
    height: 36px;
    border: 3px solid rgba(255, 255, 255, 0.08);
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

  /* Feedback & Bug Report Modal */
  .modal-backdrop {{
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
  }}
  .modal-backdrop.active {{
    opacity: 1;
    pointer-events: auto;
  }}
  .feedback-modal {{
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
  }}
  .modal-backdrop.active .feedback-modal {{
    transform: scale(1) translateY(0);
  }}
  .fb-header {{
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .fb-title {{
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .fb-tabs {{
    display: flex;
    gap: 6px;
    padding: 14px 20px 0;
  }}
  .fb-tab {{
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 11.5px;
    font-weight: 600;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s ease;
  }}
  .fb-tab:hover {{
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
  }}
  .fb-tab.active {{
    background: rgba(99, 102, 241, 0.18);
    border-color: rgba(99, 102, 241, 0.45);
    color: #818cf8;
  }}
  .fb-body {{
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .fb-field {{
    display: flex;
    flex-direction: column;
    gap: 5px;
  }}
  .fb-field label {{
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .fb-field input, .fb-field textarea {{
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 8px 12px;
    color: #fff;
    font-size: 12.5px;
    font-family: inherit;
    outline: none;
    transition: all 0.15s ease;
  }}
  .fb-field input:focus, .fb-field textarea:focus {{
    border-color: #6366f1;
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
  }}
  .fb-diag-box {{
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 6px;
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.4;
  }}
  .fb-footer {{
    padding: 14px 20px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    background: rgba(0, 0, 0, 0.2);
  }}
  .fb-submit-btn {{
    background: #4f46e5;
    border-color: rgba(99, 102, 241, 0.5);
  }}
  .fb-submit-btn:hover {{
    background: #4338ca;
  }}
  .fb-result-banner {{
    padding: 12px 14px;
    border-radius: 8px;
    font-size: 12px;
    line-height: 1.5;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: #34d399;
  }}
</style>
</head>
<body>

<div id="loading">
  <div class="loader-spinner"></div>
  <div style="color:var(--text-secondary);font-size:13px;font-weight:500;">Synthesizing semantic architecture…</div>
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
      <div class="stat-pill active" onclick="setFilter('all')">All <span class="stat-val" id="count-all">0</span></div>
      <div class="stat-pill" onclick="setFilter('domain')">Domains <span class="stat-val" id="count-domains" style="color:var(--color-domain)">0</span></div>
      <div class="stat-pill" onclick="setFilter('file')">Files <span class="stat-val" id="count-files" style="color:var(--color-file)">0</span></div>
      <div class="stat-pill" onclick="setFilter('table')">Tables <span class="stat-val" id="count-tables" style="color:var(--color-table)">0</span></div>
      <div class="stat-pill" onclick="setFilter('route')">Routes <span class="stat-val" id="count-routes" style="color:var(--color-route)">0</span></div>
      <div class="stat-pill" onclick="setFilter('event')">Events <span class="stat-val" id="count-events" style="color:var(--color-event)">0</span></div>
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
const PORT = {port};
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

let nodes = [], edges = [];
let dragging = null, dragOffX = 0, dragOffY = 0;
let pan = {{x: 0, y: 0}}, zoom = 1, isPanning = false, lastMouse = null;
let hoveredNode = null, selectedNode = null;
let activeFilter = 'all', searchQuery = '';
let telemetry = {{}};

const COLOR_MAP = {{
  domain: {{ fill: '#8b5cf6', stroke: '#a78bfa', aura: 'rgba(139, 92, 246, 0.22)', radius: 18 }},
  file:   {{ fill: '#10b981', stroke: '#34d399', aura: 'rgba(16, 185, 129, 0.18)', radius: 11 }},
  route:  {{ fill: '#0ea5e9', stroke: '#38bdf8', aura: 'rgba(14, 165, 233, 0.18)', radius: 10 }},
  table:  {{ fill: '#f59e0b', stroke: '#fbbf24', aura: 'rgba(245, 158, 11, 0.18)', radius: 10 }},
  event:  {{ fill: '#f43f5e', stroke: '#fb7185', aura: 'rgba(244, 63, 94, 0.18)', radius: 9 }}
}};

function resize() {{
  const dpr = window.devicePixelRatio || 1;
  canvas.width = window.innerWidth * dpr;
  canvas.height = window.innerHeight * dpr;
  canvas.style.width = window.innerWidth + 'px';
  canvas.style.height = window.innerHeight + 'px';
  ctx.scale(dpr, dpr);
}}
window.addEventListener('resize', resize);
resize();

async function fetchData() {{
  try {{
    const [graphRes, contextRes, statusRes] = await Promise.all([
      fetch('/codebone/graph').catch(() => fetch(`http://127.0.0.1:${{PORT}}/codebone/graph`)),
      fetch('/codebone/context?format=json').catch(() => fetch(`http://127.0.0.1:${{PORT}}/codebone/context?format=json`)),
      fetch('/codebone/status').catch(() => fetch(`http://127.0.0.1:${{PORT}}/codebone/status`))
    ]);

    if (!graphRes.ok || !contextRes.ok) {{
      throw new Error(`Data fetch failed (status: ${{graphRes.status}} / ${{contextRes.status}})`);
    }}

    const graphData = await graphRes.json();
    const contextData = await contextRes.json();
    if (statusRes && statusRes.ok) {{
      telemetry = await statusRes.json();
      updateHUDTelemetry(telemetry, contextData);
    }}

    buildGraph(graphData, contextData);
    document.getElementById('loading').style.display = 'none';
  }} catch (err) {{
    console.error("Failed to load graph data:", err);
    document.getElementById('loading').innerHTML = `
      <div style="color:#f43f5e;font-size:14px;font-weight:600;">Could not connect to codebone</div>
      <div style="color:var(--text-muted);font-size:12px;margin-top:4px;">${{err.message || err}}</div>
      <button class="action-btn" onclick="location.reload()" style="margin-top:12px;">Retry</button>
    `;
  }}
}}

function updateHUDTelemetry(status, ctxData) {{
  const pName = status.project ? status.project.split('/').filter(Boolean).pop() : 'No Project Selected';
  document.getElementById('project-name-display').textContent = pName;
  document.getElementById('project-name-display').title = status.project || '';

  const modelText = status.brain_provider === 'builtin'
    ? 'Local Apple Silicon Metal (Qwen2.5)'
    : (status.brain_provider || 'Local AI');
  document.getElementById('model-display').textContent = modelText;

  const statusBadge = document.getElementById('status-indicator');
  const statusLabel = document.getElementById('status-text');
  if (status.sniffing) {{
    statusBadge.className = 'status-badge sniffing';
    statusLabel.textContent = 'Sniffing & Indexing...';
  }} else {{
    statusBadge.className = 'status-badge';
    statusLabel.textContent = 'Active & Watching';
  }}

  // Update counts
  const entities = ctxData.entities || {{}};
  document.getElementById('count-files').textContent = ctxData.file_count || (ctxData.files ? ctxData.files.length : 0);
  document.getElementById('count-domains').textContent = (ctxData.domains || []).length;
  document.getElementById('count-tables').textContent = Object.keys(entities.tables || {{}}).length;
  document.getElementById('count-routes').textContent = Object.keys(entities.routes || {{}}).length;
  document.getElementById('count-events').textContent = Object.keys(entities.events || {{}}).length;

  checkMcpPing(status);
}}

const MCP_GUIDE_URL = "https://github.com/palusc/codebone#mcp-setup";

function openMcpGuide() {{
  window.open(MCP_GUIDE_URL, "_blank", "noopener,noreferrer");
}}

function dismissMcpPing(e) {{
  if (e) e.stopPropagation();
  const banner = document.getElementById("mcp-ping-banner");
  if (banner) banner.style.display = "none";
  localStorage.setItem("codebone_mcp_ping_dismissed", String(Date.now()));
}}

function checkMcpPing(statusData) {{
  const banner = document.getElementById("mcp-ping-banner");
  if (!banner) return;
  const dismissedAt = localStorage.getItem("codebone_mcp_ping_dismissed");
  if (dismissedAt && (Date.now() - Number(dismissedAt) < 24 * 3600 * 1000)) {{
    banner.style.display = "none";
    return;
  }}
  const isFirstDays = (statusData && statusData.is_first_days !== undefined) ? statusData.is_first_days : true;
  if (isFirstDays) {{
    banner.style.display = "block";
  }} else {{
    banner.style.display = "none";
  }}
}}

function buildGraph(graphData, ctxData) {{
  const nodeMap = {{}};
  const cx = window.innerWidth / 2, cy = window.innerHeight / 2;
  const entityIndex = ctxData.entities || {{}};
  const fileMetaMap = {{}};

  (ctxData.files || []).forEach(f => {{
    fileMetaMap[f.path] = f;
  }});

  // 1. Create Domain Nodes (Core clusters)
  const domains = ctxData.domains || Object.keys(entityIndex.domains || {{}});
  domains.forEach((d, i) => {{
    const angle = (2 * Math.PI * i) / (domains.length || 1);
    const r = Math.min(cx, cy) * 0.35;
    const id = 'domain:' + d;
    nodeMap[id] = {{
      id,
      label: d,
      type: 'domain',
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
      vx: 0, vy: 0,
      radius: COLOR_MAP.domain.radius,
      data: {{
        domains: [d],
        files: (entityIndex.domains && entityIndex.domains[d]) || [],
        summary: `Overarching architectural domain encompassing ${{((entityIndex.domains && entityIndex.domains[d]) || []).length}} active project modules.`
      }}
    }};
  }});

  // 2. Create File Nodes
  const fileList = graphData.nodes || (ctxData.files || []).map(f => f.path);
  fileList.forEach((path, i) => {{
    const meta = fileMetaMap[path] || {{}};
    const id = 'file:' + path;
    const angle = (2 * Math.PI * i) / (fileList.length || 1);
    const r = Math.min(cx, cy) * 0.65;
    const fileName = path.split('/').pop();

    nodeMap[id] = {{
      id,
      label: fileName,
      path: path,
      type: 'file',
      x: cx + Math.cos(angle) * r + (Math.random() - 0.5) * 60,
      y: cy + Math.sin(angle) * r + (Math.random() - 0.5) * 60,
      vx: 0, vy: 0,
      radius: COLOR_MAP.file.radius,
      data: meta
    }};
  }});

  nodes = Object.values(nodeMap);

  // 3. Edges
  edges = (graphData.edges || []).map(e => ({{
    from: 'file:' + e.from,
    to: 'file:' + e.to,
    type: e.type,
    entity: e.entity
  }}));

  // Domain -> File associations
  Object.entries(entityIndex.domains || {{}}).forEach(([d, files]) => {{
    files.forEach(f => {{
      edges.push({{
        from: 'domain:' + d,
        to: 'file:' + f,
        type: 'domain',
        entity: d
      }});
    }});
  }});

  document.getElementById('count-all').textContent = nodes.length;
  document.getElementById('count-edges').textContent = edges.length;

  runForceLayout(110);
  fitView();
}}

function runForceLayout(ticks) {{
  for (let t = 0; t < ticks; t++) {{
    // Repulsion
    nodes.forEach(a => {{
      nodes.forEach(b => {{
        if (a === b) return;
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        if (dist > 350) return;
        const f = 1900 / (dist * dist);
        a.vx += (dx / dist) * f;
        a.vy += (dy / dist) * f;
      }});
      a.vx *= 0.82;
      a.vy *= 0.82;
    }});

    // Spring attraction along edges
    edges.forEach(e => {{
      const a = nodes.find(n => n.id === e.from);
      const b = nodes.find(n => n.id === e.to);
      if (!a || !b) return;
      const dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const ideal = e.type === 'domain' ? 120 : 85;
      const f = (dist - ideal) * 0.055;
      a.vx += (dx / dist) * f;
      a.vy += (dy / dist) * f;
      b.vx -= (dx / dist) * f;
      b.vy -= (dy / dist) * f;
    }});

    nodes.forEach(n => {{
      n.x += n.vx;
      n.y += n.vy;
    }});
  }}
}}

// Drawing & Canvas Loop
function draw() {{
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // 1. Draw subtle background dot grid
  drawGrid();

  // 2. Draw Edges
  edges.forEach(e => {{
    const a = nodes.find(n => n.id === e.from);
    const b = nodes.find(n => n.id === e.to);
    if (!a || !b) return;

    const isHighlighted = (hoveredNode && (a.id === hoveredNode.id || b.id === hoveredNode.id)) ||
                          (selectedNode && (a.id === selectedNode.id || b.id === selectedNode.id));

    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);

    if (e.type === 'domain') {{
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = isHighlighted ? 'rgba(139, 92, 246, 0.85)' : 'rgba(139, 92, 246, 0.18)';
      ctx.lineWidth = isHighlighted ? 2 : 1;
    }} else {{
      ctx.setLineDash([]);
      ctx.strokeStyle = isHighlighted ? 'rgba(56, 189, 248, 0.8)' : 'rgba(100, 116, 139, 0.22)';
      ctx.lineWidth = isHighlighted ? 2 : 1.2;
    }}
    ctx.stroke();
    ctx.setLineDash([]);
  }});

  // 3. Draw Nodes
  nodes.forEach(n => {{
    const cfg = COLOR_MAP[n.type] || COLOR_MAP.file;
    const isHovered = (hoveredNode && hoveredNode.id === n.id);
    const isSelected = (selectedNode && selectedNode.id === n.id);
    const matchesFilter = (activeFilter === 'all' || n.type === activeFilter);
    const matchesSearch = !searchQuery || n.label.toLowerCase().includes(searchQuery) ||
                          (n.path && n.path.toLowerCase().includes(searchQuery)) ||
                          (n.data && n.data.summary && n.data.summary.toLowerCase().includes(searchQuery));

    const alpha = (matchesFilter && matchesSearch) ? 1.0 : 0.12;

    ctx.save();
    ctx.globalAlpha = alpha;

    // Subtle soft aura on hover/select
    if (isHovered || isSelected) {{
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius + 8, 0, Math.PI * 2);
      ctx.fillStyle = cfg.aura;
      ctx.fill();
    }}

    // Node body
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
    ctx.fillStyle = cfg.fill;
    ctx.fill();

    // Node sleek border ring
    ctx.lineWidth = isSelected ? 2.5 : 1.5;
    ctx.strokeStyle = isSelected ? '#ffffff' : cfg.stroke;
    ctx.stroke();

    // Labels
    if (zoom > 0.4 || isHovered || isSelected) {{
      const fontSize = Math.max(9, Math.min(12, 11 / zoom));
      ctx.font = `600 ${{fontSize}}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
      ctx.textAlign = 'center';

      // Label background pill for ultra readability
      const labelText = n.label.length > 20 ? n.label.slice(0, 18) + '…' : n.label;
      const textMetrics = ctx.measureText(labelText);
      const textWidth = textMetrics.width;
      const pillY = n.y + n.radius + 6;

      ctx.fillStyle = 'rgba(10, 13, 20, 0.78)';
      ctx.beginPath();
      ctx.roundRect(n.x - textWidth / 2 - 4, pillY, textWidth + 8, fontSize + 4, 4);
      ctx.fill();

      ctx.fillStyle = isSelected ? '#ffffff' : (isHovered ? '#38bdf8' : '#e2e8f0');
      ctx.fillText(labelText, n.x, pillY + fontSize - 1);
    }}

    ctx.restore();
  }});

  ctx.restore();
  requestAnimationFrame(draw);
}}

function drawGrid() {{
  const gridSize = 32;
  const startX = Math.floor((-pan.x / zoom) / gridSize) * gridSize;
  const endX = startX + (window.innerWidth / zoom) + gridSize;
  const startY = Math.floor((-pan.y / zoom) / gridSize) * gridSize;
  const endY = startY + (window.innerHeight / zoom) + gridSize;

  ctx.fillStyle = 'rgba(255, 255, 255, 0.035)';
  for (let x = startX; x < endX; x += gridSize) {{
    for (let y = startY; y < endY; y += gridSize) {{
      ctx.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
    }}
  }}
}}

// Coordinate transforms
function screenToWorld(sx, sy) {{
  return {{ x: (sx - pan.x) / zoom, y: (sy - pan.y) / zoom }};
}}

// Mouse & Pan / Zoom Interaction
canvas.addEventListener('mousedown', e => {{
  const w = screenToWorld(e.clientX, e.clientY);
  const hit = nodes.find(n => Math.hypot(n.x - w.x, n.y - w.y) < n.radius + 6);
  if (hit) {{
    dragging = hit;
    dragOffX = hit.x - w.x;
    dragOffY = hit.y - w.y;
    selectNode(hit);
  }} else {{
    isPanning = true;
    lastMouse = {{ x: e.clientX, y: e.clientY }};
  }}
}});

canvas.addEventListener('mousemove', e => {{
  const w = screenToWorld(e.clientX, e.clientY);

  if (dragging) {{
    dragging.x = w.x + dragOffX;
    dragging.y = w.y + dragOffY;
  }} else if (isPanning && lastMouse) {{
    pan.x += e.clientX - lastMouse.x;
    pan.y += e.clientY - lastMouse.y;
    lastMouse = {{ x: e.clientX, y: e.clientY }};
  }} else {{
    // Hover detection
    const hit = nodes.find(n => Math.hypot(n.x - w.x, n.y - w.y) < n.radius + 6);
    if (hit !== hoveredNode) {{
      hoveredNode = hit;
      updateTooltip(e.clientX, e.clientY, hit);
    }} else if (hit) {{
      updateTooltip(e.clientX, e.clientY, hit);
    }}
  }}
}});

window.addEventListener('mouseup', () => {{
  dragging = null;
  isPanning = false;
}});

canvas.addEventListener('wheel', e => {{
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.12 : 0.89;
  const cx = e.clientX, cy = e.clientY;
  pan.x = cx + (pan.x - cx) * factor;
  pan.y = cy + (pan.y - cy) * factor;
  zoom = Math.max(0.12, Math.min(4.5, zoom * factor));
}}, {{ passive: false }});

// Tooltip Logic
const tooltipEl = document.getElementById('tooltip');
function updateTooltip(sx, sy, node) {{
  if (!node) {{
    tooltipEl.classList.remove('visible');
    return;
  }}

  const ttType = document.getElementById('tt-type');
  const ttTitle = document.getElementById('tt-title');
  const ttSummary = document.getElementById('tt-summary');

  ttType.textContent = node.type;
  ttType.style.background = (COLOR_MAP[node.type] || COLOR_MAP.file).aura;
  ttType.style.color = (COLOR_MAP[node.type] || COLOR_MAP.file).stroke;
  ttTitle.textContent = node.label;

  const rawSummary = (node.data && node.data.summary) || 'No summary available.';
  ttSummary.textContent = rawSummary.length > 90 ? rawSummary.slice(0, 88) + '…' : rawSummary;

  tooltipEl.style.left = Math.min(window.innerWidth - 300, sx + 14) + 'px';
  tooltipEl.style.top = Math.min(window.innerHeight - 100, sy + 14) + 'px';
  tooltipEl.classList.add('visible');
}}

// Node Inspector Sidebar
function selectNode(n) {{
  selectedNode = n;
  const sidebar = document.getElementById('sidebar');

  document.getElementById('sb-title').textContent = n.label;
  document.getElementById('sb-path').textContent = n.path || n.id;

  const pill = document.getElementById('sb-type-pill');
  pill.textContent = n.type;
  pill.style.background = (COLOR_MAP[n.type] || COLOR_MAP.file).aura;
  pill.style.color = (COLOR_MAP[n.type] || COLOR_MAP.file).stroke;

  // AI Summary
  const summaryEl = document.getElementById('sb-summary');
  summaryEl.textContent = (n.data && n.data.summary) || 'No architectural summary indexed for this module.';

  // Discovered Entities
  const entitiesEl = document.getElementById('sb-entities');
  entitiesEl.innerHTML = '';
  const d = n.data || {{}};

  let entityCount = 0;
  (d.tables || []).forEach(t => {{
    entityCount++;
    entitiesEl.innerHTML += `<span class="entity-chip table">🗄️ ${{t}}</span>`;
  }});
  (d.routes || []).forEach(r => {{
    entityCount++;
    entitiesEl.innerHTML += `<span class="entity-chip route">⚡ ${{r}}</span>`;
  }});
  (d.events || []).forEach(ev => {{
    entityCount++;
    entitiesEl.innerHTML += `<span class="entity-chip event">📡 ${{ev}}</span>`;
  }});
  (d.domains || []).forEach(dm => {{
    entityCount++;
    entitiesEl.innerHTML += `<span class="entity-chip domain">🌐 ${{dm}}</span>`;
  }});

  if (entityCount === 0) {{
    entitiesEl.innerHTML = '<span style="font-size:11px;color:var(--text-muted);">No distinct sub-entities detected.</span>';
  }}

  // Connections
  const connList = document.getElementById('sb-connections');
  const conn = edges.filter(e => e.from === n.id || e.to === n.id);
  document.getElementById('sb-conn-count').textContent = conn.length;

  if (conn.length > 0) {{
    connList.innerHTML = conn.map(e => {{
      const targetId = (e.from === n.id) ? e.to : e.from;
      const targetNode = nodes.find(x => x.id === targetId);
      const targetLabel = targetNode ? targetNode.label : targetId.split(':').pop();
      return `
        <li class="connection-item" onclick="focusNode('${{targetId}}')">
          <span style="font-weight:600;color:#f8fafc;">${{targetLabel}}</span>
          <span style="font-size:10px;color:var(--text-muted);">${{e.type}}: ${{e.entity}}</span>
        </li>
      `;
    }}).join('');
  }} else {{
    connList.innerHTML = '<li style="font-size:11px;color:var(--text-muted);padding:4px 0;">No active connections.</li>';
  }}

  sidebar.classList.add('open');
}}

function closeSidebar() {{
  document.getElementById('sidebar').classList.remove('open');
  selectedNode = null;
}}

function focusNode(id) {{
  const target = nodes.find(n => n.id === id);
  if (!target) return;
  selectNode(target);
  pan.x = (window.innerWidth / 2) - target.x * zoom;
  pan.y = (window.innerHeight / 2) - target.y * zoom;
}}

// Viewport Actions
function zoomIn() {{ zoom = Math.min(4.5, zoom * 1.25); }}
function zoomOut() {{ zoom = Math.max(0.12, zoom / 1.25); }}
function resetPan() {{
  pan.x = window.innerWidth / 2;
  pan.y = window.innerHeight / 2;
  zoom = 1;
}}
function fitView() {{
  if (!nodes.length) return;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  nodes.forEach(n => {{
    minX = Math.min(minX, n.x);
    maxX = Math.max(maxX, n.x);
    minY = Math.min(minY, n.y);
    maxY = Math.max(maxY, n.y);
  }});

  const width = Math.max(100, maxX - minX + 160);
  const height = Math.max(100, maxY - minY + 160);
  zoom = Math.min(window.innerWidth / width, window.innerHeight / height, 1.2);
  pan.x = (window.innerWidth / 2) - ((minX + maxX) / 2) * zoom;
  pan.y = (window.innerHeight / 2) - ((minY + maxY) / 2) * zoom;
}}

function setFilter(type) {{
  activeFilter = type;
  document.querySelectorAll('.stat-pill').forEach(el => el.classList.remove('active'));
  const targetPill = Array.from(document.querySelectorAll('.stat-pill')).find(el => el.textContent.toLowerCase().includes(type));
  if (targetPill) targetPill.classList.add('active');
}}

// Live Search
const searchInput = document.getElementById('search-input');
searchInput.addEventListener('input', e => {{
  searchQuery = e.target.value.toLowerCase().trim();
}});
window.addEventListener('keydown', e => {{
  if (e.key === '/' && document.activeElement !== searchInput) {{
    e.preventDefault();
    searchInput.focus();
  }}
  if (e.key === 'Escape') {{
    closeSidebar();
    closeFeedbackModal();
    searchInput.blur();
  }}
}});

// Auto-refresh periodically
setInterval(async () => {{
  try {{
    const r = await fetch('/codebone/graph').catch(() => fetch(`http://127.0.0.1:${{PORT}}/codebone/graph`));
    if (!r.ok) return;
    const d = await r.json();
    const curFileCount = nodes.filter(n => n.type === 'file').length;
    if (d.nodes && d.nodes.length !== curFileCount) {{
      const r2 = await fetch('/codebone/context?format=json').catch(() => fetch(`http://127.0.0.1:${{PORT}}/codebone/context?format=json`));
      if (!r2.ok) return;
      buildGraph(d, await r2.json());
    }}
  }} catch (_) {{}}
}}, 6000);

// Rescan trigger
async function triggerRescan() {{
  const btn = document.getElementById('rescan-btn');
  if (!btn) return;
  btn.disabled = true;
  btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation:spin 1s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Scanning...`;

  try {{
    await fetch('/codebone/rescan', {{ method: 'POST' }});
    setTimeout(fetchData, 2000);
  }} catch (err) {{
    console.error('Rescan trigger failed:', err);
  }} finally {{
    setTimeout(() => {{
      btn.disabled = false;
      btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg> Scan Project`;
    }}, 4000);
  }}
}}

// Feedback Modal Controls
let currentFeedbackType = 'bug';

function openFeedbackModal() {{
  const bd = document.getElementById('feedback-modal-backdrop');
  if (bd) {{
    bd.classList.add('active');
    setTimeout(() => {{
      const titleInput = document.getElementById('fb-input-title');
      if (titleInput) titleInput.focus();
    }}, 100);
  }}
}}

function closeFeedbackModal() {{
  const bd = document.getElementById('feedback-modal-backdrop');
  if (bd) bd.classList.remove('active');
}}

function selectFeedbackType(type) {{
  currentFeedbackType = type;
  document.querySelectorAll('.fb-tab').forEach(t => {{
    t.classList.toggle('active', t.getAttribute('data-type') === type);
  }});
  const titleInput = document.getElementById('fb-input-title');
  if (!titleInput) return;
  if (type === 'bug') titleInput.placeholder = "e.g. Server failed to bind port or watcher stalled";
  else if (type === 'feature') titleInput.placeholder = "e.g. Export graph to SVG or Neo4j";
  else titleInput.placeholder = "e.g. Loving the live HUD, here's a thought...";
}}

async function submitFeedback() {{
  const title = document.getElementById('fb-input-title').value.trim();
  const desc = document.getElementById('fb-input-desc').value.trim();
  const includeLogs = document.getElementById('fb-include-logs').checked;
  const btn = document.getElementById('fb-submit-action');
  const resContainer = document.getElementById('fb-result-container');

  if (!title && !desc) {{
    alert('Please enter a summary or details before submitting.');
    return;
  }}

  btn.disabled = true;
  btn.innerHTML = 'Submitting...';

  try {{
    const res = await fetch('/codebone/feedback', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        type: currentFeedbackType,
        title: title,
        description: desc,
        include_logs: includeLogs
      }})
    }}).catch(() => fetch(`http://127.0.0.1:${{PORT}}/codebone/feedback`, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        type: currentFeedbackType,
        title: title,
        description: desc,
        include_logs: includeLogs
      }})
    }}));

    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();

    resContainer.style.display = 'block';
    let ghBtn = '';
    if (data.github_url) {{
      ghBtn = '<div style="margin-top:10px;"><a href="' + data.github_url + '" target="_blank" class="action-btn" style="background:#10b981;border-color:rgba(16,185,129,0.4);display:inline-flex;text-decoration:none;font-weight:700;color:#fff;">Open Pre-filled GitHub Issue ↗</a></div>';
    }}
    resContainer.innerHTML = '<div class="fb-result-banner"><div style="font-weight:700;margin-bottom:4px;">✓ Report Recorded Locally!</div><div style="font-size:11px;color:#e2e8f0;">Saved to <code>feedback.jsonl</code> with system diagnostics and sanitized logs.</div>' + ghBtn + '</div>';

    document.getElementById('fb-input-title').value = '';
    document.getElementById('fb-input-desc').value = '';
    btn.innerHTML = 'Submitted';
    setTimeout(() => {{
      btn.disabled = false;
      btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="20 6 9 17 4 12"/></svg> Submit Another`;
    }}, 2000);
  }} catch (err) {{
    alert('Error submitting feedback: ' + err.message);
    btn.disabled = false;
    btn.innerHTML = 'Submit Report';
  }}
}}

fetchData();
draw();
</script>
</body>
</html>"""
