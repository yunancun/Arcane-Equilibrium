# AMD-2026-07-08-01: IBKR Stock/ETF Phase 2 Read-Only External-Contact Authorization

Date: 2026-07-08
Status: **Active - Phase 2 read-only external-contact authorization**
Related ADRs: ADR-0033, ADR-0040, ADR-0047, ADR-0048.
Related AMD: AMD-2026-06-29-01 (which this amendment extends).
Scope: `stock_etf_cash` read-only research lane only. This amendment does **not** touch the Bybit `crypto_perp` runtime path.

> Provenance: accepted after a PM→CC→FA→PA feasibility assessment (2026-07-08) returning `CERTIFIABLE_IF_GATES_PASS`. This amendment is the governance unlock those legs identified; nothing in the phased build (P0+) may begin before the gated sequence below is satisfied in order.

## Decision

Amend ADR-0048 to authorize the `stock_etf_cash` lane to progress from source-only Phase 0/1 into **Phase 2 read-only external contact with IBKR**, and to make the two boundary revisions that progression requires, all under an unchanged fail-closed posture:

1. **Authorize Phase 2 external-contact scope** for read-only IBKR access only (connection health, account summary, portfolio positions, contract details, market-data snapshots), gated by the existing `phase2_ibkr_external_surface_gate_v1` PASS artifact and the `stock_etf_ibkr_readonly_probe_request_v1` probe contract.
2. **Revise the SDK/socket static-guard hard boundary** narrowly and explicitly (see "Static-Guard Boundary Revision") to permit a Rust-owned, gated, read-only TWS API client — and **only** that. The Python no-write / no-SDK guard is **not** revised and remains in full force.

This amendment does **not** approve any IBKR live, tiny-live, margin, short, options, CFD, transfer, account-management, or **order-write** surface (including paper order writes). Live/tiny-live remains categorically denied. Zero real money. Read-only only.

## Static-Guard Boundary Revision (the single hard-boundary change)

ADR-0048 Mandatory Phase Gates and AMD-2026-06-29-01 forbid `ibapi`/`ib_insync` imports and socket/HTTP sessions "until a later Rust-authority contract explicitly revises that boundary." This amendment is that contract, and it revises the boundary **minimally**:

- **Permitted (new):** a single named Rust module inside `openclaw_engine` may implement a **read-only** subset of the native TWS API wire protocol (connect handshake + `reqCurrentTime` / `reqAccountSummary` / `reqPositions` / `reqContractDetails` / `reqMktData` snapshot), speaking to **IB Gateway paper mode on loopback `127.0.0.1:4002` only**.
- **Unchanged / still forbidden:**
  - The **Python** no-write / no-SDK / no-socket guard (`test_stock_etf_python_no_write_static_guard.py`, `stock_etf_static_guard_helpers.py`) remains in force. Python stays display-only + thin Rust IPC caller. No Python IBKR SDK import anywhere.
  - The `openclaw_types` Rust source-only guards (`ibkr_*.rs` must stay net-free) remain. The new client lives in the **engine** crate, never in the types crate.
  - Live gateway port `4001` and live TWS port `7496` remain denied. Client Portal Web API remains denied.
  - No write/order/paper-order-write method may be added. `FORBIDDEN_FUNCTION_NAMES` / `FORBIDDEN_IPC_METHOD_STRINGS` remain and are never removed.

Any change to a static guard beyond the single permission above is out of scope of this amendment and would itself be an unauthorized hard-boundary change.

## CI Enforcement Prerequisite (blocks all Phase 2 work — CC finding, MEDIUM)

Before any Phase 2 code merges, the `stock_etf` static guards (GET-only, no-write, no-Python-SDK) must be wired into hosted CI. They previously ran only in the E4 pytest suite, not in `.github/workflows/ci.yml`; an emergency merge that skips E4 would not be machine-blocked from introducing a forbidden import on this external-contact/secret/SDK boundary.

- Add a `stock-etf-static-guards` GitHub Actions job (ubuntu-latest, PR-triggered only, single runner — consistent with the 2000-min/month cost policy) running the stock_etf static-guard tests.
- This job must be green as a precondition of the first Phase 2 (P0) merge.

## API Baseline (reaffirmed)

Unchanged from AMD-2026-06-29-01: IB Gateway + TWS API protocol; loopback-only session on `trade-core`; paper gateway port only (live ports denied); first contact gated by `phase2_ibkr_external_surface_gate_v1`; health/account/contract-details/market-data probes also satisfy `stock_etf_ibkr_readonly_probe_request_v1`.

