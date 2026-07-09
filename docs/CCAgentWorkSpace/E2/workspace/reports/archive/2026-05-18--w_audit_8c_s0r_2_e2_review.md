# E2 PR Adversarial Review — 8C-S0R-2 Python Metrics Module

Branch: `origin/worktree-agent-af73a5d4575815f26`
Commit: `c041097c`
Date: 2026-05-18
Reviewer: E2 (adversarial code-review + auditor)
Sibling review: `2026-05-18--w_audit_8c_s0r_3_e2_review.md` (already RETURN)

---

## §0 Verdict

**RETURN to E1** — 3 CRITICAL must-fix + 4 HIGH + 4 MEDIUM/LOW.

**Sign-off blocked**: math layer ships systematic bias toward over-PASS at 7d
panel; sweep grid drops 67% of cells; trigger-rate floor is anti-conservative.
None are 5-min typo fixes. ALL require E1 rework (math layer is out of scope
for E2 direct-fix per profile).

**APPROVE-NEXT-ROUND** after E1 fixes the 3 CRITICAL + at minimum the 2
HIGH-1/HIGH-2 (verdict-changing). HIGH-3/HIGH-4 + MEDIUM/LOW can ship in
follow-up if PM accepts the trade-off.

### Cross-worktree arbitration (per task brief CRITICAL section)

| Question | Verdict | Owner of rework |
|---|---|---|
| **S0R-2 return type** — `dict[str, object]` vs `list[dict]` | **S0R-2 IS CORRECT (dict)** per 8b sibling precedent line 1724: `funding_skew_stage0r_metrics.py:compute_stage0r_sweep() -> dict[str, object]`. | **S0R-3 must rework** (confirmed by sibling E2 review CRIT-2: S0R-3 line 657-676 iterates dict as if list → `AttributeError`). |
| **default param drift** (single_day_cap, single_symbol_cap, bootstrap_iters, rng_seed) per task brief CRITICAL #7 | **TASK BRIEF VALUES WRONG**. PA design §2.5 line 377-378 says `0.25` / `0.40`; spec/PA do NOT specify bootstrap_iters (E1 matched 8b `iterations=400`); rng_seed `20260518` mirrors 8b pattern `20260515`. E1 implementation is consistent with **actual** PA + 8b precedent. | No rework needed; task brief author cross-checked against stale draft. |
| **PASS-LONG-ONLY vs PASS-LONG-DIRECTION-ONLY naming** | **PA §3.1 line 441 says `PASS-LONG-DIRECTION-ONLY`** verbose form; E1 used `PASS-LONG-ONLY` shorter form. Discrepancy real but contained (only internal API since S0R-3 wrapper is sibling-pending). | **PA must amend OR E1 align**. Recommend E1 align to PA verbose form (1-line constant rename). LOW severity. |

---

## §1 改動範圍

```
helper_scripts/reports/w_audit_8c/__init__.py                      14 +
helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py  1550 +
helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_smoke.py  818 +
3 files changed, 2382 insertions(+)
```

- Single commit `c041097c` on dedicated worktree branch.
- 0 unrelated file changes (clean scope).
- File sizes: metrics 1550 (over 800 warning, under 2000 cap); smoke 818
  (over 800 warning); 8b sibling = 1805 LOC, so E1 ~14% shorter is reasonable.

---

## §2 E2 8 條 reviewer checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA §2.4/§2.5 一致 | ⚠️ MOSTLY | 漏實作 `notional_pct_floor` 軸；漏 5 個 "Mandatory report fields"（§5 CRIT-3 / HIGH-4） |
| 無 except:pass / 靜默吞異常 | ✅ | grep 0 hit；全部 `try/except (TypeError, ValueError): return None` 顯式 fail-soft |
| 日誌 %s 格式 | N/A | 純 math module 無 logging |
| 新 API 端點 _require_operator_role | N/A | 無 HTTP 端點 |
| except HTTPException raise 在 except Exception 前 | N/A | 純 Python |
| detail=str(e) 已改 Internal server error | N/A | 純 Python |
| asyncio blocking Lock | ✅ | grep `asyncio\|threading\|HTTPException\|FastAPI` = 0 hit |
| 私有屬性穿透 ._xxx | ✅ | 全用 `_safe_int` / `_safe_float` 內部 helper，無外部私有穿透 |

