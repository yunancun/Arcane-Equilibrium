# Stock/ETF Cash Phase 0 Named Contract Packet

Date: 2026-06-29
Status: **Accepted Phase 0 contract packet - no runtime authority**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow only.
Authority: ADR-0048 + AMD-2026-06-29-01.
Manifest: `2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json`

## 0. Scope

This packet is the Phase 0 source of truth for later IBKR Stock/ETF paper/shadow development. It names the contracts that Phase 1-5 must implement and verify.

Machine-readable manifest validator:
`openclaw_types::stock_etf_phase0_manifest::StockEtfPhase0ContractPacketManifestV1`.
The validator pins the manifest schema/status/scope, ADR/AMD/packet paths, IBKR
loopback paper API baseline, global denials, exact contract list, and phase
unlock table. It rejects prior IBKR contact, live-port allowance, missing or
duplicated contracts, missing global denials, and any manifest wording that
unblocks Phase 2 contact, Phase 3 evidence clock, Phase 4 GUI runtime, Phase 5
online status, tiny-live, or live.

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
| `paper_order_submit` | Paper-only, Rust-owned | external gate + paper attestation + scoped auth + risk policy + Decision Lease + Guardian |
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

Source validator: `openclaw_types::stock_etf_broker_capability_registry::StockEtfBrokerCapabilityRegistryV1`.
The validator requires exact `registry_id == broker_capability_registry_v1`,
`source_version == 1`, the complete operation matrix, `stock_etf_cash` / IBKR
scope, Bybit live execution unchanged, Python broker write authority denied,
IBKR live and CFD/margin reserved paths denied, required audit fields, source
artifact hashes, paper-write Rust ownership, required gates for read / paper /
shadow / scorecard operations including `stock_etf_risk_policy_v1`, and exact
typed denials for live, margin/short, options/CFD, and transfer/account-write
operations. It rejects first IBKR contact or serialized secret content in the
registry artifact.

## 4. `phase2_ibkr_external_surface_gate_v1`

The first IBKR contact must wait for this immutable PASS artifact.

Required fields:

- `contract_id=phase2_ibkr_external_surface_gate_v1`
- `source_version=1`
- immutable artifact `artifact_id`
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

Prerequisite policy sources must also carry exact contract identities and
`source_version=1`: `ibkr_redaction_policy_v1`,
`ibkr_rate_limit_policy_v1`, `ibkr_audit_event_policy_v1`,
`ibkr_paper_attestation_v1`, and `ibkr_python_write_guard_policy_v1`.

Any missing field blocks all IBKR contact.

## 5. `non_bybit_api_allowlist_v1`

Required fields:

- `contract_id=non_bybit_api_allowlist_v1`
- `source_version=1`
- `api_baseline=ib_gateway_tws_api`
- complete read / paper-write / denied action buckets matching the source classifier
- `client_portal_web_api_denied=true`
- live order, transfer, margin, short, options, CFD, entitlement-purchase, and account-management writes denied
- `ibkr_contact_performed=false`
- `secret_content_serialized=false`
- `bybit_live_execution_protected=true`

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

Source validator:
`openclaw_types::ibkr_non_bybit_api_allowlist::NonBybitApiAllowlistV1`.
The validator requires exact `contract_id == non_bybit_api_allowlist_v1`,
`source_version == 1`, exact action coverage once, and bucket consistency with
`classify_non_bybit_api_action`. It rejects Client Portal Web API use, live
orders, account writes, margin/short/options/CFD, entitlement purchases, IBKR
contact, serialized secrets, and Bybit-live regression.

## 5A. `instrument_identity_contract_v1`

Instrument identity must be point-in-time and source-artifact backed before
market data, contract details, shadow fill reconstruction, or paper order intent
can consume a symbol.

Required fields:

