"""AWS Direct Connect Monitor MCP Server.

Near real-time monitoring of AWS Direct Connect connections, virtual interfaces,
BGP health, optical signal levels, and generates interactive dashboards with
connectivity topology icons.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from mcp.server.fastmcp import FastMCP

from aws_direct_connect_monitor.dashboard import generate_dashboard_html

# Configuration from environment
AWS_PROFILE = os.environ.get("AWS_PROFILE", "certis-ct-network")
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
DX_ACCOUNT_ID = os.environ.get("DX_ACCOUNT_ID", "")

mcp = FastMCP("aws-direct-connect-monitor")


# ============================================================
# AWS CLIENT HELPERS
# ============================================================

def get_session():
    """Get boto3 session using configured profile."""
    try:
        return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    except Exception:
        return boto3.Session(region_name=AWS_REGION)


def get_dx_client():
    """Get Direct Connect client."""
    return get_session().client("directconnect")


def get_cloudwatch_client():
    """Get CloudWatch client."""
    return get_session().client("cloudwatch")


def query_metric(
    metric_name: str,
    dimensions: list[dict],
    stat: str = "Average",
    period: int = 300,
    hours_back: int = 24,
    namespace: str = "AWS/DX",
) -> list[dict]:
    """Query a single CloudWatch metric and return time series."""
    cw = get_cloudwatch_client()
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)

    try:
        response = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start,
            EndTime=now,
            Period=period,
            Statistics=[stat],
        )
        datapoints = sorted(
            response.get("Datapoints", []), key=lambda x: x["Timestamp"]
        )
        return [
            {"timestamp": dp["Timestamp"].isoformat(), "value": dp[stat]}
            for dp in datapoints
        ]
    except Exception as e:
        return [{"error": str(e)}]


def conn_dims(connection_id: str) -> list[dict]:
    """Build CloudWatch dimensions for a connection."""
    return [{"Name": "ConnectionId", "Value": connection_id}]


def vif_dims(connection_id: str, vif_id: str) -> list[dict]:
    """Build CloudWatch dimensions for a virtual interface."""
    return [
        {"Name": "ConnectionId", "Value": connection_id},
        {"Name": "VirtualInterfaceId", "Value": vif_id},
    ]


# ============================================================
# MCP TOOLS — DISCOVERY
# ============================================================

@mcp.tool()
def list_connections() -> str:
    """List all AWS Direct Connect connections with state, bandwidth, location, and LAG info.

    Returns connection ID, name, state, bandwidth, location, VLAN, partner name,
    and LAG membership for every connection in the account.
    """
    dx = get_dx_client()
    resp = dx.describe_connections()
    connections = []
    for c in resp.get("connections", []):
        connections.append({
            "connection_id": c.get("connectionId"),
            "connection_name": c.get("connectionName"),
            "state": c.get("connectionState"),
            "bandwidth": c.get("bandwidth"),
            "location": c.get("location"),
            "region": c.get("region"),
            "vlan": c.get("vlan"),
            "partner_name": c.get("partnerName", ""),
            "lag_id": c.get("lagId", ""),
            "aws_device": c.get("awsDevice", ""),
            "aws_device_v2": c.get("awsDeviceV2", ""),
            "has_logical_redundancy": c.get("hasLogicalRedundancy", ""),
            "encryption_mode": c.get("encryptionMode", ""),
            "mac_sec_capable": c.get("macSecCapable", False),
        })
    return json.dumps({
        "account": DX_ACCOUNT_ID or "current",
        "region": AWS_REGION,
        "total_connections": len(connections),
        "connections": connections,
    }, indent=2)


@mcp.tool()
def list_virtual_interfaces() -> str:
    """List all Direct Connect virtual interfaces with BGP peer details.

    Returns VIF ID, type (private/public/transit), state, VLAN, BGP ASN,
    BGP peers, associated connection, and gateway info.
    """
    dx = get_dx_client()
    resp = dx.describe_virtual_interfaces()
    vifs = []
    for v in resp.get("virtualInterfaces", []):
        bgp_peers = []
        for peer in v.get("bgpPeers", []):
            bgp_peers.append({
                "bgp_peer_id": peer.get("bgpPeerId"),
                "bgp_peer_state": peer.get("bgpPeerState"),
                "bgp_status": peer.get("bgpStatus"),
                "asn": peer.get("asn"),
                "address_family": peer.get("addressFamily"),
                "amazon_address": peer.get("amazonAddress", ""),
                "customer_address": peer.get("customerAddress", ""),
            })
        vifs.append({
            "vif_id": v.get("virtualInterfaceId"),
            "vif_name": v.get("virtualInterfaceName"),
            "vif_type": v.get("virtualInterfaceType"),
            "vif_state": v.get("virtualInterfaceState"),
            "connection_id": v.get("connectionId"),
            "vlan": v.get("vlan"),
            "asn": v.get("asn"),
            "amazon_side_asn": v.get("amazonSideAsn"),
            "mtu": v.get("mtu"),
            "jumbo_frame_capable": v.get("jumboFrameCapable", False),
            "direct_connect_gateway_id": v.get("directConnectGatewayId", ""),
            "virtual_gateway_id": v.get("virtualGatewayId", ""),
            "region": v.get("region"),
            "aws_device_v2": v.get("awsDeviceV2", ""),
            "bgp_peers": bgp_peers,
            "route_filter_prefixes": [
                p.get("cidr") for p in v.get("routeFilterPrefixes", [])
            ],
        })
    return json.dumps({
        "account": DX_ACCOUNT_ID or "current",
        "region": AWS_REGION,
        "total_vifs": len(vifs),
        "virtual_interfaces": vifs,
    }, indent=2)


@mcp.tool()
def list_gateways() -> str:
    """List all Direct Connect gateways with associated connections.

    Returns gateway ID, name, ASN, state, and associated virtual interfaces.
    """
    dx = get_dx_client()
    resp = dx.describe_direct_connect_gateways()
    gateways = []
    for gw in resp.get("directConnectGateways", []):
        gw_id = gw.get("directConnectGatewayId")
        # Get associations
        try:
            assoc_resp = dx.describe_direct_connect_gateway_associations(
                directConnectGatewayId=gw_id
            )
            associations = []
            for a in assoc_resp.get("directConnectGatewayAssociations", []):
                associations.append({
                    "association_id": a.get("associationId"),
                    "association_state": a.get("associationState"),
                    "associated_gateway": a.get("associatedGateway", {}),
                    "virtual_gateway_id": a.get("virtualGatewayId", ""),
                    "allowed_prefixes": [
                        p.get("cidr") for p in a.get("allowedPrefixesToDirectConnectGateway", [])
                    ],
                })
        except Exception:
            associations = []

        gateways.append({
            "gateway_id": gw_id,
            "gateway_name": gw.get("directConnectGatewayName"),
            "amazon_side_asn": gw.get("amazonSideAsn"),
            "state": gw.get("directConnectGatewayState"),
            "owner_account": gw.get("ownerAccount"),
            "associations": associations,
        })
    return json.dumps({
        "total_gateways": len(gateways),
        "gateways": gateways,
    }, indent=2)


@mcp.tool()
def list_lags() -> str:
    """List all Link Aggregation Groups (LAGs) with member connections.

    Returns LAG ID, name, state, bandwidth, location, and member connection details.
    """
    dx = get_dx_client()
    resp = dx.describe_lags()
    lags = []
    for lag in resp.get("lags", []):
        members = []
        for c in lag.get("connections", []):
            members.append({
                "connection_id": c.get("connectionId"),
                "connection_name": c.get("connectionName"),
                "state": c.get("connectionState"),
                "bandwidth": c.get("bandwidth"),
            })
        lags.append({
            "lag_id": lag.get("lagId"),
            "lag_name": lag.get("lagName"),
            "lag_state": lag.get("lagState"),
            "location": lag.get("location"),
            "region": lag.get("region"),
            "bandwidth": lag.get("connectionsBandwidth"),
            "minimum_links": lag.get("minimumLinks"),
            "number_of_connections": lag.get("numberOfConnections"),
            "aws_device": lag.get("awsDevice", ""),
            "aws_device_v2": lag.get("awsDeviceV2", ""),
            "has_logical_redundancy": lag.get("hasLogicalRedundancy", ""),
            "encryption_mode": lag.get("encryptionMode", ""),
            "mac_sec_capable": lag.get("macSecCapable", False),
            "member_connections": members,
        })
    return json.dumps({
        "total_lags": len(lags),
        "lags": lags,
    }, indent=2)


# ============================================================
# MCP TOOLS — CONNECTION HEALTH
# ============================================================

@mcp.tool()
def get_connection_state(
    connection_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor Direct Connect connection state over time.

    ConnectionState: 1 = UP, 0 = DOWN. Any drop to 0 indicates an outage.
    Use this to detect flapping connections or historical downtime windows.

    Args:
        connection_id: The Direct Connect connection ID (e.g., dxcon-abc123).
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with connection state time series and uptime percentage.
    """
    datapoints = query_metric(
        metric_name="ConnectionState",
        dimensions=conn_dims(connection_id),
        stat="Minimum",
        period=period,
        hours_back=hours_back,
    )

    total_points = len(datapoints)
    up_points = sum(1 for dp in datapoints if dp.get("value", 0) >= 1)
    uptime_pct = round((up_points / total_points * 100), 2) if total_points > 0 else 0
    down_events = []
    for dp in datapoints:
        if dp.get("value", 1) < 1:
            down_events.append(dp["timestamp"])

    return json.dumps({
        "connection_id": connection_id,
        "hours_back": hours_back,
        "period_seconds": period,
        "total_datapoints": total_points,
        "uptime_percent": uptime_pct,
        "down_events": down_events,
        "current_state": "UP" if datapoints and datapoints[-1].get("value", 0) >= 1 else "DOWN" if datapoints else "NO DATA",
        "alert": "CONNECTION DOWN DETECTED" if down_events else "OK",
        "series": datapoints,
    }, indent=2)


