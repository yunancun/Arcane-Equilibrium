# E1 IMPL — P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE

- Date: 2026-05-21
- Branch/HEAD: (working tree change，未 commit；待 E2 review)
- Spec source: E2 R2 review (2026-05-20 C 批) MEDIUM-D1 deferred follow-up
- Operator prompt: 2026-05-21 P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE

## 任務摘要

E2 R2 review 提到 [66] close_maker_pre_stopout_rate.py verdict 用 raw rate +
雙閾值 0.10 / 0.30 + min_sample=30，但缺少 conservativeness sub-clause。任務
要求 mirror [62] AC-18 Wilson 95% CI 風格，補上 Wilson upper / lower bound
sub-clause 提升 small-sample 與 over-shoot 早期偵測信號強度。

## 修改清單

| 檔 | 改動 |
|---|---|
| `helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py` | 加 `wilson_ci_95` import；`_stopout_rate_verdict` 由 `tuple[str, float]` 改為 `tuple[str, float, float, float]` 並接 `use_wilson` / `wilson_upper_pass` / `wilson_lower_fail`；`run()` 同步 propagate 並暴露於 `cells[*].wilson_lower` / `wilson_upper` + `result["thresholds"]` + `result["use_wilson_subclause"]`；`_parse_args` 加 3 個 CLI flag `--no-wilson` / `--wilson-upper-pass` / `--wilson-lower-fail`；module docstring & ladder 段落改寫 |
| `helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py` | +5 新 test case：`test_pass_when_wilson_upper_within_bound` / `test_warn_when_raw_passes_but_wilson_upper_exceeds` / `test_fail_via_raw_rate_regardless_of_wilson` / `test_fail_via_wilson_lower_when_raw_under_fail_upper`（含反向 `--no-wilson` 對照）/ `test_insufficient_sample_unchanged_under_wilson` |

## Verdict ladder 改動（前 vs 後）

### 改動前（R1）

```
n < min_sample → INSUFFICIENT_SAMPLE
rate ≤ pass_upper (0.10) → PASS
rate > fail_upper (0.30) → FAIL
其他 → WARN
```

### 改動後（R2 MEDIUM-D1，default Wilson sub-clause 啟用）

```
n < min_sample (30) → INSUFFICIENT_SAMPLE
FAIL = (raw > fail_upper 0.30) OR (Wilson lower > wilson_lower_fail 0.20)
PASS = (raw ≤ pass_upper 0.10) AND (Wilson upper ≤ wilson_upper_pass 0.15)
其他 → WARN
```

`--no-wilson` opt-out 退回 R1 ladder（已加 test 反向驗證）。

### Mirror [62] AC-18 對稱性

- [62] success-direction（rate 越高越好）：
  - PASS = Wilson **lower** ≥ pass_lower（即使 raw 高，要下界穩）
  - FAIL = Wilson **upper** < warn_lower（即使 raw 中，要上界已低）
- [66] failure-direction（rate 越低越好），對稱反轉：
  - PASS = raw ≤ pass_upper **AND** Wilson **upper** ≤ wilson_upper_pass（即使 raw 低，要上界也穩）
  - FAIL = raw > fail_upper **OR** Wilson **lower** > wilson_lower_fail（即使 raw 還沒過 fail_upper，下界已超即可判 over-shoot）

[62] 走的是「PASS 嚴 / FAIL 嚴」（success-direction 雙條件 AND/嚴）；
[66] 走「PASS AND / FAIL OR」反映 failure metric 的保守性質：寧 WARN 不誤 PASS、
寧 FAIL 不放縱 lower。

## 關鍵 diff（節錄 — 不含 docstring 改寫）

```python
# 66_close_maker_pre_stopout_rate.py — _stopout_rate_verdict 新簽名 + Wilson 分支

def _stopout_rate_verdict(
    stopouts: int,
    total: int,
    min_sample: int,
    pass_upper: float,
    fail_upper: float,
    *,
    use_wilson: bool = True,
    wilson_upper_pass: float = 0.15,
    wilson_lower_fail: float = 0.20,
) -> tuple[str, float, float, float]:
    if total < min_sample:
        rate = stopouts / total if total else 0.0
        return (VERDICT_INSUFFICIENT_SAMPLE, rate, 0.0, 0.0)
    rate = stopouts / total
    lower, upper = wilson_ci_95(stopouts, total)
    if not use_wilson:
        # R1 raw-rate-only ladder
        if rate <= pass_upper:
            return (VERDICT_PASS, rate, lower, upper)
        if rate > fail_upper:
            return (VERDICT_FAIL, rate, lower, upper)
        return (VERDICT_WARN, rate, lower, upper)
    # R2 Wilson sub-clause（default）
    if rate > fail_upper or lower > wilson_lower_fail:
        return (VERDICT_FAIL, rate, lower, upper)
    if rate <= pass_upper and upper <= wilson_upper_pass:
        return (VERDICT_PASS, rate, lower, upper)
    return (VERDICT_WARN, rate, lower, upper)
```

## Test 計數

- Baseline (整個 healthchecks/tests/ collect): **83 passed**
- 改動後: **88 passed** （+5 R2 MEDIUM-D1 case）
- 對應任務 spec「83+5=88」分支

## Sanity 驗算（pytest 之外的 manual 驗證）