---

## §3 OpenClaw §3 特殊 9 條

| Item | 狀態 | 證據 |
|---|---|---|
| 3.1 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ | grep 0 hit |
| 3.2 注釋規範（中文為主） | ✅ | 25 個「為什麼」/「不變量」/「fail-closed」/「MODULE_NOTE」標記；docstring 全中文；technical identifier 保留 snake_case |
| 3.3 Rust unsafe / unwrap / expect / panic | N/A | 純 Python |
| 3.4 跨語言 IPC schema 一致 + serde 型別安全 | ⚠️ | S0R-2 ↔ S0R-3 contract mismatch（sibling E2 report 證實 S0R-3 假錯 → S0R-3 rework；S0R-2 dict 形式正確 mirror 8b sibling） |
| 3.5 Migration Guard A/B/C | N/A | 無 V### migration |
| 3.6 healthcheck 配對 | N/A | 純 math module 無 passive-wait |
| 3.7 Singleton / monkey-patch | ✅ | 無 singleton |
| 3.8 文件大小 800/2000 | ⚠️ 1550 LOC (metrics) + 818 LOC (smoke) | 均過 800 warning，未過 2000 cap；MODULE_NOTE 自證 justification（純 math mirror 8b 1805 LOC 結構 + 8c 三大新加法）；可接受 |
| 3.9 Bybit API 改動 | N/A | 不觸 Bybit |
| 3.10 P0/P1 leak/bias caller proof | N/A | 不涉指標/leak/look-ahead（Stage 0R 是 replay tool；as-of join 由 sibling SQL CTE 處理） |

---

## §4 對抗反問結果（13 條 probes）

### §4.1 8b sibling precedent byte-equivalence

`psr_bailey_ldp` / `dsr_with_k` / `_skew` / `_kurtosis` / `block_bootstrap_ci` /
`wilson_ci_95` 6 個核心數學函數逐行對比 8b funding_skew_stage0r_metrics.py
（line 102-240）— **數學公式完全一致**，只有 `block_bootstrap_ci` 的
`seed` default 不同（8b=20260515 / 8c=20260518）對應各 module 的設計日期，
模式正確。**PASS — math primitives byte-equivalent**。

### §4.2 _n_eff_cluster_aware 公式驗證

公式：`min(n_eff_horizon, distinct_days, distinct_60min_clusters)`

對比 MIT 8b RED_FINAL review SHOULD-3 verbatim spec（line 491）：
`n_eff_cluster = min(_n_eff(n, horizon), distinct_8h_buckets, distinct_calendar_days)`

E1 替換 `8h funding window` 為 `60min cluster window` — 對 8c liquidation
cascade regime 合理 adaptation（cascade 比 funding cycle 更短暫）。

但**真實 cluster 邏輯有 bug — 見 §5 CRIT-3 SQL vs Python semantic divergence**。

### §4.3 PRIMARY horizon=5min penalty 任務 brief 詢問

`_n_eff_horizon_overlap(n, 5) = n / max(1, 5 // 5) = n / 1 = n` → horizon
penalty = 0 at primary horizon 5min。

實測驗證：n=100, horizon=5 → 100；n=100, horizon=15 → 33；n=100, horizon=30 → 16。

**這是 intended 行為**：5min horizon 下，每個 5m bar 是一個獨立觀察單位，
無 overlap penalty。`min(horizon, days, clusters)` formula 在 primary
horizon 等同 `min(n, days, clusters)`，binding dimension 必為 days 或
clusters。**Defensible math**。

