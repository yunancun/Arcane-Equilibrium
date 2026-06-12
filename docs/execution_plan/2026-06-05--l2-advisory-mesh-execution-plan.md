# L2 Advisory Mesh — Execution Plan (E1-ready roadmap)

Date: 2026-06-05
Status: **E1-READY** — gating endorsed (QC B1 / MIT M1 / MIT M2 = ENDORSE, 0 BLOCKER open).
        Awaiting operator go to start E1. Docs/design only; this plan authorizes no code,
        no migration, no DB write, no deploy until the operator opens the gate.
Owner chain: PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM (feature chain); QC/MIT/E3 sign-off
        points noted per phase.
Source design (SSOT): `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--l2-advisory-mesh-design-draft.md`
        (v4-final). Consolidated background: `docs/execution_plan/2026-06-05--l2-copilot-design-session-consolidated.md`.
Active authority: root `TODO.md` row `P1-L2-ADVISORY-MESH-TAILS`.
Historical ledger/reference: `L2_TODO.md` (repo root).

This document turns the v4-final design into an executable roadmap. It does **not**
re-litigate the design. It adds: the build-order phase decomposition, each phase's E1
acceptance criteria (incl. the QC/MIT re-confirm FIX/NOTE + CC carbon-layer fences + E3
auth/sanitize), the owner role chain, the green-gate between phases, the V134 (+ V13x)
Linux PG dry-run requirement, and the QC/MIT/E3 sign-off points.

---

## 0. Read-before-build (binding preconditions, do not skip)

These are the design's own `needs-verification` items; E1 must clear the per-phase ones
**before** that phase's implementation sign-off (design read heads/grep only — re-read in full):

- **V134 is the next free migration number** — confirm no parallel-session V134 landed first
  (latest is V133). The C1 promote-candidate table is **V13x = next free after V134**.
- **Linux PG empirical dry-run of V134 (+ V13x)** with **double-apply idempotency** per
  `feedback_v_migration_pg_dry_run.md` — Mac mock cannot catch PG runtime semantics.
- **`agent.ai_invocations` shape** (full V064 §) — finalize how much D3 reuses vs adds.
- **`Layer2CostTracker` persistence** (`runtime/layer2_cost_state.json`) — confirm cost-only,
  not a partial prompt/response audit we can extend.
- **Exact GovernanceHub read-only surface** the Orchestrator may call (capability state,
  lease/risk *projections*) without acquiring any trading-scope lease.
- **ML-pipeline read seam for `ml_advisory`** — V031 view columns + `mlde_shadow_advisor` /
  `run_training_pipeline` / `leakage_check` output shapes; confirm
  `learning.mlde_shadow_recommendations` (`applied=false`/`requires_governance=true`) is the
  right advisory sink. **Re-read those modules in full before phase 3 sign-off.**
- **Provenance-chain additive columns** (`source_l2_reply_id`) on `research.hypotheses` /
  variant / replay / demo manifests / **live fills + live `decision_outcomes` + Decision-Lease
  audit row** — confirm each target can take an additive col without schema conflict (some are
  V131/V132 hash-chained → additive only; identify the exact live fills/outcomes table on Linux).
- **`shift1_compliance` / `is_oos_gap` leak checks** — confirm whether they exist anywhere in
  `program_code/ml_training` / the gate stack or must be built (today only the 78-line
  `name_pattern_check` `leakage_check.py` exists). (MIT M3.)
- **`dsr_gate.DsrResult.n_trials_K`** can be fed `K_for_dsr = N_eff` (currently a manifest `K`);
  no caller hard-codes raw variant count. (MIT M2.)
- **PIT cap-weighted altcoin basket** return series + **leak-free down-market regime label**
  exist (or specify construction); ≥90d aligned return history reachable per candidate. (QC B1.)
- **Secret redactor** — confirm whether a vetted secret-pattern redactor exists to reuse for
  §D.1.1; else specify the pattern set. (E3 E2.)
- **Singleton SSOT** — `L2AdvisoryOrchestrator`, `ResearchAlphaWealthController`, the D3 writer,
  the N_eff cluster controller must be registered in `docs/architecture/singleton-registry.md`
  **before merge** (CLAUDE §九).

---

