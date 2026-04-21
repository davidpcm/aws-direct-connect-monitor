"""Interactive HTML Dashboard Generator for AWS Direct Connect Monitor.

Generates a self-contained HTML dashboard with:
- Connectivity topology with SVG icons (on-prem, DX location, AWS cloud, VPC)
- Connection health cards with state indicators
- BGP status and prefix monitoring
- Throughput and packet rate charts (Chart.js)
- Optical signal level gauges
- Error tracking
- Virtual interface metrics
"""

import json
from datetime import datetime, timezone


def _status_color(state: str) -> str:
    """Return CSS color for a given state."""
    s = (state or "").lower()
    if s in ("available", "up", "1", "1.0", "healthy"):
        return "#10b981"  # green
    if s in ("down", "0", "0.0", "critical", "deleted"):
        return "#ef4444"  # red
    if s in ("degraded", "warning", "pending", "confirming"):
        return "#f59e0b"  # amber
    return "#6b7280"  # gray


def _status_icon(state: str) -> str:
    """Return status emoji for a given state."""
    s = (state or "").lower()
    if s in ("available", "up", "1", "1.0", "healthy"):
        return "&#x2705;"  # green check
    if s in ("down", "0", "0.0", "critical", "deleted"):
        return "&#x274C;"  # red X
    if s in ("degraded", "warning", "pending"):
        return "&#x26A0;"  # warning
    return "&#x2753;"  # question


def _safe_vals(series: list) -> list:
    """Extract numeric values from a metric series."""
    return [dp.get("value", 0) for dp in series if "value" in dp and "error" not in dp]


def _safe_labels(series: list) -> list:
    """Extract timestamp labels from a metric series."""
    labels = []
    for dp in series:
        ts = dp.get("timestamp", "")
        if ts and "error" not in dp:
            try:
                dt = datetime.fromisoformat(ts)
                labels.append(dt.strftime("%H:%M"))
            except Exception:
                labels.append(ts[:16])
    return labels


def generate_dashboard_html(
    connections: list,
    vifs: list,
    gateways: list,
    lags: list,
    conn_metrics: dict,
    vif_metrics: dict,
    hours_back: int,
    period: int,
    account_id: str,
    region: str,
) -> str:
    """Generate the complete HTML dashboard."""

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build topology data
    topology_nodes = _build_topology(connections, vifs, gateways, lags)

    # Build connection cards HTML
    conn_cards = _build_connection_cards(connections, conn_metrics, vif_metrics)

    # Build VIF cards HTML
    vif_cards = _build_vif_cards(vifs, vif_metrics)

    # Build chart data
    chart_scripts = _build_chart_scripts(connections, vifs, conn_metrics, vif_metrics)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AWS Direct Connect Monitor — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #f1f5f9; --text2: #94a3b8; --accent: #3b82f6;
    --green: #10b981; --red: #ef4444; --amber: #f59e0b; --purple: #8b5cf6;
    --cyan: #06b6d4; --orange: #f97316;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
.header {{ background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); padding: 24px 32px; border-bottom: 1px solid var(--surface2); display: flex; align-items: center; gap: 16px; }}
.header svg {{ width: 40px; height: 40px; }}
.header h1 {{ font-size: 1.5rem; font-weight: 600; }}
.header .meta {{ margin-left: auto; text-align: right; color: var(--text2); font-size: 0.85rem; }}
.container {{ max-width: 1600px; margin: 0 auto; padding: 24px; }}
.section {{ margin-bottom: 32px; }}
.section-title {{ font-size: 1.2rem; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--surface2); }}
.section-title .icon {{ font-size: 1.4rem; }}

/* Topology */
.topology {{ background: var(--surface); border-radius: 12px; padding: 24px; margin-bottom: 32px; overflow-x: auto; }}
.topo-row {{ display: flex; align-items: center; justify-content: center; gap: 0; min-width: 900px; flex-wrap: nowrap; }}
.topo-node {{ display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 140px; padding: 16px 12px; }}
.topo-node .node-icon {{ width: 64px; height: 64px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 28px; position: relative; }}
.topo-node .node-label {{ font-size: 0.75rem; color: var(--text2); text-align: center; max-width: 130px; word-wrap: break-word; }}
.topo-node .node-name {{ font-size: 0.85rem; font-weight: 600; text-align: center; }}
.topo-node .node-status {{ font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; font-weight: 600; }}
.topo-link {{ display: flex; align-items: center; min-width: 60px; }}
.topo-link .link-line {{ height: 3px; flex: 1; min-width: 40px; border-radius: 2px; position: relative; }}
.topo-link .link-line.up {{ background: var(--green); box-shadow: 0 0 8px rgba(16,185,129,0.4); }}
.topo-link .link-line.down {{ background: var(--red); box-shadow: 0 0 8px rgba(239,68,68,0.4); }}
.topo-link .link-line.unknown {{ background: var(--surface2); }}
.topo-link .link-arrow {{ color: var(--text2); font-size: 1.2rem; }}