- `contract_id=instrument_identity_contract_v1`
- `source_version=1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- `instrument_kind`: `stock` | `etf` | `cash`
- `symbol`
- `listing_venue`
- `primary_exchange`
- `currency`
- `tradability_status`
- `priips_kid_status`
- fractional policy recorded
- point-in-time as-of timestamp
- market calendar id and hash
- broker contract-details hash
- instrument identity hash
- corporate-action adjustment version hash
- source artifact hash

Source validator:
`openclaw_types::stock_etf_instrument_identity::StockEtfInstrumentIdentityV1`.
The validator rejects crypto/CFD instruments, unknown venue/exchange, cash-vs-
noncash venue mismatches, non-USD currency in v1, non-tradable instruments,
blocked/unknown PRIIPs KID status, missing PIT/hash/calendar/fractional-policy
evidence, missing Bybit unchanged/live-denied/margin-short-denied/options-CFD-
denied proof, prior IBKR contact, and serialized secret content.

## 5B. `stock_etf_pit_universe_contract_v1`

Point-in-time universe membership must be machine-checkable before Phase 3
evidence-clock days, stock shadow signals, or scorecard derivation can rely on a
`universe_hash`.

Required fields:

- `contract_id=stock_etf_pit_universe_contract_v1`
- `source_version=1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- universe id, version, and hash
- point-in-time as-of timestamp
- effective membership window
- constituent count and v1 maximum bound
- per-constituent symbol, instrument kind, instrument identity hash, listing
  venue, primary exchange, currency, tradability, and PRIIPs status
- inclusion, exclusion, liquidity, tradability, PRIIPs, and delisted/inactive
  policy hashes
- corporate-action adjustment version hash
- market-calendar hash
- source artifact hash
- evidence-clock freeze flag
- survivorship-bias controls
- Bybit-live unchanged and IBKR-live denied proof

Source validator:
`openclaw_types::stock_etf_pit_universe::StockEtfPitUniverseV1`.
The validator rejects crypto/CFD/cash constituents, unknown or cash-ledger
venues, non-USD v1 currency, untradable constituents, blocked/unknown PRIIPs
state, missing PIT/window/hash/survivorship/freeze evidence, oversized v1
universe bounds, prior IBKR contact, serialized secret content, and any Bybit
live regression.

## 5C. `stock_etf_strategy_hypothesis_contract_v1`

Strategy hypotheses must be pre-registered and source-artifact backed before
Phase 3 evidence-clock days, shadow signals, or scorecards can treat a
`strategy_hypothesis_hash` as meaningful.

Required fields:

- `contract_id=stock_etf_strategy_hypothesis_contract_v1`
- `source_version=1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- hypothesis id and version
- strategy family: daily/weekly momentum, sector rotation, or ETF trend/risk-off
- primary timeframe: daily or weekly in v1
- instrument scope
- PIT universe contract hash and universe hash
- benchmark version hash
- cost model version hash
- entry, exit, risk-rule, feature-set, and data-source-policy hashes
- statistical design hash
- hypothesis preregistration hash
- minimum holding period and maximum monthly turnover
- maximum constituents used
- independent-observation target
- lookahead, survivorship, and multiple-testing controls
- benchmark-relative and after-cost metrics
- no options / CFD / margin / short policy
- paper/shadow-only flag
- Bybit-live unchanged and IBKR-live denied proof

Source validator:
`openclaw_types::stock_etf_strategy_hypothesis::StockEtfStrategyHypothesisV1`.
The validator rejects high-frequency/event-driven reserved families, intraday
v1 timeframe, malformed ids, missing design hashes, missing preregistration,
missing bias/multiple-testing controls, missing after-cost/benchmark metrics,
over-high turnover, premature profitability claims, live/tiny-live authority
claims, prior IBKR contact, serialized secret content, and any Bybit live
regression.

## 5D. `stock_etf_risk_policy_v1`

The Stock/ETF risk policy contract makes the dormant paper/shadow risk config
machine-checkable before future paper orders, shadow fills, or scorecards can
trust a `risk_config_hash`.

Required fields:

- `contract_id=stock_etf_risk_policy_v1`
- `source_version=1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- `environment=paper` or `environment=shadow`
- config version 1
- source posture remains `enabled=false` and `shadow_only=true` until a later
  release packet explicitly changes runtime authority