但**反面影響**：spec v0.3 line 218 寫「holding horizon: 5m primary; 1m and
15m sensitivity」— 1m sensitivity cell 的 `_n_eff_horizon = n / max(1, 1//5)
= n / 1 = n` 也等於 n（horizon // 5 = 0 → max(1, 0) = 1）。即 1m 與 5m
horizon cell 的 horizon penalty 一致（都是 0）。**這在 1m sensitivity 上
理論上錯**（1m horizon 與 5m bar 完全 overlap）— 但 E1 mirrored 8b 同公式，
是 8b 既有限制；不視為 8c 新加 finding，但 MIT 在 spec v0.4 應討論。

### §4.4 60min boundary case

實測：`signal_ts_ms` 差恰 3,600,000 ms（60min）→ same cluster；3,600,001 ms
→ new cluster。

對比 PA SQL CTE helper（line 327-330）：`CASE WHEN ... bucket_end_ts - prev_ts
> '60 minutes'::interval THEN 1 ELSE 0`。SQL 的 `>` 嚴格大於與 Python 的
`(ts_ms - last_ts_ms) > window_ms`（line 441）一致。**boundary 一致 ✓**。

### §4.5 4-value verdict synthetic emit

合成 25-symbol × 14-day × 20-event long-only fixture：

```
Verdict: RED
Reasons: ['pooled_n_eff_cluster 15 < 300', 'PSR(0) None < 0.95', 'DSR None < 0.95']
n_per_cell: 7000, pooled_n_eff: 15
long_branch_promotion_passed: False (n_eff_cluster too low)
short_branch_promotion_passed: False (no short triggers)
both_direction_floor.long_passed: True
both_direction_floor.short_passed: False
```

`pooled_n_eff` = 15 binding by `distinct_days` (14) → cluster-aware n_eff
brutally caps even 7000-row long-only sample。**4-value verdict 可達 RED，
但實際 PASS-LONG-ONLY 路徑須極端寬鬆 fixture 才能命中**。

Smoke test `_check_compute_stage0r_long_only_emits_long_only`（line 556）採
defensive 寫法：`if packet["pass"].startswith("PASS")` 才 assert
PASS-LONG-ONLY，否則只 assert direction check 對。**這是合理的 smoke
test 設計但仍是 weak verification of PASS-LONG-ONLY emit path**。

### §4.6 Smoke test 22/22 PASS 獨立重跑

```bash
cd /tmp && python3 liquidation_cluster_stage0r_smoke.py
PASS W-AUDIT-8c Stage 0R metrics smoke
ALPHA_SOURCE_ID=liquidation_cluster_reaction
```

22/22 通過確認 ✓。但 §4.5 揭：smoke 之 `_check_compute_stage0r_long_only`
未實質驗證 PASS-LONG-ONLY path（短路為 「if PASS then assert verdict」）。

### §4.7 Bootstrap CI sample replacement

`block_bootstrap_ci` line 313-325：`rng.randint(0, len(clean) - block_size)`
→ block 起點重複可選取 → with replacement at block level（standard moving
block bootstrap）。匹配 8b 同公式。**Correct**。

### §4.8 DSR K_total 計算

`k_new = max(MIN_STAGE0R_SYMBOLS, n_symbols) * K_GRID_CELLS_PER_SYMBOL`
（line 1092）`= max(25, n_symbols) * 11_664`。

對比 spec v0.3 line 258-268: `K_new_primary = N_symbols_inspected * 11_664`。
E1 額外加 `MIN_STAGE0R_SYMBOLS` floor — **這是 conservative bias（正確方向）**：
若 n_symbols=5（試小 cohort），K_total 至少按 25 計算，DSR penalty 不會
偷偷變寬。8b precedent 也是同樣 floor 模式。**Correct**。

### §4.9 PBO CSCV split 計算