/* Cards grid */
.cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 16px; }}
.card {{ background: var(--surface); border-radius: 12px; padding: 20px; border: 1px solid var(--surface2); transition: border-color 0.2s; }}
.card:hover {{ border-color: var(--accent); }}
.card-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
.card-header .status-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
.card-header .card-title {{ font-weight: 600; font-size: 1rem; }}
.card-header .card-id {{ color: var(--text2); font-size: 0.8rem; margin-left: auto; font-family: monospace; }}
.card-body {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.metric {{ padding: 8px; background: var(--bg); border-radius: 8px; }}
.metric .metric-label {{ font-size: 0.7rem; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; }}
.metric .metric-value {{ font-size: 1.1rem; font-weight: 700; margin-top: 2px; }}
.metric .metric-unit {{ font-size: 0.7rem; color: var(--text2); }}
.metric.full {{ grid-column: 1 / -1; }}

/* KPI row */
.kpi-row {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.kpi {{ background: var(--surface); border-radius: 12px; padding: 16px 20px; border-left: 4px solid var(--accent); }}
.kpi .kpi-label {{ font-size: 0.75rem; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; }}
.kpi .kpi-value {{ font-size: 1.8rem; font-weight: 700; margin-top: 4px; }}
.kpi .kpi-sub {{ font-size: 0.75rem; color: var(--text2); }}

/* Charts */
.chart-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr)); gap: 16px; }}
.chart-box {{ background: var(--surface); border-radius: 12px; padding: 20px; border: 1px solid var(--surface2); }}
.chart-box h3 {{ font-size: 0.95rem; margin-bottom: 12px; color: var(--text2); }}
.chart-box canvas {{ max-height: 280px; }}

