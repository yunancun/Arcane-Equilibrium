# Cold Audit PM Final Ruling — 2026-05-30 (campaign label "2026-05-17" re-run)

**Campaign label (operator-designated):** `2026-05-17`
**Actual run date:** `2026-05-30`
**Frozen baseline commit:** `187704f6` (branch `main`)
**HEAD at sign-off:** `cc6c54d0` (worktree churned `187704f6 → … → cc6c54d0` during the audit — all intervening commits are docs-only `[skip ci]` from a concurrent operator session; **Rust/Python source delta since 187704f6 = ZERO**, re-confirmed by CC/E3/QC/MIT/AI-E/FA).
**Canonical repo root:** `/Users/ncyu/Projects/TradeBot/srv`
**Runtime in scope:** read-only `ssh trade-core` only (engine PID 251791, `/home/ncyu/BybitOpenClaw/srv`).
**Baseline note:** `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-30--cold_audit_dispatch_baseline.md` (operator-committed, commit `d9128e22`).

---

## 1. Verdict

**PM ACCEPTS the PA validated fix plan as the authoritative output of this read-only cold audit.**

This was a RE-RUN: the prior cold audit (same prompt, campaign label "2026-05-17", executed ~2026-05-29) closed 17 P1 + 15/17 P2 + 7/7 P3 and was remediated + DEPLOYED (TODO v84; closure archive `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`). This re-run's purpose was to verify the remediation held and surface NEW issues from the 2026-05-29/30 work.

**Bottom line: the prior remediation HELD; the codebase is in good shape; there are NO P0 and NO P1 — only a small P2/P3 backlog (one gated governance item + isolated code/doc cleanups).** The system's safety-critical surfaces (5-gate live boundary, authority chain, GUI write-through-Rust, fail-closed retCode handling, ML deploy-stage gating) all passed adversarial re-audit. PA's final validation (authoritative) downgraded my draft's two P1 candidates (ADR-0046 → P2 gated; E5 file-size → P2 convention) and **REJECTED the third (E4 F-001 — see §6)**.

| Severity | Count (PA validated plan, post-dedup, post rule-10) |
|---|---:|
| **P0** | **0** |
| **P1** | **0** |
| **P2** | **5** (incl. ADR-0046, downgraded P1→P2, gated) |
| **P3** | **~8** (mostly doc-hygiene) |
| Rejected / false-positive / unproven (NOT tracked) | **6** |