## 1. Gating sign-off ledger (must be GREEN before the dependent phase starts)

The three adversarial re-confirms are **ENDORSED**; their concrete FIX/NOTE are folded into the
phase acceptance criteria below (and into the design §L as E1 acceptance). No BLOCKER is open.

| Gate | Owner | Status | Binds phase | FIX/NOTE folded into acceptance |
|---|---|---|---|---|
| **B1** beta_neutral_check deterministic spec | QC | **ENDORSE** | P3 (promotion-relevant), P4 | dual-factor BTC+altcap **mandatory** (BTC-only → DEFER); OLS at **daily/4h** (not 1m); down-market def = **30d drawdown >8% OR 7d return <-5%**, lagged-PIT, **≥30 bars** else DEFER; NOTE: `β_upper = β+1.96·SE < 0.20`; 45/45d window stability; WF-OOS window must not overlap the beta window |
| **M1** online-FDR refund accounting | MIT | **ENDORSE** | P4 | φ=1.0 proportional refund adopted; NOTE: `debit_state` needs **persistent storage** (PG `research.alpha_wealth_ledger`, not in-memory fail-safe); add **per-test `α_i ≤ α_target / min_batch_size` cap**; docs distinguish `n_trades ≥ 30` (refund bar) vs `N_trades_oos ≥ 50` (math-gate precondition) |
| **M2** N_eff ↔ FDR/DSR single-debit | MIT | **ENDORSE** | P4 | clustering = **average-linkage, Pearson corr > 0.5 cut**; NOTE: add `max(1, N_eff)` guard (K=0 raises); add `max_variants_per_cluster` anti-abuse; `dsr_gate` `n_trials` interface already compatible — no breaking change |
| B2 forward-OOS demo precondition | QC | folded (design §C.3) | P3, P4 | `MIN_FORWARD_OOS_DAYS = 21`, posture-independent, applier-owned; Stage 0R = in-sample = necessary-not-sufficient |
| C1 Orchestrator no `promote_tier` | CC | folded (design §A.1/§O.4) | P2, P5 | grep proof: 0 references to `promote_tier`/autonomy-raisers in Orchestrator + §O modules; promote-candidate = read-only inbox row; only operator-route promotes |
| C2 `can_auto_deploy_to_paper` is unlock-only | CC | folded (design §C.2) | P2, P3 | True@all-tiers → carries no posture signal; loader rejects configs that use it as a posture gate |
| Q1 math-gate step-0 sample bar | QC | folded (design §G.2) | P3, P4 | `N_trades_oos ≥ 50` → else **DEFER** (third state, not PASS/FAIL) |
| Q2 cost decomposition in packet | QC | folded (design §N) | P5 | `cost_edge_ratio`/`gross_edge_bps`/`total_cost_bps` + `max_dd_duration_days` |
| Q3 cold-start blind window | QC | folded (design §O.5) | P5 | proxy correctness (labeled) + GUI "blind window" badge + raised audit cadence |
| M3 leakage_check capped | MIT | folded (design §E(0)/§G.2) | P3 | `name_pattern_check` is NOT leak-free PIT proof; `source_class` typing mandatory |
| M4 Ollama gatekeeper calibration | MIT | folded (design §G.2.1) | P3, P4 | held-out good/bad set; **recall floor ≥ 0.85** defines "loose"; below → disable screen |
| E1 write-endpoint operator-scope | E3 | folded (design §N.2) | P2, P5 | `/cost/reset`, `/cost/pricing`, every Orchestrator/registry **write** = operator-scope; reads stay read-only |
| E2 D3 sanitize-before-persist | E3 | folded (design §D.1.1) | P1 | redact secrets/`str(e)`/raw errors on the **write path**, all 4 large-text columns, before append |

**Rule:** a phase that "ships a promotion-relevant verdict" cannot pass its gate until **B1
(QC sign-off)** lands its final numbers. Diagnose/interpret-only modes (which assert no alpha)
may ship earlier. **M1 + M2 (MIT sign-off)** gate P4 (the FDR research loop). Everything else is
design-decided.

---

## 2. Phase decomposition (strict dependency order = design §J build order)