/* Alerts */
.alerts {{ background: var(--surface); border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
.alert-item {{ padding: 8px 12px; border-radius: 8px; margin-bottom: 6px; font-size: 0.85rem; display: flex; align-items: center; gap: 8px; }}
.alert-item.critical {{ background: rgba(239,68,68,0.15); border-left: 3px solid var(--red); }}
.alert-item.warning {{ background: rgba(245,158,11,0.15); border-left: 3px solid var(--amber); }}
.alert-item.ok {{ background: rgba(16,185,129,0.1); border-left: 3px solid var(--green); }}

/* BGP table */
.bgp-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
.bgp-table th {{ text-align: left; padding: 8px 12px; background: var(--bg); color: var(--text2); font-weight: 600; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px; }}
.bgp-table td {{ padding: 8px 12px; border-bottom: 1px solid var(--surface2); }}
.bgp-table tr:hover td {{ background: var(--bg); }}

/* Responsive */
@media (max-width: 768px) {{
    .cards {{ grid-template-columns: 1fr; }}
    .chart-grid {{ grid-template-columns: 1fr; }}
    .kpi-row {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>

<div class="header">
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="40" height="40" rx="8" fill="#3b82f6"/>
        <path d="M10 20h6l3-8 4 16 3-8h4" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <div>
        <h1>AWS Direct Connect Monitor</h1>
        <div style="color:var(--text2);font-size:0.85rem;">Near Real-Time Connectivity Dashboard</div>
    </div>
    <div class="meta">
        <div>Generated: {now}</div>
        <div>Account: {account_id or 'N/A'} &bull; Region: {region}</div>
        <div>Window: {hours_back}h &bull; Period: {period}s</div>
    </div>
</div>

<div class="container">

    <!-- KPI Summary -->
    {_build_kpi_section(connections, vifs, conn_metrics, vif_metrics)}

    <!-- Alerts -->
    {_build_alerts_section(connections, vifs, conn_metrics, vif_metrics)}

    <!-- Topology -->
    <div class="section">
        <div class="section-title"><span class="icon">🗺️</span> Connectivity Topology</div>
        <div class="topology">
            {topology_nodes}
        </div>
    </div>

    <!-- Connection Health Cards -->
    <div class="section">
        <div class="section-title"><span class="icon">🔌</span> Connection Health</div>
        <div class="cards">
            {conn_cards}
        </div>
    </div>

    <!-- VIF Health Cards -->
    <div class="section">
        <div class="section-title"><span class="icon">🌐</span> Virtual Interface Health</div>
        <div class="cards">
            {vif_cards}
        </div>
    </div>

    <!-- BGP Peer Table -->
    <div class="section">
        <div class="section-title"><span class="icon">📡</span> BGP Peering Sessions</div>
        {_build_bgp_table(vifs)}
    </div>

    <!-- Charts -->
    <div class="section">
        <div class="section-title"><span class="icon">📊</span> Throughput &amp; Metrics</div>
        <div class="chart-grid" id="charts-container">
            {_build_chart_canvases(connections, vifs)}
        </div>
    </div>

</div>

<script>
const chartDefaults = {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
        legend: {{ labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }},
    }},
    scales: {{
        x: {{ ticks: {{ color: '#64748b', maxRotation: 45, font: {{ size: 10 }} }}, grid: {{ color: 'rgba(100,116,139,0.1)' }} }},
        y: {{ ticks: {{ color: '#64748b', font: {{ size: 10 }} }}, grid: {{ color: 'rgba(100,116,139,0.15)' }} }},
    }},
}};

{chart_scripts}
</script>

</body>
</html>"""

    return html


def _build_topology(connections, vifs, gateways, lags) -> str:
    """Build the connectivity topology visualization."""
    if not connections:
        return '<div style="text-align:center;color:var(--text2);padding:40px;">No connections found</div>'

    rows = []
    for c in connections:
        cid = c.get("connectionId", "")
        cname = c.get("connectionName", cid)
        state = c.get("connectionState", "unknown")
        bw = c.get("bandwidth", "")
        loc = c.get("location", "")
        link_class = "up" if state == "available" else "down" if state in ("down", "deleted") else "unknown"

        # Find VIFs for this connection
        conn_vifs = [v for v in vifs if v.get("connectionId") == cid]

        # Find gateway for VIFs
        gw_name = ""
        gw_id = ""
        for v in conn_vifs:
            gid = v.get("directConnectGatewayId", "")
            if gid:
                gw_id = gid
                for gw in gateways:
                    if gw.get("directConnectGatewayId") == gid:
                        gw_name = gw.get("directConnectGatewayName", gid)
                        break
                break

        vif_labels = []
        for v in conn_vifs:
            vid = v.get("virtualInterfaceId", "")
            vtype = v.get("virtualInterfaceType", "")
            vstate = v.get("virtualInterfaceState", "unknown")
            bgp_ok = all(p.get("bgpStatus") == "up" for p in v.get("bgpPeers", []))
            vif_color = _status_color("available" if vstate == "available" and bgp_ok else vstate)
            vif_labels.append(f'<div style="font-size:0.7rem;color:{vif_color};">{_status_icon("available" if bgp_ok else "down")} {vid} ({vtype})</div>')

        vif_html = "".join(vif_labels) if vif_labels else '<div style="font-size:0.7rem;color:var(--text2);">No VIFs</div>'

        row = f"""
        <div class="topo-row" style="margin-bottom:16px;">
            <!-- On-Premises -->
            <div class="topo-node">
                <div class="node-icon" style="background:linear-gradient(135deg,#374151,#1f2937);border:2px solid #6b7280;">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/><circle cx="6" cy="6.5" r="1" fill="#9ca3af"/><circle cx="6" cy="13.5" r="1" fill="#9ca3af"/><line x1="8" y1="20" x2="16" y2="20"/><line x1="12" y1="17" x2="12" y2="20"/></svg>
                </div>
                <div class="node-name">On-Premises</div>
                <div class="node-label">Customer Router</div>
            </div>

            <!-- Link: On-Prem to DX Location -->
            <div class="topo-link">
                <span class="link-arrow">◀</span>
                <div class="link-line {link_class}" title="{bw}"></div>
                <span class="link-arrow">▶</span>
            </div>

            <!-- DX Location -->
            <div class="topo-node">
                <div class="node-icon" style="background:linear-gradient(135deg,{'#065f46' if state=='available' else '#7f1d1d'},{'#064e3b' if state=='available' else '#450a0a'});border:2px solid {_status_color(state)};">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="{_status_color(state)}" stroke-width="1.5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                </div>
                <div class="node-name">{cname}</div>
                <div class="node-label">{cid}<br/>{bw} @ {loc}</div>
                <div class="node-status" style="background:{_status_color(state)};color:white;">{state}</div>
            </div>

            <!-- Link: DX Location to VIFs -->
            <div class="topo-link">
                <span class="link-arrow">◀</span>
                <div class="link-line {link_class}"></div>
                <span class="link-arrow">▶</span>
            </div>

            <!-- Virtual Interfaces -->
            <div class="topo-node">
                <div class="node-icon" style="background:linear-gradient(135deg,#1e3a5f,#172554);border:2px solid var(--accent);">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="1.5"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>
                </div>
                <div class="node-name">Virtual Interfaces</div>
                <div class="node-label">{vif_html}</div>
            </div>

            <!-- Link: VIFs to DX Gateway -->
            <div class="topo-link">
                <span class="link-arrow">◀</span>
                <div class="link-line {'up' if gw_id else 'unknown'}"></div>
                <span class="link-arrow">▶</span>
            </div>

            <!-- DX Gateway -->
            <div class="topo-node">
                <div class="node-icon" style="background:linear-gradient(135deg,#4c1d95,#2e1065);border:2px solid var(--purple);">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="1.5"><path d="M4 14a1 1 0 01-.78-1.63l9-11a1 1 0 011.78.63v7h5a1 1 0 01.78 1.63l-9 11a1 1 0 01-1.78-.63v-7H4z"/></svg>
                </div>
                <div class="node-name">DX Gateway</div>
                <div class="node-label">{gw_name or 'N/A'}<br/>{gw_id[:20] if gw_id else ''}</div>
            </div>

            <!-- Link: DX Gateway to AWS Cloud -->
            <div class="topo-link">
                <span class="link-arrow">◀</span>
                <div class="link-line {'up' if gw_id else 'unknown'}"></div>
                <span class="link-arrow">▶</span>
            </div>

            <!-- AWS Cloud -->
            <div class="topo-node">
                <div class="node-icon" style="background:linear-gradient(135deg,#f97316,#ea580c);border:2px solid var(--orange);">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.5"><path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z"/></svg>
                </div>
                <div class="node-name">AWS Cloud</div>
                <div class="node-label">VPCs / TGW</div>
            </div>
        </div>"""
        rows.append(row)

    return "\n".join(rows)


def _build_kpi_section(connections, vifs, conn_metrics, vif_metrics) -> str:
    """Build KPI summary cards."""
    total_conn = len(connections)
    up_conn = sum(1 for c in connections if c.get("connectionState") == "available")
    total_vifs = len(vifs)
    up_vifs = sum(1 for v in vifs if v.get("virtualInterfaceState") == "available")

    # BGP health
    total_bgp = 0
    up_bgp = 0
    for v in vifs:
        for p in v.get("bgpPeers", []):
            total_bgp += 1
            if p.get("bgpStatus") == "up":
                up_bgp += 1

    # Total throughput — prefer connection-level, fall back to VIF-level
    total_egress_mbps = 0
    total_ingress_mbps = 0
    has_conn_throughput = False
    for cid, m in conn_metrics.items():
        eg_vals = _safe_vals(m.get("bps_egress", []))
        in_vals = _safe_vals(m.get("bps_ingress", []))
        if eg_vals:
            total_egress_mbps += eg_vals[-1] / 1_000_000
            has_conn_throughput = True
        if in_vals:
            total_ingress_mbps += in_vals[-1] / 1_000_000
            has_conn_throughput = True

    # Fallback: use VIF-level metrics if connection-level are empty (hosted connections)
    if not has_conn_throughput:
        for vid, m in vif_metrics.items():
            eg_vals = _safe_vals(m.get("bps_egress", []))
            in_vals = _safe_vals(m.get("bps_ingress", []))
            if eg_vals:
                total_egress_mbps += eg_vals[-1] / 1_000_000
            if in_vals:
                total_ingress_mbps += in_vals[-1] / 1_000_000

    conn_color = "var(--green)" if up_conn == total_conn else "var(--red)"
    vif_color = "var(--green)" if up_vifs == total_vifs else "var(--amber)"
    bgp_color = "var(--green)" if up_bgp == total_bgp else "var(--red)"

    return f"""
    <div class="kpi-row">
        <div class="kpi" style="border-left-color:{conn_color};">
            <div class="kpi-label">Connections</div>
            <div class="kpi-value" style="color:{conn_color};">{up_conn}/{total_conn}</div>
            <div class="kpi-sub">Available / Total</div>
        </div>
        <div class="kpi" style="border-left-color:{vif_color};">
            <div class="kpi-label">Virtual Interfaces</div>
            <div class="kpi-value" style="color:{vif_color};">{up_vifs}/{total_vifs}</div>
            <div class="kpi-sub">Available / Total</div>
        </div>
        <div class="kpi" style="border-left-color:{bgp_color};">
            <div class="kpi-label">BGP Sessions</div>
            <div class="kpi-value" style="color:{bgp_color};">{up_bgp}/{total_bgp}</div>
            <div class="kpi-sub">Up / Total</div>
        </div>
        <div class="kpi" style="border-left-color:var(--cyan);">
            <div class="kpi-label">Current Egress</div>
            <div class="kpi-value" style="color:var(--cyan);">{total_egress_mbps:.1f}</div>
            <div class="kpi-sub">Mbps (AWS → On-Prem)</div>
        </div>
        <div class="kpi" style="border-left-color:var(--purple);">
            <div class="kpi-label">Current Ingress</div>
            <div class="kpi-value" style="color:var(--purple);">{total_ingress_mbps:.1f}</div>
            <div class="kpi-sub">Mbps (On-Prem → AWS)</div>
        </div>
    </div>"""


def _build_alerts_section(connections, vifs, conn_metrics, vif_metrics) -> str:
    """Build alerts section."""
    alerts = []

    for c in connections:
        cid = c.get("connectionId", "")
        cname = c.get("connectionName", cid)
        state = c.get("connectionState", "unknown")
        if state != "available":
            alerts.append(("critical", f"🔴 Connection {cname} ({cid}) is {state}"))

        # Check errors
        m = conn_metrics.get(cid, {})
        err_vals = _safe_vals(m.get("errors", []))
        total_err = sum(err_vals)
        if total_err > 100:
            alerts.append(("critical", f"⚠️ Connection {cname}: {int(total_err)} errors detected"))
        elif total_err > 0:
            alerts.append(("warning", f"⚡ Connection {cname}: {int(total_err)} errors detected"))

    for v in vifs:
        vid = v.get("virtualInterfaceId", "")
        vname = v.get("virtualInterfaceName", vid)
        vstate = v.get("virtualInterfaceState", "unknown")
        if vstate != "available":
            alerts.append(("critical", f"🔴 VIF {vname} ({vid}) is {vstate}"))

        for p in v.get("bgpPeers", []):
            if p.get("bgpStatus") != "up":
                alerts.append(("critical", f"📡 BGP peer {p.get('bgpPeerId','')} on {vname}: status={p.get('bgpStatus','unknown')}"))

    if not alerts:
        alerts.append(("ok", "✅ All connections, VIFs, and BGP sessions are healthy"))

    items = []
    for level, msg in alerts:
        items.append(f'<div class="alert-item {level}">{msg}</div>')

    return f"""
    <div class="alerts">
        <div class="section-title"><span class="icon">🚨</span> Alerts</div>
        {"".join(items)}
    </div>"""


def _build_connection_cards(connections, conn_metrics, vif_metrics) -> str:
    """Build connection health cards."""
    cards = []
    for c in connections:
        cid = c.get("connectionId", "")
        cname = c.get("connectionName", cid)
        state = c.get("connectionState", "unknown")
        bw = c.get("bandwidth", "N/A")
        loc = c.get("location", "N/A")
        lag = c.get("lagId", "")

        m = conn_metrics.get(cid, {})

        # Latest throughput — prefer connection-level, fall back to VIF-level
        eg_vals = _safe_vals(m.get("bps_egress", []))
        in_vals = _safe_vals(m.get("bps_ingress", []))

        # If connection-level throughput is empty, aggregate VIF-level for this connection
        if not eg_vals and not in_vals:
            for v in [vi for vi in vif_metrics.values() if vi.get("info", {}).get("connectionId") == cid]:
                veg = _safe_vals(v.get("bps_egress", []))
                vin = _safe_vals(v.get("bps_ingress", []))
                if veg:
                    eg_vals = veg if not eg_vals else [a + b for a, b in zip(eg_vals, veg)]
                if vin:
                    in_vals = vin if not in_vals else [a + b for a, b in zip(in_vals, vin)]

        eg_mbps = round(eg_vals[-1] / 1_000_000, 2) if eg_vals else 0
        in_mbps = round(in_vals[-1] / 1_000_000, 2) if in_vals else 0
        peak_eg = round(max(eg_vals) / 1_000_000, 2) if eg_vals else 0
        peak_in = round(max(in_vals) / 1_000_000, 2) if in_vals else 0

        # Errors
        err_vals = _safe_vals(m.get("errors", []))
        total_err = int(sum(err_vals))

        # Optical
        tx_vals = _safe_vals(m.get("light_tx", []))
        rx_vals = _safe_vals(m.get("light_rx", []))
        tx_dbm = round(tx_vals[-1], 2) if tx_vals else "N/A"
        rx_dbm = round(rx_vals[-1], 2) if rx_vals else "N/A"

        # Optical health
        rx_status = ""
        if isinstance(rx_dbm, (int, float)):
            if rx_dbm < -20:
                rx_status = '<span style="color:var(--red);">CRITICAL</span>'
            elif rx_dbm < -14:
                rx_status = '<span style="color:var(--amber);">WARN</span>'
            else:
                rx_status = '<span style="color:var(--green);">OK</span>'

        err_color = "var(--green)" if total_err == 0 else "var(--red)" if total_err > 100 else "var(--amber)"

        cards.append(f"""
        <div class="card">
            <div class="card-header">
                <div class="status-dot" style="background:{_status_color(state)};"></div>
                <div class="card-title">{cname}</div>
                <div class="card-id">{cid}</div>
            </div>
            <div class="card-body">
                <div class="metric">
                    <div class="metric-label">State</div>
                    <div class="metric-value" style="color:{_status_color(state)};">{state.upper()}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Bandwidth</div>
                    <div class="metric-value">{bw}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Egress (AWS→OnPrem)</div>
                    <div class="metric-value" style="color:var(--cyan);">{eg_mbps} <span class="metric-unit">Mbps</span></div>
                    <div class="metric-unit">Peak: {peak_eg} Mbps</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Ingress (OnPrem→AWS)</div>
                    <div class="metric-value" style="color:var(--purple);">{in_mbps} <span class="metric-unit">Mbps</span></div>
                    <div class="metric-unit">Peak: {peak_in} Mbps</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Errors</div>
                    <div class="metric-value" style="color:{err_color};">{total_err}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Location</div>
                    <div class="metric-value" style="font-size:0.85rem;">{loc}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Optical Tx</div>
                    <div class="metric-value">{tx_dbm} <span class="metric-unit">dBm</span></div>
                </div>
                <div class="metric">
                    <div class="metric-label">Optical Rx {rx_status}</div>
                    <div class="metric-value">{rx_dbm} <span class="metric-unit">dBm</span></div>
                </div>
                {f'<div class="metric full"><div class="metric-label">LAG</div><div class="metric-value" style="font-size:0.85rem;">{lag}</div></div>' if lag else ''}
            </div>
        </div>""")

    return "\n".join(cards) if cards else '<div style="color:var(--text2);padding:20px;">No connections found</div>'


def _build_vif_cards(vifs, vif_metrics) -> str:
    """Build virtual interface health cards."""
    cards = []
    for v in vifs:
        vid = v.get("virtualInterfaceId", "")
        vname = v.get("virtualInterfaceName", vid)
        vtype = v.get("virtualInterfaceType", "")
        vstate = v.get("virtualInterfaceState", "unknown")
        cid = v.get("connectionId", "")
        vlan = v.get("vlan", "")
        mtu = v.get("mtu", "")
        asn = v.get("asn", "")

        m = vif_metrics.get(vid, {})

        # Throughput
        eg_vals = _safe_vals(m.get("bps_egress", []))
        in_vals = _safe_vals(m.get("bps_ingress", []))
        eg_mbps = round(eg_vals[-1] / 1_000_000, 2) if eg_vals else 0
        in_mbps = round(in_vals[-1] / 1_000_000, 2) if in_vals else 0

        # BGP
        bgp_vals = _safe_vals(m.get("bgp_status", []))
        bgp_state = "UP" if bgp_vals and bgp_vals[-1] >= 1 else "DOWN" if bgp_vals else "N/A"
        bgp_color = _status_color("available" if bgp_state == "UP" else "down" if bgp_state == "DOWN" else "unknown")

        # Prefixes
        acc_vals = _safe_vals(m.get("prefixes_accepted", []))
        adv_vals = _safe_vals(m.get("prefixes_advertised", []))
        acc_count = int(acc_vals[-1]) if acc_vals else 0
        adv_count = int(adv_vals[-1]) if adv_vals else 0

        # BGP peers from API
        peers_html = ""
        for p in v.get("bgpPeers", []):
            ps = p.get("bgpStatus", "unknown")
            peers_html += f'<div style="font-size:0.75rem;color:{_status_color("available" if ps=="up" else "down")};">{_status_icon("available" if ps=="up" else "down")} ASN {p.get("asn","")} — {ps}</div>'

        type_colors = {"private": "var(--green)", "public": "var(--cyan)", "transit": "var(--purple)"}
        type_color = type_colors.get(vtype, "var(--text2)")

        cards.append(f"""
        <div class="card">
            <div class="card-header">
                <div class="status-dot" style="background:{_status_color(vstate)};"></div>
                <div class="card-title">{vname}</div>
                <div class="card-id">{vid}</div>
            </div>
            <div class="card-body">
                <div class="metric">
                    <div class="metric-label">Type</div>
                    <div class="metric-value" style="color:{type_color};font-size:0.95rem;">{vtype}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">State</div>
                    <div class="metric-value" style="color:{_status_color(vstate)};">{vstate.upper()}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">BGP Status</div>
                    <div class="metric-value" style="color:{bgp_color};">{bgp_state}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">VLAN / MTU</div>
                    <div class="metric-value" style="font-size:0.95rem;">{vlan} / {mtu}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Egress</div>
                    <div class="metric-value" style="color:var(--cyan);">{eg_mbps} <span class="metric-unit">Mbps</span></div>
                </div>
                <div class="metric">
                    <div class="metric-label">Ingress</div>
                    <div class="metric-value" style="color:var(--purple);">{in_mbps} <span class="metric-unit">Mbps</span></div>
                </div>
                <div class="metric">
                    <div class="metric-label">Prefixes Accepted</div>
                    <div class="metric-value">{acc_count}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Prefixes Advertised</div>
                    <div class="metric-value">{adv_count}</div>
                </div>
                <div class="metric full">
                    <div class="metric-label">BGP Peers</div>
                    {peers_html if peers_html else '<div style="font-size:0.75rem;color:var(--text2);">No peers</div>'}
                </div>
            </div>
        </div>""")

    return "\n".join(cards) if cards else '<div style="color:var(--text2);padding:20px;">No virtual interfaces found</div>'


def _build_bgp_table(vifs) -> str:
    """Build BGP peering sessions table."""
    rows = []
    for v in vifs:
        vid = v.get("virtualInterfaceId", "")
        vname = v.get("virtualInterfaceName", vid)
        for p in v.get("bgpPeers", []):
            status = p.get("bgpStatus", "unknown")
            state = p.get("bgpPeerState", "unknown")
            color = _status_color("available" if status == "up" else "down")
            rows.append(f"""
            <tr>
                <td>{vname}</td>
                <td style="font-family:monospace;">{vid}</td>
                <td>{p.get("bgpPeerId", "")}</td>
                <td>{p.get("asn", "")}</td>
                <td>{p.get("addressFamily", "")}</td>
                <td style="font-family:monospace;font-size:0.8rem;">{p.get("amazonAddress", "")}</td>
                <td style="font-family:monospace;font-size:0.8rem;">{p.get("customerAddress", "")}</td>
                <td style="color:{color};font-weight:600;">{_status_icon("available" if status=="up" else "down")} {status}</td>
                <td>{state}</td>
            </tr>""")

    if not rows:
        return '<div style="color:var(--text2);padding:20px;">No BGP peers found</div>'

    return f"""
    <div style="overflow-x:auto;">
        <table class="bgp-table">
            <thead>
                <tr>
                    <th>VIF Name</th><th>VIF ID</th><th>Peer ID</th><th>ASN</th>
                    <th>Address Family</th><th>Amazon Address</th><th>Customer Address</th>
                    <th>BGP Status</th><th>Peer State</th>
                </tr>
            </thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
    </div>"""


def _build_chart_canvases(connections, vifs) -> str:
    """Build chart canvas elements."""
    canvases = []
    for i, c in enumerate(connections):
        cid = c.get("connectionId", "")
        cname = c.get("connectionName", cid)
        canvases.append(f"""
        <div class="chart-box">
            <h3>🔌 {cname} — Throughput (Mbps)</h3>
            <div style="height:260px;"><canvas id="conn-tp-{i}"></canvas></div>
        </div>""")
        canvases.append(f"""
        <div class="chart-box">
            <h3>🔌 {cname} — Connection State</h3>
            <div style="height:260px;"><canvas id="conn-state-{i}"></canvas></div>
        </div>""")

    for i, v in enumerate(vifs):
        vid = v.get("virtualInterfaceId", "")
        vname = v.get("virtualInterfaceName", vid)
        canvases.append(f"""
        <div class="chart-box">
            <h3>🌐 {vname} — VIF Throughput (Mbps)</h3>
            <div style="height:260px;"><canvas id="vif-tp-{i}"></canvas></div>
        </div>""")
        canvases.append(f"""
        <div class="chart-box">
            <h3>📡 {vname} — BGP Status &amp; Prefixes</h3>
            <div style="height:260px;"><canvas id="vif-bgp-{i}"></canvas></div>
        </div>""")

    return "\n".join(canvases) if canvases else '<div style="color:var(--text2);padding:20px;">No chart data available</div>'


def _build_chart_scripts(connections, vifs, conn_metrics, vif_metrics) -> str:
    """Build Chart.js initialization scripts."""
    scripts = []

    for i, c in enumerate(connections):
        cid = c.get("connectionId", "")
        m = conn_metrics.get(cid, {})

        # Use connection-level throughput, fall back to VIF-level for hosted connections
        eg_series = m.get("bps_egress", [])
        in_series = m.get("bps_ingress", [])
        if not _safe_vals(eg_series) and not _safe_vals(in_series):
            # Aggregate VIF-level metrics for this connection
            for vid, vm in vif_metrics.items():
                if vm.get("info", {}).get("connectionId") == cid:
                    if _safe_vals(vm.get("bps_egress", [])):
                        eg_series = vm.get("bps_egress", [])
                    if _safe_vals(vm.get("bps_ingress", [])):
                        in_series = vm.get("bps_ingress", [])
                    break

        # Throughput chart
        eg_labels = json.dumps(_safe_labels(eg_series))
        eg_data = json.dumps([round(v / 1_000_000, 2) for v in _safe_vals(eg_series)])
        in_data = json.dumps([round(v / 1_000_000, 2) for v in _safe_vals(in_series)])

        scripts.append(f"""
new Chart(document.getElementById('conn-tp-{i}'), {{
    type: 'line',
    data: {{
        labels: {eg_labels},
        datasets: [
            {{ label: 'Egress (AWS→OnPrem)', data: {eg_data}, borderColor: '#06b6d4', backgroundColor: 'rgba(6,182,212,0.1)', fill: true, tension: 0.3, pointRadius: 0 }},
            {{ label: 'Ingress (OnPrem→AWS)', data: {in_data}, borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.1)', fill: true, tension: 0.3, pointRadius: 0 }},
        ]
    }},
    options: {{ ...chartDefaults, plugins: {{ ...chartDefaults.plugins, title: {{ display: false }} }} }}
}});""")

        # State chart
        state_labels = json.dumps(_safe_labels(m.get("state", [])))
        state_data = json.dumps(_safe_vals(m.get("state", [])))

        scripts.append(f"""
new Chart(document.getElementById('conn-state-{i}'), {{
    type: 'line',
    data: {{
        labels: {state_labels},
        datasets: [
            {{ label: 'Connection State (1=UP, 0=DOWN)', data: {state_data}, borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.15)', fill: true, stepped: true, pointRadius: 0 }},
        ]
    }},
    options: {{ ...chartDefaults, scales: {{ ...chartDefaults.scales, y: {{ ...chartDefaults.scales.y, min: -0.1, max: 1.1, ticks: {{ ...chartDefaults.scales.y.ticks, stepSize: 1, callback: function(v) {{ return v >= 1 ? 'UP' : 'DOWN'; }} }} }} }} }}
}});""")

    for i, v in enumerate(vifs):
        vid = v.get("virtualInterfaceId", "")
        m = vif_metrics.get(vid, {})

        # VIF throughput
        veg_labels = json.dumps(_safe_labels(m.get("bps_egress", [])))
        veg_data = json.dumps([round(v / 1_000_000, 2) for v in _safe_vals(m.get("bps_egress", []))])
        vin_data = json.dumps([round(v / 1_000_000, 2) for v in _safe_vals(m.get("bps_ingress", []))])

        scripts.append(f"""
new Chart(document.getElementById('vif-tp-{i}'), {{
    type: 'line',
    data: {{
        labels: {veg_labels},
        datasets: [
            {{ label: 'Egress', data: {veg_data}, borderColor: '#06b6d4', backgroundColor: 'rgba(6,182,212,0.1)', fill: true, tension: 0.3, pointRadius: 0 }},
            {{ label: 'Ingress', data: {vin_data}, borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.1)', fill: true, tension: 0.3, pointRadius: 0 }},
        ]
    }},
    options: {{ ...chartDefaults }}
}});""")

        # BGP status + prefixes
        bgp_labels = json.dumps(_safe_labels(m.get("bgp_status", [])))
        bgp_data = json.dumps(_safe_vals(m.get("bgp_status", [])))
        acc_data = json.dumps(_safe_vals(m.get("prefixes_accepted", [])))
        adv_data = json.dumps(_safe_vals(m.get("prefixes_advertised", [])))

        scripts.append(f"""
new Chart(document.getElementById('vif-bgp-{i}'), {{
    type: 'line',
    data: {{
        labels: {bgp_labels},
        datasets: [
            {{ label: 'BGP Status (1=UP)', data: {bgp_data}, borderColor: '#10b981', stepped: true, pointRadius: 0, yAxisID: 'y' }},
            {{ label: 'Prefixes Accepted', data: {acc_data}, borderColor: '#f59e0b', tension: 0.3, pointRadius: 0, yAxisID: 'y1' }},
            {{ label: 'Prefixes Advertised', data: {adv_data}, borderColor: '#3b82f6', tension: 0.3, pointRadius: 0, yAxisID: 'y1' }},
        ]
    }},
    options: {{
        ...chartDefaults,
        scales: {{
            x: chartDefaults.scales.x,
            y: {{ ...chartDefaults.scales.y, position: 'left', min: -0.1, max: 1.1, ticks: {{ ...chartDefaults.scales.y.ticks, stepSize: 1, callback: function(v) {{ return v >= 1 ? 'UP' : 'DOWN'; }} }} }},
            y1: {{ ...chartDefaults.scales.y, position: 'right', grid: {{ drawOnChartArea: false }}, title: {{ display: true, text: 'Prefixes', color: '#94a3b8' }} }},
        }}
    }}
}});""")

    return "\n".join(scripts)
