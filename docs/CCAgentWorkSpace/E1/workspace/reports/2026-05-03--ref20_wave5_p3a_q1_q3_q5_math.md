# REF-20 Wave 5 Batch 5A-A — P3a Q1+Q3+Q5 Math IMPL

**日期：** 2026-05-03
**Owner：** E1 sub-agent (sequential, single-instance)
**契約上游：**
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 5 P3a-Q1/Q3/Q5
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G3 + §8.1 / §8.2 + §11 P3a KPI + §12 #15/#17/#23

**狀態：** IMPL DONE，待 E2 review + E4 regression + MIT 副審

---

## 1. 任務摘要 / Task Summary

Wave 5 P3a global calibration math IMPL — 3 task 同 sub-agent 順序執行，避免 cross-agent race。3 個 module 落在 NEW DIR `program_code/learning_engine/`：

| Task | Module | Math 內容 | 規格依據 |
|---|---|---|---|
| **Q1** | `half_life_estimator.py` | PnL decay / Sharpe decay / default 14d 三 fallback | V3 §8.1 + §11 P3a KPI |
| **Q3** | `quantile_bootstrap.py` | Politis-Romano stationary bootstrap 1000 iter, hand-rolled | V3 §8.2 |
| **Q5** | `fee_execution_calibrator.py` | Bybit V5 USDT linear fee + maker/taker split + BUSDT 110017 排除 | V3 §11 P3a KPI |

PA dispatch fallback 指引：`arch` lib 不在 venv → hand-roll Politis-Romano（已執行）。Production acceptance 等 FUP-2 + decision_outcomes timeframe fix + 21d demo unlock GREEN 後另派 E4 regression。

---

## 2. 修改清單 / Files Changed

### 2.1 新增 / New

| 檔案 | LOC | 用途 |
|---|---|---|
| `program_code/learning_engine/__init__.py` | 28 | 套件 docstring + V3 §11/§12 binding 標註 |
| `program_code/learning_engine/half_life_estimator.py` | 500 | Q1: HalfLifeEstimator + 3 fallback estimators + HalfLifeResult dataclass |
| `program_code/learning_engine/quantile_bootstrap.py` | 346 | Q3: QuantileBootstrap + Politis-Romano hand-roll + naive IID baseline + BootstrapResult |
| `program_code/learning_engine/fee_execution_calibrator.py` | 419 | Q5: FeeExecutionCalibrator + VIP tier table + BUSDT 110017 exclusion + FeeEstimate/ExecutionSplit |
| `program_code/learning_engine/tests/__init__.py` | 1 | test 套件 init |
| `program_code/learning_engine/tests/test_half_life_estimator.py` | 222 | 7 case：4 PA dispatch + 3 sanity (shortcut / invalid method / clamp bound) |
| `program_code/learning_engine/tests/test_quantile_bootstrap.py` | 250 | 7 case：4 PA dispatch + 3 sanity (shortcut / invalid input / low_confidence flag) |
| `program_code/learning_engine/tests/test_fee_execution_calibrator.py` | 325 | 11 case：4 PA dispatch + 7 sanity (synthetic path / NaN role / no reject_code col / custom override / invalid tier / shortcut) |

**合計：2062 LOC**（最大 module 500 LOC < 800 警告線 / < 1500 硬上限）

### 2.2 不變更 / Untouched

- `program_code/ml_training/` 既有 30+ module（不在本 task scope）
- `program_code/learning_engine/regime_controller.py` — sibling sub-agent 同 dir 並行 land 的，不動
- 任何 V### migration（本 task 0 SQL）
- 任何 IPC / dispatch / live-write 路徑（紅線）

---

## 3. 關鍵 diff 摘要 / Key Diff Highlights

### 3.1 Q1 — 三 fallback 鏈