Each phase is independently shippable and **green-gated**: the next phase does not start until
the prior phase's acceptance criteria + sign-off are GREEN. Every implementation phase runs the
full `PA -> E1/E1a -> E2 -> E4 -> QA -> PM` chain; the role-specific sign-off points are called out.

### Phase 1 — D3 Provenance & Audit foundation (build #1, mandatory before any capability)

**Scope:** `agent.l2_calls` ledger (V134, append-only, extends `agent.ai_invocations` discipline)
+ FULL provenance chain columns (§D.2: `source_l2_reply_id` propagated reply→hypothesis→variant→
replay→demo→live) + gate-seam log (`learning.l2_gate_seam_log`) + fault-localization protocol +
**[E2] sanitize-before-persist redactor (§D.1.1)**.

**E1 acceptance criteria:**
- V134 migration: Guard A on `CREATE TABLE`, Guard B on type-sensitive cols; **append-only** —
  no UPDATE/DELETE grant for the app role; hypertable on `created_at`.
- **Linux PG dry-run + double-apply idempotency** PASS (per `feedback_v_migration_pg_dry_run.md`)
  — Mac mock is insufficient.
- Ledger stores FULL `system_prompt` + FULL `input_context` + FULL `raw_response` + `contract_ver`
  + `schema_ver` + `model`/`model_version` + `fact_inf_assm` tags + tokens/cost/latency +
  `prompt_sha256`/`response_sha256` (computed **over the sanitized stored text**).
- **[E3 E2] Sanitize pass is on the write path** (not a post-hoc cleanup leaving a window):
  inject a synthetic secret into prompt/response/`str(e)` → stored row carries `[REDACTED:<kind>]`,
  never the secret; redactor version is logged; `str(e)`/raw error strings/stack traces are
  never stored verbatim (classified error code + sanitized reason instead).
- `source_l2_reply_id` additive columns confirmed land-able on every chain target without schema
  conflict (V131/V132 hash-chained → additive only); the **live** fills/outcomes + Decision-Lease
  audit-row column is **audit-only, no live-authority change** (engine copies the lease root id
  forward, never re-derives).
- D3 writer singleton registered in singleton SSOT.

**Sign-off points:** E2 (append-only grant + schema), **E3 (E2 sanitize on write path — must
PASS)**, E4 (Linux regression + migration dry-run), QA.

**Gate to P2:** D3 green; nothing else ships until the ledger + sanitize + provenance columns
exist (retrofitting provenance is how lineage gaps happen — root principle 8).

---

### Phase 2 — Orchestrator + registry + contracts + guard + admission + adjudication (the CC linchpin)

**Scope:** `L2AdvisoryOrchestrator` singleton + `l2_capability_registry` (no `autonomy_level`
field — derived per §C.2) + checked-in default TOML (SSOT) + PromptContract/output-schema
registry + deterministic out-of-bound guards + trigger admission stage (§F.1 dedup/debounce/
coalesce) + conflict adjudication table (§F.2). All capabilities `enabled=false` by default.
Wire D3 writes. **The typed `LANE_DIRECTION` invariant lands here.**

**E1 acceptance criteria:**
- **[CC linchpin] No auto-path to live**: `LANE_DIRECTION` table is loader-owned; STEP-1
  `expand`→MANUAL is checked first and non-overridable by any tier/posture; there is **no
  `lane: live` value**; loader **rejects** a config that declares `autonomy_level` or tries to
  auto-apply an `expand` lane. (CC stress-test 5/10.)
- **[C1] Orchestrator has zero `promote_tier`/autonomy-raiser references** — grep proof in the
  Orchestrator + (later) §O modules; only writers that *raise* autonomy are reachable from the
  operator human-confirm route. (CC stress-test 15.)
- **[C2] No branch on `can_auto_deploy_to_paper`** to decide demo auto-vs-manual (it is
  True@all-tiers `learning_tier_gate.py:185/196/205/218/231` → no signal); loader rejects a
  config that uses it as a posture gate. (CC stress-test 16.)
- **[F.2] No model-adjudication path** — cross-capability + L2-vs-governor conflicts resolve via
  the fixed precedence table (`contract` > `expand`; stricter wins; unresolved → escalate, no
  auto-apply); a gate `reject` always beats an L2 `recommend`. Grep proof: no code path where a
  model output adjudicates two proposals. (CC stress-test 6.)