CSCV 用 `combinations(days, train_size)` 若超過 `max_splits=240` 改 random
sample with `seen` dedupe。對比 8b PBO line 554-625 — 邏輯一致；
`reason` 字段 None 表 valid run。**Correct**。

### §4.10 Concentration check semantic 對 PA design §2.5

`_single_day_concentration_check(cap=0.25)` ✓ matches PA §2.5 line 377
（v0.3 spec）。

`_single_symbol_concentration_check(cap=0.40)` ✓ matches PA §2.5 line 378
（NEW for 8c）。

`_both_direction_floor_check(floor_rate=0.001)` ✓ matches PA §2.5 line 375。

**Task brief CRITICAL #7 之「drift」claim 不成立** — E1 default 與 PA design
完全一致；task brief 引用值錯誤。

### §4.11 K_GRID_CELLS_PER_SYMBOL 維度核算

```python
K_GRID_CELLS_PER_SYMBOL = 11_664
# 內部 comment line 107: 4*4*3*3*3*3*3*3*2 = 23328（理論上限）
# Spec v0.3 line 268: 11_664（單向 branch 算一次；direction 雙向另計）
```

實算 `4*4*3*3*3*3*3*3 = 11664` ✓（8 維度 grid 不含 direction）。Comment
誤導但實際 constant 正確。

**BUT — see §5 CRIT-1 critical sweep dimension gap**。

### §4.12 Performance estimate

3888-cell sweep on 40-row tiny fixture: 6.5s = 1.7ms/cell。Real 7d × 32 sym
panel projected ~60k rows → ~50-100ms/cell → **3-7 分鐘 sweep wallclock**。
可接受 for CLI replay tool（per S0R-3 wrapper invocation）。

### §4.13 CandidateCell dataclass 用途

`@dataclass(frozen=True) class CandidateCell`（line 162-188）定義 + label()
helper，但**全 module 0 處實際用**（grep `CandidateCell` 只命中 MODULE_NOTE
docstring）。**Dead code** — 為「mirror 8b CandidateKey」結構而定義但實際
邏輯用 raw dict + grid_coords nested dict。**LOW-3**。

---

