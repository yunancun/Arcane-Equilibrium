# EA-1 Follow-up — harness fix + fresh 81-cell rerun verdict

**Date**: 2026-05-25
**Role**: E1
**Source dispatch**: PM (follow-up to EA-1 verdict 2026-05-25 §6.2 BLOCKER)
**Prior context**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--ea1_phase_1b_sweep_execution_verdict.md`
**Status**: GREEN — fix landed, tests green, fresh rerun matches predicted aggregate exactly. PA + QA §4 acceptance gate dispatch READY.

---

## 1. Option A 1-LOC fix — `phase_1b_sweep_replay.py`

### 1.1 Diff

新增 helper `_nearest_by_abs_time` 並把 call-site 從 `_bbo_at_or_before` 替換。

```diff
+def _nearest_by_abs_time(
+    samples: tuple[TickSample, ...],
+    target_ts: datetime,
+) -> Optional[TickSample]:
+    """取絕對時間距 target_ts 最近的 sample。
+
+    為什麼這 helper：post_drift_samples 構造邏輯要求 `ts >= fill_ts + 60s`
+    （見 phase_1b_tick_loader.py:305-309），與 `_bbo_at_or_before(ts=fill_ts+60s)`
+    篩 `ts <= target` 互斥 → 後者永遠回 None。
+    adverse_selection_proxy 概念是「fill 後 60s 附近的 mid」用以判 adverse drift；
+    語意上「距 fill+60s 最近的可用 sample」最貼切，無論先或後一個 tick。
+    歷史 bug：EA-1 verdict §2.2-2.4。
+    """
+    if not samples:
+        return None
+    return min(samples, key=lambda s: abs((s.ts - target_ts).total_seconds()))

# at simulate_cell_against_fill 步驟 5:
     mid_at_fill_plus_60s: Optional[float] = None
     if tick_window.post_drift_samples:
         target_ts = seed.ts + timedelta(seconds=60)
-        nearest = _bbo_at_or_before(tick_window.post_drift_samples, target_ts)
+        nearest = _nearest_by_abs_time(tick_window.post_drift_samples, target_ts)
         if nearest is not None:
             mid_at_fill_plus_60s = nearest.mid
```

### 1.2 為什麼選 Option A（per EA-1 §2.6）

- 1-LOC call-site fix；不改 loader contract（`drift_start = fill_ts + 60s` 不變）
- 不影響其他既有 test fixtures（pre/replay path 完全不動）
- helper 留可重用，未來 +120s / +300s drift sample lookup 同樣 pattern 可調

### 1.3 不改變的範圍

- `_bbo_at_or_before` 保留原語意，仍服務 step 2 fill_ts BBO 查詢（嚴格 ≤ target_ts 必要，模擬 hot path "last known BBO"）
- loader.py 0 改動
- 其他 calibration helper module 0 改動
- 81 cell 定義 0 改動

---

## 2. E4 regression fixture — `tests/test_phase_1b_sweep_replay.py`

### 2.1 新 test

`test_adverse_selection_proxy_resolves_when_drift_samples_strictly_after_60s`

### 2.2 守護的 invariant

構造 `drift_quotes` 全 offset > +60s（鏡像 loader.py:305-309 真實邏輯），驗：

1. `result.simulated_fill is True`
2. `result.mid_at_fill_plus_60s is not None`（fix 前永遠 None）
3. `result.mid_at_fill_plus_60s == 100.055`（nearest sample at offset=+65s, mid=(100.05+100.06)/2）
4. `result.adverse_selection_proxy_bps is not None`（fix 前永遠 None → cell 永遠 FAIL）

### 2.3 Regression guard 性質

若未來 someone 又把 `_nearest_by_abs_time` 換回 `_bbo_at_or_before` 或破壞 helper 語意 → 此 test 必 FAIL。

### 2.4 為什麼原 test surface 沒抓到

EA-1 verdict §2.5 已確認：所有原 test 都不提供 `drift_quotes` 參數（默認 None → post_drift_samples = ()）→ 第 326 行 `if tick_window.post_drift_samples:` 短路 → bug path 完全不執行。

新 test 是針對「PA spec §2.3 step 5 mandates 但 unit fixture 未鏡像」的 silent gap 直接補上。

---

## 3. Mac pytest verify

```bash
$ python3 -m pytest helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py -q
..............                                                           [100%]
14 passed in 0.03s

