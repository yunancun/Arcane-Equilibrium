# 2026-06-29 - IBKR Stock/ETF Paper + Shadow Plan E3 Review

Role: E3(explorer)
Scope owner: security, secret handling, broker API, runtime safety
Task shape: security audit
Mode: read-only. No code/runtime edit, no Linux `trade-core` touch, no IBKR/Bybit calls, no network probes.

## Verdict

STATUS: DONE_WITH_CONCERNS

Phase 0 ADR/spec work is acceptable and should be the only approved next step. Phase 1+ implementation should not start until the findings below are resolved into machine-checkable acceptance criteria.

The proposal is directionally conservative: it says IBKR is paper/shadow only, keeps non-Bybit live disabled, keeps order-capable paths under Rust authority, and explicitly requires a new ADR before changing the current Bybit-only execution boundary. That is the right posture.

The security blocker for later phases is not intent, but enforceability. The plan does not yet fully specify how IBKR paper is cryptographically and operationally distinguished from IBKR live, how broker credentials are scoped and redacted, and how Python connector code is prevented from becoming a broker order writer.

Finding counts: 0 CRITICAL / 1 HIGH / 6 MEDIUM / 4 LOW / 5 INFO.

## Sources Read

- `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `TODO.md`
- `docs/agents/context-loading.md`
- `docs/agents/sub-agent-hygiene-sop.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/PM.md`, `.codex/agents/E3.md`
- `.claude/agents/E3.md`, `docs/CCAgentWorkSpace/E3/profile.md`, `docs/CCAgentWorkSpace/E3/memory.md`
- Latest E3 baseline: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-24--demo-learning-autonomy-runtime-e3-audit.md`
- `docs/adr/0001-rust-as-trading-authority.md`
- `docs/adr/0006-bybit-only-exchange.md`
- `docs/adr/0040-multi-venue-gate-spec.md`
- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`
- Targeted implementation context: `rust/openclaw_types/src/asset_venue.rs`, `rust/openclaw_engine/src/live_authorization.rs`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py`, `rust/openclaw_engine/src/bybit_rest_client.rs`, and existing public/private quote redaction envelope examples.

Note: `.claude/agents/E3.md` normally asks E3 to append a short memory entry after a report. I did not do that because the task explicitly allowed modifying only this report.

## Findings

