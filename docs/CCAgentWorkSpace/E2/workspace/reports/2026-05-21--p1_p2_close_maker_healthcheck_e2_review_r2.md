# E2 R2 Adversarial Review — P1/P2 close_maker healthcheck · 2026-05-21

## R1 → R2 對照

R1 verdict（2026-05-20）= RETURN to E1（2 HIGH MUST-FIX + 2 MEDIUM + 2 LOW）。

E1 R2 報告 83/83 pytest pass，4 issue（A1/A2/E1/F1）已修 + 1 polish（F3）+ 1
deferred（D1）。

R2 改動範圍：5 files
- `helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py`（rename from 71_*，392 行）
- `helper_scripts/canary/healthchecks/62_close_maker_fill_rate.py`（336 行，dead init 刪）
- `helper_scripts/canary/healthchecks/__init__.py`（39 行，補 [66] + 邊界）
- `helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py`（rename + new test，301 行）
- `helper_scripts/canary/healthchecks/tests/conftest.py`（hc71 → hc66 fixture rename）

HEAD = cfb9d243（從 R1 起 0 sibling push）

---

## VERDICT

**APPROVE-CONDITIONAL — 4/4 R1 finding 真實修復 + 0 new regression；2 個 LOW nit 可跟 E4 並進；建議 PM 補 D1 + TODO line 467 同步**

不擋 E4 regression。E1 R2 修品質高，patterns 全部 source-derived（自驗 grep
risk_checks.rs / helpers_close_tags.rs / step_0_fast_track.rs / maker_price.rs
emission），新 test 設計上能 catch R1 regression（adversarial probe 證實 3/12
production stopout 字串會紅報）。

---

## 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 R1 finding 一致 | ✓（5 files 對應 4 finding + 1 polish + 1 defer）|
| 沒有 except:pass | ✓ |
| 日誌 %s 格式 | n/a（healthcheck 不用 logger）|
| 寫入操作 _require_operator_role | n/a（read-only healthcheck）|
| HTTPException 優先 raise | n/a |
| detail=str(e) → "Internal server error" | n/a |
| asyncio blocking Lock | n/a |
| 私有屬性穿透 | ✓ 0 hit |

## OpenClaw 9 條 checklist

| Item | 狀態 |
|---|---|
| 跨平台 `/home/ncyu` / `/Users/[^/]+` | ✓ 0 hit |
| 注釋規範（中文為主）| ✓（新 patterns 描述 + slot 歷史段 + new test docstring 全中文）|
| Rust unsafe / unwrap / panic | n/a（純 Python）|
| 跨語言 IPC schema | ✓（SQL params bind 正確）|
| Migration Guard A/B/C | n/a |
| healthcheck 配對 | ✓（FA OBS-2 已綁 [66] healthcheck）|
| Singleton 登記 | n/a |
| 文件 800 / 2000 | ✓ 66=392, 62=336, init=39, test_66=301 全 ≤ 800 |
| Bybit API 改動 | n/a |
| P0/P1 caller proof | ✓ patterns 對齊 production emission（自驗 grep）|

## §5 Multi-session race check — 5/5 PASS

- 5a `git fetch --prune origin`：0 sibling push since R1 cfb9d243 ✓
- 5b `git status --porcelain`：5 R2 改動檔 + 4 memory + 4 R2 report 全屬本 review scope ✓
- 5c n/a（沒看到 unknown WIP）
- 5d n/a（不 commit；E2 純 review）
- 5e n/a（review 期間 0 sibling push）

---

## R1 Finding 逐條 verify

### HIGH-A1 + HIGH-A2: stopout patterns 大小寫 + DYNAMIC STOP — ✅ FIXED

**E2 獨立 grep verify**（不 trust E1 claim）：

```
rust/openclaw_engine/src/risk_checks.rs:334    "HARD STOP: pnl {:.2}% <= -{:.2}%"
rust/openclaw_engine/src/risk_checks.rs:355    "DYNAMIC STOP: pnl {:.2}% <= -{:.2}% (regime={}, atr={:?})"
rust/openclaw_engine/src/risk_checks.rs:379    "TRAILING STOP: peak {:.2}% - current {:.2}% = ..."
rust/openclaw_engine/src/risk_checks.rs:390    "TIME STOP: held {:.1}h >= limit {:.1}h (regime={})"
```

