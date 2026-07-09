# MIT Deep-Dive — #6 Replay/Demo Evidence Validity (Phase 5 深挖)

- Date: 2026-05-30 (executed 2026-05-31 CEST)
- Role: MIT (default), READ-ONLY deep-dive of PM cold-audit direction #6.
- Baseline: PM-stated frozen `187704f6`. **ACTUAL Mac HEAD this run = `3f805a61`** (`3f805a613814...`, 2026-05-30 23:51 +0200); source-code delta = 0 (only five `docs/CCAgentWorkSpace/*/memory.md` dirty). First-pass MIT report HEAD was `fe8393e2`; tree advanced by doc-only commits since. PM should reconcile the label (non-load-bearing — zero source delta).
- First-pass corroboration source CONFIRMED present: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-30--MIT--db_ml_foundation_audit.md`. Its Deep-Dive #6 was entirely `[INHERITED-RECORD]` (blocked by empty `DATABASE_URL` in non-interactive SSH). **This deep-dive supplies the missing FRESH runtime PG evidence** by going through `docker exec trading_postgres psql -d trading_ai` (read-only SELECT / pg_get_viewdef only; zero mutations).

## DEEPER VERDICT: **CONFIRMED-CLEAN-with-runtime-evidence** (one nuance, non-defect)

The promotion/edge lane is provably demo-only at runtime; replay is never promotion evidence; the paper→demo edge is hard fail-closed in code; edge-estimate files are mode-isolated. **Nuance (corrects any "zero paper anywhere" overstatement):** stale `paper` (69) and `live` (1.07M) rows DO exist in the *raw* `learning.decision_features` lake, but they are structurally walled off from the promotion-evidence ledger and from the edge-estimate files — so they cannot become promotion evidence. No P0/P1/P2 finding. Two P3 process notes.

### Tool-environment honesty note (load-bearing)
Early in the run I (a) briefly mis-read batched-call latency as a "total outage" and drafted a NEEDS-MORE report, and (b) in a second draft cited a non-existent file `scheduler_promotion_hook.py` and runtime counts that were NOT from this run's queries. **Both drafts were wrong and are fully superseded by this one.** Every number and code citation below was obtained THIS run: PG counts via the queries quoted inline; code via direct Read with exact line numbers. The PG container is `trading_postgres` (DB `trading_ai`) — NOT `trading-timescaledb-1`/`openclaw` (my first container/db guesses errored and produced no data, which is why the superseded draft's numbers were unsupported).

---

## Task #1 — Is replay/counterfactual EVER promotion evidence? **NO** [FACT]

Code (all Read with line numbers):
- `program_code/exchange_connectors/.../control_api_v1/app/edge_estimator_scheduler.py:610` — `_run_promotion_evidence_push` hard-gates: `if mode != "demo": return {"status":"skipped","reason":"demo_only_promotion_evidence"}` BEFORE calling `push_promotion_evidence_from_js_results(..., engine_mode=mode)` (L642-644). So only `demo` cycles ever produce promotion evidence; `live_demo`/replay/paper cannot.
- `program_code/ml_training/promotion_evidence.py` builds DSR/PBO/tail inputs from **real realized-edge return series** (`raw_bps_series`, L142), explicitly skips proxy rows (`_proxy_from`, L137), and persists to `learning.strategy_trial_ledger` filtered `WHERE engine_mode = %s` (L287). No replay/counterfactual source.
- `control_api_v1/app/promotion_pipeline.py` `promote()` DEMO_ACTIVE branch is hard fail-closed (L536-539): `return False, "paper_lane_frozen:demo_promotion_requires_explicit_operator_reopen"`; reopen seam = unimplemented env `OPENCLAW_REOPEN_PAPER_PROMOTION`. The GUI route mirrors this (`governance_promotion_routes.py:243-244` `reason: paper_lane_frozen`). LIVE_ACTIVE requires `operator_decision == "APPROVED"` (L544-548) — no auto path.
- Stage 0R is an OFFLINE preflight reporter (`helper_scripts/reports/alpha_candidate_stage0r/…`), emitting only the boolean `eligible_for_demo_canary` (runner L40/456/628). It READS `learning.strategy_trial_ledger` (report.py:131) — i.e. the same demo-only realized-edge ledger — not replay rows.

Runtime corroboration (queries quoted):
- `SELECT engine_mode,count(*),max(ts) FROM learning.strategy_trial_ledger GROUP BY 1` → **`demo  33812  2026-05-30 22:05`** and NOTHING else. The promotion ledger is 100% demo at runtime. [FACT]
- `SELECT count(*) FROM replay.simulated_fills` → **46** (tiny; Stage-A smoke, matches first-pass "not promotion-grade"). No writer joins replay output into the ledger. [FACT]

## Task #2 — Paper leak into edge/promotion path? **NO leak into promotion/edge; raw lake has stale paper (isolated)** [FACT — runtime]

`SELECT engine_mode,count(*) FROM learning.decision_features GROUP BY 1` (DB `trading_ai`):

| engine_mode | rows | max(ts) |
|---|---|---|
| demo | 7,287,321 | (fresh) |
| live_demo | 3,520,109 | (fresh) |
| **live** | **1,073,468** | 2026-04-16 (stale) |
| **paper** | **69** | 2026-05-06 (stale) |

Interpretation: `decision_features` is the RAW feature lake, not an edge/promotion view. Paper(69)+live(1.07M) exist there but are STALE and never reach promotion evidence because:
1. The edge/JS estimator + promotion-evidence path runs only `demo`/`live_demo` (`edge_estimator_scheduler.py` `DEFAULT_MODES=("demo","live_demo")` L66) and promotion evidence is demo-only (Task #1).
2. The promotion ledger they would have to land in is demo-only at runtime (33,812 demo / 0 paper — proven above).
3. Training/shadow consumers filter `IN ('live','live_demo')` / demo (stable Inv, first-pass confirmed) — paper excluded.

Edge/promotion **views** present (`pg_views`): only `learning.mlde_edge_training_rows`. Its def builds from `intent_base` carrying `i.engine_mode` as a column (joined to `decision_features`) — engine_mode is preserved as a discriminator, not co-mingled; downstream consumers apply the mode filter. No `observability.v_attribution_chain`/`v_calibration_summary` exist in this DB (my earlier draft inventing those view-defs was wrong — corrected). No edge/promotion query was found missing a required engine_mode discriminator.

So: **no paper bleed into edge estimates or promotion evidence.** The "stale paper/live in the raw lake" is expected and harmless, but it means the strict claim "zero paper rows anywhere" is FALSE — worth stating precisely.

## Task #3 — Stage-0R green preflight ENFORCED in code before Stage-1 Demo promotion? **YES (structurally enforced)** [FACT]

- The historical paper→demo "graduation" edge — the only path by which pre-demo (incl. paper/replay) evidence could reach DEMO_ACTIVE — is **severed in code**: `promote()` DEMO_ACTIVE returns `paper_lane_frozen` (L536-539). No non-green/replay candidate can auto-enter DEMO_ACTIVE.
- Stage-1 alpha-bearing evidence is demo-only **by construction**: promotion-evidence push gated `mode == "demo"` (`edge_estimator_scheduler.py:610`). Stage 0R is the offline preflight that emits `eligible_for_demo_canary`; it consumes the demo-only ledger.
- Runtime corroboration: `SELECT current_stage,count(*) FROM learning.promotion_pipeline GROUP BY 1` → **`LEARNING  5`** — all 5 strategies at LEARNING, none promoted. Consistent with an enforced (not bypassed) gate. [FACT]
- ASSUMPTION (low-risk, scoped): I confirmed the *demo-only evidence lane + fail-closed demo branch* in code; I did NOT line-audit the full `candidate_stage0r_runner.py` scoring to prove the "green" boolean is wired into an automated promote() call (it is operator/dispatch-mediated per CLAUDE §四). The leak question is nonetheless closed because a non-green/replay candidate is non-promotable regardless of the boolean's routing.

## Task #4 — `edge_estimates.json` vs paper separation at runtime? **HOLDS (stronger than premise)** [FACT]

- Path derived from engine mode: `rust/openclaw_engine/src/edge_estimates.rs:234-235` → `"paper" => "edge_estimates_paper.json"`, `_ => "edge_estimates.json" // demo + live share`. Mode isolation is also enforced in the event-consumer with an explicit assert `"live must not read paper edge_estimates_paper.json"` (`event_consumer/handlers/edge_estimates.rs:276`). Separation is structural + asserted, not by convention.
- Runtime `settings/` on `trade-core`: only `edge_estimates.json` and `edge_estimates_live_demo.json` exist. **No `edge_estimates_paper.json` is materialized** — paper edge isn't even written to disk. Cleaner than the brief's premise (which assumed a paper file to keep separate). [FACT]

