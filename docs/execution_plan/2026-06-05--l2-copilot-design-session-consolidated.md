# L2 Copilot Design Session — Consolidated Background

Date: 2026-06-05
Status: Background reference for future plan/audit. Not a spec, not a TODO.
Purpose: capture the durable "why" behind the L2 Advisory Mesh so a future audit can read the
        rationale without re-deriving it — **filtered to what stays useful**, not a full transcript.

Primary artifacts (read these for the actual spec/roadmap):
- Design SSOT (v4-final): `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--l2-advisory-mesh-design-draft.md`
- Execution plan: `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md`
- Active authority: root `TODO.md` row `P1-L2-ADVISORY-MESH-TAILS`
- Historical ledger/reference: `L2_TODO.md` (repo root)
- Sibling (local sentinel basis): `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--watchdog_alert_wiring_design.md`

---

## 1. What set this direction — FinceptTerminal evaluation (catalyst)

A 6-agent deep read of FinceptTerminal (memory `project_2026_06_04_fincept_terminal_eval`)
concluded it is a Bloomberg-style **data terminal, not an execution engine**; AGPL-3.0 (cannot
copy source); its backtest/quant/execution/portfolio surfaces are all LOW value (pip-wrapper or
weaker than ours; "factor discovery" is marketing — `QLIB_AVAILABLE=False`). Only three things
were worth taking, and only as **ideas, not source**:
1. Polymarket/Kalshi free APIs = a non-price, non-beta independent signal axis (still must pass
   beta-neutralization + DSR as stage-0).
2. `finagent_core/agentic` — a Reflexion loop + cross-task lessons library + four-dimension
   budget gate + Voyager skills library (the *thinking*, not the code).
3. MCP ToolDef — exposing funding/OI/liq/CVD to L2 as typed tools.

**The load-bearing takeaway that produced the L2-copilot direction:** external projects are
strong on *integration breadth* but weak on *upstream alpha*; our edge must come from new data
axes + our own rigor, not from adopting a framework. This reframed L2 away from "another trading
signal source" toward an **advisory copilot** over our existing, already-rigorous pipeline.

This converges with the self-audit (memory `project_2026_06_04_external_framework_audit_and_self_
audit`): our position is **upstream-discovery weak, downstream-governance strong**. L2 should
amplify the strong half (governance/forensics/honest research throughput), not bolt on a weak
upstream.

---

## 2. L2 role redefinition

- **L2 evolves into a copilot, not a trading-signal emitter.** It produces *proposals* (feature
  hypotheses, leak/drift diagnoses, training-result interpretation, regime-risk caveats, incident
  runbooks), never effects. The boundary between proposal and effect is the **deterministic gate +
  lane-bound applier**, not a human reading every line.
- **Paper is retired** as a promotion-evidence lane (CLAUDE Hard Boundary; Stage-1 alpha-bearing
  promotion is Demo-only after a green Stage 0R replay). L2 inherits this — its research loop
  refunds α-wealth only on **demo-confirmed** discovery, never on a paper or gate-pass result.
- **L2 is manual-trigger today** (`POST /paper/layer2/trigger` → `run_session(trigger="manual")`,
  recommendation → `ShadowDecisionConsumer`, `is_simulated=True`). The mesh adds *gated* auto/
  scheduled/threshold triggers via the Orchestrator; the manual path stays.
- **Humans become the rare, high-leverage layer:** post-hoc forensics (provenance lookup), the
  live-cross approver (5 gates + Decision Lease), override/pause/kill, and **every autonomy
  expansion** (confirming a promote-candidate). The human is not an inline reviewer of research.

---

## 3. Design core decisions (the durable shape)

| Decision | What it is | Why it stays |
|---|---|---|
| **6 lanes + derived autonomy** | lanes = research/hypothesis/replay_0r/demo_stage1/risk_tighten/ml_backlog/ops_alert/none; `autonomy_level` is **derived from (lane + tier + posture)**, never stored | deletes the most dangerous misconfigurable knob; one truth source |
| **`LANE_DIRECTION` typed invariant** | each lane has `direction ∈ {contract, expand, neutral}`; loader-owned; `expand`→MANUAL checked first, non-overridable; no `lane: live` value exists | makes "no auto-path to live" a one-line CC-verifiable invariant, not an emergent property |
| **D3 provenance** | `agent.l2_calls` append-only ledger (full prompt+input+response+versions+tags) + full chain `source_l2_reply_id` reply→hypothesis→variant→replay→demo→live + gate-seam log + fault-localization protocol | upgrades "audit one call" to "trace a live consequence to its cognitive origin" (principle 8); sanitize-before-persist keeps it secret-free |
| **Human = post-hoc forensics + rare live approval** | humans own forensics, live-cross (unchanged 5-gate + Decision Lease), and every autonomy expansion (one-click confirm of a metric-prepared candidate) | "the human's limits must not become the bottleneck" — cost driven to one click, authority over expansion retained |
| **Q1 online-FDR** | `ResearchAlphaWealthController` (LORD/SAFFRON), conservative initial wealth, refund only on demo-confirmed discovery, family-partitioned by capability × signal-axis, N_eff cluster deflation shared with DSR | high-throughput honest research without "p-hacking at scale" |
| **Q3 cascade** | Ollama (generate + self-verify + loose coarse screen, recall ≥0.85) → deterministic math gate (the ONLY alpha validator) → cloud-L2 deep reason on math survivors only | cheap generate → math validate → expensive reason on survivors; LLM never validates alpha; cost spent only where it pays |
| **Q6 retention** | permanent-small (provenance index + lessons) / permanent-full (`consequential=true`) / hot→warm→cold (TimescaleDB native compression + drop_chunks, distill before drop) | value-driven, no bespoke archiver |
| **LearningTier fusion** | L2 capabilities slot onto the **already-wired** `LearningTierGate` L1-L5 + `TierCapabilities` flags (`can_generate_hypotheses` L3+, etc.); autonomy path matrix extended (not forked) | ~70% wiring of an already-half-built nervous system; ~30% net-new (D3, Orchestrator, contracts, FDR controller) |