`66_close_maker_pre_stopout_rate.py:159-170` patterns：

```python
DEFAULT_STOPOUT_EXIT_REASON_PATTERNS = (
    "HARD STOP%",     # :334
    "DYNAMIC STOP%",  # :355 ← R1 漏，R2 補
    "TIME STOP%",     # :390
    "TRAILING STOP%", # :379
    "trailing_stop%", # bb_breakout/mod.rs:910/919
    "fast_track%",    # step_0_fast_track.rs:486/500/603/616
    "halt_session%",  # helpers_close_tags.rs:122-127 R-A5
    "phys_lock_%",    # maker_price.rs:528/529
)
```

1:1 對應自驗：
- ✓ HARD STOP%  ↔ risk_checks.rs:334
- ✓ DYNAMIC STOP% ↔ risk_checks.rs:355 ← R2 補的 A2 fix
- ✓ TIME STOP%  ↔ risk_checks.rs:390
- ✓ TRAILING STOP% ↔ risk_checks.rs:379
- ✓ trailing_stop% ↔ bb_breakout/mod.rs:910/919 (lowercase, strategy-internal)
- ✓ fast_track%  ↔ step_0_fast_track.rs:486 emit `risk_close:fast_track_reduce_half`
- ✓ halt_session% ↔ helpers_close_tags.rs:122-127 R-A5 fallback prefix（強制 strip 後）
- ✓ phys_lock_%  ↔ maker_price.rs:528/529 emit phys_lock_gate4_giveback / _stale_roc_neg

**8/8 pattern 全部對齊 production emission source**。HIGH-A1 + HIGH-A2 真實修。

---

### MEDIUM-E1: production string adversarial test — ✅ FIXED

**E2 file:line verify**：
- `tests/test_66_pre_stopout_rate.py:256-285` 新增 `test_default_patterns_match_real_production_exit_reasons` 存在 ✓
- Helpers `_sql_like_to_fnmatch`（line 73-86）+ `_sql_like_match`（line 89-91）✓
- Fixture `EXPECTED_STOPOUT_EXIT_REASONS`（line 43-58）12 個字串，全有 source line ref 標註 ✓
- Fixture `EXPECTED_NON_STOPOUT_EXIT_REASONS`（line 61-70）8 個 graceful exit 字串 ✓
- 正向 assert（line 271-277）：每個 stopout 至少命中一個 pattern
- 反向 assert（line 280-285）：每個非 stopout 0 命中

**E2 adversarial probe（獨立執行）**：故意把 patterns 改回 R1 lowercase + 漏
DYNAMIC STOP，模擬新 test 跑：

```
[MISS] 'HARD STOP: pnl -25.00% <= -20.00%'                       -> []
[MISS] 'DYNAMIC STOP: pnl -8.50% <= -7.20% (regime=trending,...)' -> []
[MISS] 'TIME STOP: held 24.0h >= limit 24.0h (regime=trending)'  -> []
[OK]   'TRAILING STOP: peak 8.46% - current 6.46% = ...'          -> ['TRAILING STOP%']
[OK]   'trailing_stop'                                            -> ['trailing_stop%']
[OK]   'fast_track_reduce_half'                                   -> ['fast_track%']
... (其餘 9/12 OK)

TOTAL: 3/12 production stopout MISS R1 patterns
=> new test will RED on these 3 cases
=> ADVERSARIAL CATCHER WORKS
```

**設計上能 catch HIGH-A1 + HIGH-A2 regression** — 任何未來 patterns 改錯
（lowercase / 漏字根 / typo）會立即紅。MEDIUM-E1 真實修。

**Source 真實性**：12 個 EXPECTED_STOPOUT 字串全自 grep 出，1:1 對應 emission：
- HARD STOP / DYNAMIC STOP / TIME STOP / TRAILING STOP ← risk_checks.rs format!() literal
- trailing_stop ← bb_breakout/mod.rs:910/919
- fast_track* ← step_0_fast_track.rs:486/603
- halt_session* ← helpers_close_tags.rs:122-127 R-A5 + halt_session_drawdown_3pct test fixture
- phys_lock_gate4_* ← maker_price.rs:528/529

