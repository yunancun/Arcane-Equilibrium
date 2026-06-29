# Stock/ETF Cash Phase 0 Named Contract Packet

Date: 2026-06-29
Status: **Accepted Phase 0 contract packet - no runtime authority**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow only.
Authority: ADR-0048 + AMD-2026-06-29-01.
Manifest: `2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json`

## 0. Scope

This packet is the Phase 0 source of truth for later IBKR Stock/ETF paper/shadow development. It names the contracts that Phase 1-5 must implement and verify.

It does not authorize:

- IBKR API calls
- IBKR process startup
- secret-slot creation
- broker-paper order submission
- GUI runtime stock/ETF activation
- DB migration apply
- evidence clock start
- tiny-live or live

## 1. Global Invariants

| Invariant | Required behavior |
|---|---|
| Lane closure | `asset_lane` is one of `crypto_perp`, `stock_etf_cash`, `cfd_margin_reserved`; no catch-all. |
| Broker closure | `broker` is one of `bybit`, `ibkr`; no catch-all. |
| Environment closure | `readonly`, `paper`, `shadow`, `live_reserved_denied`; no functional IBKR live flag. |
| Default posture | All stock/ETF and IBKR flags default OFF; `crypto_perp` remains default lane. |
| Rust authority | Any effect-capable paper order rehearsal must enter through Rust lane-scoped IPC. |
| Python boundary | Python may read, display, import fixtures, and call Rust IPC; it must not own broker writes. |
| Secret boundary | IBKR live secret material is a blocker, not a reserved dormant path. |
| Evidence boundary | Paper/shadow evidence is not durable alpha proof and cannot auto-promote. |

## 2. `asset_lane_taxonomy_v1`

Fields:

- `asset_lane`: `crypto_perp` | `stock_etf_cash` | `cfd_margin_reserved`
- `broker`: `bybit` | `ibkr`
- `broker_environment`: `readonly` | `paper` | `shadow` | `live_reserved_denied`
- `instrument_kind`: `crypto_perp` | `stock` | `etf` | `cash` | `cfd_reserved`
- `authority_scope`: `display_only` | `readonly` | `paper_rehearsal` | `shadow_only` | `denied`

Rules:

- `stock_etf_cash` accepts only `stock`, `etf`, and cash ledger records.
- `cfd_margin_reserved` must be denied in all effect-capable code paths.
- `live_reserved_denied` is a denial value, not a dormant toggle.

## 3. `broker_capability_registry_v1`

Operation taxonomy:

- `health_read`
- `account_snapshot_read`
- `market_data_read`
- `contract_details_read`
- `paper_order_submit`
- `paper_order_cancel`
- `paper_order_replace`
- `paper_order_fill_import`
- `shadow_signal_emit`
- `shadow_fill_reconstruct`
- `scorecard_derive`
- `live_order_submit`
- `margin_or_short`
- `options_or_cfd`
- `transfer_or_account_write`

Matrix:

| Operation | `stock_etf_cash` authority | Required gates |
|---|---|---|
| `health_read` | Allowed after gate | `phase2_ibkr_external_surface_gate_v1` |
| `account_snapshot_read` | Allowed after gate | external gate + session attestation |
| `market_data_read` | Allowed after gate | external gate + provenance contract |
| `contract_details_read` | Allowed after gate | external gate + instrument identity contract |
| `paper_order_submit` | Paper-only, Rust-owned | external gate + paper attestation + scoped auth + Decision Lease + Guardian |
| `paper_order_cancel` | Paper-only, Rust-owned | same as submit + lifecycle idempotency |
| `paper_order_replace` | Paper-only, Rust-owned | same as submit + replace state machine |
| `paper_order_fill_import` | Read/import only | session attestation + idempotency |
| `shadow_signal_emit` | Allowed after Phase 3 | frozen hypothesis + universe |
| `shadow_fill_reconstruct` | Allowed after Phase 3 | cost model + market provenance |
| `scorecard_derive` | Derived only | atomic facts + hashes |
| `live_order_submit` | Denied | typed denial `ibkr_live_not_authorized` |
| `margin_or_short` | Denied | typed denial `stock_etf_cash_only` |
| `options_or_cfd` | Denied | typed denial `instrument_kind_denied` |
| `transfer_or_account_write` | Denied | typed denial `account_write_denied` |

