# Broker Settings

This directory stores broker capability contracts and default-off runtime posture. It must not contain API keys, account ids, cookies, tokens, local IBKR session details, or live credential paths.

`ibkr_external_surface_gate.toml` is a Phase 2 source template only. It carries the exact `phase2_ibkr_external_surface_gate_v1` and `non_bybit_api_allowlist_v1` / source-version fields, is intentionally `BLOCKED`, and cannot authorize IBKR contact until an immutable PASS artifact is produced under the ADR-0048 gate process.

`ibkr_phase2_policies.toml` records source policy prerequisites for redaction, rate limiting, audit events, paper attestation, and Python no-write guard with exact policy contract ids and source-version fields. It is not a PASS artifact and does not authorize IBKR contact.

`ibkr_phase2_gate_artifact.template.toml` records the immutable gate artifact shape with exact artifact/gate, secret-slot, and API topology identity/source-version fields plus empty secret-slot and API topology evidence sections. It is intentionally empty/BLOCKED and cannot authorize IBKR contact.

`ibkr_phase2_runtime_contracts.toml` records the source evidence shape for secret-slot posture and API session topology with exact `ibkr_secret_slot_contract_v1` / `ibkr_api_session_topology_v1` / source-version fields. It is intentionally incomplete and cannot authorize IBKR contact.

`ibkr_feature_flag_secret_auth_matrix.toml` records the default-blocked feature-flag, secret, and scoped-authorization matrix shape with exact `feature_flag_secret_auth_matrix_v1` / source-version fields. It does not authorize IBKR contact or paper orders.

`ibkr_paper_order_lifecycle.toml` records the default-blocked paper order lifecycle and append-only event log shape with exact `ibkr_paper_order_lifecycle_v1` / `broker_lifecycle_event_log_v1` / source-version fields. It does not authorize connector creation or paper orders.

`stock_etf_broker_capability_registry.template.toml` records the default-blocked broker capability registry contract shape with exact `broker_capability_registry_v1` / source-version fields. It is source-only and does not contact IBKR, create secrets, create connectors, route orders, or change Bybit live execution behavior.

`stock_etf_lane_scoped_ipc.template.toml` records the default-blocked lane-scoped IPC method matrix contract shape with exact `lane_scoped_ipc_v1` / source-version fields. It does not start IPC, contact IBKR, create connectors, route paper orders, inspect secrets, or change Bybit live execution behavior.

`stock_etf_risk_policy.template.toml` records the default-blocked Stock/ETF cash risk-policy contract shape with exact `stock_etf_risk_policy_v1` / source-version fields. It does not contact IBKR, create connectors, route paper orders, start collectors, write scorecards, inspect secrets, or change Bybit live execution behavior.

`stock_etf_reference_data_sources.template.toml` records the default-blocked corporate-action, FX, fee, and tax/FTT source-as-of contract shape with exact `stock_etf_reference_data_sources_v1` / source-version fields. It does not contact IBKR, create connectors, ingest market/reference data, write scorecards, apply migrations, inspect secrets, or change Bybit live execution behavior.

`stock_market_data_provenance.template.toml` records the default-blocked market-data provenance contract shape with exact `stock_market_data_provenance_v1` / source-version fields. It does not contact IBKR, start connectors or collectors, ingest market data, write scorecards, inspect secrets, authorize GUI lane state, or change Bybit live execution behavior.

`stock_etf_db_evidence_ddl.template.toml` records the default-blocked source-only DB evidence DDL contract shape with exact `stock_etf_db_evidence_ddl_v1` / source-version fields. It does not copy SQL into migrations, open Postgres, register sqlx migrations, apply DDL, contact IBKR, create secrets, route orders, or start an evidence clock.

`stock_etf_instrument_identity.template.toml` records the default-blocked point-in-time instrument identity contract shape with exact `instrument_identity_contract_v1` / source-version fields. It does not contact IBKR, create connectors, subscribe to market data, route paper orders, inspect secrets, or change Bybit live execution behavior.

`stock_etf_pit_universe.template.toml` records the default-blocked point-in-time universe contract shape with exact `stock_etf_pit_universe_contract_v1` / source-version fields. It does not contact IBKR, create connectors, collect market data, route paper orders, inspect secrets, write scorecards, or change Bybit live execution behavior.

`stock_etf_strategy_hypothesis.template.toml` records the default-blocked strategy hypothesis preregistration contract shape with exact `stock_etf_strategy_hypothesis_contract_v1` / source-version fields. It does not contact IBKR, create connectors, collect market data, route paper orders, inspect secrets, write scorecards, claim profitability, or change Bybit live execution behavior.

`stock_etf_asset_lane_events.template.toml` records the default-blocked immutable asset-lane audit event reference shape with exact `audit.asset_lane_events_v1` / source-version fields. It does not write audit rows, apply migrations, contact IBKR, create secrets, or authorize paper/tiny-live/live.

`stock_etf_gui_lane_contract.template.toml` records the default-blocked GUI lane contract shape with exact `gui_lane_contract_v1` / source-version fields. It is source-only and does not serve pages, contact IBKR, create secrets, route orders, or authorize lane selection.

`stock_etf_phase3_evidence_contracts.toml` records the default-blocked market-data provenance, DQ, frozen-input, and evidence-clock checker shape. It requires named contract fields and checker-side side-effect denials for the evidence-clock day shape and does not start the evidence clock.

`stock_etf_scorecard_inputs.template.toml` records the default-blocked cash ledger, cost model, benchmark, shadow fill, and storage capacity named input contracts plus cross-contract hashes for future stock/ETF scorecards. It denies IBKR contact, connector runtime, broker fill import, scorecard writing, DB apply, evidence-clock start, secret serialization, tiny-live/live authority, and Bybit live regression.

`stock_etf_scorecard_verdict.template.toml` records the default-blocked statistical scorecard verdict shape with formula appendix, preregistration, manifest hashes, CI/PSR/DSR-style thresholds, paper-vs-shadow divergence, regime/breadth/freshness/survivorship/execution-realism labels, and review hashes. It can seal positive or negative verdict labels without authorizing IBKR contact, scorecard writing, tiny-live/live, or Bybit changes.

`stock_etf_release_packet.template.toml` records the default-blocked Phase 5 release packet shape with exact `stock_etf_release_packet_v1` / source-version fields. It is secret-free and does not authorize IBKR contact, paper orders, GUI lane authority, tiny-live, or live.

`stock_etf_disable_cleanup_runbook.template.toml` records the default-blocked kill-switch and disable-cleanup runbook shape with exact `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` / source-version fields. It is secret-free and does not stop services, mutate DB state, contact IBKR, route paper orders, change Bybit live execution, or authorize release/tiny-live/live.

`stock_etf_tiny_live_adr_eligibility.template.toml` records the default-blocked future ADR discussion eligibility shape with exact `tiny_live_adr_eligibility_v1` / source-version fields. It is secret-free and cannot authorize IBKR tiny-live or live even if a future paper/shadow scorecard is positive.