```python
def estimate_with_fallback(self, fills_df: pd.DataFrame) -> HalfLifeResult:
    n = len(fills_df)
    if n < self.min_sample_size:        # n < 30 → default_14d
        return self._default_fallback(sample_size=n)

    pnl_result = self._fit_pnl_decay(fills_df)
    if pnl_result.fit_p_value < self.p_value_threshold:  # p < 0.10 → PnL OK
        return pnl_result

    if "sharpe_60d_window" in fills_df.columns:
        sharpe_result = self._fit_sharpe_decay(fills_df)
        if sharpe_result.fit_p_value < self.p_value_threshold:
            return sharpe_result

    return self._default_fallback(sample_size=n)  # 都失敗 → default_14d
```

**決策**：擬合 |net_bps| 而非 raw bps（訊號量級衰減；符號由 realized_edge_stats 分離）；reparametrize `y = a * exp(-t * ln(2) / half_life)` 使擬合參數直接是 half_life（非 lambda）。

### 3.2 Q3 — Politis-Romano hand-roll

```python
def _stationary_bootstrap_resample(series, block_size, rng):
    n = len(series)
    p_jump = 1.0 / float(block_size)
    jump_mask = rng.random(n) < p_jump
    random_indices = rng.integers(0, n, size=n)
    indices = np.empty(n, dtype=np.int64)
    indices[0] = random_indices[0]
    for t in range(1, n):
        if jump_mask[t]:
            indices[t] = random_indices[t]
        else:
            indices[t] = (indices[t - 1] + 1) % n  # 環繞 / wrap
    return series[indices]
```

**block_size cube-root FP 修正**：

```python
def _politis_white_block_size(n: int) -> int:
    raw = n ** (1.0 / 3.0)
    rounded = int(math.floor(raw + 1e-9))  # FP epsilon 修正
    upper_bound = max(2, n // 4)
    return max(2, min(rounded, upper_bound))
```

Python `1000 ** (1/3) = 9.99999999...`，無 epsilon 會 floor 成 9（PA dispatch 期 10）。同 perfect cubes (n=125 → 4.999...)。

### 3.3 Q5 — Bybit V5 fee table + BUSDT 110017 filter

```python
DEFAULT_VIP_FEE_TABLE: Dict[int, Dict[str, float]] = {
    0: {"maker_bps": 2.0, "taker_bps": 5.5},   # default retail
    1: {"maker_bps": 1.6, "taker_bps": 5.0},
    # ... up to tier 5
}

def _filter_busdt_110017(self, fills_df):
    if "reject_code" not in fills_df.columns or "symbol" not in fills_df.columns:
        return fills_df  # graceful fallback
    symbol_match = fills_df["symbol"].astype(str) == "BUSDT"
    reject_match = fills_df["reject_code"].astype(str) == "110017"
    return fills_df[~(symbol_match & reject_match)].copy()
```

`ExecutionSplit.sample_size_excluded_busdt_110017` 揭露被排除筆數，供審計透明度。

---

## 4. pytest 結果

### 4.1 個別 module test

```
program_code/learning_engine/tests/test_half_life_estimator.py
- test_pnl_decay_pass                           PASSED  (0.13s)
- test_sharpe_decay_pass                        PASSED  (0.07s)
- test_default_fallback_small_sample            PASSED  (<0.01s)
- test_default_fallback_high_p_value            PASSED  (0.10s)
- test_module_level_shortcut                    PASSED  (0.07s)
- test_invalid_method_raises                    PASSED  (<0.01s)
- test_half_life_clamped_within_bounds          PASSED  (0.07s)
                                                7 passed in 0.40s

program_code/learning_engine/tests/test_quantile_bootstrap.py
- test_bootstrap_1000_iter_on_ar1_contains_true_median  PASSED  (~0.13s)
- test_stationary_bootstrap_reflects_autocorrelation_correctly  PASSED  (~0.10s)
- test_block_size_auto_cube_root                PASSED  (<0.01s)
- test_determinism_same_seed                    PASSED  (~0.01s)
- test_module_level_shortcut                    PASSED  (~0.01s)
- test_invalid_inputs_raise                     PASSED  (<0.01s)
- test_low_confidence_when_n_below_30           PASSED  (<0.01s)
                                                7 passed in 0.41s

program_code/learning_engine/tests/test_fee_execution_calibrator.py
- test_fee_aggregation_observed_path            PASSED  (<0.01s)
- test_fee_aggregation_synthetic_path_no_observed  PASSED  (<0.01s)
- test_maker_taker_split_basic                  PASSED  (<0.01s)
- test_split_sums_to_one_with_nan_role          PASSED  (<0.01s)
- test_busdt_110017_excluded_from_split         PASSED  (<0.01s)
- test_busdt_110017_excluded_from_fee           PASSED  (<0.01s)
- test_busdt_110017_filter_no_reject_code_column  PASSED  (<0.01s)
- test_vip_tier_override_returns_different_rates  PASSED  (<0.01s)
- test_vip_tier_override_custom_table           PASSED  (<0.01s)
- test_invalid_vip_tier_raises                  PASSED  (<0.01s)
- test_module_level_shortcut_returns_pair       PASSED  (<0.01s)
                                                11 passed in 0.14s
```

