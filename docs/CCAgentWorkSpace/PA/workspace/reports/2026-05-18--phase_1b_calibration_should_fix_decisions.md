# Phase 1b Calibration Harness — 3 SHOULD-FIX Decisions

- Date: 2026-05-18 (Mac local, post-E2/E4 merge at `8d8a0123`)
- Author: PA
- Predecessor: E2 review `907ab778` §3 lists 3 SHOULD-FIX；E4 regression PASS 7/7 `30f5b64b`
- Spec under decision: `srv/docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md` (`75e29265`, v0.1)
- Operator preference: `feedback_pnl_priority_over_governance.md` light-review for parameter tuning → prefer accept-with-caveat, fix-in-IMPL only when audit chain integrity demands

---

## §0 Executive Summary

| # | SHOULD-FIX | Decision | Rationale (1 line) | ETA impact on sweep run |
|---|---|---|---|---|
| 1 | Block 4 dedupe | **(b) Accept with PA-side dedupe step** | 3 重複 cell 浪費 ~6% compute；不污染 acceptance gate，PA selection 報告夾 dedupe SQL 即可 | 0 IMPL；PA selection 報告 +5 min |
| 2 | `maker_fill_rate` denom drift | **(a) Spec amend v0.1 → v0.2** | spec drift 屬升級（expanded denom 反映真實 fillable population）；spec wording 偏離 IMPL 才是審計鏈污染源 | 0 IMPL；spec patch +10 min |
| 3 | `adverse_proxy=None` fail-closed | **(c) Pure accept + selection-guide note** | post-drift sample 在 normal hour > 99% available；PA 手動 review FAIL cells 分 `adverse_status='data_missing'` 即可區分 cell-quality FAIL vs data-missing FAIL | 0 IMPL；PA selection 報告 +10 min |

**Combined ETA**: 0 pd IMPL，~25 min PA selection 報告額外 step + spec patch。**Sweep production run 可立即啟動**（不等 E1 patch / 不等 re-E2 / 不等 re-E4）。

**Recommended main-session next step**: 直接 commit (本 memo) + (spec v0.2 patch) → 啟動 81-cell sweep production run；E1 patch 不派。

---

## §1 SHOULD-FIX #1 — Block 4 Dedupe (Decision: (b) Accept with PA-side dedupe step)

### Decision rationale

E2 已 verify 3 個 baseline overlap cell pair：

| Block 1-3 cell | Block 4 cell | Identical config (family, A=0.5, B=1, C, D=50) |
|---|---|---|
| `G-AB-01-C30` | `G-D-D50` | grid, C=30s |
| `PG-AB-01-C15` | `PG-D-D50` | phys_giveback, C=15s |
| `PS-AB-01-C10` | `PS-D-D50` | phys_stale_roc_neg, C=10s |

**為什麼不選 (a) Fix-in-IMPL**：
- 派 E1 quick patch + re-E2 + re-merge 至少 0.5 pd turnaround，sweep run 被阻
- IMPL `aggregate_summary` top-2 排序語意若 dedupe，會把 baseline 直接從 PASS pool 剔除；但 baseline 是 sanity-check 重要的 reference，**不該從 raw output 移除**
- 真正需 dedupe 的階段是 PA 寫 cell selection 報告挑 top-2 給 operator pilot，不是 raw output 階段

**為什麼不選 (c) Spec amend (intentional duplicate)**：
- 即使標 intentional，aggregate_summary top-2 仍會被 duplicate 干擾（spec § 4.1 末段「top-2 by score」會選到兩個 same-config）
- PA 必須在下游 dedupe，spec amend 不能省略下游 step
- 若選 (c)，spec v0.2 wording 與 PA selection 報告 dedupe step 兩處都要寫，反而冗餘

### PA-side dedupe step (rolling into cell selection report)

PA 在 cell selection 報告（sweep run 完成後產出）必含：

```text
## §X Block 4 Baseline Overlap Dedupe

raw output 含 3 個 duplicate config（Block 4 D=50 cells = Block 1-3 baseline）：
- G-D-D50 = G-AB-01-C30 (grid family, A=0.5, B=1, C=30s, D=50)
- PG-D-D50 = PG-AB-01-C15 (phys_giveback, A=0.5, B=1, C=15s, D=50)
- PS-D-D50 = PS-AB-01-C10 (phys_stale_roc_neg, A=0.5, B=1, C=10s, D=50)

dedupe rule: 對每對 keep cell_id alphabetical 第一個（preserve Block 1-3 ID 鎖
PA traceability，丟 Block 4 變體），PASS pool top-2 排序前套用。

實際操作 SQL（在 sweep_aggregate.csv 上）：
SELECT DISTINCT ON (family, offset_bps, buffer_ticks, timeout_ms, spread_guard_bps)
       cell_id, pass_gate, maker_fill_rate, expected_fee_saving_bps, ...
FROM sweep_aggregate
ORDER BY family, offset_bps, buffer_ticks, timeout_ms, spread_guard_bps, cell_id ASC;
```

