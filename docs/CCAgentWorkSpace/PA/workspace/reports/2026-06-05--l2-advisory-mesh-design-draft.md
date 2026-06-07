# PA DESIGN v4-final — L2 Advisory Mesh

Date: 2026-06-05 (v1) · 2026-06-07 (v2 = PM round 1; v3 = PM round 2; **v4-final = four-review
sign-off close-out of v3** by CC / MIT / QC / E3)
Author: PA (Project Architect)
Status: **v4-final** — the **closing** revision. All four adversarial reviews (CC compliance,
MIT quant rigor, QC data/backtest, E3 security) returned **0 CRITICAL** and **endorsed the
design skeleton**; v4 closes the **2 BLOCKERs + ~11 HIGH spec-gaps** they required **before E1
may start**, plus the MEDIUMs folded into §L. v4 is **spec-tightening only** — it adds the
*deterministic computation rules*, *sample/auth/sanitize preconditions*, and *carbon-layer
forbiddances* the reviews demanded; it **introduces no new architecture, no new authority, no
new live path**, and **preserves every v3 strength verbatim**. The single most important close
is the **alpha command-line**: v3 left `beta_neutral_check` and the FDR / N_eff plumbing as
*named-but-underspecified*, which on an unattended gate is exactly where the **down-market-beta
masquerade that has killed 5 candidates** would slip through. v4 makes those **deterministic and
sign-off-backed**. Risk class of the *design surface*: 中→高 (touches autonomy gating, learning
plane, provenance, AI cost — but **0 trading-truth / 0 order / 0 lease-authority** writes by L2).
Scope discipline: this is the **advisory copilot** architecture. L2 **never orders, never
auto-mutates live**. Every "apply" is reversible / non-live-lane only. **v3's "expand=human,
closed under autonomy itself" is preserved; v4 adds the carbon-layer proof that the Orchestrator
cannot even call the tier-promotion primitive (B/C/M/Q/E findings below).**

> **B1 / M1 / M2 are marked `NEEDS QC/MIT RE-CONFIRM`** — the deterministic numbers (beta factor
> set, β window, |residual_beta| threshold, regime-conditional rule; the online-FDR refund
> formula + W_0; the N_eff→FDR debit accounting) are **proposed by PA for QC/MIT to ratify or
> amend before E1 sign-off**. They are written as concrete defaults so the re-confirm is an
> *edit*, not a *blank*. Everything else in v4 is design-decided.

> This document is a **design**, not code. It marks (a) what is **reused** vs **new**,
> (b) what is **verified** against the repo today, (c) what is **needs-verification**,
> and (d) what must be **stress-tested by QC / MIT / E3 / CC** before any capability
> ships. Read §L (open questions) before acting.

---

## v4-final CHANGELOG vs v3 (four-review close-out)

This revision **does not re-litigate v3**. Every v3 strength is kept: §C.2 derived autonomy,
the typed `LANE_DIRECTION` invariant, the "expand=human closed under autonomy itself" (R2-1),
the de-Goodharted promote signal (R2-2), low-sample-contract-only (R2-3), the math-primary live
packet (R2-4), live-trade provenance (R2-5), and §M graceful degradation (R2-6). v4 closes the
**2 BLOCKER + ~11 HIGH** spec-gaps the four adversarial reviews required **before E1**, and
folds the MEDIUMs into §L. The findings, by owning review:

**QC — 2 BLOCKER (alpha command-line; highest priority):**
- **[B1] `beta_neutral_check` is now a deterministic spec, not an L2-self-defined pass/fail
  (§N.1 new).** This is the unattended-gate command-line: the *down-market-beta masquerade that
  killed 5 candidates*. v4 fixes (1) a **factor model** (≥ BTC beta; recommended **two-factor
  BTC_return + cap-weighted alt_return**), (2) a **≥90d rolling** estimation window (not 30d),
  (3) a **deterministic `|residual_beta| < 0.15`** threshold (not L2-chosen), (4) a
  **regime-conditional beta** re-check under down-market. **Marked `NEEDS QC RE-CONFIRM` /
  requires QC design sign-off.** (§N.1, §E(ii) guard, §G.2 gate, §K row 5/16.)
- **[B2] auto demo promotion now has a hard `min_forward_oos_days ≥ 21` precondition (§C.3
  new), independent of posture.** Stage 0R = historical in-sample replay = *necessary not
  sufficient*; it never substitutes for forward OOS. This is a **deterministic constraint, not
  L2 advisory**, and it gates the *act of auto-promoting to demo* regardless of Conservative/
  Standard. (§C table demo row, §C.1, §C.3, §B `LANE_DIRECTION` note.)

**CC — 2 HIGH (carbon-layer autonomy boundary):**
- **[C1] The Orchestrator is forbidden *in code* from calling `promote_tier()` (§A.1, §O.4
  new).** Verified: `learning_tier_gate.promote_tier()` auto-promotes L1→L4 with **no
  `approved_by`** (only L5 needs it). So the §O promote-candidate writes a **read-only inbox row**
  (`learning.l2_promote_candidates`); the **real tier/gate promotion runs only from the existing
  operator route** (the `governance_extended_routes` / TOTP-gated posture-switch pattern). New CC
  E2 test: grep proves the Orchestrator module has **no import of / no call to** `promote_tier`
  and no other auto-raise-autonomy writer. (§A.1, §O.1, §O.4, §L CC stress-test 15.)
- **[C2] `can_auto_deploy_to_paper=True@all-tiers` is demoted to a *capability-unlock* flag, not
  a demo auto/manual decider (§C.2 STEP-3, §C.3).** Verified: it is `True` at L1-L5, so it
  **cannot** gate demo posture. Demo auto-vs-manual is decided **solely** by the `LANE_DIRECTION`
  loader + §C.2 STEP-3 + the §C.3 `min_forward_oos_days` precondition; the Orchestrator **must not
  read `can_auto_deploy_to_paper` as a posture decider** (else Standard could silently auto-apply).
  (§C.2 STEP-3, §C.3.)

**MIT — 4 HIGH (statistical core):**
- **[M1] online-FDR refund policy is now precise (§G.1.1 new).** Specifies `W_0` initial wealth,
  the **refund amount formula** (full α_t vs proportional), in-flight-variant wealth accounting,
  and a **demo-confirmation minimum bar (`n_trades ≥ 30`)** before a discovery counts as
  confirmed. **Marked `NEEDS MIT RE-CONFIRM`.** (§G.1.1.)
- **[M2] N_eff deflation is now wired to the FDR controller (§G.1.2 new).** Verified: `dsr_gate`
  deflates by `n_trials_K` (a manifest input) but **does not compute or export N_eff**. v4
  specifies how N_eff is derived from the variant cluster and **handed to the α-wealth
  controller**, and how the **two rejection mechanisms (DSR K-deflation + α-wealth debit) share a
  single debit** so a discovery is not double-counted nor double-charged. **Marked `NEEDS MIT
  RE-CONFIRM`.** (§G.1.2.)
- **[M3] `leakage_check.py` is downgraded from "leak-free proof" to "name-pattern check only"
  (§E(0) source_ref typing, §G.2 gate note).** Verified: it is **pure feature-name substring/
  prefix matching** (78 lines) — it cannot catch missing `shift(1)` look-ahead, resample-boundary
  leak, or cross-section leak. So `ml_advisory` **may not claim `leakage_check`=leak-free PIT
  evidence**; the §E(0) leak `source_ref` must be **typed** as one of three classes:
  `name_pattern_check` / `shift1_compliance` / `is_oos_gap`. (§E(0), §G.2, §L MIT.)
- **[M4] Ollama gatekeeper calibration SOP added (§G.2.1 new).** A held-out good/bad-hypothesis
  benchmark set measures the screen's **precision/recall**, with a **recall floor (≥ 0.85)** that
  defines the "loose coarse screen" boundary (the screen must not false-kill real alpha). (§G.2.1.)

**QC — 3 HIGH:**
- **[Q1] math gate gets a step-0 sample precondition (§G.2 gate, §N.1).** `N_trades_oos ≥ 50`
  before DSR/PBO may be computed; below it the gate verdict is **DEFER** (a third state, not
  PASS/FAIL) — small-sample false-positive guard. (§G.2, §N math_evidence, §C table.)
- **[Q2] live-cross `math_evidence` gains the cost decomposition + DD-duration (§N block 1).**
  Adds `cost_edge_ratio`, `gross_edge_bps`, `total_cost_bps` (6 candidates died of edge<cost — a
  human cannot math-self-judge without the cost breakdown) and `max_dd_duration_days`. (§N.)
- **[Q3] cold-start blind-window protocol (§O.5 new, §H card).** While `N_outcomes < floor`, the
  §O metric logs a **human-review proxy correctness**, the GUI capability card shows a
  **"blind window" warning**, and that capability's **manual-audit cadence is raised**. (§O.5, §H.)

**E3 — 2 HIGH (security / secret-leak):**
- **[E1] all new write endpoints are operator-scope auth-hardened (§N.2 new).** `/cost/reset`,
  `/cost/pricing`, and every new Orchestrator / registry **write** endpoint require operator
  scope (read endpoints stay read-only). (§N.2, §L E3.)
- **[E2] D3 ledger sanitizes before persisting full prompt/response/`final_summary` (§D.1.1
  new).** `str(e)` / raw error strings / any secret-bearing context **never enter the ledger**; a
  deterministic sanitize pass runs **before** the append-only write. (§D.1.1, §L E3.)

**MEDIUM (folded into §L, do not block v4):** cross-axis FDR family membership · V132 `ON
CONFLICT` NOTICE · `available_signal_axes` caller healthcheck · `regime_confidence` +
`drawdown_pctile` PIT snapshot at trigger-time T (last *closed* bar) · `bull_only_flag`
deterministic rule (not LLM-judged) · `falsification_test` structured sub-fields + spec
immutability · §M-③ "clearly-bad" operationalized (`net_edge < −5bps` & `N ≥ 10`) · V134
`consequential` post-stamp vs append-only reconciliation · canary alert consumer (covered by the
local sentinel, build #3).

**Net delta v3→v4:** v3 was *architecturally complete and safe*; v4 makes it *E1-ready* by
turning every "named but underspecified" gate into a **deterministic, sign-off-backed rule** —
most importantly the **beta-neutral command-line (B1)**, the **forward-OOS demo precondition
(B2)**, the **carbon-layer proof the Orchestrator cannot raise autonomy (C1)**, and the
**FDR/N_eff/leak statistical truth (M1/M2/M3)**. **No new architecture, no new authority, no new
live path.** The skeleton is the four-reviewer-endorsed v3 skeleton; v4 only fills the spec.

---

## v3 CHANGELOG vs v2

This revision is **PM-led iteration round 2 of 3**. It does **not** re-litigate v2's preserved
strengths — §C.2 derived autonomy, §M's "suppress/demote immediate, new-rule reviewed" asymmetry,
§N's deterministic blocks + dissent, §O's dual closed-loop skeleton are all kept. It hardens the
**autonomy-expansion boundary**, the one place v2 still let the system enlarge its own automatic
scope without a human. Six changes (R2-1 is structural; the rest reinforce it):

**R2-1 [structural — the load-bearing fix]: autonomy PROMOTE is now permanently human-confirmed;
auto-promote is removed.** v2 §O let a *sustained-HIGH* metric **auto-remove** the §C.1 human
trust-gate. That is itself an **`expand` action performed automatically** — it enlarges what the
system may do without a human — which **contradicts §C.2 "expand=human"** and is the most
dangerous "system self-expands its own autonomy" hole. **v3 resolution:** *any* autonomy PROMOTE
— widening the auto-applicable scope, **including removing any trust-gate** — **always requires
human confirmation**. §O's metric role is **not to auto-expand** but to make that human decision
**trivial**: it produces a **"promote-eligible candidate"** (earned-trust evidence digest +
one-click promote) that a human confirms. **DEMOTE stays automatic** (fail-safe direction). This
makes "expand=human" **truly universal — it now governs autonomy itself**, closing v2's last
self-expansion back-door and re-aligning the design with the repo's own `_AUTONOMY_PATH_MATRIX`
(verified: row (a) promotion is `operator manual` at level1; promotion only ever auto-runs after
**a human flips the posture switch**, never because a metric decided on its own). §O, §C.1, §C.2,
§H.1, §K row 11/12, §L Q7, and the CC stress-test list are all updated. (See §O.1.)

**R2-2: the promote signal is de-Goodharted — `post_hoc_correctness` + `cost-value` primary,
`adoption` demoted out of the promote path.** v2's `quality_score` weighted `adoption` (the
fraction accepted by gate/human) as a promote driver. Adoption ≈ "agreement with the gate" and is
**Goodhartable** — a compliant-but-useless capability can inflate adoption. **v3:** the
(now human-confirmed) **promote-eligibility signal is primarily `post_hoc_correctness` +
`cost-value`; `adoption` is at most a weak tiebreak and is excluded from the promote decision.**
**DEMOTE** is triggered by **low post-hoc-correctness OR cost>value** (independent of adoption),
so "obedient score-farming → wrongful promotion" is structurally impossible. (See §O.2.)

**R2-3: low-sample asymmetry made explicit.** A low-frequency capability (e.g. incident-diagnosis,
rarely triggered) may never reach the sample floor → its metric is slow/noisy. **v3:** **below the
sample floor → never PROMOTE-eligible (stay conservative), but a single clearly-bad outcome may
still DEMOTE/DISABLE** (fail-safe direction). Small samples never *drive an expansion*; they can
still *trigger a contraction*. (See §O.3.)

**R2-4: the live-cross packet's L2 verdict is demoted — live stays math-primary.** v2 §N block 5
gave L2 a **cross/hold/reject verdict** on the **highest-risk live crossing** — which would
**anchor** a time-pressured human and brushes against "LLM must not drive trading." **v3:** on the
live-cross packet, **L2 gives no cross/hold/reject verdict**; block 5 becomes **"L2 caveats /
risks-noted"** only. The **math evidence + provenance + dissent are the primary case**, and the
human forms the judgment from the **math-primary** evidence. The (non-verdict) L2 notes are
visually **subordinate to the math** and **gated behind a human acknowledgement of the math**
before they render. This keeps the live decision math-primary and removes the anchoring / again
"LLM-drives-trading" risk. (See §N.)

**R2-5: live-trade provenance is threaded post-cross.** v2's §D.2 chain stopped at demo (correct
pre-cross). But **after a human crosses to live, live trades must also carry `l2_reply_id`**, so a
live loss months later traces to the originating L2 reply — the deep-forensic the operator cares
most about. **v3:** the chain `reply → hypothesis → variant → replay → demo → **live trades**` is
explicitly threaded **in the post-cross direction** (the live Decision-Lease audit row **and** the
resulting live fills / decision_outcomes carry the propagated `source_l2_reply_id`). (See §D.2.)

**R2-6 [minor]: §M rule-queue graceful degradation.** If the §M-① gate-rule-candidate review queue
stalls on human availability, **the system degrades gracefully**: §M-② suppression and §M-③ demote
already apply *immediately* (they protect safety), so only the **behavior-changing new rule ①**
waits — consistent with "the human is not a safety bottleneck." (Already open Q8; v3 states the
graceful-degradation guarantee inline.) (See §M.)

**Net structural delta v2→v3:** v2 made the mesh self-governing but left **one** automatic
self-expansion path (metric auto-removes a trust-gate). v3 **seals that path**: the only thing the
system may do automatically toward *more* autonomy is **prepare a human's promote decision**; every
actual expansion — trust-gate removal included — is human-confirmed, while every contraction stays
automatic. The promote signal is de-gamed (correctness/value, not adoption), low-sample can only
contract, the live packet is math-primary (L2 no longer renders a live verdict), provenance now
reaches live trades, and the rule queue degrades gracefully. **"L2 proposes, deterministic gates +
lane-bound appliers decide, humans own live, forensics, AND every autonomy expansion." No new
trading authority, no new live path, no change to the safety thesis — only a stricter, now-truly-
universal "expand=human."**

---

## v2 CHANGELOG vs v1

This revision is **PM-led iteration round 1 of 3**. It does **not** re-litigate v1's
verified strengths (grounding §0, reuse-vs-new framing §I, governance mapping §K, worked
examples §E, fail-safe state machine §F) — those are preserved. It changes the following.