- finite positive max order, max position, and max daily notional caps
- order cap less than or equal to position cap, and position cap less than or
  equal to daily cap
- bounded open-order and open-position limits
- cash-only controls denying margin, short, options, CFD, transfers, and live
- instrument kinds allowed exactly for stock, ETF, and cash usage; crypto perp
  and CFD reserved kinds must remain denied
- frozen universe hash, instrument identity hash, and market session required
- commission, spread, slippage, FX drag, and conservative fill penalty required
  before shadow fills or scorecards
- Rust authority, session attestation, Decision Lease, Guardian, idempotency,
  and broker reconciliation required before paper-order rehearsal
- Bybit live unchanged proof and no IBKR contact / connector runtime / secret
  serialization claim

Source validator:
`openclaw_types::stock_etf_risk_policy::StockEtfRiskPolicyV1`.
The validator parses the existing dormant
`settings/risk_control_rules/risk_config_stock_etf_paper.toml` through
`StockEtfRiskPolicySourceConfigV1` and rejects runtime enablement, missing
shadow-only posture, non-finite or inverted caps, over-high open-order or
open-position limits, any margin/short/options/CFD/transfer/live allowance,
missing universe or cost model prerequisites, missing paper-order gates, IBKR
contact, connector runtime, serialized secrets, and any Bybit live regression.

## 6. `ibkr_api_session_topology_v1`

Baseline:

- `contract_id=ibkr_api_session_topology_v1`
- `source_version=1`
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

- `contract_id=ibkr_session_attestation_v1`
- `source_version=1`
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

Required fields:

- `contract_id=feature_flag_secret_auth_matrix_v1`
- `source_version=1`

Flags:

- `OPENCLAW_STOCK_ETF_LANE_ENABLED=0`
- `OPENCLAW_IBKR_READONLY_ENABLED=0`
- `OPENCLAW_IBKR_PAPER_ENABLED=0`
- `OPENCLAW_ASSET_LANE_DEFAULT=crypto_perp`
- `OPENCLAW_STOCK_ETF_SHADOW_ONLY=1`

Allowed secret slots:

- `$OPENCLAW_SECRETS_DIR/external/ibkr/readonly/`
- `$OPENCLAW_SECRETS_DIR/external/ibkr/paper/`

Secret-slot source contract fields:

- `contract_id=ibkr_secret_slot_contract_v1`
- `source_version=1`
- readonly/paper slot posture is hashed or missing according to scope
- live slot is absent or empty
- secret slot and account fingerprints are hashes only
- env-var credential fallback denied
- secret content and account id serialization denied

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

Static Python guard:
`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`.
The guard parses Stock/ETF/IBKR Python surfaces and future
`program_code/broker_connectors/ibkr_connector/` files with `ast`, while
intentionally excluding existing Bybit modules. It rejects direct Python broker
write methods or calls such as `place_order`, `cancel_order`, `replace_order`,
forbidden Stock/ETF paper-order IPC method strings, direct `ibapi` / `ib_insync`
imports, and non-GET Stock/ETF/IBKR routes until a later Rust-authority contract
revision explicitly changes this surface.

## 9. `lane_scoped_ipc_v1`

Rust IPC commands must be lane-scoped and separate from existing Bybit paper commands:

- `stock_etf.get_lane_status`
- `stock_etf.get_readiness`
- `stock_etf.get_paper_status`
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
- `stock_etf_risk_policy_v1`
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