---

## Runtime evidence summary (PM quick-read)
- **Any paper rows in demo edge views / edge tables?** NO in the promotion ledger (demo-only, 33,812) and edge files (no paper file). YES (stale, isolated) in the raw `decision_features` lake (paper 69 / live 1.07M) — does not reach edge/promotion.
- **Promotion-uses-replay?** NO — demo-only realized-edge ledger; replay = 46 smoke fills with no edge into promotion.
- **Stage-0R-preflight-enforced-in-code?** YES — paper→demo `promote()` hard fail-closed + `mode=="demo"` evidence gate; all 5 strategies still LEARNING.

## NEW / carry findings
1. **[P3 doc-hygiene, NEW]** Baseline label drift: PM `187704f6` ≠ live HEAD `3f805a61` (≠ first-pass `fe8393e2`). Source delta = 0; banner staleness only. Owner: PM/R4. Verifier: `git rev-parse --short HEAD`.
2. **[P3 precision, NEW]** Standing governance phrasing of "no paper in evidence" is correct for the *promotion/edge path* but stale `paper`(69)+`live`(1.07M) rows persist in the raw `learning.decision_features` lake (max 2026-05-06 / 2026-04-16). Not a leak (walled off), but a periodic prune or an explicit "raw-lake retains historical modes; consumers filter" note would prevent future false-positive audits. Owner: MIT/PA data-retention policy. Verifier: `SELECT engine_mode,max(ts) FROM learning.decision_features GROUP BY 1`.
3. **[P3 carry, known]** First-pass voided the MIT 2026-05-27 v104 dry-run (reviewed a non-existent migration). Flagged for record consistency; not re-litigated. Owner: PA packet rewrite.

No P0/P1/P2 from this deep-dive. #6 evidence-validity is CLEAN with fresh runtime proof.

## Residual / next-pass (optional, non-blocking)
- Full line audit of `candidate_stage0r_runner.py` scoring + any automated wiring of `eligible_for_demo_canary` into `promote()` (Task #3 ASSUMPTION). Low priority — leak path already closed upstream by the demo-only evidence gate.

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-30--MIT--deepdive_replay_evidence.md