## §5 Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **CRIT-1** | metrics.py:92 `DEFAULT_PCT_GRID` + line 1402-1433 sweep loop + line 979-1004 `compute_stage0r` signature + line 845-924 `_extract_trigger_rows` | **`notional_pct_floor` 軸完全缺實作**。Spec v0.3 line 191 把 `notional_percentile_24h >= notional_pct_floor` 列為 `magnitude_ok` 硬 gate；line 215 + line 264 + PA design line 156 + line 191 把 `(0.90, 0.95, 0.98)` 列為 8-D sweep 之一軸。但 E1: (1) `compute_stage0r` 簽名無 `notional_pct_floor` 參數；(2) `_extract_trigger_rows` 雖取 `notional_pct_24h` row 字段但 0 處與 floor 比較；(3) `compute_stage0r_sweep` 7-D 迴圈（k×n×m×floor×side_dom×quiet×horizon = 3888 cells）不含 pct 軸。**實際 sweep 只覆蓋 3888/11664 = 33% search space**，但 DSR penalty 仍按 11664 計算（per spec）。**真實 best cell 可能落在未探索的 67%**；replay 結論不可信。 | E1 加 `notional_pct_floor` 至 `compute_stage0r` 簽名（default 0.90）+ `_extract_trigger_rows` 加 `if notional_pct_24h is not None and notional_pct_24h < notional_pct_floor: continue` filter + sweep loop 加最外層 `for pct in pct_grid` 變 8-D（3888×3 = 11664 cells）。Performance 約 9-21 分鐘 wallclock — 仍可接受 for CLI。 |
| **CRIT-2** | metrics.py:1060-1062 `total_bucket_count is None: total_bucket_count = len(rows)` + line 1014-1016 docstring 「fallback 用 len(rows)（偏保守但仍有意義）」 | **trigger-rate 分母 fallback 是 anti-conservative**。`_both_direction_floor_check` 公式 `long_count / total_bucket_count >= 0.001`。當 caller 不傳 `total_bucket_count`，fallback 用 `len(rows)`（CTE 5 final_signals 過濾後的 trigger 候選 ~1000）；但真實 5m bucket 母體應從 CTE 1 raw_buckets 取 `count(*)`（7d × 32 sym × 12 buckets/h × 24h ≈ 64,500）。**fallback 把分母低估 64×** → trigger rate 高估 64× → floor check 永遠 pass when it shouldn't → 8b crowded_long_fade dead-direction 教訓失效。E1 docstring 自稱「偏保守」實際 anti-conservative。 | (a) **首選**：fallback 改 fail-closed — 若 `total_bucket_count is None` raise `ValueError` 或 return RED packet 強迫 caller 顯式傳。(b) 或保留 fallback 但改 docstring + 改邏輯：若 None，set `passed=None` 並進 `other_red_reasons` "total_bucket_count required for both-direction floor check"。 |
| **CRIT-3** | metrics.py:418-446 `_n_eff_cluster_aware` cluster aggregation algorithm + line 445-446 comment「anchor never advances within a cluster」 | **SQL vs Python cluster semantic divergence**。PA design §2.3 line 327-330 SQL helper 用 `lag(bucket_end_ts) > 60min`（delta vs PREVIOUS event）。E1 Python 用 anchor pattern（line 441-446）：`last_ts_ms` 只在 NEW cluster 開時更新 → delta vs CLUSTER ANCHOR 不是 vs previous。實測 5 events at t=[0,30,60,90,120]min → SQL 認 1 cluster（每相鄰 30min ≤ 60min）；E1 認 2 clusters（t=90 與 anchor t=0 差 90min > 60min → 新 cluster）。對 10 events 30min 間隔 cascade：SQL = 1 cluster；E1 = 4 clusters。**E1 算法在長 cascade 場景 OVER-counts clusters → OVER-estimates n_eff → 削弱 MIT SHOULD-3 cluster penalty 用意（cluster penalty 應 MORE 不 LESS）**。 | E1 改 cluster aggregation 邏輯為 `last_ts_ms = ts_ms`（每 event 都更新 last_ts，無論新舊 cluster）— mirror SQL `lag()` semantic：`if (ts_ms - last_ts_ms) > window_ms: distinct_clusters += 1; last_ts_ms = ts_ms` 改為 `if last_key != key or last_ts_ms is None or (ts_ms - last_ts_ms) > window_ms: distinct_clusters += 1; last_key = key; last_ts_ms = ts_ms` 並在 if 外加 `else: last_ts_ms = ts_ms`（推進 anchor）。重跑 smoke test 之 `_check_cluster_neff_60min_window` + `_check_cluster_neff_spaced` + `_check_cluster_neff_three_way_binding` 驗證 + 加 new smoke case `_check_cluster_30min_cascade` 確認長 cascade 認 1 cluster。 |
| **HIGH-1** | metrics.py:1130-1136 density_efficacy fallback `passed: True` 當 raw/after counts None | **silent SKIP 偽 PASS**。當 caller 不傳 `raw_5m_bucket_count` / `after_k/n/m_count`，code 直接設 `passed: True, fail_reason: None, reason_for_skip: "raw/..."`。下游 verdict 推導（line 1193-1196）看 `density_efficacy.get("passed")` 為 True 即不加 RED reason。**spec v0.3 line 244 明列「density-floor filter efficacy」為 mandatory report field**。fallback 應 fail-closed（PASS 變 None / skipped）而非靜默 True。 | 改 `passed` 為 `None`（三態），verdict 邏輯 line 1193 改 `if density_efficacy.get("passed") is False: ...` 並 separately 在 packet warn `density_efficacy.skipped = True` → S0R-3 wrapper 看到 skipped 必明確 report。 |
| **HIGH-2** | metrics.py:1387-1400 sweep BB demo-bias short-circuit returns 不含 `eligible_for_demo_canary_per_tier` symmetric structure with non-skipped path | **sweep refusal packet 結構與成功 packet 不對稱**。Refusal packet 有 `eligible_for_demo_canary_per_tier` 但**缺** `best_per_tier_per_direction / symbol_tiers`。下游 S0R-3 wrapper（per sibling E2 report）期望統一 keys，refusal path miss key 會在 dict-access 端 raise KeyError。 | E1 在 refusal packet 加 `"best_per_tier_per_direction": {tier: {"long_liquidated": None, "short_liquidated": None} for tier in DENSITY_TIERS}, "symbol_tiers": {}` — 鎖死兩 path 同 6 top-level keys。 |
| **HIGH-3** | metrics.py:90-94 + line 1377-1383 `DEFAULT_PCT_GRID` 定義但 sweep 不用；同類「dead default」現象 | **constant 與 sweep 不一致**：`DEFAULT_PCT_GRID = (0.90, 0.95, 0.98)` 定義但無 caller。屬同 §5 CRIT-1 root cause 的表現之一，但作為 separate code smell finding 列出 — 任何將來 reviewer 看 DEFAULT_PCT_GRID 會誤以為 sweep 用之；命名 misleading。 | 修 CRIT-1 同時：`compute_stage0r_sweep` 簽名加 `pct_grid: Sequence[float] | None = None`，default fallback 用 `DEFAULT_PCT_GRID`；sweep loop 加 `for pct in pct_grid`；`grid_cell_count()` 公式加 `* len(pct_grid)`。 |
| **HIGH-4** | metrics.py 整體 — 缺 5 個 "Mandatory report fields" per spec v0.3 line 234-253 | **缺 baseline_lift / pulse_age_distribution / stale/missing/mixed/quiet/density_floor_fail exclusion counts (5 categories) / maker_taker assumption / c1_proof_id** — 部分屬 S0R-3 wrapper 責任（c1_proof_id / maker_taker / pulse_age_distribution）defensible scope；但 `baseline_lift`（vs single-event-bucket noise baseline）+ `exclusion_counts`（5 categories）合理屬 metrics module 計算。 | (1) `compute_stage0r` 加 `baseline_lift_vs_single_event_bucket` 計算（比 `_extract_trigger_rows` 用 `m_dominant=1` 之 trigger 集 vs default `m_dominant=2` 集的 avg_net 差）；(2) `_extract_trigger_rows` 額外返回 `excluded_by_density / excluded_by_magnitude / excluded_by_dominance / excluded_by_quiet / excluded_by_density_floor_fail` 5-tuple counters 並掛入 packet。 |
| **MEDIUM-1** | metrics.py:1325-1340 `_binding_dimension` defined 在 `compute_stage0r` 之後（line 1325 vs 1264 callsite） | **Python forward reference 不會運行時報錯但 lint 風格不良**。`compute_stage0r` 第 1264 行 call `_binding_dimension(cluster_neff)`，定義在 1325 行。Python 在 module load 時兩個都 defined，runtime 找得到，無 actual bug — 但 readability 差，IDE jump-to-definition 體驗差。 | E1 把 `_binding_dimension` 移到 `compute_stage0r` 之前（line ~840 處 `Tier classification helpers` 區塊附近）。1-行 cut/paste。 |
| **MEDIUM-2** | smoke.py:556-583 `_check_compute_stage0r_long_only_emits_long_only` | **smoke 對 PASS-LONG-ONLY emit path 是 weak assertion**。當前邏輯：「若 verdict starts with PASS 才 assert PASS-LONG-ONLY；否則 assert direction check 對」— 即 RED 時 PASS-LONG-ONLY 永遠不會被驗。實際合成 fixture 結構（25 sym × 7d × 10 long-only events × spaced 70min）跑出來會 RED（per §4.5 實測）— 即此 smoke case 從未真正驗 PASS-LONG-ONLY emit。 | 加 new smoke case `_check_compute_stage0r_long_only_pass_emit`：構造 extreme bypass fixture（n=10000 across 50 sym × 50 days × 5 events/day spaced 90min；pre-compute net_bps 隨機 N(30, 5) 引入 variance 讓 PSR 可算；force `bb_demo_bias_confirmed=True` + `k=1 n_usd=1 m=1`）→ assert `packet["pass"] == "PASS-LONG-ONLY"` 而非 conditional。 |
| **MEDIUM-3** | metrics.py:445-446 misleading comment「anchor never advances within a cluster 直到超過 60min 才算 cluster 結束」 | **comment 描述當前 anchor-pattern 行為但不指明 vs SQL semantic divergence**。屬 §5 CRIT-3 的 byproduct — 修 CRIT-3 算法時這 comment 也需更新為「each event advances last_ts_ms; new cluster opens only when gap from PREVIOUS event > 60min」。 | 修 CRIT-3 後改 comment 與新算法一致。 |
| **LOW-1** | metrics.py:21 + line 949 + line 964 + line 968 + line 1464 `PASS-LONG-ONLY` / `PASS-SHORT-ONLY` constant 字面 | **vs PA §3.1 line 441 `PASS-LONG-DIRECTION-ONLY` 不一致**。E1 短形式可能 sibling S0R-3 wrapper / 4-agent review 文件混淆。1-字串替換但 5 處 + smoke test 全要改。 | E1 改為 `PASS-LONG-DIRECTION-ONLY` / `PASS-SHORT-DIRECTION-ONLY` aligned PA 全文；smoke test `_check_compute_stage0r_long_only_emits_long_only` 之 assertion 同步改。 |
| **LOW-2** | metrics.py:105-108 K_GRID_CELLS_PER_SYMBOL comment 含 `*2 = 23328（理論上限）` 但實際 const = 11664 | **comment 引導讀者誤判維度**。E1 寫「23328 含 direction 雙向另計」但 const 11664 不含 direction。讀者來理解 K_total 為何不 ×2 易誤判。 | comment 改寫釐清：「Spec v0.3 K_new_primary = N × 11_664（包含 8 grid 軸；direction 雙向計入 K_total 分子但不重複 sweep loop iteration — branch-level promotion floor 機制獨立於 K_total penalty）」。 |
| **LOW-3** | metrics.py:162-188 `CandidateCell` dataclass | **dead code**。Defined 為「mirror 8b CandidateKey」結構，但 module 0 處實際 instantiate。MODULE_NOTE 自誇「CandidateCell / SweepGrid」首要類 — 但 SweepGrid 也 dead（grep 0 hit）。 | 刪除 `CandidateCell` 與 MODULE_NOTE 內 mention，或在後續 worktree（S0R-3 CLI）實際用之；當前留 = 維護債。 |
| **LOW-4** | smoke.py:818 + metrics.py:1550 | **文件大小 over 800 warning line**。S0R-2 metrics 1550 / smoke 818。MODULE_NOTE 已 justify metrics 1550（8b mirror 1805 + 8c 三大新加法）；smoke 818 justify weak。 | E1 in MODULE_NOTE for smoke 加 justify「14 unit test cases × 30-60 LOC 每 case + fixture builders 200 LOC = 800 LOC unavoidable，2000 cap 充足 buffer」。 |

