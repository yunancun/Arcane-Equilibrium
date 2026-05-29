# PA IMPL Spec — Cold Audit Package C: Evidence & Promotion Gates

Date prefix: `2026-05-29` (Europe/Madrid).
Repo root: `/Users/ncyu/Projects/TradeBot/srv`. HEAD baseline ~`b93d3210` on `main`.
Role: PA(default). Mutation scope: this report file only.
Source baseline: validated fix plan `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--cold_audit_validated_fix_plan.md` (Parallelizable Fix Section 4 "Evidence and promotion package"); CLAUDE.md §四 paper-lane-freeze boundary.

Findings covered: **P1-09, P1-10, P1-11, P1-16, P2-01, P2-05, P2-06, P2-07**.

This is a design/spec deliverable only. No impl code, no migration applied, no deploy, no TODO/memory/TOML/secret edits. `cargo`/`psql` empirical verification is Linux-authoritative (`ssh trade-core`); Mac mock pytest cannot catch PG/runtime semantics.

---

## 0. PA Source Recheck Record (read-only)

| Finding | Recheck evidence |
|---|---|
| P1-09 | `edge_estimates.rs:80-124` (`_meta.updated_at` parsed for `grand_mean_bps` only — NOT into struct, no TTL field exists); `CellEstimate` (`:20-42`) has `validation_passed` parsed (`:104-107`) but `runtime_bps.or(shrunk_bps)` fallback (`:91-94`); `gates.rs cost_gate_live_with_slippage:240-272` matches only `cell.shrunk_bps > 0.0`, **never reads `validation_passed` or freshness**. `edge_estimates.json:3` `updated_at=2026-04-20` (>1yr stale), legacy cell has no `runtime_bps`/`validation_passed`. Defect real: a positive legacy `shrunk_bps` with no `runtime_bps`/`validation_passed` and a stale snapshot passes the live gate. |
| P1-10 | `promotion_pipeline.py promote():518-521` `target==DEMO_ACTIVE` calls `_check_paper_gates(entry)` over `paper_*` metrics — this **is** the PAPER_SHADOW→DEMO_ACTIVE transition. `governance_promotion_routes.py:236-243` active route exercises it. `tests/test_promotion_pipeline.py:142-144` happy-path asserts `ok` on paper→demo. |
| P1-11 | Validated plan line 73: PA runtime `to_regclass('learning.close_maker_audit') = MISSING`. **NEW PA call-path proof**: close-maker evidence is persisted as **columns on `trading.fills`** (V094 `close_maker_attempt BOOL` + `close_maker_fallback_reason TEXT` 10-enum CHECK + partial index `idx_fills_close_maker_attempt_v094`); writer = Rust `commands.rs:659 apply_confirmed_fill_with_close_maker_audit` → `step_4_5_dispatch.rs:891/1373`; readers = `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py` (`FROM trading.fills ... WHERE close_maker_attempt=TRUE` at `:239,263,333,378,459,499`) + healthchecks `[62][63][64][66][71]`. The `learning.close_maker_audit` table has **no writer or reader in source**. |
| P1-16 | `helper_scripts/alpha_tournament/attribution_daily.py:283-299` is an explicit **W2-B scaffold**: `main()` logs `"Sprint 2 W2-B scaffold"` warning, emits `status="wire_up_pending_w2f_pa"`, `cumulative_n_fills=0`, `min_sample_gate_pass=False`, then `return 0`. Exit-0 with zero candidate data = false-evidence risk if a caller treats exit-0 as Stage B pass. Module header already SELECT-only / no PG write. |
| P2-01 | `backtest_engine.py:1-13` self-labels `STUB`, `run()` returns zero-filled `BacktestResult(warning="backtest stubbed — run in Rust openclaw_core::backtest")`. But `backtest_routes.py:358` auto-injects TruthSourceRegistry when `result.sharpe_ratio > 1.0 and result.total_trades >= 10` with **no stub guard**. Currently dead (stub zeros never satisfy), but one mis-wire leaks stub zeros into the evolution learning plane (principle 12). |
| P2-05 | `helper_scripts/cron/ml_training_maintenance.py:57` `DEFAULT_TRAINING_ENGINE_MODES = "demo"` vs `:58` `DEFAULT_SHADOW_ENGINE_MODES = "demo,live_demo"`. Training demo-only by intent; live_demo only shadowed. |
| P2-06 | Validated plan: `observability.drift_events=0`, `observability.model_performance=0`; writer `helper_scripts/cron/feature_baseline_writer_cron.sh` + `canary_promoter.py`. |
| P2-07 | `helper_scripts/cron/m11_replay_runner_daily_cron.sh` DESIGN-FIX header (2026-05-29) confirms Stage A smoke-only + zombie-row risk; Stage B nightly cohort wrapper does not exist (see PA 2026-05-28 m11 schedule proposal). |

