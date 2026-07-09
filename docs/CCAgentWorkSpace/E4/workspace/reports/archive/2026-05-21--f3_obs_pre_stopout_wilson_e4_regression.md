# E4 Regression Report — F3 P2-OBS-PRE-STOPOUT-WILSON · 2026-05-21

## 範圍

F3 P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE (DEFER-D1 follow-up) light regression。

工作鏈：
- PA spec → E1 R1 IMPL（+88 LOC / 5 new tests / 88 PASS）
- E2 R2 APPROVE-CONDITIONAL（Wilson 公式 + 對稱反轉 + 5 test 真實覆蓋全 PASS；建議 `wilson_lower_fail` default 0.20 → 0.15 避 demo velocity n~70/week dead gate）
- PM 主會話 inline 修：default 0.20 → 0.15（4 處 — docstring 2 處 + argparse default + test assertion）
- E4 light regression（本報告）

改動 2 files（純 Python read-only healthcheck observability layer）：
- 改 `helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py` (392 → 492，+100 LOC：docstring 大改 + Wilson CLI flags + _stopout_rate_verdict 簽名擴展 + run() kwargs propagation)
- 改 `helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py` (301 → 484，+183 LOC：5 new Wilson sub-clause tests + EXPECTED_* fixture 對齊備註)

E4 範圍：light（純 Python pytest + cross-module 不破 + CLI + adversarial catcher 真實性 + 規範驗證 + mock 真實性 spot check）。Rust regression + Linux PG empirical + Deploy 不在 scope（observability layer，不 deploy / 純 Python 無 Rust counterpart）。

HEAD 對齊 PM 主會話 inline 修後狀態。

---

## VERDICT: **PASS**

- pytest 88/88 PASS（healthchecks/tests/ scope）× 3 runs identical green（0.04s / 0.04s / 0.04s, non-flaky）
- cross-module canary/ 212/212 PASS × 2 runs（31.21s / 31.17s, non-flaky）
- passive_wait [71] `test_close_maker_audit_healthcheck.py` 8/8 + 14 subtests PASS（cross-namespace 不擾）
- CLI / argparse / `--no-wilson` / `--wilson-lower-fail 0.15` 預設全 OK
- **adversarial regression catcher 真實**：strip `run()` line 338 default `0.15` → `0.20` → `test_pass_when_wilson_upper_within_bound` line 362 RED（`assert 0.2 == 0.15`）→ byte-identical restore → GREEN
- 規範全綠（file size 492/484 ≤ 800 / 0 emoji / 0 hardcoded path / 中文注釋默認）
- mock 真實性 5-spot 全 OK，無 self-consistent fake-success（Wilson 5 new test 全 real 計算）
- 0 新外部 dependency（`wilson_ci_95` 同 package `_common` 內 pre-existing 函數）

可進 PM commit + push。

---

## 數字總表

| 引擎 | passed | failed | baseline | delta | verdict |
|---|---|---|---|---|---|
| Python pytest (healthchecks/tests/) 1st | 88 | 0 | 88 (E2 R2 自跑) | 0 | ✓ |
| Python pytest (healthchecks/tests/) 2nd | 88 | 0 | 88 | 0 | ✓ |
| Python pytest (healthchecks/tests/) 3rd | 88 | 0 | 88 | 0 | ✓ non-flaky |
| Python pytest (canary/) 1st | 212 | 0 | 207 (5/21 P1-WATCHDOG-NETOUTAGE R2) + 5 sibling drift | 0 | ✓ |
| Python pytest (canary/) 2nd | 212 | 0 | 同 | 0 | ✓ non-flaky |
| Python pytest (helper_scripts/db/test_close_maker_audit_healthcheck.py) | 8 + 14 subtests | 0 | 8/8 + 14 (5/21 早晨) | 0 | ✓ |

**baseline 漂移說明**：5/21 早晨 C1+C2 baseline canary/ 為 201；之後 P1-WATCHDOG-NETOUTAGE R2 (`fbe8b8d5`) report +6 = 207；當前 212 比 207 + 5 = 與 `f3_obs_pre_stopout_wilson` 改動本身**無關**（本 PR 0 新 test in canary/ 主目錄，5 new 全在 canary/healthchecks/tests/ 已計入 88/88）。delta attribution = sibling drift（5/21 P1-WATCHDOG R2 之後 / 之前的 sibling test commit）。本 PR 對 canary/ baseline 貢獻 = 0。