- **[E3 E1] Every Orchestrator/registry WRITE endpoint is operator-scope** (reuse
  `governance_autonomy_service` / `governance_extended_routes` operator-role/TOTP pattern);
  reads stay read-only and cannot mutate. (CC stress-test 18.)
- **[F.1] Storm control**: admission order dedup→debounce→coalesce→budget→tier/posture; a trigger
  storm cannot blow the DOC-08 $2/day envelope even with debounce off; suppressed volume logged
  with a `trigger_decision` reason; per-capability hard daily call ceiling degrades to NO_ADVICE.
- **[F] Fail-safe**: HEALTHY→RETRY→DEGRADE_OLLAMA→NO_ADVICE→TRIPPED→GLOBAL_CONSERVATIVE; the
  iron rule — **no path from any fail-safe state to "block the deterministic baseline" or
  "auto-apply to live"**; worst case = NO_ADVICE = today's behavior. (CC/E3 stress-test.)
- `unknown field → reject load`; `enabled` defaults false (fail-closed).
- Orchestrator + admission/adjudication singletons registered in singleton SSOT; route handlers
  are parse→call→format only (business logic below).

**Sign-off points:** **CC (stress-tests 5/6/10/15/16/18 — the load-bearing compliance audit)**,
E2, **E3 (E1 write-endpoint operator-scope; fail-safe never blocks under fault injection)**, E4, QA.

**Gate to P3:** CC APPROVE on the no-auto-path-to-live + carbon-layer fences; fail-safe verified;
all write endpoints operator-scope.

---

### Phase 2p (parallel, cheap, local — independent of P1/P2 cloud path)

**Scope:** `incident_sentinel` — local liveness/anomaly/regime detection on the watchdog→alert
wire (sibling PA report `2026-06-05--watchdog_alert_wiring_design.md`). `model_tier=local_sentinel`,
`direction=neutral`/alert-only, **never remediate**. Closes the 20h-silent-outage gap.

**E1 acceptance criteria:** local-only (no cloud dependency for liveness — E3 sentinel-locality
check); alert ≠ remediation (L2 may *draft* a runbook step, never executes); does not touch the
stop/conditional-order path; consumes the watchdog→alert wire, not parallel to it.

**Sign-off points:** E2, E3 (sentinel locality), E4, QA. **Gate:** independent — may ship
alongside any phase; no D3-blocking, no cloud.

---

### Phase 3 — `ml_advisory.v1` (FIRST L2 capability — operator's choice)

**Scope:** attaches to the existing ML pipeline (`run_training_pipeline.py` /
`mlde_shadow_advisor.py` / `leakage_check.py`; V031 view). Three advisory modes
(hypothesize→backlog / diagnose_leak / interpret_result), all `direction=neutral`, feeding the
existing `applied=false`/`requires_governance=true` surface — 0 new execution authority. Cascade
Ollama screen → deterministic math/leak gate → cloud-L2 interpret on survivors only.

**E1 acceptance criteria:**
- **[B1 — gated on QC sign-off for promotion-relevant verdict]** the math gate this capability
  uses includes the deterministic `beta_neutral_check` (§N.1): **dual-factor BTC+altcap
  mandatory** (BTC-only → DEFER), OLS at **daily/4h** (not 1m), `|β_btc|<0.15` AND `|β_alt|<0.15`,
  **down-market `|β_down|<0.15`** with down-market def = 30d drawdown >8% OR 7d return <-5%
  (lagged-PIT, ≥30 bars else DEFER), and `β_upper = β+1.96·SE < 0.20`. **Diagnose/interpret modes
  (assert no alpha) may ship before B1 final numbers; hypothesize→promotion-relevant verdict may
  not.**
- **[Q1] math-gate step-0**: `N_trades_oos ≥ 50` else verdict = DEFER (third state); DEFER
  propagates to §C.3 (cannot auto-promote) and §N (`gate_verdict:"DEFER"` shown).
- **[M3] leak typing**: every leak/PIT claim carries `source_class ∈ {name_pattern_check,
  shift1_compliance, is_oos_gap}`; a `name_pattern_check` (leakage_check.py) pass is NOT
  sufficient for the leak-free precondition of the math gate; `ml_advisory` may not claim
  `leakage_check` output as leak-free PIT evidence.