8 個 EXPECTED_NON_STOPOUT 字串：
- ma_reverse_cross ← trading_writer.rs:1290 已驗
- bb_mean_revert / pctb_revert / bw_squeeze ← bb_breakout/mod.rs:952/956 + grid_trading/signal.rs:194
- grid_close_long / grid_close_short ← grid_trading/signal.rs:340/372 ✓
- funding_arb_exit_settled ← funding_arb.rs:412
- "take_profit: price ..." ← lowercase TP 假設（risk_checks.rs:365 emit 是大寫 TAKE PROFIT，假名稱不影響反向 assert）

---

### MEDIUM-F1: [71] → [66] slot rename — ✅ FIXED

**E2 cross-namespace grep verify**：

```
=== F1: [71] 在 canary tree (should be 歷史說明 only) ===
__init__.py:12,22,37 — 都是 doc/comment「passive_wait [70-74] / 從 [71] rename」歷史
66_close_maker_pre_stopout_rate.py:11,13 — 都是 MODULE_NOTE 「Slot 命名歷史」段
tests/test_66_pre_stopout_rate.py:13 — 都是 docstring「F1 → [66] 避碰」
tests/conftest.py:63,64 — fixture comment「R2 從 [71] 改 [66]」歷史
0 個 active slot 編號還是 [71] ✓

=== F1: [66] 在 canary tree ===
__init__.py:5,21,24,26 — 入口列表 + namespace 邊界
66_close_maker_pre_stopout_rate.py:2,7,14,21,24,182 — module docstring + check_id
0 個 active slot 是 [71] ✓

=== F1: hc71 grep ===
0 hit ✓

=== F1: passive_wait [71] 仍 own close_maker_zero_spine_lineage ===
checks_close_maker_audit.py:442 [71] close_maker_zero_spine_lineage ✓（不影響）

=== F1: [71] in tests ===
0 hit（除歷史 comment）✓
```

`66_close_maker_pre_stopout_rate.py:341` `check_id = "[66]"` ✓
`tests/conftest.py:60-67` `hc66` fixture ✓
`tests/test_66_pre_stopout_rate.py:99,115,134,151,168,189,205,234,256,288,294` 9 個 test function 全用 `hc66` parameter ✓
`__init__.py:26-37` 入口列表含 5 個 entry（62/63/64/65/66）+ slot 邊界段（20-24）✓

跨檔 rename 完整同步。F1 真實修。

---

### LOW-F2: __init__.py 入口列表 + slot 邊界段 — ✅ FIXED

**E2 read verify** `__init__.py:19-37`：

```
Slot 編號邊界（2026-05-21 R2 釐清，避 namespace 混淆）：
  - canary/healthchecks/（本 package）：[62][63][64][65][66]
  - passive_wait_healthcheck/：[70][71][72][73][74]
  - 兩 namespace 物理分離但 PM/operator 看 mixed report 可能誤判同一
    slot，故新加 healthcheck 必走未被佔用 slot；[66] 之選定即源於此。

入口 5 個腳本：
  - 62_*  / 63_*  / 64_*  / 65_*  / 66_close_maker_pre_stopout_rate.py
    [66] 條目註明 P1-OBS-PRE-STOPOUT-RATE + 2026-05-21 FA round 1 #5 +
    閾值 0.10 PASS / 0.30 FAIL + R2 從 [71] rename 歷史
```

完整對齊 R1 LOW-F2 要求。

---

### LOW-F3: 62_close_maker_fill_rate.py:225 dead init 清理 — ✅ FIXED

**E2 read verify** `62_close_maker_fill_rate.py:224-232`：

```python
cells: list[dict] = []
# overall_verdict 由下方兩條路徑（not rows / else stratify branch）獨立
# 賦值；舊版 line 225 ``"PASS"`` init 已被 stratify branch line 277 / 282
# 覆蓋兩次，純 dead init（R2 E2 review LOW-F3 清理）。
total_attempts = 0
total_fills = 0

if not rows:
    overall_verdict = VERDICT_INSUFFICIENT_SAMPLE
    ...
```

dead init `overall_verdict = "PASS"` 已刪。Static review：
- Path A (`if not rows`, line 231-243)：本地賦值 `VERDICT_INSUFFICIENT_SAMPLE` ✓
- Path B (`else stratify=none`, line 279-282)：本地賦值 `"PASS"` + severity_max loop ✓
- Path C (`else stratify!=none`, line 283-286)：本地賦值 `_stratified_overall_verdict(...)` ✓

3/3 路徑都本地賦值；刪 init 不影響功能。LOW-F3 真實修。