---

## 1. P1-09 — Edge cost gate accepts stale/legacy/unvalidated edge (E1 Rust, HIGH)

### Contract: positive production edge freshness gate

Define the **production edge admission contract** (applies to `cost_gate_live_with_slippage` and the demo positive branch `gates.rs:170-190`; demo cold-start exploration and deep-negative blocking are unchanged):

A cell with `shrunk_bps > 0.0` may **pass** a production (demo/live) cost gate only if ALL hold:
1. **Fresh**: `_meta.updated_at` is present and parses, and `now - updated_at <= EDGE_TTL`.
2. **Runtime-derived**: the cell's bps came from `runtime_bps` (not the legacy `shrunk_bps` fallback). Add a `from_runtime_field: bool` to `CellEstimate` set true only when the JSON key `runtime_bps` was present.
3. **Validated**: `cell.validation_passed == true`.

If `shrunk_bps > 0.0` but any of (1)(2)(3) fails → **fail** the positive branch.

### Fail vs defer behavior (PA decision)
- **Live**: fail-closed → reject (root principle 5/6). New `RejectionCode::CostGateJsLiveStaleOrUnvalidated { age_secs, has_runtime, validated }`.
- **Demo**: **defer to exploration**, NOT reject. A positive-but-unproven cell is treated like the existing low-sample exploration branch (`gates.rs:156-168` semantics): allow with `tracing::info` `cost_gate(JS-demo): positive edge unproven — exploration mode`. Rationale: demo is the learning data source (memory `feedback_demo_loose_live_strict_policy`); fail-closing demo on unvalidated-positive recreates the Phase 5 dead-loop. Negative-edge demo blocking is untouched.
- Demo cold-start (cell missing) stays allow-with-warning; live cold-start stays reject. Unchanged.

### TTL value
`EDGE_TTL = 48h`. Rationale: producer `edge_estimator_scheduler` refreshes hourly and `reload_edge_estimates` daemon reloads 1h (`event_consumer/handlers/edge_estimates.rs:11-13`); 48h tolerates a one-day scheduler/cron outage + weekend gap before a fresh-but-positive cell silently keeps authorizing live. Make it a `risk_config.slippage.*` field (`edge_estimate_ttl_secs`, default 172800) so it is runtime-tunable per Rust-config authority, NOT a literal.

### Interface changes
- `edge_estimates.rs`: parse `_meta.updated_at` (RFC3339 → epoch secs) into a new `EdgeEstimates.updated_at: Option<i64>` field (both `load_from_file` and `load_from_str`). Add `from_runtime_field: bool` to `CellEstimate`, set in both parse loops (`:91-94` and `:162-166`). Add `pub fn updated_at(&self) -> Option<i64>` and `pub fn is_fresh(&self, now: i64, ttl: i64) -> bool` (None updated_at → not fresh).
- `gates.rs`: in the positive branch, before threshold compare, evaluate freshness+runtime+validated; route to reject (live) / exploration (demo) per above. Freshness read via `self.edge_estimates.is_fresh(...)`; `now` from existing pipeline clock source (verify how gates obtains time — if none, thread a `now_secs: i64` param from the caller rather than calling wallclock inside the gate, to keep the gate pure/testable).

### Owner / E1 implements
E1 Rust. Add `from_runtime_field` + `updated_at` parse + `is_fresh`; gate-branch admission logic; new RejectionCode; TTL config field wired through `RiskManagerConfig.slippage`.

### Tests (cargo, Linux-authoritative)
- `edge_estimates.rs`: `updated_at` parses RFC3339; missing `_meta.updated_at`→None; `from_runtime_field` true only when `runtime_bps` key present (extend existing `test_runtime_bps_overrides_positive_shrunk_bps`).
- `gates.rs` (mirror existing `cfg(test)` gate tests): positive+fresh+runtime+validated → pass; positive+stale → live reject / demo exploration; positive+legacy-shrunk-only (no runtime field) → live reject / demo exploration; positive+`validation_passed=false` → live reject / demo exploration; negative and cold-start branches unchanged (regression).