Every operation must emit an audit event with `asset_lane`, `broker`, `environment`, `operation`, `allowed`, `denial_reason`, and source artifact hash.

## 4. `phase2_ibkr_external_surface_gate_v1`

The first IBKR contact must wait for this immutable PASS artifact.

Required fields:

- `status`: `PASS` | `BLOCKED`
- `adr`: `ADR-0048`
- `amd`: `AMD-2026-06-29-01`
- `api_baseline`: `ib_gateway_tws_api`
- `host_policy`: loopback only
- `port_policy`: paper gateway port only
- `live_ports_denied`: true
- `secret_contract_present`: true
- `live_secret_absent_or_empty`: true
- `api_allowlist_present`: true
- `redaction_suite_passed`: true
- `rate_limit_policy_present`: true
- `audit_event_policy_present`: true
- `paper_attestation_contract_present`: true
- `python_no_write_guard_present`: true
- `ibkr_call_performed`: false for the gate itself

Any missing field blocks all IBKR contact.

## 5. `non_bybit_api_allowlist_v1`

Initial transport baseline:

- IBKR IB Gateway using TWS API protocol
- loopback host only
- no Client Portal Web API in Phase 2 unless a later contract revision replaces this baseline

Allowed read-style actions after external gate PASS:

- server time / connection health
- account summary snapshot
- portfolio positions snapshot
- contract details
- market data snapshot or subscribed data within approved entitlements
- historical bars for approved universe
- open paper orders
- executions and commission reports for the paper account

Allowed paper-write actions only after paper-order gates:

- submit paper order
- cancel paper order
- replace paper order

Denied actions:

- live order
- live account query using a live account fingerprint
- account transfer
- margin enablement
- short borrow
- options
- CFD
- market-data entitlement purchase
- account-management write

Raw payloads must be hashed and redacted. Secrets, account ids, local paths, cookies, tokens, and stack traces must not appear in logs or reports.

## 6. `ibkr_api_session_topology_v1`

Baseline:

- `api_baseline = ib_gateway_tws_api`
- runtime owner: Linux `trade-core`
- host: `127.0.0.1` or Unix-local equivalent only
- paper gateway port policy: configured paper port, default candidate `4002`
- live gateway/TWS ports: denied
- client id: configured, deterministic, per lane
- process owner: user service or explicit manual process recorded in attestation

The topology contract must record:

- process identity
- host/port
- gateway mode
- account fingerprint
- API server version
- data tier/entitlements
- startup time
- attestation expiry

## 7. `ibkr_session_attestation_v1`

Required before any read-only account snapshot or paper lifecycle rehearsal:

- `status`: `PAPER_ATTESTED` | `READONLY_ATTESTED` | `BLOCKED`
- `account_fingerprint`
- `environment`: `paper` or `readonly`
- `host`
- `port`
- `process_identity`
- `gateway_mode`
- `secret_slot_fingerprint`
- `secret_slot_mode`
- `live_secret_absent_or_empty`
- `api_server_version`
- `attested_at`
- `expires_at`
- `raw_artifact_hash`

Blockers:

- live account fingerprint
- live port
- missing or world-readable secret
- env-var credential fallback
- unknown session mode
- stale attestation

## 8. `feature_flag_secret_auth_matrix_v1`

Flags:

- `OPENCLAW_STOCK_ETF_LANE_ENABLED=0`
- `OPENCLAW_IBKR_READONLY_ENABLED=0`
- `OPENCLAW_IBKR_PAPER_ENABLED=0`
- `OPENCLAW_ASSET_LANE_DEFAULT=crypto_perp`
- `OPENCLAW_STOCK_ETF_SHADOW_ONLY=1`

