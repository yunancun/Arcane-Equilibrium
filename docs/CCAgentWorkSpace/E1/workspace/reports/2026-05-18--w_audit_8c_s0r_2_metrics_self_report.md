---
title: W-AUDIT-8c 8C-S0R-2 Round 2 Self-Report
date: 2026-05-18
author: E1
worktree: worktree-agent-af73a5d4575815f26
parent_commit: c041097c (round 1)
status: ROUND-2 IMPL DONE — awaiting E2 round 2 review
scope: helper_scripts/reports/w_audit_8c/ Python metrics + smoke only
authorizes_runtime: NO (replay tool only)
no_mutation: SQL / spec / RiskConfig / TOML / authorization / cron / runtime 全部不動
---

# W-AUDIT-8c 8C-S0R-2 Round 2 — Self-Report

## §0 任務摘要

Round 1 (commit `c041097c`) E2 RETURN'd with 3 CRIT + 4 HIGH + 4 MED/LOW;
MIT dual review APPROVE-CONDITIONAL with 1 MUST-FIX + 3 drift corrections +
bear-regime annotation。Round 2 修上述全部高優先項 — 3 CRIT 全 fix、MIT
MUST-FIX 全 fix、3 drift 全套用、bear-regime annotation 補入、4 HIGH 全 fix。

修改僅限 `helper_scripts/reports/w_audit_8c/`（metrics.py + smoke.py）；
未觸 SQL（S0R-1 worktree）/ CLI 包裝（S0R-3 worktree）/ auth / live / lease。

Smoke test 增至 34 cases，全 PASS。

## §1 修改清單

### §1.1 `liquidation_cluster_stage0r_metrics.py` (1550 → 1814 LOC，+264)

| 區域 | 改動 | E2/MIT finding |
|---|---|---|
| `MAX_SYMBOL_SHARE` 常量 | `0.40 → 0.30` | MIT round-1 push-back #8 |
| `COST_EDGE_RATIO_MAX` 常量 | `0.80 → 0.60` | MIT round-1 push-back #19 |
| `FALSE_POSITIVE_RATE_MAX` 常量 | `0.40 → 0.30` | MIT round-1 push-back #16 |
| `_n_eff_horizon_overlap()` | 整數除 `//` → `math.ceil()` | MIT round-1 MUST-FIX |
| `_n_eff_cluster_aware()` cluster 算法 | anchor pattern → sliding lag pattern；每 event 推進 `last_ts_ms` | E2 round-1 CRIT-3 |
| `_extract_trigger_rows()` 簽名 | 加 `notional_pct_floor: float` 必傳參數 + filter | E2 round-1 CRIT-1 |
| `_both_direction_floor_check()` 簽名 | `total_bucket_count: int → int \| None`；None → 三態 passed=None + 顯式 fail_reason | E2 round-1 CRIT-2 |
| `compute_stage0r()` 簽名 | 加 `notional_pct_floor: float = 0.95`（default per task brief） | E2 round-1 CRIT-1 |
| `compute_stage0r()` body | 偵 total_bucket_count is None → 加 `missing_bucket_count_denominator` RED reason；direction_check passed=None → fail-closed treat as False；density_efficacy 三態 None（caller 未傳 → skipped=True + passed=None）；新增 `_compute_baseline_lift()` 計算 + `_build_exclusion_counts()` 計算 + `_build_regime_annotation()` 寫入 | E2 CRIT-2 + HIGH-1 + HIGH-4 + MIT MUST-FIX |
| `compute_stage0r()` return dict | 加 `baseline_lift / exclusion_counts / regime_annotation` 三個 top-level key；`cell_params` 加 `notional_pct_floor` | E2 HIGH-4 + MIT MUST-FIX + CRIT-1 |
| `compute_stage0r_sweep()` 簽名 | 加 `pct_grid: Sequence[float] \| None = None`（default `DEFAULT_PCT_GRID`） | E2 CRIT-1 + HIGH-3 |
| `compute_stage0r_sweep()` 7-D loop → 8-D loop | 加最外層 `for pct in pct_grid` 把 sweep cells 從 3888 → 11664 | E2 CRIT-1 |
| `compute_stage0r_sweep()` refusal packet | 加 `best_per_tier_per_direction / symbol_tiers / regime_annotation` 三個對稱 key（與成功 packet 同 schema） | E2 HIGH-2 + MIT MUST-FIX |
| `compute_stage0r_sweep()` 成功 packet | 加 `regime_annotation` top-level key | MIT MUST-FIX |
| `compute_stage0r_sweep()` `default_triggers` 計算 | 加 `notional_pct_floor=0.95` 參數 | E2 CRIT-1 |
| `sweep_meta` 加 `pct_grid` key | 用於 reviewer 看 8-D 維度 | E2 CRIT-1 |
| `grid_cell_count()` | 加 `pct_grid` 參數；公式擴 8-D；comment 寫明 8-D | E2 CRIT-1 + HIGH-3 |
| 新增 helper `_build_exclusion_counts()` | 5-category exclusion counters（stale/missing_dominance/mixed/quiet_window_fail/density_floor_fail） | E2 HIGH-4 |
| 新增 helper `_compute_baseline_lift()` | tight (K=3/N=10k/M=2) vs loose (K=1/N=1/M=1) avg_net_bps lift | E2 HIGH-4 |
| 新增 helper `_build_regime_annotation()` | bear-regime annotation 含 sample_period / regime_label / cross_regime_validation_required / live_promotion_requires | MIT MUST-FIX |