---

## §6 §5 Multi-session race check（P0-GOV-MULTI-SESSION-RACE-SOP-1 Phase 2）

| Check | 狀態 |
|---|---|
| 5a 提交前 fetch + sibling window check | ✅ `git fetch --prune origin`；origin/main HEAD 75e29265 領先 worktree base ab6f5c3e（10+ commits），與 S0R-2 file scope `helper_scripts/reports/w_audit_8c/*` 0 overlap |
| 5b sub-agent IMPL DONE 前 status clean | N/A — E2 read-only review，不創 commit |
| 5c 看到 unknown WIP 禁 revert | ✅ 開始時 6 個 sibling agent untracked files（E2 sibling S0R-3 review 報告 / PA design 報告 / 2 QA reports / memory edit）— 識別為其他並行 review session 工作；不 touch |
| 5d Sign-off report commit | ⏸ pending — E2 在後續寫 report 時 narrow stage 自己 report |
| 5e Sibling 推 origin 期間 → 重 fetch 重 review | ✅ review 中段 fetch；最新 origin/main HEAD 75e29265 與 review 開始時相同；無 sibling push 影響 |

**All 5 checks PASS** — review session 期間無 multi-session race violation。

---

## §7 結論

**RETURN to E1 — 3 CRITICAL + 4 HIGH + 4 MEDIUM/LOW**