Allowed secret slots:

- `$OPENCLAW_SECRETS_DIR/external/ibkr/readonly/`
- `$OPENCLAW_SECRETS_DIR/external/ibkr/paper/`

Denied secret slot:

- `$OPENCLAW_SECRETS_DIR/external/ibkr/live/`

Authorization envelope fields:

- `asset_lane`
- `broker`
- `environment`
- `permission_scope`
- `secret_slot_fingerprint`
- `account_fingerprint`
- `risk_config_hash`
- `expires_at`

Rules:

- Read-only flag does not imply paper write.
- Paper flag does not imply live.
- Shadow-only flag blocks paper orders even when read-only is enabled.
- GUI lane state cannot override server/Rust matrix results.

## 9. `lane_scoped_ipc_v1`

Rust IPC commands must be lane-scoped and separate from existing Bybit paper commands:

- `stock_etf.get_lane_status`
- `stock_etf.get_readiness`
- `stock_etf.preview_paper_order`
- `stock_etf.submit_paper_order`
- `stock_etf.cancel_paper_order`
- `stock_etf.replace_paper_order`
- `stock_etf.import_paper_fills`
- `stock_etf.evaluate_shadow_signal`

Every effect-capable command requires:

- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- `environment=paper`
- valid session attestation
- scoped authorization
- Decision Lease id
- Guardian state
- risk config hash
- instrument identity hash
- idempotency key

Denied reasons:

- `lane_disabled`
- `broker_disabled`
- `shadow_only`
- `live_reserved_denied`
- `market_closed`
- `instrument_blocked`
- `cost_model_missing`
- `universe_mismatch`
- `credential_unavailable`
- `connector_unavailable`
- `authorization_invalid`
- `decision_lease_invalid`
- `guardian_denied`

## 10. `ibkr_paper_order_lifecycle_v1`

States:

- `LOCAL_INTENT_CREATED`
- `RUST_AUTHORITY_ACCEPTED`
- `BROKER_SUBMIT_REQUESTED`
- `BROKER_ACKNOWLEDGED`
- `PARTIALLY_FILLED`
- `FILLED`
- `CANCEL_REQUESTED`
- `CANCELLED`
- `REPLACE_REQUESTED`
- `REPLACED`
- `REJECTED`
- `INACTIVE`
- `STATE_UNKNOWN`
- `MANUAL_REVIEW_REQUIRED`

Terminal states:

- `FILLED`
- `CANCELLED`
- `REJECTED`
- `INACTIVE`
- `MANUAL_REVIEW_REQUIRED`

Required ids:

- local order id
- idempotency key
- broker order id
- execution id
- commission report id
- lifecycle event id
- reconciliation run id

Restart recovery:

- known broker state reconciles by broker order id and idempotency key
- unknown broker state maps to `STATE_UNKNOWN`
- `STATE_UNKNOWN` must transition only to `MANUAL_REVIEW_REQUIRED` or a reconciled terminal state with evidence

## 11. `broker_lifecycle_event_log_v1`

Append-only event fields:

- `event_id`
- `event_time`
- `asset_lane`
- `broker`
- `environment`
- `operation`
- `order_local_id`
- `broker_order_id`
- `execution_id`
- `commission_report_id`
- `previous_state`
- `next_state`
- `allowed`
- `denial_reason`
- `raw_artifact_hash`
- `redacted_summary_hash`

Lifecycle events are atomic evidence. Daily summaries and scorecards are derived artifacts only.

## 12. `stock_etf_db_evidence_ddl_v1`

Required schemas:

- `broker`
- `research`
- `audit`

Required tables:

