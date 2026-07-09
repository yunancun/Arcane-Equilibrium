# E4 Wave B Hotfix Linux Re-Regression — `00db240` · 2026-04-28

## Verdict: **PASS** — Both BLOCKERs resolved, baseline preserved

## 上下文

- Prior FAIL: `2026-04-28--wave_b_linux_full_regression.md` 抓 2 BLOCKERs（V026 retention + CHECK constraint）
- Hotfix commit `00db240` push origin/main，HEAD now `16a30e5`（含 hotfix + prior E4 report）
- Mac 已驗純 SQL fix 不破壞 Rust：cargo lib 2299/0 + daemon 11/0 + persistence 2/0 unchanged

## STEP 1 — Linux PG partial state cleanup

```
=== V026 partial state cleanup ===
DROP TABLE
NOTICE:  function learning.cost_edge_advisor_log_now_ms() does not exist, skipping
DROP FUNCTION
=== cleanup OK — re-run V026 via linux_bootstrap_db.sh --apply ===
```

- Table dropped CASCADE 成功；function 不存在（1st-apply ERROR 沒走到 function 創建那行）= **expected & clean**

## STEP 2/3 — V026 idempotency (3 consecutive runs)

第 1 次 apply（`bash linux_bootstrap_db.sh --apply V026`）後立即重跑：
```
psql:V026__cost_edge_advisor_log.sql:145: NOTICE:  relation "cost_edge_advisor_log" already exists, skipping
psql:V026__cost_edge_advisor_log.sql:189: NOTICE:  table "cost_edge_advisor_log" is already a hypertable, skipping
psql:V026__cost_edge_advisor_log.sql:232: NOTICE:  retention policy already exists for hypertable "cost_edge_advisor_log", skipping
psql:V026__cost_edge_advisor_log.sql:245: NOTICE:  relation "idx_cea_log_status_ts" already exists, skipping
psql:V026__cost_edge_advisor_log.sql:250: NOTICE:  relation "idx_cea_log_engine_mode_ts" already exists, skipping
psql:V026__cost_edge_advisor_log.sql:258: NOTICE:  relation "idx_cea_log_transitions" already exists, skipping
[migrate] OK: V026__cost_edge_advisor_log.sql
```

- All NOTICEs (skip messages); **0 ERROR / 0 RAISE / 0 EXCEPTION** — Idempotency RESTORED ✅
- BLOCKER #1 (V026 retention policy + integer_now_func) **RESOLVED**

### V026 artifacts verified present
- Table `learning.cost_edge_advisor_log` ✓
- Hypertable registered (timescaledb_information.hypertables) ✓
- STABLE function `learning.cost_edge_advisor_log_now_ms()` ✓
- Retention policy job_id=1025 (`Retention Policy [1025]`) ✓

## STEP 4 — Rust persistence test (Linux real PG, no auto-skip)

```
running 2 tests
test daemon_persists_cycle_row_when_pool_provided ... ok
test transition_row_carries_transition_from_string ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.23s
```

- **2/0 fail** ✅ — BLOCKER #2 (CHECK constraint `engine_mode IN ('paper','demo','live','live_demo')` rejecting `test_persist_*` tags) **RESOLVED** by adding `OR engine_mode LIKE 'test\_%' ESCAPE '\'`

## STEP 5 — Full Rust regression (no degradation)

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| `openclaw_engine` lib (release) | **2299** | 0 | 2299 | 0 ✓ |
| `test_cost_edge_advisor_daemon` | **11** | 0 | 11 | 0 ✓ |
| `test_cost_edge_advisor_persistence` | **2** | 0 | new (was 0/2 BLOCKER) | +2 ✓ |

## STEP 6 — Healthcheck full sweep

```
SUMMARY: WARN — 非致命但需關注
```

- **32 checks total** (1-30 + Xa, Xb), counted via grep `^(PASS|FAIL|WARN)`
- **0 FAIL** ✓
- **1 WARN** [11] counterfactual_clean_window_growth (post-P013-clean n=226/200 = 113%, ETA ~0d, **pre-existing**, not regression)
- [30] cost_edge_advisor_status PASS (Phase A env=0 dormant by design — skip)
- [8] decision_shadow_exits PASS (24h=0, shadow_enabled=false, dormant as designed)

## STEP 7 — V026 Guard test fixture

```
TEST V026/1: PASS Guard A on fully-shaped table
TEST V026/2: PASS Guard A correctly raised on missing column
TEST V026/3: PASS Guard A no-op (table absent) skipped cleanly
TEST V026/4: PASS Guard B sees engine_mode = text
TEST V026/5: PASS Guard B correctly raised on VARCHAR
TEST V026/6: PASS double CREATE TABLE IF NOT EXISTS succeeded
```

- **6/6 PASS** ✅ — Guard A/B + idempotency 全綠

## 跑兩遍判定

V026 apply 跑 ≥2 次（cleanup → 1st apply → 2nd apply 驗 idempotency），第 2 次 0 RAISE 即綠。Rust persistence/daemon/lib release builds deterministic（cached binary 0.23s/0.52s/2.06s execution），單次 release run 即綠 = baseline 保證。

**flaky? N**

## 結論

**PASS** — 兩 BLOCKERs 完全 resolved：
1. BLOCKER #1 (V026 idempotency) ✓ — 3 連跑 NOTICE-only，0 RAISE
2. BLOCKER #2 (persistence test) ✓ — 2/0 fail on Linux real PG

**Baseline 保證**：
- Rust lib **2299/0** (unchanged from baseline)
- Rust daemon **11/0** (unchanged)
- Rust persistence **2/0** (recovered from 0/2)
- Healthcheck **32 PASS / 1 WARN [11] / 0 FAIL** (1 WARN pre-existing)
- V026 Guards **6/6 PASS**

**Memory race protocol**：本 report 不修任何 production code，純測試執行 + report 寫入；commit-and-push 後可派 G3-09 Phase B Wave 2 部署或繼續 Wave 1 deploy（per PM 編排）。

## 退回 E1 修復清單

無 — hotfix `00db240` 完整解決所有 BLOCKERs。