| Severity | ID | Area | Finding | Required resolution |
|---|---|---|---|---|
| HIGH | E3-IBKR-01 | Paper/live binding | The plan says `OPENCLAW_IBKR_PAPER_ENABLED=1` enables paper order rehearsal and `OPENCLAW_IBKR_LIVE_ENABLED=0` keeps live closed, but it does not yet require broker-reported paper-account attestation before any order-capable call. A host/port/session/account-mode misconfiguration could make a "paper" code path talk to a live IBKR session. | Before Phase 2 order rehearsal, require a Rust-side pre-order invariant: broker account/session response proves `broker=ibkr`, `environment=paper`, expected account fingerprint, allowed host/port, and no live slot. Mismatch must fail before order intent construction. Bind that proof into the paper authorization envelope and audit row. |
| MEDIUM | E3-IBKR-02 | External secret slots | The proposed `$OPENCLAW_SECRETS_DIR/external/ibkr/{readonly,paper,live}/` slots are directionally correct, but the contract is underspecified. Existing Bybit settings code uses an explicit slot whitelist, chmod 700 dirs/600 files, and no arbitrary path input. IBKR must not regress to path strings or env-var fallback. | Define exact filenames, permissions, ownership, TTL/rotation, fingerprint algorithm, and no-env-fallback rule. Keep `live/` absent or empty and make its presence with credential material a startup/healthcheck failure. GUI/API should use typed slot enums only, never user-supplied paths. |
| MEDIUM | E3-IBKR-03 | Authorization schema | The plan correctly says not to reuse Bybit live authorization, but the first-stage read-only/paper envelope is not detailed enough. Current Rust `LiveAuthorization` signs only tier/time/operator/system mode/env labels and has no `asset_lane`, `broker`, `environment`, `permission_scope`, or secret-slot fingerprint. | Make the paper/read-only authorization schema a Phase 0 deliverable, not a Phase 2 detail. Required signed fields: `asset_lane=stock_etf_cash`, `broker=ibkr`, `environment=readonly|paper`, `permission_scope`, `secret_slot_fingerprint`, account/session fingerprint, expiry, operator, and immutable no-live/no-transfer/no-margin/no-short/no-options flags. |
| MEDIUM | E3-IBKR-04 | Non-Bybit API policy | The plan says to define non-Bybit API policy, but it does not yet list allowed IBKR endpoints/actions, transport limits, redirect policy, request count, rate limits, or raw-response persistence rules. Existing Bybit public/private capture helpers use explicit allowlists and sanitized artifacts; IBKR needs the same before any call. | Phase 0 ADR must include an IBKR API allowlist by method/action and environment. Deny by default: transfer, withdrawal, margin, short, option, CFD, live order, account-management write, broad account enumeration. Require bounded timeouts, no redirects, TLS verification, rate limits, single-purpose invocation IDs, and sanitized artifact schemas. |
| MEDIUM | E3-IBKR-05 | Python connector boundary | The proposed `broker_connectors/ibkr_connector/paper_client.py` is acceptable only if it cannot become an order writer. The same plan also mentions "paper-only order lifecycle rehearsal", which could tempt a direct Python order method. That would conflict with ADR-0001 if Python submits broker orders outside Rust authority. | Enforce structurally: Python may read health/snapshots/import fills/fixtures. Any broker order placement/cancel/replace method must either not exist in Python or be a thin IPC caller that cannot sign or send broker requests. Add tests/grep guards rejecting Python `place_order`, `cancel_order`, `replace_order`, or broker write endpoints outside the Rust-owned adapter path. |
| MEDIUM | E3-IBKR-06 | Redaction and argv/log leaks | The plan includes "secrets not in argv/log", but the acceptance criteria do not specify how IBKR auth tokens, session IDs, account IDs, request signatures, local paths, raw HTTP errors, and broker payloads are sanitized. Existing redaction work is L2/Bybit-specific and should not be assumed to cover IBKR. | Define a broker-agnostic redaction policy before Phase 2: no secrets in argv, no auth headers in artifacts, no raw request signatures, no cookies/session tokens, path redaction, account-id masking/fingerprinting, error classification instead of `str(e)`, raw-response hash only after deciding it cannot become a secret oracle, and regression tests with synthetic IBKR-like credentials/session strings. |
| MEDIUM | E3-IBKR-07 | Runtime/deploy surface | The plan does not specify where IBKR Gateway/TWS or equivalent API process runs, how local ports are bound, how service units are isolated, or how trade-core avoids becoming a second uncontrolled broker terminal. This is a runtime attack surface separate from code. | ADR/spec must define deployment topology before any runtime work: no Linux cargo/build by subagents, no service restart outside PM deploy path, local-only broker API bind, firewall/Tailscale posture, dedicated user or sandbox if applicable, startup healthcheck that proves paper mode, and kill switch behavior. No IBKR process should be installed on `trade-core` without a separate E3 runtime review. |
| LOW | E3-IBKR-08 | GUI lane selector | The plan says the GUI lane selector is not authority, which is good. It still needs a testable guarantee that lane selection cannot grant broker permissions, mutate authorization, or change the execution environment. | Treat the selector as a read/query filter plus UX state only. Mutating actions must carry signed server-side lane/broker/environment context. Add static and route tests proving hidden fields or client-side lane changes cannot authorize orders. |
| LOW | E3-IBKR-09 | Type/enum boundary | Existing `Venue` enum only reserves Bybit/Binance and explicitly rejects catch-all venue strings. The plan proposes a new `BrokerVenue`/`AssetLane` layer, which is probably the right approach, but it must preserve the no-string-routing invariant. | New broker/asset lane types must be enums without `Other(String)` catch-alls. Unknown broker, CFD, margin, short, options, and IBKR live must parse to fail-closed errors until a future ADR explicitly enables them. |
| LOW | E3-IBKR-10 | Evidence data minimization | Proposed broker schemas store instruments, account snapshots, orders, fills, commissions, FX, and scorecards. That is reconstructable, but it may also persist account identifiers and broker metadata more widely than needed. | Store account IDs as stable salted fingerprints where possible; expose masked IDs in GUI; keep raw broker payloads out of durable tables unless separately justified; set retention/export rules for broker account metadata. |
| LOW | E3-IBKR-11 | Paper credentials scope proof | The plan forbids transfers, margin, short, options, CFD, and live, but it does not require machine-readable proof of actual broker permission scope for readonly/paper credentials. | Add a permission-scope check artifact: credential can read only approved data and paper-trade only approved cash stock/ETF instruments; transfer/withdraw/live/margin/options permissions must be absent or ignored with fail-closed evidence. |

## Positive Controls