Source validator:
`openclaw_types::stock_etf_lane_scoped_ipc::StockEtfLaneScopedIpcContractV1`.
The validator requires exact `contract_id == lane_scoped_ipc_v1`,
`source_version == 1`, the exact Stock/ETF IPC method matrix, required gates,
request fields, typed denials, and Rust ownership. Paper submit/cancel/replace
must require `phase2_ibkr_external_surface_gate_v1`,
`ibkr_session_attestation_v1`, `stock_etf_scoped_authorization_v1`,
Decision Lease, Guardian, `stock_etf_risk_policy_v1`, risk-config hash,
instrument identity, idempotency, `ibkr_paper_order_lifecycle_v1`,
`broker_capability_registry_v1`, and `audit.asset_lane_events_v1`. It rejects
missing or duplicate methods, unknown/Bybit paper methods, direct Python broker
write authority, reuse of existing Bybit paper IPC paths, IBKR contact,
connector runtime, serialized secrets, live environment, and Bybit-live
regressions. This contract starts no IPC server and authorizes no paper order.

## 9A. `stock_etf_paper_order_request_v1`

Required fields:

- exact contract id `stock_etf_paper_order_request_v1`
- `source_version=1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- `environment=paper`
- lane-scoped IPC method, broker operation, authority scope, and effect-capable
  flag
- request id and account fingerprint hash

Preview/submit order intent fields:

- normalized symbol
- stock/ETF instrument kind
- buy/sell side
- market/limit order type
- positive decimal quantity
- explicit limit-price policy
- day/GTC time in force

Submit-only fields:

- session attestation hash
- scoped authorization hash
- Decision Lease id
- Guardian state hash
- risk config hash
- instrument identity hash
- local order id
- idempotency key
- lifecycle contract hash
- broker capability registry hash
- audit event id

Cancel-only fields:

- local order id
- broker order id
- cancel reason
- idempotency key
- lifecycle / capability / audit lineage

Replace-only fields:

- local order id
- broker order id
- instrument identity hash
- symbol and side
- replacement idempotency key
- replacement positive decimal quantity
- replacement limit-price policy
- replacement time in force
- replace reason
- lifecycle / capability / audit lineage

Source validator:
`openclaw_types::stock_etf_paper_order_request::StockEtfPaperOrderRequestEnvelopeV1`.
The validator rejects wrong lane/broker/environment, unsupported IPC methods,
operation/scope/effect mismatches, missing hashes/ids, lower-case or unsafe
symbols, CFD/crypto/cash instrument kinds for orders, non-positive decimal
quantities, implicit or mismatched limit-price policy, market orders with a
limit price, cancel requests polluted by submit order-shape fields, replace
requests polluted by original mutable fields, IBKR contact, connector runtime,
serialized secrets, routed orders, Bybit path reuse, live/tiny-live authority,
margin/short/options/CFD requests, and Python direct broker writes.
This contract creates no order and only defines the typed request envelope that
future runtime code must satisfy before reaching the paper lifecycle.

## 9B. `stock_etf_paper_fill_import_request_v1`

Required fields:

- exact contract id `stock_etf_paper_fill_import_request_v1`
- `source_version=1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- `environment=paper`
- `request_method=import_paper_fills`
- `operation=paper_order_fill_import`
- `authority_scope=readonly`
- `effect_capable=false`
- request id
- session attestation hash
- lifecycle contract id/hash
- event log contract id/hash
- redaction policy contract id/hash
- source artifact hash
- reconciliation run id
- broker order id
- execution id
- commission report id
- import idempotency key
- observed order state
- stale-state policy
- raw artifact hash
- redacted summary hash

Source validator:
`openclaw_types::stock_etf_paper_fill_import_request::StockEtfPaperFillImportRequestV1`.
The validator rejects wrong lane/broker/environment, method/operation/scope/
effect mismatches, missing lifecycle/event-log/redaction lineage, missing broker
order/execution/commission ids, missing import idempotency, missing observed
state, missing stale-state policy, duplicate imports, stale unknown state without
policy, IBKR contact, connector runtime, serialized secrets, fill import side
effects, DB apply, routed orders, Bybit path reuse, live/tiny-live authority,
margin/short/options/CFD requests, and Python direct broker writes. This contract
does not import fills; it defines the evidence-safe request shape future fill
import code must satisfy before lifecycle reconstruction or DB persistence.