```
(10, 200) raw=0.0500 lower=0.0274 upper=0.0896 → PASS   ✓
(4,   50) raw=0.0800 lower=0.0315 upper=0.1884 → WARN   ✓ (raw 過、Wilson upper 超 0.15)
(40, 100) raw=0.4000 lower=0.3094 upper=0.4980 → FAIL   ✓ (raw FAIL，與 R1 一致)
(250,1000) raw=0.2500 lower=0.2242 upper=0.2778 → FAIL  ✓ (raw 還沒過 0.30，Wilson lower 超 0.20)
(10,  29) n<30 → INSUFFICIENT_SAMPLE，wilson sentinel (0,0)  ✓
```

第 4 行就是 sub-clause 的 raison d'être — R1 在此 fixture 會回 WARN（任務在
測試裡同時 assert 了 `--no-wilson` 對照組仍回 WARN）。

## 後向兼容

- 既有 4 個 R1 test (`test_pass_when_low_stopout_rate` / `test_warn_in_middle_zone`
  / `test_fail_when_above_fail_upper` / `test_multi_engine_takes_most_severe`)
  以 default Wilson 模式跑也全綠 — 因為 fixture (n=100) 的 Wilson CI 不會把
  原 verdict 拉到不同 bucket：(5,100) upper=0.1118<0.15 仍 PASS；(20,100)
  仍中段 WARN；(50,100) raw FAIL；multi case 不變。
- `result["cells"][*]` 多了 `wilson_lower` / `wilson_upper` 兩個 key，但既有
  R1 test 只 assert `stopout_rate` / `verdict` — 新增 key 不打斷。
- `result["thresholds"]` 多 `wilson_upper_pass` / `wilson_lower_fail`；
  `result` top-level 多 `use_wilson_subclause`。
- CLI 新增 3 個 flag，全部有 default，operator 既有 invocation 不需改。

## 治理對照

- 範圍：嚴格按 prompt 指定文件，未動 `_common.py`（Wilson helper 已在那
  裡複用，不修改）；未動 SQL；未動 `risk_close:` strip chain。
- 注釋：default 中文；技術名 `Wilson` / `pass_upper` / `LIKE` / `Wilson upper
  pass` 等英文保留。
- argparse 注意：`Wilson 95% CI` help 字串需 `%%` escape 避 `_expand_help`
  ValueError，已修並驗 `--help` render。
- min_sample 仍走 R1 sentinel `(verdict, rate, 0.0, 0.0)` 設計（mirror [62]
  `_common.fill_rate_verdict`）；新加 test 驗 `wilson_lower==0.0` /
  `wilson_upper==0.0` 防 downstream 把 sentinel 誤讀成真實 CI。

## 不確定之處 / Push Back

無重大 push back。三點次要觀察：

1. **PASS test (10,200) 實際 Wilson upper ≈ 0.0896** — 任務描述用 0.12 表示，
   實算值更低；不影響 PASS 判定（兩者都 ≤ 0.15）。test docstring 寫實際值。
2. **FAIL via Wilson lower 場景需要 n ≈ 1000** — 小樣本 (n~100) raw=0.25 的
   Wilson lower 約 0.17 不超 0.20。這是 Wilson 本質的正確行為（小樣本要更
   多 evidence 才允升級為 FAIL），test docstring 已標註「Wilson sub-clause
   只在大樣本時補強訊號，小樣本停在 WARN 等更多 evidence」。E2 若覺得這對
   實 production 數據量（demo n 通常 < 200 / week）「太晚 trigger」，可考慮：
   - 降 `wilson_lower_fail` 至 0.15 / 0.17（更激進）
   - 或保 0.20 但補一條 raw rate ≥ 0.25 AND n ≥ 200 的中段 conservatism
   目前 sticking with prompt 給的 0.20，請 E2 / FA 決議。
3. **`severity_max` 對 INSUFFICIENT_SAMPLE 行為與 [62] 一致** — multi-engine
   出現 (PASS, INSUFFICIENT_SAMPLE) 時 INSUFFICIENT_SAMPLE 排序高於 PASS
   （`_common.severity_max` order: PASS=0 < INSUFFICIENT=1 < WARN=2 < FAIL=3），
   意味 multi-cell aggregation 會被 INSUFFICIENT 拉成 INSUFFICIENT。本 patch
   未動此邏輯，但若未來 (one cell PASS Wilson tight + one cell INSUFFICIENT)
   想合報為 PASS-with-caveat，需另開 ticket。

## Operator / E2 下一步

1. **E2 review**：對齊 mirror [62] AC-18 風格、PASS AND / FAIL OR 不對稱性
   是否正確、Wilson 門檻 0.15 / 0.20 是否合理（vs. raw 0.10 / 0.30 的距離）、
   `wilson_lower==0.0 sentinel` 是否需要顯示為 `null` 給 downstream。
2. **E4 regression**：跑全 healthcheck pytest + 任何外部 CI 對 `wilson_lower
   / wilson_upper` key 的 schema sensitivity。
3. **QA**：如果 E2 通過，QA 拿 production demo 過去 7d fills 跑 `--text`
   觀察 (n, rate, wilson_lower, wilson_upper, verdict) cell 對 raw / Wilson
   行為是否合理。
4. **PM**：commit + push（強制鏈 E1→E2→E4→QA→PM）。

## 檔案絕對路徑

- 改動 1：`/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py`
- 改動 2：`/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py`
- 本 report：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p2_obs_pre_stopout_wilson_subclause.md`

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p2_obs_pre_stopout_wilson_subclause.md）