Primary plan: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-30--PA--cold_audit_validated_fix_plan.md`.

---

## 2. Dispatch Compliance (and disclosed deviations)

Chain followed: **PM baseline freeze → R4/TW (index/doc map) → 10 specialist cold audits → PA validate/dedup/re-probe → PM final.** All sub-agents bound to repo roles `ROLE(codex_type)`.

Disclosed deviations (fail-loud, per CLAUDE §八 "if a role is skipped, say why"):
1. **Write-capability gap (structural):** 9 of 13 audit roles (R4, CC, FA, E3, BB, QC, MIT, AI-E, A3) have READ-ONLY toolsets (no `Write`). To satisfy the "report落盤" requirement (rule 6), CC/E3/BB/FA were run on a `general-purpose` substrate **bound to the repo role in-prompt** (identity preserved, e.g. "acting as CC(default)"); MIT/AI-E wrote via `Bash`; R4/QC/A3 returned inline and **PM persisted their verbatim content** (with a persistence note in each file). This is a flaw in the audit roster design, not in the findings. **Recommendation: future audit prompts must dispatch read-only roles on a write-capable substrate, or accept inline-return + PM-persist.**
2. **Accidental double-dispatch of CC/E3/BB:** a foreground-agent timing effect (fast tools return before agents) led me to re-dispatch; the `PRE-CHECK` no-overwrite guard caught BB#2 ("ALREADY DONE") and CC#2 deferred, so waste was bounded — and it yielded **free cross-verification** (both CC runs agreed; both E3 runs found no live bypass and each retracted a flaky-output fabrication).
3. **Session token-cap interruptions (×2):** the audit hit the Anthropic session cap twice (resets 8:20am, then 2:20pm Europe/Madrid). FA failed once at 0 tokens and was re-dispatched. Remaining batches used tighter per-agent budgets (≤120k) and Sonnet for mechanical roles (E4/E5/A3) to fit the cap.
4. **TODO.md NOT edited directly** — see §8.

---

## 3. Root-Principle Ruling

**The audit procedure itself complied with the root principles:** no fix, deploy, restart, migration, auth mutation, config/TOML/risk/strategy mutation, or trading action was performed. Only audit-report files were written.

**Codebase compliance (16 root principles + 9 safety invariants + hard boundaries):**
- **No P0 / no live breach.** CC verified the authority chain (StrategySignal→…→ExecutionReport) has no bypass / no fake lineage / no Python-only fake-success; Python live cancel-all is gone (→ Rust IPC). Principles 1/2/3/4 hold.
- **5-gate live boundary NOT bypassable** (E3, two independent runs): `all_five_live_gates_ok(require_authz=True)` enforced; `authorization.json` unforgeable (mode-600 signing key) and non-replayable (env-match + expiry + constant-time HMAC); `execution_authority` is denylist-not-auth (honored). LiveDemo skips only the mainnet gate per §四 — **not** downgraded. Hard boundaries 0 touched.
- **Only at-risk principle: #8/#10 (traceability / fact-vs-inference)** via the single P1 (ADR-0046 governance gap, §4). Gated by funding_arb being Retired-closed (`active=false` hard-lock, runtime fail-closed) → no live-money path.
- ML/Dream/Executor/Strategist do not live-order without GovernanceHub + Decision Lease (Inv-7 verified); ML stage = **shadow/advisory + demo-apply; live ML BLOCKED** (MIT). Paper is not promotion evidence (Inv-9; QC confirmed no paper→edge leak).
- No fake AI/fills/lineage/healthcheck/test detected (Inv-8): AI-invocation is HONEST and cost-ledgered (AI-E); fallbacks honestly report no-call.

---

## 4. Lead Item — ADR-0046 Governance Gap (P2, gated; was P1 in draft)

**[FACT · P2 · gated]** (PA downgraded from P1: funding_arb is hard-locked `active=false` with runtime fail-closed → zero live impact → P2; still a pre-revival blocker needing an operator governance decision.) TODO §3/§6/§8/§9 and `docs/adr/0018-funding-arb-v2-deprecation-watch.md` cite "**ADR-0046 Accepted**" as the funding_arb revive hard-gate, but `docs/adr/0046-*.md` does not exist and `SPECIFICATION_REGISTER.md` has no ADR-0046 row; the TOMLs/ADR-0018 also call the same slot "n (Proposed)" (name-split). Cross-confirmed by **R4 + CC + QC** and PA-spot-verified (`glob docs/adr/0046*`=∅).
- **Impact:** a risk-control revive gate hangs off a governance ID with no loadable artifact → a future revive path cannot load the gate, or could treat a stub as satisfying it.
- **Why not P0/higher:** funding_arb is Retired-closed with three-env `active=false` hard-lock + runtime fail-closed → no current live-money path. It is a **pre-revival blocker**, not a live defect.
- **Owner:** PA (author ADR-0046 as Proposed, or strike the "Accepted" citation) + TW (register/TODO). **Verifier:** R4 + CC. **Operator decision required** (see §7).

P2/P3 details (110009 enum mislabel, get_positions pagination, confluence DB-load guard, Stage-0R test coverage, promotion-freeze test alignment, Earn Wave-D toast, file-size hard-cap, doc-hygiene) are enumerated in the PA plan §-by-§ with file scope, tests, acceptance, owners.

---

## 5. Deep-Dive Answers (the 8 mandated directions)

1. **Source vs Runtime Drift — CLEAN.** Source delta since 187704f6 = ZERO (docs-only). `e9f01569` (TODO's "engine binary SHA") = the engine **binary content-hash**, NOT a git commit (MIT confirmed via `ssh` `sha256sum`; real build commit = `ec995160`); the earlier "missing commit" worry is REJECTED. `V104 supervised.live_audit` **never existed** (V103→V106 gap) — the prior TODO "V104 applied/checksum-frozen" was a hallucination **already self-corrected in v85**. Residual: `_sqlx_migrations` max=115 + basis_panel row-recency need a Linux read-only re-check (ssh DATABASE_URL was empty in non-interactive shell).
2. **Authority Chain Integrity — SOUND.** No bypass / no fake lineage / no missing ExecutionReport / no Python fake-success (CC). The D2 ghost-converge reconciler is **LIVE/wired** (`position_reconciler/mod.rs:552 → orphan_handler.rs:457 ConvergeExchangeZero → handlers/mod.rs:401`, no off-flag) — but the converge path is **guard-correct** (BB: `is_primary ∧ reduce_only ∧ qty==0 full-close ∧ retCode 110017`, S-6 single-symbol point-query fail-closed, one-way-mode tripwire) and E4-tested. Acceptable; noted as a live auto-position-mutation path under strong guards.
3. **Live/LiveDemo Boundary — NOT bypassable** (E3). authorization.json/OPENCLAW_ALLOW_MAINNET/secret-slot/operator-role all enforced; LiveDemo not treated as low-risk. The OPS-2 Phase-1 signing-key fallback is the only residual and is already tracked (`P1-OPS-2-PHASE-2-CUTOVER`, due ~2026-06-10, runtime-dormant 0 log hits).
4. **Tunable vs Hardcoded — mostly config'd.** RiskConfig/Kelly SSOT'd and sane (QC). One real gap: confluence weight-sum `validate()` is construction-time only — no DB-load guard (dirty `73≠65` ma_crossover persists; advisory, alpha-distortion not safety) → P2.
5. **AI Truthfulness — HONEST** (AI-E). Ledger written only when a model is actually invoked; paid-provider ledger-write failure fails closed; dual-table durable ledger with deterministic dedup; no provider-HTTP leak in business code. Residual P2: cumulative daily-USD cap fail-closed unproven on Mac (needs Linux PG).
6. **Replay/Demo Evidence Validity — CLEAN** (QC). No paper→edge leak; Stage 0R (offline replay) / Stage 1 (Demo-only) boundary intact; P0-EDGE-1 honestly represented (no cherry-picked positive edge); funding_arb retirement mathematically justified.
7. **GUI Fake-Success — RESOLVED + held** (A3). All 8 prior GUI findings FIXED (Wave3 `7909ca3d` held); write surfaces (mode/live-start/emergency-stop/close-all/paper-stop/earn/canary) go through Rust authority with partial-failure contracts. One new P2 (Earn `wave_d_pending` not distinguished from success in toast).
8. **Test Blind Spots** (E4). Env-test-lock remediation held. Real gaps: Stage-0R runner has 0 pytest coverage (P2); paper→demo promotion-freeze test alignment unconfirmed (P2). **E4's F-001 ("dispatch Transient-retry violates §四") was REJECTED by PA — the create path is strict single-attempt fail-closed (`dispatch.rs:28-30,756-761`); only idempotent reduce-only close retries; see §6.** Full `cargo test`/`pytest` regression counts were NOT run locally (budget) → Linux re-run required before any commit+deploy.

---

## 6. Rejected / False-Positive / Unproven — **MUST NOT be written to TODO**

These were flaky-tool artifacts or already-self-corrected; tracking them would pollute the queue:
1. **e9f01569 "source-ahead drift"** — REJECTED (it is a binary content-hash, not a git commit; MIT+FA).
2. **V104 `supervised.live_audit` "missing/undeployed"** — REJECTED (never existed; already corrected in v85; MIT+FA).
3. **D2 ghost-converge reconciler "shipped DISABLED"** (BB run#2) — REJECTED (FA traced it LIVE + correct).
4. **CC "no source / skeleton checkout / P0"** (an earlier CC draft) — REJECTED (cwd artifact; repo fully populated; self-retracted).
5. **E3 "program_code git-ignored"** (an earlier E3 draft) — REJECTED (`git check-ignore` RC=1 ×3; 861 tracked files; self-retracted).
6. **E4 F-001 "dispatch retry-on-Transient violates §四"** — REJECTED by PA (claim factually **inverted**): `dispatch.rs:28-30,756-761` shows OPEN/create = empty delay slice = **single attempt / 0 retries / strict fail-closed** (the comment literally cites §四 "order_link_id is Bybit-side mitigation, NOT a license for hidden retry of trading effects"); only idempotent reduce-only CLOSE gets a bounded 2-retry (survival exception); unknown codes → `Structural` (no retry). It is the already-remediated prior P1-07. Cross-confirmed BB + CC. → **DO NOT add a "dispatch retry" fix or test that touches this logic.**

(All six were caught by the agents themselves or by cross-role re-probe — evidence that the FACT/INFERENCE/ASSUMPTION discipline + rule-10 cross-checking worked.)

---

## 7. Operator Decisions Required (before any related fix)

1. **ADR-0046 (P1):** author a Proposed `docs/adr/0046-*.md` + register row, **OR** strike the "ADR-0046 Accepted" gate citation and replace with "future ADR slot, not yet filed." (Governance content decision.)
2. **P0-EDGE-1 tournament timeline:** structural (no alpha-bearing candidate ready); needs operator call on Alpha-Tournament timing / A1 basis-panel forward-accumulation (~2026-06-13). No code fix.
3. **OPS-2 Phase-2 cutover window** (~2026-06-10): already scheduled; confirm/keep.
4. **TODO delta application** (see §8): approve PM applying the proposed deltas on a clean tree, or apply them yourself.

---

## 8. TODO.md — Proposed Deltas (NOT applied directly)

**Why not applied:** the operator baseline note (`d9128e22`) explicitly says "no edits to TODO.md (operator WIP dirty); PM proposes TODO deltas in final ruling." `TODO.md` is currently dirty with a concurrent session's WIP (it advanced v84→v85 and HEAD moved repeatedly during this audit). Editing it now would risk the documented multi-session race (memory `project_multi_session_memory_race`). **PM proposes; operator approves application on a clean tree.**

Proposed additions to the active queue (all confirmed + actionable + trackable):
> **Authoritative set:** the PA validated plan (`…/PA/…/2026-05-30--PA--cold_audit_validated_fix_plan.md`) is the canonical enumeration — **5 confirmed P2 + ~8 P3**, all non-overlapping → fully parallel except the ADR-0046 operator gate. The deltas below map to that set.

- **P2** `COLD-AUDIT-0530-ADR0046` — author a Proposed `docs/adr/0046-*.md`+register row, or strike/repoint the "ADR-0046 Accepted" gate citation to ADR-0018 (also resolves the ADR-0046-vs-"n" name-split) (PA+TW; verify R4+CC). *Operator decision first.* (Gated; funding_arb dormant.)
- **P2** `COLD-AUDIT-0530-110009` — rename retcode 110009 `PositionNotFound`→`StopOrderLimitExceeded`, remove from NoOp arm, fix dict+test (BB+E1→E2).
- **P2** `COLD-AUDIT-0530-PAGINATION` — `get_positions(Linear,None)` add `nextPageCursor` loop + explicit limit (E1+BB→E2) [defense-in-depth; S-6 already protects the delete path].
- ~~`COLD-AUDIT-0530-DISPATCH-RETRY-TEST`~~ — **DROPPED.** PA REJECTED F-001 (create path already strict single-attempt fail-closed). Do NOT touch `dispatch.rs` retry/classify logic.
- **P2** `COLD-AUDIT-0530-CONFLUENCE-GUARD` — validate confluence weight-sum on DB-load, reject/fallback (E1+MIT→QC+E2).
- **P2** `COLD-AUDIT-0530-STAGE0R-TESTS` — pytest coverage for Stage-0R runner (Wilson CI/threshold/smoke) (E4).
- **P2** `COLD-AUDIT-0530-PROMO-FREEZE-TEST` — confirm/align paper→demo promotion-freeze tests (E4).
- **P2** `COLD-AUDIT-0530-EARN-WAVED-TOAST` — Earn tab branch on `wave_d_pending` (E1→E2+A3).
- **P2** `COLD-AUDIT-0530-FILESIZE` — split `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py` (2552 > 2000 cap, 3rd carry-over) + watch `commands.rs`/`intent_processor/mod.rs`/`governance_routes.py` (98-99% of cap) (E5 plan → E1→E2). (Convention-with-documented-exception, not a hard boundary.)
- **P2/P3 doc-hygiene** `COLD-AUDIT-0530-DOCS` — README ADR count (14→45), v65 archive path (TODO:23,491), SPEC_REGISTER counts + DEPRECATED.md denylist, Operator-mirror 56-dup dedup, funding_arb 2026-04-16/17 SUPERSEDED headers, TODO HEAD-banner stale (R4+TW).
- **Linux read-only evidence (passive checks):** `_sqlx_migrations max=115` + basis_panel row-recency (MIT); AI cumulative daily-cap fail-closed under real PG (AI-E); full `cargo test`/`pytest` regression counts (E4).

Already-tracked — DO NOT duplicate: `P1-OPS-2-PHASE-2-CUTOVER` (E3 OPS-2 fallback).

---

## 9. Strictly Forbidden Before Operator Approval

- Any funding_arb revival (ADR-0046 gate unresolved).
- Any TOML / risk / strategy / live-config edit.
- Any change to the D2 reconciler (it is correct as shipped).
- Any change to `dispatch.rs` retry/classify logic (PA verified correct — create path strict single-attempt, reduce-only close idempotent; F-001 rejected).
- Any migration / `_sqlx_migrations` checksum touch (V115 frozen — hash-drift hazard).
- Direct `TODO.md` edits while the worktree is dirty / concurrent session active.
- Any deploy / restart / rebuild / auth mutation / trading start.

---

## 10. Report Index

| Role | Report |
|---|---|
| Baseline | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-30--cold_audit_dispatch_baseline.md` |
| R4 | `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-30--R4--index_integrity_audit.md` |
| TW | `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-30--TW--doc_inventory_dedup_audit.md` |
| CC | `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-30--CC--root_principle_compliance_audit.md` |
| FA | `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-30--FA--full_chain_functional_gap_dead_code_audit.md` |
| E3 | `docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-30--E3--security_gate_secret_audit.md` |
| BB | `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-30--BB--bybit_api_compatibility_audit.md` |
| QC | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-30--QC--strategy_risk_math_audit.md` |
| MIT | `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-30--MIT--db_ml_foundation_audit.md` |
| AI-E | `docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-30--AI-E--ai_usage_effectiveness_audit.md` |
| E4 | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-30--E4--full_chain_test_audit.md` |
| E5 | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-30--E5--optimization_readability_performance_audit.md` |
| A3 | `docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-30--A3--gui_usability_dead_button_audit.md` |
| **PA validated plan** | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-30--PA--cold_audit_validated_fix_plan.md` |

---

## 11. Process Notes (meta-findings for future audits)

- **Harness tool flakiness** (intermittent empty/stale/garbled `Bash`/`Read` output) nearly produced ≥3 fabricated findings; the FACT/INFERENCE/ASSUMPTION discipline + rule-10 cross-checking caught all of them. Keep "re-run before trusting; never ship a single-flaky-read finding."
- **Read-only audit roles cannot write reports** — see §2.1; fix the roster/substrate in the next audit.
- **Session token cap** bounded throughput; tight per-agent budgets + model tiering (Opus for analytical, Sonnet for mechanical) are necessary at this scale.
- **The cold audit re-run found the prior remediation solid** — the highest-value outcome is the *confirmation* that the 2026-05-29 fixes held with zero source regression, plus a small, mostly-doc backlog.
