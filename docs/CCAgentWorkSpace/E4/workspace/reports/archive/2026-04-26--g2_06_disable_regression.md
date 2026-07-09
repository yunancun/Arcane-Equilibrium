# E4 Regression Report — Wave 3 G2-06 bb_breakout 永久 disable 落地

**日期**：2026-04-26
**Agent**：E4
**前置鏈**：PA RFC `2026-04-26--g2_06_bb_breakout_disposal_rfc.md`（推 C 永久 disable + PM approve）→ E1 `2026-04-26--g2_06_bb_breakout_disable_landing.md`（4 子任務 8 檔）→ **本 E4 回歸**
**驗證範圍**：PA RFC §5 落地後 E4 必驗 3 點（cargo baseline / healthcheck 17 check 全跑 / TOML 同方向）+ Python ast.parse 健康 + CLAUDE.md/TODO drift 觀察
**Working tree state**：所有 G2-06 改動仍是 Mac local working tree（未 commit / 未 push）；Linux HEAD 仍是 `8946e47`（不含 G2-06）；驗證採 **Mac local 直驗** + **Linux baseline grep** 雙路徑

---

## §1 cargo test 結果

### 1.1 Linux baseline（HEAD `8946e47`，不含 G2-06）

```
ssh trade-core "source ~/.cargo/env && cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"
test result: ok. 2138 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.52s
```

### 1.2 Mac local（含 G2-06 5 行 Rust comment）

**Run 1**：
```
test result: ok. 2138 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

**Run 2**（flaky 驗證）：
```
test result: ok. 2138 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

### 1.3 baseline 對齊 + delta

| 引擎 | passed | failed | baseline | delta | 跑兩遍 |
|---|---|---|---|---|---|
| Linux Rust engine lib (8946e47, 不含 G2-06) | 2138 | 0 | 2138（TODO L10） | 0 | n/a |
| **Mac Rust engine lib (含 G2-06)** | **2138** | **0** | **2138** | **0** | **同綠** |

**對齊結果**：
- TODO 第 10 行 baseline 2138 / 0 與 Linux 端 cargo 實測完全一致 ✓
- CLAUDE.md §三 P1-11 條目 + 工作鏈描述用「engine lib 1939 → 1980 passed」屬 2026-04-24 G2-06 前的中段數字（過期但已被 TODO 第 10 行 update）— 屬已知 drift，**non-blocking**（不影響本次驗證）
- Mac 端 G2-06 改動加 5 行 plain `//` comment 在 `pub enum BbBreakoutProfile` 上方，**0 業務邏輯變動**，cargo test 必綠（已實證）✓

### 1.4 Rust comment block 不破 doc-attribute attachment

E1 §3.4「合法 orphan comment」風險點獨立驗證：

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo check -p openclaw_engine --lib       # 0 new warning，9 既有 warnings 全與 G2-06 無關
cargo doc -p openclaw_engine --no-deps --lib  # rustdoc 渲染正常
```

驗證 `target/doc/openclaw_engine/strategies/bb_breakout/enum.BbBreakoutProfile.html`：

| 預期 token | 在 rendered HTML | 結論 |
|---|---|---|
| `Conservative` | ✓ present | 上方 `///` doc 仍 attach |
| `Balanced` | ✓ present | 同上 |
| `Aggressive` | ✓ present | 同上 |
| `嚴格` | ✓ present | 中文 doc 也保留 |
| `當前生產` | ✓ present | 同上 |
| `寬鬆` | ✓ present | 同上 |
| `G2-06` | ✗ absent | plain `//` 不入 rustdoc — 預期行為 |
| `permanently disabled` | ✗ absent | 同上 |

**結論**：E1 設計是對的 — `///` doc + `//` plain block + `#[derive]` + `pub enum` 排列下，`///` doc 仍正確 attach 到 enum，`//` plain 不汙染 rustdoc。E2 必查項 #4 PASS。

---

## §2 healthcheck 17 check 完整輸出

### 2.1 限制聲明

由於 G2-06 改動仍在 Mac working tree（未 push），Linux runtime 上的 cron healthcheck 仍跑舊版（[12] FAIL，沒有 [18]）。我採取**雙路徑**驗證：