## Secret Boundary (reaffirmed + operationalized)

- Create the previously-allowed slots `$OPENCLAW_SECRETS_DIR/external/ibkr/{readonly,paper}/` via a Rust, engine-side **fingerprint-only** loader (stat + owner-only-permission check; emit `secret_slot_fingerprint` sha256 + `account_fingerprint_hash`; never serialize credential material or account id into any IPC / DB / log surface).
- `$OPENCLAW_SECRETS_DIR/external/ibkr/live/` remains **denied and must stay absent**. If live credential material is found, healthcheck fails closed and emits a typed blocker. Environment-variable credential fallback remains denied.
- Live denial is structural: the `FeatureFlagSecretAuthMatrixV1` fingerprint triangulation (secret-slot contract ∧ session attestation ∧ sealed gate artifact must agree on one non-live account fingerprint) is the real authorization mechanism.

## Runtime Boundary (Rust authority; normalizer lockstep)

- Rust remains the trading, risk, strategy-config, and execution authority. The new read-only connector is Rust-owned in `openclaw_engine`. Python exposes read-only status + a thin Rust IPC caller only.
- The account/status normalizer (`stock_etf_account_normalizers.py`) is a negative-space attestation gate: it currently flags **any** populated value as a `contract_violation`. At Phase 2 activation it must evolve **in lockstep with the Rust emitter, in the same PR**, from "any real value = violation" to "real value **without** a valid PASS + session-attestation lineage = violation." When the sealed Phase-2 gate artifact is absent, the all-false fail-closed posture must still be enforced (a fail-closed regression test with gate=BLOCKED must still flag any injected real value).
- The dormant risk config `settings/risk_control_rules/risk_config_stock_etf_paper.toml` is wired into Rust via the already-existing `StockEtfRiskPolicyV1::from_source_config()` so displayed risk config becomes the enforced source-of-record and `risk_config_hash` derives from a real file. This does not enable any order path; the lane stays `enabled=false`, `shadow_only=true`.

## GUI Real-Data Display is a Separate Phase 4 (do not co-sign)

Rendering real IBKR account/positions/orders/market-data in the GUI is governed by `gui_lane_contract_v1` (route/cache/auth negative tests; GET-only; client lane state untrusted) as an independent Phase 4 gate. It must not be co-signed with this Phase 2 external-contact authorization. Independent of this AMD, the current GUI "fake $0.00 account" honesty defect (`tab-stock-etf-auth-account.js`: rendered `cash=0` when `account_snapshot_present:false`) is fixed under this same change set to gate numerics behind `present && accepted`.

## Invariants That Never Loosen

1. IBKR live / tiny-live categorically DENIED (typed policy, not a "five-gate minus one" — no IBKR live gate is ever built).
2. Zero real money; read-only lane; no capital exposure.
3. No order-write surface of any kind (including paper order writes) in this authorization.
4. No fake-success: the first and every IBKR read is a real call or fails closed; no fabricated green healthcheck.
5. Read/write separation: Python display-only; Rust owns all writes/authority; client lane state (localStorage/query/hidden form) is never authorization.
6. Live secret slot absent + env-var credential fallback denied.
7. Bybit `crypto_perp` live execution path unchanged (a "bybit-live-unchanged" proof is required at each gate).
8. No DB migration / apply in read-only scope; source-only DDL stays gated by separate migration authorization.
9. No automatic promotion; positive paper/shadow evidence may only open a future `tiny_live_adr_eligibility_v1` discussion, which is discussion-only and requires a further ADR.
10. No market-data entitlement purchase; Client Portal Web API denied.

## Compliance-Gated Sequence (no step begins before the prior signs off)