## 9C. `stock_etf_shadow_signal_request_v1`

Required fields:

- exact contract id `stock_etf_shadow_signal_request_v1`
- `source_version=1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- `environment=shadow`
- `request_method=evaluate_shadow_signal`
- `operation=shadow_signal_emit`
- `authority_scope=shadow_only`
- `effect_capable=false`
- request id
- evaluation run id
- shadow signal id
- evidence clock hash
- PIT universe contract hash
- strategy hypothesis hash
- instrument identity hash
- market-data provenance hash
- cost model version hash
- asset-lane event contract hash
- source artifact hash

Source validator:
`openclaw_types::stock_etf_shadow_signal_request::StockEtfShadowSignalRequestV1`.
The validator rejects wrong lane/broker/environment, method/operation/scope/
effect mismatches, missing signal identity, missing lineage hashes, IBKR
contact, connector runtime, serialized secrets, shadow signal emission, shadow
fill generation, scorecard writer startup, DB apply, routed orders, Bybit path
reuse, live/tiny-live authority, margin/short/options/CFD requests, and Python
direct broker writes. This contract does not emit a shadow signal or generate a
fill; it defines the evidence-safe request shape future shadow evaluation code
must satisfy before any collector or scorecard path can exist.

## 10. `ibkr_paper_order_lifecycle_v1`

Required fields:

- `lifecycle_contract_id=ibkr_paper_order_lifecycle_v1`
- `event_log_contract_id=broker_lifecycle_event_log_v1`
- `request_contract_id=stock_etf_paper_order_request_v1`
- `source_version=1`
- `event_sequence`
- `genesis_event`
- `previous_event_hash`
- `event_hash`
- `request_envelope_hash`
- `stale_state_policy`

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

Operation-bound transition policy:

- submit operations may only cover local intent, Rust authority acceptance,
  broker submit request, broker acknowledgement, submit rejection, submit
  unknown-state, or manual-review transitions.
- cancel operations may only cover cancel request, cancel acknowledgement,
  cancel unknown-state, or manual-review transitions.
- replace operations may only cover replace request, replacement
  acknowledgement/rejection, replacement unknown-state, or manual-review
  transitions.
- fill-import operations may only cover partial/full fill, inactive state, or
  reconciled terminal-state transitions.
- denied events may not advance an order into an active broker state.
- non-genesis lifecycle events require a valid previous event hash; genesis
  events must be sequence `1` and have no previous event hash.

## 11. `broker_lifecycle_event_log_v1`

Append-only event fields:

- `lifecycle_contract_id`
- `event_log_contract_id`
- `source_version`
- `event_id`
- `event_sequence`
- `genesis_event`
- `event_time`
- `previous_event_hash`
- `event_hash`
- `request_contract_id`
- `request_envelope_hash`
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
- `stale_state_policy`
- `raw_artifact_hash`
- `redacted_summary_hash`

Lifecycle events are atomic evidence. Daily summaries and scorecards are derived artifacts only.

### 11A. `audit.asset_lane_events_v1`

Immutable event references must cover cross-phase stock/ETF lane evidence, not
only order lifecycle events. Required fields:

- schema version
- source version
- event id and event kind
- sequence number
- genesis marker or previous event hash
- event time
- producer commit
- actor and source
- `asset_lane`, `broker`, `environment`, `operation`, and permission scope
- account and session fingerprint hashes only
- decision id and order intent id, using explicit not-applicable markers when absent
- allowed flag and denial reason invariant
- payload hash
- raw artifact hash
- redacted summary hash
- source artifact hash
- input artifact hashes

Rules:

- schema version must be exactly `audit.asset_lane_events_v1`.
- source version must be `1`.
- `asset_lane` must be `stock_etf_cash`.
- `broker` must be `ibkr`.
- live environment is denied.
- non-genesis events require a valid previous event hash.
- allowed events must not carry denial reason.
- denied events must carry denial reason.
- raw payloads and secret contents must never be serialized inline.

Source validator: `openclaw_types::stock_etf_audit_events::StockEtfAssetLaneEventV1`.
The validator requires exact `audit.asset_lane_events_v1` schema version,
source version `1`, immutable hash-chain shape, lane/broker/environment
binding, artifact hashes, allowed/denied denial-reason invariants, and redaction
boundaries. This validator writes no audit row and does not apply the DDL.

## 12. `stock_etf_db_evidence_ddl_v1`

Required fields:

- `contract_id=stock_etf_db_evidence_ddl_v1`
- `source_version=1`
- `source_only=true`

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

Source validator: `openclaw_types::stock_etf_db_evidence_ddl::StockEtfDbEvidenceDdlContractV1`.
The validator requires exact `stock_etf_db_evidence_ddl_v1` contract id, source
version `1`, the source-only SQL path, required `broker` / `research` /
`audit` schemas, all required tables, natural-key declarations, stock/ETF
asset-lane checks, IBKR broker checks, live-environment denial, paper/shadow
table separation, synthetic shadow checks, raw artifact hash retention,
`audit.asset_lane_events`, forward-only evidence retention, destructive cleanup
rollback denial, Guard A/B/C requirements, and future E2/E4 + Linux PG dry-run
and double-apply requirements. It rejects copied migration paths,
`sql/migrations/` promotion claims, DB apply, PG writes, sqlx registration,
PM/Operator apply authorization claims, and serialized secret content.

## 13. `stock_market_data_provenance_v1`

Required on every market-data fact:

- `contract_id=stock_market_data_provenance_v1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- read-only, paper, or shadow environment only
- `source_version=1`
- source vendor/broker
- entitlement tier
- raw payload hash
- received time
- exchange time when available
- adjusted/unadjusted marker
- corporate-action adjustment version
- symbol and instrument identity hash
- calendar session id
- source artifact hash
- Bybit-live unchanged proof
- no IBKR contact, connector runtime, serialized secret content, tiny-live, or
  live authorization claim