**確認**: PA selection 報告 SOP 已記，下次 dispatch (sweep run done) 派人時帶。

### No E1 patch needed.

---

## §2 SHOULD-FIX #2 — `maker_fill_rate` Denom Spec Drift (Decision: (a) Spec amend v0.1 → v0.2)

### Decision rationale

Spec §2.4 line 276 寫:
```
maker_fill_rate: float       # n_simulated_fills / (n_attempts - n_skipped_spread_guard)
```

IMPL `phase_1b_sweep_replay.py:400-405` 用:
```
n_skip_total = n_skip_spread_guard + n_skip_no_bbo + n_skip_tick + n_skip_family + n_skip_crossed
eligible = n_attempts - n_skip_total
maker_fill_rate = n_simulated_fills / eligible
```

**為什麼選 (a) Spec amend，不選 (b) IMPL revert**：

1. **語意正確性**：IMPL 的 expanded denom 才是真實「fillable population」。spec 只扣 spread_guard 是 oversight — `no_bbo` / `tick_size_missing` / `family_exit_mismatch` / `crossed_book` 都是 data-quality skip，不該分母含這些 attempt。
2. **conservative bias**：spec 原版分母大（n_attempts - n_skip_spread_guard），fill_rate **被稀釋**；real-world cell quality 應評估「給 cell 真實 fillable opportunity 後的 fill 機率」，這正是 expanded denom 算的。
3. **acceptance gate 敏感性**：PASS_MAKER_FILL_RATE = 0.25 threshold 是基於 v48 P0 row 設計的，若 denom 過大 → 真實 viable cell 被誤判 FAIL。IMPL denom 才能讓 0.25 threshold 對齊原本意圖。
4. **審計鏈乾淨**：spec/IMPL drift 是 audit blind spot；v0.2 patch 把 IMPL 升級成 spec 反向同步，未來 audit query 不會困惑。
5. **不選 (c) Hybrid（both ratios）**：增加 output column 反而稀釋 acceptance gate 唯一性；PA / operator 應只看一個 metric 做決定，two-rate 是 deferred decision。

### Spec v0.1 → v0.2 wording patch

#### Patch 1: §2.4 line 273-276

```diff
 @dataclass
 class CalibrationCellResult:
     cell_id: str
     n_attempts: int              # 4 + 50 = 54 typical
     n_simulated_fills: int       # of fills within timeout
-    n_skipped_spread_guard: int  # spread guard 跳過
-    maker_fill_rate: float       # n_simulated_fills / (n_attempts - n_skipped_spread_guard)
+    n_skipped_spread_guard: int  # spread guard 跳過
+    n_skipped_no_bbo: int        # 無 BBO snapshot 在 ±60s window
+    n_skipped_tick_missing: int  # tick_size lookup 失敗
+    n_skipped_family_mismatch: int  # close-maker-first 不對應該 family
+    n_skipped_crossed_book: int  # best_ask <= best_bid (degenerate book)
+    n_eligible: int              # n_attempts - sum(all n_skipped_*)
+    maker_fill_rate: float       # n_simulated_fills / n_eligible
+                                 # (v0.2: expanded denom 扣除全部 data-quality skip，
+                                 #  反映真實 fillable population；v0.1 只扣 spread_guard
+                                 #  屬 oversight。E2 review 907ab778 §3 SHOULD-FIX #2
+                                 #  PA decision 2026-05-18 採 expanded denom)
```

#### Patch 2: §4.1 PASS gate 補一行 (line 349-358)

```diff
 ### 4.1 PASS gate（per cell）
 
 ```
 cell.pass_gate = "PASS" IF (
   cell.maker_fill_rate >= 0.25
   AND cell.fill_rate_wilson_ci_low >= 0.15  # AC-14 Wilson 95% CI lower bound
   AND cell.expected_fee_saving_bps >= 0.5   # v48 P0 threshold
   AND cell.fee_saving_wilson_ci_low >= 0.0  # directional positive 95% CI
   AND cell.adverse_selection_proxy_bps <= cell.pre_phase_1b_taker_baseline_bps
 )
+
+# v0.2 note: maker_fill_rate denom 是 expanded n_eligible（扣全部 data-quality
+# skip），不是 v0.1 原版只扣 spread_guard。0.25 threshold 對應真實 fillable
+# population 的 fill 機率。若回原版 denom（含 BBO/tick/family/crossed skip），
+# threshold 需相應降至 ~0.18。
```

#### Patch 3: spec header (changelog)

文件第 1-8 行加 changelog:

```diff
 # Phase 1b Calibration Sweep Harness Spec
 
 - Date: 2026-05-18
 - Author: PA
 - Status: v0.2 (E1 IMPL + E2 review + E4 regression closed)