| Gate | Content | Sign-off (order) |
|---|---|---|
| G0 | This AMD accepted | Operator (accept) · PM · CC→FA→PA compliance |
| G0.5 | `stock-etf-static-guards` CI job wired + green | E1→E2→E4 · CC confirm |
| P0 | Risk TOML → Rust loader (displayed = enforced source-of-record) | E1→E2→E4 (Linux cargo) |
| P1 | Fingerprint-only secret-slot loader; prove live slot absent | E1→E2→E4 · E3→BB→Operator (slot creation) |
| P2 | Phase-2 external-surface gate producer; seal immutable PASS artifact | E1→E2→E4→BB→E3→QA→CC/FA→PM |
| G4 | **First external contact** (health/server-time read = external contact) | **Operator one-time explicit approval** + BB + E3; QA captures runtime evidence |
| P4 | Dispatch fork + `get_connection_health` IPC/route + normalizer lockstep | E1→E2→E4→QA |
| P5 | Account/positions/open-orders reads + session attestation | E1→E2→E4→QA · CC audit lineage |
| P6 | Market-data + contract-details reads (needs new positions-row + quote/bar-row contracts) | E1→E2→E4→QA |
| Phase 4 | GUI real-data runtime (`gui_lane_contract_v1`) — separate | E1→E2→E4→QA→PM |

## Required Source-of-Truth Updates (on acceptance)

Minimal stable-boundary wording updates, preserving the Bybit runtime path and marking IBKR as read-only Phase 2:
- `CLAUDE.md` (§一 boundary line references AMD-2026-07-08-01; read-only Phase 2 external contact authorized; live/tiny-live still denied)
- `README.md`
- `docs/_indexes/document_index.md`, `docs/_indexes/initiative_index.md`
- `docs/governance_dev/SPECIFICATION_REGISTER.md`
- `TODO.md` (explicit next row: G0.5 CI guard → P0 risk-config wiring)

## Completion Criteria

This AMD is complete (Accepted) when:
1. Operator accepts (sign-off table below).
2. Stable boundary docs distinguish active Bybit execution from IBKR read-only Phase 2 external contact.
3. TODO carries an explicit next row for G0.5 + P0 without implying any write/live enablement.
4. PM and Operator checkpoint reports exist.
5. Verification confirms no live secret, no order-write surface, no Bybit path regression, and no DB migration were introduced by the amendment itself (the amendment authorizes the phased build; it does not itself perform it).

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | Approved the drafted amendment to authorize Phase 2 read-only external contact + narrow SDK/socket guard revision | 2026-07-08 | **Accepted — read-only Phase 2 external contact only** |
| PM | AMD drafting + materialization from PM→CC→FA→PA assessment | 2026-07-08 | Active |
| CC | Compliance mapping (16 principles / 9 invariants / 5 hard gates) | 2026-07-08 | `CERTIFIABLE_IF_GATES_PASS` · 0 BLOCKER · 1 MEDIUM (CI drift, addressed by G0.5) |
| FA | Functional spec + acceptance criteria | 2026-07-08 | `CERTIFIABLE_IF_GATES_PASS` · gaps: positions-row + quote/bar-row contracts, `$0` honesty fix (fixed) |
| PA | Architecture + phased workplan (P0–P6) | 2026-07-08 | FEASIBLE inside boundary; Rust-owned engine connector |
| E3 / BB / QA | Secret custody / external-facing / runtime acceptance | — | Pending at G1/G3/G4 |

## Post-Acceptance Clarification (2026-07-09, non-substantive — CC-ruled materialization)

Provenance: P1 build kickoff PM→PA (tech design) → E3 (security review, 0 CRITICAL / 0 HIGH) → CC (compliance ruling, Conditional Approve). This clarification touches only path-token wording; it does **not** modify the Decision, Static-Guard Boundary Revision, Secret Boundary constraints, Invariants, or Sign-off above.

In the Secret Boundary section, `$OPENCLAW_SECRETS_DIR` denotes the **secrets root** (the parent of `secret_files/`); the IBKR slots therefore resolve to `<secrets-root>/external/ibkr/{readonly,paper}/`, with `<secrets-root>/external/ibkr/live/` denied and absent. On `trade-core` this materializes to `/home/ncyu/BybitOpenClaw/secrets/external/ibkr/...`. Because the pre-existing Bybit code (`read_secret_file`, `authorization_path`) already uses the env var `OPENCLAW_SECRETS_DIR` with a **different** meaning — the `secret_files/bybit` root — the fingerprint-only IBKR loader **must not overload** `OPENCLAW_SECRETS_DIR`. It resolves the IBKR base dir from a **distinct locator** (`OPENCLAW_SECRETS_ROOT` if set, else `$HOME`/`$USERPROFILE` `/BybitOpenClaw/secrets`) joined with `external/ibkr`, so that both the env-set and fallback branches are secrets-root-based and internally consistent. The env var is a base-directory **locator only** and is never a credential source; `env_var_credential_fallback_denied` remains a hard-coded constant `true`, and the loader never reads credential material or account id from any environment variable. This clarification changes no protected quantity of the Secret Boundary (slot locations, live-denial, fingerprint-only posture, and credential-fallback denial are all unchanged); it corrects a path-token shorthand to match runtime reality and eliminates a false-live-absent pathway. No re-approval of the Secret Boundary is required; Operator acknowledgement only.