**healthchecks/tests/ 88/88 file 分布**：
- test_62_fill_rate.py: 19 tests（C1+C2 5/21 加 12 stratify tests）
- test_63_fallback_audit.py: 5 tests
- test_64_rate_limit.py: 5 tests
- test_65_reject_sample.py: 6 tests
- **test_66_pre_stopout_rate.py: 16 tests**（C1+C2 11 + F3 +5 Wilson sub-clause tests）
- test_67_pulse_freshness.py: 15 tests
- test_common.py: 22 tests

5 new Wilson tests:
- `test_pass_when_wilson_upper_within_bound`
- `test_warn_when_raw_passes_but_wilson_upper_exceeds`
- `test_fail_via_raw_rate_regardless_of_wilson`
- `test_fail_via_wilson_lower_when_raw_under_fail_upper`
- `test_insufficient_sample_unchanged_under_wilson`

---

## Verify Step 詳結果

### Step 1 — 完整 pytest healthchecks/tests/

```bash
$ python3 -m pytest helper_scripts/canary/healthchecks/tests/ -v --tb=short
# 1st run
============================== 88 passed in 0.04s ==============================
# 2nd run
============================== 88 passed in 0.04s ==============================
# 3rd run (post adversarial restore)
============================== 88 passed in 0.04s ==============================
```

5 new Wilson tests 全 PASS。3 runs identical green = non-flaky。

### Step 2 — Cross-module pytest 不破

```bash
$ python3 -m pytest helper_scripts/canary/ -q --tb=short
# 1st run
212 passed in 31.21s
# 2nd run
212 passed in 31.17s
```

cross-module canary/ (含 test_canary.py + test_engine_watchdog.py + healthchecks/tests/) 212/212 × 2 runs identical green。

```bash
$ python3 -m pytest helper_scripts/db/test_close_maker_audit_healthcheck.py -q --tb=short
8 passed, 14 subtests passed in 0.03s
```

passive_wait `[71] close_maker_zero_spine_lineage` cross-namespace 不擾驗證通過。

### Step 3 — Syntax + import + CLI check

| Check | Result |
|---|---|
| `python3 -c "import helper_scripts.canary.healthchecks"` | exit 0 ✓ |
| `python3 66_close_maker_pre_stopout_rate.py --help` | exit 0 ✓ |
| `python3 66_close_maker_pre_stopout_rate.py --no-wilson --help` | exit 0 ✓ |
| argparse defaults 提取（programmatic） | `--pass-upper=0.10` / `--fail-upper=0.30` / `--min-sample=30` / `--stopout-patterns=None` / `--wilson-upper-pass=0.15` / `--wilson-lower-fail=0.15` ✓ |
| --help text 含 `wilson_lower_fail ≤ 0.15` 字面 | ✓ |
| --help text 含「E2 R2 push back 後從 0.20 調降」rationale | ✓ |

CLI 全 OK。`--wilson-lower-fail` default 0.15 已從 0.20 調降，help text 解釋完整。

### Step 4 — Adversarial regression catcher（核心驗證）

**Probe A**：strip `run()` line 338 default `wilson_lower_fail: float = 0.15` → `wilson_lower_fail: float = 0.20`

```bash
$ python3 -m pytest helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py -v --tb=short
# Result:
FAILED test_pass_when_wilson_upper_within_bound
E   assert 0.2 == 0.15
1 failed, 15 passed in 0.03s
```

`test_pass_when_wilson_upper_within_bound` line 362 assertion `result["thresholds"]["wilson_lower_fail"] == 0.15` 失敗 → 1 RED + 15 PASS。**Test 真實 catch default 變動，非 self-consistent mock**。

**Restore**：byte-identical（`diff /tmp/66_backup.py source = empty`） → 跑 test → 88/88 PASS。

**設計健全度**：strip 1 default value 必 RED + 其他 15 test 不依賴此 default（design isolation）+ restore byte-identical 必 GREEN → **100% adversarial cycle 通過**。

**Probe B (additional)**：`_stopout_rate_verdict()` line 281 default 改 0.20 不會紅 — 因為 `run()` line 417 永遠 explicit pass `wilson_lower_fail=wilson_lower_fail`，line 281 default 是 dead default value（call site 必傳）。這是設計上預期；不影響 Probe A 結論。