### 退回 E1 修復清單（CRITICAL）

1. **CRIT-1 — 加 `notional_pct_floor` 整 8th sweep dimension**（metrics.py
   全 3 處：`compute_stage0r` signature / `_extract_trigger_rows` filter /
   `compute_stage0r_sweep` outer loop）。預估 4 LOC change + 1 new smoke
   test。**Owner: E1**。
2. **CRIT-2 — fix `total_bucket_count` fallback anti-conservative
   bias**（metrics.py:1060-1062 + 1014-1016 docstring）— fail-closed 或
   raise；不接受 silent `len(rows)` fallback。預估 3 LOC + docstring rewrite。
   **Owner: E1**。
3. **CRIT-3 — fix cluster aggregation algorithm anchor → previous semantic
   divergence vs SQL helper**（metrics.py:418-446）— mirror SQL `lag()`
   semantic：每 event 更新 last_ts_ms 不論新舊 cluster。預估 4 LOC change
   + 2 new smoke case（30min cascade / 60min boundary cascade）。**Owner:
   E1**。

### HIGH 要求 next round 修

4. **HIGH-1** — density_efficacy `passed: True` 改三態 None；改 verdict 邏輯。
5. **HIGH-2** — sweep refusal packet 補 `best_per_tier_per_direction` /
   `symbol_tiers` keys 對稱。