### Acceptance
Stale (`updated_at` older than TTL), legacy-only (`shrunk_bps` without `runtime_bps`), or unvalidated positive edge cannot pass the **live** cost gate; demo routes them to exploration not reject; current negative snapshot behavior unchanged; TTL is config-driven.

---

## 2. P1-10 — Paper→demo promotion stays frozen (E1 Python + TW, HIGH)

PM pre-decision: **paper lane STAYS FROZEN**. No `PAPER_SHADOW → DEMO_ACTIVE`. Approach = **freeze the transition at the gate, not delete the stage enum** (the enum/history rows and LIVE_PENDING/LIVE_ACTIVE machinery are still referenced and must keep compiling).

### Interface change (single chokepoint)
`promotion_pipeline.py promote()` — the `elif target_stage == PromotionStage.DEMO_ACTIVE:` branch (`:518-521`): replace the `_check_paper_gates` call with a hard freeze:
```
return False, "paper_lane_frozen:demo_promotion_requires_explicit_operator_reopen"
```
This is the single authoritative chokepoint — `check_paper_graduation` (`:454-469`) may remain as a read-only eligibility reporter but must NOT be a promotion path. The route `governance_promotion_routes.py:236-243` already calls `gate.promote()` after its pre-check, so freezing `promote()` is sufficient; additionally short-circuit the route's `paper_graduation` pre-check block to return `promotion_blocked` with reason `paper_lane_frozen` so the GUI shows the freeze explicitly rather than a generic gate failure.

Keep a single env/operator reopen seam documented in the comment (e.g. `OPENCLAW_REOPEN_PAPER_PROMOTION` — NOT implemented now, just named) so a future explicit operator decision has one place to flip, matching CLAUDE.md §四 "unless a future explicit operator decision reopens it".

### Owner / E1 implements
E1 Python: freeze `promote()` DEMO_ACTIVE branch + route pre-check message. TW: doc the freeze in the promotion-pipeline module docstring (the `LEARNING -> PAPER_SHADOW -> DEMO_ACTIVE` header line is now aspirational/frozen — annotate).

### Tests (pytest)
- **Rewrite the happy-path** `test_promotion_pipeline.py:125-154`: paper→demo must now assert `not ok` and `"paper_lane_frozen" in msg`; continue the LEARNING→PAPER_SHADOW and demo→live_pending coverage by seeding the entry directly at DEMO_ACTIVE (bypassing the frozen transition) so downstream stages stay tested.
- **New regression** `test_paper_cannot_promote_demo`: register → LEARNING→PAPER_SHADOW → set paper metrics that would have passed the old gates → assert `promote(..., DEMO_ACTIVE)` returns `(False, "paper_lane_frozen...")`. This is the explicit "paper cannot promote demo" guard the fix plan requires.
- Route test: POST promote target DEMO_ACTIVE from PAPER_SHADOW returns `promoted=False, reason=paper_lane_frozen`.

### Acceptance
No code path moves a strategy PAPER_SHADOW→DEMO_ACTIVE; happy-path test no longer asserts paper→demo success; regression proves the freeze; one named reopen seam exists for a future operator decision.

---

## 3. P1-11 — close_maker_audit: amend spec, do NOT create the table (TW + PM doc; NOT migration)

### PA recommendation: **`trading.fills` columns are canonical — amend the spec, retire the `learning.close_maker_audit` requirement.**

**Rationale (call-path proof in §0):** the entire close-maker evidence pipeline already exists and is wired end-to-end on `trading.fills`:
- Writer: Rust `commands.rs:659` populates `close_maker_attempt` / `close_maker_fallback_reason` per confirmed fill.
- Schema: V094 (applied — Guard A/B/C + 10-enum CHECK + partial index).
- Readers: `checks_close_maker_audit.py` + canary healthchecks `[62][63][64][66][71]` all `SELECT ... FROM trading.fills WHERE close_maker_attempt=TRUE`.