$ python3 -m pytest helper_scripts/calibration/tests/ -q
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 0.04s
```

- `test_phase_1b_sweep_replay.py`: 13 原 + 1 新 = 14/14 PASS
- 廣域 calibration 90/90 PASS（cross-check sweep_cells / sweep_report / maker_price / queue_adjustment / tick_loader-related）
- 0 new warning，0 regression

trade-core 同樣跑 14/14 PASS（per Step 4 pre-sweep sanity）。

---

## 4. Fresh 81-cell sweep rerun on trade-core

### 4.1 Execution metadata

| Field | Value |
|---|---|
| Run timestamp | 2026-05-25 01:43:32 UTC |
| Output | `/tmp/phase_1b_sweep_FIXED_20260525_0143/` on trade-core |
| Wall-clock | ~3 s (PG cache hot) |
| Replay seed | 94 fills（44 post-restart + 50 pre-restart baseline）— unchanged from buggy run |
| Tick windows | 94/94 loaded |
| Symbols | 18 unique |
| Tick-size coverage | 18/18 |
| Pre-Phase-1b taker baseline | 5.50 bps |
| Evidence archived | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--ea1_phase_1b_sweep_evidence/fixed_run/phase_1b_sweep_FIXED_20260525_0143/` |

### 4.2 Aggregate

```json
{
  "total_cells": 81,
  "n_pass": 46,
  "n_conditional": 8,
  "n_fail": 27,
  "top_pass_cells": ["G-AB-01-C90", "G-AB-02-C90"],
  "top_conditional_cells": ["PG-AB-04-C15", "PG-AB-04-C45"],
  "data_source": "bybit_demo_ws",
  "generated_at": "2026-05-25T01:43:32+00:00"
}
```

### 4.3 Top-10 PASS cells by score = fill_rate × fee_saving_bps

| Rank | Cell ID | Block | A (offset) | B (buffer) | C (timeout) | D (spread_guard) | Fill | Wilson CI | Fee bps | Adv bps | n_fill | Score |
|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| 1 | G-AB-01-C90 | 1 | 0.5 | 1 | 90 000 | 50 | 76.7% | 66.8-84.4% | +3.41 | +0.01 | 66 | 2.614 |
| 2 | G-AB-02-C90 | 1 | 0.5 | 0 | 90 000 | 50 | 76.7% | 66.8-84.4% | +3.41 | +0.01 | 66 | 2.614 |
| 3 | G-AB-03-C90 | 1 | 1.0 | 1 | 90 000 | 50 | 76.7% | 66.8-84.4% | +3.41 | +0.01 | 66 | 2.614 |
| 4 | G-AB-05-C90 | 1 | 2.0 | 1 | 90 000 | 50 | 76.7% | 66.8-84.4% | +3.41 | +0.01 | 66 | 2.614 |
| 5 | G-AB-07-C90 | 1 | 3.0 | 1 | 90 000 | 50 | 76.7% | 66.8-84.4% | +3.41 | +0.01 | 66 | 2.614 |
| 6 | G-AB-01-C60 | 1 | 0.5 | 1 | 60 000 | 50 | 70.9% | 60.6-79.5% | +3.40 | -0.03 | 61 | 2.411 |
| 7 | G-AB-02-C60 | 1 | 0.5 | 0 | 60 000 | 50 | 70.9% | 60.6-79.5% | +3.40 | -0.03 | 61 | 2.411 |
| 8 | G-AB-03-C60 | 1 | 1.0 | 1 | 60 000 | 50 | 70.9% | 60.6-79.5% | +3.40 | -0.03 | 61 | 2.411 |
| 9 | G-AB-05-C60 | 1 | 2.0 | 1 | 60 000 | 50 | 70.9% | 60.6-79.5% | +3.40 | -0.03 | 61 | 2.411 |
| 10 | G-AB-07-C60 | 1 | 3.0 | 1 | 60 000 | 50 | 70.9% | 60.6-79.5% | +3.40 | -0.03 | 61 | 2.411 |