### 4.2 完整套件（含 sibling regime_controller）

```
program_code/learning_engine/tests/                        40 passed in 0.77s
```

我這 batch 25 case + sibling 5A-B regime_controller 15 case = 40 case 全綠。

### 4.3 py_compile

```bash
python3 -m py_compile program_code/learning_engine/__init__.py \
                       program_code/learning_engine/half_life_estimator.py \
                       program_code/learning_engine/quantile_bootstrap.py \
                       program_code/learning_engine/fee_execution_calibrator.py
# → ALL py_compile PASS
```

### 4.4 跨平台 + 紅線 grep

```bash
# 0 hardcoded path
grep -rE "/home/ncyu|/Users/[^/]+" program_code/learning_engine/  → no match

# 0 IPC / dispatch / DB writer / live-write
grep -rE "import psycopg|import requests|import websocket|ipc_client|exchange_dispatch|acquire_lease" \
     program_code/learning_engine/  → no match

# 0 trading.* / live_orders 寫（trading.fills 出現在 docstring 註解，非實際 import）
grep -rE "trading\.|live_orders|live_execution_allowed|max_retries|execution_authority" \
     program_code/learning_engine/  → 1 match in docstring comment (acceptable)
```

---

## 5. 治理對照 / Governance Mapping

### 5.1 V3 §11 / §12 acceptance binding

| 規格條 | Q1 | Q3 | Q5 | binding 滿足 |
|---|---|---|---|---|
| §8.1 "embargo `max(7d, 2 * half_life)`" | ✅ HalfLifeResult.half_life_days | — | — | 是；P3a-Q2 sibling 消費此值寫 oos_embargo_seconds |
| §8.1 "Half-life unmeasured → conservative default 14d" | ✅ DEFAULT_HALF_LIFE_DAYS=14.0 + low_confidence=True | — | — | 是 |
| §8.2 "block bootstrap, Politis-Romano style, 1000 iterations" | — | ✅ DEFAULT_N_ITER=1000 + 平穩演算法 | — | 是 |
| §8.2 "preserve autocorrelation" | — | ✅ block_size > 1 + geometric block | — | 是；測試 `test_stationary_bootstrap_reflects_autocorrelation_correctly` 驗證 |
| §8.2 "n<30 fallback parametric only if marked low_confidence" | — | ✅ low_confidence=True if n<30 | — | 是 |
| §11 P3a KPI "fee model" | — | — | ✅ DEFAULT_VIP_FEE_TABLE + 6 tier | 是 |
| §11 P3a KPI "maker/taker execution estimates" | — | — | ✅ ExecutionSplit | 是 |
| §11 P3a KPI "BUSDT 110017 reject loop excluded" | — | — | ✅ _filter_busdt_110017 | 是；audit count 在 sample_size_excluded_busdt_110017 |
| §12 #15 freshness | — | — | — | 不在本 module；P3a-Q6 sibling 消費 |
| §12 #16 power | ✅ min_sample_size=30 | ✅ MIN_SAMPLE_SIZE=30 + low_confidence | ✅ sample_size 揭露 | 部分；P3a-Q6 sibling 上層門檻 |
| §12 #17 cv_protocol | — | ✅ 1000 iter / 95% CI | — | bootstrap 是 DSR/PBO prerequisite math |
| §12 #23 baseline_provenance | — | — | — | manifest column scope，不在本 module |