- `broker.instruments`
- `broker.instrument_listings`
- `broker.market_sessions`
- `broker.corporate_actions`
- `broker.fx_rates`
- `broker.account_cash_ledger`
- `broker.paper_orders`
- `broker.paper_fills`
- `broker.commissions`
- `research.stock_shadow_signals`
- `research.stock_shadow_fills`
- `research.stock_etf_scorecard`
- `audit.asset_lane_events`

Minimum keys:

- instrument natural key: `asset_lane`, `broker`, `symbol`, `listing_venue`, `currency`, `primary_exchange`
- order natural key: `asset_lane`, `broker`, `environment`, `account_fingerprint`, `local_order_id`
- fill natural key: `asset_lane`, `broker`, `environment`, `broker_order_id`, `execution_id`
- scorecard natural key: `asset_lane`, `strategy_id`, `universe_version`, `benchmark_version`, `as_of_date`

Required constraints:

- `asset_lane='stock_etf_cash'` for stock tables
- `broker='ibkr'` for IBKR paper facts
- `synthetic_shadow=true` only in shadow fill tables
- paper fills and shadow fills must not share a table without explicit discriminator and tests
- live environment is not allowed

Migration rules:

- Guard A for `CREATE TABLE IF NOT EXISTS`
- Guard B for type-sensitive `ADD COLUMN`
- Guard C for hot-path indexes
- Linux PG dry-run before apply
- idempotency double-apply before sign-off

## 13. `stock_market_data_provenance_v1`

Required on every market-data fact:

- source vendor/broker
- entitlement tier
- raw payload hash
- received time
- exchange time when available
- adjusted/unadjusted marker
- corporate-action adjustment version
- symbol and instrument identity hash
- calendar session id

Unknown provenance blocks scorecard readiness.

## 14. `broker_account_portfolio_cash_ledger_v1`

Cash ledger fields:

- account fingerprint
- currency
- cash balance
- settled cash
- buying power paper value
- FX rate source
- FX rate as-of
- paper equity
- source artifact hash

This is paper evidence only and cannot be used as live account proof.

## 15. `cost_model_version_v1`

Required components:

- commission schedule
- exchange/regulatory fee placeholder
- spread estimate
- slippage estimate
- FX drag
- tax/FTT placeholder when applicable
- conservative fill penalty sensitivity

Cost model version hash must be frozen before evidence clock starts.

## 16. `benchmark_versions_v1`

Each hypothesis must name:

- benchmark id
- benchmark data source
- benchmark construction version
- rebalancing rule
- currency treatment
- corporate-action adjustment version
- matched-control rule

Benchmark version hash must be frozen before evidence clock starts.

## 17. `stock_shadow_fill_model_v1`

Required fields:

- signal id
- instrument identity
- intended side
- intended notional
- market session
- quote/bar source hash
- conservative fill price
- spread/slippage/cost components
- rejection reason if not filled
- synthetic marker

Shadow fills must be clearly separate from broker paper fills and must never be counted as live fills.

## 18. `stock_etf_evidence_clock_v1`

Clock start requires:

- IBKR read-only/paper connector green for 5 trading days
- shadow collector green for 5 trading days
- frozen universe hash
- frozen benchmark hash
- frozen cost model hash
- frozen strategy hypothesis hash
- corporate-action/FX/fee source as-of frozen
- paper-vs-shadow divergence thresholds frozen
- GUI evidence view available
- daily scorecard regeneration pass

Statuses:

- `NOT_STARTED`
- `PASS_DAY`
- `QUARANTINED_DAY`
- `BLOCKED`
- `WINDOW_COMPLETE`

The clock counts engineering shakedown days. It does not prove durable alpha by itself.

## 19. `gui_lane_contract_v1`

First GUI slice:

- default `crypto_perp` lane badge
- stock/ETF readiness/status display
- stock live disabled display
- no login-success selector until backend route/cache/auth partition tests pass
- no disabled CFD surface in first slice except fail-closed status/tests

Negative tests:

- localStorage lane cannot authorize
- query param lane cannot authorize
- hidden field lane cannot authorize
- stale cache cannot mix crypto/stock rows
- stock live shows denied/no authorization path
- existing crypto tabs and Decision Lease/risk behavior do not regress

## 20. `stock_etf_storage_capacity_v1`

Required estimates before Phase 3:

- universe size
- bars/quotes/fills/signals rows per day
- raw payload hash retention
- compressed/raw retention duration
- index budget
- query SLO
- archive path
- disable cleanup retention policy

Capacity breach blocks evidence clock.

## 21. `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`

Kill actions:

- set `OPENCLAW_STOCK_ETF_LANE_ENABLED=0`
- set `OPENCLAW_IBKR_READONLY_ENABLED=0`
- set `OPENCLAW_IBKR_PAPER_ENABLED=0`
- preserve `OPENCLAW_STOCK_ETF_SHADOW_ONLY=1`
- stop collector
- hide GUI stock views or show disabled status
- prove live secret absence
- archive evidence forward-only

No destructive DB cleanup is allowed as rollback. Data retention is forward-only unless a separate data-correction process is approved.

## 22. `stock_etf_release_packet_v1`

Release packet must include:

- ADR/AMD/spec paths
- role reports
- E2/E4/QA logs
- manifest hashes
- PG dry-run and double-apply logs if migrations exist
- redaction fixtures
- GUI screenshots
- DQ manifests
- scorecard regeneration outputs
- kill/disable cleanup proof
- evidence archive pointer

## 23. `tiny_live_adr_eligibility_v1`

Eligibility to discuss tiny-live requires:

- Phase 5 release packet hash
- scorecard manifest hash
- DQ manifest hash
- statistical preregistration hash
- QC/MIT review hashes
- paper/shadow window complete
- benchmark-relative after-cost lower confidence bound > 0
- independent-observation threshold met
- conservative cost stress still positive
- paper-vs-shadow divergence inside threshold
- concentration/regime/freshness labels pass
- QC/MIT review pass
- decision value exactly `adr_discussion_only`
- no serialized secret content
- sealed source artifact

Passing this contract does not authorize tiny-live. It only allows a new ADR discussion, and any `tiny_live_authorized` or `live_authorized` decision value must fail validation.

## 24. Phase Unlock Table

| Phase | Unlock condition | Explicitly still blocked |
|---|---|---|
| Phase 1 | This packet present and internally consistent | IBKR connector/API/secret/runtime |
| Phase 2 | External-surface gate PASS | live, transfer, margin, short, options, CFD |
| Phase 3 | Data/provenance/evidence contracts implemented | durable alpha proof |
| Phase 4 | route/cache/auth negative tests PASS | GUI authority |
| Phase 5 | release packet + shakedown complete | tiny-live/live |

## 25. Verification Requirements

Minimum Phase 1 verification:

- Rust focused type/denial tests
- Python flag/readiness tests
- static guard proving no Python broker write API
- GUI JS `node --check` if GUI changes
- `git diff --check`

Minimum Phase 2 verification:

- external-surface gate immutable PASS
- session attestation PASS
- redaction fixtures PASS
- no secrets in argv/logs
- paper lifecycle idempotency and unknown-state tests

Minimum Phase 3 verification:

- scorecard regeneration from atomic facts
- DQ/quarantine manifest
- evidence clock day-count checker
- benchmark/cost/universe hash checks

Minimum Phase 4 verification:

- route/cache/auth partition tests
- crypto regression tests
- desktop/mobile screenshots

Minimum Phase 5 verification:

- release packet manifest
- kill/disable cleanup proof
- evidence archive proof
- QC/MIT/QA/PM sign-off

## 26. Current Phase 0 Acceptance

This packet accepts the governance and interface baseline only. The next allowed engineering task is Phase 1 source foundation with default-off flags and denial-first tests. Connector creation, IBKR contact, secret slots, paper order rehearsal, GUI runtime stock activation, and evidence clock remain blocked until their named gates pass.