- **[M4] Ollama screen calibrated**: recall ≥ 0.85 on the held-out good/bad benchmark set
  ("loose" = most-permissive operating point that still meets recall ≥ 0.85); below that → screen
  disabled (degrade to "no screen", everything to math gate) and flagged to MIT.
- **[C2]** demo-promotion path (if any) does not read `can_auto_deploy_to_paper` for auto-vs-manual.
- out-of-bound guard: reject hypotheses whose `signal_axes_used ⊄ available_signal_axes`, reject
  empty mechanism (curve-fit guard), dedupe against `dead_failure_modes` (novelty), reject a
  promotion-ready interpretation lacking a `regime_caveat` when metrics flagged bull-only.
- PromptContract is a **deterministic versioned template** (Ollama forbidden from generating
  prompts); `contract_ver`+`schema_ver` written to every D3 row.
- bull-only / rally-dominated results labeled `regime-bet/learning-only` per Alpha Evidence
  Governance — never called promotion proof.

**Sign-off points:** PA (read the ML-pipeline seam in full first), E1, E2, **QC (B1 final
numbers + leak-free PIT features)**, **MIT (M3 leak coverage + M4 recall calibration)**, E4, QA.

**Gate to P4:** ml_advisory green on the cascade + the deterministic math gate (incl. B1 once
QC signs off); the first capability proves the full cascade the research loop reuses.

---

### Phase 4 — online-FDR research loop (tier-gated L3+)

**Scope:** `ResearchAlphaWealthController` (LORD/SAFFRON α-wealth, GREENFIELD) + sealed-holdout
sealer for V132 (the 0-write gap) + novelty gate (agent.lessons V133 dead-modes) +
pre-registration (`research.pre_registered_hypotheses`) + N_eff cluster controller + Q3 cascade.
Upgrades the ml_advisory backlog into a disciplined infinite-test stream. Resource-isolated from
the live engine (§K2).

**E1 acceptance criteria:**
- **[M1 — MIT-ratified] refund accounting**: `W_0 = γ·α_target`, **γ=0.10**, per
  (capability×signal-axis) family; debit `W ← W − α_i` on test; **φ=1.0 proportional refund**
  on demo-confirmed discovery only; in-flight debits stay debited (`pending→confirmed` refunds,
  `pending→failed` does not); **demo-confirm bar = `n_trades ≥ 30` AND green Stage 0R AND
  non-negative demo net edge AND ≥21 forward-OOS days**. NOTE folded: **`debit_state` in
  persistent PG `research.alpha_wealth_ledger`** (not in-memory fail-safe); per-test
  **`α_i ≤ α_target / min_batch_size` cap**; docs distinguish the `n_trades ≥ 30` refund bar from
  the `N_trades_oos ≥ 50` math-gate precondition.
- **[M2 — MIT-ratified] N_eff single-debit wiring**: N_eff computed from the variant cluster via
  **average-linkage, Pearson corr > 0.5 cut**; **one effective trial ⇒ one DSR K-slot
  (`K_for_dsr = N_eff` into `dsr_gate`) AND one α-wealth debit/refund per cluster** — no
  double-charge, no double-count; cluster representative = best-by-DSR member carries the
  debit/refund. NOTE folded: **`max(1, N_eff)` guard** (K=0 raises); **`max_variants_per_cluster`**
  anti-abuse; `dsr_gate` `n_trials` interface already compatible (no breaking change).
- **[B2] forward-OOS bar** `MIN_FORWARD_OOS_DAYS = 21` enforced in the deterministic applier,
  posture-independent; no auto-promote with `forward_oos_days < 21` or a §G.2 DEFER verdict.
  (CC stress-test 17.)
- sealed-holdout sealer actually writes `state='sealed'` (V132 0-write gap closed) and the
  auto-loop cannot see or change sealed splits; `ON CONFLICT` emits a NOTICE so a double-seal is
  observable (MEDIUM folded).
- pre-registered `{spec, mechanism, falsification_test}` is **immutable** after registration;
  `falsification_test` has structured sub-fields `{null_hypothesis, test_statistic,
  reject_condition}` (MEDIUM folded).