---

### MEDIUM-D1: Wilson upper bound — ⚠️ DEFERRED（acceptable per R1 spec）

**E2 verify**：E1 R2 report §MEDIUM-D1 (deferred) 確實標 deferred + 在
`66_close_maker_pre_stopout_rate.py:230-235` `_stopout_rate_verdict` docstring
記錄 raw rate vs Wilson 設計理由。

E1 R2 報告末段建議 PM follow-up ticket：
> 若 PM 未來決定加，建議：在 [66] cells loop 內補 Wilson upper > 0.20 / > 0.40
> sub-clause（mirror AC-18 QC-SF-6 機制），跟 raw rate 雙軌取較嚴的 verdict。

**但 TODO §11.3 backlog 尚未明確登記 D1**。是 PM/E1 收尾職責，不擋 E4。

**建議 PM**：在 TODO §11.3 補 `P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE` ticket（low
priority，post-T+24h verification），或在現 P1-OBS-PRE-STOPOUT-RATE 條目註記
「Wilson sub-clause 為 follow-up enhancement」。

---

## E2 不應有 regression check

| 項目 | 結果 |
|---|---|
| R1 APPROVE C2 stratify SQL injection safety | ✓ 仍 PASS（psycopg2 bind 不變）|
| R1 APPROVE 向後兼容（stratify=none 與舊行為 byte-identical）| ✓ 仍 PASS（line 184-200 SQL 字串未動）|
| 文件大小 800/2000 | ✓ 66=392, 62=336, init=39, test_66=301 全 ≤ 800 |
| 83/83 pytest pass | ✓ 自跑驗 `83 passed in 0.03s` |
| 跨平台 `/home/ncyu` / `/Users/[^/]+` | ✓ 0 hit |
| 71_* leftover file | ✓ 0 leftover |
| dead import / dead var | ✓ R2 已清 dead init；其他無 |

---

## E2 額外 adversarial probe（不擋 merge but 報告）

### Probe 1: regime_shift 是否該算 stopout？

bb_breakout/mod.rs:939 emit `regime_shift`，性質介於 stopout 和 graceful 之間
（trend regime 反轉觸發 exit）。E1 patterns **不命中 regime_shift**，等於把它
歸入 graceful 母體。

E2 評估：spec design choice 合理（risk_checks driven path = stopout；strategy
driven exit = graceful），但 docstring `66_close_maker_pre_stopout_rate.py:54-56`
非 stopout list 沒明寫 `regime_shift` 是 strategy-driven graceful。**LOW nit
（不擋 merge）**：建議 E1 在 follow-up 補一條
`- ``regime_shift`` ← bb_breakout regime 反轉退出（strategy-driven graceful）`
到非 stopout 列表 docstring，避免未來 reader 誤解。

### Probe 2: patterns 過寬 false positive

E2 跑 8 個 edge case 字串測 false positive：
- `phys_lock_gate1_low_edge` HIT — 但 risk_checks.rs comment 明說「no longer
  emitted after GATE1-REVERSAL-1 (2026-04-21)」；production 不寫 → 無實際影響
- 其他 6 個都是假設未來字串，不影響 production data

**0 對 production data 的 false positive**。

### Probe 3: VERDICT_PASS literal inconsistency

`62_close_maker_fill_rate.py:280` 用 `"PASS"` literal 而非 `VERDICT_PASS` 常數
（`_common.py:52` `VERDICT_PASS = "PASS"`）。功能 100% 等價（同 string value），
但 style inconsistent。

E2 評估：**LOW nit（不擋 merge）**，R1 未提及，R2 也未處理；可在 E4 / E1 polish
階段順手改。

### Probe 4: TODO line 467 還是 reference 71_*

`TODO.md:467` 仍提 `新 healthcheck 71_close_maker_pre_stopout_rate.py（FA round
1 #5）`，沒同步 rename 到 `66_*`。

E2 評估：**LOW（不擋 merge，PM/PA 後續同步即可）**。PM 在 E4/QA 通過後 commit
+ push 時順手改即可。

---

