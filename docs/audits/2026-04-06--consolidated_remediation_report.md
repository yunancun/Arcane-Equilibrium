# 2026-04-06 Consolidated Remediation Report
# OpenClaw / Bybit AI Agent Trading System

**Author:** PA (Project Architect)
**Date:** 2026-04-06
**Inputs:** 13 audit reports under `/home/ncyu/BybitOpenClaw/srv/` (A3, AI-E, BB, CC, E3, E4, E5, FA, MIT, PA, QC, R4, TW)
**Method:** Read all reports → extract findings → cross-check against current code → de-duplicate → re-prioritize → batch into R0-R3 → schedule.
**Baseline:** Rust 856 + Python 1075 = 1931 tests (per CLAUDE.md §三, 2026-04-06)
**Predecessor:** `audit_PA_consolidated_remediation_plan.md` (63 issues / 11 work packages, 2026-04-05) — this report supersedes it with status verification.

---

## 1. Executive Summary

### 1.1 Aggregate Counts (raw, before de-dup)

| Source | Findings | P0 | P1 | P2 | P3 |
|--------|---------:|---:|---:|---:|---:|
| A3 GUI Usability | 53 | 1 | 10 | ~30 | ~12 |
| AI-E Effectiveness | 11 | 0 | 2 | 5 | 4 |
| BB Bybit API | 62 (47 endpoints + 15 issue items) | 0 | 0 | 3 | 0 (rest = pass) |
| CC Compliance | 13 | 1 | 2 | 3 | 0 (8 pass) |
| E3 Security | 20 | 2 | 5 | 5 | 0 (8 pass) |
| E4 Test Coverage | 40 | 4 | 6 | 12 | 18 |
| E5 Optimization | 27 | 2 | 8 | 6 | 11 |
| FA Functional Spec | 10 GAPs | 0 | 1 | 6 | 3 |
| MIT DB/ML | 14 | 2 | 4 | 7 | 1 |
| PA (prior plan) | 63 | 7 | 21 | 25 | 10 |
| QC Math/Algo | 51 (43 hardcoded + 8 notes) | 0 | 5 | 14 | 24 |
| R4 Index Verify | 28 | 0 | 2 | 4 | 22 |
| TW Doc Inventory | 22 | 3 | 7 | 3 | 9 |
| **Raw total** | **414** | **22** | **73** | **123** | **114** |

> Note: PA's 63-issue tracker already de-duplicates the other reports. Numbers below operate on PA's 63 plus a small set of newly verified items uncovered during 04-06 cross-check.

### 1.2 De-duplicated, Status-Verified Inventory (63 base issues)

| Severity | Total | DONE | PARTIAL | OPEN |
|----------|-----:|-----:|--------:|-----:|
| P0 | 7  | 2 | 1 | 4 |
| P1 | 21 | 4 | 2 | 15 |
| P2 | 25 | 0 | 1 | 24 |
| P3 | 10 | 0 | 0 | 10 |
| **Total** | **63** | **6 (9.5%)** | **4 (6.3%)** | **53 (84.1%)** |

### 1.3 Headline Findings

- The system passes 14/16 root principles. 8/8 fail-closed paths verified. 7/7 gate chain verified for `process()` (paper mode).
- **Exchange mode is NOT ready.** I-01 (Cost Gate missing in `process_gates_only`) is still OPEN as of 2026-04-06 cross-check (intent_processor.rs lines 317-396 contain Gate 3 in `process()` only; `process_gates_only()` at L396 has no Gate 3 block).
- **IPC socket still has no auth and no 0o600 permission** (no `set_permissions` / `0o600` reference in `rust/openclaw_engine/src/`).
- **stress_integration.rs has been removed entirely** (file no longer exists under `tests/`); the 29 stress scenarios are gone, not fixed. New OPEN item NEW-1.
- Session 9c realized_pnl wiring is **DONE and verified** (`tick_pipeline.rs:737-763` returns and forwards `realized_pnl` from `apply_fill`; `trading_writer.rs:151-163` binds it into `trading.fills`).
- `market_data_client.rs` is **still 1422 lines** (hard-limit violation). `intent_processor.rs` is now 698 lines (fine). `tick_pipeline.rs` was 1209 — recheck recommended after WP-D.
- DDL V001-V007 still flagged "not yet executed" by MIT; planned execution date 2026-04-11. All five Rust DB writers are wired but no-op without PG schema.
- ML pipeline (Scorer/ONNX) is still un-wired into `tick_pipeline.rs`. AI-E score 42/100 holds.

---

## 2. De-duplication Map

Findings that collapse into single tracker IDs:

| Tracker | Description | Source Reports | Notes |
|---------|-------------|----------------|-------|
| I-01 | Cost Gate missing in exchange path | FA-GAP1, E3-SEC01, CC-§10, PA | 3 reports → 1 issue |
| I-02 | IPC Unix socket no auth / 0o600 | E3-SEC08, PA | unique to E3 |
| I-06 | `market_data_client.rs` >1200 LOC | E5-§1, CC-§4.2, PA | 2 reports |
| I-07 | DDL V001-V007 not executed | MIT-§1/§2, PA | unique to MIT |
| I-17 | High-risk hardcoded values (HC-S1/S2/S3/CG1/CG2) | QC-§15, PA | 5 sub-items |
| I-19 | Scorer not wired to tick_pipeline | FA-GAP5, AI-E-§3.2, MIT-§5, PA | 3 reports |
| I-20 | `record_trade()` never called → Kelly has no data | FA-GAP6, AI-E-§3.1, PA | 2 reports |
| I-21 | `PositionSnapshot` DB message never emitted | FA-GAP7, MIT-§2, PA | 2 reports |
| I-23 | `ort` crate not integrated | AI-E-§4, MIT-§5/§6, PA | 1 root issue (multiple sections) |
| I-24/I-25/I-26 | docs/README + SCRIPT_INDEX + worklog merge | TW, R4, PA | 3 docs items collapsed under WP-I |
| I-29 | `correlated_exposure_pct = 0.0` hardcoded | FA-GAP3, CC-#16, QC-§1.1, PA | 3 reports |
| I-50/I-51/I-52 | Bybit API low-risk items | BB-§7/§8.3/§10.1, PA | All sub-1.0 risk |
| I-62 | Legacy Python AI subsystems (~100 files) | AI-E-§11.3, PA | unique |

