# E1 R2 — P1/P2 close_maker healthcheck E2 RETURN fix · 2026-05-21

## 任務摘要

E2 R1 review verdict = RETURN to E1（2 HIGH MUST-FIX + 2 MEDIUM + 2 LOW）。
本 R2 修 4 個 issue（A1/A2/E1/F1）+ 1 optional polish（F3）。MEDIUM-D1 Wilson
upper bound 暫不加（per E2 spec：不阻 merge，可 follow-up ticket）。

R1 → R2 結果：82/82 → **83/83 tests pass**（新加 1 個 production-string match
adversarial test `test_default_patterns_match_real_production_exit_reasons`）。

## 修改清單

| 改動 | 檔 | 改動類型 |
|---|---|---|
| Rename file | `helper_scripts/canary/healthchecks/71_close_maker_pre_stopout_rate.py` → `66_close_maker_pre_stopout_rate.py` | F1 |
| Rename test file | `helper_scripts/canary/healthchecks/tests/test_71_pre_stopout_rate.py` → `test_66_pre_stopout_rate.py` | F1 |
| `DEFAULT_STOPOUT_EXIT_REASON_PATTERNS` 全替 | `66_close_maker_pre_stopout_rate.py:154-164` | A1+A2 |
| `check_id "[71]"` → `"[66]"` | `66_close_maker_pre_stopout_rate.py:341` | F1 |
| MODULE_NOTE patterns 描述更新 | `66_close_maker_pre_stopout_rate.py:1-95` | A1+A2+F1 |
| Inline patterns comment 更新（含 risk_checks.rs line ref） | `66_close_maker_pre_stopout_rate.py:128-164` | A1+A2 |
| `_parse_args` name 從 `71_` → `66_` | `66_close_maker_pre_stopout_rate.py:175-180` | F1 |
| Conftest fixture `hc71` → `hc66` | `tests/conftest.py:60-67` | F1 |
| Test 整檔重寫（含新 production-string test） | `tests/test_66_pre_stopout_rate.py` | A1+A2+E1+F1 |
| `__init__.py` docstring 補 [66] 入口 + slot 邊界說明 | `__init__.py:1-39` | F2 |
| 刪 `overall_verdict = "PASS"` dead init | `62_close_maker_fill_rate.py:225` | F3 |

## 每個 issue 修法 + verify

### HIGH-A1 + HIGH-A2: stopout patterns 大小寫錯誤 + 漏 DYNAMIC STOP

**位置**：`66_close_maker_pre_stopout_rate.py:154-164` `DEFAULT_STOPOUT_EXIT_REASON_PATTERNS`

**修法**：grep `rust/openclaw_engine/src/risk_checks.rs` + `helpers_close_tags.rs`
完整 emission chain 後，patterns 全替：

```python
DEFAULT_STOPOUT_EXIT_REASON_PATTERNS: tuple[str, ...] = (
    # 大寫 + 空格家族（risk_checks.rs:334/355/379/390 format!() emit）
    "HARD STOP%",        # risk_checks.rs:334
    "DYNAMIC STOP%",     # risk_checks.rs:355（R2 HIGH-A2 補）
    "TIME STOP%",        # risk_checks.rs:390
    "TRAILING STOP%",    # risk_checks.rs:379
    # 小寫底線家族
    "trailing_stop%",    # strategies/bb_breakout/mod.rs:910/919（lowercase）
    "fast_track%",       # step_0_fast_track.rs:486/500/603/616
    "halt_session%",     # helpers_close_tags.rs:122-127 R-A5 fallback prefix
    "phys_lock_%",       # physical_micro_profit_lock_v2 emit
)
```

**Source verify**（grep 自驗，不 trust prompt）：
- `risk_checks.rs:334` `format!("HARD STOP: pnl {:.2}% <= -{:.2}%", ...)`
- `risk_checks.rs:355` `format!("DYNAMIC STOP: pnl ... (regime=..., atr=...)")`
- `risk_checks.rs:379` `format!("TRAILING STOP: peak ...")`
- `risk_checks.rs:390` `format!("TIME STOP: held {:.1}h >= limit {:.1}h ...")`
- `helpers_close_tags.rs:122-127` HaltSession R-A5 強制 `risk_close:halt_session`
  prefix（涵蓋 SESSION DRAWDOWN / DAILY LOSS / CONSECUTIVE LOSS）