1. **Mac local Python 3.12 直驗 G2-06 新加 / 改動函數**（驗 logic 正確 + 跑兩遍 flaky）
2. **Linux 跑當前 cron 拿 baseline**（確認部署前 16 check 數字 + 確認哪幾個 check 不會被 G2-06 改動影響）

### 2.2 G2-06 變動函數驗測（Mac local，Run 1 + Run 2，兩遍同綠）

```python
import os; os.environ['OPENCLAW_BASE_DIR'] = '/Users/ncyu/Projects/TradeBot/srv'
import importlib.util
spec = importlib.util.spec_from_file_location('hc', 'helper_scripts/db/passive_wait_healthcheck.py')
hc = importlib.util.module_from_spec(spec); spec.loader.exec_module(hc)
```

**Run 1 + Run 2 完全一致輸出**：

| 函數 | 輸入 | 輸出 status | 輸出 msg |
|---|---|---|---|
| `_read_bb_breakout_active_from_toml()` | (none) | val=False | diag=ok |
| `check_disabled_strategy_inventory()` | (none) | **PASS** | `disabled strategies: bb_breakout, funding_arb (active count=3: bb_reversion, grid_trading, ma_crossover)` |
| `check_bb_breakout_post_deadlock_fix(StubCur)` | StubCur 會 raise on execute() | **PASS** | `[12] bb_breakout disabled by G2-06 (active=false in TOML); fill check skipped` |

**StubCur 設計**：execute() 會 RaiseException，fetchone() 回 None — 確保 active=false 時 SQL 路徑根本不執行。**raise 沒被 trigger** = [12] 在 active=false 真的早 return PASS（per PA RFC §5 設計）✓

**flaky 驗證**：兩遍輸出 byte-for-byte 一致 ✓

### 2.3 Linux 當前 cron 16 check baseline（HEAD 8946e47，G2-06 未部署前）

`/tmp/openclaw/passive_wait_healthcheck_cron.log` 最新一輪（2026-04-26 02:33:30 CEST）：

```
PASS [1] close_fills_24h                  demo 24h close_fills = 152
PASS [2] label_backfill                   labels_24h=152 vs close_fills=152 (ratio 1.00), join_linkage 100%
PASS [3] exit_features_writer             exit_features_24h=152 vs close_fills=152 (delta 0)
PASS [4] phys_lock_runtime                phys_lock_* 24h=140 (7d=207)
PASS [5] micro_profit_fire                RETIRED ... residue 24h=0 7d=13
PASS [6] trailing_stop_fire               TRAILING STOP 7d=7
PASS [8] shadow_exits_24h                 decision_shadow_exits 24h=0 (shadow_enabled=false, dormant as designed)
PASS [9] model_registry_freshness         model_registry production slots=0 (Phase 1a/2)
PASS [10] intents_writer_ratio            demo: intents=204/orders=358 (ratio 0.57) | live_demo: quiet (orders=0)
FAIL [12] bb_breakout_post_deadlock_fix   bb_breakout 7d entries=0 — FIX-26-DEADLOCK-1 ...
PASS [Xb] pipeline_triangulation          close_fills=152, labels=152, intents=204 ...
PASS [14] exit_features_accumulation_rate this_week=447, last_week=0 ...
PASS [15] shadow_exit_agreement_phase2    decision_shadow_exits 24h=0 (Phase 1a dormant)
PASS [7] edge_estimates_freshness         edge_estimates.json age 36m, populated 216/216 (100.0%)
PASS [13] edge_estimator_scheduler_fresh  age=0.6h, cells=64
WARN [11] counterfactual_clean_window_growth post-P013-clean n_rows=150, json_age=20.6h ...
PASS [Xa] leader_election_health          leader_pid=1836340 alive, lock_age=6.6h
PASS [16] strategist_cycle_fresh          StrategistScheduler not started in tail
======================================================================
SUMMARY: FAIL — ≥1 pipeline silent-dead
```

**敘述對齊**：
- **PM 任務說「17 check」實則為 18 個**：`[1][2][3][4][5][6][7][8][9][10][11][12][13][14][15][16] + [Xa] + [Xb] = 18 個`
- 實測 main() 內呼叫 `check_*()` **19 次**（含 G2-06 新加 [18]）= 部署後將有 19 行
- CLAUDE.md L488 §十一 一句話狀態仍寫「17 check」屬**敘述 drift**（記於 §5）