## Findings 一覽（R2 新增 only）

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| (R1 全部 ✅ FIXED) | — | 詳上 R1 finding 逐條 | — |
| **LOW-G1**（new nit）| `66_close_maker_pre_stopout_rate.py:54-56` 非 stopout list docstring | `regime_shift` 是 strategy-driven graceful exit 但未在 docstring 非 stopout 列表顯式說明，未來 reader 易誤解為 oversight | 補一條：`- regime_shift ← bb_breakout regime 反轉退出（strategy-driven graceful）` |
| **LOW-G2**（new nit）| `62_close_maker_fill_rate.py:280` | `"PASS"` literal 與 `VERDICT_PASS` constant 並用 style inconsistent；100% 等價但易讀性差 | 改為 `overall_verdict = VERDICT_PASS` |
| **LOW-G3**（new docs sync）| `TODO.md:467` | 仍 reference `71_close_maker_pre_stopout_rate.py`，沒同步 rename 到 `66_*` | PM 在 E4/QA 通過後 commit push 時順手改 |
| **DEFER-D1**（per R1 spec）| `66_close_maker_pre_stopout_rate.py:223-245` | Wilson upper bound sub-clause | PM 補 TODO §11.3 follow-up ticket（low priority） |

---

## 對抗反問

1. **「8 條 patterns 全部對齊 production emission？grep 自驗了嗎？」**
   E2 答: ✓ 8/8 對齊。自跑 grep `rust/openclaw_engine/src/risk_checks.rs`（334/355/379/390 全大寫 + 空格 + colon）、
   `helpers_close_tags.rs:122-127` R-A5 halt_session、`step_0_fast_track.rs:486` fast_track、
   `maker_price.rs:528/529` phys_lock、`bb_breakout/mod.rs:910/919` trailing_stop lowercase — 全 confirmed。

2. **「test_default_patterns_match_real_production_exit_reasons 真會 catch R1 regression？」**
   E2 答: ✓。自跑 adversarial probe：故意把 patterns 改回 R1 lowercase + 漏 DYNAMIC STOP，
   12 個 production stopout 字串中 3 個 MISS（HARD STOP / DYNAMIC STOP / TIME STOP）→
   test 會立即紅。catcher 設計正確。

3. **「slot rename [71] → [66] 跨檔同步完全乾淨嗎？」**
   E2 答: ✓。`hc71` 0 hit；`[71]` 在 canary tree 只剩歷史說明 comment（passive_wait `[71]`
   仍 own close_maker_zero_spine_lineage）。conftest hc66 / 9 test function / check_id / __init__
   全同步。

4. **「R2 改動有沒有破壞 R1 已 APPROVE 部分（stratify SQL safety / 向後兼容）？」**
   E2 答: ✓ 0 regression。`62_close_maker_fill_rate.py:184-200` SQL 字串
   stratify=none branch 未動（與 R1 byte-identical）；`_stratified_overall_verdict`
   helper 未動；只刪 line 225 dead init + 補一段 R2 comment。

5. **「Adversarial 還有沒漏的 production stopout 字串？」**
   E2 答: 找到 `regime_shift`（bb_breakout/mod.rs:939）是 strategy-driven exit；E1 patterns
   不命中（歸入 graceful 母體）是 spec design choice 合理，但 docstring 沒明說 → LOW-G1 nit。
   其他 emission paths 全部 8 patterns 覆蓋。

---

## 結論

**APPROVE-CONDITIONAL · PASS to E4**

- R1 4 個 finding（A1/A2/E1/F1）+ 2 LOW（F2/F3）全部真實修復 ✓
- 0 new regression（C2 stratify safety / 向後兼容 / file size 全 PASS）
- 新 test 設計上能 catch R1 regression（adversarial probe 通過 3/12 紅報）
- Patterns 全部 source-derived（自驗 grep 全對齊）
- 3 個 new LOW nit（G1 docstring + G2 literal style + G3 TODO sync）不擋 merge
- 1 個 DEFER-D1（Wilson upper sub-clause）per R1 spec acceptable

建議 PM：
1. 派 E4 regression 跑全管線 pytest + Linux PG empirical（如可行）
2. 通過後 PM commit + push：順手改 TODO.md line 467 `71_` → `66_`（G3）
3. 補 TODO §11.3 P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE follow-up ticket（D1）
4. G1/G2 nit 不阻 — 可入未來 polish 批

E1 R2 修品質高，source-derived + adversarial-tested + 跨檔 rename 完整。

E2 REVIEW DONE: APPROVE-CONDITIONAL · report path:
`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-21--p1_p2_close_maker_healthcheck_e2_review_r2.md`
