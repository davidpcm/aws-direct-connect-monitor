# Direct Connect Investigation Guide

## When to Use This Guide
Use this guide when investigating Direct Connect connectivity issues, BGP problems, or capacity concerns.

## Investigation Workflow

### Step 1: Quick Health Check
Start with `health_check` to get an overview of all connections and VIFs:
- Checks API state for all connections
- Checks CloudWatch ConnectionState metric
- Checks BGP peer status from API
- Checks CloudWatch VirtualInterfaceBgpStatus metric
- Reports error counts

### Step 2: Connection-Level Investigation
If a connection shows issues:
1. `get_connection_state` — Check for downtime windows
2. `get_connection_errors` — Check for physical layer errors (CRC)
3. `get_optical_levels` — Check fiber signal health (Tx/Rx dBm)
4. `get_connection_throughput` — Check for traffic anomalies
5. `get_encryption_state` — Check MACsec status (if applicable)

### Step 3: VIF-Level Investigation
If a VIF shows issues:
1. `get_bgp_status` — Check for BGP flapping (state transitions)
2. `get_bgp_prefixes` — Check for route withdrawals or leaks
3. `get_vif_throughput` — Check per-VIF traffic patterns
4. `get_vif_packets` — Check packet rates for anomalies

### Step 4: Generate Dashboard
Use `generate_dx_dashboard` to create a visual report for stakeholders.

## Key Metrics Interpretation

### Connection State
- `1` = UP, `0` = DOWN
- Flapping between 0 and 1 = unstable physical connection

### Optical Levels (dBm)
- **Normal**: -14 to +2.5 dBm
- **Warning**: Below -14 dBm
- **Critical**: Below -20 dBm
- **N/A**: Hosted connections don't expose optical metrics

### BGP Status
- `1` = UP, `0` = DOWN
- Frequent transitions = BGP flapping

### BGP Prefixes
- Drop to 0 = route withdrawal
- Sudden spike = possible route leak

### Error Count
- `0` = healthy
- Low = minor physical issues (dirty fiber)
- High = serious physical layer problem

## Common Issues

### Connection Down
1. `get_connection_state` for timing
2. `get_optical_levels` for fiber issues
3. `get_connection_errors` for physical errors
4. Contact AWS Support or DX partner

### BGP Flapping
1. `get_bgp_status` for flap count
2. `get_bgp_prefixes` for prefix instability
3. Common causes: MTU mismatch, BGP timer mismatch, route policy changes

### High Throughput / Capacity
1. `get_connection_throughput` for peak utilization
2. Compare peak vs bandwidth allocation
3. `get_vif_throughput` to identify which VIF is consuming most