A separate `learning.close_maker_audit` table has **zero writer and zero reader in source**. Creating it would be a dead table (anti-pattern: dead schema; violates "no fake/empty evidence lane"). The MISSING `to_regclass` is therefore a **stale spec/TODO artifact**, not a real gap.

### What changes (TW + PM, doc-only)
- Mark the `learning.close_maker_audit` requirement **SUPERSEDED by V094 fills-column persistence** in whatever spec registered it.
- TODO `P1-LEARNING-CLOSE-MAKER-AUDIT-TABLE-MISSING` (TODO.md — PM owns, PA does not edit TODO): reclassify from "table missing" to "spec drift resolved: canonical = trading.fills V094 columns; close as not-a-bug".
- Add a one-line cross-ref in the close-maker spec pointing readers at `checks_close_maker_audit.py` + V094 as the canonical evidence surface.

### If PM rejects the amendment (fallback, operator-deploy-gated)
Only if PM insists on a dedicated table: spec a `learning.close_maker_audit` migration `V###` (next free number; Guard A schema-exists, Guard B type drift, Guard C index) **plus** a Rust/Python writer wiring it from the same `CloseMakerFillAudit` struct + a healthcheck. **MIT must do a Linux PG empirical dry-run before sign-off; APPLY is operator-deploy-gated (forbidden here).** PA does not recommend this path — it duplicates a working lane.

### Acceptance
Either: spec/TODO reclassified to point at `trading.fills` V094 columns as canonical (recommended); or a fully-wired (writer+reader+healthcheck) migration spec'd with MIT dry-run gate. No empty/dead table created.

---

## 4. P1-16 — Alpha Tournament / M11 doc-status split (TW + PM doc; E1 scaffold guard)

PM pre-decision: mark as **scaffold / Stage-A-smoke**, do NOT claim scaffold success as Stage B evidence, do NOT wire `attribution_daily` as live evidence now. Mostly a TW/PM doc patch.

### Precise doc-status split (TW + PM — PA specifies wording, does not rewrite docs)
For each surface, the status MUST decompose into these five orthogonal facts (no single "done" / "pending" claim):
1. **source-scaffold: DONE** — `attribution_daily.py` + `tournament_orchestrator.py` exist, importable, SELECT-only.
2. **active: FALSE** — not wired to a cron / not producing promotion evidence.
3. **Stage 0R evidence: PENDING** — replay preflight not green (cross-ref Stage 0R replay foundation, §7).
4. **M11 Stage A smoke: INSTALLED** — daily 04:00 UTC heartbeat cron exists (`m11_replay_runner_daily_cron.sh`); satisfies `[48]` liveness ONLY.
5. **M11 Stage B divergence: PENDING** — nightly cohort replay + `replay_divergence_log` materialization not implemented.

Surfaces to patch (TW): `docs/.../alpha_tournament_ssot_spec.md:5`, `SPECIFICATION_REGISTER.md:123`, `SCRIPT_INDEX.md:61`. PM owns `TODO.md:29,48,186-187` (PA does not edit). The contradiction to remove: docs simultaneously saying "IMPL-pending" and "mostly done" — replace both with the five-fact split.

### Anti-false-evidence guard (E1 Python, small)
`attribution_daily.py main()` currently `return 0` after emitting zero-data scaffold output (`:298-299`). To prevent a caller reading exit-0 as "Stage B pass", change the scaffold path to **`return 0` with an explicit machine-readable `summary["stage"]="A_scaffold"` and `summary["promotion_evidence"]=False`** already-present-style marker, AND have any future cron wrapper key on `promotion_evidence` not on exit code. (PA keeps exit-0 so `--dry-run` syntax checks still pass; the guard is the explicit `promotion_evidence=False` field, which a wrapper must check.) Do NOT wire the real PG path now.

### Owner
TW + PM doc patch (primary). E1 Python: add `promotion_evidence=False` / `stage="A_scaffold"` marker to the scaffold summary (≤5 lines). FA + E4 verify no caller treats scaffold exit-0 as evidence.

### Acceptance
Active docs carry the five-fact split with no internal contradiction; scaffold output self-declares non-evidence; `attribution_daily` not wired as live evidence.

---

## 5. P2-01 — Backtest API is a stub; block evidence injection (E1 Python + TW)

The stub already self-labels (`backtest_engine.py:1-13`, returns zero + warning). The real defect is `backtest_routes.py:358` auto-injecting TruthSourceRegistry with no stub guard.