Unknown provenance blocks scorecard readiness.

Source validator:
`openclaw_types::stock_etf_phase3_evidence::StockMarketDataProvenanceV1`.
The validator requires exact `stock_market_data_provenance_v1` contract id and
source version `1`. It rejects wrong lane/broker/environment, missing
vendor/entitlement/timestamps/symbol/calendar/hash evidence, unknown adjustment
marker, missing source artifact hash, Bybit-live regression, IBKR contact,
connector runtime, serialized secrets, and tiny-live/live authority.

## 13A. `stock_etf_reference_data_sources_v1`

Corporate-action, FX, fee, and tax/FTT source records must be
machine-checkable before Phase 3 evidence-clock days, shadow-fill
reconstruction, or scorecards can consume their hashes.

Required fields:

- `contract_id=stock_etf_reference_data_sources_v1`
- `source_version=1`
- `asset_lane=stock_etf_cash`
- `broker=ibkr`
- read-only, paper, or shadow environment only
- evidence-clock freeze flag
- corporate-action source name, as-of timestamp, raw payload hash,
  adjustment-version hash, policy hash, and dividend-treatment hash
- FX rate source name, as-of timestamp, USD base/quote currency pair in v1,
  FX snapshot hash, and FX drag model hash
- fee schedule source name, as-of timestamp, commission schedule hash,
  exchange/regulatory fee hash, tax/FTT placeholder hash, and withholding-tax
  treatment hash
- source artifact hash
- Bybit-live unchanged proof
- no IBKR contact, connector runtime, serialized secret content, tiny-live, or
  live authorization claim