**The single safety invariant:** L2 produces proposals, never effects; the only automatic
movement of the autonomy frontier is *inward* (auto-contract / human-expand), now closed under
autonomy itself.

---

## 4. Four-review outcome (the close that made it E1-ready)

Four adversarial reviews (CC compliance / MIT quant / QC data-backtest / E3 security) returned
**0 CRITICAL** and endorsed the v3 skeleton. v4 closed **2 BLOCKER + ~11 HIGH** spec-gaps before
E1 may start. Both BLOCKERs are folded into the design body and are now **closed**:

- **B1 (QC) — `beta_neutral_check` deterministic spec.** The unattended-gate command-line: the
  **down-market-beta masquerade that killed 5 candidates** is a short-a-falling-market exposure
  relabeled as alpha. v4 makes it a deterministic, repo-owned computation (factor model ≥ BTC,
  recommended BTC+altcap; ≥90d rolling window; `|residual_beta| < 0.15`; **down-market-conditional
  `|β_down| < 0.15`**) consumed by the math gate + live packet + regime advisor — L2 may read it,
  never compute or relax it.
- **B2 (QC) — forward-OOS demo precondition.** Auto demo-promotion has a hard
  `forward_oos_days ≥ 21`, posture-independent, applier-owned. Stage 0R (in-sample replay) is
  necessary-not-sufficient. B1 stops beta-masquerade from looking like alpha; B2 stops in-sample
  evidence from looking like forward alpha — the exact two ways the 5 dead candidates slipped.

The ~11 HIGH (folded, closed): CC C1 (Orchestrator forbidden in code from calling `promote_tier`,
which auto-raises L1→L4 with no `approved_by`) + C2 (`can_auto_deploy_to_paper` is unlock-only);
MIT M1 (FDR refund accounting) + M2 (N_eff single-debit) + M3 (`leakage_check.py` is
name-pattern-only, not leak-free PIT) + M4 (Ollama recall floor ≥0.85); QC Q1 (`N_trades_oos≥50`
DEFER) + Q2 (cost decomposition in packet) + Q3 (cold-start blind window); E3 E1 (write-endpoint
operator-scope) + E2 (D3 sanitize-before-persist).

**v3's structural strengths preserved verbatim into v4:** derived autonomy (§C.2), the typed
`LANE_DIRECTION` invariant, "expand=human closed under autonomy itself" (R2-1), the de-Goodharted
promote signal (R2-2, correctness/value not adoption), low-sample-can-only-contract (R2-3), the
math-primary live packet with no L2 verdict (R2-4), live-trade provenance (R2-5), graceful
rule-queue degradation (R2-6).

---

## 5. Gating and E1 acceptance (pointer)

Three re-confirms are **ENDORSED** (QC B1 / MIT M1 / MIT M2); their concrete FIX/NOTE are the E1
acceptance form and live in the design §L + the execution plan §1/§2:

- **B1 ENDORSE:** dual-factor BTC+altcap **mandatory** (BTC-only → DEFER); OLS at **daily/4h**
  (not 1m); down-market def = **30d drawdown >8% OR 7d return <-5%** (lagged-PIT, ≥30 bars else
  DEFER); NOTE `β+1.96·SE < 0.20`, 45/45d window stability, WF-OOS window not overlapping the beta
  window.
- **M1 ENDORSE:** φ=1.0 proportional refund; NOTE `debit_state` in persistent PG
  `research.alpha_wealth_ledger` (not in-memory); per-test `α_i ≤ α_target/min_batch_size` cap;
  docs distinguish `n_trades≥30` (refund) vs `N_trades_oos≥50` (math gate).
- **M2 ENDORSE:** average-linkage Pearson corr>0.5 cut; NOTE `max(1,N_eff)` guard (K=0 raises),
  `max_variants_per_cluster` anti-abuse, `dsr_gate` `n_trials` interface already compatible.

Build order (design §J / plan §2): **D3 foundation → Orchestrator+registry+contracts+guard →
local sentinel (parallel) → ml_advisory → online-FDR loop → feedback/quality + GUI.** Each phase
green-gated; promotion-relevant verdicts gated on B1 (QC sign-off); the FDR loop gated on M1 + M2
(MIT sign-off). Everything else is design-decided. No new architecture, no new authority, no new
live path — v4 is spec-tightening on the four-reviewer-endorsed skeleton.

---

## 6. What this is NOT (scope guard, for future audit)

- Not a new trading agent (Orchestrator is a conductor, principle 15 — no order/lease authority).
- Not a new live path — live crossing stays the unchanged human + 5-gate + Decision-Lease flow;
  the post-cross `source_l2_reply_id` is audit-only.
- Not an LLM alpha validator — the deterministic math gate (DSR/PBO/CSCV/leak/beta-neutral/
  walk-forward + FDR) is the only validator; the LLM generates and (post-math) interprets.
- Not a bull-data alpha proof — bull-heavy/rally-only results are `regime-bet/learning-only` per
  Alpha Evidence Governance; news/X/Reddit agents are corroborating context only, never the main
  signal.
