"""
Governance module package.

This directory is reserved for the future migration of governance modules
from program_code/exchange_connectors/bybit_connector/control_api_v1/app/
to a dedicated governance subsystem.

During migration, governance modules will be reorganized into:
- base: Core governance interfaces and utilities
- authorization: Authorization and permission state machines
- risk_governor: Risk management and governor state machines
- decision_lease: Decision lease and TTL enforcement
- reconciliation: Reconciliation engines and audit trails
"""