Source validator:
`openclaw_types::stock_etf_reference_data_sources::StockEtfReferenceDataSourcesV1`.
The validator requires exact `stock_etf_reference_data_sources_v1` contract id
and source version `1`. It rejects missing source names, zero as-of timestamps,
malformed hashes, non-USD v1 currency treatment, missing evidence-clock freeze,
live environment, live/tiny-live authority, prior IBKR contact, connector
runtime, serialized secrets, and any Bybit live regression.

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

Source validator: `openclaw_types::stock_etf_scorecard_inputs::BrokerAccountPortfolioCashLedgerV1`.
The validator requires exact `broker_account_portfolio_cash_ledger_v1` contract
id and source version `1`, and rejects non-`stock_etf_cash`, non-IBKR,
live-denied environments, missing source hashes, and missing as-of/currency
fields.

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

Source validator: `openclaw_types::stock_etf_scorecard_inputs::StockEtfCostModelVersionV1`.
The validator requires exact `cost_model_version_v1` contract id, source
version `1`, commission, exchange/regulatory fee, spread, slippage, FX drag,
tax/fee placeholder, version hash, and conservative penalty inputs.

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

Source validator: `openclaw_types::stock_etf_scorecard_inputs::StockEtfBenchmarkVersionV1`.
The validator requires exact `benchmark_versions_v1` contract id, source
version `1`, source, construction, rebalance, currency, corporate-action,
matched-control, and version hashes.

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

Source validator: `openclaw_types::stock_etf_scorecard_inputs::StockShadowFillModelV1`.
The validator requires exact `stock_shadow_fill_model_v1` contract id, source
version `1`, `synthetic_shadow=true`, rejects broker-paper/live fill links, and
requires conservative fill or explicit rejection evidence.

## 18. `stock_etf_evidence_clock_v1`

Clock start requires:

- IBKR read-only/paper connector green for 5 trading days
- shadow collector green for 5 trading days
- accepted `stock_etf_pit_universe_contract_v1` and frozen universe hash
- frozen benchmark hash
- frozen cost model hash
- accepted `stock_etf_strategy_hypothesis_contract_v1` and frozen strategy hypothesis hash
- accepted `stock_etf_reference_data_sources_v1` and frozen corporate-action /
  FX / fee / tax source-as-of hash
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

Source validator:
`openclaw_types::stock_etf_phase3_evidence::StockEtfEvidenceClockDayV1`.
The validator requires exact `stock_etf_evidence_clock_v1` contract id, source
version `1`, `stock_etf_cash` / IBKR lane binding, read-only/paper/shadow
environment, source artifact hash, market-data provenance contract hash,
scorecard input bundle hash, frozen inputs, DQ manifest shape, Bybit-live
unchanged proof, and checker-side denials for IBKR contact, connector runtime,
runtime evidence-clock start, scorecard writer, DB apply, serialized secrets,
and tiny-live/live authority. `WINDOW_COMPLETE` remains unavailable from the
source checker alone.

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

Source validator: `openclaw_types::stock_etf_gui_lane_contract::StockEtfGuiLaneContractV1`.
The validator requires exact `gui_lane_contract_v1` contract id, source version
`1`, `crypto_perp` as the default displayed lane, and these exact GET-only
display surfaces:

- `/api/v1/stock-etf/readiness`
- `/api/v1/stock-etf/lane-status`
- `/api/v1/stock-etf/phase0-status`
- `/api/v1/stock-etf/data-foundation-status`
- `/api/v1/stock-etf/policy-status`
- `/api/v1/stock-etf/authorization-status`
- `/api/v1/stock-etf/evidence-status`
- `/api/v1/stock-etf/universe-status`
- `/api/v1/stock-etf/shadow-status`
- `/api/v1/stock-etf/paper-status`
- `/api/v1/stock-etf/reconciliation-status`
- `/api/v1/stock-etf/account-status`
- `/api/v1/stock-etf/scorecard-status`
- `/api/v1/stock-etf/launch-status`
- `/api/v1/stock-etf/release-packet-status`
- `/api/v1/stock-etf/disable-cleanup-status`

