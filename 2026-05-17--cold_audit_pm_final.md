# Cold Audit PM Final Ruling

Requested audit date: `2026-05-17`  
Actual PM final time: `2026-05-29T00:11:28Z` / `2026-05-29T02:11:28+0200`  
Canonical repo root: `/Users/ncyu/Projects/TradeBot/srv`  

## Verdict

PM accepts the PA validated plan as the authoritative output of this read-only cold audit.

Final confirmed counts:

| Severity | Count |
|---|---:|
| P0 | 0 |
| P1 | 17 |
| P2 | 17 |
| P3 | 7 |

Rejected / downgraded / unproven raw findings: 10.

Primary report:

- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--cold_audit_validated_fix_plan.md`

Supporting reports:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md`
- `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md`
- `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md`
- `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-17--root_principle_compliance_audit.md`
- `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-17--full_chain_functional_gap_dead_code_audit.md`
- `docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-17--security_gate_secret_audit.md`
- `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-17--bybit_api_compatibility_audit.md`
- `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-17--strategy_risk_math_audit.md`
- `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-17--db_ml_foundation_audit.md`
- `docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-17--ai_usage_effectiveness_audit.md`
- `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-17--full_chain_test_audit.md`
- `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-17--optimization_readability_performance_audit.md`
- `docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-17--gui_usability_dead_button_audit.md`

## Root-Principle Ruling

The audit procedure itself complied with the root principles: no fix, deploy, restart, migration, auth mutation, config mutation, or trading action was performed.

The codebase has confirmed P1 violations or near-violations if left unfixed:

- Principle 1 / 2: Python live cancel-all remains an exchange-mutating write path outside Rust authority.
- Principle 3 / 4 / 8: live session and GUI success states can overstate actual Rust/live authorization state.
- Principle 6: order-create retry and stale edge snapshot gates are not strictly fail-closed enough for their claimed boundaries.
- Principle 10: active docs/spec registers contain source-of-truth drift.
- Principle 13: provider-native AI calls are not fully tied to durable invocation/cost ledgers.

None of these are P0 in the current evidence because PA did not verify a direct current path that bypasses Rust live authorization and places new live orders.

## Dispatch Compliance

PM followed the requested role chain:

- PM baseline freeze
- R4(explorer) + TW(worker)
- CC(default), FA(default), E3(explorer), BB(default), QC(default), MIT(default), AI-E(default), E4(worker), E5(explorer), A3(default)
- PA(default) validation and dedupe
- PM final ruling

Deviation accepted: PM used read-only `git ls-remote` instead of `git fetch` where read-only mode made `.git/FETCH_HEAD` writes undesirable. This is recorded in the baseline.

## Runtime / Docs Drift

FACT:

- Baseline freeze first observed source/runtime drift during this audit.
- PA later rechecked local and Linux as aligned at `575a0a94e5501539c992281ea4d79382109d534e`.
- PM final recheck first observed transient drift: local `HEAD=be529e96fba984dc874433dd23c83f7336728fce`, origin/Linux `575a0a94e5501539c992281ea4d79382109d534e`.
- PM final-final recheck observed local, origin `main`, and Linux `trade-core` aligned at `3004edb4fea7cdc619cf30d9e7f35d09fdebb8bb`.
- Local worktree also contains unrelated dirty/untracked work outside this cold audit.

Inference:

- Any implementation session based on this audit must start with a new source/runtime freeze before touching files.

Docs drift confirmed:

- SPECIFICATION_REGISTER ADR paths for ADR-0036..0041 point to non-existent filenames while matching ADRs exist under different names.
- Operator mirror drift exists for at least one PA redesign report.
- Alpha/M11 state is split across docs/runtime in a way that can cause duplicate dispatch or false evidence claims.

## Operator Decisions Required

Implementation is blocked on these decisions before E1 work:

1. Order-create retry policy: strict reconcile-before-retry vs explicit idempotent retry exception.
2. Python live cancel-all authority: Rust-only write path vs formally ratified emergency exception.
3. Paper promotion lane: confirm frozen; no `PAPER_SHADOW -> DEMO_ACTIVE` promotion without future explicit reopen.
4. Alpha/M11 evidence semantics: Stage A smoke heartbeat is liveness only; Stage B divergence/promotion evidence remains separate.
5. AI provider-native policy: paid calls fail closed on missing ledger/pricing, or remain advisory and cannot satisfy cost gates.
6. Docs/index policy: literal complete index vs generated per-area manifests.

## TODO Update Policy

Only confirmed, actionable PA findings were added to `TODO.md` as compact follow-up packages. Unproven/rejected findings were not written into TODO. P2/P3 details remain in the PA report unless PM schedules a later cleanup wave.

## Next Dispatch Recommendation

Recommended first implementation sessions:

1. Live gates and fake-success package.
2. Order retry policy decision + exchange semantics package.
3. Evidence/promotion gates package.
4. AI/ML lineage package.
5. Governance SoT/docs drift package.

Every implementation session must run PA -> E1 -> E2 -> E4 -> QA/PM as applicable, with BB/MIT/AI-E/A3/CC verification where named by the PA plan.