### Interface change (E1 Python, surgical)
At `backtest_routes.py:358`, before the `sharpe>1.0 and trades>=10` injection, add a stub guard: if `getattr(result, "warning", "")` contains `"stubbed"` (or `engine.get_status()["stub"] is True`), skip injection and log `info` "backtest stub — TruthRegistry injection blocked (not real evidence)". This is the precise "block evidence injection from stub" the fix plan asks for; it survives a future partial-wire of the stub.

### Owner
E1 Python (route guard). TW: ensure the route docstring `:32,38` no longer implies stub results feed evolution.

### Tests (pytest)
- Route test: stub backtest with any sharpe/trades → assert TruthSourceRegistry injection NOT called (mock the registry).
- Regression: a non-stub `BacktestResult` (warning empty, sharpe=1.5, trades=20) still injects (guard only blocks stub).

### Acceptance
Stub backtest results can never inject into the evolution/truth plane; non-stub path unaffected; docs match behavior.

---

## 6. P2-05 — Scheduled ML training stage policy (E1 + MIT; PA decision)

### PA recommendation: **keep training demo-only, intentionally — document it, do NOT add a live_demo training lane now.**

Rationale: `ml_training_maintenance.py:57` trains on `demo` while shadowing `demo,live_demo` (`:58`). Per LiveDemo policy (memory `feedback_live_no_degradation_by_endpoint`), live_demo IS live control flow on a demo endpoint — its fills are valid edge data, but mixing live_demo into the training lane now, before drift/performance evidence tables are populated (P2-06) and before Stage 0R replay is green (P2-07), would train on a wider lane than the promotion gates can yet validate. Sequencing: populate evidence tables (P2-06) → green Stage 0R/Stage B replay (P2-07) → THEN consider an isolated live_demo-widened training lane as a separate ticket.

### What changes now (E1 + TW, doc + comment)
- Add a comment at `ml_training_maintenance.py:57` stating demo-only is intentional pending P2-06/P2-07, with the named follow-up condition.
- No code behavior change now. Defer the isolated live_demo lane to a post-burn-in ticket.

### Owner / Acceptance
E1 (comment) + TW (doc rationale). MIT + QC verify the sequencing rationale. Acceptance: demo-only training documented as intentional with explicit reopen condition; no premature lane widening.

---

## 7. P2-06 — Drift / model_performance evidence (E1 + MIT; deploy-gated enablement)

### Spec
`observability.drift_events` and `observability.model_performance` are empty. Two-part fix:
1. **Enable evaluator/writer after burn-in** (E1 + MIT): `feature_baseline_writer_cron.sh` / `canary_promoter.py` write paths must populate drift/model_performance once a burn-in window of mode-scoped fills exists. Enablement of any cron/writer that mutates DB is **operator-deploy-gated** — spec the wiring, do not enable here.
2. **Gate live packets on non-empty mode-scoped evidence** (E1): a live-readiness/canary packet must FAIL-closed (defer) when its mode-scoped (`engine_mode IN ('live','live_demo')` for live, `'demo'` for demo) drift/performance evidence row count is zero. This prevents promoting on an empty evidence table (false-green).

### Owner / Tests / Acceptance
E1 + MIT. Tests: MIT SELECT proof (Linux) of non-empty mode-scoped rows after a staged/burn-in run; unit test that the packet gate returns defer on zero rows. Acceptance: no live packet passes on empty mode-scoped drift/performance; writer enablement is deploy-gated and idempotent.

---

## 8. P2-07 — Stage B cohort replay (PA design only, defer impl)

### Spec (design only — IMPL deferred)
Current state: M11 is Stage A single-manifest smoke (heartbeat; `replay.experiments=24`, `completed=0`, `replay_divergence_log=0`). Stage B requires (per PA 2026-05-28 m11 schedule proposal + ADR-0038 Sprint 3 Phase A):
- A **nightly cohort wrapper** (does not exist) iterating 5 strategy × N symbol → ~125 replay runs/night under `ReplayProfile::Isolated`.
- **Completion materialization**: each run writes `completed_at` + `exit_code` to `replay.run_state` (fixes the zombie-row risk noted in the cron DESIGN-FIX header).
- **Veto materialization**: divergence beyond threshold writes `learning.replay_divergence_log` rows; a veto row blocks the corresponding promotion packet.