- family partitioning per (capability × signal-axis); cross-axis discoveries don't subsidize.
- **[M4]** Ollama generator/screen recall ≥ 0.85 (re-measured monthly + on benchmark version bump).
- `ResearchAlphaWealthController` + N_eff cluster controller registered in singleton SSOT;
  research workers resource-isolated (nice/cgroup, separate PG pool, off-peak) — must not starve
  the live engine (E3 stress-test #3).
- V13x table(s) (`research.alpha_wealth_ledger`, `research.pre_registered_hypotheses`,
  `research.gate_rule_candidates`): Linux PG dry-run + double-apply idempotency.

**Sign-off points:** **MIT (M1 + M2 final ratification — gates this phase)**, QC (pre-registration
prevents post-hoc spec mining; sealed-holdout prevents reuse), E2, E3 (research-worker resource
isolation), E4, QA.

**Gate to P5:** MIT APPROVE on M1 + M2; sealed-holdout proven; FDR controller self-throttles on
demo-confirmed discovery.

---

### Phase 5 — feedback→rule pipeline (§M) + per-capability quality/ROI metric (§O) + GUI

**Scope:** `research.gate_rule_candidates` feedback pipeline (§M: ①gate-rule-candidate /
②lesson / ③demote) + `learning.l2_capability_quality` metric + `learning.l2_promote_candidates`
read-only inbox (§O.4) + the GUI panel (tier ladder + Posture + LIVE hard line + per-capability
cards + §N live-cross approval inbox + NL-on-demand + §H.1 annotations).

**E1 acceptance criteria:**
- **[C1] promote-candidate = read-only inbox row**: §O HIGH branch writes
  `learning.l2_promote_candidates`; **only** the operator-scope TOTP-gated human-confirm route
  flips `pending→confirmed` AND performs the actual gate-removal/promotion; grep proof: §O metric
  module has **zero** `promote_tier`/autonomy-raiser references. (CC stress-test 15.)
- **[R2-1] no automatic autonomy expansion anywhere**: no code path where the §O metric (or any
  tier/posture/feedback/schedule signal) removes a trust-gate, widens an auto-applicable lane, or
  raises effective autonomy without a human-confirm event; every automatic autonomy writer moves
  **down** only. (CC stress-test 10 — the linchpin.)
- **[R2-2] promote signal excludes adoption**: `promote_signal = w_corr·post_hoc_correctness −
  w_cost·(cost/value)`; adoption is weak-tiebreak-only, excluded from the promote decision; a
  high-adoption/low-correctness capability **demotes**. (CC stress-test 11.)
- **[R2-3] low-sample can only contract**: below the sample floor → no promote-candidate
  emittable; a single clearly-bad outcome can still demote/disable. (CC stress-test 12.)
- **[§M demote-only]** the feedback pipeline has **no promote target**; ② (lesson) / ③ (demote)
  are fail-safe-direction and immediate; ① (new gate rule) lands as a PROPOSED, review-gated,
  test-required `research.gate_rule_candidates` row (never auto-active); the ① queue degrades
  gracefully (safety contractions already fired). (CC stress-test 7.)
- **[Q2] live-cross packet** shows `cost_edge_ratio`/`gross_edge_bps`/`total_cost_bps` +
  `max_dd_duration_days`, the deterministic `beta_neutral_check` (B1: residual β + down-market β +
  factor model + window), and `gate_verdict` incl. DEFER (Q1).
- **[R2-4] live packet is math-primary**: block 5 has **no `verdict`/`cross|hold|reject` field**
  (caveats/risks-noted only), rendered subordinate to + gated behind `math_ack_required`; the
  packet endpoint is read-only and cannot itself approve. (CC stress-test 13/14.)
- **[Q3] cold-start blind window**: while `N_outcomes < floor` the card shows a "blind window —
  k/N" badge, displays human-review **proxy** correctness (clearly labeled proxy, cannot drive a
  promote-candidate), and raises the manual-audit cadence.
- **[E3 E1]** the human-confirm promote action + `/cost/reset` + `/cost/pricing` are operator-scope
  writes; all §O/§H/§N reads stay read-only. (CC stress-test 18.)
- GUI is **Vanilla JS** (no React/Vue/Angular); `node --check` (or stronger) passes; route
  handlers parse→call→format only; LIVE hard-line banner always visible; per-layer annotations
  rendered (Chinese-primary per repo convention, §H.1 draft strings).