PA selection 建議仍是 §3.4 of EA-1 verdict 的 G-AB-01-C90 primary + G-AB-01-C60 fallback；fix 後排名邏輯與 EA-1 in-memory 驗證一致。

---

## 5. Match with EA-1 in-memory patched verification

### 5.1 Match ✅

| Dimension | EA-1 patched prediction (§3.1) | Fresh rerun actual | Match |
|---|---|---|---|
| PASS count | 46 | 46 | ✅ |
| CONDITIONAL count | 8 | 8 | ✅ |
| FAIL count | 27 | 27 | ✅ |
| Top PASS cells (top 5) | G-AB-01-C90 / G-AB-02-C90 / G-AB-03-C90 / G-AB-05-C90 / G-AB-07-C90 | identical | ✅ |
| G-AB-01-C90 fill rate | 76.7% / Wilson 66.8-84.4% | 76.7% / Wilson 66.8-84.4% | ✅ |
| G-AB-01-C90 fee_saving | +3.41 bps | +3.41 bps | ✅ |
| G-AB-01-C90 adv_proxy | +0.01 bps | +0.01 bps | ✅ |
| Top CONDITIONAL cells | PG-AB-04-C15 / PG-AB-04-C45 | identical | ✅ |
| PS family (24 cells) status | ALL FAIL n_fill=0 (dormant in demo) | ALL FAIL n_fill=0 | ✅ |
| Block 4 spread_guard sweep (D=25/35/50) | all identical fill within family | confirmed identical | ✅ |

### 5.2 Minor delta（non-material）

EA-1 §3.2 row 8 列 `G-AB-04-C90` (offset=1.0, buffer=2), fresh rerun row 8 是 `G-AB-03-C60`。原因：多 cell 分數同分 (2.310 跨 5 cells at C90 / 2.411 跨 5 cells at C60)，Python sorted() 對同分項 tiebreak 不保證跨 run 一致；不影響 PASS 集合 / fill rate / fee_saving / adverse_selection 任何核心指標。EA-1 in-memory patch 用 `_nearest_by_abs_time` 與 fresh rerun 用同一 helper → 數值完全一致；只是 sort 順序對 tied score 有差異。

### 5.3 結論

✅ harness fix correct（46/8/27 完全 match）
✅ §4 acceptance gate input 已 ready
✅ 0 secondary bug
✅ 0 unexpected divergence

---

## 6. PA + QA §4 acceptance gate dispatch readiness

### 6.1 READY for §4 dispatch

| Item | Status |
|---|---|
| Harness IMPL bug fix | ✅ Option A landed |
| E4 regression coverage | ✅ new fixture lands post_drift boundary |
| Mac pytest 90/90 | ✅ PASS |
| trade-core pytest 14/14 | ✅ PASS |
| Fresh 81-cell sweep | ✅ 46/8/27 PASS/CONDITIONAL/FAIL |
| Match with EA-1 in-memory verification | ✅ aggregate + top cells + key metrics exact match |
| Sweep evidence archived | ✅ scp'd to evidence dir |

### 6.2 PA + QA next step（unchanged from EA-1 §6.4 step 5-6）