- `step_0_fast_track.rs:486/500/603/616` emit `risk_close:fast_track_*`
- `strategies/bb_breakout/mod.rs:910/919` emit lowercase `trailing_stop`
- `strategies/common/maker_price.rs:528/529` 確認 `phys_lock_gate4_giveback` /
  `phys_lock_gate4_stale_roc_neg`

Chain 完整：`risk_close:HARD STOP: ...` → `build_close_tags_from_legacy` strip
`risk_close:` → `exit_reason="HARD STOP: ..."` 大寫保留寫入 trading.fills。

**Verify**：`test_default_pattern_list_contains_known_stopout_reasons` (R1 強化版
驗 8 個前綴存在) + 新 `test_default_patterns_match_real_production_exit_reasons`
驗 12 個 production 真實字串全 match + 8 個非 stopout 字串全 0 match。83/83 pass。

### MEDIUM-E1: test 沒驗 production 真實字串

**位置**：`tests/test_66_pre_stopout_rate.py`

**修法**：補新 test `test_default_patterns_match_real_production_exit_reasons`：
- Helper `_sql_like_to_fnmatch` + `_sql_like_match` 用 stdlib `fnmatch` 模擬
  PG LIKE 行為（`%` → `*`）
- Fixture `EXPECTED_STOPOUT_EXIT_REASONS` 12 個從 risk_checks.rs / step_0_fast_track.rs
  / bb_breakout/mod.rs / helpers_close_tags.rs grep 出來的真實字串
- Fixture `EXPECTED_NON_STOPOUT_EXIT_REASONS` 8 個 graceful exit + TP 字串
- 正向 assert：每個 stopout 字串至少命中一個 default pattern（否則紅報「漏字根
  或大小寫錯」）
- 反向 assert：每個非 stopout 字串 0 命中（否則紅報「pattern 過寬會把 graceful
  exit 誤計入 stopouts」）

**Adversarial verify**：把 patterns 改回 R1 lowercase + 漏 DYNAMIC STOP，跑同
邏輯確認 `HARD STOP:` / `DYNAMIC STOP:` / `TIME STOP:` 三條 0 match → 新 test
設計上確實能 catch HIGH-A1+A2 regression。

```
'HARD STOP: pnl -25.00% <= -20.00%'                -> matches=[]
'DYNAMIC STOP: pnl -8.50% <= -7.20% (regime=...)' -> matches=[]
'TIME STOP: held 24.0h >= limit 24.0h (regime=...)' -> matches=[]
```

### MEDIUM-F1: [71] slot 編號碰撞

**修法**：cross-namespace rename `[71]` → `[66]`（standalone canary
[62][63][64][65] 鄰近 slot；passive_wait 用 [70-74]，[66] 全 namespace 唯一）：

1. File rename：`71_close_maker_pre_stopout_rate.py` → `66_close_maker_pre_stopout_rate.py`
2. Test file rename：`test_71_pre_stopout_rate.py` → `test_66_pre_stopout_rate.py`
3. `check_id` 從 `"[71]"` → `"[66]"` (line 341)
4. `_parse_args` description `[71]` → `[66]` (line 177)
5. Conftest fixture `hc71` → `hc66` + module name `hc71_pre_stopout_rate` →
   `hc66_pre_stopout_rate`
6. 9 test functions + 9 `hc71` parameter → `hc66`
7. MODULE_NOTE + docstring 全 `[71]` → `[66]` + 新增 Slot 命名歷史段
8. `__init__.py` docstring 列入 [66] 並補 slot 邊界說明

**Verify cross-namespace grep**：
```
helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py:341: "check_id": "[66]"
helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py:112: assert result["check_id"] == "[66]"
helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py:443: schema = _schema_guard(cur, "[71]")
```
canary `[66]` 不再與 passive_wait `[71]` 碰撞。

### LOW-F2: `__init__.py` docstring 沒更新

**位置**：`__init__.py:1-39`