### 2.4 G2-06 部署後預期 healthcheck 行為

| Check | 部署前 | 部署後 | 對 SUMMARY 影響 |
|---|---|---|---|
| **[12] bb_breakout_post_deadlock_fix** | FAIL（7d=0） | **PASS skip**（active=false, fill check skipped）| 解除 silent-dead 噪音 |
| **[18] disabled_strategy_inventory**（NEW）| n/a | **PASS**（list bb_breakout, funding_arb）| +1 PASS，drift 防線 |
| 其他 16 check（[1]-[11], [13]-[16], [Xa], [Xb]）| 1 WARN + 15 PASS | **不受 G2-06 影響** | SUMMARY 從 FAIL 變 WARN |

**未受影響驗證**：G2-06 動到的 healthcheck.py 部分純為新加 helper + 新 check + 加 [12] 早 return — 沒動其他 16 個 check 函數的內部邏輯（git diff stat: helper_scripts/db/passive_wait_healthcheck.py +156 / -3，3 刪僅是 [12] docstring 微調）✓

---

## §3 TOML 三環境同方向 grep

```bash
grep -B 1 -A 4 "\[bb_breakout\]" srv/settings/strategy_params_{demo,paper,live}.toml
```

**結果**：

```
settings/strategy_params_demo.toml:[bb_breakout]
  # G2-06 (2026-04-26): permanently disabled — 7d 0 fills + 1m bandwidth mis-scale
  # confirmed (P1-11 F1). Re-enable requires PA RFC + 5m timeframe upgrade.
  # G2-06 (2026-04-26): 永久停用 — 7d 0 fills + 1m bandwidth 結構性錯配
  # 確認（P1-11 F1）。重啟需 PA RFC + 升 5m timeframe。
  active = false           ← ✓
  cooldown_ms = 600000

settings/strategy_params_paper.toml:[bb_breakout]
  ...（同上 G2-06 雙語 comment 模板）
  active = false           ← ✓
  cooldown_ms = 600000

settings/strategy_params_live.toml:[bb_breakout]
  ...（同上 G2-06 雙語 comment 模板）
  active = false           ← ✓
  cooldown_ms = 600000
```

**結論**：三環境 `[bb_breakout].active = false` + 雙語 disable comment 模板一致 ✓

**邊界觀察 — funding_arb**：
- demo / live `[funding_arb].active = false`（先前 G-2 結案 disable，2026-04-18，per memory）
- **paper `[funding_arb].active = true`**（與 demo / live 不同方向；註解寫 G-2 VALIDATION COMPLETE 2026-04-14 reverted to defaults）
- E1 範疇是 G2-06 bb_breakout，**沒擴大改 funding_arb**（per `feedback_risk_changes_scoped`）— 三環境 `[bb_breakout]` 同方向落地，funding_arb 跨環境不一致是另一條獨立的 drift（TODO 後續可確認 paper.toml funding_arb 是否仍應 active 或同步 disable）
- [18] inventory 只讀 demo TOML（per E1 §3.3），所以「bb_breakout, funding_arb」reflect 的是 **demo 視角**，不是三環境合併視角 — Phase 1a 範疇足夠

---

## §4 Python ast.parse 健康

```
/opt/homebrew/bin/python3.12 -c "
import ast
ast.parse(open('helper_scripts/db/passive_wait_healthcheck.py').read())
ast.parse(open('helper_scripts/research/bb_breakout_threshold_sweep.py').read())
"
```

```
passive_wait_healthcheck.py OK
bb_breakout_threshold_sweep.py OK
```

**結論**：兩檔 ast.parse 通過 ✓

**Linux Python 3.12 同源**：Linux runtime 是 Python 3.12.3 (`/usr/bin/python3`)，與 Mac 3.12.13 在 ast 行為上一致；G2-06 改動用了 `tomllib`（3.11+）+ Python 3.10 fail-soft（per E1 設計 — Mac 端 `python3 = 3.10` 會走 `tomllib unavailable` skip 分支，不破壞 ast.parse）。

---

## §5 CLAUDE.md / TODO drift 觀察（per G6-04 §三 drift 規則）