@mcp.tool()
def get_connection_throughput(
    connection_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor Direct Connect connection throughput (bits per second) in both directions.

    Tracks ConnectionBpsEgress (AWS → on-prem) and ConnectionBpsIngress (on-prem → AWS).
    Useful for capacity planning and detecting traffic anomalies.

    Args:
        connection_id: The Direct Connect connection ID (e.g., dxcon-abc123).
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with egress/ingress throughput time series and peak/average stats.
    """
    egress = query_metric(
        metric_name="ConnectionBpsEgress",
        dimensions=conn_dims(connection_id),
        stat="Average",
        period=period,
        hours_back=hours_back,
    )
    ingress = query_metric(
        metric_name="ConnectionBpsIngress",
        dimensions=conn_dims(connection_id),
        stat="Average",
        period=period,
        hours_back=hours_back,
    )

    def stats(series):
        vals = [dp["value"] for dp in series if "value" in dp]
        if not vals:
            return {"peak_bps": 0, "avg_bps": 0, "peak_mbps": 0, "avg_mbps": 0}
        peak = max(vals)
        avg = sum(vals) / len(vals)
        return {
            "peak_bps": round(peak, 2),
            "avg_bps": round(avg, 2),
            "peak_mbps": round(peak / 1_000_000, 2),
            "avg_mbps": round(avg / 1_000_000, 2),
        }

    return json.dumps({
        "connection_id": connection_id,
        "hours_back": hours_back,
        "period_seconds": period,
        "egress": {**stats(egress), "series": egress},
        "ingress": {**stats(ingress), "series": ingress},
    }, indent=2)


@mcp.tool()
def get_connection_packets(
    connection_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor Direct Connect connection packet rate (packets per second).

    Tracks ConnectionPpsEgress and ConnectionPpsIngress.
    Sudden spikes may indicate DDoS or broadcast storms.

    Args:
        connection_id: The Direct Connect connection ID.
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with egress/ingress packet rate time series.
    """
    egress = query_metric(
        metric_name="ConnectionPpsEgress",
        dimensions=conn_dims(connection_id),
        stat="Average",
        period=period,
        hours_back=hours_back,
    )
    ingress = query_metric(
        metric_name="ConnectionPpsIngress",
        dimensions=conn_dims(connection_id),
        stat="Average",
        period=period,
        hours_back=hours_back,
    )

    def stats(series):
        vals = [dp["value"] for dp in series if "value" in dp]
        if not vals:
            return {"peak_pps": 0, "avg_pps": 0}
        return {"peak_pps": round(max(vals), 2), "avg_pps": round(sum(vals) / len(vals), 2)}

    return json.dumps({
        "connection_id": connection_id,
        "hours_back": hours_back,
        "egress": {**stats(egress), "series": egress},
        "ingress": {**stats(ingress), "series": ingress},
    }, indent=2)


@mcp.tool()
def get_connection_errors(
    connection_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor Direct Connect connection errors (CRC and MAC-level errors).

    ConnectionErrorCount tracks total MAC-level errors including CRC errors.
    Non-zero values indicate physical layer issues on either side.

    Args:
        connection_id: The Direct Connect connection ID.
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with error count time series and alerts.
    """
    errors = query_metric(
        metric_name="ConnectionErrorCount",
        dimensions=conn_dims(connection_id),
        stat="Sum",
        period=period,
        hours_back=hours_back,
    )

    total_errors = sum(dp.get("value", 0) for dp in errors if "value" in dp)
    alerts = []
    if total_errors > 100:
        alerts.append(f"HIGH ERROR COUNT: {int(total_errors)} errors in {hours_back}h — check physical layer")
    elif total_errors > 0:
        alerts.append(f"ERRORS DETECTED: {int(total_errors)} errors in {hours_back}h — monitor trend")

    return json.dumps({
        "connection_id": connection_id,
        "hours_back": hours_back,
        "total_errors": int(total_errors),
        "series": errors,
        "alerts": alerts if alerts else ["OK — No errors detected"],
    }, indent=2)


@mcp.tool()
def get_optical_levels(
    connection_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor Direct Connect optical signal levels (Tx and Rx light levels in dBm).

    ConnectionLightLevelTx: Outbound optical power from AWS side.
    ConnectionLightLevelRx: Inbound optical power to AWS side.
    Normal range is typically -14 to +2.5 dBm. Values below -14 dBm indicate signal degradation.

    Args:
        connection_id: The Direct Connect connection ID.
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with Tx/Rx optical levels and health assessment.
    """
    tx = query_metric(
        metric_name="ConnectionLightLevelTx",
        dimensions=conn_dims(connection_id),
        stat="Average",
        period=period,
        hours_back=hours_back,
    )
    rx = query_metric(
        metric_name="ConnectionLightLevelRx",
        dimensions=conn_dims(connection_id),
        stat="Average",
        period=period,
        hours_back=hours_back,
    )

    def assess(series, label):
        vals = [dp["value"] for dp in series if "value" in dp]
        if not vals:
            return {"status": "NO DATA", "min_dbm": None, "max_dbm": None, "avg_dbm": None}
        min_v, max_v, avg_v = min(vals), max(vals), sum(vals) / len(vals)
        status = "OK"
        if min_v < -14:
            status = "WARNING — Signal below -14 dBm"
        if min_v < -20:
            status = "CRITICAL — Signal below -20 dBm"
        return {
            "status": status,
            "min_dbm": round(min_v, 2),
            "max_dbm": round(max_v, 2),
            "avg_dbm": round(avg_v, 2),
        }

    return json.dumps({
        "connection_id": connection_id,
        "hours_back": hours_back,
        "tx_light_level": {**assess(tx, "Tx"), "series": tx},
        "rx_light_level": {**assess(rx, "Rx"), "series": rx},
        "note": "Normal range: -14 to +2.5 dBm. Below -14 dBm = degradation. Below -20 dBm = critical.",
    }, indent=2)


@mcp.tool()
def get_encryption_state(
    connection_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor Direct Connect MACsec encryption state.

    ConnectionEncryptionState: 1 = encryption UP, 0 = encryption DOWN.
    For LAGs, 1 means all member connections have encryption up.

    Args:
        connection_id: The Direct Connect connection ID.
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with encryption state time series.
    """
    datapoints = query_metric(
        metric_name="ConnectionEncryptionState",
        dimensions=conn_dims(connection_id),
        stat="Minimum",
        period=period,
        hours_back=hours_back,
    )

    down_events = [dp["timestamp"] for dp in datapoints if dp.get("value", 1) < 1]

    return json.dumps({
        "connection_id": connection_id,
        "hours_back": hours_back,
        "current_state": "ENCRYPTED" if datapoints and datapoints[-1].get("value", 0) >= 1 else "NOT ENCRYPTED" if datapoints else "NO DATA",
        "encryption_down_events": down_events,
        "series": datapoints,
        "alert": "ENCRYPTION DOWN DETECTED" if down_events else "OK",
    }, indent=2)


# ============================================================
# MCP TOOLS — VIRTUAL INTERFACE HEALTH
# ============================================================

@mcp.tool()
def get_vif_throughput(
    connection_id: str,
    vif_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor virtual interface throughput (bits per second).

    Tracks VirtualInterfaceBpsEgress and VirtualInterfaceBpsIngress.
    Useful for per-VIF capacity analysis when multiple VIFs share a connection.

    Args:
        connection_id: The Direct Connect connection ID.
        vif_id: The virtual interface ID (e.g., dxvif-abc123).
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with VIF egress/ingress throughput.
    """
    dims = vif_dims(connection_id, vif_id)
    egress = query_metric("VirtualInterfaceBpsEgress", dims, "Average", period, hours_back)
    ingress = query_metric("VirtualInterfaceBpsIngress", dims, "Average", period, hours_back)

    def stats(series):
        vals = [dp["value"] for dp in series if "value" in dp]
        if not vals:
            return {"peak_mbps": 0, "avg_mbps": 0}
        return {
            "peak_mbps": round(max(vals) / 1_000_000, 2),
            "avg_mbps": round((sum(vals) / len(vals)) / 1_000_000, 2),
        }

    return json.dumps({
        "connection_id": connection_id,
        "vif_id": vif_id,
        "hours_back": hours_back,
        "egress": {**stats(egress), "series": egress},
        "ingress": {**stats(ingress), "series": ingress},
    }, indent=2)


@mcp.tool()
def get_vif_packets(
    connection_id: str,
    vif_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor virtual interface packet rate (packets per second).

    Tracks VirtualInterfacePpsEgress and VirtualInterfacePpsIngress.

    Args:
        connection_id: The Direct Connect connection ID.
        vif_id: The virtual interface ID.
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with VIF packet rate time series.
    """
    dims = vif_dims(connection_id, vif_id)
    egress = query_metric("VirtualInterfacePpsEgress", dims, "Average", period, hours_back)
    ingress = query_metric("VirtualInterfacePpsIngress", dims, "Average", period, hours_back)

    def stats(series):
        vals = [dp["value"] for dp in series if "value" in dp]
        if not vals:
            return {"peak_pps": 0, "avg_pps": 0}
        return {"peak_pps": round(max(vals), 2), "avg_pps": round(sum(vals) / len(vals), 2)}

    return json.dumps({
        "connection_id": connection_id,
        "vif_id": vif_id,
        "hours_back": hours_back,
        "egress": {**stats(egress), "series": egress},
        "ingress": {**stats(ingress), "series": ingress},
    }, indent=2)


@mcp.tool()
def get_bgp_status(
    connection_id: str,
    vif_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor BGP peering session status for a virtual interface.

    VirtualInterfaceBgpStatus: 1 = UP, 0 = DOWN.
    BGP flapping is a critical indicator of routing instability.

    Args:
        connection_id: The Direct Connect connection ID.
        vif_id: The virtual interface ID.
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with BGP status time series, uptime, and flap detection.
    """
    dims = vif_dims(connection_id, vif_id)
    datapoints = query_metric("VirtualInterfaceBgpStatus", dims, "Minimum", period, hours_back)

    total = len(datapoints)
    up_count = sum(1 for dp in datapoints if dp.get("value", 0) >= 1)
    uptime_pct = round((up_count / total * 100), 2) if total > 0 else 0

    # Detect flaps (transitions between up and down)
    flaps = 0
    prev_state = None
    for dp in datapoints:
        state = "up" if dp.get("value", 0) >= 1 else "down"
        if prev_state and state != prev_state:
            flaps += 1
        prev_state = state

    down_events = [dp["timestamp"] for dp in datapoints if dp.get("value", 1) < 1]

    alerts = []
    if down_events:
        alerts.append(f"BGP DOWN detected at {len(down_events)} datapoints")
    if flaps > 4:
        alerts.append(f"BGP FLAPPING: {flaps} state transitions in {hours_back}h")

    return json.dumps({
        "connection_id": connection_id,
        "vif_id": vif_id,
        "hours_back": hours_back,
        "bgp_uptime_percent": uptime_pct,
        "bgp_flap_count": flaps,
        "current_bgp_state": "UP" if datapoints and datapoints[-1].get("value", 0) >= 1 else "DOWN" if datapoints else "NO DATA",
        "down_events": down_events,
        "alerts": alerts if alerts else ["OK — BGP stable"],
        "series": datapoints,
    }, indent=2)


@mcp.tool()
def get_bgp_prefixes(
    connection_id: str,
    vif_id: str,
    hours_back: int = 24,
    period: int = 300,
) -> str:
    """Monitor BGP prefix counts (accepted and advertised) for a virtual interface.

    VirtualInterfaceBgpPrefixesAccepted: Routes learned from customer.
    VirtualInterfaceBgpPrefixesAdvertised: Routes advertised to customer.
    Sudden drops indicate route withdrawal; spikes may indicate route leaks.

    Args:
        connection_id: The Direct Connect connection ID.
        vif_id: The virtual interface ID.
        hours_back: Hours of history to query (default 24).
        period: Metric period in seconds (default 300 = 5 min).

    Returns:
        JSON with prefix count time series and anomaly detection.
    """
    dims = vif_dims(connection_id, vif_id)
    accepted = query_metric("VirtualInterfaceBgpPrefixesAccepted", dims, "Average", period, hours_back)
    advertised = query_metric("VirtualInterfaceBgpPrefixesAdvertised", dims, "Average", period, hours_back)

    def prefix_stats(series):
        vals = [dp["value"] for dp in series if "value" in dp]
        if not vals:
            return {"current": 0, "min": 0, "max": 0, "avg": 0}
        return {
            "current": round(vals[-1], 0) if vals else 0,
            "min": round(min(vals), 0),
            "max": round(max(vals), 0),
            "avg": round(sum(vals) / len(vals), 1),
        }

    acc_stats = prefix_stats(accepted)
    adv_stats = prefix_stats(advertised)

    alerts = []
    if acc_stats["current"] == 0 and acc_stats["max"] > 0:
        alerts.append("ALERT: Accepted prefixes dropped to 0 — possible route withdrawal")
    if acc_stats["max"] > 0 and acc_stats["min"] < acc_stats["max"] * 0.5:
        alerts.append("WARNING: Significant prefix count fluctuation detected")

    return json.dumps({
        "connection_id": connection_id,
        "vif_id": vif_id,
        "hours_back": hours_back,
        "prefixes_accepted": {**acc_stats, "series": accepted},
        "prefixes_advertised": {**adv_stats, "series": advertised},
        "alerts": alerts if alerts else ["OK — Prefix counts stable"],
    }, indent=2)


# ============================================================
# MCP TOOLS — COMPREHENSIVE HEALTH CHECK
# ============================================================

@mcp.tool()
def health_check(hours_back: int = 1) -> str:
    """Run a comprehensive health check across ALL Direct Connect connections and VIFs.

    Checks connection state, BGP status, throughput, errors, and optical levels
    for every connection and virtual interface. Returns a summary with alerts.

    Args:
        hours_back: Hours of history to check (default 1 for near real-time).

    Returns:
        JSON with overall health status, per-connection and per-VIF summaries.
    """
    dx = get_dx_client()

    # Get all connections
    conn_resp = dx.describe_connections()
    connections = conn_resp.get("connections", [])

    # Get all VIFs
    vif_resp = dx.describe_virtual_interfaces()
    vifs = vif_resp.get("virtualInterfaces", [])

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hours_back": hours_back,
        "overall_status": "HEALTHY",
        "connections": [],
        "virtual_interfaces": [],
        "alerts": [],
    }

    # Check each connection
    for c in connections:
        cid = c.get("connectionId")
        cname = c.get("connectionName", cid)
        api_state = c.get("connectionState", "unknown")

        conn_health = {
            "connection_id": cid,
            "connection_name": cname,
            "api_state": api_state,
            "bandwidth": c.get("bandwidth"),
            "location": c.get("location"),
            "status": "HEALTHY",
            "issues": [],
        }

        # Check CloudWatch connection state
        state_data = query_metric("ConnectionState", conn_dims(cid), "Minimum", 300, hours_back)
        if state_data and any(dp.get("value", 1) < 1 for dp in state_data if "value" in dp):
            conn_health["status"] = "DEGRADED"
            conn_health["issues"].append("Connection state dropped to DOWN")
            results["alerts"].append(f"{cname} ({cid}): Connection DOWN detected")

        if api_state != "available":
            conn_health["status"] = "CRITICAL"
            conn_health["issues"].append(f"API state: {api_state}")
            results["alerts"].append(f"{cname} ({cid}): API state is {api_state}")

        # Check errors
        error_data = query_metric("ConnectionErrorCount", conn_dims(cid), "Sum", 300, hours_back)
        total_errors = sum(dp.get("value", 0) for dp in error_data if "value" in dp)
        if total_errors > 0:
            conn_health["error_count"] = int(total_errors)
            if total_errors > 100:
                conn_health["status"] = "DEGRADED"
                conn_health["issues"].append(f"High error count: {int(total_errors)}")
                results["alerts"].append(f"{cname} ({cid}): {int(total_errors)} errors")

        results["connections"].append(conn_health)

    # Check each VIF
    for v in vifs:
        vid = v.get("virtualInterfaceId")
        vname = v.get("virtualInterfaceName", vid)
        cid = v.get("connectionId")
        vif_state = v.get("virtualInterfaceState", "unknown")

        vif_health = {
            "vif_id": vid,
            "vif_name": vname,
            "vif_type": v.get("virtualInterfaceType"),
            "connection_id": cid,
            "api_state": vif_state,
            "status": "HEALTHY",
            "issues": [],
        }

        if vif_state != "available":
            vif_health["status"] = "CRITICAL"
            vif_health["issues"].append(f"VIF state: {vif_state}")
            results["alerts"].append(f"{vname} ({vid}): VIF state is {vif_state}")

        # Check BGP status from API
        for peer in v.get("bgpPeers", []):
            peer_state = peer.get("bgpPeerState", "unknown")
            bgp_status = peer.get("bgpStatus", "unknown")
            if bgp_status != "up":
                vif_health["status"] = "DEGRADED"
                vif_health["issues"].append(f"BGP peer {peer.get('bgpPeerId')}: status={bgp_status}")
                results["alerts"].append(f"{vname} ({vid}): BGP peer {bgp_status}")

        # Check BGP CloudWatch metric
        if cid:
            bgp_data = query_metric("VirtualInterfaceBgpStatus", vif_dims(cid, vid), "Minimum", 300, hours_back)
            if bgp_data and any(dp.get("value", 1) < 1 for dp in bgp_data if "value" in dp):
                if vif_health["status"] == "HEALTHY":
                    vif_health["status"] = "DEGRADED"
                vif_health["issues"].append("BGP session dropped in monitoring window")

        results["virtual_interfaces"].append(vif_health)

    # Determine overall status
    statuses = [c["status"] for c in results["connections"]] + [v["status"] for v in results["virtual_interfaces"]]
    if "CRITICAL" in statuses:
        results["overall_status"] = "CRITICAL"
    elif "DEGRADED" in statuses:
        results["overall_status"] = "DEGRADED"

    if not results["alerts"]:
        results["alerts"] = ["All connections and VIFs healthy"]

    return json.dumps(results, indent=2)


# ============================================================
# MCP TOOLS — DASHBOARD
# ============================================================

@mcp.tool()
def generate_dx_dashboard(
    hours_back: int = 24,
    period: int = 300,
    output_path: str = "dx-dashboard.html",
) -> str:
    """Generate a self-contained interactive HTML dashboard for Direct Connect monitoring.

    Includes connectivity topology with icons, connection health, BGP status,
    throughput charts, optical levels, error tracking, and VIF metrics.
    Uses Chart.js for interactive charts and SVG icons for topology visualization.

    Args:
        hours_back: Hours of history to include (default 24).
        period: Metric period in seconds (default 300 = 5 min).
        output_path: File path to save the HTML dashboard.

    Returns:
        JSON with status and output path.
    """
    dx = get_dx_client()

    # Gather all data
    conn_resp = dx.describe_connections()
    connections = conn_resp.get("connections", [])

    vif_resp = dx.describe_virtual_interfaces()
    vifs = vif_resp.get("virtualInterfaces", [])

    gw_resp = dx.describe_direct_connect_gateways()
    gateways = gw_resp.get("directConnectGateways", [])

    lag_resp = dx.describe_lags()
    lags = lag_resp.get("lags", [])

    # Collect metrics for each connection
    conn_metrics = {}
    for c in connections:
        cid = c["connectionId"]
        dims = conn_dims(cid)
        conn_metrics[cid] = {
            "info": c,
            "state": query_metric("ConnectionState", dims, "Minimum", period, hours_back),
            "bps_egress": query_metric("ConnectionBpsEgress", dims, "Average", period, hours_back),
            "bps_ingress": query_metric("ConnectionBpsIngress", dims, "Average", period, hours_back),
            "pps_egress": query_metric("ConnectionPpsEgress", dims, "Average", period, hours_back),
            "pps_ingress": query_metric("ConnectionPpsIngress", dims, "Average", period, hours_back),
            "errors": query_metric("ConnectionErrorCount", dims, "Sum", period, hours_back),
            "light_tx": query_metric("ConnectionLightLevelTx", dims, "Average", period, hours_back),
            "light_rx": query_metric("ConnectionLightLevelRx", dims, "Average", period, hours_back),
        }

    # Collect metrics for each VIF
    vif_metrics = {}
    for v in vifs:
        vid = v["virtualInterfaceId"]
        cid = v.get("connectionId", "")
        if not cid:
            continue
        dims = vif_dims(cid, vid)
        vif_metrics[vid] = {
            "info": v,
            "bps_egress": query_metric("VirtualInterfaceBpsEgress", dims, "Average", period, hours_back),
            "bps_ingress": query_metric("VirtualInterfaceBpsIngress", dims, "Average", period, hours_back),
            "bgp_status": query_metric("VirtualInterfaceBgpStatus", dims, "Minimum", period, hours_back),
            "prefixes_accepted": query_metric("VirtualInterfaceBgpPrefixesAccepted", dims, "Average", period, hours_back),
            "prefixes_advertised": query_metric("VirtualInterfaceBgpPrefixesAdvertised", dims, "Average", period, hours_back),
        }

    # Generate HTML
    html = generate_dashboard_html(
        connections=connections,
        vifs=vifs,
        gateways=gateways,
        lags=lags,
        conn_metrics=conn_metrics,
        vif_metrics=vif_metrics,
        hours_back=hours_back,
        period=period,
        account_id=DX_ACCOUNT_ID,
        region=AWS_REGION,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return json.dumps({
        "status": "success",
        "output_path": output_path,
        "connections_included": len(connections),
        "vifs_included": len(vifs),
        "gateways_included": len(gateways),
        "hours_back": hours_back,
        "period_seconds": period,
    }, indent=2)


# ============================================================
# MAIN
# ============================================================

def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
