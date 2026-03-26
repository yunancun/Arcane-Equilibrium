# Runtime Snapshot Specification

## Purpose

This document defines the normalized JSON snapshot contract consumed by:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/runtime_bridge.py`

## Required top-level fields

- `runtime_snapshot_id`: string
- `runtime_snapshot_ts_ms`: integer
- `rest_private_connection_state`: enum(`ready`,`degraded`,`down`,`unknown`)
- `ws_private_connection_state`: enum(`ready`,`degraded`,`down`,`unknown`)
- `runtime_connection_state`: enum(`ready`,`degraded`,`down`,`unknown`)
- `account_fact_completeness_state`: enum(`complete`,`partial`,`missing`,`unknown`)
- `source_snapshot_completeness_state`: enum(`complete`,`partial`,`missing`,`unknown`)
- `global_runtime_facts`: object
- `product_family_facts`: object

## global_runtime_facts fields

- `system_mode_fact`: enum(`observe_only`,`shadow_only`,`design_only`,`demo_reserved`,`live_reserved`)
- `execution_state_fact`: enum(`execution_disabled`,`demo_blocked`,`demo_enabled`,`live_blocked`,`unknown`)
- `runtime_last_refresh_ts_ms`: integer
- `runtime_data_freshness_state`: enum(`fresh`,`stale`,`unknown`)

## product_family_facts keys

Supported product families:

- `spot`
- `margin`
- `perp_linear`
- `perp_inverse`
- `options`
- `other_derivatives_reserved`

Each product family object must include:

- `exchange_permission_fact`: enum(`readonly_visible`,`unavailable`,`unknown`)
- `account_permission_fact`: enum(`readonly_visible`,`unavailable`,`unknown`)

## Optional fields

- `readonly_connector_name`
- `execution_connector_name`
- `health_telemetry`

## Validation helper

Use:

```bash
python3 scripts/validate_runtime_snapshot.py examples/runtime_snapshot.example.json
```
