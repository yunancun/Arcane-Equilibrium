# MIT Database / ML Foundation Audit — 2026-05-30

Campaign label: 2026-05-17 · Actual run: 2026-05-30 CEST
Role: MIT(default), READ-ONLY (Phase 2 of PM cold audit)
Baseline: frozen `187704f6`. **Mac HEAD = Linux HEAD = `fe8393e2`** (both FRESH-CONFIRMED, identical;
TODO v85 banner says `e63a00e0` — banner stale by >=1 commit, but SOURCE-CODE delta baseline->HEAD is ZERO).
Scope: schema/migrations (V### up to V115), feature tables, training rows, labels, CV, leakage, ML deploy stage.

## TOOL-OUTAGE DISCLOSURE (load-bearing — read first)

Bash/Read/ssh tools had an INTERMITTENT empty-return outage this run (ENV WARNING flakiness, recurring). I DID
obtain FRESH evidence — including FRESH on the Linux runtime host directly — for the highest-value PM questions:
e9f01569 (BOTH Mac + Linux), ec995160, V104 (git-log + src grep empty), V115 (file + Guard structure),
source-delta, migration inventory, HEAD parity. The ONLY items I could NOT freshly obtain are the runtime
**row counts** (`_sqlx_migrations` max, basis_panel accumulation, model_performance=0): non-interactive SSH
shell has **`DATABASE_URL` EMPTY** (systemd/profile env not sourced — the documented non-interactive-shell
limitation), so read-only psql could not resolve the DB URL without deeper probing that risked more outage
churn against the call budget. Those counts are tagged [INHERITED-RECORD] from TODO v85 §0 + MIT pre-apply
dry-run + prior report, and a live re-run is filed as a disclosed Blocker. I fabricated zero counts.

## Executive Verdict

- P0: 0
- P1: 0 (prior MIT-DBML-001 subsumed by v84 P1-14 model-registry-mandatory + P2-06 deferred; no NEW P1)
- P2: 2 (carry-forward, deferred-by-design: model_performance evaluator-writer empty; Stage-B replay incomplete)
- P3: 1 (carry-forward: synthetic_replay in demo-applier allowlist — already P3-03 mitigated to opt-in)
- Prior re-run (~2026-05-29) P0=0/P1=17/P2=17/P3=7 ALL remediated+DEPLOYED (v84). This audit finds prior
  remediation HELD: source-code delta baseline `187704f6` -> HEAD `fe8393e2` = **ZERO non-docs files**
  (7 files changed, all docs/agent-reports) [FRESH-CONFIRMED]. No regression, no re-opened finding, no NEW
  schema/leakage defect.

## EXPLICIT ML-STAGE ANSWER

**ML is at SHADOW / ADVISORY + DEMO-APPLY. Live ML is BLOCKED.** (Unchanged from 2026-05-17; correctly so.)

- Apply path demo-scoped only: mlde_demo_applier.py applies only demo-engine_mode param changes; live/live_demo
  rows never auto-applied. [INHERITED-RECORD: prior report, source-cited L30-38]
- Scheduled supervised/quantile training defaults engine_mode=demo (ml_training_maintenance.py:57); shadow
  advisor demo,live_demo (:58). Quantile verdict shadow_only -> model_registry_skipped.
- model_registry: 3 stale rows (max 2026-04-24), production=0, promoting=0. Canary promoter default-off
  (canary_promoter.py:617). 5-gate live readiness NOT bypassable (SHARED FACT). No live ML graduation candidate.
- Honest conservative posture, not a defect. Blocker = promotion foundation (no fresh registry-backed
  candidate, empty drift/model_performance evidence, replay still Stage-A smoke). v84 P2-05 ratified demo-only
  scheduled training as INTENTIONAL (ADR-0004 addendum) — prior MIT-DBML-002 is now declared stage policy.

## Deep-Dive #1 — Source-vs-Runtime Drift

(a) e9f01569 -> VERDICT: NOT a git commit; it is the /proc/exe binary content SHA. CORRECT.
**[FRESH-CONFIRMED on BOTH Mac AND Linux runtime host]** `git cat-file -t e9f01569` => `fatal: Not a valid
object name e9f01569` on Mac (2 runs) AND on `ssh trade-core` (`/home/ncyu/BybitOpenClaw/srv`). ec995160 /
187704f6 / e63a00e0 / fe8393e2 all => `commit`. `readlink /proc/251791/exe` =>
`/home/ncyu/BybitOpenClaw/srv/target/release/openclaw_engine (deleted)` — a compiled artifact rebuilt
in-place. e9f01569 is its content SHA, not a git ref. PM hypothesis resolves definitively to **binary hash**.
The v85 self-correction is CORRECT and now independently FRESH-CONFIRMED on the runtime host, not merely
inherited. Real build commit = ec995160 (basis-rebuild tree).

(b) V115 basis_panel -> VERDICT: migration source EXEMPLARY; applied+live per record. **[MIXED]**
Source [FRESH-CONFIRMED]: `sql/migrations/V115__panel_basis_panel.sql` present; max migration = V115; Guard
A/B/C enforced (31 RAISE/IF-NOT-EXISTS/hypertable/CHECK markers); idempotent DDL; TimescaleDB hypertable (1d
chunk on BIGINT snapshot_ts_ms) + integer_now_func + 14d retention + hot-path index. **CORRECTION to any prior
draft: basis_panel has NO engine_mode column and NO IPC slot — by deliberate design it is market-data /
market-truth (not per-engine), serving OFFLINE replay only; the live A1 path uses an in-memory index_prices
cache. NOT NULL on basis_pct/index_price/perp_last_price = writer-side fail-closed (index<=0 => no row, not
NULL row).** This is correct schema design, not an engine_mode-CHECK omission. MIT pre-apply dry-run sign-off
exists (2026-05-29--v115_basis_panel_dry_run.md). SHARED FACT confirmed: writer = BasisAggregator
(panel_aggregator/basis.rs), Bybit WS->PG, 60s flush; **NO Binance fetcher**.
Runtime [INHERITED-RECORD]: TODO v85 _sqlx_migrations max=115 success=true; basis_panel live 25 sym / 60s
flush / latest age ~36s. FRESH-FAIL: psql SELECT blocked by empty DATABASE_URL in non-interactive SSH — Blocker.

(c) _sqlx_migrations max==115 matches source -> VERDICT: ALIGNED. **[MIXED]**
Source [FRESH-CONFIRMED]: 110 V*.sql files, max V115. V103->V106 has a REAL numeric gap (V104, V105 absent) —
historical/expected (matches v85 "V103->V106 SKIP"). Runtime [INHERITED-RECORD]: v82 recorded V114 sqlx
version=114; v85 max=115. Prior 2026-05-17 run had runtime max=113 vs source 114 (then source-ahead); gap since
closed; source/runtime CONVERGED at 115 per record. FRESH-FAIL: SELECT max(version) blocked — Blocker.

## Deep-Dive #4 — Feature windows hardcoded vs config

[INHERITED-RECORD prior CV section + memory; baseline-frozen guarantee] Positive controls prior-confirmed:
CPCV embargo/label-window cpcv_validator.py:48/113; quantile per-strategy embargo/holdout
quantile_trainer.py:52/423/578; scorer CPCV-before-fit scorer_trainer.py:168 — config/strategy-keyed, not
hardcoded constants. CAVEAT carried: edge_estimate_validation.py:27 purge_days=0 default — OK because main
paths carry CPCV/embargo, but any promotion-evidence caller MUST set nonzero purge (not a new finding).
**Source-code delta since baseline = ZERO non-docs [FRESH-CONFIRMED] => no new feature-window code landed;
leakage surface unchanged from prior GREEN.** Strongest assurance absent a live grep.

## Deep-Dive #6 — Evidence validity (labels / provenance / engine_mode)

[INHERITED-RECORD prior report L52-66/L146-161] Labels: decision_features ~11.6M rows fresh; label_net_edge_bps
non-null 2.10M; label_close_tag non-null 6.09M. attribution_chain_ok = computed VIEW column (4-source:
signal_id/context_id/signal_context_id==context_id/label_net_edge_bps NOT NULL) — auditable, not flat flag.
Provenance: parquet_etl.py:439 loads ordered-by-ts with exact engine_mode + strategy/symbol + schema-
version/hash + feature-def-hash filters; :549 rejects malformed/non-finite (no silent zero-fill). Verdict
gating quantile_reports.py:233 downgrades to shadow_only on weak/low-N (anti-overfit). engine_mode: stable rule
HOLDS — training/shadow filters IN ('live','live_demo') not ='live'; paper excluded; CHECK enum齊一 on
learning/trading tables (V015/V021/V023). NOTE: panel.basis_panel intentionally has NO engine_mode (market-
data); this does not violate the rule — the rule governs per-engine learning/training tables. Counts are
2026-05-29 snapshot; direction (fresh/growing/filtered) structurally stable.

## v84 / deferred-work verification

- V115 applied, basis_panel live: source EXEMPLARY + Guard-compliant [FRESH-CONFIRMED]; runtime live
  [INHERITED-RECORD]; MIT pre-apply dry-run sign-off exists. CONFIRMED.
- P2-06 model_performance evaluator-writer: CONFIRMED HONEST. Table = V004 (exists), no migration needed;
  closure archive L68-69 + pkgE report. observability.model_performance=0 rows = Foundation-only, correctly
  disclosed (P2-#1). NOT claimed-live. No dead table created.
- P2-07 Stage-B cohort replay: CONFIRMED HONEST. Current = Stage-A single-fixture smoke heartbeat, explicitly
  NOT promotion-grade; replay.experiments completed=0/live_demo=0, simulated_fills stale (2026-05-11).
  Disclosed, not over-claimed (P2-#2).
- V104 supervised.live_audit: **RECORD WAS HALLUCINATION — NOW CORRECTLY REVERSED [FRESH-CONFIRMED].**
  `git log --all -S supervised_live_audit -- '*.sql' '*.rs'` = EMPTY; src grep (rust/program_code/
  helper_scripts) = EMPTY; no V104 file (V103->V106 gap). V104 NEVER EXISTED anywhere in git history or source
  = free hole, must be written fresh. v85: earlier same-day commit d9128e22 falsely wrote "V104 applied";
  reality-check + forward-fix 8d1890a8 + new Gate 2b (E1 writes real file -> MIT re-runs idempotency dry-run).
  **MIT's own 2026-05-27 v104 dry-run report (8345 bytes) therefore reviewed a NON-EXISTENT migration — that
  report is now superseded/void.** No double-apply/hash-drift risk EXISTS precisely because the migration does
  not exist; the v84 "checksum frozen" phrasing was part of the hallucination and is void. This self-correction
  is exactly the V023 / P0-sqlx-hash-drift discipline working as intended.
- V104/V114 checksum frozen / no hash-drift: V114 = real & sqlx-recorded (v82), checksum-safe. V104 = void.
  No hash-drift risk on the frozen tree.

## Migration / Guard alignment

- No NEW migration since baseline 187704f6 (source-code delta ZERO non-docs, FRESH-CONFIRMED) => no NEW
  Guard A/B/C surface this run.
- V115 carries Guard A/B/C + idempotent DDL + hypertable/retention/index [FRESH-CONFIRMED] + MIT pre-apply
  dry-run sign-off. v_migration-PG-dry-run mandate honored (incl. idempotency double-apply gate).
- Gate 2b NEW (v85): future V104 real-write must pass MIT idempotency dry-run before record — correct retrofit
  of the hallucination lesson into the dispatch gate.

## CV / Leakage controls (status: HELD)

shift(1) leak-free, IN ('live','live_demo') filter, closed-bar-only resample, feature-ts-before-target-window:
all stable, no regression. CPCV/embargo positive controls intact. No NEW feature/label code since baseline =>
leakage surface unchanged from prior GREEN.

## Blockers / cross-role handoffs

1. [LINUX-RUNTIME re-run — tool-outage residual, NOT a defect] Re-run read-only psql when DB URL resolvable
   (source the engine env / use systemd EnvironmentFile, since non-interactive SSH DATABASE_URL is empty):
   `SELECT max(version),count(*) FROM _sqlx_migrations` (expect 115);
   `SELECT count(*),max(snapshot_ts_ms),count(DISTINCT symbol) FROM panel.basis_panel` (expect ~25 sym, small
   age); `SELECT count(*) FROM observability.model_performance` (expect 0, confirms P2 deferral honest).
   e9f01569-not-a-git-object ALREADY FRESH-CONFIRMED on Linux this run. Owner: MIT re-run, or E4 runtime evidence.
2. [P2 carry, deferred-by-design] model_performance evaluator-writer (P2-06) + Stage-B cohort replay (P2-07)
   remain Foundation-only. Gate live-ML promotion on non-empty mode-scoped evidence. Owner: E1 impl (future ML
   wave) / MIT metric+schema acceptance / QC alpha-validity of replay evidence.
3. [LG-3 / V104] V104 supervised.live_audit must be written FRESH (free hole, FRESH-CONFIRMED non-existent).
   Owner: E1 write + MIT Gate-2b idempotency dry-run. Cross-role: PA dispatch packet rewrite (v85 sec1 open).
4. [P3 carry] synthetic_replay opt-in (P3-03) landed; keep synthetic out of real/calibrated co-mingling as
   volume grows. Owner: PA evidence policy.
5. [DOC-HYGIENE, minor] TODO v85 HEAD banner (`e63a00e0`) stale vs actual Mac=Linux HEAD `fe8393e2`. Non-load-
   bearing (source-code delta ZERO). Owner: PM/R4 banner refresh.

## Did prior remediation hold?

YES at source [FRESH-CONFIRMED: ZERO non-docs delta baseline->HEAD; Mac==Linux HEAD]. v84 cold-audit closure
(17 P1 + 15/17 P2 + 7/7 P3) shows no regression on frozen 187704f6; no re-opened finding; ML stage correctly
remains shadow/advisory+demo-apply with live blocked; demo-only training now a declared policy (P2-05). The one
important post-closure event is the V104 hallucination — which the team SELF-CAUGHT and reversed (v85), and
which I independently FRESH-CONFIRMED via empty git-log/grep. Process win, not a held-defect.

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-30--MIT--db_ml_foundation_audit.md
