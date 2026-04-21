# AWS Direct Connect Monitor

An MCP (Model Context Protocol) server for near real-time monitoring of AWS Direct Connect connections, virtual interfaces, BGP health, optical signal levels, and interactive dashboard generation.

Built for [Kiro](https://kiro.dev) as a Power with 16 monitoring tools.

## Features

- **Discovery** — List connections, virtual interfaces, DX gateways, and LAGs
- **Connection Health** — State monitoring, throughput, packet rates, errors, optical signal levels, encryption state
- **VIF Health** — Per-VIF throughput, packet rates, BGP status, prefix counts
- **BGP Monitoring** — Session status, flap detection, prefix accepted/advertised tracking
- **Health Check** — Single-command check across all connections and VIFs
- **Interactive Dashboard** — Self-contained HTML with Chart.js charts and SVG connectivity topology

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- AWS CLI configured with SSO profile that has Direct Connect + CloudWatch read access

### Install

```bash
git clone https://github.com/certisgroup/aws-direct-connect-monitor.git
cd aws-direct-connect-monitor
uv sync
```

### Add to Kiro

Add to your `.kiro/settings/mcp.json`:

```json
{
  "aws-direct-connect-monitor": {
    "command": "uv",
    "args": [
      "--directory",
      "/path/to/aws-direct-connect-monitor",
      "run",
      "aws-direct-connect-monitor"
    ],
    "env": {
      "AWS_PROFILE": "your-sso-profile",
      "AWS_REGION": "ap-southeast-1",
      "DX_ACCOUNT_ID": "",
      "PYTHONDONTWRITEBYTECODE": "1"
    },
    "disabled": false,
    "autoApprove": []
  }
}
```

### Install as Kiro Power

1. Open the **Powers** panel in Kiro
2. Click **Add Custom Power** → **Local Directory**
3. Point to the `power/` directory in this repo

## Tools

| Category | Tool | Description |
|----------|------|-------------|
| Discovery | `list_connections` | All DX connections with state, bandwidth, location |
| Discovery | `list_virtual_interfaces` | All VIFs with BGP peer details |
| Discovery | `list_gateways` | DX gateways with associations |
| Discovery | `list_lags` | LAGs with member connections |
| Connection | `get_connection_state` | UP/DOWN timeline with uptime % |
| Connection | `get_connection_throughput` | Egress/ingress bps |
| Connection | `get_connection_packets` | Packet rate (pps) |
| Connection | `get_connection_errors` | MAC-level/CRC errors |
| Connection | `get_optical_levels` | Tx/Rx signal in dBm |
| Connection | `get_encryption_state` | MACsec encryption status |
| VIF | `get_vif_throughput` | Per-VIF throughput |
| VIF | `get_vif_packets` | Per-VIF packet rate |
| VIF | `get_bgp_status` | BGP session with flap detection |
| VIF | `get_bgp_prefixes` | Prefix counts with anomaly detection |
| Operations | `health_check` | Full health check across all resources |
| Operations | `generate_dx_dashboard` | Interactive HTML dashboard |

## Required IAM Permissions

```
directconnect:DescribeConnections
directconnect:DescribeVirtualInterfaces
directconnect:DescribeDirectConnectGateways
directconnect:DescribeDirectConnectGatewayAssociations
directconnect:DescribeLags
cloudwatch:GetMetricStatistics
cloudwatch:ListMetrics
```

## Dashboard

The `generate_dx_dashboard` tool creates a self-contained HTML file with:

- KPI summary (connections, VIFs, BGP sessions, throughput)
- Alerts panel
- Connectivity topology with SVG icons
- Connection and VIF health cards
- BGP peering table
- Interactive Chart.js time series

## License

Internal — Certis Group CCoE