**修法**：
- 入口列表從 4 個 (`62/63/64/65`) → 5 個 (`62/63/64/65/66`)
- 補新 slot 編號邊界段（canary [62-66] vs passive_wait [70-74]）
- [66] 條目註明 `P1-OBS-PRE-STOPOUT-RATE`、`2026-05-21 FA round 1 #5`、閾值
  `0.10 PASS / 0.30 FAIL`、「R2 從 [71] rename 避碰」歷史

### LOW-F3: `62_close_maker_fill_rate.py:225` dead init

**位置**：`62_close_maker_fill_rate.py:225`

**Static analysis**：line 225 `overall_verdict = "PASS"` init，
- not rows path (line 230) 覆蓋為 INSUFFICIENT_SAMPLE
- else path 中 stratify="none" (line 280) 重置為 "PASS" + severity_max loop
- else path 中 stratify!="none" (line 282) 直接賦值 `_stratified_overall_verdict(...)`

兩條路徑都本地賦值，刪 init 安全。

**修法**：刪 line 225 init，補 comment 記錄為何 dead init 已清。
跑 pytest test_62_fill_rate.py 20 個 case 全 pass，包含 stratify=none/hour/dow/both
四個分支 + INSUFFICIENT_SAMPLE / FAIL / WARN cells 路徑覆蓋。

### MEDIUM-D1 (deferred): Wilson upper bound sub-clause

E2 spec 標「不阻 merge」+「可 follow-up ticket」。R2 不加；MODULE_NOTE 內
`_stopout_rate_verdict` docstring 已說明 raw rate vs Wilson 設計理由。

## Pytest 結果

```
83 passed in 0.04s
```

R1 = 82/82。R2 新加 `test_default_patterns_match_real_production_exit_reasons`
1 個 case → 83/83，全綠。其中 [66] 路徑 11 cases 全綠（含新 production-string
adversarial test）。

## 治理對照

- 中文注釋 default：✓（新 patterns 描述 + slot 命名歷史段 + MEDIUM-E1 新 test
  docstring 全中文）
- 不改 `_common.py`：✓（共享 helper 凍結）
- 維持 ≤ 800 行：✓（66 = 392 行；62 = 336 行；test_66 = 301 行）
- 跨檔 rename 同步：✓（file / test file / conftest fixture / module name /
  `__init__.py` / docstring 全部對齊）
- 跨平台 `/home/ncyu` / `/Users/[^/]+` hardcoded：✓ 0 hit
- SQL 參數化：✓（patterns / liquidation pattern / window_secs / engine_modes 全
  psycopg2 bind）
- Migration Guard A/B/C：n/a（純 Python healthcheck，無 SQL DDL）
- 新 singleton：n/a
- 私有屬性穿透：✓ 0 hit
- Bybit API 改動：n/a

## 不確定之處

無 ambiguity。R1 → R2 修全 source-derived（risk_checks.rs format!() literal
+ helpers_close_tags.rs strip chain 完整 grep），不靠 prompt 列表。

唯一 deferred = MEDIUM-D1 Wilson upper bound（E2 spec 標非 blocker）；若 PM
未來決定加，建議：在 [66] cells loop 內補 Wilson upper > 0.20 / > 0.40 sub-clause
（mirror AC-18 QC-SF-6 機制），跟 raw rate 雙軌取較嚴的 verdict。

## Operator 下一步

1. PM 派 E2 R2 review（per `feedback_impl_done_adversarial_review`；HIGH 修不可
   直接 E4）
2. E2 重點 verify：
   - patterns 對齊 production（grep risk_checks.rs 自驗 4 條大寫 + 4 條小寫）
   - 新 test `test_default_patterns_match_real_production_exit_reasons` 設計合理
   - slot rename 跨檔同步無遺漏
   - [62] dead init 清理不影響 stratify branches
3. E2 R2 PASS 後 → E4 regression → QA → PM commit + push

## 檔案路徑

- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py`
  （new file rename from 71_*）
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/62_close_maker_fill_rate.py`
  （dead init 清理）
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/__init__.py`
  （docstring 補 [66] 入口 + slot 邊界）
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py`
  （new file rename + production-string test 補）
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/tests/conftest.py`
  （hc66 fixture rename）

E1 R2 FIX DONE: 待 E2 R2 review · report path:
`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p1_p2_close_maker_healthcheck_round2_fix.md`
