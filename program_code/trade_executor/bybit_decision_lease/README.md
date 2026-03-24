# bybit_decision_lease

Canonical implementation directory for Bybit decision-lease core modules.

Migration policy:
- real implementation files move here gradually
- legacy entrypoints remain under
  `program_code/exchange_connectors/bybit_connector/scripts/`
  as compatibility wrappers
- runtime behavior should remain stable during staged migration

Current migrated batch:
- batch1_core_schema_preflight