The validator also requires display-only semantics, client lane
state treated as untrusted, denied localStorage/query-param/hidden-field
authority, no login-success selector, no POST/order/secret/contact surfaces,
paper-order entry hidden, stock live disabled display, CFD hidden or fail-closed,
route/cache/auth partition evidence, stale-cache cross-lane denial, existing
crypto tab regression evidence, Decision Lease/risk regression evidence, source
and test hashes, denied effect operations, `ibkr_contact_performed=false`, and
`secret_content_serialized=false`.

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

Source validator: `openclaw_types::stock_etf_scorecard_inputs::StockEtfStorageCapacityV1`.
The validator requires exact `stock_etf_storage_capacity_v1` contract id, source
version `1`, non-zero capacity estimates, lane-scoped relative archive path,
capacity-plan hash, and an explicit policy that capacity breach blocks the
evidence clock. The source validator also caps the initial paper/shadow evidence
plan to at most `1,000` instruments, `5,000,000` rows/day, `8,192` MB index
budget, and `5,000` ms query SLO; raw payload hashes must be retained at least
`365` days, compressed retention must not be shorter than raw-hash retention,
and compressed retention must not exceed `3,650` days without a new reviewed
source version.

Scorecard bundle validator:
`openclaw_types::stock_etf_scorecard_inputs::StockEtfScorecardInputBundleV1`
requires cash ledger, cost model, benchmark, shadow fill, storage capacity,
market-data provenance contract hash, reference-data source contract hash,
risk-policy contract hash, atomic fact hash, source commit, derived-only
scorecard status, paper/shadow fill separation, Bybit-live unchanged proof, and
`live_fill_claimed=false`. It rejects IBKR contact, connector runtime, broker
fill import, scorecard writer, DB apply, evidence-clock start, serialized
secret content, and tiny-live/live authority.

Downstream Phase 3 verdict validator:
`openclaw_types::stock_etf_scorecard_verdict::StockEtfScorecardVerdictV1`
requires exact `stock_etf_scorecard_verdict_v1` contract id, source version `1`,
formula appendix hash, statistical preregistration hash, scorecard/input/DQ
manifest hashes, pre-registered window and independent-observation thresholds,
paper-vs-shadow divergence threshold, benchmark/cost lower-confidence-bound
metrics, PSR/DSR-style thresholds, regime/breadth/freshness/survivorship/
execution-realism labels, and QC/MIT/QA review hashes. It can seal positive
or negative verdict labels, but it rejects IBKR contact, connector runtime,
broker fill import, scorecard writer side effects, DB apply, evidence-clock
start, secret serialization, tiny-live/live authority, and Bybit-live
regression.

## 21. `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`

Required fields:

- `runbook_id=stock_etf_kill_switch_and_disable_cleanup_runbook_v1`
- `source_version=1`

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

Source validator:
`openclaw_types::stock_etf_disable_cleanup_runbook::StockEtfDisableCleanupRunbookV1`.
The validator requires exact
`stock_etf_kill_switch_and_disable_cleanup_runbook_v1` runbook id, source
version `1`, exact disable env-flag evidence, collector stop proof, GUI
disabled/hidden proof, live-secret absence proof, forward-only evidence archive
and DB-retention proof, append-only audit preservation, and Bybit live execution
unchanged. It rejects IBKR contact, connector runtime, paper order routing,
secret-slot creation, secret serialization, destructive DB cleanup, DB
delete/truncate permission, paper-shadow launch authority, tiny-live, and live.

## 22. `stock_etf_release_packet_v1`

Release packet must include:

- exact packet id `stock_etf_release_packet_v1`
- source version `1`
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

- exact contract id `tiny_live_adr_eligibility_v1`
- source version `1`
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