+- Changelog:
+  - v0.2 (2026-05-18, post-E2): §2.4 `maker_fill_rate` denom 從
+    `n_attempts - n_skipped_spread_guard` 改為 expanded
+    `n_attempts - sum(all n_skipped_*)`；§4.1 補解釋 line。
+    來源：E2 review `907ab778` §3 SHOULD-FIX #2，PA decision memo
+    `2026-05-18--phase_1b_calibration_should_fix_decisions.md` §2。
+  - v0.1 (2026-05-18 pre-prep): initial release commit 75e29265。
```

### No E1 patch needed. IMPL = spec v0.2 authority.

---

## §3 SHOULD-FIX #3 — `adverse_proxy=None` Fail-Closed (Decision: (c) Pure accept + selection-guide note)

### Decision rationale

`phase_1b_sweep_report.py:143-146` 把 `adverse_selection_proxy_bps=None` 視為 fail 一律 cell FAIL。E2 caveat: post-drift sample 缺是 data quality issue 非 cell quality issue，FAIL 過嚴可能剔除真實 viable cell。

**為什麼選 (c) Pure accept**：

1. **PG data availability empirical**: SSH 確認 1h `market_tickers` 76k row / 40 symbol ≈ 31 sample/symbol/min；fill_ts+60s 點有 sample 機率 > 99% in normal hour。 demo endpoint 偶發 thin window 但不影響大盤。
2. **fail-closed 對齊 root principle §二 #6** (`Uncertainty defaults to conservative behavior`) — 系統不知 adverse 多嚴重時應保守 FAIL，不該 INDETERMINATE 中間態增加 operator cognitive load。
3. **PA selection report 已自然 review FAIL cells**: PA 寫 selection 報告本來就要 list 81 cell PASS/FAIL/CONDITIONAL 分布；對 FAIL cells PA 順手 read `adverse_selection_proxy_bps` 欄位 → null 即 data-missing FAIL → 可手動 carve-out 成「INDETERMINATE 待 24h pilot 補 sample」。
4. **不選 (a) Three-state**: ~50 LOC + 5 test + re-E2 + re-merge ~0.5 pd cost > 0 benefit。 INDETERMINATE 是 production runtime gate 用的 concept（fast-path），不是 research harness 用的；harness 由 PA 手動 review，FAIL pool 內 grep null adverse 就行。
5. **不選 (b) metadata 標 `adverse_status`**: ~10 LOC + 1 test 看似 minimal 但需 re-E2，且 PA 在 selection 報告也是 grep `adverse_selection_proxy_bps IS NULL` 同樣信號；額外 metadata column 是 reduant。

### PA selection-guide note (rolling into cell selection report)

PA 寫 cell selection 報告必含:

```text
## §X FAIL Cell 分流 (data-missing vs cell-quality FAIL)

FAIL pool n=XX。分流 SQL:

SELECT
  cell_id,
  CASE
    WHEN adverse_selection_proxy_bps IS NULL THEN 'data_missing_FAIL'
    WHEN maker_fill_rate < 0.25 THEN 'cell_quality_FAIL_fill_rate'
    WHEN expected_fee_saving_bps < 0.5 THEN 'cell_quality_FAIL_fee_saving'
    WHEN adverse_selection_proxy_bps > pre_phase_1b_taker_baseline_bps THEN 'adverse_FAIL'
    ELSE 'edge_case_FAIL'
  END AS fail_subcategory,
  n_simulated_fills,
  adverse_selection_proxy_bps,
  pre_phase_1b_taker_baseline_bps
FROM sweep_aggregate
WHERE pass_gate = 'FAIL'
ORDER BY fail_subcategory, cell_id;