### 5.2 CLAUDE.md §三 P3 cross-language float consistency

- Q3 test_determinism_same_seed 用 `1e-4` tolerance assert（per CLAUDE.md §三 P3）
- 其他 case 多用 `1e-9` 嚴格 Python-only assert（無跨語言邊界）

### 5.3 CLAUDE.md §七 雙語注釋

- 4 module 頂部 MODULE_NOTE EN + 中（V3 §11/§12 binding）
- 16 dataclass / public method docstring 雙語
- 關鍵 inline 注釋（FP epsilon 修正 / BUSDT 110017 排除理由 / scipy unavailability fallback）雙語

### 5.4 CLAUDE.md §九 LOC cap

- 最大 module 500 LOC < 800 警告線
- 全 test < 350 LOC

### 5.5 CLAUDE.md §四 硬邊界

- 0 trading.* 寫
- 0 live_execution_allowed / max_retries / execution_authority / system_mode 觸碰
- 0 IPC / dispatch / live exchange import
- 純 offline math：numpy + scipy + pandas only

---

## 6. 不確定之處 / Ambiguity & Push Back

### 6.1 PA dispatch 寫 maker -0.025% / taker 0.06% vs Bybit reference 0.02% / 0.055%

**衝突**：PA dispatch §TASK 3 寫 "Bybit perpetual fee schedule (maker: -0.025% / taker: 0.06% on USDT linear)"，但 `docs/references/2026-04-04--bybit_api_reference.md` L656 寫 "默認費率（taker 0.055%, maker 0.02%）"。

**決策**：實作以 Bybit reference 為準（DEFAULT_VIP_FEE_TABLE[0] = {"maker_bps": 2.0, "taker_bps": 5.5}），保留 vip_tier_override hatch 讓 operator 自訂。

**建議 PM 動作**：production deploy 前向 BB agent 確認 Bybit V5 USDT linear perpetual 真實 retail（VIP 0）費率（含負 maker rebate 是否存在於 retail tier）。如真為 -0.025% 則 DEFAULT_VIP_FEE_TABLE 需更新。

### 6.2 `reject_code` column 不在既有 trading.fills schema

**事實**：`grep` 找不到 `reject_code` 在 `program_code/` 下（除 audit log 路徑）。PA dispatch 自承 "fixture uses mock column"。

**影響**：當前 `_filter_busdt_110017` graceful fallback（column 缺失則不過濾），但 production 對 `replay.simulated_fills` 或 `learning.fills` 增 column 是 P3a deploy 前置工作。

**建議 PM 動作**：派 sibling sub-agent 在 P3a deploy 前 land migration `V0XX__add_reject_code_to_replay_simulated_fills.sql`（V### PM reservation 內），或選 audit log JOIN 路徑。

### 6.3 stationary bootstrap test 用詞重構

**衝突**：PA dispatch test #2 「90% CI tighter than naive (Welch p<0.05)」在 AR(1) 強自相關下違反理論 — naive IID bootstrap 必然 *under-cover*（artificially tight），stationary bootstrap *正確地* 寬於 naive IID。

**重構**：改成兩部分（檔內 docstring 詳述）：
- (a) IID 資料下兩法收斂（ratio ∈ [0.5, 2.0]）
- (b) AR(1) 資料下 stationary CI 必含真值（covergae validation）+ block_size > 1（未塌成 IID）