**A. Applied operator's 3 decisions (v1 was stale / open on these):**
1. **First Tier-1 capability after D3 = ML hypothesis/diagnosis advisor** (operator chose
   this over v1's recommended incident-diagnosis). Scoped to the **v1 version**: it attaches
   to the **existing ML pipeline** (feature hypotheses → backlog + leak/drift diagnosis +
   training-result interpretation; Ollama→math→cloud cascade + D3 provenance). It does **not**
   require the full online-FDR research loop first. Build order §J reordered to
   **D3 → ML advisor (on existing pipeline) → online-FDR research loop → rest**. New worked
   example **`ml_advisory.v1`** added to §E. incident-sentinel demoted to a **parallel cheap
   local fix** (still in §J, no longer the first L2 capability). §L Q4 updated.
2. **Defensive risk-tighten = automatic, operator-confirmed-accepted** (bounded + cooldown;
   the deterministic governor owns the final clamped number). The asymmetry "tighten auto /
   loosen + live human" is **upgraded from a documented principle to a typed structural
   invariant** (a `lane.direction` property + loader enforcement, not just prose). §L Q3 marked
   RESOLVED.
3. **Shipped Posture default = Conservative** — confirmed. §L Q5 marked RESOLVED.

**B. Closed v1's underspecified gaps (these were one-liners / "mentioned only" in v1):**
4. **Feedback → rule pipeline** (v1 Q7 was one bullet): now a **first-class process** — §M.
   "post-hoc forensic conclusion → one-click into ① new deterministic gate rule, OR ②
   novelty-failure-library pattern, OR ③ a capability autonomy demote." Process-driven so it
   does not depend on a human remembering.
5. **One-page live-cross packet** (v1 mentioned only): full content spec — §N. (math evidence
   digest + complete provenance chain + NL summary + current 5-gate status checklist +
   recommended decision.)
6. **Per-capability quality / ROI metric** (v1 named it, never defined it): defined — §O.
   adoption rate / post-hoc correctness / $-spend-vs-value, **auto-driving each capability's
   keep / promote / demote autonomy** + a cost-benefit close-the-loop.
7. **Full provenance lineage chain**: §D.2 upgraded — `l2_reply_id` now threads
   **L2 reply → hypothesis → strategy → demo result → (live)** end-to-end, so a live problem
   months later traces to the originating reply (not just a hypothesis row — the whole chain).
8. **Trigger debounce / storm control** (v1 had only per-call cooldown): added explicit
   **debounce / dedup / coalesce** — §F.1.
9. **Conflict resolution** (absent in v1): cross-capability conflicts and L2-vs-deterministic-
   governor conflicts now have a deterministic adjudication rule — §F.2.

**C. Contradiction / clarification resolved:**
10. v1's "human exits inline" vs §C "demo Stage1 = operator manual under Conservative" was
    self-contradictory. **Resolved: option (b)** — Conservative **deliberately** inserts the
    human at demo-promotion as a **trust-building stage**; higher tiers auto-remove it. Made
    consistent with "the human's limits must not become the bottleneck" (the human is a
    *temporary* trust gate at low tier, not a permanent inline reviewer). §C table + §C.1.
11. **GUI per-layer annotation text** (operator's explicit Q2): actual annotation copy drafted
    (each tier meaning, each Posture effect, the live hard line, each capability) — §H.1, not
    just "annotate".

**D. Highest-standard optimization (simplicity):**
12. **Simplified autonomy knob**: v1 had `capability.autonomy_level` × lane × Posture × tier +
    a max-strictness rule = too many knobs. v2 **derives `autonomy_level` from
    (lane + tier + posture)** — single source of truth, fewer config knobs. The capability
    registry §B **no longer stores `autonomy_level`**; it is computed. §C.2 gives the derivation.
13. **online-FDR parameter policy** (design-level intent; the math stays MIT's): stated in §G.1
    — conservative initial α-wealth, **refund only on demo-confirmed discovery** (not merely
    passing a gate), family partitioned by capability / signal axis.

**Net structural delta:** v1 = "complete a half-built nervous system." v2 = same thesis, plus
the **closed-loop discipline** that makes it self-governing: provenance is now a *full chain*,
feedback is a *pipeline*, quality is *measured and drives autonomy*, the autonomy knob is
*derived not configured*, and the tighten/loosen asymmetry is a *typed invariant the loader
enforces*. No new trading authority, no new live path, no change to the safety thesis.

---

## 0. Grounding — what the repo already gives us (VERIFIED today)

I read the source before designing. Confirmed wired/dormant status:

| Component | File / migration | Status | Load-bearing fact for this design |
|---|---|---|---|
| `LearningTierGate` L1–L5 | `learning_tier_gate.py` | **WIRED** | Instantiated `paper_trading_wiring.py:374`; injected into `GovernanceHub.set_learning_tier_gate()`; drives `analyst_agent.update_metrics()`; **enforced** at `governance_hub.py:1286` (de-escalation needs L4+). `can_modify_live_config()` returns `False` **hardcoded all tiers** (`learning_tier_gate.py:664-671`) = **the live hard line is already in code**. |
| `TierCapabilities` flags | `learning_tier_gate.py:165-234` | **WIRED (schema)** | Already has `can_generate_hypotheses` (L3+), `can_propose_strategy_variants` / `can_evolve_strategies` / `can_predict_regime_transition` (L4+), `can_optimize_learning_pipeline` (L5+). **These are exactly the L2 capability hooks the operator wants** — no new tier scaffold needed. |
| `Layer2Engine` + 10 routes | `layer2_engine.py`, `layer2_routes.py` | **WIRED, manual-trigger only** | `POST /paper/layer2/trigger` → `run_session(trigger="manual")`. Recommendation → `ShadowDecisionConsumer` (paper/shadow). `is_simulated=True` invariant. **No auto/scheduled trigger today.** |
| `governance_autonomy_service` + `_AUTONOMY_PATH_MATRIX` | `…/control_api_v1/app/governance_autonomy_service.py:80-131` | **WIRED** | Conservative(level1)/Standard(level2) switch (advisory-lock + TOTP + cooldown + fail-closed). `_AUTONOMY_PATH_MATRIX` is a `list[dict[str,str]]`, **already ~20 rows** with a `category` field ∈ {`hard-locked baseline`, `protected`, `protected hard-lock`, `protected fail-closed`, `opt-in`, `opt-in fail-closed`, `hard-locked carve-out`}. Each row has `id/path/category/level1/level2`. **Crucially the tighten/loosen asymmetry is already half-present in the vocabulary**: kill-criteria (e) + health-degradation (j) are `auto-trigger` at *both* levels (contract), while promotions/activations (a)/(c)/(d) are `operator manual` at level1 (expand). **This is the spine for §C and the typed `lane.direction` invariant (v2 change 2).** |
| **ML pipeline** (training + MLDE shadow/demo + leak check) | `program_code/ml_training/` (`run_training_pipeline.py`, `mlde_shadow_advisor.py`, `mlde_demo_applier.py`, `leakage_check.py`, `linucb_trainer.py`, `quantile_trainer.py`) + V031 ML/Dream edge-unblock view | **WIRED** | `mlde_shadow_advisor.py` reads the **V031 training view** and emits **advisory** rank/veto rows into `learning.mlde_shadow_recommendations` with `applied=false` + `requires_governance=true` (deliberately not an execution path). Veto rules already encode `cost_edge_ratio<0.8` / `PBO>0.5` / `DSR<0.95` (V043 allowlist). `leakage_check.py` exists. **This is exactly the existing pipeline the operator-chosen first Tier-1 ML advisor attaches to (v2 change 1) — it reads the same V031 view + training artifacts, proposes feature hypotheses / leak-drift diagnoses / result interpretations, and feeds the SAME advisory `requires_governance` discipline. Strong reuse; the ML advisor is a *reasoning layer over an already-advisory surface*, adding 0 execution authority.** |
| `agent.ai_invocations` | `V064__agent_spine_decision_store.sql:355` + `bybit_ai_invocation_ledger.py` | **WIRED (precedent)** | An AI-call lineage ledger **already exists** (sha256 of text, deterministic ts, idempotency). **D3 must EXTEND this lineage discipline, not reinvent a ledger.** |
| L2 full prompt/response persistence | `layer2_engine.py` | **GAP — confirmed absent** | `system_prompt` is passed to the model but **never written to a durable store**. `Layer2CostTracker` persists only cost/metadata to `runtime/layer2_cost_state.json` (in-process JSON, not the full prompt/response, not append-only audit). **This is the central D3 gap.** |
| `context_distiller.py` | `ContextDistiller.distill_for_prompt()` | **WIRED** | Existing **input → structured-context** path. **This is the Ollama-extraction seam (§E I/O contract, input side).** |
| `layer2_critic.py` | `CriticResult` / `merge_critic_verdict` (continue/replan/stop, fail-soft) | **WIRED (flag-off default)** | Reflexion critic already exists (`OPENCLAW_L2_CRITIC_ENABLED`). **This is the precedent for the Q3 Ollama self-verify / AutoMix gatekeeper.** |
| `agent.lessons` | `V133__agent_lessons.sql` | **WIRED (DB), producer partial** | pg_trgm lesson store; `persist_lessons` / `retrieve_lessons`. **Q6 永久-小 lesson layer foundation exists.** |
| `learning.hidden_oos_state_registry` | `V132` | **WIRED (DB), sealer 0-write** | Durable hidden-OOS state machine (sealed→consumed). Memory note: **0 `state='sealed'` writes today** = the sealer producer is the gap. **Q1 封存輪換 holdout hooks here.** |
| `learning.demo_residual_alpha_reports` | `V131` | **WIRED (DB)** | Residual-alpha report registry (gate-seam evidence precedent). |
| Latest migration | `sql/migrations/` | **V133 is highest** | → **D3 ledger = V134** (next free number; verify no parallel-session V134 lands first). |
| Online-FDR / alpha-investing / LORD / SAFFRON | — | **GREENFIELD** | grep = 0 hits. **Q1 α-wealth controller is net-new (deterministic Python, research-plane).** |
| Singleton registry SSOT | `docs/architecture/singleton-registry.md` | **AUTHORITY** | New mutable singletons (Orchestrator, FDR controller, D3 writer) **must register here before merge** (CLAUDE.md §七/§九). |
| Watchdog → alert wire | `2026-06-05--watchdog_alert_wiring_design.md` (sibling PA report) | **DESIGNED** | The local-sentinel alerting (Tier-1 capability, §J) **builds on this**, not parallel to it. |

**Design consequence:** the L2 Advisory Mesh is **~70% wiring of existing dormant/partial
parts + ~30% net-new (D3 ledger + full-chain provenance, Orchestrator, PromptContract registry,
FDR controller, auto-trigger + admission stage, feedback→rule pipeline, quality metric).** This
is the single most important framing: we are **completing a half-built nervous system**, not
greenfielding one. **v2 reinforces this**: the operator-chosen first capability (`ml_advisory`)
attaches to the **already-wired ML pipeline** and feeds its **already-advisory**
`requires_governance` surface — so even the first capability is mostly wiring + a reasoning
layer, with 0 new execution authority.

---

## A. Architecture overview (total picture)

```
                          ┌──────────────────────────────────────────────────────────┐
                          │  HUMAN (rare, high-leverage)                              │
                          │  • forensics (provenance lookup, post-hoc)               │
                          │  • LIVE-CROSS approver (5 gates + Decision Lease)         │
                          │  • override / pause / kill                               │
                          │  • feedback → new gate rule / failure mode / tier demote │
                          └───────────────▲──────────────────────────▲───────────────┘
                                          │ one-page packet          │ NL on demand
                                          │ (math + provenance)      │
   ┌──────────────────────────────────────┴──────────────────────────┴───────────────┐
   │  GUI: ONE panel — Tier ladder (capability lock/unlock/active) + Posture knob      │
   │       (Conservative/Standard) + bright LIVE hard line + per-layer annotations     │
   └──────────────────────────────────────▲───────────────────────────────────────────┘
                                          │ read-only (+ approve/override endpoints)
   ┌──────────────────────────────────────┴───────────────────────────────────────────┐
   │  L2 ADVISORY ORCHESTRATOR  (runtime advisory scheduler — NOT a trading agent;      │
   │  NO order authority, NO lease authority, NO live-config write)                     │
   │  • reads capability registry (enabled / tier / model-tier / trigger / budget /     │
   │    autonomy-level / output-schema)                                                 │
   │  • gates each capability on LearningTierGate.can_*()  +  Posture  +  budget        │
   │  • routes capability → PromptContract → cascade → deterministic gate → applier     │
   │  • fail-safe state machine (retry → Ollama → no-advice → trip → global Conservative)│
   └───┬───────────────┬───────────────┬───────────────┬───────────────┬───────────────┘
       │               │               │               │               │
       ▼               ▼               ▼               ▼               ▼
 ┌───────────┐  ┌────────────┐  ┌────────────────┐ ┌───────────┐ ┌────────────────────┐
 │ Local     │  │ Ollama     │  │ DETERMINISTIC  │ │ Cloud L2  │ │ Appliers (LANE-BOUND)│
 │ sentinels │  │ (L1)       │  │ MATH GATES     │ │ (L2)      │ │ • research store      │
 │ (watchdog,│  │ • input    │  │ DSR/PBO/CSCV/  │ │ ~6 core   │ │ • hypothesis registry │
 │ anomaly,  │  │   extract  │  │ leak/beta-neut/│ │ irreplace-│ │ • replay 0R (auto)    │
 │ regime,   │  │ • generate │  │ walk-forward + │ │ -able     │ │ • demo Stage1 (auto)  │
 │ liveness) │  │ • self-    │  │ out-of-bound   │ │ uses only │ │ • risk-tighten (auto, │
 │ MUST be   │  │   verify   │  │ guardrail +    │ │ math      │ │   deterministic gov)  │
 │ LOCAL     │  │ • NL render│  │ FDR α-wealth   │ │ survivors │ │ • LIVE = HUMAN ONLY   │
 └───────────┘  └────────────┘  └────────────────┘ └───────────┘ └────────────────────┘
       │               │               │               │               │
       └───────────────┴───────────────┴───────────────┴───────────────┘
                                          │
                                          ▼
   ┌────────────────────────────────────────────────────────────────────────────────┐
   │  D3 PROVENANCE & AUDIT LAYER  (FOUNDATION — built first, mandatory before any     │
   │  capability ships)                                                                │
   │  • agent.l2_calls (append-only ledger: full prompt + full input + full response + │
   │    contract_ver + schema_ver + model+ver + fact/inf/assm tags + tokens/cost/lat)  │
   │  • provenance propagation: every downstream artifact carries source='l2'+l2_reply_id│
   │  • gate-seam record: each gate logs l2_reply_id / verdict / applier / applied_as  │
   │  • fault-localization protocol (bad param → trace in seconds)                     │
   └────────────────────────────────────────────────────────────────────────────────┘
```

**The single invariant that makes this safe:** L2 produces **proposals**, never effects.
The boundary between proposal and effect is the **deterministic gate + lane-bound applier**,
not a human reading every line. Humans are the *forensic* and *live-cross* layer.

---

## A.1 The Advisory Orchestrator (decisive design choice)

**What it is:** a runtime async scheduler/dispatcher singleton (`L2AdvisoryOrchestrator`)
that owns the loop "trigger fires → check tier/posture/budget → build PromptContract →
run cascade → deterministic gate → route to lane-bound applier → emit provenance".

**What it is NOT (hard):** it is **not** a sixth trading agent (root principle 15),
**not** an order path, **not** a lease holder. It has **no import of** `IntentProcessor`,
the Rust IPC order surface, or `acquire_lease` for *trading* scope. (It MAY *read*
`GovernanceHub` capability state and *read* lease/risk projections.)

**[v4 C1] It is ALSO forbidden — in code — from raising autonomy.** Verified against the repo:
`learning_tier_gate.promote_tier(target_tier, …, approved_by=None)` (`learning_tier_gate.py:520`)
**auto-promotes L1→L4 with no `approved_by`** — only the L5 step requires it
(`learning_tier_gate.py:550-553`), and the L1→L4 path emits `AUTO_PROMOTE_*` events
(`learning_tier_gate.py:117-119, 570-574`). So a careless Orchestrator call to `promote_tier()`
**would silently raise the learning tier with no human** — a direct violation of R2-1
("expand=human, closed under autonomy itself"). v4 therefore makes the forbiddance **structural,
at the carbon layer**:
- `L2AdvisoryOrchestrator` (and every module it imports for the advisory loop) **must not import
  or call** `LearningTierGate.promote_tier`, nor any other writer that *raises* tier / removes a
  trust-gate / widens an auto-applicable lane. The §O promote-eligibility signal writes **only**
  a read-only inbox row (`learning.l2_promote_candidates`, §O.4); it **cannot** itself promote.
- The **only** path that actually promotes a tier or removes the §C.1 trust-gate is the **existing
  operator route** — the `governance_extended_routes` / TOTP-gated posture-switch pattern
  (`governance_autonomy_service.py`), reachable **solely** from a human-confirm handler.
- **New CC E2 test (grep proof):** the Orchestrator module's import + call graph contains **zero**
  references to `promote_tier` / any auto-raise-autonomy writer; the only writers that *raise*
  autonomy are reachable only from the human-confirm route. (§O.4, §L CC stress-test 15.)

**Why a new singleton (not extend Layer2Engine):** `Layer2Engine` is the *worker* for one
deep-reasoning session. The Orchestrator is the *conductor* across capabilities, triggers,
budgets, and lanes. Conflating them would push scheduling/gating/fail-safe into the session
worker and break the route-thin discipline. The Orchestrator **owns** `Layer2Engine` as one
of several executors (cloud-L2 capabilities); local-sentinel and Ollama-only capabilities
do not even touch `Layer2Engine`.

**Registration:** new mutable singleton → register in `docs/architecture/singleton-registry.md`
before merge (mandatory per CLAUDE.md §九).

---

## B. Capability config registry — schema

A capability is the atomic unit the operator enables/tunes. Stored as a **deterministic,
versioned registry** (proposed: `learning.l2_capability_registry` table + a checked-in
default TOML so the system boots with zero external state; TOML is SSOT, DB row mirrors
runtime overrides — same pattern as RiskConfig TOML > runtime).

```jsonc
// one row / one TOML stanza per capability
{
  "capability_id": "ml_advisory",              // stable key (first Tier-1 cap, v2)
  "enabled": false,                            // master off-switch (fail-closed default)
  "min_tier": "L1",                            // LearningTier required (maps to can_*())
  "tier_capability_flag": null,                // optional: bind to a TierCapabilities.can_* flag
  "model_tier": "local_sentinel|ollama|cloud_l2",
  "cloud_model_pref": "sonnet",                // only if model_tier=cloud_l2
  "trigger": {                                 // see §C / §F / §F.1
    "kind": "event|schedule|manual|threshold",
    "spec": "ml:training_complete | watchdog:circuit_broken | cron:*/15 | regime:transition",
    "debounce_secs": 900,                      // v2 change 8: coalesce window (see §F.1)
    "dedup_key": "capability_id+spec+coarse_subject"  // v2: storm control identity
  },
  "budget": {                                  // see §K (AI cost) + §O (ROI loop)
    "per_call_usd_cap": 0.50,
    "daily_usd_cap": 1.00,                     // ≤ DOC-08 $2/day global unless rule-raised
    "tier_gated_spend": true
  },
  // v2 change 12: autonomy_level is NO LONGER stored here — it is DERIVED from
  // (lane + min_tier + current Posture). See §C.2. Single source of truth.
  "lane": "research|hypothesis|replay_0r|demo_stage1|risk_tighten|ml_backlog|ops_alert|none",
  "output_schema_ref": "ml_advisory.v1",       // → §E output-schema registry
  "prompt_contract_ref": "ml_advisory.v1",
  "out_of_bound_guard_ref": "ml_advisory.guard.v1",
  "novelty_gate": true,                        // Q1: skip known-dead failure modes
  "consequential_default": false,              // Q6: retention class hint at creation
  "quality_metric_ref": "ml_advisory.metric.v1" // v2 change 6: → §O ROI/keep-promote-demote
}
```

**Hard rules baked into the registry loader (CC stress-test targets):**
- **`lane` carries a `direction` ∈ {`contract`, `expand`, `neutral`} resolved from a fixed,
  loader-owned `LANE_DIRECTION` table (v2 change 2 — the typed asymmetry invariant).** The
  derivation in §C.2 may only auto-apply lanes whose `direction=contract` or `=neutral`;
  any `direction=expand` lane is **structurally forced to operator-manual regardless of tier
  or Posture**. There is **no `lane: live` value** at all — live is unreachable from any auto
  path. This is enforced in code (the loader rejects a config that tries to auto-apply an
  `expand` lane), not in prose.
- `autonomy_level` is **derived, never declared** (v2 change 12). A config file that contains
  an `autonomy_level` key → **reject load** (catches stale v1 configs / drift).
- A capability whose `model_tier=cloud_l2` but `tier_capability_flag` resolves to `False`
  at current tier → Orchestrator **refuses to run it** (logs `tier_locked`), not "runs degraded".
- `enabled` defaults `false`; unknown fields → reject load (fail-closed, no silent drift).
- `LANE_DIRECTION` (loader-owned, the single typed truth): `risk_tighten=contract`,
  `replay_0r=neutral`, `research=neutral`, `hypothesis=neutral`, `ml_backlog=neutral`,
  `ops_alert=neutral` (alert ≠ remediation), `demo_stage1=expand`, and **any future
  `risk_loosen`/`*_promote`/live = `expand`** → forced human.
- **[v4 B2] `demo_stage1` auto-promotion has a hard `min_forward_oos_days ≥ 21` precondition,
  loader-owned and posture-independent.** Even where §C.2 STEP-3 *would* allow auto (Standard, or
  Conservative after a human-confirmed trust-gate removal), the applier **must additionally**
  prove **≥ 21 days of forward OOS** on the candidate before it may auto-promote to demo. A green
  Stage 0R replay is **in-sample historical** and is **necessary but not sufficient** — it does
  **not** satisfy the forward-OOS bar. This is a **deterministic constraint in the applier, not an
  L2 advisory input**; a candidate with `forward_oos_days < 21` → `demo_stage1` auto-promotion
  **DEFERS** (stays manual / waits), regardless of posture. (Full spec §C.3.)
- **[v4 C2] `can_auto_deploy_to_paper` is a capability-UNLOCK flag, NOT a demo posture decider.**
  Verified: `TierCapabilities.can_auto_deploy_to_paper = True` at **every** tier L1-L5
  (`learning_tier_gate.py:185/196/205/218/231`), so it carries **no** auto-vs-manual signal — it
  only says "this tier is *permitted* to touch the paper/demo lane at all." The demo auto-vs-manual
  decision is made **solely** by `LANE_DIRECTION` + §C.2 STEP-3 + the §C.3 `min_forward_oos_days`
  precondition. The Orchestrator/applier **must not** branch on `can_auto_deploy_to_paper` to
  decide auto vs manual (doing so would let Standard silently auto-apply because the flag is always
  True). The loader rejects any capability config that uses `can_auto_deploy_to_paper` as a posture
  gate.

---

## C. Autonomy-level ↔ gate routing table

This **extends the existing `_AUTONOMY_PATH_MATRIX`** (do not fork it). The matrix already
encodes Conservative(level1)/Standard(level2) × {hard-locked / protected / opt-in / fail-closed}.
L2 capabilities slot in as **new rows** with the same vocabulary.

| Lane (capability output) | `direction` | Conservative (level1) | Standard (level2) | Gate that guards the seam |
|---|---|---|---|---|
| **research / hypothesis / ml_backlog draft** | neutral | auto | auto | online-FDR α-wealth + DSR/PBO/CSCV/leak/beta-neutral/walk-forward + novelty gate |
| **strategy variant draft** | neutral | auto-draft, **no apply** | auto-draft, **no apply** | math gate cascade; produces a *proposal*, never a deploy |
| **replay Stage 0R** | neutral | auto | auto | deterministic preflight (existing Stage 0R green-replay) |
| **demo Stage 1 promotion** | **expand** | **operator manual (trust-building, §C.1)** | **auto with light gate + fail-safe**, gated by §C.3 | **[v4]** demo gate + Stage 0R green precondition + **hard `min_forward_oos_days ≥ 21` (B2, §C.3)**; auto-vs-manual decided by `LANE_DIRECTION`+STEP-3, **NOT** by `can_auto_deploy_to_paper` (C2) |
| **risk tighten / defensive** | **contract** | **auto** (survival-first) | **auto** | deterministic risk governor; hard ceiling + cooldown; L2 = advisory input only |
| **risk loosen / relax** | **expand** | **operator manual** | **operator manual** | never auto (typed `expand` → forced human) |
| **ops alert (sentinel)** | neutral | **auto** (local) | **auto** (local) | local sentinel; alert ≠ remediation |
| **ops remediation / restart** | **expand** | **human / runbook** | **human / runbook** | L2 may *draft* a runbook step; never *executes* it |
| **LIVE crossing** | **expand** | **HUMAN: 5 gates + Decision Lease** | **HUMAN: 5 gates + Decision Lease** | the auto-loop **cannot reach** this row; structurally human-only |

### C.1 Resolution of the v1 contradiction (v2 change 10 — option (b), explicit)

v1 simultaneously said "the human exits inline" *and* "demo Stage 1 = operator manual under
Conservative." That is a real contradiction. **Resolved as option (b):** the demo-promotion
human gate under Conservative is **deliberate and temporary** — it is a **trust-building
stage**, not a permanent inline reviewer. The reconciliation with "the human's limits must
not become the bottleneck":

- **Conservative (low tier / fresh capability):** the human approves demo promotion. This is
  the *only* place a human is inline in the auto-research loop, and it exists **to build
  operator trust in a new capability before it earns the right to self-promote to demo.**
- **Standard / higher tier (capability has a proven track record per §O quality metric):** the
  demo-promotion gate **becomes removable** — once the §O **correctness/value** signal is
  sustained-HIGH (and ≥ sample floor), the system emits a **one-click promote-eligible candidate**
  and **a human confirms** the gate's removal; thereafter promotion runs on
  `can_auto_deploy_to_paper` + the light gate + Stage 0R-green precondition and the human is **out**
  of that capability's demo loop. **v3 (R2-1): the metric does not remove the gate by itself —
  removing a trust-gate is an autonomy *expansion*, which is human-confirmed (§O.1). The metric's
  job is to make that confirmation a single click, not to skip it.**
- **Invariant preserved:** the human is *never* inline for `direction=neutral` lanes (research
  / hypothesis / ml_backlog / replay) at any tier, and *always* required for `direction=expand`
  to **live**. The human's only inline role narrows to: (a) demo-promotion **while a capability
  is junior** (removable — but the *act of removing it* is itself a human-confirmed expansion,
  R2-1), and (b) live-crossing **forever** (structural).

This makes the system consistent with the operator's vision: *automatic research → demo*, with
the human as a **bounded trust gate that the system grows out of** — but **growing out of it is a
human-confirmed step**, plus the permanent live + forensic role. The human is a bottleneck **only
by deliberate choice at the junior stage**; the §O quality metric makes **shedding** that stage a
near-zero-effort **one-click human confirmation** (R2-1/§O.1), not an automatic metric action and
not something a human must remember to do. The asymmetry is exact: **the system may
auto-*contract* autonomy (demote), but every autonomy *expansion* — this trust-gate removal
included — is human-confirmed.**

### C.2 Derived autonomy (v2 change 12 — single source of truth, fewer knobs)

v1 stored `capability.autonomy_level` and combined it with lane × Posture × tier via a
`max_strictness` rule = 4 knobs + a combination rule. v2 **derives** the effective autonomy
from **3 inputs the system already owns**, so there is exactly one truth source and the
registry stores **no autonomy knob at all**:

```
effective_autonomy(capability) = derive(lane.direction, min_tier vs current_tier, Posture)

  STEP 1 — direction gate (typed, loader-owned, non-overridable):
    if lane.direction == "expand":            return MANUAL          # never auto. full stop.
    # contract / neutral may proceed to step 2

  STEP 2 — tier gate:
    if current_tier < capability.min_tier
       OR (tier_capability_flag set AND flag==False):
                                              return TIER_LOCKED      # refuse, don't degrade

  STEP 3 — posture modulation (can only ADD friction, never remove the deterministic gate):
    if Posture == Conservative AND lane is a promotion-class lane (e.g. demo_stage1):
                                              return MANUAL           # §C.1 trust-building
    else:                                     return AUTO_VIA_GATE    # runs through the
                                                                      # deterministic gate/applier
    # [v4 C2] STEP 3 NEVER reads can_auto_deploy_to_paper (always True @all tiers → no signal).
    # [v4 B2] AUTO_VIA_GATE for demo_stage1 still has to clear the §C.3 forward-OOS precondition
    #         inside the applier; AUTO_VIA_GATE means "eligible to attempt", not "promote now".
```

**Why this is strictly simpler *and* safer than v1:** (1) the `expand`→MANUAL rule is checked
**first and is structural** — no Posture or tier can ever unlock it, so the "no auto-path to
live" property is a one-line invariant CC verifies, not an emergent property of a strictness
lattice. (2) There is **no `autonomy_level` field to misconfigure** — the most dangerous knob
in v1 is deleted. (3) Posture's only job shrinks to "add friction to promotion-class lanes
under Conservative," which is exactly the §C.1 trust gate. The `max_strictness` lattice is gone.

**Asymmetry principle, now a typed invariant (was prose in v1):** *`direction=contract` and
`direction=neutral` may be auto; `direction=expand` is human — enforced by the loader's
`LANE_DIRECTION` table + STEP 1, not by documentation.* This is the single typed rule that
makes "mostly automatic" safe under root principle 5 (survival > profit), and it is the load-
bearing thing CC stress-tests (§L).

**v3 (R2-1) — the asymmetry now also governs autonomy *itself*, not just lanes.** The derivation
above decides, per capability, whether a *capability's lane* runs auto or manual. But there is a
*second* kind of expansion: **changing the rules so that more becomes automatic** — e.g. removing
the §C.1 demo-promotion trust-gate so that capability self-promotes to demo. v2 let the §O metric
do that automatically; that is an `expand` action and so, by the **same** universal rule, **must be
human**. v3 therefore states the invariant at two levels:
- **First-order (this derivation):** a capability's `expand` lane is human (typed, STEP 1).
- **Second-order (autonomy promotion):** *raising* a capability's effective autonomy — removing a
  trust-gate, widening an auto-applicable lane, promoting a tier-gate — is **itself** an `expand`
  and is **human-confirmed** (§O.1). The §O metric may only **propose** it (one-click candidate);
  it may **auto-apply autonomy changes only in the contract/demote direction.**

So "expand=human" is now **closed under autonomy changes**: the system can never bootstrap itself
into doing *more* automatically. The only automatic movement of the autonomy frontier is *inward*.
This is the v3 strengthening CC must verify (§L stress-test 5/10).

### C.3 [v4 B2] Forward-OOS precondition for auto demo-promotion (deterministic, posture-independent)

**QC BLOCKER B2.** The demo-promotion lane is `direction=expand`, so it is human-confirmed under
Conservative (§C.1) and — once a human has confirmed the trust-gate removal (§O.1) — may run auto
under Standard. **But "auto" must never mean "promote on in-sample evidence alone."** Stage 0R is a
**historical in-sample replay**: it is a **necessary** preflight (a candidate that fails Stage 0R is
killed) but it is **not sufficient** for a demo promotion — it proves nothing about *forward* /
out-of-sample behavior, and the whole project's recurring failure (6 weeks, 5 candidates) is
candidates that looked fine in-sample and died forward on cost / beta. v4 therefore adds a
**deterministic, applier-owned, posture-independent** precondition on the *act of auto-promoting to
demo*:

```
auto_promote_to_demo(candidate) is permitted ONLY IF:
   stage0r_green(candidate) == True                     # necessary preflight (in-sample)
   AND candidate.forward_oos_days >= MIN_FORWARD_OOS_DAYS    # MIN_FORWARD_OOS_DAYS = 21 (default)
   AND <the §G.2 math gate verdict == PASS, not DEFER>  # Q1 sample precondition, §G.2
   # else → DEFER (stay manual / wait; never auto-promote on in-sample evidence)
```

- **`MIN_FORWARD_OOS_DAYS = 21`** (PA default; tunable by QC). "Forward OOS days" = wall-clock days
  of **genuinely out-of-sample, point-in-time** evaluation accrued **after** the candidate's spec
  was frozen (pre-registration timestamp, §G.1) — *not* replayed history. A candidate with
  `forward_oos_days < 21` cannot be auto-promoted **under any posture**; it stays in the manual
  trust-gate or waits.
- This is a **constraint in the deterministic applier**, **not** an L2 advisory and **not** subject
  to the §O metric. The §O metric can shed the *human* trust-gate (R2-1, human-confirmed); it can
  **never** shed this forward-OOS bar — that bar is unconditional.
- **Interaction with §C.1/§O.1:** the human-confirmed trust-gate removal (R2-1) changes *who*
  approves (human → automatic); the §C.3 bar changes *what evidence is required* (must include ≥21d
  forward OOS) and is **invariant across that change**. So even a fully "trusted, auto" capability
  cannot demo-promote a candidate that has not lived ≥21 forward-OOS days.
- **CC/QC stress-test:** no code path auto-promotes to demo with `forward_oos_days < 21` or with a
  §G.2 verdict of DEFER; the bar is read inside the applier, not from any L2 field. (§L QC.)

This is the second of the two deterministic "alpha command-line" constraints (the first is the
§N.1 `beta_neutral_check`): **B1 stops a beta-masquerade from looking like alpha; B2 stops
in-sample evidence from looking like forward alpha.** Together they harden the exact two ways the
5 dead candidates would have slipped an unattended gate.

---

## D. D3 Provenance & Audit Layer (the foundation — build #1)

### D.1 Ledger: `agent.l2_calls` (new, V134) — EXTENDS the `agent.ai_invocations` discipline

Reuse the `bybit_ai_invocation_ledger` patterns (sha256 of text, deterministic event ts,
idempotency key, the `agent` schema). New table because L2 needs richer, advisory-specific
columns the existing `ai_invocations` lineage table was not shaped for. Append-only.

```
agent.l2_calls (
  l2_reply_id        text PRIMARY KEY,     -- "l2r:<uuid12>" — the universal lineage handle
  session_id         text,                 -- groups multi-call sessions (Layer2Session.session_id)
  capability_id      text NOT NULL,        -- which capability produced this
  trigger            text NOT NULL,        -- event|schedule|manual|threshold + spec
  created_at         timestamptz NOT NULL,
  model              text NOT NULL,         -- provider/model-id
  model_version      text,
  contract_ver       text NOT NULL,         -- PromptContract version (§E)
  schema_ver         text NOT NULL,         -- output-schema version (§E)
  system_prompt      text NOT NULL,         -- FULL deterministic prompt as sent
  input_context      jsonb NOT NULL,        -- FULL structured input + offered tool defs
  raw_response       text NOT NULL,         -- FULL raw model output (pre-parse)
  parsed_output      jsonb,                 -- schema-validated structured output (null if rejected)
  guard_verdict      text,                  -- out-of-bound guard result (pass|clamp|reject)
  fact_inf_assm      jsonb,                 -- {facts:[], inferences:[], assumptions:[]} tags
  input_tokens       int, output_tokens int,
  cost_usd           numeric, latency_ms int,
  prompt_sha256      text, response_sha256 text,  -- integrity / dedup (reuse ledger helper)
  -- retention class (§Q6): set AT CREATION
  consequential      boolean NOT NULL DEFAULT false
)
-- append-only: no UPDATE/DELETE grant for app role; Guard A/B/C per CLAUDE.md migration rules.
-- hypertable on created_at (TimescaleDB) so non-consequential rows can drop_chunks (§Q6).
```

**Why store the FULL prompt + FULL response (not a hash/summary):** root principle 8
(every decision reconstructable) + the operator's fault-localization requirement. A hash
proves integrity but cannot answer "what exactly did the model see and say?" during a
post-mortem. Storage cost is bounded by retention (§Q6: non-consequential → TTL + native
compression). **MIT/QC stress-test target: is full-text retention affordable at projected
call volume? (see §L).**

### D.1.1 [v4 E2] Sanitize-before-persist (secret-leak guard — E3 HIGH)

**E3 HIGH E2.** The whole point of D3 is to store the **full** `system_prompt` / `input_context` /
`raw_response` / any `final_summary` — but that is exactly the surface where a secret can leak into
a durable, append-only, hard-to-purge store. A captured `str(e)` from an exception, a raw error
string echoing a connection URL, an API token that drifted into a context block, or a stack trace
with a path/credential **must never enter the ledger**. v4 mandates a **deterministic sanitize pass
that runs *before* the append-only `agent.l2_calls` write** (and before any `final_summary`
persistence):

- **No raw exception text.** `str(e)` / raw error strings / stack traces are **never** stored
  verbatim. If a call fails, the ledger stores a **classified error code + a sanitized reason**, not
  the raw exception. (Mirrors the project's existing "never log tokens / prompts-with-secrets"
  rule, CLAUDE §十一 / E3 review.)
- **Secret-pattern redaction.** A deterministic redactor scrubs known secret shapes (API keys,
  bearer tokens, `authorization.json` contents, secret-slot material, DB DSNs/passwords, private
  URLs) from **all four** large text columns before write, replacing them with a stable
  `[REDACTED:<kind>]` token so the row is still forensically useful but carries no live secret.
- **Provenance-safe.** Redaction is applied to the **stored** copy only and is **idempotent +
  logged** (which redactor version ran), so D3 remains reconstructable (you know a redaction
  happened and of what kind) without the secret itself. The `prompt_sha256` / `response_sha256` are
  computed **over the sanitized text actually stored** (so the hash matches the row).
- **Applies everywhere full text is persisted:** the §D.1 ledger, the §N `nl_summary` /
  `final_summary` if persisted, and the §O quality evidence digest. **No code path may write an
  unsanitized large-text field to any durable store.**
- **E3 stress-test:** inject a prompt/response/error carrying a synthetic secret; confirm the
  stored row contains `[REDACTED:*]` and never the secret, and that the sanitize pass is on the
  **write path** (not a post-hoc cleanup that leaves a window). (§L E3.)

### D.2 Provenance propagation — the FULL lineage chain (v2 change 7)

v1 attached `l2_reply_id` to the *immediate* downstream artifact (a hypothesis row). v2
requires the **complete chain**, so a live problem months later traces all the way back to the
originating reply — not just to the hypothesis, but through strategy → demo → live:

```
agent.l2_calls.l2_reply_id   (the universal lineage handle, D.1)
        │  carried as source_l2_reply_id
        ▼
research.hypotheses           (hid, source_l2_reply_id)            ← step 1
        │  carried as origin_hid + propagated source_l2_reply_id
        ▼
strategy variant / config draft (variant_id, origin_hid, source_l2_reply_id)   ← step 2
        │  carried into the replay/demo manifest
        ▼
replay.experiments / demo Stage1 manifest (run_id, variant_id, source_l2_reply_id)  ← step 3
        │  carried into the demo-fills attribution + (if promoted) the live decision record
        ▼
demo fills / decision_outcomes (… source_l2_reply_id on the originating decision)   ← step 4
        │  ONLY if a human later crosses to live via the 5-gate flow
        ▼
live decision record + LIVE FILLS / live decision_outcomes                          ← step 5
        (Decision-Lease audit row AND the resulting live fills/outcome rows
         all carry the propagated source_l2_reply_id)            ← v3 R2-5: post-cross
```

**v3 (R2-5) — the chain reaches *live trades*, not just the live decision record.** v2 stopped at
the Decision-Lease audit row (step 5 = the *decision*). The operator's deepest forensic need is to
take a **live loss months later** — i.e. a **live fill / live `decision_outcomes` row** — and trace
it to the originating L2 reply. So **post-cross, the propagated `source_l2_reply_id` is carried not
only onto the live Decision-Lease audit row but onto the live *fills* and live *decision_outcomes*
rows that result** (same propagate-unchanged discipline as every other hop). Concretely: when a
human crosses a candidate to live via the unchanged 5-gate + Decision-Lease flow, the lease carries
the candidate's `source_l2_reply_id`; the engine, when it records the resulting live fills /
outcomes, copies that root id forward (an additive provenance column, never re-derived). Then
`SELECT source_l2_reply_id FROM <live fill or live decision_outcome> → join agent.l2_calls` answers
"which L2 reply ultimately spawned this live trade?" — the months-later live-forensic the operator
cares most about. **This is read/audit provenance only — it adds no live authority and no new live
path; live crossing remains the unchanged human + 5-gate + Decision-Lease flow.** (Whether the live
fills/outcomes table can take the additive column is a §L needs-verification item — additive col on
a possibly-hash-chained table.)

Concretely, every link adds **two** columns (or a provenance jsonb): the **immediate parent
id** (`origin_hid`, `variant_id`, `run_id`) **and** the **root** `source_l2_reply_id` that is
copied forward unchanged at every hop. The root never gets rewritten, so any artifact in the
chain answers "which L2 reply ultimately spawned this?" in one column, and the parent ids let
you walk the chain step by step.

- hypothesis rows (research) → `source_l2_reply_id`
- strategy variant / config draft → `origin_hid` + propagated `source_l2_reply_id`
- residual / replay manifests → already hash-chained (V131/V132); add `source_l2_reply_id`
  provenance col (propagated, not re-derived)
- demo Stage 1 promotion manifest + the demo decision/outcome rows → propagated `source_l2_reply_id`
- (live, rare) **post-cross (v3 R2-5):** the Decision-Lease audit row **and the resulting live
  fills / live `decision_outcomes` rows** of any human-crossed live decision → propagated
  `source_l2_reply_id` (this is what makes a months-later **live trade** traceable to one reply —
  audit-only, no new live authority)
- `agent.lessons` rows distilled from an L2 insight → `l2_reply_id` (V133 has `context_id`; map it)

**Forensic payoff:** `SELECT source_l2_reply_id FROM <any artifact in the chain>` → join to
`agent.l2_calls` → the exact prompt + response that started it, months back. The chain is what
upgrades D3 from "audit a single call" to "trace a live consequence to its cognitive origin."

Rule: **no artifact enters a gate without provenance.** A gate receiving an artifact lacking
`source` treats it as **non-L2** (human/deterministic origin) — which is correct and is itself
the first step of fault localization. **MIT/QC stress-test: confirm the root id is propagated
unchanged at every hop (no rewrite, no loss across the V131/V132 hash-chained manifests).**

### D.3 Gate-seam record

Every deterministic gate logs, per artifact: `l2_reply_id`, `gate_id`, `verdict`
(pass/clamp/reject), `applier`, `applied_as` (what concretely changed, or "proposal only").
Proposed: `learning.l2_gate_seam_log` (append-only). This is what lets a human answer "which
gate let this through?" in one query.

### D.4 Fault-localization protocol (the operator-facing payoff)

Bad parameter / surprising behavior observed → run the protocol:
1. Does the artifact carry `source='l2'`? **No** → not L2-originated; investigate
   deterministic/human path. (Cuts the search space immediately.)
2. **Yes** → `SELECT * FROM agent.l2_calls WHERE l2_reply_id = ?` → full prompt + full
   response + tags + contract/schema version in one row → second-level localization.
3. `SELECT * FROM learning.l2_gate_seam_log WHERE l2_reply_id = ?` → which gate passed it,
   what it was applied as, by which applier → "how did a proposal become an effect?".
4. Replay: re-run the same `contract_ver` + `input_context` deterministically → reproduce.

**This protocol is why prompts must be deterministic templates (§E): a model-generated prompt
is not reproducible and breaks step 4.** (CC/MIT stress-test: is replay bit-reproducible given
model nondeterminism? At minimum the *prompt+input* must be; the *response* is archived verbatim.)

---

## E. PromptContract + output-schema (the I/O contract)

### E.1 Principle

**Both** input and output are schema'd. The prompt is a **deterministic, versioned template**
— **Ollama is forbidden from generating prompts** (it would stack hallucination, destroy D3
attribution, and break replay). Ollama is allowed in exactly two seams:
1. **Input extraction**: unstructured (news / logs) → structured fields that fill the template.
   (Reuses `ContextDistiller`.)
2. **Output NL rendering**: structured output → human prose, **on human trigger only** (§4 vision).

A `PromptContract` (versioned) declares: `role`, `task`, **echoed output-schema**,
`constraints` (advisory-not-decision + governance + fact/inference/assumption discipline),
`few_shot`, `uncertainty_rule`. Plus a **structured-label context** block (the only place
free text enters, and it is pre-extracted, not model-authored).

The **out-of-bound guard** is deterministic and runs **before** a proposal is formed — it
catches hallucinated parameters (e.g. leverage 50x, size 80%, negative cost) **without human
eyes**. Guard verdict ∈ {pass, clamp, reject} is logged to D3.

`contract_ver` + `schema_ver` are written into every `agent.l2_calls` row.

### E.2 Worked examples (illustrative, not exhaustive)

**(0) `ml_advisory.v1`** — **the operator-chosen first Tier-1 capability (v2)** — attaches to
the **existing ML pipeline** (`run_training_pipeline.py` / `mlde_shadow_advisor.py` /
`leakage_check.py`; V031 view → `learning.mlde_shadow_recommendations`). Three sub-modes, all
advisory, all `direction=neutral` (so auto-runnable through the deterministic gate; **never an
execution path** — it feeds the SAME `applied=false`/`requires_governance=true` surface the
shadow advisor already uses). Cascade: Ollama screen → deterministic math/leak gate → cloud-L2
interpretation on survivors only.
```jsonc
PromptContract:
  role: "You are an ML RESEARCH ADVISOR for the OpenClaw learning pipeline. You PROPOSE
         feature hypotheses, DIAGNOSE leakage/drift, and INTERPRET training results. You never
         retrain, never deploy, never write to a live model. Every output is a backlog item or
         a diagnosis routed to the existing requires_governance advisory surface."
  task: "Given {recent training run metrics + feature-importance table + leakage_check output +
         drift signals}, do EXACTLY ONE of: (a) propose pre-registerable feature hypotheses for
         the backlog, each with an economic mechanism and a falsification test; (b) diagnose the
         most likely leakage/drift cause and cite the evidence; (c) interpret what the training
         result implies, separating signal from regime artifact."
  constraints: ["advisory only — output is a backlog item / diagnosis, never a retrain trigger",
                "every feature hypothesis MUST state an economic mechanism (no pure curve-fit)",
                "do NOT propose features matching the dead-failure-mode list (novelty gate)",
                "leak/drift claims MUST cite the specific evidence AND tag its source_ref CLASS
                 (name_pattern_check | shift1_compliance | is_oos_gap) — see [v4 M3] below;
                 a name_pattern_check pass is NOT a leak-free / PIT proof",
                "label fact|inference|assumption; a mechanism is an inference/assumption, say so",
                "if metrics are bull-only / rally-dominated, label result 'regime-bet/learning-only'
                 per Alpha Evidence Governance — do NOT call it promotion proof"]
  context (structured, extracted from the pipeline, NOT model-authored):
        {mode:"hypothesize|diagnose_leak|interpret_result",
         training_run_id, metrics{auc, sharpe, pbo, dsr, cost_edge_ratio},
         feature_importance[], leakage_check_findings[], drift_signals[],
         available_signal_axes[], dead_failure_modes[] (agent.lessons / novelty),
         regime_label, alpha_wealth_remaining}
output-schema (ml_advisory.v1):
  { mode: "hypothesize|diagnose_leak|interpret_result",
    feature_hypotheses: [{ hid, statement, mechanism, falsification_test,
                           signal_axes_used:[str], expected_direction, beta_neutralization_plan }],
    leak_drift_diagnosis: { suspected_cause:str,
                            evidence:[{claim, kind:"fact|inference|assumption",
                                       source_ref:str,
                                       source_class:"name_pattern_check|shift1_compliance|is_oos_gap"}],
                            recommended_check:str } | null,   // [v4 M3] source_class mandatory
    result_interpretation: { reading:str, regime_caveat:str, confidence:float } | null,
    backlog_items: [{ item:str, priority:"low|med|high", rationale:str }] }
out_of_bound_guard:
  reject any feature_hypothesis whose signal_axes_used ⊄ available_signal_axes (no inventing data);
  reject if mechanism empty (curve-fit guard);
  dedupe feature_hypotheses against dead_failure_modes by similarity (novelty);
  reject a result_interpretation that asserts promotion-readiness without a regime_caveat when
    metrics are flagged bull-only (defense-in-depth vs Alpha Evidence Governance)
```
**Why this first (operator's choice over incident-diagnosis):** it lands on an **already-
advisory, already-`requires_governance`** surface (lowest possible blast — the ML pipeline is
*designed* not to be an execution path), exercises the **full cascade** (Ollama generate →
math/leak gate → cloud interpret) that the research loop will later reuse, and directly serves
the project's core deficit (upstream alpha discovery) without needing the online-FDR controller
to exist yet. The math gate (DSR/PBO/leak) is the **only** validator — the ML advisor never
validates its own hypotheses. incident-diagnosis remains valuable but is demoted to a parallel
cheap local fix (§J), not the first L2 capability.

**[v4 M3] `leakage_check.py` is a name-pattern check, NOT a leak-free / PIT proof.** Verified
against the repo: `program_code/ml_training/leakage_check.py` (78 lines) checks **only feature-name
substrings/prefixes** — it lower-cases each feature name and matches a forbidden-pattern list +
an allowed-prefix list (`leakage_check.py:57-68`). It **cannot** detect: (a) a **missing
`shift(1)`** look-ahead (using a bar's own close to predict that bar — the exact `rolling(N).max()`
look-ahead bias the project has been burned by, memory `feedback_indicator_lookahead_bias`),
(b) **resample-boundary leak** (a feature that peeks across a resample edge), or (c) **cross-section
leak** (universe-relative features computed with contemporaneous cross-sectional info). Therefore:
- `ml_advisory` **may NOT claim `leakage_check` output as leak-free PIT evidence.** A
  `leakage_check` pass is at most a `name_pattern_check` — a weak, necessary-not-sufficient screen.
- Every leak/PIT claim's `source_ref` must be **typed** `source_class ∈ {name_pattern_check,
  shift1_compliance, is_oos_gap}` (schema above). A promotion-relevant "leak-free" assertion
  requires `shift1_compliance` (the feature pipeline provably uses only information available at or
  before the decision bar) and/or `is_oos_gap` (a real in-sample → out-of-sample temporal gap),
  **not** a `name_pattern_check`. The out-of-bound guard (§E(0) guard) and the §G.2 math gate both
  enforce this typing — a leak claim backed **only** by `name_pattern_check` cannot satisfy the
  leak-free precondition of the math gate.
- This does **not** remove `leakage_check` (it is a cheap useful first screen); it **caps its
  evidentiary weight** and forbids over-claiming. MIT/QC own whether `shift1_compliance` /
  `is_oos_gap` checks already exist elsewhere or must be built (§L).

**(i) `incident_diagnosis.v1`** (cloud-L2, Tier-1)
```jsonc
PromptContract:
  role: "You are an OPS DIAGNOSTICIAN for the OpenClaw trading system. You DIAGNOSE; you
         never execute remediation. Your output is a proposed runbook, not an action."
  task: "Given the incident signal + recent logs + system state, identify the most likely
         root cause and propose ordered, REVERSIBLE diagnostic/remediation steps."
  constraints: ["advisory only — no step is auto-executed",
                "label each claim fact|inference|assumption",
                "if confidence < 0.5, say 'insufficient evidence' and propose what to gather"]
  context (structured, Ollama-extracted from logs): {incident_kind, since_ts, last_failure_reason,
                engine_state, recent_canary_events[], snapshot_age_secs}
output-schema (incident_diagnosis.v1):
  { root_cause_hypothesis: str,
    confidence: float[0..1],
    evidence: [{claim:str, kind:"fact|inference|assumption", source_ref:str}],
    proposed_steps: [{step:str, reversible:bool, blast_radius:"none|low|med", rationale:str}],
    escalation_required: bool }
out_of_bound_guard: reject if any step.reversible=false AND blast_radius!="none"
                    (a non-reversible high-blast step may never be auto-anything; human-only)
```

**(ii) `regime_risk_advisory.v1`** (cloud-L2 or Ollama, Tier-1; feeds risk-tighten lane)
```jsonc
PromptContract:
  role: "You are a REGIME RISK ADVISOR. You advise the deterministic risk governor; you do
         not set risk parameters. Tightening may be applied automatically; loosening never."
  task: "Given leak-free PIT regime features + portfolio exposure, assess whether the system
         should DEFENSIVELY tighten, and by how much (bounded)."
  constraints: ["you may only recommend tighten or hold — never loosen",
                "recommendation is an INPUT to a deterministic governor with hard ceilings",
                "label fact|inference|assumption; cite the PIT features used"]
  context (structured): {regime_label, regime_confidence, realized_vol_pctile, portfolio_beta,
                gross_exposure_pct, corr_cluster_max, drawdown_pctile}
output-schema (regime_risk_advisory.v1):
  { stance: "tighten|hold",
    suggested_exposure_cap_pct: float|null,    // governor clamps to its own hard ceiling
    suggested_cooldown_minutes: int|null,
    rationale: str, confidence: float,
    evidence: [{claim, kind, source_ref}] }
out_of_bound_guard: clamp suggested_exposure_cap_pct to [governor_floor, current];
                    reject stance="loosen" (schema disallows; defense-in-depth);
                    deterministic governor applies the FINAL bounded value, not the model's number
```
Note: per root principle 4/5 the **deterministic risk governor owns the final number**;
the model's value is advisory and always clamped. Auto-apply is allowed **only because it can
only tighten and is bounded + cooled** (asymmetry rule, §C).

**[v4 B1] `portfolio_beta` and any residual-beta input fed here is the DETERMINISTIC value from
§N.1, never an L2-estimated beta.** The regime-risk advisor *reads* a deterministically-computed
beta (§N.1 factor model, ≥90d window); it never estimates or asserts beta itself. The same
deterministic `beta_neutral_check` (§N.1) is the binding alpha gate in §G.2 and the §N packet —
all three consume the **one** deterministic computation, so a capability can never substitute its
own looser beta.

**(iii) `hypothesis_generation.v1`** (cloud-L2, Tier-3+, research loop)
```jsonc
PromptContract:
  role: "You are an ALPHA HYPOTHESIS GENERATOR. You PROPOSE testable, pre-registerable
         hypotheses with a stated economic mechanism. You do not validate them — the
         deterministic math gate is the only validator."
  task: "Given the failure-mode memory + recent non-OHLCV signal axes, propose N novel,
         pre-registerable hypotheses, each with a mechanism and a falsification test."
  constraints: ["each hypothesis MUST state an economic mechanism (no pure curve-fit)",
                "do NOT propose anything matching the provided dead-failure-mode list (novelty)",
                "label fact|inference|assumption; mechanism is an inference/assumption, say so"]
  context (structured): {available_signal_axes[], dead_failure_modes[] (from agent.lessons /
                novelty gate), recent_regime, alpha_wealth_remaining}
output-schema (hypothesis_generation.v1):
  { hypotheses: [{ hid:str, statement:str, mechanism:str, falsification_test:str,
                   signal_axes_used:[str], expected_direction:"long|short|neutral",
                   beta_neutralization_plan:str }] }
out_of_bound_guard: reject any hypothesis whose signal_axes_used ⊄ available_signal_axes
                    (no inventing data we don't have); reject if mechanism empty
                    (curve-fit guard); dedupe against dead_failure_modes by similarity
```

**QC stress-test target:** are these schemas tight enough that a hallucinated/over-confident
LLM output is *structurally* caught by the guard rather than relying on the downstream math
gate as the only net? (Defense-in-depth: guard catches *form*, math gate catches *substance*.)

---

## F. Fail-safe state machine

L2 failure must **always** degrade to the deterministic baseline — **never block, never
unsafe** (the iron rule). Reuses the layered-autonomy Conservative/Standard +
notification-failsafe + cooling precedent (`governance_autonomy_service`, V114).

```
            ┌─────────┐   call ok
            │ HEALTHY │◄───────────────────────────────┐
            └────┬────┘                                 │
        call fails│                                     │ N consecutive ok
                  ▼                                      │
            ┌─────────┐  retry (bounded, jittered)       │
            │ RETRY   │──────────────────────────────────┘
            └────┬────┘ retries exhausted
                  ▼
            ┌──────────────┐  cloud L2 down / over-budget
            │ DEGRADE_OLLAMA│  (capability runs on local Ollama if its model_tier allows;
            └────┬─────────┘   cloud-only capabilities skip to NO_ADVICE)
                  ▼  Ollama also unavailable / not permitted
            ┌──────────────┐  *** system runs on DETERMINISTIC BASELINE; advice = none ***
            │ NO_ADVICE     │  (NEVER blocks; trading/risk run on existing deterministic paths)
            └────┬─────────┘  repeated failure / guard storm
                  ▼
            ┌──────────────┐  circuit trips per capability; cooling timer starts
            │ TRIPPED       │  (capability disabled; emits alert via §J sentinel wire)
            └────┬─────────┘  systemic (many capabilities tripping / health degraded)
                  ▼
            ┌────────────────────┐  global posture forced → Conservative
            │ GLOBAL_CONSERVATIVE │  (reuse autonomy switch path; + notify→1h→Defensive
            └────────────────────┘   + 7d cooling, per layered-autonomy / V114)
```

Plus the deterministic **out-of-bound guard** runs at every proposal regardless of state.

### F.1 Trigger debounce / dedup / coalesce (v2 change 8 — storm control)

v1 had only a per-call cooldown. Auto-triggers (regime transition, anomaly, ml:training_complete)
can fire in bursts → cost + noise. The Orchestrator owns a **deterministic admission stage**
*before* any model call, with three layers (all in code, all per-capability-configurable via the
`trigger.debounce_secs` / `dedup_key` fields in §B):

1. **Dedup (identity collapse):** compute `dedup_key = capability_id + spec + coarse_subject`
   (e.g. regime transition on the same symbol-pair within the window collapses to one). A trigger
   whose `dedup_key` matches an in-flight or recently-served key in the window is **dropped**
   (logged `trigger_deduped`, no model call). This is exact-match suppression, mirroring the
   watchdog `emit_restart_skipped_if_new` precedent (PA memory 2026-06-05).
2. **Debounce (settle window):** for bursty signals, **wait `debounce_secs` for the burst to
   settle**, then fire **once** on the latest state (trailing-edge debounce). A regime flapping
   3×/min fires one advisory after it settles, not three.
3. **Coalesce (batch):** multiple distinct-but-related triggers in the window (e.g. anomaly on 5
   symbols) **coalesce into one call** with a batched context block, when the PromptContract
   supports a list input. One reasoning call, one cost, one provenance row covering the batch.

**Admission order:** dedup → debounce → coalesce → budget check (§K) → tier/posture (§C.2) →
model call. Anything dropped/coalesced is logged with a `trigger_decision` reason so the §O
metric can see suppressed volume (a capability that triggers a lot but is mostly deduped is a
demote candidate). **Per-capability daily call ceiling** (hard) is the final backstop: once a
capability hits its daily cap, further triggers degrade to `NO_ADVICE` for that capability
(never blocks anything; just stops spending). E5/AI-E stress-test: confirm a storm cannot blow
the DOC-08 $2/day envelope even with debounce off.

### F.2 Conflict resolution (v2 change 9 — deterministic adjudication)

Two conflict classes; both resolve **toward the deterministic / more-conservative side** (root
principles 4, 6), never by a model arbitrating:

**(a) L2 advisory vs deterministic governor (the load-bearing case).** The deterministic
governor / gate is **always authoritative**; the L2 value is advisory and clamped. Specifically:
- risk-tighten: the governor applies the **stricter** of {its own deterministic computation,
  the L2 suggestion clamped to [floor, current]}. If L2 says tighten less than the governor's own
  rule, the **governor's stricter number wins**. L2 can only ever *pull tighter*, never *relax*.
- any gate (DSR/PBO/leak/FDR): a gate `reject` **always** beats an L2 `recommend`. The model
  never overrides a failed quantitative gate (Alpha Evidence Governance is explicit on this).
- This is not a "tie-break" — it is a **strict precedence**: `deterministic > advisory`, encoded
  as the gate/governor consuming the advisory as a *bounded input*, never as a command.

**(b) Cross-capability conflict (two L2 capabilities disagree).** Resolved by a fixed precedence,
no model adjudication:
1. **Direction precedence:** a `contract` (tighten/defensive) recommendation **always wins over**
   an `expand` (loosen/promote) recommendation on the same target. Survival-first: when ML-advisor
   says "promote variant X" but regime-risk-advisor says "tighten / defensive now," the
   **tighten wins and the promotion is deferred** (logged, surfaced; the promotion is not killed,
   just queued behind the all-clear).
2. **Same-direction conflict** (two tighten suggestions of different magnitude on the same param):
   take the **stricter** (more conservative) value (root principle 6).
3. **Orthogonal targets** (different params / different lanes): no conflict — both proceed through
   their own gates independently.
4. **Unresolvable / novel conflict** the precedence table doesn't cover → **NO auto-apply**,
   escalate to the human inbox (§N packet) with both recommendations + provenance. Fail-closed.

Every conflict adjudication is logged to the gate-seam log (§D.3) with the losing recommendation
+ reason, so forensics (§D.4) and the §M feedback pipeline can later turn a recurring bad
adjudication into a new deterministic rule. CC stress-test: confirm there is **no code path**
where a model output adjudicates between two proposals — adjudication is always table-driven.

**Human interventions** (orthogonal to the machine, always available): approve / reject /
modify (Decision-Lease for live-cross), override / pause / kill, escalation, feedback →
failure library + per-capability quality metrics, manual trigger.

**Invariant (CC/E3 stress-test):** there is **no path** from any fail-safe state to "block
the trading/risk deterministic baseline" or "auto-apply to live". The worst case is
NO_ADVICE = the system behaves exactly as it does today without L2.

---

## G. Q1 / Q3 / Q6 landing

### G.1 Q1 — high-throughput × statistically honest research (research plane, deterministic)

New deterministic Python module (research plane, **resource-isolated from live**, §K2):
- **online-FDR α-wealth controller** (LORD / SAFFRON): an α-wealth budget for an *infinite*
  sequence of tests; a confirmed discovery refunds wealth (self-throttling). **GREENFIELD.**
  New singleton `ResearchAlphaWealthController` → register in singleton SSOT.
- **N_eff cluster deflation** (López de Prado): correlated variants grouped so the bar is not
  inflated by near-duplicates. (Repo already has `dsr_gate` / `pbo_gate` vetted helpers per
  memory `project_2026_06_05_residual_producer_build` — **reuse, do not re-handroll**.)
- **sealed rotating holdout / CPCV**: wire the **already-built** `learning.hidden_oos_state_registry`
  (V132) — the sealer that writes `state='sealed'` is the gap (memory: 0 writes today). The
  auto-loop cannot see or change sealed splits.
- **failure-mode novelty gate**: query `agent.lessons` (V133) dead-modes; reject re-testing
  known-dead hypotheses. Feeds §E (iii) `dead_failure_modes` context.
- **pre-registration**: register `{spec, mechanism}` *before* backtest (new
  `research.pre_registered_hypotheses` or reuse `replay.experiments.manifest`).

Throughput is **gated by tier** (more α-wealth / parallelism unlocked at higher tier) and by
local compute headroom (§K2).

**online-FDR parameter policy (v2 change 13 — design-level intent; the MATH is MIT's to
specify/verify, this is the policy the controller must implement):**
- **Conservative initial α-wealth.** Start the wealth budget low (a small fraction of the
  notional FDR target), so early in a capability's life it cannot spray discoveries. The system
  earns the right to test more by confirming, not by configuration.
- **Refund only on demo-confirmed discovery (not on merely passing a gate).** This is the
  load-bearing policy choice and it differs from textbook online-FDR: α-wealth is **debited when
  a hypothesis is tested** and **credited back only when the discovery is confirmed in DEMO**
  (a green Stage 0R + demo-fills result), **not** when it merely clears the offline math gate.
  Rationale: passing an in-sample/backtest gate is cheap and gameable; surviving demo is the
  honest signal. This makes the wealth self-throttle on **real** out-of-sample success and
  directly serves "6 weeks of candidates died of edge<cost" — only demo-survivors refund.
- **Family partitioning by capability / signal axis.** Maintain **separate α-wealth families**
  per capability and per signal axis (funding / OI / liquidations / orderbook / CVD / price),
  so a flood of tests on one axis cannot exhaust the budget for an independent axis, and the
  FDR guarantee is per-family. Cross-axis discoveries don't subsidize each other.
- **No human in this loop** (it is `direction=neutral` research) — the FDR controller is fully
  deterministic; the only human touch in research is the §C.1 demo-promotion trust gate at low
  tier. MIT owns: LORD/SAFFRON wealth update math, the demo-refund accounting correctness, and
  N_eff cluster deflation. PA owns only this policy framing.

#### G.1.1 [v4 M1] online-FDR refund policy — precise accounting (`NEEDS MIT RE-CONFIRM`)

**MIT HIGH M1.** v3 stated the *intent* ("refund only on demo-confirmed discovery") but left the
accounting underspecified, which is where an FDR controller silently becomes either too permissive
(over-refunding → spray) or vacuous. v4 specifies the accounting; **MIT ratifies/amends the formula
and constants.**

- **Initial wealth `W_0`.** Start conservative: `W_0 = γ · α_target` with `γ = 0.10` (a capability
  begins with 10% of the notional FDR budget; it *earns* more by confirming, not by config). Per
  the family partition, **each (capability × signal-axis) family has its own `W_0`** (§G.1).
- **Debit on test.** When hypothesis *i* is tested at level `α_i`, debit the wealth: `W ← W − α_i`
  (LORD-style: `α_i` is the controller's chosen test level for slot *i*). A family whose wealth
  would go `≤ 0` **cannot test** until a refund arrives (self-throttle).
- **Refund amount on demo-confirmed discovery — the load-bearing choice.** When (and only when) a
  tested hypothesis is **confirmed in demo** (definition below), refund. **PA default = proportional
  refund of the level spent on that discovery, `W ← W + φ · α_i`** with `φ = 1.0` (full refund of
  that hypothesis's own debit) as the starting point; the textbook LORD "+α on each rejection"
  refund is **deferred to demo-confirmation**, not granted at gate-pass. **MIT decides** whether the
  refund is the full `α_t` (a fixed wealth increment per confirmed discovery, LORD-classic) or the
  proportional `φ · α_i` (refund what that hypothesis cost) — both are defensible; PA's default is
  proportional `φ=1.0` because it is exactly self-funding (a confirmed discovery pays back its own
  budget, no net inflation). **This is the `NEEDS MIT RE-CONFIRM` knob.**
- **In-flight variant accounting.** A hypothesis can be **tested (debited) but not yet
  demo-resolved** (it is replaying / in demo). Such in-flight debits **stay debited** — wealth is
  **not** restored on "still pending," only on confirmed. So a family can exhaust its wealth on
  in-flight tests and must wait for confirmations; this is the intended back-pressure. Track each
  debit's state `{pending | confirmed | failed}`; only `pending→confirmed` triggers a refund;
  `pending→failed` triggers **no** refund (the wealth stays spent — failing forward is costly, as it
  should be).
- **Demo-confirmation minimum bar.** A discovery counts as "confirmed" **only** if its demo result
  clears a minimum so a lucky 3-fill run cannot refund wealth: **`n_trades ≥ 30` in demo AND a
  green Stage 0R AND a non-negative demo net edge** (and it has satisfied §C.3's ≥21 forward-OOS
  days). Below `n_trades = 30` the demo result is **insufficient** → the debit stays `pending`
  (neither confirmed nor failed) until enough demo trades accrue. (This `n_trades ≥ 30` bar is the
  same spirit as the §G.2 step-0 `N_trades_oos ≥ 50` math-gate bar — small samples never drive an
  irreversible accounting credit.)
- **MIT owns:** the LORD/SAFFRON wealth-update math, the `W_0`/`γ`/`φ` constants, the
  full-vs-proportional refund choice, and proving the refund cannot be gamed by repeatedly
  re-testing a near-duplicate (this is why §G.1.2 N_eff clustering must gate which tests are even
  *distinct*).

#### G.1.2 [v4 M2] N_eff deflation ↔ FDR controller wiring (`NEEDS MIT RE-CONFIRM`)

**MIT HIGH M2.** Verified against the repo: `program_code/learning_engine/dsr_gate.py` deflates the
Sharpe by `n_trials_K` — but `K` is a **manifest-supplied input** (`DsrResult.n_trials_K`), and the
gate **does not compute or export an effective number of trials / N_eff**. So today there are **two
disconnected selection-bias mechanisms**: (a) DSR's K-deflation inside the math gate, and (b) the
new α-wealth controller's per-test debit. If they run independently, a cluster of near-duplicate
variants either **double-charges** (debited in α-wealth *and* deflated in DSR as K independent
trials) or **double-counts a discovery** (refunds wealth *and* passes a K-deflated DSR as if it were
one of K independent shots). v4 wires them through a **single N_eff**:

- **N_eff is computed from the variant cluster** (López de Prado clustering on the variants' return
  correlation): a set of `M` correlated variants collapses to `N_eff ≤ M` effective independent
  trials. PA default: hierarchical clustering on the variant return-correlation matrix, `N_eff =
  number of clusters at a correlation cut` (MIT ratifies the linkage + cut, reusing the project's
  vetted clustering if one exists; **do not re-handroll**, memory `project_2026_06_05_residual_
  producer_build`).
- **N_eff is the single quantity handed to BOTH mechanisms.** (i) The math gate's DSR uses
  **`n_trials_K = N_eff`** (not the raw variant count `M`) — so a family of near-duplicates is not
  punished as `M` independent shots, and not under-punished as 1. (ii) The α-wealth controller
  treats the cluster as **one effective test** for debit purposes: a cluster of `M` correlated
  variants debits **once** (at the cluster's chosen `α_i`), not `M` times, and a confirmed discovery
  in that cluster refunds **once**. The cluster's representative (best-by-DSR member) carries the
  debit/refund.
- **Single shared debit — no double-charge, no double-count.** The contract: **one effective trial
  (N_eff unit) ⇒ one α-wealth debit and one DSR K-slot.** A discovery is "one rejection" for both
  mechanisms simultaneously. Concretely the controller emits, per cluster: `{N_eff, K_for_dsr =
  N_eff, alpha_debited, debit_state}`; the math gate reads `K_for_dsr`; the wealth ledger reads
  `alpha_debited` + `debit_state`. They reconcile on the same cluster id.
- **Why this matters for honesty:** the project's recurring lesson is selection-bias dressed as
  discovery. Deflating by raw `M` *over-states* rigor on duplicates (you "tried 50" but they were
  the same idea); deflating by 1 *under-states* it. N_eff is the honest middle, and making **both**
  the DSR gate and the FDR budget consume the **same** N_eff is what keeps "high-throughput" from
  quietly becoming "p-hacking at scale."
- **MIT owns:** the clustering method + cut (what makes two variants "the same"), the proof that
  N_eff→K_for_dsr is the correct deflation input to `dsr_gate`, and the single-debit reconciliation
  (a discovery is never both refunded *and* counted as an independent K-shot). **`NEEDS MIT
  RE-CONFIRM`.**

### G.2 Q3 — research pipeline LLM cascade

```
Ollama (generate + AutoMix-style self-verify + LOOSE coarse screen;
        GATEKEEPER calibrated to AVOID false-kills — recall floor ≥0.85, §G.2.1)  ← layer2_critic precedent
   │  survivors only
   ▼
DETERMINISTIC MATH GATE — the ONLY alpha validator (NOT the LLM). Members, all hard:
   STEP 0  [v4 Q1]  sample precondition: N_trades_oos ≥ 50  → else verdict = DEFER (not PASS/FAIL)
   then    DSR(N_eff) / PBO / CSCV
           leak-free precondition [v4 M3]: requires shift1_compliance and/or is_oos_gap —
                   a name_pattern_check (leakage_check.py) pass is NOT sufficient
           beta-neutral [v4 B1]: the DETERMINISTIC §N.1 check (≥90d, |β|<0.15, |β_down|<0.15) —
                   a candidate failing §N.1 cannot pass the gate
           walk-forward / backtest
   │  math survivors only (verdict == PASS)
   ▼
Cloud L2 (deep reasoning ONLY on math survivors: interpret / red-team /
        propose new axes)                                              ← cost spent only here (§K1)
```
Cheap generate → math validate → expensive deep reason on survivors. Cost + governance align:
the LLM never validates alpha; it generates and (post-math) interprets. **[v4] Three new hard
members of the gate:** (Q1) a **step-0 `N_trades_oos ≥ 50`** precondition that yields a third
verdict **DEFER** below threshold (small-sample false-positive guard — never let DSR/PBO run on a
handful of trades and mint a false pass); (M3) the **leak precondition is `shift1_compliance` /
`is_oos_gap`**, not a `name_pattern_check` pass; (B1) **beta-neutral is the deterministic §N.1
computation** and is a hard precondition at the same tier as DSR/PBO. A DEFER verdict propagates to
§C.3 (cannot auto-promote to demo) and §N (`gate_verdict:"DEFER"` shown to the human).

#### G.2.1 [v4 M4] Ollama gatekeeper calibration SOP — defines "loose coarse screen"

**MIT HIGH M4.** The cascade leans on Ollama as a **cheap coarse screen** in front of the expensive
cloud reasoning, but "loose" was never operationalized — and a mis-calibrated screen is dangerous in
the **false-kill** direction: if Ollama silently drops real alpha before it reaches the math gate,
the project's core deficit (upstream discovery) gets *worse*, invisibly. v4 adds a calibration SOP
so "loose" is a measured property, not a vibe:

- **Held-out benchmark set.** Maintain a curated set of **known-good** and **known-bad** hypotheses
  / diagnoses (seeded from `agent.lessons` dead-modes for the bad class, and from historically
  demo-confirmed discoveries / correct post-hoc diagnoses for the good class). This is the gatekeeper
  test set; it is versioned and grows as outcomes accrue.
- **Measure precision/recall of the SCREEN (not the final answer).** The screen's job is binary:
  *pass-through* vs *coarse-reject*. On the benchmark set, measure **recall** (fraction of known-good
  that the screen *passes through* to the math gate) and **precision** (fraction of what it passes
  that is actually good). The objective is **high recall** — a loose screen must rarely false-kill.
- **Recall floor = 0.85 (PA default; MIT may raise).** The Ollama screen must achieve **recall
  ≥ 0.85** on the known-good set — i.e. it lets through ≥85% of genuinely good hypotheses (the math
  gate is the real filter; the screen only sheds obvious junk to save cloud cost). Precision may be
  modest (false-passes are caught downstream by the deterministic math gate at low cost — a
  false-pass wastes a cheap screen slot, a false-kill loses alpha forever). **The screen is tuned for
  recall, the math gate provides precision** — this is the defense-in-depth split.
- **Boundary of "loose."** "Loose coarse screen" = **threshold set to the most permissive operating
  point that still meets recall ≥ 0.85 while removing at least the obvious dead-modes** (novelty-gate
  duplicates, no-mechanism curve-fits, axes-not-available). If the screen cannot hit recall ≥ 0.85
  without passing essentially everything, it is **disabled** (degrade to "no screen" — everything
  goes to the math gate; costs more cloud but loses no alpha) and flagged for MIT.
- **Re-calibration cadence.** Re-measure on each benchmark-set version bump and at least monthly;
  drift in recall below the floor → screen disabled until re-tuned. Calibration runs are logged
  (precision/recall/threshold/version) so the §O metric and MIT can audit the screen over time.
- **MIT owns:** the benchmark-set construction, the recall floor (≥0.85 default), and the
  false-kill-vs-false-pass cost trade-off ratification.

### G.3 Q6 — retention (value-driven, TimescaleDB-native)

| Class | Content | Mechanism |
|---|---|---|
| **Permanent-small** | provenance index + distilled lessons / failure library | `agent.lessons` (V133) + a compact `agent.l2_calls` index view |
| **Permanent-full** | consequential rows: reached demo/live, adopted proposal, incident, gate survivor, registered hypothesis | `agent.l2_calls WHERE consequential=true` (set **at creation**) — never auto-dropped |
| **Hot→warm→cold** | non-consequential raw prompts/responses | TimescaleDB **native compression** + `drop_chunks` (NOT hand-rolled); cron: distill (feed Q1 novelty) → compress → drop |

`consequential` is stamped **at write time** by the applier/gate that consumes the reply
(reached a lane → true). The cron distills before dropping so lessons survive even when raw
rows are pruned. Reuses TimescaleDB native mechanisms (no bespoke archiver).

---

## H. GUI panel (ONE panel, vanilla JS)

Single panel `L2 Advisory Mesh` (extends the existing AI cockpit; vanilla JS, route =
parse→call→format only):

1. **Tier ladder** — current LearningTier + each capability's lock/unlock/active state, with
   **per-layer annotation** of what that tier means (read from `TIER_CAPABILITIES.description`,
   already bilingual in code). Visual: L1→L5 with the unlock criteria and which capabilities
   each unlocks.
2. **Posture knob** — Conservative / Standard (drives the existing autonomy switch; TOTP-gated
   write already exists). Shows what each posture changes per the §C table.
3. **Bright LIVE hard line** — a prominent, always-visible banner: "L2 NEVER orders, NEVER
   auto-mutates live. Live crossing = human + 5 gates + Decision Lease." Annotated with the
   5 gates from `_AUTONOMY_PATH_MATRIX` rows 1-5.
4. **Per-capability cards** — enabled/tier/model-tier/trigger/budget/spend + **the §O quality
   panel** (post-hoc correctness + $-spent-vs-value as the **promote drivers**; adoption shown but
   labeled weak-tiebreak / excluded from promote, v3 R2-2; current keep / **promote-eligible
   candidate awaiting human confirm** / demote state + why, v3 R2-1); feed of recent advisories
   with `l2_reply_id` (click → ground truth: full prompt/response).
   **The "earned-trust" promote candidate surfaces here as a one-click human confirm — the metric
   proposes, the human expands (v3 R2-1); the confirm is an operator-scope write (v4 §N.2/§O.4).**
   **[v4 Q3] While a capability is in its cold-start blind window (`N_outcomes < floor`), the card
   shows a prominent "blind window — k/N outcomes; metric not yet trustworthy" badge, displays the
   human-review *proxy* correctness (clearly labeled proxy, not measured), and the card's manual
   audit cadence is raised (§O.5).**
5. **Live-cross approval inbox** — the **one-page packet** (full spec in §N) for the rare human
   approval. **Math-primary (v3 R2-4): math + provenance lead; L2 contributes caveats only (no
   live verdict), rendered subordinate to the math and after a math acknowledgement.**
   **[v4] The math block now also shows the deterministic `beta_neutral_check` (residual β +
   down-market β + factor model + window, B1/§N.1), the gate verdict incl. DEFER (Q1), and the cost
   decomposition `cost_edge_ratio`/`gross_edge_bps`/`total_cost_bps` + `max_dd_duration_days` (Q2)
   — so the human can math-self-judge edge-vs-cost and beta-masquerade without a model.**
6. **NL render on demand** — a "render to prose" button (human-triggered only); the structured
   ground truth is **always** shown alongside, never replaced (root principle: human always
   sees ground truth).

Both GUI and backend **annotate every layer's meaning** (the operator's explicit ask).

### H.1 Per-layer annotation copy (v2 change 11 — actual text, not "annotate")

These are the **draft strings** the GUI renders next to each control (Chinese-primary per repo
convention; E1a finalizes wording, this is the substance). Tier descriptions are read from
`TIER_CAPABILITIES.description` where they already exist (bilingual in code); the rest are new.

**Tier ladder (per tier):**
- **L1 — 觀測**：「系統只觀測與本地告警。可跑 ml_advisory 的 diagnose/interpret（唯讀建議），不
  產生任何自動變更。L2 在此層 = 純顧問。」
- **L2 — 假設**：「解鎖特徵假設產生（feature hypotheses → backlog）。所有假設只進研究待辦，由
  確定性數學閘（DSR/PBO/leak）驗證；L2 從不自驗。」
- **L3 — 研究迴圈**：「解鎖 online-FDR α-wealth 研究迴圈與策略變體草擬。仍只產 proposal，不部署。
  α-wealth 保守起始，只有 demo 確認的發現才回補額度。」
- **L4 — Demo 自晉升**：「能力憑 §O **正確率/價值** 紀錄**贏得『晉升至 demo 的資格』**。達標時系
  統送出**一鍵 promote-eligible 候選**，由**人工確認**移除信任關卡（v3 R2-1：品質度量只**提議**晉
  升，**不自動**移除關卡——移除信任關卡屬自主**擴張**，恆需人工確認）。確認後晉升走 Stage 0R 綠 +
  輕量閘。」
- **L5 — 管線自優化**：「解鎖學習管線自我優化建議。仍不可改 live；can_modify_live_config 在所有
  層永遠為 False（硬編碼於碼）。」

**Posture knob:**
- **Conservative（出廠預設）**：「最保守。研究/假設/診斷照常自動；但**晉升類**動作（demo 晉升）
  在此 posture 下**刻意插入人工核准**作為信任建立關卡——能力憑 §O 正確率/價值證明可靠後，系統送
  出**一鍵候選**由**人工確認**移除此關卡（v3 R2-1：**度量不自動移除**，只把人工決策簡化為一鍵）。
  防禦性收緊仍自動。」
- **Standard**：「能力達標後，由**人工一鍵確認**移除 demo 晉升的人工關卡；確認後走確定性輕量閘自
  動晉升。**仍不觸及 live**；放鬆類動作**永遠**人工；**任何自主擴張（含移除信任關卡）皆人工確認**
  （v3 R2-1）。收緊類動作兩種 posture 皆自動。」

**LIVE hard line banner (always visible, bright):**
- 「**L2 永不下單、永不自動改動 live。** 任何 live 跨越 = 人工 + 5 道閘 + Decision Lease。
  自動迴圈在結構上**無法觸及** live（lane.direction=expand → 強制人工，由 loader 型別強制）。」
- 下方列出 5 道閘現狀（讀 `_AUTONOMY_PATH_MATRIX` 前 5 行）：`live_reserved` / Operator 角色
  認證 / `OPENCLAW_ALLOW_MAINNET` / 有效 secret slot / 簽署未過期 `authorization.json`。

**Per-capability card (per capability):**
- 「**ml_advisory**：接現有 ML 管線（訓練結果 / 特徵重要度 / leakage_check）。產：特徵假設 →
  backlog、洩漏/漂移診斷、結果解讀。**唯建議**，寫入既有 requires_governance 面，從不重訓/不部署。
  Cascade：Ollama 篩 → 數學/leak 閘 → 倖存者才用 cloud-L2 深推。」
- 「**incident_sentinel（本地廉價修）**：本地 liveness/異常偵測 → 告警。**告警 ≠ 補救**；L2 至多
  草擬 runbook 步驟，從不執行。」
- 每張卡底部固定一行：「此能力的 direction = <contract|neutral|expand>；autonomy 由
  (lane+tier+posture) **推導**，非設定（§C.2）。**自主擴張（升級/移除信任關卡）= 人工一鍵確認；
  自主收縮（降級）= 自動**（v3 R2-1）。」
- §O 品質面板（每張卡）：顯示 **post-hoc 正確率 + 成本/價值**（主驅動）與 adoption（僅弱輔，**不**
  進晉升判定，v3 R2-2）；當前 keep / **promote-eligible 候選（待人工確認）** / demote 狀態與原因。

---

## I. Reuse vs new

| Build | Decision | Why |
|---|---|---|
| LearningTier L1–L5 scaffold | **REUSE** (`learning_tier_gate.py`) | Already wired, already has the exact capability flags, already enforces `can_modify_live_config=False`. |
| **ML pipeline (training + MLDE shadow/demo + leak check)** | **REUSE** (`program_code/ml_training/*`, V031 view, `learning.mlde_shadow_recommendations`) | **v2:** the first L2 capability (`ml_advisory`) attaches here. It reads the V031 view + training artifacts and feeds the **existing** `applied=false`/`requires_governance=true` advisory surface — a reasoning layer over an already-advisory pipeline, 0 new execution authority. |
| Autonomy Conservative/Standard + path matrix | **REUSE + EXTEND** (`governance_autonomy_service.py` `_AUTONOMY_PATH_MATRIX`) | Add L2 lanes as rows; do not fork the switch. |
| AI-call lineage discipline | **REUSE pattern** (`bybit_ai_invocation_ledger.py`, `agent.ai_invocations`) | sha256/idempotency/event-ts helpers; D3 table extends, not reinvents. |
| Layer2Engine session worker | **REUSE** as one Orchestrator executor | Don't merge scheduling into the worker. |
| ContextDistiller (input extraction) | **REUSE** | The §E input-Ollama seam. |
| layer2_critic (Reflexion) | **REUSE** | The §G2 Ollama self-verify / AutoMix gatekeeper. |
| agent.lessons (V133) | **REUSE** | Q6 permanent-small + Q1 novelty gate. |
| hidden_oos_state_registry (V132) | **REUSE (wire the sealer)** | Q1 sealed holdout; sealer producer is the gap. |
| residual report registry (V131) | **REUSE** | Gate-seam evidence precedent. |
| dsr_gate / pbo_gate vetted helpers | **REUSE** | Q1 math gate; do not re-handroll stats (memory lesson). |
| TimescaleDB native compression / drop_chunks | **REUSE** | Q6 retention; no bespoke archiver. |
| Watchdog→alert wire | **REUSE / build-on** | §J local sentinel; sibling PA report 2026-06-05. |
| **`agent.l2_calls` ledger (V134)** | **NEW** | The central D3 gap — no full prompt/response audit exists. |
| **`L2AdvisoryOrchestrator` singleton** | **NEW** | The conductor; register in singleton SSOT. |
| **PromptContract + output-schema registry** | **NEW** | Versioned deterministic templates + guards. |
| **online-FDR α-wealth controller** | **NEW** | Q1 LORD/SAFFRON; greenfield. |
| **auto/scheduled/threshold trigger surface** | **NEW** | L2 is manual-only today; Orchestrator adds gated triggers. |
| **`l2_capability_registry` + default TOML** | **NEW** | §B registry (no `autonomy_level` field; derived). |
| **`l2_gate_seam_log` + full-chain provenance cols** | **NEW** | §D3/D4 + §D.2 chain (`source_l2_reply_id` propagated to hypothesis/variant/replay/demo/live). |
| **`LANE_DIRECTION` typed table + loader enforcement** | **NEW** | v2: the typed tighten/loosen asymmetry invariant (§B, §C.2). |
| **Trigger admission stage (debounce/dedup/coalesce)** | **NEW** | v2 §F.1 storm control. |
| **Conflict adjudication table** | **NEW** | v2 §F.2 (deterministic precedence, no model arbitration). |
| **Feedback→rule pipeline + `research.gate_rule_candidates`** | **NEW** | v2 §M (forensic → ①gate-rule-candidate / ②lesson / ③demote). |
| **`learning.l2_capability_quality` + rollup policy** | **NEW** | §O — **v3: drives auto-DEMOTE + emits a human-confirmed PROMOTE candidate (R2-1); promote signal = correctness+value, not adoption (R2-2); sample-floor gates promotion only (R2-3).** |
| **Live-cross packet assembler (`GET /…/live_cross/{id}`)** | **NEW** | §N — read-only render; no new live path. **v3 (R2-4): block 5 = L2 caveats, NOT a verdict; math-primary + math-ack-gated.** |
| **Post-cross live-trade provenance col (`source_l2_reply_id` on live fills/outcomes + lease audit row)** | **NEW (v3 R2-5)** | §D.2 — audit-only; threads the lineage chain to live trades; no live-authority change. |
| **Deterministic `beta_neutral_check` computation (§N.1)** | **NEW (v4 B1)** | factor model (≥BTC; rec. BTC+altcap) + ≥90d window + `|β|<0.15` + down-market `|β_down|<0.15`; one computation consumed by math gate + §N packet + §E(ii). **Reuses** `dsr_gate`/`pbo_gate` vetted stats + any existing PIT universe; **NEEDS QC sign-off**. |
| **`learning.l2_promote_candidates` read-only inbox (§O.4)** | **NEW (v4 C1)** | the metric writes a candidate row; **only** the operator-scope human-confirm route promotes. Carbon-layer proof the Orchestrator cannot call `promote_tier`. |
| **N_eff cluster controller ↔ FDR/DSR single-debit wiring (§G.1.2)** | **NEW (v4 M2)** | computes N_eff from variant cluster; feeds `K_for_dsr=N_eff` to `dsr_gate` **and** one α-wealth debit/refund per cluster. **Reuses** vetted clustering; **NEEDS MIT sign-off**. |
| **D3 sanitize-before-persist redactor (§D.1.1)** | **NEW (v4 E2)** | scrubs secrets/`str(e)`/raw errors from all 4 large-text columns on the write path; reuse a repo redactor if one exists. |
| **Ollama gatekeeper calibration SOP + benchmark set (§G.2.1)** | **NEW (v4 M4)** | held-out good/bad set, recall floor ≥0.85 defines "loose"; **NEEDS MIT ratify**. |

---

## J. Build order

Strict dependency order; each phase is independently shippable and green-gated. **v2 change 1
reordered this**: the ML advisor (operator's choice) is the first L2 capability, before the
online-FDR research loop; incident-sentinel drops to a parallel cheap local fix.

1. **D3 foundation (V134 `agent.l2_calls` + FULL provenance chain §D.2 + gate-seam + fault-loc
   protocol + [v4 E2] sanitize-before-persist §D.1.1).** Nothing else ships until this is in. *Why
   first:* every capability must be auditable from day one; retrofitting provenance is how lineage
   gaps happen (root principle 8). **The sanitize pass (§D.1.1) is part of the D3 write path from
   day one — a ledger that can leak a secret is worse than no ledger.**
2. **Orchestrator + capability registry (no `autonomy_level` field; derived per §C.2) +
   PromptContract/output-schema registry + out-of-bound guards + trigger admission stage (§F.1)
   + conflict adjudication table (§F.2)** — all capabilities `enabled=false` by default. Wire
   D3 writes. **The typed `LANE_DIRECTION` invariant lands here (the CC linchpin).**
3. **ML advisor `ml_advisory.v1` (FIRST L2 capability — operator's choice).** Attaches to the
   existing ML pipeline (`run_training_pipeline.py` / `mlde_shadow_advisor.py` /
   `leakage_check.py`; V031 view). Modes: feature-hypothesis → backlog, leak/drift diagnosis,
   training-result interpretation. Cascade Ollama→math/leak→cloud. `direction=neutral`, feeds the
   existing `requires_governance` advisory surface (lowest blast). **Does NOT need the online-FDR
   controller yet** — uses the existing DSR/PBO gates as the validator. **[v4] The math gate this
   uses already includes the deterministic §N.1 `beta_neutral_check` (B1), the §G.2 step-0
   `N_trades_oos≥50` DEFER bar (Q1), and the typed leak `source_class` (M3) — so even the first
   capability cannot mistake a beta-masquerade or a small-sample pass for alpha. B1's QC sign-off is
   a precondition for this phase shipping a *promotion-relevant* verdict (diagnose/interpret modes
   can ship earlier as they do not assert alpha).**
4. **online-FDR research loop** (α-wealth controller per §G.1 policy + sealed-holdout sealer for
   V132 + novelty gate + Q3 cascade) — the high-throughput honest research engine that upgrades
   the ML advisor's backlog into a disciplined infinite-test stream. Tier-gated (L3+).
5. **Feedback→rule pipeline (§M) + per-capability quality/ROI metric (§O).** Land once ≥1
   capability has produced advisories to measure and forensic conclusions to harvest. These close
   the self-governing loop (**v3:** quality auto-*demotes* and *proposes* a human-confirmed
   promote; forensics become rules — every autonomy *expansion* stays human-confirmed, R2-1). The
   §O metric ships with the **human-confirm promote-candidate** path (R2-1), the
   **adoption-excluded** promote signal (R2-2), and the **sample-floor-gates-promotion** rule (R2-3).
   **[v4] The §O promote-candidate writes the read-only `learning.l2_promote_candidates` inbox
   (C1, §O.4) — the Orchestrator/metric have no `promote_tier` call; only the operator-scope
   human-confirm route promotes. The §O.5 cold-start blind-window protocol (Q3) ships with it.**
6. **Other Tier-1 capabilities** (cloud/Ollama, low blast): regime/risk advisory (feeds the
   deterministic tighten lane, `direction=contract`, auto), candidate-death-cause analysis,
   **incident-diagnosis (advisory runbook)** — now here, not first.
   **In parallel (cheap, local, independent of the above):** `incident_sentinel` — local
   liveness/anomaly/regime detection on the watchdog→alert wire (sibling PA report 2026-06-05),
   `model_tier=local_sentinel`, `direction=neutral`/alert-only, **never remediate**. Closes the
   20h-silent-outage gap; needs no cloud, no D3-blocking, so it can ship alongside any phase.
7. **GUI panel** (tier ladder + Posture + live line + per-capability cards w/ §O quality panel +
   §N approval inbox + NL-on-demand + §H.1 annotations). Last, because it visualizes everything.

(Live-cross human approval + Decision-Lease already exist; L2 only *packages* the §N one-page
packet into the existing approval flow — no new live path.)

---

## K. Governance mapping (per root principle + Hard Boundary)

| # | Principle | How L2 Advisory Mesh complies |
|---|---|---|
| 1 | Single write entry | L2 has **no** order path; proposals reach effects only via existing deterministic appliers/gates. |
| 2 | Read/write separation | L2 is research/advisory = read-heavy; the only writes are to its own provenance/registry tables + lane-bound reversible appliers. |
| 3 | AI output ≠ command | **The thesis of the whole design.** Output → deterministic gate → (proposal) → human for live. `is_simulated`/shadow preserved. |
| 4 | Strategies cannot bypass Guardian/risk | Risk-tighten advisory is an *input* to the deterministic governor; governor owns the final clamped number (§F.2(a) strict precedence: deterministic > advisory). No bypass. |
| 5 | Survival > profit | **Typed** asymmetry (§C.2/§B `LANE_DIRECTION`): `contract`/`neutral` may auto, `expand` forced human — loader-enforced. §F.2(b): `contract` recommendation beats `expand`. Fail-safe degrades to baseline; DOC-08 cap. **v4: the deterministic `beta_neutral_check` (§N.1, B1) — ≥90d window, `|β|<0.15`, down-market `|β_down|<0.15` — and the §C.3 forward-OOS bar (B2) are hard gate members, so the down-beta masquerade that killed 5 candidates cannot pass an unattended gate.** |
| 6 | Uncertainty → conservative | Derived autonomy picks MANUAL/TIER_LOCKED when in doubt; guard rejects/clamps; §F.2 unresolved conflict → no auto-apply; fail-safe → NO_ADVICE. **v3: autonomy only ever moves *down* automatically; every expansion is human-confirmed; low-sample can only contract (R2-1/R2-3).** |
| 7 | Learning ≠ rewrite live | `can_modify_live_config=False` all tiers (already in code); no `lane: live` value exists; `expand`→MANUAL structural. **v4 (C1): the Orchestrator also has no `promote_tier` call — verified that primitive auto-raises L1→L4 with no `approved_by`; the metric writes only a read-only candidate inbox (§O.4), promotion is operator-route-only.** |
| 8 | Reconstructable & explainable | D3 ledger stores FULL prompt+input+response+versions; **full §D.2 provenance chain reply→hypothesis→strategy→demo→live**; fault-loc protocol; gate-seam log. **v4 (E2): full text is sanitized before persist (§D.1.1) — reconstructable without storing secrets/`str(e)`.** |
| 9 | Local + exchange protection | Sentinels are **local** (reliability); L2 never touches the stop/conditional-order path. |
| 10 | Fact/inference/assumption | Mandatory `fact_inf_assm` tags in every PromptContract + stored in D3. |
| 11 | Max autonomy in P0/P1 | L2 expands *research/advisory* autonomy within deterministic boundaries; never relaxes a hard limit; autonomy is **derived**, not a knob that can be misset upward. **v3 (R2-1): the system can never auto-*raise* its own autonomy — every expansion (incl. removing a trust-gate) is human-confirmed; only contraction is automatic. "expand=human" is now closed under autonomy itself.** |
| 12 | Evolve from evidence | Tier-promotion *eligibility* is **§O-quality-metric-driven** on **post-hoc correctness + cost-value** (v3 R2-2: not adoption — Goodhart-proof; v3 R2-3: never below sample floor), but the promotion itself is a **one-click human confirmation** (v3 R2-1, earned-trust candidate); research loop is FDR-disciplined (refund only on demo-confirmed §G.1); **§M feedback→rule pipeline turns forensics into gate rules / lessons / demotes** (graceful-degrades if the ① queue stalls, v3 R2-6). |
| 13 | AI cost ≥ edge | Cloud spend only on math survivors (§G2); per-capability + tier-gated budget; **§O auto-disables a capability whose cost > value**; DOC-08 cap. |
| 14 | Zero-external-cost operable | NO_ADVICE fail-safe = full deterministic baseline; sentinels local; Ollama fallback. |
| 15 | Multi-agent formal; Conductor ≠ trader | Orchestrator is a conductor, explicitly **not** a sixth trading agent; no order authority. |
| 16 | Portfolio-level risk | Regime/risk advisory consumes portfolio beta / corr-cluster exposure, not isolated trades. |

**Hard Boundary check:** L2 touches **none** of `live_execution_allowed`, `max_retries`,
`OPENCLAW_ALLOW_MAINNET`, `authorization.json`, `execution_authority`, `system_mode`, lease
*trading* authority. Live requires the unchanged 5 gates + Decision Lease, human-only. ML /
Dream / Executor / Strategist boundary preserved: L2 proposals still pass GovernanceHub +
Decision Lease before any live effect. **CC must verify there is no auto-path to live in the
registry loader and Orchestrator (the load-bearing CC stress-test).** **v4 adds the carbon-layer
autonomy boundary to the same check: the Orchestrator + §O metric have NO call to
`LearningTierGate.promote_tier` (verified to auto-promote L1→L4 with no `approved_by`) — the only
autonomy-raising writer is the operator-scope human-confirm route (§O.4); every new write endpoint
is operator-scope (§N.2); and D3 sanitizes secrets before persist (§D.1.1).**

---

## L. Open questions · needs-verification · who stress-tests what

### Open questions (for PM / operator)
1. **[OPEN] D3 retention economics.** Full prompt+response per call × projected volume — at what
   call rate does TimescaleDB compression keep this affordable? Need a volume estimate to set
   the non-consequential TTL. (Drives §D1/§G3.) *Still open in v2.*
2. **[OPEN] Auto-trigger cadence vs DOC-08 $2/day.** Local sentinels are free, but auto/scheduled
   *cloud* capabilities spend. What is the per-capability daily envelope, and may high-ROI
   capabilities exceed $2/day "by rule" (and what is the rule)? *v2 adds §F.1 hard per-capability
   daily ceiling + §O cost-vs-value auto-disable as the backstop, but the $2/day-override policy
   itself is still an operator call.*
3. **[RESOLVED v2]** ~~Risk-tighten auto-apply — operator comfort.~~ **Operator confirmed: accepts
   automatic defensive tightening (bounded + cooldown; deterministic governor owns the final
   clamped number).** Upgraded to a typed `direction=contract` invariant (§C.2, §B `LANE_DIRECTION`).
4. **[RESOLVED v2]** ~~First Tier-1 capability after D3.~~ **Operator chose the ML hypothesis/
   diagnosis advisor** (`ml_advisory.v1`, §E (0)), scoped to attach to the existing ML pipeline,
   ahead of the online-FDR loop. incident-diagnosis demoted to §J phase 6 + parallel local sentinel.
5. **[RESOLVED v2]** ~~Posture default.~~ **Shipped default = Conservative** (operator confirmed).
6. **[OPEN] Ollama generation quality for the cascade.** Is local Ollama strong enough to be the
   *generator* (and the `ml_advisory` hypothesizer) without a false-kill / false-pass storm?
   (Calibration risk — see MIT below.) *Still open in v2; applies to both §E(0) and §G.2.*

### Open questions newly surfaced by v2 (for PM / operator)
7. **§O promote weights + sample floor + threshold (v3 R2-1/R2-2/R2-3 reshape this).** What
   `w_corr / w_cost` (on **post-hoc correctness + cost-value only** — adoption is excluded, R2-2),
   what **sample floor N** (below which a capability can **never** become promote-eligible, R2-3),
   and what sustained-HIGH threshold should make the system **emit a one-click promote-eligible
   candidate** (NOT auto-remove — the removal is a **human confirmation**, R2-1)? (Sets how fast a
   capability *earns the right to ask*; the human still grants. Recommend starting strict + a
   high sample floor.) *v3: this is now a "when to surface the candidate" threshold, not a
   "when to auto-expand" threshold.*
8. **§M-① gate-rule-candidate review SLA.** Feedback-pipeline gate-rule candidates land
   review-gated (not auto-active). Who reviews (PA/CC) and on what cadence? **v3 (R2-6): a stalled
   ① queue degrades gracefully — ② suppression and ③ demote already fired immediately, so safety
   holds; only *new behavior* waits. The SLA governs how fast improvements land, not whether the
   system stays safe.** (②lesson/③demote apply immediately as fail-safe; only ① needs this.)
9. **§F.1 debounce defaults per trigger class.** Per-capability `debounce_secs` defaults for
   regime-transition vs anomaly vs ml:training_complete — operator/E5 tune vs cost.

### Needs-verification (before E1 design-sign-off)
- V134 is the next free migration number (confirm no parallel-session V134 lands first).
- `agent.ai_invocations` shape (re-read full V064 §) to finalize how much D3 reuses vs adds.
- `Layer2CostTracker` persistence (`runtime/layer2_cost_state.json`) — confirm it is **not**
  already a partial audit we can extend (I believe it is cost-only, not full prompt/response).
- Linux PG empirical dry-run of V134 (double-apply idempotency) per `feedback_v_migration_pg_dry_run.md`.
- Exact GovernanceHub read-only surface the Orchestrator may call (capability state, lease/risk
  *projections*) without acquiring any trading-scope lease.
- **(v2) Exact ML-pipeline read seam for `ml_advisory`.** Confirm the V031 view columns +
  `mlde_shadow_advisor` / `run_training_pipeline` / `leakage_check` output shapes so §E(0)'s
  structured `context` block is grounded, and confirm `learning.mlde_shadow_recommendations`
  (`applied=false` / `requires_governance=true`) is the right advisory sink for the backlog
  items (re-read those modules in full before E1 sign-off — this design read heads/grep only).
- **(v2) Provenance-chain column adds (§D.2)** to `research.hypotheses` / variant / replay /
  demo manifests — confirm each target table can take a propagated `source_l2_reply_id` without
  schema conflict (some are V131/V132 hash-chained; additive col only).
- **(v3 R2-5) Post-cross live-trade provenance column.** Confirm the **live fills / live
  `decision_outcomes`** table(s) and the **Decision-Lease audit row** can each take an additive
  `source_l2_reply_id` column (propagated, never re-derived) without schema conflict, and confirm
  the engine write-path that records live fills can copy the lease's root id forward. Audit-only
  column; **no live-authority change**. (Identify the exact live fills/outcomes table on Linux;
  some lineage rows may be hash-chained — additive col only, like V131/V132.)
- **(v4 B1) §N.1 beta-neutral inputs.** Confirm a leak-free PIT **cap-weighted altcoin basket**
  return series exists (or specify its construction) for the two-factor model, and confirm a
  leak-free **down-market regime label** is available for the regime-conditional sub-sample (per
  Alpha Evidence Governance — computed locally, not future-looking). Confirm ≥90d aligned return
  history is reachable per candidate.
- **(v4 M3) Leak-check coverage.** Confirm whether **`shift1_compliance`** (feature pipeline uses
  only ≤-decision-bar info) and **`is_oos_gap`** (real IS→OOS temporal gap) checks already exist
  anywhere in `program_code/ml_training` / the gate stack, or must be built — today only the
  `name_pattern_check` (`leakage_check.py`, 78 lines) is present.
- **(v4 M2) `dsr_gate` N_eff input.** Confirm `dsr_gate.DsrResult.n_trials_K` can be fed
  `K_for_dsr = N_eff` from the cluster controller (it currently takes a manifest `K`), and that no
  caller hard-codes raw variant count.
- **(v4 C1) `learning.l2_promote_candidates` table.** New read-only inbox table (V13x — next free
  after V134); Linux PG dry-run + double-apply idempotency per `feedback_v_migration_pg_dry_run.md`.
  Confirm nothing reads it to auto-change behavior.
- **(v4 E2) Secret redactor.** Confirm whether a vetted secret-pattern redactor already exists in
  the repo to reuse for §D.1.1 (do not re-handroll if one exists); else specify the pattern set.

### Open MEDIUMs (folded into §L for E1; do NOT block v4 sign-off)
- **Cross-axis FDR family membership** — define exactly which (capability × signal-axis) pairs share
  a family vs are independent (§G.1 partition); edge cases like a hypothesis spanning two axes.
- **V132 `ON CONFLICT`** — when the sealer writes `state='sealed'`, emit a `NOTICE` on conflict so a
  double-seal is observable (not silent).
- **`available_signal_axes` caller healthcheck** — the §E(0)/(iii) `available_signal_axes` context
  must reflect axes that are *actually live* (funding/OI/liq/orderbook/CVD/price); add a healthcheck
  so a dead feed cannot let L2 propose on data we are not really ingesting.
- **PIT snapshot at trigger-time T** — `regime_confidence` + `drawdown_pctile` (and any §E(ii)
  feature) must be snapshotted using the **last *closed* bar at trigger time T**, never a partial
  in-progress bar (the `rolling(N).max()` look-ahead lesson, memory `feedback_indicator_lookahead_bias`).
- **`bull_only_flag` deterministic rule** — compute it from a deterministic regime-share rule (e.g.
  fraction of evidence bars in up-regime > threshold), **not** an LLM judgment.
- **`falsification_test` structure + immutability** — give it structured sub-fields
  (`{null_hypothesis, test_statistic, reject_condition}`) and make a registered spec **immutable**
  after pre-registration (§G.1) so it cannot be silently edited post-hoc.
- **§M-③ "clearly-bad" operational definition** — e.g. `net_edge < −5 bps AND N ≥ 10` as the
  threshold that lets a single outcome auto-demote (§O.3 / §M-③), so "clearly-bad" is not subjective.
- **V134 `consequential` post-stamp vs append-only** — the row is append-only but `consequential` is
  stamped *at creation*; if an artifact only later reaches a lane, reconcile (a side index table, or
  a defined "stamp at first lane-entry within an append-only-safe pattern") rather than UPDATE.
- **Canary alert consumer** — already covered by the build #3 local sentinel (watchdog→alert wire,
  sibling PA report); noted so the 20h-silent-outage gap is explicitly owned.

### Stress-test ownership
- **CC (compliance):** (1) prove **no auto-path to live** exists in the registry loader +
  Orchestrator routing (the single most important check); (2) 16-principle + Hard-Boundary
  audit of the Orchestrator and appliers; (3) verify `consequential` / append-only grants
  cannot be subverted; (4) verify the asymmetry rule (tighten-auto/loosen-human) is
  structurally enforced, not just documented. **(v2 additions):** (5) the typed
  `LANE_DIRECTION` + §C.2 STEP-1 `expand`→MANUAL is non-overridable by any tier/posture, and a
  config that declares `autonomy_level` or tries to auto-apply an `expand` lane is **rejected by
  the loader** (the derived-autonomy linchpin); (6) §F.2 has **no code path** where a model
  output adjudicates between two proposals (adjudication is table-driven; deterministic always
  wins); (7) §M is **demote-only** — it has no promote target; §M ②/③ only ever move in the
  fail-safe direction; (8) the §O metric can **auto-move autonomy only in the DEMOTE/DISABLE
  direction**. **(v3 additions — the round-2 load-bearing checks):**
  **(10) THE LINCHPIN — no automatic autonomy expansion exists anywhere.** Prove there is **no code
  path** by which the §O metric (or any automatic signal — tier, posture, feedback, schedule)
  **removes a trust-gate, widens an auto-applicable lane, or raises a capability's effective
  autonomy without a human confirmation event.** The §O HIGH branch may **only** emit a
  *promote-eligible candidate*; the actual gate-removal/expansion must be a distinct
  human-confirm action (mirror the TOTP-gated posture-switch precedent). Grep proof required: the
  only writers that *raise* autonomy are reachable solely from a human-confirm handler; every
  automatic writer moves autonomy *down* only. **This is "expand=human" closed under autonomy
  itself — the single most important v3 check.**
  **(11) Promote signal excludes adoption (R2-2).** The promote-eligibility computation reads
  `post_hoc_correctness` + `cost-value` and **not** `adoption`; a high-adoption / low-correctness
  capability **demotes** (is not protected). No code path lets adoption drive a promotion.
  **(12) Low-sample can only contract (R2-3).** Below the sample floor, **no** promote-candidate is
  emittable; a single clearly-bad outcome **can** still demote/disable. Verify the floor gates
  promotion but not demotion.
  **(13) Live packet is math-primary, L2 gives no live verdict (R2-4).** The §N packet block 5
  contains **no `verdict`/`cross|hold|reject` field** (caveats/risks-noted only), and is rendered
  **subordinate to + gated behind acknowledgement of** the math block (`math_ack_required`); the
  packet endpoint is read-only and cannot itself approve. **(14, was 9)** the §N packet endpoint is
  read-only and cannot itself approve (re-confirm with the block-5 demotion).
  **(v4 additions — the four-review carbon-layer checks):**
  **(15) [C1 LINCHPIN] The Orchestrator cannot call the tier-promotion primitive.** Grep proof: the
  `L2AdvisoryOrchestrator` + §O metric modules contain **zero** references to
  `LearningTierGate.promote_tier` (verified to auto-promote L1→L4 with no `approved_by`) or any
  other autonomy-raising / trust-gate-removing writer; the §O promote-candidate writes **only** the
  read-only `learning.l2_promote_candidates` inbox row; the **only** callers of `promote_tier` /
  gate-removal are inside the operator-scope human-confirm route (§O.4, §N.2). Every automatic
  autonomy writer moves **down** only.
  **(16) [C2] Demo posture does not read `can_auto_deploy_to_paper`.** That flag is `True` at all
  tiers (verified `learning_tier_gate.py:185/196/205/218/231`); grep the applier/Orchestrator for a
  branch on `can_auto_deploy_to_paper` that decides auto-vs-manual demo → must be **none**;
  auto-vs-manual is `LANE_DIRECTION`+STEP-3+§C.3 only.
  **(17) [B2] No auto demo-promotion below the forward-OOS bar.** No code path auto-promotes to demo
  with `forward_oos_days < 21` or a §G.2 verdict of DEFER; the bar is read inside the deterministic
  applier, not from any L2 field (§C.3).
  **(18) [E1] All new write endpoints are operator-scope.** `/cost/reset`, `/cost/pricing`, every
  Orchestrator/registry mutation route reject non-operator callers; no write endpoint is reachable
  from a read-only surface (§N.2).
  **(19) [E2] No unsanitized large-text write to any durable store.** The D3 sanitize pass is on the
  write path; a synthetic-secret prompt/response/error stores `[REDACTED:*]`, never the secret
  (§D.1.1).
- **MIT (quant/ML rigor):** (1) Q1 online-FDR α-wealth correctness (LORD/SAFFRON math,
  wealth refund, N_eff deflation) — this is where statistical-honesty lives or dies;
  (2) sealed-holdout sealer actually prevents reuse (the V132 0-write gap); (3) Ollama
  gatekeeper false-kill / false-pass calibration; (4) the §E guards catch hallucinated
  params *structurally*. **(v4 RE-CONFIRM, must close before E1):** **[M1]** ratify/amend the
  §G.1.1 refund accounting — `W_0`/`γ`/`φ`, full-vs-proportional refund, in-flight wealth state
  machine, the `n_trades ≥ 30` demo-confirm bar; **[M2]** ratify/amend §G.1.2 N_eff clustering +
  the single-N_eff wiring to **both** `dsr_gate` (`K_for_dsr = N_eff`) and the α-wealth debit (one
  debit/refund per cluster — no double-charge, no double-count); **[M3]** confirm whether
  `shift1_compliance` / `is_oos_gap` checks exist or must be built (today only the
  `name_pattern_check` `leakage_check.py` exists); **[M4]** ratify the §G.2.1 recall floor (≥0.85)
  + benchmark-set construction.
- **QC (data/backtest):** (1) leak-free PIT regime features feeding §E (ii); (2) beta-neutral
  + walk-forward in the math gate; (3) pre-registration prevents post-hoc spec mining;
  (4) bull-only / regime-bet labeling per Alpha Evidence Governance. **(v4 RE-CONFIRM / SIGN-OFF,
  must close before E1):** **[B1 — QC design sign-off required]** ratify/amend the §N.1
  `beta_neutral_check` deterministic spec: factor set (BTC-only vs BTC+altcap + the altcap basket
  construction), `WINDOW_DAYS` (≥90 default), `BETA_NEUTRAL_THRESHOLD` (0.15 default), and the
  down-market regime-label definition + `|β_down|` rule — **this is the alpha command-line; QC owns
  the final numbers**; **[B2]** confirm `MIN_FORWARD_OOS_DAYS = 21` and the "forward-OOS days"
  definition (post-pre-registration, PIT, not replayed history); **[Q1]** confirm the
  `N_trades_oos ≥ 50` math-gate step-0 DEFER bar; **[Q2]** confirm the cost-decomposition fields
  (`cost_edge_ratio`/`gross_edge_bps`/`total_cost_bps`) + `max_dd_duration_days` are computable from
  stored demo results; **[Q3]** confirm the §O.5 blind-window floor `N`.
- **E3 (security/deploy):** (1) fail-safe degrade-to-baseline never blocks trading
  (the iron rule) under fault injection; (2) sentinel locality (no cloud dependency for
  liveness); (3) resource isolation of research workers from the live engine (§K2: nice /
  cgroup / separate PG pool / off-peak) — must not starve the live engine on the shared box;
  (4) secret handling in D3 (never log tokens/prompts-with-secrets). **(v4 HIGH, must close before
  E1):** **[E1]** every new write endpoint (`/cost/reset`, `/cost/pricing`, Orchestrator/registry
  mutations) is **operator-scope** and unreachable from a read-only surface (§N.2); **[E2]** the D3
  **sanitize-before-persist** pass (§D.1.1) runs on the write path — inject a synthetic secret into
  prompt/response/`str(e)` and confirm the stored row carries `[REDACTED:*]`, never the secret, with
  no write-then-clean window.

---

## K-extra. Cost (AI-E) + Compute (E5) notes

- **AI-E (cost):** cloud $ spent only on math survivors (§G2); per-capability `budget` +
  `tier_gated_spend`; DOC-08 $2/day global cap holds unless a documented per-capability ROI
  rule raises it (open question #2). Ollama + local sentinels = $0.
- **E5 (compute):** research workers **resource-isolated** from the live engine — `nice` /
  cgroup CPU caps, **separate PG connection pool**, off-peak batch scheduling. Throughput
  bounded by `min(tier headroom, local compute headroom)`. **Must never degrade the live
  engine on the shared box** (E3 stress-test #3). This constraint caps Q1 parallelism.

---

## M. Feedback → rule pipeline (v2 change 4 — first-class process, not "remember to")

**Operator's core concern:** humans make mistakes and forget; the pipeline must be process-
driven so a forensic lesson **mechanically** becomes a durable improvement, never depending on
someone remembering to wire it. This is the closed loop that makes the mesh self-governing.

**Trigger:** any forensic conclusion — reached via §D.4 fault-localization, a §F.2 conflict
adjudication that went wrong, a bad advisory caught post-hoc, or an operator's manual review of
an `l2_reply_id`. From the GUI (the §H card feed or the §N packet), the human clicks **one
button: "promote this conclusion to a rule."** That opens a typed form with **exactly three
target types** (the only three places a lesson can land):

```
Forensic conclusion (carries l2_reply_id + gate-seam refs)
        │  one click: "promote to rule"
        ▼
   pick ONE target:
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │ ① NEW DETERMINISTIC GATE RULE                                                  │
   │    → drafts a candidate rule for a deterministic gate (e.g. out-of-bound guard │
   │      clause, governor clamp, FDR family split). Lands as a PROPOSED rule in     │
   │      research.gate_rule_candidates (NOT auto-active). Requires PA/CC review +    │
   │      a regression test before it becomes live policy. The point is it is        │
   │      CAPTURED and QUEUED, not lost — activation stays gated.                     │
   ├──────────────────────────────────────────────────────────────────────────────┤
   │ ② NOVELTY-FAILURE-LIBRARY PATTERN                                              │
   │    → writes a dead-mode row into agent.lessons (V133), tagged with the          │
   │      originating l2_reply_id, so the §E novelty gate will reject re-proposing    │
   │      this pattern. This one IS effectively immediate (it only ADDS a            │
   │      suppression — fail-safe direction, can't loosen anything).                 │
   ├──────────────────────────────────────────────────────────────────────────────┤
   │ ③ CAPABILITY AUTONOMY DEMOTE                                                   │
   │    → flips the capability toward more friction: demote its effective autonomy   │
   │      (e.g. force Conservative-style manual on its promotion lane, or disable     │
   │      auto-trigger, or `enabled=false`). Writes to the capability registry +      │
   │      the §O metric history. Demote is ALWAYS allowed without further gate        │
   │      (adds friction = fail-safe direction, root principle 6). This pipeline can  │
   │      ONLY demote — it has NO promote target at all. PROMOTE is never a feedback- │
   │      pipeline action; it can come only from a §O earned-trust candidate confirmed │
   │      by a human (v3 R2-1 §O.1). A §M one-off click can contract autonomy, never  │
   │      expand it — consistent with the universal "auto-contract / human-expand".   │
   └──────────────────────────────────────────────────────────────────────────────┘
```

**The asymmetry that keeps this safe:** ② and ③ (add suppression / add friction) are
**fail-safe-direction** and apply immediately — they can only make the system more conservative.
① (a new gate rule that could *change* behavior) lands as a **proposed, review-gated, test-
required** candidate, never auto-active. So the pipeline is fast where it's safe (tightening)
and gated where it could be wrong (new logic) — same asymmetry as §C.

**Graceful degradation if the ① queue stalls (v3 R2-6).** Because ② (suppression) and ③ (demote)
apply *immediately* and are the **safety-relevant** outputs, a backlog in the human review of
①-candidates **degrades gracefully**: safety is already protected (② and ③ have fired), and only
the **behavior-changing new rule ①** waits in the review queue. So a slow/absent reviewer **never**
holds back a safety contraction — it only delays adding *new* behavior, which is exactly where
delay is the safe choice. This is consistent with "the human is not a safety bottleneck": the
human gates *new logic* (correctly slow), never the *tightening* (already immediate). The ①-queue
is therefore allowed to grow without endangering the system; it is a backlog of *potential
improvements*, not of *pending protections*. (Open Q8 sets who reviews ① and on what SLA — but the
SLA governs how fast improvements land, not whether safety holds.)

**Provenance:** every rule/lesson/demote created this way stores the `l2_reply_id` (and gate-
seam refs) it came from, so the loop is itself auditable: "why does this gate rule exist?" →
the forensic conclusion → the originating L2 reply. This is the §D.2 chain extended into the
governance layer. CC owns reviewing ①-candidates; this section just guarantees nothing is lost.

---

## N. One-page live-cross packet (v2 change 5 — full content spec)

The rare, high-leverage human decision (cross a demo-proven candidate to live) must be **fast
and correct**, and — **v3 R2-4 — math-primary**: the human decides from the quantitative case, not
from a model verdict. The packet is a single screen / single API payload
(`GET /api/v1/l2/live_cross/{id}`) assembled deterministically from already-stored data — **L2 does
not author it as prose, and L2 does NOT recommend the live decision; it is a structured render** of
the math + provenance + live gate state, plus subordinate L2 *caveats* (no verdict) and an optional
NL summary the human can request. Exactly six blocks (block 5 is L2 caveats, **not** a verdict):

```jsonc
LiveCrossPacket {
  // 1. MATH EVIDENCE DIGEST — the quantitative case, deterministic, no model text
  math_evidence: {
    dsr, pbo, cscv_summary, deflated_sharpe, n_eff, walk_forward_oos_sharpe,
    gate_verdict: "PASS|FAIL|DEFER",            // [v4 Q1] DEFER if N_trades_oos < 50 (§G.2 step-0)
    n_trades_oos: int,                          // [v4 Q1] the sample the gate ran on
    // [v4 B1] beta_neutral_check is the DETERMINISTIC §N.1 computation, not L2-asserted:
    beta_neutral_check: {                       // §N.1 full spec
      passed: bool,                             // |residual_beta| < 0.15 (deterministic threshold)
      residual_beta: float,                     // from the ≥90d rolling factor model
      factor_model: "btc|btc+altcap",           // ≥ BTC beta; recommended two-factor
      window_days: int,                         // ≥ 90
      regime_conditional: {                     // [v4 B1] down-market re-check
        down_market_residual_beta: float, down_market_passed: bool }
    },
    // [v4 Q2] cost decomposition — 6 candidates died of edge<cost; the human MUST see it:
    cost_edge_ratio: float, gross_edge_bps: float, total_cost_bps: float,
    demo_result: {n_fills, net_edge_bps, win_rate, max_dd,
                  max_dd_duration_days: float,  // [v4 Q2] not just depth — duration
                  days_live_in_demo, forward_oos_days: float},  // [v4 B2] ≥21 to be auto-eligible
    regime_label_of_evidence: str, bull_only_flag: bool  // Alpha Evidence Governance honesty
  },
  // 2. COMPLETE PROVENANCE CHAIN — the §D.2 lineage, root → here
  provenance_chain: [
    { hop:"l2_reply",  id, capability_id, created_at, model },   // the originating reply
    { hop:"hypothesis", hid, mechanism, falsification_test },
    { hop:"variant",    variant_id },
    { hop:"replay",     run_id, stage0r_green:bool },
    { hop:"demo",       demo_run_id, source_l2_reply_id }
  ],
  // 3. NL SUMMARY — human-readable, generated ON REQUEST, ground truth always shown beside it
  nl_summary: str | null,   // "render to prose" button; never replaces the structured blocks
  // 4. CURRENT 5-GATE STATUS CHECKLIST — live, read from the real auth surface NOW
  five_gate_status: [
    { gate:"live_reserved",           status:"set|unset" },
    { gate:"operator_role_auth",      status:"present|absent" },
    { gate:"OPENCLAW_ALLOW_MAINNET",  status:"1|0" },
    { gate:"secret_slot",             status:"valid|missing" },
    { gate:"authorization.json",      status:"signed_unexpired|expired|absent", expires_at }
  ],
  // 5. L2 CAVEATS / RISKS-NOTED — v3 R2-4: NO cross/hold/reject verdict on the live crossing.
  //    L2 contributes only risks/caveats to consider; it does NOT recommend a live decision.
  //    Rendered SUBORDINATE to the math (block 1) and ONLY after the human acknowledges the math.
  l2_caveats: { risks_noted:[str], caveats:[str], confidence:float,
                dissenting_signals:[str] } | null,  // e.g. a §F.2 contract-conflict (tighten-now)
  math_ack_required: true,   // block 5 stays hidden/inert until the human acks block 1 (the math)
  // 6. THE ACTION — links to the EXISTING approve/Decision-Lease flow (no new live path)
  action_endpoint: "the unchanged 5-gate + Decision-Lease approval route"
}
```

**Design rules:** (1) blocks 1, 2, 4 are **pure deterministic renders** of stored facts — no
model in the path, so the human is reading ground truth, not a model's gloss. **(2) v3 R2-4 —
the live decision is math-primary; L2 gives NO live verdict.** v2 had block 5 emit a
`cross/hold/reject` verdict. On the **highest-risk action in the whole system (a live crossing)**
an L2 verdict would **anchor** a time-pressured human and brushes against "LLM must not drive
trading." So in v3 block 5 carries **only L2 caveats / risks-noted** (things to consider, plus any
§F.2 contract-direction dissent like "regime-risk says tighten now"), **never a cross/hold/reject
recommendation**. The **math evidence (block 1) + full provenance (block 2) + honest dissent are
the primary case**, and the human forms the cross/hold judgment from that **math-primary**
evidence — not from a model's verdict. Block 5 is rendered **visually subordinate to block 1** and
is **gated behind `math_ack_required`**: the human must first acknowledge the math block before the
(non-verdict) L2 notes render or can be acted on, so the math is read first and L2 can never be the
lead. (3) Block 4 is read **live at packet-open**, not cached, so the human sees the real current
gate state. (4) The action is the **unchanged** existing flow — the packet only *assembles the
case*; it adds no live authority. This is what makes the rare decision fast (everything in one
screen) **and** correct **and math-primary** (math + full lineage + honest dissent + live gate
truth, all grounded; L2 demoted to caveats). CC stress-test: the packet endpoint is read-only and
cannot itself approve, **and block 5 contains no `verdict`/`cross|hold|reject` field and never
renders ahead of (or unguarded by) the math block.**

### N.1 [v4 B1] `beta_neutral_check` — deterministic computation spec (`NEEDS QC RE-CONFIRM`)

**QC BLOCKER B1 — the single most important alpha close in v4.** This is the unattended-gate
command-line: the **down-market-beta masquerade** that has killed **5 candidates** is precisely a
strategy whose apparent edge is *short exposure to a falling market* re-labeled as alpha. On an
unattended gate, a loose or L2-self-defined beta check is exactly where that masquerade passes. v4
makes `beta_neutral_check` a **deterministic, repo-owned computation with fixed parameters** — **not
an L2-advisory field and not an L2-chosen threshold.** The L2/Orchestrator may *read* its result;
it may never compute or relax it. **This spec needs QC design sign-off (factor set / window /
threshold / regime rule) before E1.**

**(1) Factor model — at minimum BTC beta; recommended two-factor.**
```
default (minimum):   r_strategy_t = α + β_btc · r_btc_t + ε_t
recommended:         r_strategy_t = α + β_btc · r_btc_t + β_alt · r_altcap_t + ε_t
   where r_altcap_t  = return of a market-cap-weighted altcoin basket (ex-BTC), PIT-computed
```
The recommended two-factor model separates **BTC beta** from **broad-alt beta**, because several of
the dead candidates were *alt down-beta* not *BTC down-beta* — a BTC-only model would have scored
them "neutral" while they were simply short a falling alt complex. `r_altcap` must be a **leak-free,
point-in-time** cap-weighted basket (QC owns the construction; reuse the project's existing PIT
universe if one is available, §L). The estimated coefficient of interest is the **residual α**
(intercept); `ε_t` is the residual return.

**(2) Estimation window — ≥ 90 days rolling (NOT 30d).** β is estimated on a **≥90-day rolling**
window of aligned returns at the candidate's native bar. A 30d window is too short to separate a
genuine alpha from a regime-coincident beta (a 30d down-leg makes a short look like alpha); 90d
spans enough regime variation that a persistent residual-α is more credibly skill. (`WINDOW_DAYS =
90` default; QC may raise.) Insufficient history (< 90d aligned returns) → `beta_neutral_check` =
**DEFER**, never an auto-pass.

**(3) Threshold — deterministic `|residual_beta| < 0.15` (NOT L2-chosen).** The candidate passes
the beta-neutral check **iff** `|β_btc| < 0.15` **AND** (two-factor) `|β_alt| < 0.15` on the ≥90d
window. `BETA_NEUTRAL_THRESHOLD = 0.15` is a **deterministic constant in the gate**, not a value any
capability proposes. A residual-α that only exists when `|β| ≥ 0.15` is **beta, not alpha**, and is
**rejected** (this is the exact gate that would have killed the 5 masquerade candidates).

**(4) Regime-conditional re-check under down-market (the masquerade-specific guard).** A candidate
can show `|β| < 0.15` *pooled* yet carry a large **down-market** beta that averages out against an
up-market leg. So v4 requires a **regime-conditional** computation: estimate β **separately on the
down-market sub-sample** (PIT regime label = down / high-drawdown bars, computed leak-free per
Alpha Evidence Governance — *not* from a future-looking label) and require **`|β_down| < 0.15`**
as well. A candidate that is beta-neutral on average but **`|β_down| ≥ 0.15`** is a down-market-beta
masquerade and is **rejected**. This sub-sample check is the direct, deterministic answer to "5
candidates died of down-beta dressed as edge."

**(5) Where it binds (one computation, three consumers).** The §N.1 result is computed **once**
deterministically and is consumed by **all three** of: (a) the §G.2 **math gate** (a candidate
failing §N.1 cannot pass the math gate — beta-neutral is a hard precondition, same tier as
DSR/PBO/leak), (b) the §N **live-cross packet** `math_evidence.beta_neutral_check` (so the human
sees the deterministic residual β + the down-market β + the factor model + window), and (c) the
§E(ii) regime-risk advisor's `portfolio_beta` input. No capability ever substitutes its own beta;
the L2 layer reads this value and cannot relax it.

**QC sign-off items (`NEEDS QC RE-CONFIRM`):** ratify or amend {factor set (BTC-only vs BTC+altcap;
the altcap basket construction), `WINDOW_DAYS` (≥90 default), `BETA_NEUTRAL_THRESHOLD` (0.15
default), the down-market regime-label definition + the `|β_down|` rule}. These four numbers are the
alpha command-line; QC owns their final values. PA's defaults are written concretely so QC's
re-confirm is an edit, not a blank.

### N.2 [v4 E1] Write-endpoint auth-hardening (operator scope — E3 HIGH)

**E3 HIGH E1.** The §N packet endpoint is read-only (already specified). But the mesh introduces
**write** endpoints — `/cost/reset`, `/cost/pricing`, the Orchestrator/registry mutation routes
(enable/disable a capability, edit budget, post a promote-candidate confirmation, demote) — and
every one of them **must require operator scope**, not be openly callable. v4 mandates:
- **All new Orchestrator / capability-registry / cost-config WRITE endpoints require operator-scope
  auth** (reuse the existing operator-role / TOTP-gated pattern from `governance_autonomy_service`
  / `governance_extended_routes`). Specifically `/cost/reset` and `/cost/pricing` are
  operator-scope writes.
- **Read endpoints stay read-only** (the §N packet `GET`, the §H card reads, the §O quality reads)
  — no auth escalation needed, and they **cannot mutate**.
- The **human-confirm promote** action (§O.1/§O.4) is an operator-scope write reachable **only** via
  this hardened route (this is also the C1 carbon-layer boundary — the only autonomy-raising writer
  is operator-gated).
- **E3 stress-test:** every write endpoint rejects an unauthenticated / non-operator caller; no
  write endpoint is reachable from a read-only surface. (§L E3.)

---

## O. Per-capability quality / ROI metric (v2 change 6 — defined; v3 R2-1/R2-2/R2-3 — promote is human-confirmed, de-Goodharted, sample-floored)

v1 named a "quality-metric" but never defined it. v2 defines it as the **closed-loop signal that
drives each capability's keep / demote automatically and *proposes* its promote**, so "selectively
enable by cost-benefit" becomes self-tuning instead of a manual judgment — **v3 (R2-1): the metric
auto-applies only the keep/demote/disable (contraction) side; promotion is a one-click human
confirmation the metric merely prepares, never an automatic metric action.** Stored per capability
in `learning.l2_capability_quality` (append-only history + a current rollup).

**Three measured dimensions (all derivable from D3 + the provenance chain + demo outcomes):**

| Dimension | Definition | Source | Role (v3) |
|---|---|---|---|
| **Post-hoc correctness** | of advisories that reached an outcome, fraction that proved correct (hypothesis → demo-confirmed; diagnosis → root cause confirmed; tighten → drawdown actually avoided) | provenance chain §D.2 → demo/incident outcome | **PRIMARY promote driver; primary demote driver** |
| **Cost vs value** | $ spent on this capability (D3 `cost_usd` sum) vs realized value (demo-confirmed edge $ / incidents caught early / false-alarms avoided) | D3 cost + outcome join | **PRIMARY promote driver; cost>value → demote** |
| **Adoption rate** | fraction of this capability's advisories a gate/applier/human accepted (vs rejected/clamped/ignored) | gate-seam log §D.3 (`verdict`) + human accept/reject | **weak tiebreak only — EXCLUDED from the promote decision (R2-2, Goodhart-prone)** |

**Rollup → autonomy action (deterministic policy, no model judgment) — v3 rewrites both the
signal weighting (R2-2) and what PROMOTE is allowed to do (R2-1):**
```
# PROMOTE-eligibility signal (de-Goodharted, R2-2): correctness + value, NOT adoption.
promote_signal = w_corr·post_hoc_correctness − w_cost·(cost / value)   # adoption NOT in this term
   over a rolling window with a minimum-sample floor (R2-3: below N outcomes → never promote-eligible)

   # --- the EXPANSION direction (R2-1): METRIC PROPOSES, HUMAN CONFIRMS — never auto ---
   HIGH promote_signal & sustained & sample ≥ floor
                      → emit a PROMOTE-ELIGIBLE CANDIDATE (NOT an auto-action):
                        a one-click "earned-trust" item in the operator inbox (§H card / §M-style
                        button) carrying the evidence digest. A HUMAN confirms it to remove the
                        §C.1 demo-promotion trust-gate. *No metric ever removes a trust-gate or
                        widens auto-scope on its own.* (See §O.1.)
   MID                → KEEP as-is.

   # --- the CONTRACTION direction: AUTOMATIC (fail-safe), independent of adoption ---
   LOW post_hoc_correctness  OR  cost > value
                      → DEMOTE automatically: add friction (force manual / disable auto-trigger);
                        if it stays LOW → recommend `enabled=false` (auto-applied only in the
                        disable direction). adoption is NOT required for demote (R2-2).
   negative value     → auto-DISABLE candidate (cost with no edge — root principle 13).
   sample < floor     → may DEMOTE/DISABLE on a single clearly-bad outcome; may NEVER promote (R2-3).
```

### O.1 PROMOTE is human-confirmed; the metric only prepares the decision (R2-1 — load-bearing)

v2 let a sustained-HIGH score **auto-remove** the §C.1 human trust-gate. Removing a trust-gate is
an **expansion of what the system does automatically** — i.e. an `expand` action — so doing it
automatically **violated §C.2 "expand=human"** and was the design's last self-expanding back-door
(the system enlarging its own autonomy without a human). **v3 makes the metric's role advisory in
the expansion direction:** a HIGH-and-sustained score does **not** remove any gate; it emits a
**promote-eligible candidate** — an earned-trust evidence digest (the correctness/cost-value
record + the provenance of the advisories that earned it) plus a **one-click confirm** — into the
operator's inbox. **A human confirms the promotion.** The metric's job is to make that decision
**near-zero-effort** (everything pre-assembled, one click), **not** to make it disappear. This is
exactly "the human's limits must not become the bottleneck" done **without** letting the system
self-expand: the human stays in the expansion loop but the cost of being there is driven to a
single click.

**The asymmetry, now truly universal (the heart of v3):**
- **PROMOTE / any autonomy expansion / any trust-gate removal → HUMAN-CONFIRMED, always.** Metric
  may *propose* (one-click candidate); only a human *expands*. No tier, no posture, no metric, no
  feedback path may auto-expand. This now covers **autonomy itself**, not just lanes.
- **DEMOTE / any autonomy contraction / adding friction → AUTOMATIC, always** (fail-safe direction,
  root principle 6). Metric, feedback (§M-③), and fail-safe (§F) may all auto-contract.

This re-aligns with the repo's verified `_AUTONOMY_PATH_MATRIX`: promotion rows (a)/(c)/(d) are
`operator manual` at level1 and only become `auto with fail-safe` at level2 — **and the only thing
that flips level1→level2 is a human setting the posture switch (TOTP-gated), never a metric.** v3's
promote-eligible candidate is the natural extension: the metric earns the *right to ask*, the human
*grants* it. CC stress-test (updated): **there is no code path where the §O metric (or any
automatic signal) removes a trust-gate, widens an auto-applicable lane, or raises effective
autonomy without a human confirmation event.** The only automatic autonomy movement is *downward*.

### O.2 De-Goodharting the promote signal (R2-2)

`adoption` measures "how often the gate/human accepted this capability's advice" — which is mostly
**agreement with the existing gate**, and is **Goodhartable**: a capability that learns to echo the
gate's likely verdict (compliant but adding no information) can run its adoption up without being
*useful*. If adoption drove promotion, the system would reward sycophancy. **v3 therefore drives
promote-eligibility from `post_hoc_correctness` (did the advice prove right against a real
outcome?) + `cost-value` (did it pay for itself?)**, the two dimensions that are **outcome-grounded
and hard to fake** (you cannot fake a demo-confirmed discovery or an actually-avoided drawdown).
**`adoption` is demoted to at most a weak tiebreak and is excluded from the promote decision.**
Conversely, **DEMOTE keys on low correctness OR cost>value, independent of adoption** — a
high-adoption but low-correctness capability (the exact sycophancy failure) **demotes**, it does not
get protected by its adoption. This makes "obedient score-farming → wrongful promotion"
**structurally impossible**, while keeping the cost-benefit auto-disable loop intact.

### O.3 Low-sample asymmetry (R2-3)

Low-frequency capabilities (incident-diagnosis fires rarely; a niche regime advisor) may take a long
time to accumulate `N` outcomes, so their metric is slow and noisy. The danger is letting a thin,
lucky sample **drive an expansion**. **v3 rule (matches the universal asymmetry):**
- **Below the sample floor → NEVER promote-eligible.** No promote-candidate is emitted until the
  capability has ≥ N outcomes. Sparse evidence keeps the conservative (junior) posture; the human
  trust-gate stays. Small samples never expand autonomy.
- **A single clearly-bad outcome may still DEMOTE / DISABLE**, regardless of sample count
  (fail-safe direction). One bad incident-diagnosis that would have caused harm is enough to add
  friction or disable, even at n=1.

So sample-size gates *expansion* (strict, needs N) but never gates *contraction* (one bad outcome
suffices). Low frequency can only ever make a capability **more** conservative, never auto-promote
it. (Operator open Q7 updated: set N — the promote sample floor — strict; a low-frequency capability
that wants more autonomy earns it the slow honest way or stays junior.)

**The two closed loops this completes (v3 form):** (1) **promotion** is *earned and
human-confirmed* — a sustained-HIGH **correctness/value** score (not adoption, R2-2; not below
floor, R2-3) emits a one-click candidate that **a human confirms** (R2-1); never a metric acting
alone. This is the mechanical answer to "the human shouldn't be a permanent bottleneck" **without**
self-expansion — the human's cost shrinks to one click, the human's authority over expansion does
not. (2) **cost-benefit enable** is *self-correcting downward* — a capability that costs more than it
returns demotes then disables itself **automatically** (root principle 13). The metric is the input
to the **promote-candidate** (§O.1, human-confirmed) and to the **§M-③ auto-demote**; **promote is
human-confirmed-only, demote/disable is automatic.** CC stress-test: the §O metric can **auto-move
autonomy only in the demote/disable direction**; every promote / trust-gate-removal / autonomy
expansion requires a human confirmation event and can come **only** from a confirmed promote
candidate (never a manual flag bypassing the candidate, never feedback/§M, never a raw metric
threshold auto-applying).

### O.4 [v4 C1] The promote-candidate is a READ-ONLY inbox row; the Orchestrator cannot promote

**CC HIGH C1 — carbon-layer enforcement of R2-1.** §O.1 says the metric "emits a promote-eligible
candidate" the human confirms. v4 specifies the **mechanism** so there is no code path by which the
metric (or the Orchestrator) actually raises autonomy:

- The §O HIGH branch writes a row into a **new read-only inbox table `learning.l2_promote_candidates`**
  `(candidate_id, capability_id, evidence_digest jsonb, promote_signal, sample_n, created_at,
  status ∈ {pending|confirmed|dismissed|expired})`. Writing this row is the **only** thing the
  metric does in the expand direction. **This table is not a tier/gate; nothing reads it to change
  behavior automatically.**
- **The Orchestrator and the §O metric module have NO import of and NO call to**
  `LearningTierGate.promote_tier` (verified to auto-promote L1→L4 without `approved_by`,
  `learning_tier_gate.py:520/550-553/570-574`), nor any other writer that raises tier / removes a
  trust-gate / widens an `expand` lane. The promote-candidate is *data*, not an *action*.
- **Promotion happens only from the existing operator route.** A human reviews the candidate in the
  §H card / inbox and confirms via the **operator-scope, TOTP-gated** handler (the
  `governance_extended_routes` / `governance_autonomy_service` posture-switch pattern, §N.2). That
  handler — and **only** that handler — flips the candidate to `confirmed` **and** performs the
  actual gate-removal / promotion (it may call `promote_tier` *because it is the human-confirm path*).
  The candidate's `status` transition `pending→confirmed` and the promotion are one operator action.
- **CC E2 grep proof (the linchpin test):** in the Orchestrator + §O modules, `grep` returns **zero**
  hits for `promote_tier` / `set_autonomy_level`-style raisers / any trust-gate-removal writer; the
  **only** callers of those raisers are inside the human-confirm operator route. Every automatic
  writer touching autonomy moves it **down** (demote/disable) only. (§L CC stress-test 15.)

This makes R2-1 ("expand=human, closed under autonomy itself") true **in code**, not just in prose:
the system literally lacks a function call by which an automatic signal raises its own autonomy.

### O.5 [v4 Q3] Cold-start blind-window protocol (`N_outcomes < floor`)

**QC HIGH Q3.** Before a capability has accumulated the §O sample floor of real outcomes, its
post-hoc-correctness is **unmeasurable** — the metric is blind. v3 already forbids *promotion* in
that window (R2-3); v4 adds the **operating protocol** for the blind window so it is handled
honestly rather than silently:

- **Human-review proxy correctness.** While `N_outcomes < floor`, the §O metric records a
  **proxy-correctness signal sourced from explicit human review** of that capability's advisories
  (the operator/PA marks sampled advisories correct/incorrect in the §H card). This proxy is **clearly
  labeled as human-review proxy, not measured post-hoc correctness**, and it **cannot** drive a
  promote-candidate (R2-3 — below floor, never promote-eligible). It exists so the blind window is
  *observed*, not dark.
- **GUI "blind window" warning.** The §H capability card shows a prominent **"blind window —
  N_outcomes = k / floor = N; metric not yet trustworthy"** badge while below floor, so the operator
  never mistakes a thin/lucky early signal for an earned track record.
- **Raised manual-audit cadence.** While in the blind window, that capability's advisories are
  **audited manually more frequently** (a higher human-sampling rate than a mature capability), and
  it stays at the conservative junior posture (the §C.1 human trust-gate remains; demo auto-promotion
  is unavailable — also blocked independently by §C.3's forward-OOS bar). A **single clearly-bad
  outcome still demotes/disables** even at `n=1` (R2-3 fail-safe direction).
- **Exit.** The window closes when `N_outcomes ≥ floor`; only then does measured post-hoc-correctness
  replace the proxy and a promote-candidate become *possible* (still human-confirmed, §O.1).

---

## Summary verdict (v4-final)

The L2 Advisory Mesh is **mostly the completion of an already-half-wired system**:
LearningTier (wired), autonomy path matrix (wired), AI-lineage discipline (precedent),
hidden-OOS / lessons / residual registries (DB built), **and the ML pipeline (wired — the first
capability's attach surface)**. The **net-new core is small and sharp**: the D3 `agent.l2_calls`
full-audit ledger (V134, build #1) **now carrying a full reply→hypothesis→strategy→demo→live
provenance chain**, the `L2AdvisoryOrchestrator` conductor, the versioned PromptContract/output-
schema registry with deterministic out-of-bound guards, and the online-FDR α-wealth controller.

**What v2 adds beyond v1 is the *closed-loop discipline* that makes the mesh self-governing:**
(1) autonomy is **derived from (lane + tier + posture)** — one truth source, the `autonomy_level`
knob deleted, the tighten/loosen asymmetry a **typed `LANE_DIRECTION` invariant the loader
enforces**; (2) the first capability is the **ML hypothesis/diagnosis advisor on the existing ML
pipeline** (operator's choice, lowest-blast advisory surface); (3) a **feedback→rule pipeline**
turns forensic conclusions into gate-rule-candidates / lessons / demotes so nothing depends on a
human remembering; (4) a **per-capability quality/ROI metric** mechanically drives **auto-demote**
and **proposes** a human-confirmed promotion so "enable by cost-benefit" is a measured loop and the
human trust-gate is *shed by a one-click human confirmation*, not permanent and not auto-removed;
(5) trigger **debounce/dedup/coalesce** and (6) deterministic **conflict adjudication**
(deterministic > advisory, contract > expand) close the storm and tie-break gaps.

**What v3 (round 2) adds is a stricter, now-truly-universal autonomy-expansion boundary:**
(R2-1) **autonomy PROMOTE is permanently human-confirmed** — the §O metric may only *propose* a
one-click earned-trust candidate; **no metric/tier/posture/feedback ever auto-removes a trust-gate
or raises autonomy** (only contraction is automatic). "expand=human" is now **closed under autonomy
itself** — the system can never bootstrap itself into doing more automatically. (R2-2) the promote
signal is **de-Goodharted** — driven by **post-hoc correctness + cost-value, not adoption**, so a
compliant-but-useless capability cannot score its way to promotion. (R2-3) **low-sample capabilities
can only ever contract** — below the floor, never promote-eligible, but still demotable on one bad
outcome. (R2-4) the **live-cross packet is math-primary** — **L2 gives no cross/hold/reject verdict**
on a live crossing (caveats only, subordinate to + gated behind the math), so the rare highest-risk
decision is made from the quantitative case, not anchored by a model. (R2-5) **provenance now reaches
live trades** — post-cross, live fills/outcomes carry `source_l2_reply_id`, so a live loss months
later traces to the originating reply. (R2-6) the **§M rule queue degrades gracefully** — safety
contractions are immediate; only new behavior waits on review.

**What v4-final adds is the E1-readiness the four reviews required — every named-but-underspecified
gate is now a deterministic, sign-off-backed rule, with the alpha command-line first:**
**[B1]** `beta_neutral_check` is a **deterministic computation** (≥BTC factor, rec. BTC+altcap; ≥90d
rolling window; `|residual_beta| < 0.15`; **down-market-conditional `|β_down| < 0.15`**) consumed by
the math gate + the live packet + the regime advisor — directly closing the **down-beta masquerade
that killed 5 candidates** (`NEEDS QC sign-off`). **[B2]** auto demo-promotion has a hard
**`forward_oos_days ≥ 21`** precondition, posture-independent — Stage 0R (in-sample) is necessary
not sufficient. **[C1]** the Orchestrator is **forbidden in code** from calling `promote_tier`
(verified to auto-raise L1→L4 with no `approved_by`); the metric writes only a **read-only
candidate inbox** and only the operator-scope human-confirm route promotes — R2-1 made true at the
carbon layer. **[C2]** `can_auto_deploy_to_paper` (True@all-tiers) is demoted to a capability-unlock
flag, never a demo posture decider. **[M1]** the online-FDR refund is precise (`W_0`, refund formula,
in-flight wealth state, `n_trades ≥ 30` demo-confirm bar; `NEEDS MIT sign-off`). **[M2]** N_eff is
computed from the variant cluster and wired so **one effective trial ⇒ one DSR K-slot and one
α-wealth debit** — no double-charge, no double-count (`NEEDS MIT sign-off`). **[M3]**
`leakage_check.py` is capped at `name_pattern_check`; a leak-free claim needs `shift1_compliance` /
`is_oos_gap`. **[M4]** the Ollama screen has a calibration SOP (recall floor ≥0.85 defines "loose").
**[Q1]** the math gate gets a `N_trades_oos ≥ 50` step-0 → **DEFER** below it. **[Q2]** the live
packet shows the cost decomposition + DD-duration. **[Q3]** a cold-start blind-window protocol
(proxy correctness + GUI warning + raised audit cadence). **[E1]** all new write endpoints are
operator-scope. **[E2]** D3 sanitizes secrets/`str(e)` before persist. **No new architecture, no new
authority, no new live path — v4 is spec-tightening on the four-reviewer-endorsed v3 skeleton.**

The safety thesis is unchanged and now **typed, universal, and deterministic at the alpha gate**:
**L2 proposes, deterministic gates + lane-bound appliers decide, humans own live, forensics, AND
every autonomy expansion** — with the asymmetry that `contract`/`neutral` auto and
`expand`/live/**autonomy-promotion** human, enforced in the loader + the (no-auto-promote, no
`promote_tier`-call) §O metric, not in prose; and with the **down-beta / in-sample / small-sample
masquerades closed by deterministic gate members (B1/B2/Q1)**, not by an LLM's judgment. The only
automatic movement of the autonomy frontier is *inward*. Worst-case failure is NO_ADVICE = today's
deterministic baseline. No new trading authority, no new live path. **Gating items before E1:
B1 (QC sign-off), M1 + M2 (MIT sign-off); everything else is design-decided.**

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--l2-advisory-mesh-design-draft.md