Cron entry pattern is unchanged from Stage A (PA proposal designed Stage A→B to be wrapper-internal). **Defer implementation** until Stage A zombie-row fix lands and Stage 0R preflight is green. This finding produces a design note + ticket, not code now.

### Owner / Acceptance
PA design (this section) + future E1 IMPL ticket. MIT + QC verify the cohort/veto contract at IMPL time. Acceptance now: Stage B contract documented (cohort + completion + veto) with explicit defer; no smoke-only result is claimed as promotion-grade.

---

## 9. Implementation Classification

| Class | Findings | Notes |
|---|---|---|
| **Implementable now** (code + cargo/pytest, Linux-authoritative build) | P1-09 (Rust gate), P1-10 (Python freeze + tests), P2-01 (route guard), P1-16 scaffold marker (≤5 lines) | No DB schema change, no deploy. cargo/pytest run on trade-core. |
| **Doc-only now** | P1-11 (spec/TODO reclassify — recommended), P1-16 doc split, P2-05 comment+rationale | TW + PM. PA does not edit TODO/memory. |
| **Operator-deploy-gated** | P2-06 writer/cron enablement; P1-11 fallback migration IF PM rejects amendment (MIT Linux PG dry-run mandatory before any apply) | No APPLY here. |
| **Defer-to-later (design only)** | P2-07 Stage B cohort replay | Ticket + design note; IMPL after Stage A zombie fix + green Stage 0R. |

## 10. E1/MIT/TW Dispatch Lanes (max parallelism, non-overlapping files)

| Lane | Owner | Files | Blocking |
|---|---|---|---|
| C1 | E1 Rust | `edge_estimates.rs`, `intent_processor/gates.rs` (+ RiskConfig slippage field) | independent |
| C2 | E1 Python | `promotion_pipeline.py`, `governance_promotion_routes.py`, `tests/test_promotion_pipeline.py` | independent |
| C3 | E1 Python | `backtest_routes.py` (+ route test) | independent |
| C4 | E1 Python | `helper_scripts/alpha_tournament/attribution_daily.py` (scaffold marker), `cron/ml_training_maintenance.py:57` (comment) | independent |
| C5 | TW + PM | `alpha_tournament_ssot_spec.md`, `SPECIFICATION_REGISTER.md`, `SCRIPT_INDEX.md`, close-maker spec; PM: `TODO.md` | independent (no code) |
| C6 | E1 + MIT | P2-06 writer gate + packet defer (enablement deploy-gated) | after burn-in evidence design agreed |

C1–C5 are fully parallel (disjoint files). C6 trails. P2-07 = design note only (no lane).

## 11. E2 Top-3 Review Focus

1. **P1-09 gate purity + demo/live asymmetry**: confirm the freshness/runtime/validated check routes **live→reject, demo→exploration** (NOT demo-reject, which recreates Phase 5 dead-loop); confirm `now` is injected (not wallclock inside the pure gate) and TTL reads from config not a literal; confirm negative/cold-start branches are untouched (regression-locked).
2. **P1-10 single chokepoint**: confirm `promote()` is the only path that can advance stage and the DEMO_ACTIVE branch is hard-frozen; confirm `check_paper_graduation` cannot be used as an alternate promotion path; confirm the happy-path test was rewritten (not just deleted) so downstream stages stay covered.
3. **P2-01 stub guard durability**: confirm the injection guard keys on a stub signal (`warning`/`get_status().stub`) that survives a future partial-wire, not on the current zero-values (which would silently re-open the leak the moment the stub returns non-zero).

## 12. Genuine Operator Decisions Still Needed

1. **P1-11 canonical source**: approve PA recommendation that `trading.fills` V094 columns are canonical and the `learning.close_maker_audit` table requirement is retired (recommended), OR mandate a dedicated table (deploy-gated migration + writer — PA advises against). *Only real decision in this package.*
2. **P1-09 EDGE_TTL value**: confirm 48h (PA default) or set another value. Low-risk; PA default stands absent objection.
3. (Informational, already PM-pre-decided) P1-10 freeze, P1-16 scaffold-not-evidence, P2-05 demo-only-intentional — no further decision needed unless PM wants the live_demo training lane pulled earlier than post-burn-in.

PA PKG-C EVIDENCE/PROMOTION SPEC DONE.
