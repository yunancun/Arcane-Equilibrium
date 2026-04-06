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