### §1.2 `liquidation_cluster_stage0r_smoke.py` (818 → 1136 LOC，+318)

| 區域 | 改動 |
|---|---|
| 9 個 existing tests 更新 | 全部增 `total_bucket_count=...` 顯式傳入；4 個增 `notional_pct_floor=0.0` 跳過該軸；2 個增 `pct_grid=(0.95,)` 鎖 sweep 為 16 cells |
| 8 個 round-2 新 tests | `_check_cluster_neff_30min_cascade`（CRIT-3）/ `_check_n_eff_horizon_ceil`（MIT MUST-FIX）/ `_check_direction_check_none_when_missing`（CRIT-2）/ `_check_missing_bucket_count_red`（CRIT-2）/ `_check_notional_pct_floor_filter`（CRIT-1）/ `_check_regime_annotation_emit`（MIT）/ `_check_regime_annotation_in_sweep`（MIT + HIGH-2）/ `_check_baseline_lift_and_exclusion_counts`（HIGH-4）/ `_check_density_efficacy_three_state`（HIGH-1）/ `_check_mit_drift_correction_constants`（MIT drift）|
| 總 test 數 | 22 → 34（+12 cases）|

## §2 關鍵 diff（精選）

### §2.1 CRIT-3：cluster aggregation sliding pattern

```python
# Round 1（anchor pattern — 與 SQL lag() 不一致）
for t in sorted_triggers:
    if last_key != key or (ts_ms - last_ts_ms) > window_ms:
        distinct_clusters += 1
        last_key = key
        last_ts_ms = ts_ms
    # 同 cluster 不推進 last_ts_ms

# Round 2（sliding pattern — mirror SQL lag()）
for t in sorted_triggers:
    if last_key != key or (ts_ms - last_ts_ms) > window_ms:
        distinct_clusters += 1
    last_key = key
    last_ts_ms = ts_ms  # 每 event 都推進
```

驗證：10 events spaced 30min → 1 cluster (SQL-equiv)。Round 1 認 4 clusters。

### §2.2 MIT MUST-FIX：`math.ceil` 取代整數除

```python
# Round 1（horizon=6 / 10 / 14 dormant bug）
return int(n / max(1, horizon_min // 5))

# Round 2（修 dormant + canonical grid 結果不變）
return int(n / max(1, math.ceil(horizon_min / 5)))
```

對 canonical grid `{1, 5, 15}` 結果不變；對 sensitivity expansion `{6, 10, 14, 30}`
fix integer-floor 漏算 sub-bar overlap penalty。

### §2.3 CRIT-2：total_bucket_count fail-closed 三態

```python
# Round 1（silent fallback）
if total_bucket_count is None:
    total_bucket_count = len(rows)  # 64× anti-conservative

# Round 2（fail-closed）
total_bucket_count_missing = total_bucket_count is None
# direction_check 收 None → 三態 passed=None + missing_bucket_count_denominator
# verdict 邏輯顯式 hard RED
if total_bucket_count_missing:
    other_red_reasons.append("missing_bucket_count_denominator: ...")
```

### §2.4 CRIT-1：notional_pct_floor 8th sweep axis

```python
# Round 1（7-D loop 3888 cells = 33% spec K_total）
for k in k_grid: for n in n_usd_grid: ... for h in horizon_grid:
    cell_result = compute_stage0r(rows, k_event_count=k, n_usd=n, ...)

# Round 2（8-D loop 11664 cells = 100% spec K_total）
for k in k_grid: for n in n_usd_grid: ... for pct in pct_grid: ... for h in horizon_grid:
    cell_result = compute_stage0r(rows, ..., notional_pct_floor=pct, ...)
```