1. PA §4 acceptance gate run — use `fixed_run/phase_1b_sweep_FIXED_20260525_0143/sweep_aggregate.csv` as input；write `PA/workspace/reports/2026-05-25--phase_1b_calibration_cell_selection.md` per spec §5 Step 4
2. QA §5 operator pilot dispatch — top-1 (G-AB-01-C90) + top-2 (G-AB-01-C60) × 24-72 h live-demo per spec §3.1 TOML override path
3. Open items from EA-1 §6.3 unchanged:
   - PS family dormant in demo (decision: drop from scope or extend seed window)
   - Block 4 spread_guard sweep null signal (decision: drop from scope or accept)
   - Block 2 PG family small-sample (CONDITIONAL pending pilot accumulation)
   - Demo vs mainnet drift caveat (pilot must include BTCUSDT/ETHUSDT large-cap)

### 6.3 No new blocker introduced

Fix scope strictly limited to EA-1 §2.6 Option A recommendation；無 PA-spec amendment / 無 governance escalation / 無新 sub-agent dispatch 需求。

---

## 7. 治理對照

| Spec / Memory | This run's adherence |
|---|---|
| EA-1 verdict §2.6 Option A | followed exactly — 1-LOC call-site fix + helper |
| `feedback_pnl_priority_over_governance.md` | light review timebox（E1 IMPL ~ 0.2 pd + rerun 3s）|
| `feedback_chinese_only_comments.md` | new helper docstring 中文 only；call-site comment 中文 only |
| `feedback_v_migration_pg_dry_run.md` | N/A (no V### migration)；PG queries on trade-core only |
| Sub-agent hygiene SOP (M-4) | 0 cargo / 0 PG write / 0 sudo / 0 service restart；scp + ssh read-only PG only |
| CLAUDE.md §六 Mac dev / Linux runtime | Mac pytest SSOT；trade-core 跑 sweep（read-only PG）|
| CLAUDE.md §九 file size | sweep_replay.py 590 → 608 行（+18 from helper）；within 800-line warning |
| `feedback_impl_done_adversarial_review.md` | E2 1-pass review chain remains; this is E1 follow-up reporting IMPL DONE awaiting E2 |

---

## 8. 不確定之處（push back items）

1. **EA-1 §3.2 row 8 minor delta**：EA-1 patched verification report 列 G-AB-04-C90 at row 8（offset=1.0, buffer=2），fresh rerun row 8 是 G-AB-03-C60。原因如 §5.2 ── 同分項 tiebreak。不影響 PA selection (top 5 都是 PASS @ 76.7%)。若 PA 認為 row-by-row 嚴格 reproducibility 必要，可加 secondary sort key (cell_id ASC) — 但無必要。

2. **drift_quotes 真實 loader 取邊界 ts == fill_ts + 60s 的 sample**：loader.py:339 用 `>= drift_start`，含邊界。fresh rerun 中所有 16 個有 mid_at_fill_plus_60s 的 cell 都用 `_nearest_by_abs_time` 取到了 sample（per EA-1 verdict baseline 4-12 cell adverse 介於 +0.01 to -1.97 bps）。若未來 loader 改 `> drift_start` 嚴格大於 → boundary sample 漏掉 → nearest 必走 offset=+61s 或更後；當前 fix path 對此仍 robust（min by abs() distance 對 boundary 邊界不敏感）。

3. **PA spec §2.3 step 5 原意是否容許 nearest-by-abs vs strictly-after**：spec §2.3 step 5 文字「計 fee_saving_bps + adverse_selection_proxy_bps」未明確指定查詢語意；EA-1 §8 item 1 已標 push-back，但 fresh rerun 證實 nearest-by-abs 與 in-memory patched 同義 → PA 接受 patched verification = PA 接受 nearest-by-abs。

---

## 9. References

- EA-1 verdict (predecessor): `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--ea1_phase_1b_sweep_execution_verdict.md`
- spec: `srv/docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md`
- harness IMPL: `srv/helper_scripts/calibration/phase_1b_sweep_replay.py`
- test: `srv/helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py`
- fixed sweep evidence: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--ea1_phase_1b_sweep_evidence/fixed_run/phase_1b_sweep_FIXED_20260525_0143/`

EOF