Reports that contributed *no new* findings beyond PA's tracker:
- **CC** mostly pass (4 partials: file size, dual-rail stops, principle #7, principle #16) — all already tracked.
- **BB** confirms 47 endpoints OK, only 3 P2 items already tracked.
- **R4 / TW** are entirely WP-I (documentation hygiene).
- **A3** GUI items mapped to WP-F (D-01..D-11, AH-01..AH-11, UX-01..UX-13, O-01..O-12).
- **QC** 43 hardcoded values mapped to WP-G; the 5 high-risk are I-17.

---

## 3. Status-Annotated Inventory (per PA tracker, with 2026-04-06 verification)

Legend: ✅ DONE (verified in code) · 🟡 PARTIAL · ⬜ OPEN · 🆕 NEW (added during this audit)

### 3.1 P0 — Blocking

| ID | Title | Status | Verification |
|----|-------|:------:|--------------|
| I-01 | `process_gates_only()` missing Gate 3 Cost Gate | ⬜ OPEN | `intent_processor.rs` `process_gates_only()` (L396+) confirmed to lack the `cost_gate:` block that exists in `process()` (L317-355). |
| I-02 | IPC Unix socket no auth / 0o600 | ⬜ OPEN | grep `0o600|set_permissions` in `rust/openclaw_engine/src/` → 0 hits. |
| I-03 | `stress_integration.rs` 29 tests broken | 🆕 NEW-1 | File no longer present under `rust/openclaw_engine/tests/`. Tests were *removed*, not repaired. Re-classified as NEW-1 (re-create stress harness). |
| I-04 | `test_grafana_data_writer.py` 20 tests failing | 🟡 PARTIAL | TODO.md notes "1 pre-existing grafana test skip". Need to re-run to confirm whether 20 → 1 was a fix or a skip. Treat as PARTIAL pending E4 re-run. |
| I-05 | `test_label_generator.py` 2 tests failing | ⬜ OPEN | No record of fix in changelog. Needs re-run. |
| I-06 | `market_data_client.rs` 1422 LOC > 1200 | ⬜ OPEN | `wc -l` confirms 1422. |
| I-07 | DDL V001-V007 not executed in PG | ⬜ OPEN | DDL still draft per MIT, planned 2026-04-11. |

### 3.2 P1 — Important

| ID | Title | Status |
|----|-------|:------:|
| I-08 | `StopRequest` channel not wired into `set_trading_stop` | ⬜ OPEN |
| I-09 | IPC risk param setters lack `.clamp()` (hard_stop_pct, leverage, etc.) | ⬜ OPEN |
| I-10 | Cookie `secure=False` (legacy_routes.py L382) | ⬜ OPEN |
| I-11 | GUI `innerHTML` potential XSS | ⬜ OPEN |
| I-12 | Risk-tab inputs overwritten every 15 s | ⬜ OPEN |
| I-13 | AI-advice Apply button double `display:none` | ⬜ OPEN |
| I-14 | Delete strategy / Danger Zone lack confirm modal | ⬜ OPEN |
| I-15 | Feed/Demo/Scanner shortcut buttons are no-ops | ⬜ OPEN |
| I-16 | `saveProviderKey` silent fail + `runEvolution` wrong call shape | ⬜ OPEN |
| I-17 | 5 high-risk hardcoded values (HC-S1/S2/S3/CG1/CG2) | ⬜ OPEN |
| I-18 | Regime multipliers (12 values) hardcoded in match | ⬜ OPEN |
| I-19 | Scorer not wired into `tick_pipeline.rs` | ⬜ OPEN |
| I-20 | `record_trade()` never called → Kelly empty stats | ⬜ OPEN |
| I-21 | `PositionSnapshot` DB message never emitted | ⬜ OPEN |
| I-22 | `event_consumer.rs` 957 LOC zero tests | ⬜ OPEN |
| I-23 | `ort` crate not integrated, ONNX `predict()` is `None` | ⬜ OPEN |
| I-24 | `docs/README.md` index 25 entries missing | ⬜ OPEN |
| I-25 | `helper_scripts/SCRIPT_INDEX.md` does not exist | ⬜ OPEN |
| I-26 | 04-05 worklog fragments not merged into daily_summary | ⬜ OPEN |
| I-27 | 5 Rust compiler warnings (W1-W5) | 🟡 PARTIAL — some may have been fixed; needs `cargo check` |
| I-28 | 5+ Python files >1200 LOC (paper_trading_engine/governance/risk_manager…) | ⬜ OPEN (most DEPRECATED) |

### 3.3 P2 — Improvement (25 items)

| ID | Title | Status |
|----|-------|:------:|
| I-29 | `correlated_exposure_pct` hardcoded 0.0 | ⬜ |
| I-30 | Kelly ATR% placeholder 0.02 | ⬜ |
| I-31 | `cost_ratio` + `regime` placeholders in `check_position_on_tick` | ⬜ |
| I-32 | Thompson Sampling no PG persistence | ⬜ |
| I-33 | `drift_detector` not reading from PG | ⬜ |
| I-34 | No end-to-end ML training driver script | ⬜ |
| I-35 | `scorer_trainer` uses 80/20 split, not CPCV | ⬜ |
| I-36 | ETL ASOF JOIN type mismatch (BIGINT vs TIMESTAMPTZ) | ⬜ |
| I-37 | `requirements-ml.txt` missing | ⬜ |
| I-38 | `intent_processor` gate logic ~120 LOC duplicated | ⬜ |
| I-39 | `on_tick()` 550 LOC | ⬜ |
| I-40 | `exec_id` dedup O(n) linear scan | ⬜ |
| I-41 | 14 duplicate file pairs (audit/ vs CCAgentWorkSpace/) | ⬜ |
| I-42 | docs/audit/ vs docs/audits/ naming clash | ⬜ |
| I-43 | 18 audit reports not following YYYY-MM-DD-- pattern | ⬜ |
| I-44 | 8 .DS_Store files in repo | ⬜ |
| I-45 | CLAUDE_CHANGELOG missing RRC-1 entry | 🟡 PARTIAL — RRC-1 mentioned in §三 but no full entry |
| I-46 | Optuna `EV_net` fee model simplification | ⬜ |
| I-47 | "ATR" naming misleading (it's avg abs return, not Wilder ATR) | ⬜ |
| I-48 | Learning artifacts have no approval gate (principle #7) | ⬜ |
| I-49 | `operator_risk_config.json` diverges from Rust defaults | ⬜ |
| I-50 | No active rate-limit slowdown | ⬜ |
| I-51 | Python GET signature does not sort query string | ⬜ |
| I-52 | WS configured for Linear only; multi-category needs work | ⬜ |
| I-53 | Some TimescaleDB tables lack compression policy | ⬜ |

### 3.4 P3 — Backlog (10 items)

I-54..I-63 all OPEN. Notable: I-62 Legacy Python AI subsystem cleanup (~100 files), I-63 Decision Lease bypassed in Rust fast path.

### 3.5 New Items Found 2026-04-06

| ID | Title | Severity | Source |
|----|-------|:--------:|--------|
| NEW-1 | `tests/stress_integration.rs` removed entirely; 29 stress scenarios no longer in suite | P0 | Filesystem cross-check |
| NEW-2 | Session 9c `realized_pnl` wiring confirmed DONE — archive I-shadow item | (info) | `tick_pipeline.rs:737-763`, `trading_writer.rs:151-163` |
| NEW-3 | A3 P0 button visibility (D-05 double display:none) — may already be fixed in Session 9 GUI work; needs visual verification | P1 | A3-D05, Session 9 risk GUI work |

---

## 4. Remediation Batches

### Batch R0 — Immediate (P0 blockers, 2-3 days)

Goal: clear all P0 before *any* new feature work; unblock Exchange mode prerequisites.

| # | IDs | Files | Effort | Owner | Dependencies |
|---|-----|-------|-------:|-------|--------------|
| R0-1 | I-01 | `rust/openclaw_engine/src/intent_processor.rs` (`process_gates_only`) | 1 h | Rust | none |
| R0-2 | I-02 + I-09 (P1 partial) | `rust/openclaw_engine/src/main.rs`, `ipc_server.rs`, `event_consumer.rs` | 3 h | Rust | none |
| R0-3 | I-06 | `rust/openclaw_engine/src/market_data_client.rs` → split into `market_data_client.rs` + `market_data_types.rs` (+ optional `market_data_history.rs`) | 1 h | Rust | none |
| R0-4 | I-07 | `db_migrations/V001..V007`, run against prod PG; verify all 6 writers produce rows | 1 d | Rust + DBA | PG instance reachable |
| R0-5 | NEW-1 | Re-create `tests/stress_integration.rs` against current 4-arg `IntentProcessor::process()` signature; restore the 29 scenarios from git history | 0.5 d | Rust + E4 | none |
| R0-6 | I-04, I-05 | Re-run `test_grafana_data_writer.py` and `test_label_generator.py`; if still red, fix root cause | 1 h | Python + E4 | none |

**Exit criteria:** all 7 P0 IDs flipped to DONE; full Rust test suite green incl. stress; PG schema deployed; `process_gates_only` covered by ≥1 test asserting Gate 3 rejection.

### Batch R1 — P1 sprint (~5-6 days)

| # | IDs | Description | Effort | Owner |
|---|-----|-------------|-------:|-------|
| R1-A | I-08 | Wire `StopRequest` channel into `PositionManager::set_trading_stop` | 2 h | Rust |
| R1-B | I-10 | Cookie `secure=True` (env-driven) | 30 m | Python |
| R1-C | I-11 | Replace `innerHTML` with `textContent` in tab-strategy/trading/risk | 1 h | GUI |
| R1-D | I-12 | Skip risk-tab refresh when input is `:focus` | 1 h | GUI |
| R1-E | I-13 | Remove parent `display:none` for AI advice apply button | 15 m | GUI |
| R1-F | I-14 | Add confirmation modals to Delete strategy + Danger Zone buttons | 30 m | GUI |
| R1-G | I-15 | Convert Feed/Demo/Scanner shortcut buttons to read-only indicators | 30 m | GUI |
| R1-H | I-16 | Fix `saveProviderKey` round-trip + `runEvolution` to use `ocPost` | 30 m | GUI |
| R1-I | I-17 + I-18 | Move HC-S1/S2/S3/CG1/CG2 + 12 regime multipliers into `StopConfig` / `RegimeConfig` | 2 h | Rust |
| R1-J | I-19 + I-20 + I-21 | Wire Scorer into `tick_pipeline` after signal generation; call `record_trade()` in fill callback; emit `PositionSnapshot` every 30 s | 1.5 d | Rust |
| R1-K | I-22 | Add ≥15 unit tests for `event_consumer.rs` (initialization, fill dispatch, IPC dispatch) | 3 h | Rust + E4 |
| R1-L | I-23 | Add `ort = "2"` to `Cargo.toml`; replace `predict()` placeholder with real session run | 2 d | Rust |
| R1-M | I-24 + I-25 + I-26 | Update `docs/README.md` (25 entries), create `helper_scripts/SCRIPT_INDEX.md`, merge 04-05 worklog fragments | 1 h | Docs |
| R1-N | I-27 | Run `cargo fix --lib -p openclaw_engine`, address W5 manually | 15 m | Rust |
| R1-O | I-28 | Plan/timeline for Python file-size compliance (most DEPRECATED) | 1 h | Python + PA |

**Exit criteria:** 21 P1 IDs DONE; GUI smoke walkthrough OK; Scorer Tier-2 evaluating live signals (still without ONNX OK).

### Batch R2 — P2 medium-term (~2 weeks)

Group into thematic mini-batches:

- **R2-DB:** I-32, I-33, I-36, I-53 (Thompson PG persistence, drift detector PG read, ETL type fix, TimescaleDB compression). Owner: Rust + Python. ~2 d.
- **R2-ML:** I-34, I-35, I-37 (end-to-end training driver, CPCV in scorer_trainer, requirements-ml.txt). Owner: Python. ~2 d. Depends on I-07 + 7-14 days of accumulated data.
- **R2-Code-Quality:** I-38, I-39, I-40 (gate dedup, on_tick split, exec_id HashSet). Owner: Rust + E5. ~1 d.
- **R2-Risk-Wiring:** I-29, I-30, I-31, I-49 (correlated exposure, Kelly ATR%, cost_ratio/regime, operator config alignment). Owner: Rust + QC. ~1 d.
- **R2-Bybit:** I-50, I-51, I-52. Owner: Rust. ~0.5 d.
- **R2-Docs:** I-41..I-45 (duplicate cleanup, naming, .DS_Store, CHANGELOG RRC-1 entry). Owner: Docs. ~0.5 d.
- **R2-Math:** I-46, I-47 (Optuna fee model, ATR naming). Owner: QC + Rust. ~0.5 d.
- **R2-Governance:** I-48 (learning approval gate). Owner: Python. ~0.5 d.

### Batch R3 — Backlog / Phase 4+ (~1 week, lower priority)

I-54 (IPC stubs), I-55 (limit-order simulation), I-56 (provider pricing table), I-57 (latency_us u64), I-58 (token JSON body), I-59 (legacy index.html cleanup), I-60 (terminology unification), I-61 (NaN feature handling), I-62 (Legacy Python subsystems audit), I-63 (Decision Lease re-wire to Rust path).

---

## 5. Risks & Dependencies

| Risk | Affects | Mitigation |
|------|---------|------------|
| DDL execution may break running engine | R0-4 | Run in maintenance window; use `CREATE TABLE IF NOT EXISTS`; have rollback DDL ready. |
| Re-creating `stress_integration.rs` from history may not match current `IntentProcessor::process()` (4 args incl. `atr`) | R0-5 | Take latest signature, port stress scenarios incrementally; treat as a new harness rather than full restore. |
| `ort` crate integration may pull large dependencies (CUDA, MKL) | R1-L | Use `ort` with `download-binaries` feature and CPU provider only on Linux x86_64 first; canary on dev machine. |
| Wiring Scorer in `tick_pipeline.rs` may cause regression in confidence-driven Cost Gate | R1-J | Keep Scorer in shadow mode for first 24 h, log delta vs current confidence. |
| GUI input-overwrite fix (I-12) is invasive across all auto-refresh tabs | R1-D | Centralize in `common.js` `ocStartPolling` helper and add focus check. |
| Python deprecated files >1200 LOC are hard to refactor | I-28 | Most are slated for removal post-Phase 3a. Only enforce limit on net-new code. |
| Removing `stress_integration.rs` already cost 29 safety-net tests; absence may delay Exchange mode | NEW-1 | Treat as P0 blocker for Exchange-mode go/no-go. |

---

## 6. Recommended Execution Schedule

| Day | Batch | Focus |
|-----|-------|-------|
| Day 1 | R0-1, R0-2, R0-3 | Cost Gate + IPC auth + market_data_client split |
| Day 2 | R0-5, R0-6 | Stress test re-creation + grafana/label generator re-run |
| Day 3 | R0-4 | DDL execution + writer verification |
| Day 4 | R1-A..R1-H (GUI + StopRequest + Cookie) | Quick wins, parallelize GUI + Rust |
| Day 5 | R1-I (param config) + R1-N (warnings) | Hardcoded value migration |
| Day 6-7 | R1-J (Scorer wiring + record_trade + PositionSnapshot) | ML wiring sprint |
| Day 8 | R1-K (event_consumer tests) + R1-M (docs) | Tests + docs |
| Day 9-10 | R1-L (`ort` integration) | ONNX path |
| Day 11-15 | R2 thematic mini-batches | Medium-term cleanup |
| Phase 4+ | R3 | Backlog |

**Critical-path Exchange mode prerequisites (blocking go-live):** R0-1, R0-2, R0-5, R1-A, R1-I (HC-S/CG), R1-J. Earliest realistic Exchange mode-ready date: **2026-04-15** (with conservative buffer).

---

## 7. Cross-Cutting Themes

1. **Exchange-mode readiness:** 6 of 7 P0 items map to Exchange-mode prerequisites. None are blocked by external dependencies.
2. **ML pipeline is the biggest gap by line-count of dead-but-correct code.** Phase 4 should treat I-19/I-20/I-21/I-23/I-34 as a single epic.
3. **Documentation hygiene** is mostly cosmetic but will compound if left to Phase 4.
4. **Hardcoded values** (QC's 43) follow an 80/20 rule: 5 high-risk (I-17) drive the actual risk; the rest are low-priority.
5. **Dual-rail stops** (I-08) is a single 2-h fix that closes Principle #9 partial compliance.

---

## 8. Reference

- Predecessor plan: `/home/ncyu/BybitOpenClaw/srv/audit_PA_consolidated_remediation_plan.md`
- Source audit reports: `/home/ncyu/BybitOpenClaw/srv/audit_*.md` (13 files)
- Affected primary files (verified at audit time):
  - `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/src/intent_processor.rs` (698 LOC)
  - `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/src/market_data_client.rs` (1422 LOC, hard-limit violation)
  - `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/src/tick_pipeline.rs`
  - `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/src/event_consumer.rs` (957 LOC, no tests)
  - `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/src/database/trading_writer.rs` (realized_pnl wiring verified)
  - `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/src/ml/{scorer.rs,model_manager.rs}` (un-wired)
  - `/home/ncyu/BybitOpenClaw/srv/program_code/.../control_api_v1/app/legacy_routes.py` (cookie secure=False)
  - `/home/ncyu/BybitOpenClaw/srv/static/tab-{strategy,risk,system,ai}.html` (GUI items)

---

*End of report. Generated 2026-04-06 by PA. Supersedes audit_PA_consolidated_remediation_plan.md as the live remediation tracker.*

---

## 9. Reviewer Addendum (2026-04-06, Committee Review)

**Verdict: APPROVE WITH CHANGES**

Committee perspectives represented: QC, E3, E4, E5, MIT, FA, A3, CC, BB, R4, TW, AI-E, PA.

### 9.1 Factual Corrections (must fix before execution)

1. **NEW-1 / R0-5 — WRONG STATUS.** The file `rust/openclaw_engine/tests/stress_integration.rs` **DOES exist** (655 LOC, 29 scenarios intact). The real defect is *compile failure* — `IntentProcessor::process()` gained an `atr` parameter and the stress harness was not updated (TODO.md L118 already records this). Action: re-classify NEW-1 from "re-create from history" to "fix call sites for new 4-arg signature". Effort drops from **0.5 d → ~1 h**. Severity remains P0 (29 tests still excluded from green baseline).

2. **I-01 — VERIFIED OPEN.** `process_gates_only()` at L396 confirmed to lack the `cost_gate:` block present in `process()` (L317-355). Correctly P0.

3. **I-02 — VERIFIED OPEN.** Zero hits for `0o600` / `set_permissions` under `rust/openclaw_engine/src/`. Correctly P0.

4. **I-06 — VERIFIED.** `market_data_client.rs` = 1422 LOC (hard-limit violation). `event_consumer.rs` = 957 LOC (warning line, no tests — I-22). Correct.

5. **Session 9c realized_pnl — VERIFIED DONE.** `trading_writer.rs:151,154,163` confirms the column is bound from `TradingMsg::Fill.realized_pnl`. NEW-2 archive note is accurate.

6. **I-04 — should be downgraded to PARTIAL→DONE pending re-run.** TODO.md L117 states "1 pre-existing grafana test skip" and L610 records "grafana_data_writer 30 tests PASS". The "20 failing" framing is stale; reclassify as P2/PARTIAL, not P0. Effort for R0-6 drops accordingly.

### 9.2 Prioritization Adjustments

- **I-22 (event_consumer.rs 957 LOC, zero tests)** is currently P1. Given that this module is on the IPC fill-dispatch path and feeds directly into Exchange-mode plumbing, **promote to P0** for Exchange-mode go-live gating, OR explicitly mark "non-blocking for paper" and keep P1. Committee leans P0-Exchange.
- **I-09 (IPC param clamps)** bundled into R0-2 is correct — keep.
- **I-08 (StopRequest dual-rail wiring)** at P1 is borderline. Principle #9 (exchange disaster protection) is a憲法-level requirement; recommend promoting to P0 for Exchange-mode prereq list (effort still 2 h).

### 9.3 R0 Batch — Missing Items

The R0 batch should also include (or explicitly defer with rationale):
- **I-08 dual-rail stops** (2 h) — Principle #9 hard requirement for Exchange mode.
- **stress_integration.rs compile fix** is the right scope, not "re-create".

Add an R0-7 line item or fold I-08 into R1-A but flag as Exchange-mode blocker.

### 9.4 Effort Estimates

- R0-3 (market_data_client split, 1422 → ≤1200) at 1 h is **optimistic**. Realistic: 3-4 h including test re-runs and import fixes. Bump to 0.5 d.
- R0-4 (DDL execution + 6-writer verification) at 1 d is realistic only if PG instance is pre-provisioned. Otherwise add 0.5 d.
- R1-L (`ort` integration) at 2 d is optimistic on first attempt; recommend 3 d with CPU-only canary buffer.
- R0-5 corrected to 1 h (was 0.5 d) — see §9.1.

### 9.5 Findings Possibly Lost in Consolidation

Spot-checked 13 source reports. No material loss detected. Minor:
- E4's note about *which* 5 compiler warnings (W1-W5) is collapsed into I-27 without IDs; recommend cross-link.
- BB's per-endpoint pass list (47 endpoints) is correctly summarized; no findings dropped.
- QC's 43 hardcoded values are correctly bucketed (5 high-risk → I-17, rest → WP-G).

### 9.6 TODO.md Archival

TODO.md (718 lines) retains the historical Phase 0-3b records intact. R0 items are present at L19-20. No content destroyed. ✅

### 9.7 Confidence

**Confidence: HIGH** on file-level verifications (intent_processor, market_data_client, trading_writer, stress_integration, IPC perms).
**Confidence: MEDIUM** on effort estimates (only spot-checked 4 of 16 line items).
**Confidence: HIGH** on de-dup map fidelity vs source audits.

### 9.8 Required Pre-Execution Actions

1. Fix NEW-1 description: "compile fix for new `atr` arg" not "re-create from history".
2. Decide P0 vs P1 for I-08 and I-22 (Exchange-mode gating).
3. Re-run grafana + label_generator tests once to settle I-04/I-05 status before R0 sprint kicks off.
4. Bump R0-3 effort to 0.5 d.

*— Committee review complete. Approve with above corrections.*

---

## 10. Sub-Checklists — Per-Finding Traceability

This section expands every bucket-folded WP into individual sub-items so each of the ~170 findings from the 414-item raw audit gets its own checkbox. Each line format is:

`- [ ] WP-X/TAG — {short title} ({source_report}:§{anchor}) — P{severity}`

Source reports are the 13 files under `/home/ncyu/BybitOpenClaw/srv/audit_*_report.md`. Counts per WP are given at the end of each subsection. Items already tracked as top-level I-## in §3 remain authoritative; sub-items here provide finer-grained audit coverage and enable per-file remediation tracking.

### 10.1 WP-F — GUI Usability (A3 report, 47 items)

Source: `audit_A3_gui_usability_report.md`

**D — Dead Buttons / Controls (11)**
- [ ] WP-F/D-01 — `tab-risk.html` Apply-AI button toast-only, no effect (audit_A3_gui_usability_report:§1.1) — P1
- [ ] WP-F/D-02 — `tab-system.html` Feed shortcut button is no-op (§1.1) — P1
- [ ] WP-F/D-03 — `tab-system.html` Bybit Demo shortcut button is no-op (§1.1) — P1
- [ ] WP-F/D-04 — `tab-system.html` Scanner shortcut button is no-op (§1.1) — P1
- [ ] WP-F/D-05 — `tab-risk.html` Apply-AI double `display:none` (永不可見) (§1.1) — P0
- [ ] WP-F/D-06 — Legacy `index.html` panel still routed at `/gui` (§1.2) — P2
- [ ] WP-F/D-07 — Legacy Bearer Token input panel still present (§1.2) — P1
- [ ] WP-F/D-08 — `trading.html` iframe lacks common.js helpers (§1.2) — P2
- [ ] WP-F/D-09 — `tab-strategy.html` Delete button has no confirm (§1.3) — P1
- [ ] WP-F/D-10 — `tab-ai.html` `saveProviderKey` silent-fail (provider_keys unhandled) (§1.3) — P1
- [ ] WP-F/D-11 — `tab-ai.html` `runEvolution` wrong call shape (should `ocPost`) (§1.3) — P1

**UX — Design Issues (13)**
- [ ] WP-F/UX-01 — Delete strategy no confirm modal (audit_A3_gui_usability_report:§2.1) — P0
- [ ] WP-F/UX-02 — Danger Zone (Reset Loss Cooldown / Unhalt Session) no confirm (§2.1) — P0
- [ ] WP-F/UX-03 — Three "保存設定" buttons share single `saveRiskConfig` → cross-field overwrite (§2.1) — P0
- [ ] WP-F/UX-04 — All Save buttons missing loading/disabled state (§2.2) — P1
- [ ] WP-F/UX-05 — `createStrategy` submit not disabled; double-submit risk (§2.2) — P1
- [ ] WP-F/UX-06 — `saveProviderKey` no loading state / no key format validation (§2.2) — P1
- [ ] WP-F/UX-07 — Tab titles mix Chinese/English inconsistently (§2.3) — P1
- [ ] WP-F/UX-08 — "Demo" vs "測試" vs "執行引擎" three names for same concept (§2.3) — P1
- [ ] WP-F/UX-09 — "Paper" naming inconsistent across 5 surfaces (§2.3) — P1
- [ ] WP-F/UX-10 — "Session" overloaded (Paper / AI / Auth) (§2.3) — P1
- [ ] WP-F/UX-11 — `tab-risk.html` P0 Category Limits shows raw "--" (§2.4) — P2
- [ ] WP-F/UX-12 — `tab-system.html` degraded mode does not list running services (§2.4) — P2
- [ ] WP-F/UX-13 — `console.html` 15s refresh has no visual update cue (§2.4) — P2

**O — Optimization (12)**
- [ ] WP-F/O-01 — `tab-system.html` information overload (§3.1) — P2
- [ ] WP-F/O-02 — `tab-ai.html` content too dense, needs sub-tabs (§3.1) — P2
- [ ] WP-F/O-03 — `tab-risk.html` vertical over-length, Danger Zone buried (§3.1) — P3
- [ ] WP-F/O-04 — PnL has no trend chart (§3.2) — P2
- [ ] WP-F/O-05 — Risk Pressure missing colored progress bar (§3.2) — P3
- [ ] WP-F/O-06 — AI Cost missing budget progress bar (§3.2) — P3
- [ ] WP-F/O-07 — Engine start flow too long; needs one-click (§3.3) — P2
- [ ] WP-F/O-08 — Risk config save has no diff confirmation (§3.3) — P2
- [ ] WP-F/O-09 — New strategy not auto-scrolled into view (§3.3) — P3
- [ ] WP-F/O-10 — `console.html` <860px hides sidebar; no scroll indicator (§3.4) — P2
- [ ] WP-F/O-11 — `tab-risk.html` oc-grid-3 overflows on narrow (§3.4) — P2
- [ ] WP-F/O-12 — `tab-ai.html` Provider cards cramped on mobile (§3.4) — P3

**AH — Anti-Human Design (11)**
- [ ] WP-F/AH-01 — Danger Zone buried at page bottom (§4.1) — P1
- [ ] WP-F/AH-02 — Governance Status lacks full-page warning on FROZEN / Risk≥4 (§4.1) — P1
- [ ] WP-F/AH-03 — `tab-learning.html` Auto-Scan buttons hidden in `<details>` (§4.1) — P1
- [ ] WP-F/AH-04 — Feed/Demo/Scanner buttons look like toggles but aren't (§4.2) — P1
- [ ] WP-F/AH-05 — "AI 止損建議 Apply" misleading label (§4.2) — P1
- [ ] WP-F/AH-06 — Risk-tab inputs overwritten every 15 s while editing (§4.2) — P1
- [ ] WP-F/AH-07 — Strategy Delete adjacent to Stop/Pause, no confirm (§4.3) — P1
- [ ] WP-F/AH-08 — `tab-settings.html` Enable Demo visually indistinct (§4.3) — P1
- [ ] WP-F/AH-09 — Sidebar Live panel opacity 0.5 implies broken state (§4.4) — P2
- [ ] WP-F/AH-10 — 6 Provider cards equal-weight, configured ones not highlighted (§4.4) — P2
- [ ] WP-F/AH-11 — `tab-live.html` has no interactive CTA, users land on dead page (§4.4) — P2

**WP-F total: 47**

### 10.2 WP-G — Hardcoded Values (QC report, 43 items)

Source: `audit_QC_math_algorithm_report.md:§15`

**High-Risk (5)**
- [ ] WP-G/HC-S1 — `risk/checks.rs:183` dynamic stop base = hard_stop × 0.6 (§15) — P1
- [ ] WP-G/HC-S2 — `risk/stops.rs:51` dynamic stop cap = hard_stop × 0.8 (§15) — P1
- [ ] WP-G/HC-S3 — `risk/stops.rs:55` ATR multiplier 1.5 (§15) — P1
- [ ] WP-G/HC-CG1 — `intent_processor.rs:325` Cost Gate K_PAPER = 1.5 (§15) — P1
- [ ] WP-G/HC-CG2 — `intent_processor.rs:324` MIN_CONFIDENCE floor = 0.15 (§15) — P1

**Medium-Risk (14)**
- [ ] WP-G/HC-K1 — `kelly_sizer.rs:143` Kelly ATR% reference 0.02 (§15) — P2
- [ ] WP-G/HC-K2 — `kelly_sizer.rs:143` Kelly vol clamp 0.5–1.5 (§15) — P2
- [ ] WP-G/HC-K3 — `kelly_sizer.rs:123` negative-Kelly floor 0.01 (§15) — P2
- [ ] WP-G/HC-G1 — `guardian.rs:107/119/129/139/149` risk_score weights 0.4/0.3/0.4/0.15/0.35 (§15) — P2
- [ ] WP-G/HC-G2 — `guardian.rs:159` reject threshold 0.3 (§15) — P2
- [ ] WP-G/HC-G3 — `guardian.rs:124` leverage double factor 2.0 (§15) — P2
- [ ] WP-G/HC-S4 — `risk/stops.rs:21` anti-cluster ±0.15 (§15) — P2
- [ ] WP-G/HC-S5 — `risk/stops.rs:66` min stop-percent floor 0.1 (§15) — P2
- [ ] WP-G/HC-B1 — `black_swan_detector.rs:58` MAD threshold 6.0 (§15) — P2
- [ ] WP-G/HC-B2 — `black_swan_detector.rs:60` correlation threshold 0.85 (§15) — P2
- [ ] WP-G/HC-B3 — `black_swan_detector.rs:62` volume multiplier 5.0 (§15) — P2
- [ ] WP-G/HC-B4 — `black_swan_detector.rs:64` velocity bars 15 (§15) — P2
- [ ] WP-G/HC-P1 — `intent_processor.rs:114` P1 risk clamp 0.20 (§15) — P2
- [ ] WP-G/HC-F1 — `feature_collector.rs:21` buffer capacity 3000 (§12/§15) — P2

**Low-Risk (24)**
- [ ] WP-G/HC-A1 — `price_tracker.rs:7` ATR window 300s (§15) — P3
- [ ] WP-G/HC-A2 — `price_tracker.rs:10` ATR min samples 10 (§15) — P3
- [ ] WP-G/HC-A3 — `price_tracker.rs:13` Spike σ threshold 3.0 (§15) — P3
- [ ] WP-G/HC-B5 — `black_swan_detector.rs:107` return window 720 bars (§15) — P3
- [ ] WP-G/HC-B6 — `black_swan_detector.rs:108` volume window 43200 bars (§15) — P3
- [ ] WP-G/HC-B7 — `black_swan_detector.rs:169` MAD min samples 30 (§15) — P3
- [ ] WP-G/HC-B8 — `black_swan_detector.rs:246` volume min samples 100 (§15) — P3
- [ ] WP-G/HC-B9 — `black_swan_detector.rs:218` correlation window 30 (§15) — P3
- [ ] WP-G/HC-T1 — `thompson_sampling.py:86` NIG lam_0 = 3.0 (§15) — P3
- [ ] WP-G/HC-T2 — `thompson_sampling.py:87` NIG alpha_0 = 3.0 (§15) — P3
- [ ] WP-G/HC-T3 — `thompson_sampling.py:255` exploitation floor 10 (§15) — P3
- [ ] WP-G/HC-C1 — `cpcv_validator.py:51` n_folds = 4 (§15) — P3
- [ ] WP-G/HC-C2 — `cpcv_validator.py:61` power threshold 0.5 (§15) — P3
- [ ] WP-G/HC-C3 — `cpcv_validator.py:62` min samples/fold 30 (§15) — P3
- [ ] WP-G/HC-C4 — `cpcv_validator.py:60` label window 4.0 h (§15) — P3
- [ ] WP-G/HC-C5 — `cpcv_validator.py:196` effect size 0.3 (§15) — P3
- [ ] WP-G/HC-D1 — `drift_detector.rs:116` ADWIN delta 0.05 (§15) — P3
- [ ] WP-G/HC-D2 — `drift_detector.rs:116` ADWIN min_width 50 (§15) — P3
- [ ] WP-G/HC-D3 — `drift_detector.rs:116` ADWIN consecutive 3 (§15) — P3
- [ ] WP-G/HC-D4 — Bootstrap block_size 4 (§15) — P3
- [ ] WP-G/HC-O1 — `optuna_optimizer.py:91` n_trials 30 (§15) — P3
- [ ] WP-G/HC-O2 — `optuna_optimizer.py:92` min fills 80 (§15) — P3
- [ ] WP-G/HC-O3 — `optuna_optimizer.py:234` fee_rate 0.0006 (§15) — P3
- [ ] WP-G/HC-O4 — `optuna_optimizer.py:506` perturbation 0.001 (§15) — P3

**WP-G total: 43**

### 10.3 WP-E4 — Test Coverage Gaps (E4 report, 34 items)

Source: `audit_E4_test_coverage_report.md`

**P0 — Broken / Failing (4)**
- [ ] WP-E4/T-P0-1 — `stress_integration.rs` compile failure (29 scenarios) (§二.P0-1) — P0
- [ ] WP-E4/T-P0-2 — `test_grafana_data_writer.py` 20 failing (§二.P0-2) — P0
- [ ] WP-E4/T-P0-3 — `test_label_generator.py` 2 failing (§二.P0-3) — P0
- [ ] WP-E4/T-P0-4 — `test_market_data.py` 1 failing (§二.P0-4) — P0

**P1 — High-Risk Zero-Coverage (6)**
- [ ] WP-E4/T-P1-1 — `event_consumer.rs` 957 LOC zero tests (+15) (§五.P1) — P1
- [ ] WP-E4/T-P1-2 — `layer2_engine.py` 730 LOC zero tests (+10) (§五.P1) — P1
- [ ] WP-E4/T-P1-3 — `ai_service.py` 729 LOC zero tests (+8) (§五.P1) — P1
- [ ] WP-E4/T-P1-4 — `ipc_client.py` 560 LOC zero tests (+10) (§五.P1) — P1
- [ ] WP-E4/T-P1-5 — `strategies/mod.rs` 110 LOC zero tests (+5) (§五.P1) — P1
- [ ] WP-E4/T-P1-6 — database writers missing failure-rollback tests (+8) (§五.P1) — P1

**P2 — Improvement (12)**
- [ ] WP-E4/T-P2-1 — `evolution_engine.py` zero tests (+8) (§五.P2) — P2
- [ ] WP-E4/T-P2-2 — `indicator_engine.py` zero tests (+6) (§五.P2) — P2
- [ ] WP-E4/T-P2-3 — `position_sizer.py` zero tests (+5) (§五.P2) — P2
- [ ] WP-E4/T-P2-4 — `scorer_trainer.py` zero tests (+5) (§五.P2) — P2
- [ ] WP-E4/T-P2-5 — `rest_poller.rs` zero tests (+5) (§五.P2) — P2
- [ ] WP-E4/T-P2-6 — `quality_writer.rs` zero tests (+3) (§五.P2) — P2
- [ ] WP-E4/T-P2-7 — `sm/mod.rs` zero tests (+4) (§五.P2) — P2
- [ ] WP-E4/T-P2-8 — `pipeline_types.rs` zero tests (+3) (§五.P2) — P2
- [ ] WP-E4/T-P2-9 — PyO3 bridge test infrastructure missing (+10) (§五.P2 / §4.8) — P2
- [ ] WP-E4/T-P2-10 — Rust panic-path `#[should_panic]` gap (+8) (§五.P2) — P2
- [ ] WP-E4/T-P2-11 — Arc/Mutex concurrency safety tests (+6) (§五.P2) — P2
- [ ] WP-E4/T-P2-12 — WS reconnect integration tests (+5) (§五.P2) — P2

**Quality Dimension Notes (8)**
- [ ] WP-E4/T-Q1 — Happy-path coverage 4/5 — systematic audit missing (§4.1) — P3
- [ ] WP-E4/T-Q2 — Boundary/edge-case coverage weak outside golden_extreme (§4.2) — P3
- [ ] WP-E4/T-Q3 — Error-path Rust panic coverage 3/5 (§4.3) — P3
- [ ] WP-E4/T-Q4 — Concurrency coverage 3/5 (§4.4) — P3
- [ ] WP-E4/T-Q5 — Regression test markers incomplete (§4.5) — P3
- [ ] WP-E4/T-Q6 — Assertion quality spot-check (§4.6) — P3
- [ ] WP-E4/T-Q7 — Integration smoke insufficient for Phase splits (§4.7) — P3
- [ ] WP-E4/T-Q8 — PyO3 bridge tests 1/5 — cannot link in CI (§4.8) — P2

**Infrastructure (4)**
- [ ] WP-E4/T-I1 — No `cargo-tarpaulin` / `pytest-cov` coverage tool (§六) — P2
- [ ] WP-E4/T-I2 — No CI/CD test gate (manual only) (§六) — P2
- [ ] WP-E4/T-I3 — Rust integration tests decoupled from lib tests (§六) — P2
- [ ] WP-E4/T-I4 — No test infra docs for new contributors (§六) — P3

**WP-E4 total: 34**

### 10.4 WP-I — Documentation Hygiene (R4 + TW reports, 42 items)

Source: `audit_R4_index_verification_report.md` (25) + `audit_TW_document_inventory_report.md` (17)

**R4 — Index Verification (25)**
- [ ] WP-I/R4-REF-1 — `2026-04-02--system_status_report.md` not in docs/README (R4:§1.1) — P2
- [ ] WP-I/R4-REF-2 — `2026-04-03--agent_param_tuning_design_draft_v0.2.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-REF-3 — `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-REF-4 — `2026-04-03--llm_abstraction_audit.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-REF-5 — `2026-04-03--ml_dl_learning_architecture_v0.4.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-REF-6 — `2026-04-04--bybit_api_reference.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-REF-7 — `2026-04-04--comprehensive_audit_template_v1.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-REF-8 — `2026-04-04--execution_plan_v1.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-REF-9 — `2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-WL-1..14 — 14 worklog root files (2026-04-03 ~ 2026-04-05) not indexed in docs/README (R4:§1.1) — P2
- [ ] WP-I/R4-ARCH-1 — `docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md` not declared (R4:§1.1) — P2
- [ ] WP-I/R4-AUD-1 — `docs/audits/2026-04-04--bybit_api_infra_audit.md` not indexed (R4:§1.1) — P2
- [ ] WP-I/R4-NAME-1 — `bilingual_comment_audit_report.md` index name missing date prefix (R4:§1.3) — P3
- [ ] WP-I/R4-REF-ST-1 — CLAUDE_REFERENCE.md last-update date stale (R4:§3.2) — P3
- [ ] WP-I/R4-CHG-1 — CLAUDE_CHANGELOG missing RRC-1 full entry (R4:§4.2) — P2
- [ ] WP-I/R4-SCR-1 — `helper_scripts/SCRIPT_INDEX.md` file does not exist (R4:§5.1) — P1
- [ ] WP-I/R4-MEM-1 — MEMORY.md has file not indexed (R4:§7.2) — P3
- [ ] WP-I/R4-DIR-1 — `docs/audit/` vs `docs/audits/` dir clash (R4:§8.1) — P2
- [ ] WP-I/R4-DIR-2 — `docs/architecture/` not in README tree (R4:§8.2) — P2

**TW — Document Inventory (17)**
- [ ] WP-I/TW-DUP-1..14 — 14 duplicate file pairs audit/ vs CCAgentWorkSpace/ (TW:§3.1) — P2
- [ ] WP-I/TW-DUP-15 — Rust migration plan multi-version drift (TW:§3.2) — P3
- [ ] WP-I/TW-DUP-16 — Execution plan duplicated in 2 locations (TW:§3.3) — P3
- [ ] WP-I/TW-DUP-17 — Data storage architecture duplicated (TW:§3.4) — P3
- [ ] WP-I/TW-STALE-1 — Pre-Rust state docs not marked deprecated (TW:§5.1) — P3
- [ ] WP-I/TW-STALE-2 — Superseded CCAgentWorkSpace reports (TW:§5.2) — P3
- [ ] WP-I/TW-STALE-3 — `governance_dev/` entirely stale (TW:§5.3) — P3
- [ ] WP-I/TW-NAME-1 — Files not following `YYYY-MM-DD--` pattern (TW:§6.1) — P2
- [ ] WP-I/TW-DS-1 — 8 `.DS_Store` files committed (TW:§6.2) — P2
- [ ] WP-I/TW-WL-1 — 2026-04-05 worklog fragments not merged to daily_summary (TW:§7.3) — P1

**WP-I total: 42** (R4 19 unique items incl. 14 worklogs collapsed as 1 cluster→listed as 14 granular items = 19, TW 17)

> Note: R4-WL sub-cluster expanded to 14 individual worklog files for traceability; effective R4 count = 25, TW count = 17, combined = 42.

### 10.5 WP-E5 — Optimization / Code Quality (E5 report, 20 items)

Source: `audit_E5_optimization_report.md`

- [ ] WP-E5/F1 — `intent_processor.rs` process() vs process_gates_only() duplication (~120 LOC) (§三.F1) — P1
- [ ] WP-E5/F2 — `tick_pipeline.rs` ring buffer push+trim repeated 7× (§三.F2) — P2
- [ ] WP-E5/F3 — `tick_pipeline.rs` ID generation format scattered (§三.F3) — P2
- [ ] WP-E5/F4 — `tick_pipeline.rs` `TradingMsg::Intent` construction repeated (§三.F4) — P2
- [ ] WP-E5/F5 — `tick_pipeline.rs` exchange/paper Intent push duplication (§三.F5) — P3
- [ ] WP-E5/P1 — `event_consumer.rs` exec_id dedup O(n) linear scan (§四.P1) — P1
- [ ] WP-E5/P2 — `tick_pipeline.rs` `on_tick()` heavy String clones (§四.P2) — P2
- [ ] WP-E5/P3 — `tick_pipeline.rs` `snapshot()` full-state clone (§四.P3) — P2
- [ ] WP-E5/P4 — `tick_pipeline.rs` positions collect-then-iterate (§四.P4) — P3
- [ ] WP-E5/S1 — `tick_pipeline.rs` `on_tick()` ~550 LOC (§五.S1) — P2
- [ ] WP-E5/S2 — `event_consumer.rs` `run_event_consumer()` ~850 LOC (§五.S2) — P2
- [ ] WP-E5/S3 — `intent_processor.rs` `new()` vs `with_fee_rate()` duplication (§五.S3) — P3
- [ ] WP-E5/D1 — `strategies/funding_arb.rs` entire module `#[allow(dead_code)]` (§六.D1) — P2
- [ ] WP-E5/D2 — `strategies/grid_trading.rs` 4× dead_code (§六.D2) — P2
- [ ] WP-E5/D3 — Python `governance_hub.py` 5 DEPRECATED methods retained (§六.D3) — P2
- [ ] WP-E5/D4 — Compiler unused-import/variable warnings (§六.D4) — P3
- [ ] WP-E5/R1 — `TickPipeline` struct has 27 fields (§七.R1) — P2
- [ ] WP-E5/R2 — `EventConsumerDeps` has 16 fields (§七.R2) — P2
- [ ] WP-E5/PY1 — Python DEPRECATED modules retained (§八.PY1) — P2
- [ ] WP-E5/PY2 — `paper_trading_routes.py` wildcard imports (§八.PY2) — P2

**WP-E5 total: 20**

### 10.6 WP-B — Security (E3 report, 12 items; 8 folded into top-level)

Source: `audit_E3_security_report.md`

- [ ] WP-B/SEC-01 — Exchange-mode Cost Gate missing in `process_gates_only` (§1.SEC-01) — P0
- [ ] WP-B/SEC-02 — H0Gate shadow_mode remotely toggleable via unauth IPC (§1.SEC-02) — P1
- [ ] WP-B/SEC-04 — SQL injection review (safe, tracked) (§2.SEC-04) — P2
- [ ] WP-B/SEC-05 — GUI `innerHTML` potential XSS (§2.SEC-05) — P1
- [ ] WP-B/SEC-06 — API token returned in JSON body plaintext (§3.SEC-06) — P2
- [ ] WP-B/SEC-08 — IPC Unix socket no auth + no 0o600 (§4.SEC-08) — P0
- [ ] WP-B/SEC-09 — `/api/v1/system/startup-status` unauthenticated (§4.SEC-09) — P2
- [ ] WP-B/SEC-11 — Cost Gate ATR=0 fail-open (§5.SEC-11) — P1
- [ ] WP-B/SEC-13 — `latency_us` u32 truncation (§6.SEC-13) — P2
- [ ] WP-B/SEC-17 — `OPENCLAW_ALLOW_MAINNET` single-factor guard (§8.SEC-17) — P2
- [ ] WP-B/SEC-18 — IPC risk-param setters lack `.clamp()` (§9.SEC-18) — P1
- [ ] WP-B/SEC-21 — Cookie `secure=False` (legacy_routes.py L382) (§10.SEC-21) — P1

**WP-B total: 12**

### 10.7 WP-BB — Bybit API (BB report, 3 real findings)

Source: `audit_BB_bybit_api_report.md`

- [ ] WP-BB/W-1 — Python GET signature does not sort query string (§14.W-1) — P2
- [ ] WP-BB/W-2 — Public WS configured for Linear only (§14.W-2) — P2
- [ ] WP-BB/S-1 — No active rate-limit slowdown (§14.S-1) — P2

**WP-BB total: 3** (47 endpoint passes correctly skipped per task instructions)

### 10.8 WP-CC — Compliance (CC report, 8 partial/fail items)

Source: `audit_CC_compliance_report.md`

- [ ] WP-CC/P4 — Principle #4 (strategy cannot bypass risk) partial — Gate 3 missing exchange (§1.#4) — P0
- [ ] WP-CC/P7 — Principle #7 (learning ≠ live) missing explicit approval gate (§1.#7) — P2
- [ ] WP-CC/P9 — Principle #9 (exchange disaster protection) — dual-rail stops incomplete (§1.#9 / §10) — P1
- [ ] WP-CC/P16 — Principle #16 (portfolio risk) — correlated_exposure hardcoded 0 (§1.#16) — P2
- [ ] WP-CC/FS-1 — File-size hard-limit violations `market_data_client.rs`, `event_consumer.rs` (§4.2) — P1
- [ ] WP-CC/BI-1 — Bilingual comment coverage gaps in new Rust modules (§4.1) — P3
- [ ] WP-CC/SM-1 — Singleton registry missing newly added globals (§6.2) — P3
- [ ] WP-CC/WF-1 — Workflow chain E2/E4 occasionally skipped on hotfixes (§5) — P2

**WP-CC total: 8**

### 10.9 WP-FA — Functional Spec Gaps (FA report, 5 partial items not in top-level)

Source: `audit_FA_functional_spec_report.md`

- [ ] WP-FA/GAP-2 — `cost_ratio` and `regime` placeholders in `check_position_on_tick` (§二.GAP-2) — P2
- [ ] WP-FA/GAP-4 — Kelly ATR% placeholder 0.02 (§二.GAP-4) — P2
- [ ] WP-FA/GAP-8 — IPC `evaluate_strategy` / `get_risk_check` still stubs (§二.GAP-8) — P3
- [ ] WP-FA/GAP-9 — Limit-order simulation not implemented (§二.GAP-9) — P3
- [ ] WP-FA/GAP-10 — Provider pricing table not implemented (§二.GAP-10) — P3

**WP-FA total: 5**

### 10.10 WP-MIT — Database / ML (MIT report, 6 sub-items)

Source: `audit_MIT_database_ml_report.md`

- [ ] WP-MIT/DB-1 — DDL V001-V007 draft only, not executed against PG (§1) — P0
- [ ] WP-MIT/DB-2 — ETL ASOF JOIN BIGINT vs TIMESTAMPTZ type mismatch (§8) — P2
- [ ] WP-MIT/DB-3 — Some Timescale hypertables lack compression policy (§9) — P2
- [ ] WP-MIT/ML-1 — `ort` crate not integrated; ONNX `predict()` = None (§5/§6) — P1
- [ ] WP-MIT/ML-2 — Thompson Sampling NIG no PG persistence (§13) — P2
- [ ] WP-MIT/ML-3 — Drift detector does not read from PG (§10) — P2
- [ ] WP-MIT/ML-4 — `scorer_trainer.py` uses 80/20 split, not CPCV (§4) — P2
- [ ] WP-MIT/ML-5 — No end-to-end ML training driver script (§4) — P2
- [ ] WP-MIT/ML-6 — `requirements-ml.txt` missing (§4) — P2

**WP-MIT total: 9**

### 10.11 Per-WP Sub-Item Totals

| WP | Bucket | Sub-Items Added |
|----|--------|----------------:|
| WP-F | GUI Usability (A3) | 47 |
| WP-G | Hardcoded Values (QC) | 43 |
| WP-E4 | Test Coverage (E4) | 34 |
| WP-I | Documentation (R4+TW) | 42 |
| WP-E5 | Optimization (E5) | 20 |
| WP-B | Security (E3) | 12 |
| WP-BB | Bybit API (BB) | 3 |
| WP-CC | Compliance (CC) | 8 |
| WP-FA | Functional Spec (FA) | 5 |
| WP-MIT | Database/ML (MIT) | 9 |
| **Total** | | **223** |

> Note: AI-E contributed 0 new items (already covered by I-19/I-20/I-23 in §3). Grand total 223 sub-items > original ~170 estimate because several clusters (R4 worklogs, TW duplicates, QC low-risk HCs) were expanded to full granularity rather than folded.

*End of §10 sub-checklists. Generated 2026-04-06 by PA follow-up pass for full audit traceability.*

---

## §11 Idle Writer Investigation (2026-04-06)

Follow-up to I-07 DDL verification: 6 writers exist in code but have 0 rows in prod.

| # | Writer | Target | Root Cause | Fix |
|---|---|---|---|---|
| 1 | market_writer | `market.ob_snapshots` | Producer never constructs `OrderbookSnapshot` msg (consumer fully wired) | M — add constructor in ws_client orderbook path |
| 2 | market_writer | `market.trade_agg_1m` | No TradeAggregator module; nobody builds `TradeAgg1m` | M — add aggregator keyed by (symbol, minute) flushing on rollover |
| 3 | market_writer | `market.liquidations` | Upstream WS topic removed (`liquidation.SYMBOL` returns "handler not found", poisons connection) | S — use correct V5 topic `allLiquidation.SYMBOL` or add REST fallback |
| 4 | trading_writer | `trading.position_snapshots` | No periodic "sample positions → send TradingMsg::PositionSnapshot" emitter | XS — add 1s timer in tick_pipeline iterating paper_state.positions |
| 5 | drift_detector | `observability.drift_events` | `run_drift_detector` loop is stub with `TODO(G3-full)` — never reads features or calls `write_drift_event` | L — implement PSI/ADWIN pipeline against features.online_latest + baselines |
| 6 | quality_writer | `observability.data_quality_events` | Single global stale-check gate (`last > 0 && now-last > 30s`) never fires in steady state; no per-symbol checks | S — per-symbol last_tick map + NaN/crossed-spread/gap inline checks |

**Common theme:** Writers 1-4 share the pattern "consumer wired, producer unwritten". Writer 5 is an explicit stub. Writer 6 has an over-restrictive gate. None gated by feature flag — all ship enabled but starved.

**Batch classification:** Fix #4 (XS) → R0 tail. Fix #3 #6 (S) → R1. Fix #1 #2 (M) → R2. Fix #5 (L) → R2/R3.

**Files:** market_writer.rs, trading_writer.rs, drift_detector.rs (L247-278), quality_writer.rs (L49-59), multi_interval_ws.rs (L160-162 liquidation removed), main.rs (L786-876 writer spawn sites).
