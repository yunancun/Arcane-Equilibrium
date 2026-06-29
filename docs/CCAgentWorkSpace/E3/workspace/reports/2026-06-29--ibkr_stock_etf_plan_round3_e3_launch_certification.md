STATUS: DONE
CERTIFICATION: CERTIFIABLE_IF_GATES_PASS, SCOPE=paper_shadow_only, FINDINGS=0(C:0/H:0/M:0/L:0)

# IBKR Stock/ETF Paper/Shadow Round 3 E3 Launch Certification Audit

Date: 2026-06-29
Role: E3(explorer)
Scope owner: security/secrets/runtime launch certification
Mode: report-only. No code, runtime, TODO, IBKR, Bybit, Linux, PG, services, secrets, or network actions were performed.

## Decision

E3 can certify `stock_etf_cash` paper/shadow launch security/runtime readiness if all hardened gates pass exactly as written and produce immutable artifacts with hashes.

This is a conditional certification path, not a statement that the current repo is already launch-ready. The current plan still describes a design proposal and Phase 0 packet; the round-two reports explicitly did not certify current "fully online" readiness. Under the operator's narrowed interpretation, however, the remaining E3 concerns are covered if the hardened gates are actually implemented and pass: external-surface gate, session attestation, secret/redaction, API allowlist, Python no-write/Rust authority, kill switch, degraded mode, audit/reconstructability, and release packet.

Minimum missing E3 gate under the stated all-gates-pass assumption: none.

## Basis

- The plan's allowed final scope is limited to IBKR read-only healthcheck, IBKR paper order lifecycle rehearsal, shadow signal/fill/cost reconstruction, and GUI evidence viewing; it excludes IBKR live, margin, short, options, CFD, transfer, and non-Bybit live ([plan:25](/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:25)).
- Phase 0 now names the missing contract packet: API/session baseline, capability registry, allowlist, session attestation, feature/secret/auth matrix, lane IPC, order lifecycle, event log, DB/evidence DDL, GUI contract, storage/capacity, kill switch/disable cleanup, release packet, and tiny-live eligibility separation ([plan:492](/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:492)).
- E3 round two required immutable gate artifacts and hard BLOCK decisions before healthcheck, fill import, paper order rehearsal, or tiny-live ADR if any item is missing ([E3 round2:127](/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_e3_review.md:127)).
- QA's minimum launch checklist already includes accepted ADR/AMD, Phase 0 packet, source-of-truth sync, default-off flags, Rust/Python/DB/E3/attestation/evidence/GUI/kill-switch gates, and release packet artifacts ([QA round2:121](/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_qa_review.md:121)).
- Existing project hard boundaries remain in force: Bybit-only execution remains current until ADR amendment, Rust remains trading authority, Python is not the trading truth layer, true live requires the five live gates, and fake healthcheck/trading evidence is prohibited ([CLAUDE:27](/Users/ncyu/Projects/TradeBot/srv/CLAUDE.md:27), [CLAUDE:81](/Users/ncyu/Projects/TradeBot/srv/CLAUDE.md:81)).

## Security/Runtime Launch Checklist

For E3 certification, each item below must be PASS with a durable artifact path and hash.

1. Scope and ADR gate
   - Accepted ADR/AMD approves only `stock_etf_cash` read-only / broker-paper rehearsal / shadow research.
   - It explicitly denies IBKR live, tiny-live, margin, short, options, CFD, transfer, withdrawal, and any automatic promotion path.
   - Operator approval is recorded in governance docs; chat-only approval is invalid.

2. Source-of-truth sync gate
   - PM records which of ADR, README, CLAUDE, `.codex/MEMORY.md`, TODO, and role reports changed, or why no change was required.
   - `crypto_perp` remains default; stock lane flags are default OFF until their phase gates pass.

3. External-surface gate before any IBKR call
   - Exactly one API baseline is selected, or a no-order spike is explicitly scoped.
   - Process owner, host, bind address, service policy, logs, firewall/Tailscale posture, no-public-exposure rule, upgrade policy, rate limits, TLS/no-redirect/timeout behavior, renewal/expiry behavior, and raw artifact policy are accepted.
   - The first read-only healthcheck is blocked unless this manifest is PASS.

4. Secret and redaction gate
   - IBKR secret slots are exact, typed, chmod-verified, fingerprinted, no-env-fallback, TTL/rotation governed, and external to Bybit live authorization.
   - IBKR live slot is absent/empty; live material causes fail-closed healthcheck.
   - Redaction fixtures cover selected API-family credential/session/log shapes, including cookies, session ids, account ids, order ids, client ids, local paths, headers, certificates, tracebacks, and broker errors.