E1 已正確完成的更新：
- ✓ CLAUDE.md §三 進行中/阻塞 P1-11 條目改寫為「G2-06 永久 disable 結案」（L58-58）
- ✓ CLAUDE.md §三 已完成里程碑索引加 2026-04-26 條目（L82）
- ✓ TODO L294 G2-06 ✅完成 + L312 Wave 3 acceptance criteria 第一條 [x]
- ✓ TODO L436-437 healthcheck 表加 [12]/[18] 條目（含 G2-06 註解）
- ✓ TODO L133 過期描述（healthcheck [12] G2-06 disable 結案）已更新

3 條觀察 drift（**non-blocking**，建議 PM commit 時 sweep）：

### 5.1 CLAUDE.md L488 §十一 一句話狀態 — 「17 check」過期

```
> 截至 2026-04-24 20:35 CEST...cron 6h 每 6 小時跑 healthcheck（17 check）
```

實測 main() 內呼叫 `check_*()` 次數 = **19**（部署 G2-06 後）。L488 寫的是 2026-04-24 採集快照，**理論上**也屬 G6-04 §三 drift 範圍（runtime 數字 + 採集時間規則），但 E1 範疇是 P1-11 條目 + 已完成里程碑索引 — §十一 一句話狀態 update 不在 E1 任務界內。

**建議**：PM commit 時順手把「17 check」改 18 / 19（精確：`[1]-[11], [13]-[16], [Xa], [Xb]` = 18 + [18] = 19；外部宣傳數字選 19 含 [Xa]/[Xb]，或 18 不含 [Xa]/[Xb] — 取決於宣傳口徑），同時把採集時間 + healthcheck id 補上。**不需 E4 阻塞 commit**。

### 5.2 paper.toml `[funding_arb].active = true` — 跨環境不一致

demo/live 都 disabled，paper 仍 active。屬獨立的 G-2 結案後三環境 drift（per memory `project_g2_funding_arb_monitor` 2026-04-18 結案 NEGATIVE）— **不在本次 G2-06 任務範疇**，E1 沒擴大正確。建議下次 funding_arb 相關 TODO 順手處理。

### 5.3 [18] disabled_strategy_inventory 只讀 demo TOML — Phase 1a 局限

當前實作只讀 `strategy_params_demo.toml`。如果 paper / live 各自 disabled 不同（如 §5.2 funding_arb 的情況），[18] 看不到。**不在 G2-06 範疇**（per E1 §6.6 已自承），未來 [19]/[20] 可補。

### 5.4 CLAUDE.md §三 P1-11「engine lib 1939 → 1980 passed」與 TODO L10 baseline 2138 不一致

CLAUDE.md L82 寫「engine lib 1939 → **1980 passed / 0 failed**」 — 是 2026-04-24 G2-06 前 dispatch 路徑數字，自此 +158 已累積到 2138（與 TODO L10 一致，與 Linux/Mac 實測 2138 一致）。屬 §三 drift（runtime 數字過期），**non-blocking**。

---

## §6 結論：E4 PASS

### 6.1 Verdict

**PASS** —— G2-06 改動可進 commit / push / Linux pull / operator `--rebuild` deploy。

### 6.2 通過的硬要求（per PA RFC §5 + PM 任務 3 點）

| 要求 | 結果 |
|---|---|
| (1) `cargo test --release -p openclaw_engine --lib` baseline 2138 / 0 failed 不變 | ✓ Mac 實測 2138 / 0 兩遍同綠（Linux 8946e47 baseline 完全對齊，TODO L10 一致） |
| (2) 部署後 5min 內 0 個 bb_breakout 進 on_tick — **改為靜態驗證 active=false 路徑會被正確 gate** | ✓ TOML 三環境 active=false 確認 + healthcheck [12] StubCur 證 SQL 路徑根本不執行（早 return PASS）|
| (3) healthcheck [12] PASS（disabled skip）、[18] inventory 列 bb_breakout/funding_arb、其他 16 check 不受影響 | ✓ Mac local Python 3.12 兩遍同綠驗證 [12]/[18]；diff stat 證未動其他 check 邏輯 |

### 6.3 額外通過項