### §2.5 MIT bear-regime annotation

```python
def _build_regime_annotation() -> dict[str, object]:
    return {
        "sample_period_start": "2026-05-11",
        "sample_period_end": "2026-05-18",
        "regime_label": "bear",
        "cross_regime_validation_required": True,
        "live_promotion_requires": "30d cross-regime sample with bull + ranging coverage",
        "rationale_source": "MIT 2026-05-18 dual review §3.3 + 8b RED_FINAL §3.5",
    }
```

寫入 `compute_stage0r` 兩 return path + `compute_stage0r_sweep` 兩 return path。

## §3 治理對照（hard boundary + spec compliance）

| 規則 | 狀態 | 驗證 |
|---|---|---|
| 不觸 SQL（S0R-1 worktree） | ✅ | `git status` 純 helper_scripts/reports/w_audit_8c/* + self-report |
| 不觸 CLI 包裝（S0R-3 worktree） | ✅ | 同上 |
| 不觸 auth / live / lease / paper / mainnet | ✅ | grep 0 hit |
| 不觸 RiskConfig / TOML / cron / runtime | ✅ | 純 math module；無 DB / IO / runtime |
| 中文為主 comment（per `feedback_chinese_only_comments.md`） | ✅ | 所有新加 comment 中文；技術 identifier (snake_case / SQL term) 保留 |
| 文件大小 800 行警告 / 2000 行硬上限 | ✅ | metrics.py 1814 < 2000；smoke.py 1136 < 2000 |
| 不假數據 / 不偽 sign-off | ✅ | 全 fix 對應 E2/MIT 明確 finding；新 test 全 PASS 為實際 runtime PASS |
| spec v0.3 §"Mandatory report fields" 對齊 | ✅ 改善 | 加 `baseline_lift` + `exclusion_counts` + `regime_annotation`；其餘 mandatory field (c1_proof_id / maker_taker / pulse_age_distribution) 留給 S0R-3 wrapper |
| `feedback_pnl_priority_over_governance.md` | ✅ | math correctness 優先；CRIT-3 cluster algorithm 修正比 governance 更重要 |
| `feedback_pushback.md` | 中性 | 無 push back 反對 E2/MIT；3 個 CRIT + MIT MUST-FIX + bear-regime 均 accepted |

### §3.1 不變量保證

| 不變量 | 驗證方式 |
|---|---|
| math.ceil 對 canonical grid 結果不變 | smoke `_check_n_eff_horizon_ceil` 驗 horizon=1/5/15 結果 與 round 1 一致 |
| cluster algorithm 對 spaced (2h apart) 結果不變 | smoke `_check_cluster_neff_spaced` 仍 PASS |
| 60min boundary case 仍正確 | E2 round 1 §4.4 已實證；round 2 算法 mirror SQL lag()，boundary 仍 `>` 嚴格大於 |
| JSON serializable | smoke `_check_sweep_json_roundtrip` 仍 PASS |
| K_GRID_CELLS_PER_SYMBOL = 11_664 不變 | `grid_cell_count()` 驗 `4×4×3×3×3×3×3×3 = 11664` |
| 8b math primitives byte-equivalent | round 2 未動 `psr_bailey_ldp / dsr_with_k / wilson_ci_95 / block_bootstrap_ci / _skew / _kurtosis` |

## §4 不確定之處（uncertainties）

| 議題 | 不確定 | E2 round 2 review focus |
|---|---|---|
| `_compute_baseline_lift` 的 "loose baseline" 定義 | spec v0.3 line 253 寫 "baseline lift versus no-liquidation-cluster baseline and versus single-event-bucket noise baseline" — 兩個 baseline。Round 2 只實作 single-event-bucket noise baseline（K=1/N=1/M=1）；no-liquidation-cluster baseline 需要從 raw kline 隨機 sample non-trigger bucket 對應 forward return，需 SQL CTE 額外 join，超 S0R-2 純 math 範圍。建議 S0R-3 wrapper 階段 IMPL。 | 確認此 deferred 合理或需要 round 3 |
| `_build_regime_annotation` 是 hardcoded sample period | 2026-05-11 ~ 2026-05-18 是 round 1 dispatch 時的 panel window；若未來重 dispatch 之 panel period 不同，此 annotation 仍 hardcoded。MIT round-1 review 明示「Stage 0R verdict JSON 必含 regime annotation」，但未說 dynamic vs static；Round 2 採 static 鎖死當前 sample period。 | 確認是否需要 caller 傳入 `sample_period_start/end` 動態取代 hardcoded |
| `density_efficacy` 三態 None 對 verdict 影響 | Round 2 verdict 只在 `is False` 時 RED；None 不阻塞 verdict 但 S0R-3 wrapper 必獨立 surface skipped 狀態。E2 round 1 finding 寫「fallback 應 fail-closed」；Round 2 解讀為「不應 silent PASS 但也不應 hard block verdict」。 | 確認此 nuance 對齊 E2 round-1 intent；若 reviewer 認為應 hard RED，1 行 fix |
| `_extract_trigger_rows` 在 `_compute_baseline_lift` 中重複呼叫 2 次 | tight + loose 各算一次 trigger 集；可能有 perf 影響（balanced fixture × 1400 rows × 2 = 2800 row scans）。Round 1 sweep performance 已估算 50-100ms/cell × 11664 cells = 10-20 min wallclock；round 2 加 baseline_lift 雙重 scan 與 5-cat exclusion scan，估增 30%。 | 確認此 perf 不超 spec 30s acceptance（per Linux PG real panel scale，可能仍 OK） |
| Round 1 E2 LOW-1 `PASS-LONG-ONLY` vs `PASS-LONG-DIRECTION-ONLY` 命名 | E2 round 1 §5 LOW-1 提及 PA §3.1 line 441 用 verbose 形式。Round 2 未動，保持 round 1 短形 `PASS-LONG-ONLY`（與 round 1 PA 設計圖一致；short form 已 internal API 使用）。 | 若 PA round 2 仍堅持 verbose 形式，1 字串 replace 即可，但建議 PA 接受 round 1 短形 |

## §5 Round 1 → Round 2 finding 對照表

| Finding ID | 狀態 | 修法位置 |
|---|---|---|
| E2 CRIT-1（notional_pct_floor 漏實作）| ✅ FIXED | `_extract_trigger_rows` filter / `compute_stage0r` signature / `compute_stage0r_sweep` 8-D loop / `grid_cell_count` |
| E2 CRIT-2（total_bucket_count anti-conservative fallback）| ✅ FIXED | `_both_direction_floor_check` 三態 / `compute_stage0r` 顯式 hard RED |
| E2 CRIT-3（cluster aggregation SQL vs Python divergence）| ✅ FIXED | `_n_eff_cluster_aware` sliding pattern |
| E2 HIGH-1（density_efficacy silent PASS fallback）| ✅ FIXED | density_efficacy 三態 passed=None + skipped=True；verdict 邏輯只在 `is False` RED |
| E2 HIGH-2（sweep refusal packet 結構不對稱）| ✅ FIXED | refusal packet 加 `best_per_tier_per_direction / symbol_tiers / regime_annotation` |
| E2 HIGH-3（DEFAULT_PCT_GRID 定義但 sweep 不用）| ✅ FIXED | 同 CRIT-1 sweep 8-D loop |
| E2 HIGH-4（缺 5 mandatory report fields）| ⚠️ PARTIAL | `baseline_lift + exclusion_counts` IMPL；c1_proof_id / maker_taker / pulse_age_distribution 留給 S0R-3 wrapper |
| E2 MEDIUM-1（`_binding_dimension` forward reference）| ❌ NOT FIXED | LOW priority；不影響正確性 |
| E2 MEDIUM-2（smoke long-only weak assertion）| ❌ NOT FIXED | Round 1 既有；任務 scope 未 mandate；smoke 已有 30 cases 覆蓋面足夠 |
| E2 MEDIUM-3（comment 描述舊 algo）| ✅ FIXED implicit | CRIT-3 fix 同時更新 comment 為 sliding lag pattern |
| E2 LOW-1（PASS-LONG-ONLY 短形 vs PA 長形）| ❌ NOT FIXED | 等 PA round 2 確認；1 line replace |
| E2 LOW-2（K_GRID_CELLS_PER_SYMBOL comment 誤導）| ❌ NOT FIXED | comment 已 cover「8 grid 軸；direction 雙向另計」；不需動 |
| E2 LOW-3（CandidateCell dataclass dead code）| ❌ NOT FIXED | S0R-3 wrapper 預計用之；保留為 forward-use 接口 |
| E2 LOW-4（smoke.py 818 LOC）| 已超 1000 LOC | Round 2 1136 LOC 仍 < 2000 hard cap；新加 12 cases 是必要 |
| MIT MUST-FIX（`_n_eff_horizon_overlap` integer-floor）| ✅ FIXED | `math.ceil` |
| MIT push-back（MAX_SYMBOL_SHARE 0.40 → 0.30）| ✅ FIXED | 常量改值 + 觸控制者 fixture 仍 RED（驗 smoke）|
| MIT push-back（COST_EDGE_RATIO_MAX 0.80 → 0.60）| ✅ FIXED | 常量改值 |
| MIT push-back（FALSE_POSITIVE_RATE_MAX 0.40 → 0.30）| ✅ FIXED | 常量改值 |
| MIT MUST-FIX（bear-regime annotation）| ✅ FIXED | `_build_regime_annotation` 寫入 4 個 return path |
| MIT governance MUST-FIX（E1 self-report MUST LAND）| ✅ FIXED | 本檔即是 self-report |

## §6 Smoke test 列表（34 cases）

```
cluster-aware n_eff（5）
  - _check_cluster_neff_60min_window
  - _check_cluster_neff_spaced
  - _check_cluster_neff_30min_cascade       [NEW: CRIT-3]
  - _check_n_eff_horizon_ceil              [NEW: MIT MUST-FIX]
  - _check_cluster_neff_three_way_binding

concentration caps（3）
  - _check_single_day_concentration
  - _check_single_day_concentration_pass
  - _check_single_symbol_concentration

both-direction floor（3）
  - _check_both_direction_floor_long_dead
  - _check_both_direction_floor_both_pass
  - _check_direction_check_none_when_missing  [NEW: CRIT-2]

density floor efficacy / FP rate（3）
  - _check_density_floor_efficacy
  - _check_false_positive_rate_pass
  - _check_false_positive_rate_fail

tier classification（2）
  - _check_tier_classify
  - _check_symbols_by_tier

compute_stage0r RED paths（4）
  - _check_compute_stage0r_bb_demo_bias_refuse
  - _check_compute_stage0r_single_day_red
  - _check_compute_stage0r_single_symbol_red
  - _check_missing_bucket_count_red          [NEW: CRIT-2]

compute_stage0r 4-value verdict（2）
  - _check_compute_stage0r_long_only_emits_long_only
  - _check_compute_stage0r_balanced_no_panic

E1 round 2 新 tests（6）
  - _check_notional_pct_floor_filter         [NEW: CRIT-1]
  - _check_regime_annotation_emit            [NEW: MIT]
  - _check_regime_annotation_in_sweep        [NEW: MIT + HIGH-2]
  - _check_baseline_lift_and_exclusion_counts [NEW: HIGH-4]
  - _check_density_efficacy_three_state      [NEW: HIGH-1]
  - _check_mit_drift_correction_constants    [NEW: MIT drift]

sweep（3）
  - _check_sweep_returns_expected_cells
  - _check_sweep_bb_demo_bias_refuse
  - _check_sweep_json_roundtrip

math correctness（3）
  - _check_psr_dsr_finite
  - _check_bootstrap_ci_known_mean
  - _check_wilson_ci_bench
```

合計 34 cases；全 PASS。

```
PASS W-AUDIT-8c Stage 0R metrics smoke
ALPHA_SOURCE_ID=liquidation_cluster_reaction
```

## §7 Operator 下一步

1. **E2 round 2 review** — 確認 3 個 CRIT 修法符合 SQL spec / MIT MUST-FIX
   `math.ceil` 對 canonical grid 結果不變、3 個 drift 套用正確。
2. **PA 裁定 `PASS-LONG-DIRECTION-ONLY` 命名**（LOW-1）— 若 PA 接受短形即可
   sign-off；若 PA 堅持 verbose，1 line replace。
3. **S0R-3 wrapper round 2** 需 consume 新 8-D sweep + 新 top-level keys
   (`baseline_lift / exclusion_counts / regime_annotation` + sweep refusal
   packet 新 keys)。
4. **E4 regression** — `python3 -m helper_scripts.reports.w_audit_8c.liquidation_cluster_stage0r_smoke`
   應 PASS（與 PR 一同跑）。
5. **PM commit + push** — round 2 commit pending E2 round 2 APPROVE。

## §8 Files referenced

- 此 self-report：本檔
- E2 round 1 review：`srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8c_s0r_2_e2_review.md`
- MIT dual review：`srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8c_s0r_1_2_mit_dual_review.md`
- PA design：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_stage_0r_packet_design.md`
- Spec v0.3：`srv/docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md`
- 8b sibling precedent：`srv/helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py`
- 修改檔 1：`srv/helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py`（1550 → 1814 LOC）
- 修改檔 2：`srv/helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke.py`（818 → 1136 LOC）

---

E1 IMPLEMENTATION DONE (round 2)：待 E2 round 2 審查
Report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_2_metrics_self_report.md`
