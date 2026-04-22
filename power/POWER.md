---
name: "aws-direct-connect-monitor"
displayName: "AWS Direct Connect Monitor"
description: "Near real-time monitoring of AWS Direct Connect connections, virtual interfaces, BGP health, optical signal levels, and interactive dashboards with connectivity topology icons."
keywords: ["direct-connect", "dx", "bgp", "connection", "virtual-interface", "vif", "throughput", "optical", "signal", "bandwidth", "latency", "network", "connectivity", "dashboard", "topology"]
author: "Davidpcm"
---

# AWS Direct Connect Monitor

## Overview

An MCP server for near real-time monitoring of AWS Direct Connect infrastructure. It queries the Direct Connect API for connection/VIF/gateway inventory and CloudWatch Metrics (AWS/DX namespace) for performance and health data.

Key capabilities:
- **Discovery** — List connections, virtual interfaces, DX gateways, and LAGs
- **Connection Health** — State monitoring, throughput, packet rates, errors, optical signal levels, encryption state
- **VIF Health** — Per-VIF throughput, packet rates, BGP status, prefix counts
- **BGP Monitoring** — BGP session status, flap detection, prefix accepted/advertised tracking
- **Comprehensive Health Check** — Single-command check across all connections and VIFs
- **Interactive Dashboard** — Self-contained HTML with Chart.js charts and SVG connectivity topology icons

## Architecture

```
AWS Direct Connect API  →  Connection/VIF/Gateway inventory
CloudWatch Metrics      →  AWS/DX namespace (5-min intervals)
        ↓
  MCP Server (this tool)
        ↓
  HTML Dashboard / JSON responses
```

## Onboarding

### Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed
- AWS CLI configured with SSO profile for the account owning the Direct Connect connections

### Installation

```bash
git clone https://github.com/davidpcm/aws-direct-connect-monitor.git
cd aws-direct-connect-monitor
uv sync
```

Then update the `mcp.json` in this power directory — set the `--directory` path to where you cloned the repo, and set your `AWS_PROFILE`.

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_PROFILE` | SSO profile for the account with DX connections | `certis-tgw-gto` |
| `AWS_REGION` | AWS region | `ap-southeast-1` |
| `DX_ACCOUNT_ID` | Account ID (for dashboard display) | `` |

### Required IAM Permissions

- `directconnect:Describe*`
- `cloudwatch:GetMetricStatistics`
- `cloudwatch:ListMetrics`

## Tools Reference

### Discovery
| Tool | Description |
|------|-------------|
| `list_connections` | All DX connections with state, bandwidth, location, LAG info |
| `list_virtual_interfaces` | All VIFs with BGP peer details |
| `list_gateways` | DX gateways with associations |
| `list_lags` | LAGs with member connections |

### Connection Health
| Tool | Description |
|------|-------------|
| `get_connection_state` | Connection state over time (1=UP, 0=DOWN) with uptime % |
| `get_connection_throughput` | Egress/ingress throughput in bps with peak/avg stats |
| `get_connection_packets` | Egress/ingress packet rate (pps) |
| `get_connection_errors` | MAC-level error count (CRC errors) |
| `get_optical_levels` | Tx/Rx optical signal levels in dBm with health assessment |
| `get_encryption_state` | MACsec encryption state monitoring |

### Virtual Interface Health
| Tool | Description |
|------|-------------|
| `get_vif_throughput` | Per-VIF egress/ingress throughput |
| `get_vif_packets` | Per-VIF packet rate |
| `get_bgp_status` | BGP session status with flap detection |
| `get_bgp_prefixes` | BGP prefix counts (accepted/advertised) with anomaly detection |

### Operations
| Tool | Description |
|------|-------------|
| `health_check` | Comprehensive health check across ALL connections and VIFs |
| `generate_dx_dashboard` | Generate interactive HTML dashboard with topology icons |

## Common Workflows

### Quick Health Check
```
"Run a Direct Connect health check"
"Are all my DX connections up?"
"Generate a DX dashboard"
```

### Connection Investigation
```
"Show me throughput for connection dxcon-abc123"
"Check optical levels for dxcon-abc123"
"Are there any errors on dxcon-abc123?"
```

### BGP Troubleshooting
```
"Is BGP flapping on dxvif-xyz789?"
"How many prefixes are being accepted?"
"Show me BGP prefix history for the last 24 hours"
```

## Troubleshooting

### SSO Session Expired
**Error:** `UnauthorizedSSOTokenError`
**Solution:** `aws sso login --profile <your-profile>`

### Connection Throughput Shows 0
**Cause:** Hosted connections don't publish `ConnectionBpsEgress/Ingress` metrics
**Solution:** The dashboard automatically falls back to VIF-level throughput metrics

### Optical Levels Show N/A
**Cause:** Hosted connections don't expose optical metrics — only dedicated connections do

### No Metrics Data
**Solution:** Run `list_connections` to verify connection IDs exist
