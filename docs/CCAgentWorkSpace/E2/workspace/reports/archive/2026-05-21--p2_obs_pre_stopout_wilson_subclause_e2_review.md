# E2 PR Adversarial Review — P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE

- Date: 2026-05-21
- Branch/HEAD: HEAD = `4acf2c01`（origin/main 同步，無 sibling push）
- Spec source: E2 R2 review C 批 MEDIUM-D1 deferred follow-up
- E1 report: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p2_obs_pre_stopout_wilson_subclause.md`
- 改動範圍：[66] healthcheck + 對應 test
- 88/88 pytest pass（83+5）

## §5 Multi-Session Race Check

| 條 | 結果 | 備註 |
|---|---|---|
| 5a fetch + sibling window | ✅ | origin/main = HEAD = `4acf2c01`；無 sibling push 衝突 |
| 5b status clean（本 review scope） | ⚠️ | 本 review 涉及 2 檔（66 + test_66）pristine staged；working tree 另有非 scope 改動（`2026-05-20--execution-plan-v5.[2-7].md` 6 個 staged 檔 + `docs/CCAgentWorkSpace/E5/memory.md` + `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md` + `docs/CCAgentWorkSpace/E1/memory.md` modified）— **非本 review session 改動，按 §5c 不 revert，留 PM 處理** |
| 5c unknown WIP 禁 revert | ✅ | 未動非 scope 檔；未 stash drop |
| 5d sign-off report path clean | ✅ | 本 report write 後將自動 untracked，僅本 commit 對應 |
| 5e PR review 中 sibling push | ✅ | review 期間無 sibling push（fetch 確認 origin/main 仍 4acf2c01） |

## 改動範圍

| 檔 | 行數 |
|---|---|
| `66_close_maker_pre_stopout_rate.py` | 392 → 490（+98；E1 self-report +5-10，實偏多但是 docstring 大改可接受） |
| `tests/test_66_pre_stopout_rate.py` | 301 → 484（+183；E1 self-report +50；含 +5 test case + 大塊註釋） |

兩檔均 < 800 行警告線，遠 < 2000 行硬上限。

## 8 條 E2 Reviewer Checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ | 只動 66 + test_66 + E1 report，無範圍漂移 |
| 沒有 except:pass 或靜默吞異常 | ✅ | 0 違規 |
| 日誌使用 %s 格式（非 f-string） | ✅ | 改動內無新 log statement |
| 新 API 端點有 _require_operator_role() | N/A | 非 API 改動 |
| except HTTPException: raise 在 except Exception 之前 | N/A | 無 exception 改動 |
| detail=str(e) 已改為 "Internal server error" | N/A | 無 API 改動 |
| asyncio 路由中沒有 blocking threading.Lock | N/A | 純同步 healthcheck |
| 沒有私有屬性穿透（._xxx） | ✅ | wilson_ci_95 走 _common 公開 API |

## OpenClaw 特殊 9 條 §3 Checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 3.1 跨平台合規（無 `/home/ncyu` / `/Users/[^/]+`） | ✅ | 0 hit |
| 3.2 注釋規範（中文 default + 英文技術名保留 + MODULE_NOTE） | ✅ | 全中文 + 英文技術名（Wilson / pass_upper / LIKE 等）保留 + MODULE_NOTE 完整 |
| 3.3 Rust 代碼 unsafe/unwrap/panic | N/A | Python only |
| 3.4 跨語言 IPC schema | N/A | 純 PG SQL，無跨語言 IPC |
| 3.5 Migration Guard A/B/C | N/A | 無 SQL migration |
| 3.6 healthcheck 配對（被動等待） | N/A | 非 passive_wait TODO；本 [66] 為 standalone manual healthcheck（QA T+24h verify） |
| 3.7 Singleton / monkey-patch | ✅ | 無新 singleton；wilson_ci_95 純函數 |
| 3.8 文件大小 800/2000 | ✅ | 490 / 484 行 |
| 3.9 Bybit API | N/A | 無 Bybit endpoint 變動 |
| 3.10 P0/P1 leak caller proof | N/A | P2 obs follow-up，非 leak finding |
| 3.11 ML training pipeline 非輸入 | ✅ | close_maker_* 仍只用於 healthcheck observability，未進 LinUCB/Scorer/Quantile/MLDE/DL3；本 patch 沒擴大欄位範圍 |

## A. Wilson 公式正確性

### A1. `_common.wilson_ci_95()` 標準 score Wilson CI

`_common.py:121-146` 實作標準 Wilson score 95% CI（z=1.96）：
```python
denom = 1.0 + z²/n
center = p_hat + z²/(2n)
spread = z*sqrt((p(1-p) + z²/(4n))/n)
lower = (center - spread) / denom
upper = (center + spread) / denom
```
domain [0,1] 保證。✓ 公式正確。

### A2. [66] caller 用 `wilson_ci_95(stopouts, attempts)` 是否正確？

正確。Wilson 是「事件比例」CI，**方向 agnostic** — successes 放哪個事件 = 量哪個比例。[66] 量 stopout rate，所以 successes=stopouts 正確。

### A3. 與 [62] AC-18 對稱性 — Mirror 真實對稱？

**結論：對稱反轉邏輯正確**。

| 方向 | [62] success-direction（rate 越高越好） | [66] failure-direction（rate 越低越好） |
|---|---|---|
| PASS 看哪界 | Wilson **lower** ≥ pass_lower | Wilson **upper** ≤ wilson_upper_pass |
| FAIL 看哪界 | Wilson **upper** < warn_lower | Wilson **lower** > wilson_lower_fail |

Wilson 對稱反轉的 inferential 邏輯：
- success-direction：「即使有不確定性，下界仍夠高」= 確證 PASS；「即使有不確定性，上界仍太低」= 確證 FAIL
- failure-direction（鏡像）：「即使有不確定性，上界仍夠低」= 確證 PASS；「即使有不確定性，下界仍太高」= 確證 FAIL

E1 對稱反轉正確 ✓。

### A4. 對稱性次要 deviation（不擋 review）

[62] PASS **純看 Wilson lower**（不要求 raw）；
[66] PASS **要 raw ≤ pass_upper AND Wilson upper ≤ wilson_upper_pass**（雙條件 AND）。

E1 在 docstring 解釋「raw 0.10/0.30 為 rate-level 直觀門檻，operator 報告易理解；Wilson 為 secondary conservativeness layer」。這是 sub-optimal sequence（純 Wilson 統計上更 rigorous），但 E1 自己有 disclose，且 operator readability 是合理 trade-off。**不算錯，不擋**。

## B. 預設 threshold trade-off — **核心對抗發現**

### B1. 數值驗證（E1 sanity 表格全對）

| (s, n) | raw | Wilson lower | Wilson upper | 期望 | 實算 verdict |
|---|---|---|---|---|---|
| (10, 200) | 0.0500 | 0.0274 | 0.0896 | PASS | PASS ✓ |
| (4, 50) | 0.0800 | 0.0315 | 0.1884 | WARN | WARN ✓ |
| (40, 100) | 0.4000 | 0.3094 | 0.4980 | FAIL（via raw） | FAIL ✓ |
| (250, 1000) | 0.2500 | 0.2242 | 0.2778 | FAIL（via Wilson lower） | FAIL ✓ |
| (10, 29) | 0.3448 | – | – | INSUFFICIENT | INSUFFICIENT ✓ |

### B2. **Production demo sample velocity 實測（key finding）**

Production `trading.fills WHERE close_maker_attempt=TRUE` 過去 7d 統計（trade-core PG empirical query）：

```
demo|32
```

對應**全部 close_maker_attempt 歷史**（2026-05-18 enable 至 2026-05-21）= 32 fills / 3 days = **≈ 10 / day = 70 / week**。

### B3. **0.20 wilson_lower_fail 在實際 production 下的 fire 條件**

| n（real velocity） | raw=0.25 Wilson lower | > 0.20? |
|---|---|---|
| n=70（1 week，default window） | 0.1575 | **❌ 不 fire** |
| n=140（2 weeks，需擴 window） | 0.1856 | **❌ 不 fire** |
| n=280（4 weeks） | 0.2029 | ✅ fire（但 default 7d window 不會累積到） |

**結論**：wilson_lower_fail = 0.20 在預設 7d window + production demo velocity（~70/week）+ raw=0.25（仍未 raw FAIL）下**永遠不會 fire** — 等同 dead gate。

### B4. 替代 threshold 計算

| threshold | n=70 raw=0.25 Wilson lower=0.1575 fire? | n=100 raw=0.25 Wilson lower=0.1755 fire? |
|---|---|---|
| **0.20**（當前 default） | ❌ | ❌（需 n≥300） |
| 0.17 | ❌ | ✅ |
| 0.15 | ✅ | ✅ |

E1 R1 push back 認知**完全正確**。

### B5. 對 PM 的建議

**強烈建議**：把 `wilson_lower_fail` default 從 0.20 → 0.15。

理由：
1. 在預設 7d window + 真實 production demo velocity (n~70/week) 下，0.15 才會在 raw=0.25 即 fire；0.17 / 0.20 都需 n≥100 / n≥300 才 fire，在 7d window 永遠達不到。
2. 0.20 是 cron schedule + n~1000 / month 的 mature production assumption；對 demo 階段 close_maker_attempt 新 enable（3 days history）不合理。
3. 0.15 不會與其他守線衝突：raw=0.10/0.30 + Wilson upper 0.15 + Wilson lower 0.15 形成「上下對稱 conservativeness layer」更乾淨。

**但這是 threshold tuning judgment，不擋 E4** — E1 sticking 0.20 是按 prompt 要求（prompt 指定 0.20），所以這是 PM 層 decision。E2 立場：留 follow-up sub-clause，建議 PM 決議調 0.15-0.17 再 deploy。

## C. 向後兼容

### C1. `--no-wilson` opt-out 真退回 R1 ladder

`_stopout_rate_verdict(use_wilson=False)` 走 raw-rate-only ladder：
```python
if rate <= pass_upper: return PASS
if rate > fail_upper: return FAIL
return WARN
```
但即使 use_wilson=False，wilson_lower / wilson_upper 仍計算並回傳 cell payload（observer 可看，但不參與 verdict）。`test_fail_via_wilson_lower_when_raw_under_fail_upper` 反向 case 驗（250, 1000）下 `use_wilson=True` → FAIL，`use_wilson=False` → WARN。✓ 行為正確。

### C2. **R2 default behavior change 對既有 caller 的影響（**潛在 borderline finding**）**

R1 → R2 default 行為改變不只是新增 PASS→WARN，**還有 borderline WARN→FAIL**：

| Case (real production) | R1 verdict | R2 default verdict |
|---|---|---|
| raw=0.10 n=100 upper=0.1744 | PASS | WARN（upper > 0.15） |
| raw=0.10 n=200 upper=0.1494 | PASS | PASS（保持） |
| raw=0.30 n=100 lower=0.2189 | WARN（rate NOT > 0.30） | **FAIL**（lower > 0.20） |
| raw=0.30 n=50 lower=0.1910 | WARN | WARN（保持） |

E1 在 report C 段宣稱「既有 4 個 R1 test (n=100) fixture 跑 default 仍綠」是因為 fixture (5,100) upper=0.1118 / (20,100) raw=0.20 / (50,100) raw=0.50 都剛好不踩 R2 邊界。**但真實 production data 在 n>100 + raw 接近 0.10 or 0.30 boundary 會更嚴格**。

**目前無 downstream consumer / cron 自動 fire**（[66] 是 manual standalone QA T+24h verify），所以沒有 caller 會被破。E2 認可這條 holds。但 PM 應知道 R2 default 更嚴格、不對稱影響。

### C3. JSON output schema 改動

R1 cells payload：`{engine_mode, n_attempts, n_stopouts, n_clean_exits, stopout_rate, verdict}`

R2 cells payload：原 6 key + `wilson_lower` + `wilson_upper`。

R2 `result` top-level 新增：`use_wilson_subclause`、`thresholds.wilson_upper_pass`、`thresholds.wilson_lower_fail`。

對 JSON parser 而言**只擴展不刪除**，向後相容。沒有外部 consumer 依賴具體 cell key set，所以**不破 schema**。✓

## D. 5 新 test 真實性審查

| Test | 覆蓋 path | mock 程度 | 真實性 |
|---|---|---|---|
| `test_pass_when_wilson_upper_within_bound` | PASS path (raw≤0.10 AND upper≤0.15) | fake cursor 餵 (10,200) | ✓ 真實覆蓋 R2 PASS gate；額外驗 result thresholds 暴露 |
| `test_warn_when_raw_passes_but_wilson_upper_exceeds` | WARN-via-Wilson-upper（R2 唯一新 verdict path 之一） | fake cursor 餵 (4,50) | ✓ 真實覆蓋 R1→R2 PASS→WARN 降級 |
| `test_fail_via_raw_rate_regardless_of_wilson` | FAIL-via-raw（R1 行為保留） | fake cursor 餵 (40,100) | ✓ 真實覆蓋 raw 短路 |
| `test_fail_via_wilson_lower_when_raw_under_fail_upper` | FAIL-via-Wilson-lower（R2 核心新增） + **反向 --no-wilson 對照** | fake cursor 餵 (250,1000) | ✓ 含 use_wilson=False vs True 對照 — 真切回 R1 ladder（WARN） |
| `test_insufficient_sample_unchanged_under_wilson` | INSUFFICIENT_SAMPLE 不被 Wilson 干擾 + sentinel(0,0) | fake cursor 餵 (15,29) | ✓ 驗 sentinel 行為 |

**Boundary case coverage gap**：raw=0.10 exact 邊界（n≥200 PASS，n<200 WARN）/ raw=0.30 exact 邊界（n=50 WARN，n≥100 FAIL）未直接覆蓋。但這是 trade-off — 5 case prompt 上限，加邊界會超範圍。**接受**。

對 mock 過頭審查：5 test 都用 `fake_cursor_factory` 走完整 `run()` flow（從 SQL row → verdict → result dict），非 unit-mock `_stopout_rate_verdict()` 直跑。所以 SQL parse + ladder + payload assembly 都真實執行。✓ 不是 mock 過頭。

## E. 對抗反問結果

| Q | A | 評估 |
|---|---|---|
| 「Wilson 公式 z=1.96 嗎？」 | `_common.py:42` `WILSON_Z_95: float = 1.96` ✓ | 正確 |
| 「[66] successes=stopouts 對嗎，不是 fills？」 | `_stopout_rate_verdict(stopouts, attempts, ...)` 然後 `wilson_ci_95(stopouts, total)` ✓ | 正確 |
| 「對稱反轉 PASS=upper / FAIL=lower 對嗎？」 | E1 邏輯 mirror [62] ✓ | 正確 |
| 「測試覆蓋 raw=0.10 / raw=0.30 邊界嗎？」 | 沒覆蓋 exact boundary，但 5 case prompt 上限 | 接受 |
| 「--no-wilson 真退 R1？」 | test_fail_via_wilson_lower 反向驗 ✓ | 真退 |
| 「default 0.20 在 production demo velocity 下 fire 嗎？」 | n=70 (real 7d) raw=0.25 lower=0.1575 不 fire；需 n≥300 才 fire | **❌ 等同 dead gate，建議調 0.15** |
| 「R2 default behavior change 對 caller 破壞嗎？」 | 沒 downstream cron / consumer，[66] manual standalone | 不破，但更嚴格 |
| 「test 沒 mock 過頭嗎？」 | 跑完整 run() flow，非 unit-mock verdict | 真實 |

## Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **CRITICAL** | – | 無 | – |
| **HIGH** | – | 無 | – |
| **MEDIUM** | `66_close_maker_pre_stopout_rate.py:236` (`wilson_lower_fail: float = 0.20`) | **Dead-gate 風險**：production demo velocity (n~70/week) + 7d default window 下，0.20 永遠不會 fire；需 n≥300 raw=0.25。建議 PM 決議調 0.15。 | 改 default `wilson_lower_fail=0.15`；OR 留 0.20 但補 raw≥0.25 AND n≥200 中段 conservatism；OR PM 明確 accept 「dead gate by design until production velocity 增」 |
| **LOW** | `66_close_maker_pre_stopout_rate.py` LOC 估計 | E1 self-report +5-10 行，實際 +98 行（含 docstring 大改） | 不擋；E1 report 可後補一致性說明 |

## 結論

**APPROVE-CONDITIONAL → 可進 E4**

理由：
- Wilson 公式正確（z=1.96 標準 score CI）
- 對稱反轉正確（mirror [62] AC-18：[62] PASS=lower/FAIL=upper；[66] PASS=upper/FAIL=lower）
- 5 test 真實覆蓋（不 mock 過頭）
- `--no-wilson` opt-out 真退 R1 ladder（含反向對照）
- 0 cross-platform / 0 secret-leak / 0 except-pass 違規
- 注釋全中文 + MODULE_NOTE 完整
- 文件 490/484 行（< 800 警告線）
- 88/88 pytest pass

**threshold 0.20 vs 0.15-0.17 trade-off 結論建議 PM**：
- E1 push back 屬實（**production demo n~70/week 實測**確認 0.20 7d window 下 dead gate）
- 強烈建議 default 改 0.15（n=70 raw=0.25 即 fire；對稱漂亮配 raw upper 0.15）
- 0.17 中庸但仍要 n=100 才 fire，不如 0.15
- 但 0.20 sticking with prompt 不擋 E4 — 由 PM 判 deploy 前是否調

## 退回 E1 修復清單

無 — E1 IMPL 通過 E2 對抗審查，可進 E4。

## PM Decision Point

**threshold 0.15 vs 0.17 vs 0.20 trade-off**：請 PM 在進 E4 前明確：
- (a) accept 0.20 sticking with prompt（document 為 dead gate by design，待 demo velocity 增）
- (b) E1 改 0.15（推薦）
- (c) E1 補 raw ≥ 0.25 AND n ≥ 200 中段 conservatism（複雜但靈活）

E2 review 立場：(b) > (c) > (a)。

## 檔案絕對路徑

- 改動 1：`/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py`
- 改動 2：`/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py`
- E1 report：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-21--p2_obs_pre_stopout_wilson_subclause.md`
- 本 E2 report：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-21--p2_obs_pre_stopout_wilson_subclause_e2_review.md`

E2 REVIEW DONE: **APPROVE-CONDITIONAL** · report path: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-21--p2_obs_pre_stopout_wilson_subclause_e2_review.md`