**Sign-off points:** **CC (stress-tests 7/10/11/12/13/14/15/18 — the second load-bearing audit)**,
**QC (Q2/Q3)**, E2, **E3 (E1 endpoint auth)**, E4, QA. GUI: E1a finalizes wording.

**Gate to done:** CC APPROVE on the no-auto-expansion linchpin + the read-only promote inbox;
math-primary live packet verified; GUI green.

---

## 3. Cross-phase invariants (CC re-checks every phase, all three engines)

Per `16-root-principles-checklist` and CLAUDE Hard Boundaries — verified in **every** phase, not
once; 3E-ARCH (paper/demo/live) verified independently (no "only-paper-PASS"):

- L2 touches **none** of `live_execution_allowed`, `max_retries`, `OPENCLAW_ALLOW_MAINNET`,
  `authorization.json`, `execution_authority`, `system_mode`, lease **trading** authority.
- `can_modify_live_config=False` at all tiers (already hardcoded `learning_tier_gate.py:664-671`).
- Live requires the unchanged 5 gates + Decision Lease, human-only; the auto-loop structurally
  cannot reach the live row (`expand`→MANUAL, loader-enforced).
- Single write entry (principle 1): L2 has no order path; proposals reach effects only via
  existing deterministic appliers/gates.
- AI output ≠ command (principle 3): output → deterministic gate → (proposal) → human for live.
- Survival > profit (principle 5): the typed `LANE_DIRECTION` asymmetry + the deterministic
  `beta_neutral_check` (B1) + forward-OOS bar (B2) + `N_trades_oos≥50` DEFER (Q1) are hard gate
  members — the down-beta / in-sample / small-sample masquerades cannot pass an unattended gate.
- AI cost ≥ edge (principle 13): cloud spend only on math survivors; per-capability + tier-gated
  budget; §O auto-disables cost>value; DOC-08 $2/day cap holds unless a documented ROI rule raises
  it (open question, operator call).

---

## 4. Open questions for operator (do not block E1 start; resolve before the dependent phase)

1. **[OPEN] D3 retention economics** — full prompt+response × projected volume; at what call rate
   does TimescaleDB compression stay affordable (sets the non-consequential TTL)? (P1/P4.)
2. **[OPEN] Auto-trigger cadence vs DOC-08 $2/day** — per-capability daily cloud envelope; may a
   high-ROI capability exceed $2/day "by rule," and what is the rule? (P2 has the hard ceiling +
   §O auto-disable backstop; the override policy itself is an operator call.)
3. **[OPEN] §O promote weights + sample floor + sustained-HIGH threshold** (`w_corr`/`w_cost`, N,
   threshold) — sets how fast a capability *earns the right to ask*; recommend strict + high floor.
   (P5.)
4. **[OPEN] §M-① gate-rule-candidate review SLA** — who reviews (PA/CC) and on what cadence (the
   SLA governs how fast improvements land, not whether safety holds — ②/③ are immediate). (P5.)
5. **[OPEN] §F.1 debounce defaults per trigger class** — regime-transition vs anomaly vs
   ml:training_complete; operator/E5 tune vs cost. (P2/P4.)
6. **[OPEN] Ollama generation quality** — is local Ollama strong enough to *generate* the
   hypotheses without a false-kill/false-pass storm? (M4 calibration is the guard; P3/P4.)

---

## 5. Completion check (as of this plan)

Complete:
- v4-final design 0 CRITICAL; QC B1 / MIT M1 / MIT M2 re-confirm = **ENDORSE**; 2 BLOCKER + ~11
  HIGH spec-gaps closed in the design body; MEDIUMs folded into §L.
- This executable roadmap (phase decomposition + per-phase E1 acceptance + sign-off points + gates).

Not complete (awaiting operator go to start E1):
- No code, no migration (V134/V13x), no DB write, no deploy, no singleton registration has landed.
- B1 final numbers / M1 + M2 final ratification are **endorsed in principle**; the FIX/NOTE above
  are the E1 acceptance form — QC/MIT confirm the concrete constants at their phase sign-off.
- Three-end sync of any committed plan/TODO is **PM's** action, not this plan's.