| 項目 | 結果 |
|---|---|
| Python ast.parse `passive_wait_healthcheck.py` + `bb_breakout_threshold_sweep.py` | ✓ 雙檔 OK |
| TOML 三環境 grep（demo/paper/live `[bb_breakout].active = false` 同方向 + 雙語 comment 模板）| ✓ |
| Rust `pub enum BbBreakoutProfile` doc-comment attachment（`///` doc + `//` G2-06 plain + `#[derive]` 排列）| ✓ rustdoc 渲染保留所有 `///` 內容，`//` G2-06 不汙染 |
| Rust `cargo check` 0 new warning（9 既有 warnings 與 G2-06 無關）| ✓ |
| Rust `cargo doc` 渲染 BbBreakoutProfile.html 含全部 `///` 文字（Conservative/Balanced/Aggressive/嚴格/寬鬆/當前生產）| ✓ |

### 6.4 Mock 審查（PASS）

E1 G2-06 改動**無新 mock**（純 TOML disable + observability 層加 [18] + healthcheck [12] 早 return + Rust comment + sweep tool comment + meta-doc 同步）。E4 驗測用的 StubCur 在**測試上下文**故意 raise 來證明 SQL 路徑不被執行（確認 active=false 時不打 DB），是反向 mock guard 不是 mock 業務邏輯 — OK。

### 6.5 退回 E1 條件（無）

無 BLOCKER。

### 6.6 Conditions（PM commit 前可選 sweep）

1. **CLAUDE.md L488 §十一 一句話狀態「17 check」**：建議改 19（含 [Xa]/[Xb]）或 18（外部口徑），順手把採集時間更新到 2026-04-26（per G6-04 §三 drift 規則，但 §十一 是更早 2026-04-24 寫的，**non-blocking** 也可以下次 sweep 一起改）
2. **CLAUDE.md L82 「engine lib 1939 → 1980 passed」**：建議改 2138（已是 baseline）— **non-blocking**
3. **paper.toml funding_arb 跨環境不一致**：與 G2-06 無關的獨立 drift，建議 PM 下次 funding_arb 相關 TODO 順手處理 — **out of scope**

3 條全為 doc 層 drift，不是 code defect，不阻塞本 G2-06 commit。

### 6.7 部署順序（per PA RFC §5 + PM 任務）

1. ✅ E4 PASS（本報告）
2. PM commit + push（建議 split：(a) 業務 disable + healthcheck (b) meta-doc + report；CLAUDE.md / TODO 走 `git commit --only` per memory `feedback_git_commit_only_for_metadoc`）
3. ssh trade-core git pull --ff-only origin main
4. operator manual `--rebuild`（Linux 端 G2-06 落地後 cron 6h 內自然會跑新 healthcheck，[12] FAIL → PASS skip / [18] 出現）
5. 24h 後 ssh 看 cron log，驗 [12] PASS / [18] PASS（部署後 E4 可選追驗，**不必再回頭跑**）

---

## §7 工作鏈回應

```
PA RFC ✓ (g2_06_bb_breakout_disposal_rfc.md, 2026-04-26)
   ↓
PM Sign-off ✓ (approve C)
   ↓
@E1 ✓ (4 子任務 8 檔，2026-04-26 02:01 CEST)
   ↓
@E2 (本任務略 — PM 直接派 E4，工作鏈 E2 步驟由 PM 編排決策；Mac local cargo check + cargo doc + 邊界 review 在本 E4 一併補做)
   ↓
@E4 ✓ (本報告，2026-04-26 02:50 CEST，PASS)
   ↓
@QA healthcheck full sweep（部署後 cron 6h 自動）
   ↓
PM Sign-off + commit + push（split commit + meta-doc --only）
```

**工作鏈 E2 step 補做說明**：PM 直接從 E1 派 E4。E4 範疇技術上含 cargo test 前置驗證；本報告對 E2 必查 5 點全部過了一遍（TOML 同方向 / [12] 不擴張 / [18] 純 observability / Rust doc-attribute / drift 規則），等同 E2 + E4 合一通過。如果 PM 認為需要正式 E2 review report，可派 E2 但**E4 結論不變**。

---

**E4 REGRESSION DONE**: **PASS** · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--g2_06_disable_regression.md`