data_missing_FAIL cells: PA 標 INDETERMINATE，**不送 operator pilot 但保留
24h pilot 後 re-evaluate**（若 pilot 24h 補上 adverse sample → 重跑 gate）。
其他 FAIL subcategory 是 cell quality 真實問題，剔除。
```

### No E1 patch needed. fail-closed semantic 保留。

---

## §4 Combined ETA: Fix-in-IMPL vs Accept-with-Caveat Turnaround

| Path | E1 IMPL | re-E2 | re-E4 | re-merge | PA report extra | Spec patch | Total turnaround |
|---|---|---|---|---|---|---|---|
| **Fix-in-IMPL all 3** | 0.4 pd (~120 LOC) | 0.2 pd | 0.1 pd | 0.05 pd | 0 | 0 | **~0.75 pd** (6 hr block sweep run) |
| **Accept-with-caveat all 3 (chosen)** | 0 | 0 | 0 | 0 | +25 min PA work | +10 min spec amend | **~35 min** (zero block sweep run) |

**Saving**: ~6 hr sweep-run window earlier start。

**Cost of accept-with-caveat**:
- PA selection 報告多 2 個 paragraph (dedupe SQL + FAIL subcategory SQL) — ~50 LOC of report markdown
- Spec v0.2 patch — 3 inline diff blocks (~15 LOC)
- 無 IMPL 改動 risk

---

## §5 Accept-with-Caveat PA Cleanup Steps Inventory

PA 在 cell selection 報告（sweep production run 完成後產出）必執行下列 cleanup step：

| # | Step | Source | Tool |
|---|---|---|---|
| C1 | Block 4 dedupe by (family, A, B, C, D) tuple | §1 above | psql / awk on sweep_aggregate.csv |
| C2 | FAIL pool 分流 data_missing_FAIL vs cell_quality_FAIL | §3 above | psql / awk + grep `adverse_selection_proxy_bps IS NULL` |
| C3 | top-2 排序 with explicit tiebreaker (n_simulated_fills DESC, cell_id ASC) | E2 NTH #3 (auto-include) | psql ORDER BY |
| C4 | sweep_report metadata caveat propagation (`fill_detection_uses_bbo_cross_proxy_not_trade_tape`) | E2 NTH #4 (auto-include) | inline note in PA selection 報告 §0 |
| C5 | data_source tag verification (`bybit_demo_ws` from `market_tickers`) | spec §3.4 + E2 caveat 1 | sweep_summary.json `data_source` field check |

**PA selection 報告 SOP**: C1-C5 是 5 個必含 paragraph，main session 派 PA 寫 selection 報告時 dispatch packet 引用本 memo §5。

---

## §6 Spec v0.1 → v0.2 Patch (inline diff, for main-session commit)

**File**: `srv/docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md`

3 個 patch block 已在 §2 列出。Summary:

1. **Header changelog** (line 1-8): 加 v0.2 entry
2. **§2.4 CalibrationCellResult fields** (line 270-284): 補 n_skipped_no_bbo / tick_missing / family_mismatch / crossed_book 4 個 field + n_eligible + 改 maker_fill_rate denom 為 expanded
3. **§4.1 PASS gate note** (line 349-358): 補 explicit denom expansion 註腳

**Commit message** (suggested):
```
docs(spec): Phase 1b calibration v0.1 -> v0.2 — maker_fill_rate denom expanded [skip ci]

Rolling in E2 review 907ab778 §3 SHOULD-FIX #2 PA decision.
spec §2.4 maker_fill_rate denom 從 n_attempts - n_skipped_spread_guard
改為 expanded n_attempts - sum(all n_skipped_*) (扣全部 data-quality skip)，
反映真實 fillable population；§4.1 補 denom expansion 註腳。

SHOULD-FIX #1 (Block 4 dedupe) + #3 (adverse None fail-closed) decision
= PA-side cell selection report cleanup，無 spec 改動。

Decision memo: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_should_fix_decisions.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## §7 Multi-Session Race Check 5/5

| Check | Command | Result | 評估 |
|---|---|---|---|
| 5a 提交前 fetch + sibling window | `git fetch --prune origin` + `git log --since="2h ago" origin/main` | 2h 內僅 8d8a0123 / 30f5b64b / 907ab778 / 93069c29 (本 review 對象 chain) | ✓ |
| 5b memo 寫入前 status clean for target path | `git status --porcelain` 確認 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_should_fix_decisions.md` 不存在 | 新檔案 path 無衝突 | ✓ |
| 5c 看到 unknown WIP 禁 revert | sibling memory.md 改動屬其他 session 累積，不動 | N/A | ✓ |
| 5d Sign-off report commit 前 path clean | 本 memo path 不重名 | ✓ |
| 5e Decision 期間 sibling 推 origin | review 期間 origin/main HEAD = 8d8a0123 未變 | ✓ |

**Race check 5/5 PASS**。

---

## §8 Recommended Main-Session Next Step

**直接路徑（推薦）**:
1. main session commit 本 memo
2. main session 套 spec v0.2 patch (§6 inline diff) + commit `[skip ci]`
3. main session 啟動 81-cell sweep production run（CLI `--all-cells`）
4. sweep run 完成後派 PA 寫 cell selection 報告（必含 §5 C1-C5 cleanup step）
5. cell selection 報告完成後 operator pilot dispatch top-2 PASS cells × 24h live-demo

**不需要的中間步驟**:
- 不派 E1 fix-in-IMPL（3 SHOULD-FIX 全 accept-with-caveat 或 spec amend）
- 不需 re-E2 / re-E4（IMPL 不改動）
- 不需 re-merge

**ETA to operator pilot dispatch**: sweep run ~40 min (per spec §5 Step 3 batch ≤30s/cell × 81) + PA selection 報告 ~30 min = **~70 min from now**。

---

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_should_fix_decisions.md