**Probe C (additional)**：test 完全不 touch argparse / sys.argv（grep `args.` / `_parse_args` / `argparse` / `sys.argv` 均 0 hit in test_66）— 所以 argparse line 255 default 改變 test 看不見。argparse default 跟 docstring line 88/103 + function default 一致性由 PM 視覺檢查（4 處 inline edit 對齊）保證。NTH-P2 可加 1 個「argparse defaults snapshot」test 把第 4 處納入自動 catch（不擋 commit；E2 R2 + 本 E4 已視覺確認 4 處對齊）。

### Step 5 — 規範驗證

| Check | Result |
|---|---|
| `66_close_maker_pre_stopout_rate.py` LOC | 492 ≤ 800 ✓ |
| `tests/test_66_pre_stopout_rate.py` LOC | 484 ≤ 800 ✓ |
| Emoji scan (regex `\U0001F300-\U0001FAFF` + emoji 範圍) | 0 / 0 ✓ |
| `/home/ncyu` / `/Users/ncyu` / `/Users/[a-zA-Z]+` hardcoded path | 0 hit ✓ |
| 注釋規範（中文 default per feedback_chinese_only_comments 2026-05-05） | spot 抽 line 256-260 全中文 + Wilson/CI 等英文技術名保留 ✓ |
| 新 import dependency | 0（`wilson_ci_95` 同 package `_common` pre-existing 函數，E2 §A1 已 verify） ✓ |

### Step 6 — Mock 真實性 5-spot check

抽 5 個 Wilson sub-clause new test 對照 Mock 安全規則 §5.1/§5.2：

| Test | mock 內容 | 業務邏輯 | OK? |
|---|---|---|---|
| test_pass_when_wilson_upper_within_bound | FakeCursor IO only | wilson_ci_95 真跑 + raw rate 真算 + verdict ladder 真判 | ✓ |
| test_warn_when_raw_passes_but_wilson_upper_exceeds | FakeCursor IO only | wilson_ci_95 真跑（驗 upper > 0.15）+ ladder 真判 WARN | ✓ |
| test_fail_via_raw_rate_regardless_of_wilson | FakeCursor IO only | raw FAIL 純走 ladder 真判 | ✓ |
| test_fail_via_wilson_lower_when_raw_under_fail_upper | FakeCursor IO only | wilson_ci_95 真跑（驗 lower > 0.20）+ ladder Wilson-FAIL 真判 + use_wilson=False reverse case 真跑（同 fixture 兩走 path 比對） | ✓ |
| test_insufficient_sample_unchanged_under_wilson | FakeCursor IO only | min_sample gate 早返 + Wilson 不執行（lower/upper = sentinel 0.0） | ✓ |

**評估**：mock 嚴守 IO 邊界（FakeCursor.execute / fetchall）；Wilson 數學 + verdict ladder 100% 真跑；EXPECTED_* fixture 全部 production-derived（n,k 組合對齊 demo velocity scenario）。

特殊驗證 — `test_fail_via_wilson_lower_when_raw_under_fail_upper` 在同一 fixture 上 use_wilson=True/False 雙跑驗 reverse case（Wilson FAIL vs R1 WARN），這種設計能 catch 「Wilson sub-clause 與 R1 ladder collapse」regression。比標準 mock test 更嚴格。

### Step 7 — `wilson_lower_fail` 4 處對齊驗證

PM inline edit 修 4 處 default：

| Location | 內容 | 0.15 status |
|---|---|---|
| `66_close_maker_pre_stopout_rate.py:88` (docstring) | 「預設門檻 0.10 / 0.30 / Wilson upper 0.15 / Wilson lower 0.15」 | ✓ |
| `66_close_maker_pre_stopout_rate.py:103` (docstring CLI 範例) | `[--wilson-lower-fail 0.15]` | ✓ |
| `66_close_maker_pre_stopout_rate.py:255` (argparse) | `default=0.15` | ✓ |
| `66_close_maker_pre_stopout_rate.py:281` (`_stopout_rate_verdict()` signature) | `wilson_lower_fail: float = 0.15` | ✓ |
| `66_close_maker_pre_stopout_rate.py:338` (`run()` signature) | `wilson_lower_fail: float = 0.15` | ✓ |
| `tests/test_66_pre_stopout_rate.py:362` (assertion) | `result["thresholds"]["wilson_lower_fail"] == 0.15` | ✓ |

**6 處 0.15 全對齊**（PM brief 說 4 處實 6 處，多 2 處是兩個 function default + 1 docstring，視覺一致性更強）。Docstring line 258-259 解釋從 0.20 改下的 rationale 完整。