5. API allowlist and Python no-write gate
   - Allowed methods/endpoints/actions are exact for health/session/account/market-data/fill import/paper rehearsal as applicable.
   - Forbidden classes include order/cancel/replace outside Rust-owned paper path, account-management writes, transfer, margin, short, options, CFD, and live.
   - Python routes/connectors pass AST/grep/route tests proving no direct broker writer or generic authenticated write-helper bypass.

6. Session attestation gate
   - `ibkr_session_attestation_v1` proves broker-reported paper environment, expected account/session/host/port/process identity, secret fingerprint, permission scope, market-data tier, timestamp, expiry, and source artifact hash.
   - Paper order construction fails before intent if account/session/topology is mismatched, stale, live, unknown, or ambiguous.

7. Rust authority and final-window gate
   - Paper submit/cancel/replace rehearsal, if enabled, is Rust-owned through lane-scoped IPC, not legacy Bybit/Paper `submit_paper_order`.
   - Signed scoped paper-order envelope, Decision Lease, Guardian/risk, cost model, instrument tradability, market session, account attestation, audit sink, max notional/loss/attempt/concurrency limits, and BBO/market freshness all pass in the same final window.

8. Kill switch and degraded-mode gate
   - Kill switch overrides all IBKR flags and blocks new broker calls while preserving status/audit reads.
   - Degraded states are typed and fail closed: broker down, session expired, account mismatch, data tier insufficient, stale/unknown broker state, paper-shadow divergence, and kill-switch active.
   - Degraded mode never silently downgrades live to paper, paper to shadow, or failed paper evidence to valid shadow evidence.

9. Audit and reconstructability gate
   - `audit.asset_lane_events_v1` or equivalent immutable event refs include actor, source, asset lane, broker, environment, account/session fingerprint, permission scope, decision/order ids, payload hash, previous hash/sequence, denial reason, and artifact refs.
   - Paper order lifecycle and fill import are idempotent, duplicate-safe, stale-state safe, and route unknown state to manual review/quarantine.
   - Scorecard is derived-only; atomic facts remain the evidence source of truth.

10. Release packet gate
   - `stock_etf_release_packet_v1` includes ADR/spec paths, role reports, E2/E4/QA outputs, command transcripts, manifest JSON schemas, hash list, PG dry-run/double-apply logs if DB is in scope, redaction fixture outputs, GUI screenshots, DQ manifests, scorecard regeneration outputs, and disable/cleanup runbook paths.
   - The release packet is sufficient for PM/QA to reconstruct why every launch surface is allowed or denied.

## Explicit Exclusions

This E3 certification would not certify:

- IBKR live or tiny-live.
- Margin, shorting, options, CFD, futures, crypto stocks proxy baskets, transfers, withdrawals, or account-management writes.
- Any profitability, alpha, positive expected value, or tiny-live eligibility result.
- Legacy Paper promotion reopening.
- Bybit live/Demo/LiveDemo changes.
- GUI lane state as authority.
- Python as broker order truth.
- Any scheduled rollout where the gate artifacts are absent, stale, hash-mismatched, or only approved in chat.

## Missing Gates

Under the exact assumption in this audit question, there is no additional minimum E3 gate to add. The hardened gate set is sufficient for E3 to certify security/runtime readiness of the `stock_etf_cash` paper/shadow launch lane.

If PM asks about the current state before those artifacts pass, the answer remains not currently certifiable. The first missing gate before any IBKR call is `phase2_ibkr_external_surface_gate_v1`; before any paper order rehearsal, the additionally missing gates are `ibkr_session_attestation_v1`, lane-scoped Rust IPC/order lifecycle, Python no-write guard, scoped paper-order envelope, final-window Decision Lease/Guardian/risk/cost/session/audit checks, kill switch/degraded-mode proof, and release packet.

## PM Wording

Exact wording PM may use:

> E3 can certify `stock_etf_cash` paper/shadow launch security/runtime readiness if and only if the hardened gate artifacts all pass exactly as written: external-surface gate, IBKR session attestation, secret/redaction contract, API allowlist, Python no-write/Rust authority, kill switch, degraded mode, audit/reconstructability, and `stock_etf_release_packet_v1`. This certifies only IBKR read-only/paper/shadow surfaces. It does not authorize IBKR live/tiny-live, margin, short, options, CFD, transfer, or any profitability claim.

Forbidden wording:

- "IBKR is live-ready."
- "No omissions for production live."
- "Paper/shadow success proves profitability."
- "Positive paper/shadow result can go tiny-live."
- "GUI lane choice authorizes trading."
- "Python connector may submit/cancel/replace directly."

## Final Decision

PM-facing decision: PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS
