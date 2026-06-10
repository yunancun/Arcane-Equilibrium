# MIT ML-Pipeline + Leak-Typing + Calibration Audit — L2 Phase 3a `ml_advisory` (diagnose_leak + interpret_result)

Date: 2026-06-09
Auditor: MIT (ML & Database Auditor)
Scope: E1 P3a implementation — branch `feature/l2-critic-lessons-tools` @ `6a9dd0f1` (P3a uncommitted)
Spec: PA `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-09--l2-p3-ml-advisory-tech-design.md` (DESIGN-ONLY)
Gate role: **MIT named sign-off for M3 (leak typing) + M4 (Ollama recall calibration)** per PA §N + execution-plan §1.

## Verdict: MIT APPROVE-CONDITIONAL (M3+M4 GRANTED; 1 HIGH Linux-owed + 1 MED sink-semantic to acknowledge)

M3 typing and M4 recall — the two MIT-named gates — are **sound and PASS**. Two findings on the **sink** (the #1 MIT decision point) must be acknowledged by PM/operator before the sink-write path can be trusted in production: one HIGH (V037 REVOKE collision, Linux-owed), one MED (semantic overload of an active applier-feed namespace).

---

## Files reviewed (in full)

| File | Lines | Role |
|---|---|---|
| `control_api_v1/app/l2_ml_advisory_executor.py` | 699 (new) | cascade + M4 `OllamaScreenCalibration` + sink writer |
| `control_api_v1/app/l2_out_of_bound_guard.py` | 342 | M3 source_class typing (clause B) + regime_caveat (clause C) + axes (D) |
| `control_api_v1/app/l2_prompt_contract_registry.py` | 308 | 2 contracts + M3 source_class constants |
| `control_api_v1/app/l2_advisory_orchestrator.py` :377-460 | — | `dispatch_and_execute` executor wiring |
| `control_api_v1/tests/test_l2_p3a_ml_advisory.py` | 934 | 41 tests (intent-level) |
| `ml_training/leakage_check.py` | 78 | name_pattern_check producer (M3 grounding) |
| `sql/migrations/V031` :407-470 | — | advisory sink schema |
| `ml_training/mlde_demo_applier{,_evidence_filter}.py` | — | sink CONSUMER (collision analysis) |
| V036/V037/V038/V040 | — | sink evidence-tier governance |

---

## Axis 1 (★) — M3 leak typing: IS IT HONEST? → **YES**

**Question answered: ml_advisory does NOT pretend leakage_check output = leak-free PIT.**

Guard clause B (`_guard_ml_advisory_v1`, `l2_out_of_bound_guard.py:227-255`) — verified deterministically via AST-extracted pure functions (12 invariants, all green):

| Invariant | Result |
|---|---|
| B.1 source_class missing/invalid → reject | reject ✓ (`invalid_leak_source_class`) |
| **B.2 name_pattern_check claims `leak_free=true` → reject** | reject ✓ (`leakfree_claim_unsupported_by_source_class`) — the M3 iron rule |
| B.2 name_pattern_check claims `pit_verified=true` → reject | reject ✓ |
| name_pattern_check WITHOUT leak-free claim → pass | pass ✓ (weak evidence allowed) |
| leak_free via `shift1_compliance` → pass | pass ✓ (legal typing; producer P3b-owned) |
| unknown/`hypothesize` mode at guard → reject | reject ✓ (fail-closed) |
| missing sub-object → reject | reject ✓ |

**Grounding:**
- `leakage_check.py` read in full = **78 lines, pure name-substring/prefix matching only** (`FORBIDDEN_PATTERNS` + `ALLOWED_PREFIXES`). Zero shift(1) verification, zero PIT temporal-gap check. This empirically confirms M3's thesis: `name_pattern_check` is a necessary-not-sufficient screen and **cannot** establish leak-free PIT.
- `ML_ADVISORY_LEAKFREE_SOURCE_CLASSES = frozenset{shift1_compliance, is_oos_gap}` (`l2_prompt_contract_registry.py:163-165`) — `name_pattern_check` correctly excluded.
- diagnose contract template (`:177-195`) hard-constrains: *"You MUST NOT claim leak-free point-in-time integrity backed only by name_pattern_check"* — belt-and-suspenders with the deterministic guard.
- **shift1_compliance/is_oos_gap producers do not exist** (PA §F.1 confirmed; MIT-owned P3b build). P3a enforcing **typing only** (not requiring the producers) is the correct, honest scope: a diagnose evidence row is typed `name_pattern_check` and the guard forbids it from masquerading as leak-free. **This is sufficient honesty for P3a** — it does not fabricate leak-free evidence it does not have.

**M3 sign-off: GRANTED.**

---

## Axis 2 (★) — M4 Ollama recall mechanism: IS IT SOUND? → **YES**

`load_ollama_screen_calibration` (`l2_ml_advisory_executor.py:145-195`) — verified deterministically via isolated exec (7 branches, all green):

| Branch | enabled | Correct? |
|---|---|---|
| no artifact | False (`benchmark_version=absent`, `flag_mit`) | ✓ fail-closed |
| malformed JSON | False (`malformed`) | ✓ |
| recall key missing | False (`recall_missing`) | ✓ |
| recall non-numeric ("high") | False (`recall_missing`) | ✓ |
| recall 0.70 < floor | False (`below_floor`) | ✓ |
| **recall 0.85 == floor** | **True** | ✓ (floor is `>=`, not `>`) |
| recall 0.88 ≥ floor | True | ✓ ENABLED |

**Assessment of the three MIT-judgment questions:**
1. **recall≥0.85 "loose" definition correct?** YES. The screen is recall-tuned (strongly biased to `pass`, `_SCREEN_SYSTEM_PROMPT:232-239`); precision is provided by the downstream deterministic gate (defense-in-depth). "loose" = most-permissive operating point still clearing recall≥0.85. Sound.
2. **disable-on-low-recall fail-safe direction correct?** YES, and this is the key design judgment. When the screen is unreliable, everything routes to the deterministic gate (costs more cloud, loses no alpha) — **NOT** everything-passes. The risk a screen introduces is false-kill of a genuinely-good hypothesis; disabling it only costs cloud (the gate still gives precision). The fail-safe is correctly directed.
3. **placeholder=DISABLED a correct conservative start?** YES. With no MIT benchmark artifact yet, starting DISABLED (everything to gate) is the safe default — it cannot false-kill, and the gate-seam flags MIT (`applied_as=screen_disabled_flag_mit`).

**Benchmark artifact schema — MIT recommendation (how I would build the held-out set):**
- **good set**: historically demo-confirmed discoveries (Stage-0R/Stage-1 promoted candidates) + post-hoc-correct diagnoses (e.g. the 5 down-beta-masquerade NO-GOs, where the correct diagnosis was "beta, not alpha").
- **bad set**: `agent.lessons` V133 dead-modes (trigram-retrieved failure patterns).
- **artifact JSON** (E1 defined `{benchmark_version, recall, measured_at}`; MIT extends): add `precision`, `n_good`, `n_bad`, `per_class_recall{good_recall, bad_reject_rate}`, `confusion{tp,fn,fp,tn}`, `classifier_version` (pin the screen prompt/model version). Measure recall of the SCREEN (pass-through-vs-coarse-reject), not the final answer — the design correctly specifies this (§G.2.1).
- Re-calibrate on benchmark-version bump + monthly; log to D3 gate-seam for §O metric + MIT audit.

**M4 sign-off: GRANTED.** (E1 built the mechanism + correct fail-safe + placeholder; the benchmark *data* is MIT-owned and is the next MIT deliverable, not a P3a blocker.)

---

## Axis 3 (★) — Sink ML-appropriateness (the #1 MIT decision point) → **2 FINDINGS**

The executor writes diagnose/interpret output to `learning.mlde_shadow_recommendations` via a **direct INSERT** (`l2_ml_advisory_executor.py:428-446`) with `source='ml_shadow'`, `recommendation_type='regret_summary'`, `created_by='ml_advisory'`, `expected_net_bps=NULL`, `confidence=NULL`, `applied=false`, `requires_governance=true`, `decision_lease_id=NULL`.

### Finding S-1 (HIGH, Linux-owed — Mac-RCA blind spot)
**V037 REVOKE PUBLIC INSERT may fail-close the P3a direct INSERT at runtime.**
- V037 (`V037__replay_evidence_revoke_public_insert.sql`) REVOKEs PUBLIC INSERT on `learning.mlde_shadow_recommendations`; the only sanctioned write path post-V037 is `learning.verify_replay_evidence_and_insert()` (V036, SECURITY INVOKER).
- **BOTH existing producers** route through that function: `mlde_shadow_advisor.py:470`, `opportunity_tracker.py:329`. The P3a executor is the **ONLY** direct-INSERT writer.
- V037 is in the migration tree (V036-V040; branch at V134+) → almost certainly applied on Linux.
- **If the control_api login role lacks `replay_writer_role` GRANT, the P3a direct INSERT fails-closed at runtime.** Because the executor is fail-soft, this manifests as **silent sink-write failure** (`ok=False`, `errors=['insert_failed']`, gate-seam `ml_advisory_sink reject`) — the advisory is silently dropped, not crashed.
- Mac mocked-conn tests cannot see this. **OWED: Linux `SELECT has_table_privilege('<control_api_role>', 'learning.mlde_shadow_recommendations', 'INSERT')` + check `replay_writer_role` membership.**
- **Reconciliation note**: routing through `verify_replay_evidence_and_insert(tier='real_outcome', ...)` IS schema-possible (P3a has no replay_experiment_id/manifest_hash so passes the real_outcome compound CHECK) — but that would **falsely tag a zero-alpha diagnostic as `evidence_source_tier='real_outcome'`** (the exact tier-mislabeling the function exists to prevent). So the function is NOT a clean fix either; it reinforces that this table is the wrong sink for diagnostics.

### Finding S-2 (MED — semantic overload of an active consumer namespace)
`mlde_shadow_recommendations` is an **alpha-evidence / applier-feed table** governed by V036/V037/V038 evidence-tier contracts and consumed by `mlde_demo_applier` to **mutate demo RiskConfig** (`mlde_demo_applier.py:451,1496` route on `recommendation_type=='regret_summary'` → `build_risk_patch` → IPC).
- P3a's `(source='ml_shadow', recommendation_type='regret_summary')` collides with the active producer (`mlde_shadow_advisor` writes `ml_shadow`; `opportunity_tracker` writes `regret_summary`).
- The only barrier keeping P3a diagnostic rows out of the applier is **coincidental, not by-design**: the fetch WHERE (`mlde_demo_applier_evidence_filter.py:629-636`) is `engine_mode=demo AND NOT applied AND COALESCE(confidence,0.0)>=min_confidence AND COALESCE(sample_count,0)>=min_samples AND <evidence_filter>`. P3a `applied=false` PASSES `NOT applied`; P3a `confidence=NULL`→`0.0 < 0.35` (default min_confidence) is the **only** thing filtering it out. Set `OPENCLAW_MLDE_DEMO_APPLIER_MIN_CONFIDENCE=0.0` and P3a rows get fetched (second-line save: empty `net_regret_direction` → empty patch no-op).
- The Block-A evidence filter does NOT save it: `COALESCE(evidence_source_tier,'real_outcome')=ANY(allowlist)` — P3a writes no tier → coalesced to `'real_outcome'` → IN allowlist → not filtered.

### Sink recommendation (for PM/operator)
A zero-alpha diagnostic/interpretation is **not a model recommendation** and is semantically misplaced in an applier-feed evidence table regardless of the `created_by` discriminator. MIT preference, in order:
- **(a) move sink to `agent.lessons` (V133) or a dedicated diagnostic table** — cleanest; removes P3a from the alpha-evidence/applier namespace entirely. agent.lessons already stores L2 Reflexion lessons (diagnostic-shaped). **MIT top pick.**
- **(c) V137 adds `source='ml_diagnostic'` + `recommendation_type ∈ {diagnostic, interpretation}`** to the CHECK enums — keeps the table but de-overloads `ml_shadow`/`regret_summary`. (Requires migration; PA design said zero-migration, so this reopens V137.)
- **(b) keep current sink + harden the consumer**: add `AND created_by NOT LIKE 'ml_advisory%'` to the `mlde_demo_applier` fetch WHERE. Lowest-effort but leaves the semantic overload + relies on the consumer remembering the discriminator forever. **Least preferred.**

---

## Axis 4 — Cascade ML correctness → **PASS**

- **LLM never validates alpha**: executor real-code has **0** alpha-gate imports (grep `dsr_gate`/`pbo_gate`/`beta_neutral`/`residual_alpha_gate`/`compute_dsr` = empty; test `test_executor_has_no_alpha_gate_imports`). P3a has NO alpha gate (asserts no alpha) — correct; there is no alpha to validate.
- **Guard is deterministic**: ml_advisory guard real-code has 0 model calls (grep `run_session`/`_provider_complete`/`LocalLLMClient` = empty). Form-check only.
- **cost only on survivors**: screen `skip` → 0 cloud call (short-circuit, executor:531-536; mutation-bite test `test_mutation_bite_cloud_only_on_screen_survivors`).
- **regime_caveat enforced**: interpret with `promotion_ready=true` + bull-only + no `regime_caveat` → guard reject (clause C, verified). Aligns Alpha Evidence Governance.
- **cost wiring**: screen + cloud each call `record_claude_cost` with distinct token counts (triage tier + sonnet tier) → genuine two-call accumulation into DOC-08 daily counter, NOT double-counting. Storm-protection visible to admission budget gate.
- **orchestrator wiring**: executor runs ONLY on `admitted AND routed_to=neutral_sink AND capability.startswith('ml_advisory')` (`l2_advisory_orchestrator.py:410-416`); disabled/deduped/tier/MANUAL/fail-safe short-circuit with 0 model calls (5 dispatch-reachability tests). `direction=neutral` for all P3a caps (TOML `lane=ml_backlog`). fail-soft: cascade exception never propagates into dispatch.

---

## Axis 5 — diagnose/interpret own look-ahead → **PASS (no leak)**

- `context` is caller-supplied, structured, pre-extracted **post-training** data (`{training_run_id, metrics, leakage_check_findings, drift_signals}` / `{..., feature_importance, regime_label}`). The executor does NOT fetch any data itself — it reads what the pipeline already produced **after** training completed. Diagnosing a finished training result with its own post-hoc metrics introduces no future-information穿越.
- `_extract_fact_inf_assm` (`:610-634`) correctly separates fact/inference/assumption per root principle 10: diagnose → `evidence_kinds` + `suspected_cause`; interpret → `confidence` + `has_regime_caveat`. Written to D3 `fact_inf_assm` column.

---

## Migration → ZERO (correct)

P3 ships no migration: sink V031, D3 V134/V135, novelty V133, registry=TOML — all existing. V137 reserved-not-used. **EXCEPTION**: if the sink fix takes option (c), V137 is reopened (source/type enum extension → Guard A/B/C + Linux double-apply idempotency owed).

---

## Test posture

41 intent-level tests (2 modes; cascade survivors-only + mutation-bite; M4 4 branches + mutation-bite; M3 typing; regime_caveat; sink zero-exec-authority + grep iron-rules; dispatch reachability; coarse_subject DoS). **Comprehensive and intent-verifying** (CLAUDE Operating Style 9).

**Mac cannot run the full suite** (py3.10 lacks `tomllib`; py3.12 lacks `pydantic`+`pytest` — environmental, NOT a P3a defect; documented Mac-sandbox limitation). MIT compensated by AST-extracting the pure M3 guard functions (12 invariants) + M4 calibration loader (7 branches) into isolated namespaces — all green. **Full-suite green is E4-Linux owed.**

---

## Required actions before PM sign-off

1. **HIGH (S-1, Linux)**: verify `learning.mlde_shadow_recommendations` INSERT privilege for the control_api login role post-V037 (`has_table_privilege` + `replay_writer_role` membership). If revoked → P3a sink silently drops every advisory.
2. **MED (S-2, decision)**: PM/operator pick sink option (a)/(b)/(c). MIT recommends (a) agent.lessons or (c) V137 de-overload — diagnostics do not belong in the applier-feed evidence namespace.
3. **E4**: run full `test_l2_p3a_ml_advisory.py` on Linux (py3.11+ with pydantic) for true green.
4. **MIT-owned follow (non-blocking for P3a ship)**: build the M4 held-out benchmark artifact (good/bad set + schema above) to move the screen from placeholder-DISABLED to live-calibrated.

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-09--l2_p3a_ml_advisory_m3_m4_signoff.md