---

## E4 對 PM brief 數字校正（非 BLOCKER）

PM brief 寫：
- E1 R1 +5 new test → 實測 5 new + 1 改 assertion (`test_pass_when_wilson_upper_within_bound` line 362) = 6 變動
- "default 0.20 → 0.15（4 處）" → 實 PM 主會話 inline 修 6 處（docstring 2 + argparse 1 + function default × 2 + test assertion 1）；brief 寫 4 處是約略表達，視覺角度看 4 處 user-visible（docstring 2 + argparse 1 + test 1），function default × 2 是內部技術一致性。E2 R2 + 本 E4 視覺驗 6 處均對齊。

E4 必跑命令拿 baseline（per regression-testing-protocol §1 規則）— brief 寫死數字僅參考。

---

## 跑兩遍結果

| Run | healthchecks/tests/ | canary/ | passive_wait close_maker |
|---|---|---|---|
| 1st | 88 PASS in 0.04s | 212 PASS in 31.21s | 8 PASS + 14 subtests |
| 2nd | 88 PASS in 0.04s | 212 PASS in 31.17s | (重跑省略；passive_wait 對改動無暴露面，1st run 已足夠) |
| 3rd (post adversarial restore) | 88 PASS in 0.04s | n/a | n/a |

flaky? **N**（multi-run identical green，0.03-0.04s wall time spread within 噪訊範圍）

---

## SLA / 浮點 / 跨語言

**不適用**（healthcheck 是 read-only SQL observability，非 hot path / 非 indicator 計算 / 純 Python 無 Rust counterpart）。

Wilson CI 浮點數計算精度：`_common.wilson_ci_95()` z=1.96 標準 score formula；test 用 `<=` / `>` / `==` 對 round(4) 後的值 assertion（無 1e-4 容差需求 — round 已 normalize 浮點誤差）。E2 §A1 已 verify 公式正確。

---

## E2 R2 nit / defer 狀態

本 PR 已是 E2 R2 §MEDIUM-D1 DEFER 的 follow-up land。E2 R2 R3 review (`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-21--p2_obs_pre_stopout_wilson_subclause_e2_review.md`) APPROVE-CONDITIONAL。

E2 R3 殘留建議 → PM inline 已修：
- `wilson_lower_fail` 0.20 → 0.15（已修 6 處對齊）✓

E4 觀察（NTH-P2，**不擋 commit**）：

| ID | 描述 | 處理方 |
|---|---|---|
| NTH-P2-E4-A | argparse default snapshot test 缺失 — test 不 touch sys.argv，無法 catch argparse line 255 default 漂移（雖 docstring + function default + test assertion 3 路綁定可間接 catch） | Backlog (P2) — 加 `test_argparse_defaults_snapshot` 1 個 test 把所有 user-visible default 鎖死 |

---

## E4 FLAG（不擋 commit）

無新 BLOCKER / 無 mock 過頭 / 無結構性 test 失靈 / 無跨檔 broken 發現。

Adversarial probe A 證實 test_pass_when_wilson_upper_within_bound line 362 是真實 catcher，非 self-consistent assertion。byte-identical restore 後 88/88 GREEN。

---

## 結論

**PASS · commit ready**

- 88/88 pytest（healthchecks/tests/）× 3 runs identical green（含 5 new Wilson tests）
- 212/212 cross-module（canary/）× 2 runs identical green，0 regression
- 8/8 + 14 subtests passive_wait close_maker_audit（cross-namespace 不擾）
- adversarial cycle 100% 通過：strip default 0.15 → 0.20 → 1 RED → byte-identical restore → 88/88 GREEN
- CLI / argparse / `--no-wilson` / `--wilson-lower-fail 0.15` 預設全 OK + help text rationale 完整
- 6 處 default value 0.15 視覺一致（docstring × 2 + argparse + `_stopout_rate_verdict` default + `run()` default + test assertion）
- 規範全綠（2 file size ≤ 800 / 0 emoji / 0 hardcoded path / 中文注釋默認 / 0 新外部 dependency）
- mock 真實性 5-spot 全 OK（Wilson 數學 + ladder 100% 真跑）

PM 建議：
1. commit + push F3 P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE 完成
2. backlog NTH-P2-E4-A：可選未來加 `test_argparse_defaults_snapshot` 把 argparse default 納入自動 catch

E4 REGRESSION DONE: PASS · report path:
`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--f3_obs_pre_stopout_wilson_e4_regression.md`