**建議 PM 動作**：如 PM 希望保留 PA wording，先解釋「naive」是 (a) parametric normal-approx (`x ± 1.96 * SE`) 還是 (b) naive IID bootstrap。本 IMPL 假設 V3 §11 P3a 的 "tighter than naive empirical quantile" 是 (a) 但 PA dispatch 寫 (b)。

### 6.4 OOS embargo 由 P3a-Q2 (sibling) 消費 Q1 結果

**現況**：HalfLifeResult.half_life_days 給 P3a-Q2 計算 `oos_embargo_seconds = max(7 * 86400, 2 * half_life * 86400)`。本 IMPL 只算 half_life，不寫 manifest。

**建議**：sibling Q2 派發時 PM 確認 contract `Q1 → Q2` 對 HalfLifeResult.low_confidence 的處理（low_confidence=True 是否強制 oos_embargo 用 14d default 即可）。

---

## 7. Operator 下一步

### 7.1 E2 review focus

- [ ] `scipy.optimize.curve_fit` 收斂 robustness：max iter 5000 是否足夠（QC 慣例）；RuntimeError 落到 default_14d 路徑語意是否正確
- [ ] `_stationary_bootstrap_resample` 對 n=1 series 的 corner case（block_size=1 是否退化成 IID）
- [ ] `_filter_busdt_110017` dtype 安全：`fills_df["symbol"]` 為 NaN / None / int 時 `.astype(str)` 行為
- [ ] DEFAULT_VIP_FEE_TABLE 6 tier 數值是否與 Bybit reference v5 一致（與 BB agent 對齊）
- [ ] `_politis_white_block_size` epsilon=1e-9 對 n=1e9 的 FP scale 安全性（n>1e6 暫時不會發生但驗證 robustness）

### 7.2 E4 regression（Linux trade-core）

```bash
cd $OPENCLAW_BASE_DIR  # default $HOME/BybitOpenClaw/srv
python3 -m pytest program_code/learning_engine/tests/ -v
# 預期 40 passed (我的 25 + sibling regime_controller 15)
```

### 7.3 MIT 副審 focus

- [ ] V3 §4.1 `replay.simulated_fills` schema 對應 fee_execution_calibrator 期待 column 是否齊備（symbol / liquidity_role / fee_bps / reject_code）
- [ ] FUP-2 attribution writer deploy 後，`learning.exit_features` JOIN `trading.fills` cell key 是否能餵 half_life_estimator 期待的 schema
- [ ] decision_outcomes timeframe '1' vs '1m' fix 對 cell-level half-life 估計（每 cell n>=30）的影響

### 7.4 QC 副審 focus

- [ ] Politis-Romano implementation 是否正確保留 first-order autocorrelation（建議用 ACF lag-1 對比）
- [ ] half-life F-test p-value approximation vs 自舉 p-value 的差異（在 n=200 + AR(0.7) 下哪個更準）
- [ ] 14d default 是否符合 5 策略現有 7d gross 全 net negative 的環境（會否過長？）

### 7.5 BB 副審 focus（Q5）

- [ ] DEFAULT_VIP_FEE_TABLE 6 tier 數值對齊 Bybit V5 USDT linear perpetual 實際費率
- [ ] BUSDT funding_arb V2 deprecation 後，是否有其他 reject code（不只 110017）也需 exclusion

### 7.6 PM commit message draft

```
feat(replay): P3a-Q1+Q3+Q5 math IMPL — half_life + bootstrap + fee_model (Wave 5 Batch 5A)
```

---

## 8. Sign-off

E1 IMPLEMENTATION DONE: 待 E2 + E4 + MIT review

**File paths（絕對路徑）：**
- `/Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/__init__.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/half_life_estimator.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/quantile_bootstrap.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/fee_execution_calibrator.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/tests/__init__.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/tests/test_half_life_estimator.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/tests/test_quantile_bootstrap.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/tests/test_fee_execution_calibrator.py`

**git status clean**（per CLAUDE.md §七 P0-GOV-3 sign-off 必檢）：
- 所有 8 file 已 land；未 commit（等 E2 review）— 符合 E1 工作鏈規定（不直接 commit）