## Post-Acceptance Clarification #2 — P2 gate-seal Operator-approval security model (2026-07-09, non-substantive — CC-ruled materialization)

Provenance: P2 build PM→PA (tech design) → E3 (security review, 0 CRITICAL / 1 HIGH / 3 MEDIUM, empirical `OPENCLAW_DATA_DIR`) → CC (compliance ruling, Conditional-Approve B; finding-2 waiver granted) → E1 → E2 (APPROVE, 0 blocker post-waiver) → E4 (Linux cargo PASS). This clarification documents the approval-security-model decision for the P2 external-surface gate producer; it does **not** modify the Decision, Static-Guard Boundary Revision, Secret Boundary, Invariants, or Sign-off above.

**Decision (CC-ruled).** The Operator sign-off that lets the P2 producer seal an immutable PASS artifact uses an **owner-only approval file + binding model (option A)**, not HMAC-signed parity with `authorization.json` (option B). Rationale: this is a **governance-evidence sign-off on a read-only / zero-money path** (a different authorization axis from CLAUDE.md §四#5, which governs live-money execution); its worst-case failure is a premature loopback:4002 paper read, not a live order (live ports 4001/7496 structurally denied, live secret slot absent, no order-write, and G4 first contact needs an independent one-time Operator approval). Under the same-`ncyu`-uid threat model, HMAC adds ≈0 cryptographic protection (the signing key is same-uid readable), so requiring (B) here would be a net-negative over-gate.

**Approval model = 6 bindings** (any missing → fail-closed, Operator role not injected, no seal): owner-only `0o600` file + `0o700` owner-only ancestor chain + symlink-reject; `source_commit == BUILD_GIT_SHA` (anti-replay); `adr == ADR-0048` ∧ `amd == AMD-2026-07-08-01` (the approval references the **contact-authorization** AMD); expiry/freshness window (clock-guard fail-closed); approval lineage recorded into the sealed artifact hash coverage; producer **never self-injects** "Operator". Defense-in-depth is the dual Operator gate (approval file for the seal + independent G4 approval for first contact) plus structural read-only denials and tamper-evident lineage — **not** an HMAC stand-in.

**Immutable artifact storage.** Sealed PASS artifacts write to `<OPENCLAW_DATA_DIR>/governance/ibkr_phase2/` (a persistent, owner-only, governance-evidence location in the same class as `halt_audit.log` / `boot_history.jsonl`; not a DB migration). The producer **refuses to seal** if the path resolves to an ephemeral `/tmp/*` or `OPENCLAW_DATA_DIR` is unset. The `IbkrPhase2GateArtifactV1.amd` field remains the shape-provenance constant `AMD-2026-06-29-01`; the contact-authorization AMD `2026-07-08-01` is surfaced at the report layer (`artifact_shape_amd` + `contact_authorization_amd`) and enforced via the approval binding.

**Mandatory escalation trigger.** If this owner-only approval mechanism is ever extended to a higher-consequence surface — any paper order-write, `tiny_live_adr_eligibility_v1` discussion, or any capital exposure — it **must** be upgraded to option (B): HMAC-signed via a controlled approve path with parity to `authorization.json` discipline. Option (A) is authorized **only** for the read-only / zero-money gate-seal.

**Open WAIVER-gated follow-ups** (both are hard blockers on any future "P2-seal-wiring" work that makes a production, non-test caller invoke `seal_phase2_artifact`; neither is closed by the P2 producer PR): (1) `IBKR-P2-SEAL-LINEAGE-FIELDS` — add `contact_authorization_amd` + `approval_lineage_hash` to `IbkrPhase2GateArtifactV1` (types crate, via PA→E1→E2→E4) before any production seal caller; (2) `IBKR-P2-TRIANGULATION-CROSSCHECK` — remove the unconditional topology-fingerprint overwrite in the producer and replace it with a real cross-leg equality check when either P5 session-attestation provides an independent account source or seal is wired to production, whichever is earlier. The P2 producer landed as a fail-closed scaffold with **zero runtime effect** (it never seals in production: real slots absent + no approval). No re-approval is required; Operator acknowledgement only.