| Severity | ID | Control | Assessment |
|---|---|---|---|
| INFO | E3-IBKR-I01 | Phase 0 first | The plan explicitly recommends Phase 0 ADR/spec only, with no runtime, no IBKR API calls, and no live-boundary edit before approval. This is the correct next step. |
| INFO | E3-IBKR-I02 | Live disabled intent | The plan repeatedly forbids IBKR live, non-Bybit live, margin, short, options, CFD, and transfers. Intent is conservative; the missing part is machine enforcement. |
| INFO | E3-IBKR-I03 | Rust authority | The plan correctly states any order-capable path must remain under Rust authority and Python may only forward/read. This aligns with ADR-0001. |
| INFO | E3-IBKR-I04 | External secret slot direction | `external/ibkr` slot separation follows the ADR-0040/H-21 precedent. With the extra constraints above, it is the right storage direction. |
| INFO | E3-IBKR-I05 | Evidence separation | The plan distinguishes broker paper fills from synthetic shadow fills and says IBKR paper does not equal live proof. This is necessary and should be retained. |

## Gate Verdict By Topic

| Topic | Verdict |
|---|---|
| External IBKR secret slots | PASS WITH CONDITIONS. Use typed external slots, exact files/permissions, no env fallback, no live material, and slot fingerprint binding. |
| Live-disabled invariant | NOT YET MACHINE-CHECKABLE. Good intent, but needs broker-reported paper attestation and a hard failure on any live IBKR session or live credential material. |
| Paper API credentials | PASS WITH CONDITIONS. Paper credentials must be scoped, fingerprinted, non-transfer/non-live, and never reused as live authorization. |
| Redaction | NEEDS SPEC. Require broker-agnostic secret/session/account redaction before any IBKR artifact or log writer. |
| argv/log leaks | NEEDS SPEC. Ban secrets in CLI args, process env dumps, curl args, exception strings, raw request artifacts, and service logs. |
| Non-Bybit API policy | NEEDS ADR DETAIL. Endpoint/action allowlist and transport policy must exist before the first IBKR call. |
| Paper order execution authority | PASS WITH CONDITIONS. Rust-only authority must be enforced structurally; Python must not directly send broker order/cancel/replace requests. |
| Python connector boundary | NEEDS GUARDS. Read/import helpers only unless routed through Rust IPC authority with tests proving no direct write path. |
| GUI lane selector | PASS WITH CONDITIONS. Selector can be UX/query state only; server-side signed context remains authority. |
| Runtime/deploy | NEEDS SEPARATE E3 REVIEW. No broker gateway/process/service on `trade-core` without a specific runtime topology and PM-owned deploy review. |

## Recommended Acceptance Criteria Before Phase 1

1. Accepted ADR/AMD that amends the current Bybit-only boundary only for `stock_etf_cash` read-only/paper/shadow research, not live.
2. `BrokerVenue`/`AssetLane` enum contract with no string catch-all and explicit fail-closed states for IBKR live, CFD, margin, short, options, and unknown brokers.
3. IBKR secret-slot contract: exact path/files, chmod 700/600, no env fallback, live slot absent/empty, fingerprint bound to authorization, rotation/TTL rules.
4. IBKR API allowlist: methods/actions/endpoints, host/port, redirect/TLS/timeout/rate-limit policy, no transfer/withdraw/live/margin/options/CFD actions.
5. Paper session attestation: broker response proves paper environment and expected account fingerprint before any order-capable code can construct an order request.
6. Paper/read-only authorization envelope schema with lane/broker/environment/scope/fingerprint/expiry/operator fields and no reuse of Bybit `authorization.json`.
7. Python connector negative guard: no direct broker order/cancel/replace methods or routes outside Rust-owned IPC authority.
8. Redaction regression suite for IBKR-like keys, session tokens, cookies, account IDs, signatures, local paths, tracebacks, and raw broker errors.
9. Runtime topology spec for IBKR Gateway/TWS or equivalent, with local binding, process ownership, service policy, kill switch, and no trade-core deployment without E3 review.

## Final Position

Approve only Phase 0 ADR/spec work.

Do not approve Phase 1+ implementation, IBKR credential entry, IBKR healthcheck calls, paper order rehearsal, runtime service installation, GUI lane activation, or any broker API contact until the HIGH finding and the MEDIUM findings are converted into reviewed, testable gate criteria.

E3 AUDIT DONE: 0 CRITICAL / 1 HIGH / 6 MEDIUM / 4 LOW / 5 INFO - report path: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md`