6. **HIGH-3** — DEFAULT_PCT_GRID 在 CRIT-1 同步用上。
7. **HIGH-4** — `baseline_lift_vs_single_event_bucket` + `exclusion_counts`
   5-category 加入 metrics output（部分 S0R-3 wrapper 仍責任但 metrics 必算）。

### MEDIUM/LOW 可後續

8-11. forward reference cleanup / smoke test 強化 / comment 釐清 / 文件大小
justify。

### 下一步

1. E1 修 CRIT 1/2/3（**必要**）+ HIGH 1/2（**verdict-affecting**）。
2. PA 裁定 `PASS-LONG-DIRECTION-ONLY` 命名（PA 認 E1 align OR PA amend）。
3. E1 修完重提 → E2 round 2 review（focus CRIT 修正驗證 + smoke 重跑）。
4. 通過 E2 round 2 → E4 regression（cargo workspace test + Python smoke）。

### S0R-3 wrapper 相依

S0R-2 dict 形式正確（mirror 8b 1724）。S0R-3 必 rework consume：
```python
sweep_result = compute_stage0r_sweep(...)
cells = sweep_result["sweep_cells"]
non_red = [c for c in cells if c.get("pass") != "RED"]
# 另保存 sweep_result["best_per_tier_per_direction"] etc.
```
（per sibling E2 report CRIT-2）。

---

E2 REVIEW DONE: RETURN to E1 (3 CRITICAL + 4 HIGH + 4 MEDIUM/LOW)
Report: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8c_s0r_2_e2_review.md`
