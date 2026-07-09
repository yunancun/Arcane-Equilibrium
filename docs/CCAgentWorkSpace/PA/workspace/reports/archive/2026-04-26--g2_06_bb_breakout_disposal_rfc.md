# PA RFC — G2-06 bb_breakout 結構性 Dormancy 處置決策

**日期**：2026-04-26
**作者**：PA
**前置**：G2-05 ✅ FIX-26-DEADLOCK-1 多次 rebuild 驗證後 7d entries=0；P1-11 multi-role audit；MIT 2026-04-26 wave3 data audit；TODO L294
**範圍**：bb_breakout 策略結構性 dormancy 二選一決策（disable 永久 vs 升 5m + recalibrate），不含 bb_reversion / 其他 G2 / G8 項

---

## 1. 背景與根因摘要

bb_breakout 7d demo entries=0（healthcheck `[12]` FAIL）已**不是 deadlock 殘留**：FIX-26-DEADLOCK-1（commits `bcc5401` + `63957ad`，7 regression tests）含 `squeeze_detected_ms` 過期 auto-clear，已於 2026-04-24 02:06 / 22:34 + 2026-04-25 01:30 三次 `--rebuild` 進入 binary，部署嫌疑排除。

**根因**：1m timeframe × 當前 BB bandwidth thresholds 結構性不匹配 — Phase 1 sweep CONFIRMED `squeeze_bw=0.03` 對 1m crypto 100% 觸發（noise floor 之內，無資訊量）、`expansion_bw=0.04` 永不達。FIX 前 deadlock 藏住了「**就算 deadlock 修了信號鏈也根本不會放行**」這層。F3「Donchian 反向」RETRACT 為 measurement bias（leak-free shift(1) 下消失），不能拿來救援；F2「signals ≠ edge」歷史警告下 1m 直接 sweep 救援於統計上是 replication crisis 紅旗。

**結論**：1m bandwidth mis-scale 是**架構級錯誤**而非 calibration miss — BB squeeze 文獻典型 frequency 是 5m+，1m 等於把 squeeze 條件下放到「永遠很窄」。決策必須在「結構級正確解（5m）」與「永久退役（disable）」二選一，**1m 重 sweep 直接禁**（PM/QC 共識）。

---

## 2. 選項 C：永久 disable

### 落地工作（檔案層）
1. **`srv/settings/strategy_params_demo.toml`** + `..._live.toml` + `..._paper.toml`：`[bb_breakout].active = true → false`（demo / live / paper 三環境同改，`feedback_env_config_independence` 三 config 故意分開但本次同方向）
2. **`rust/openclaw_engine/src/strategies/registry.rs:160`**：保留 `bbb.set_active(p.bb_breakout.active);`（無需動 code，TOML flip 即生效）
3. **`helper_scripts/db/passive_wait_healthcheck.py`**：check `[12] bb_breakout_post_deadlock_fix` 改判 — 當 `[bb_breakout].active=false` 時 PASS 跳過（避免持續 FAIL 噪音蓋過真 alarm）
4. **healthcheck 新增**：`[18] check_disabled_strategies_inventory`（純記錄性 INFO，列出 `active=false` 策略 + disable 日期 + 對應 RFC commit hash），確保 disable 不會被未來 audit「忘了還有這策略」誤撿回
5. **CLAUDE.md §三 + TODO L294**：條目從「dormant 處置中」改「disable 永久 — RFC G2-06」+ 入「已完成里程碑索引」表

**不動**：
- Rust strategy registry **不移除** bb_breakout 模組（`set_active(false)` 已是冷啟路徑，bbb instance 不進 on_tick；保留代碼 + 5556 行 tests 為日後重新評估保留物）
- `bb_breakout_threshold_sweep.py` 工具不刪（QC 5/03+ 後做 leak-free re-validation 仍需）
- `BbBreakoutProfile` enum 不刪（保留物）

### 影響面
| 維度 | 量化 |
|---|---|
| Active 策略 | 4 → 3（ma_crossover / grid_trading / bb_reversion） |
| 集中度風險 | ↑（grid 比例提升；P1-10 fee drag 主導 grid，已是 G2-04 議題）|
| Cognitive budget | ↓（少 1 個策略要 calibrate / monitor）|
| Cost 影響 | 0（active=false 不觸發任何成本路徑）|
| 回滾代價 | 極低（TOML flip + rebuild ≤5min）|

### 量化判據（disable 何時是「永久」vs 暫時暫停）
- **本 RFC 的 disable 預設 = 永久暫停**（不是不可逆 retire）
- **重新評估觸發條件**（任一達成由 QC 提案 → PM 決議 → 新 RFC）：
  1. 5m / 15m timeframe 重做 sweep 顯示 forward-return mean ≥ +5 bps fee-net + n ≥ 100 fires/symbol/14d，或
  2. 跨 regime 評估顯示某 regime（如 high-vol）下 1m bb_breakout 有正 edge（regime-conditional 重啟），或
  3. 策略大盤被砍至 ≤2 個 → 集中度風險主導，需要弱信號策略補位
- **永不重啟條件（true retirement）**：上述 3 項 6 個月內均未達 → 從 registry 物理移除，TODO 項刪除

### 工時
- TOML flip + healthcheck 改 + CLAUDE.md/TODO 同步 + commit：**~0.5d**（E1 1 子任務 + E2 review）

---

## 3. 選項 B：升 5m timeframe + recalibrate

### 落地工作（檔案層）

**Rust 層改動（核心，工時主體）**：

| 檔案 | 改動 | 風險 |
|---|---|---|
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_1_2_klines_indicators.rs:62` | 黑天鵝檢測仍鎖 1m，**但** `compute_indicators(sym)` 需新增 5m 路徑專供 bb_breakout 用 | 中 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs:108` | `signal_engine.evaluate(sym, "1m", ...)` 改 per-strategy timeframe（bb_breakout 用 5m，其他保 1m） | 中 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs:299` | `const TIMEFRAME` 拆 per-strategy | 低 |
| `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs` | `on_tick` 內 `BB / ATR / volume_ratio` indicator source 切 5m；`squeeze_expiry_ms` 從 30min → ~150min（5x 換算）；`min_persistence_ms` 同比換算；`cooldown_ms` 重評 | **高** — 行為語義變動，bit-identical 保證消失 |
| `rust/openclaw_engine/src/strategies/registry.rs` | bb_breakout 構造路徑可能需傳入 timeframe 參數 | 低 |
| `rust/openclaw_core/src/klines.rs` | KlineManager 已支援 5m（`DEFAULT_TIMEFRAMES` 含），**無新增工作** | n/a |
| WS 訂閱層 | `multi_interval_topics::DEFAULT_INTERVALS` 已含 Min5，**無新增工作** | n/a |

**Python sweep 工具改造**：

`helper_scripts/research/bb_breakout_threshold_sweep.py` 已有 `--timeframe` flag（line 663-664），但實作對 5m 有 2 個 caveat 要修：
1. **L686 `horizons_bars = forward_mins if args.timeframe == "1m" else forward_mins`** 是 buggy fallback — 5m 下需 `horizons_bars = [m // 5 for m in forward_mins]`（forward 30min → 6 bars，非 30 bars）
2. **`donchian_period=20` 在 5m 下對應 100min lookback**（vs 1m 下 20min），需驗 squeeze persistence 假設仍成立；MIT 建議若不成立加 sweep period（line 145，「BB period 是 separate study」鬆綁為 5m G2-06 範圍內）

**TOML 新增**（如選 B）：
```toml
[bb_breakout]
timeframe = "5m"  # 新欄位，default "1m" 向後相容
squeeze_expiry_ms = 9_000_000  # 30min × 5 = 150min
# squeeze_bw / expansion_bw / volume_threshold 由 G2-06 sweep 決定 + BbBreakoutProfile::Aggressive 起點
```

### 量化判據（5m viable / 不 viable 二判）
**Viable**（→ 部署 + 觀察）：
- demo 連 7d 累積 **fills ≥30**（per healthcheck [12] 改判），且
- leak-free shift(1) 確認 fwd return mean **net of 1bps PostOnly fee × 2 sides** ≥ +5 bps，且
- DSR (K=3 profile, BbBreakoutProfile × top-3 grid) > 0（QC 起點，PA 對齊）

**Not viable**（→ 自動轉 disable，per §6 回滾路徑）：
- 7d 累積 fills < 10 → 5m 也 dormant，timeframe 不是答案
- 7d fills ∈ [10, 30] 但 fee-net mean ≤ 0 → 結構級 alpha-failed
- DSR ≤ 0 → multi-test 後無正 edge

### 工時
| 階段 | 工作 | 工時 |
|---|---|---|
| T1 | sweep 工具 5m 修正 + 1m + 5m 雙跑（25 symbol × 30d） | 1d（含 MIT review） |
| T2 | Rust per-strategy timeframe 接線 | 1d |
| T3 | TOML schema + 預設值 + hot-reload 路徑驗證 | 0.5d |
| T4 | E2 review + E4 regression test（既有 1980 baseline 不能 break） | 1d |
| T5 | demo deploy + 7d 觀察期 | passive 7d |
| **合計** | impl 3.5d 主動 + 7d passive | **~10d wall-clock** |

---

## 4. 二選一決策

### PA 推薦：**選項 C（永久 disable）**

### 理由

**QC 推 C 為主 + B 備援；MIT 推 5m**。PA 角度（架構決策最終責任）切 C，三條：

**1. ROI vs cost ratio 不利於 B**
- B 工時 ~10d wall-clock（Rust 高風險改動 + 雙 sweep + 部署 + 觀察），對應**單一 dormant 策略**
- 同時 Wave 3 主軸是 EDGE-P3（解鎖最早 4/30，per MIT report (c) gate fix 後）+ EDGE-P1b（5/03 滿週 → 5/10 真 bind） + G2-02 ma R:R counterfactual + G8-01/02 測試完善 — **B 的 10d 會擠壓更高 ROI 的 Wave 3 主軸**
- C 工時 0.5d，5/23 樂觀 Live 日期前不擠任何時間預算

**2. 結構性 alpha 假設未經驗證**
- MIT 立場「5m 是結構級正確解」是**機制假設**，不是已驗證 fact — 1m vs 5m 雙 sweep 的 forward-return 對比尚未跑
- F2「signals ≠ edge」對 1m 成立，**對 5m 同樣可能成立**（5m 信號變多但 fee drag + slippage 同時放大）
- 5m 改動觸 step_1_2/step_3/on_tick_helpers + bb_breakout mod 全鏈 — bit-identical 保證消失，1980 baseline 全部要重新驗
- **C 是無 regret 路徑**（5/03 後若仍想驗證 5m，B 永遠可以做；B 失敗則代碼債 + observation budget 已花）

**3. 集中度風險可由 G2-04 主路徑處理**
- 4 → 3 active 策略後集中度上升，但 grid 已是 G2-04 (P1-10 PostOnly 1-2w 驗收) 主議題；ma_crossover 是 G2-02 (R:R counterfactual) 主議題；bb_reversion 仍 active
- 3 active 策略中**結構性問題已知 + 主動處置中** vs 4 active 含 1 個 dormant + 1 個重大重構 = 後者治理面更糟
- 集中度緩解可由 EDGE-P2-flip 後 dynamic position cap + G7-09 fee fix 後 grid edge 恢復處理，**不靠 bb_breakout 補位**

### 風險與緩解

| 風險 | 嚴重性 | 機率 | 緩解 |
|---|---|---|---|
| C：未來發現 5m 真有正 edge → 錯失機會 | 中 | 中（30% per MIT 立場） | §6 重啟條件保留路徑；BbBreakoutProfile + sweep 工具不刪 |
| C：3 active 策略某個崩 → 系統無 fallback | 高 | 低（grid 5月底前還 fee 主導，不至崩） | 等 G2-04 PostOnly 1w 結果決定 grid disable / 不用 bb_breakout 保險 |
| 選 B 但 5m 也 dormant → 10d budget 全費 | 高 | 中（35%） | §6 自動轉 C 條件嚴格，最大損失 ~10d wall-clock |
| 選 B 但 5m 改動 break 既有 strategy（regression） | **極高** | 低（10%，per E4 test） | per-strategy timeframe pattern 嚴格 isolation；bb_breakout 改動以外 0 diff |
| 選 B sweep 結果模糊（sharpe ~0） → 灰色決策又回 RFC | 中 | 高（45%） | 預先設 hard threshold（fee-net mean +5 bps）避免 hand-wavy |

### 量化決策樹

```
Q1：5/23 樂觀 Live 日期前還要塞 10d 工時嗎？
├─ 是 → 進 Q2
└─ 否 → C ✓（節省的 budget 給 EDGE-P3/P1b/Wave 3 主軸）

Q2：1m vs 5m 雙 sweep 跑完後 forward-return 是否顯示 5m 結構級優勢（fee-net ≥ +5 bps + n ≥ 30/sym/14d）？
├─ 是 → B（推進部署 + 7d 觀察）
└─ 否 → C ✓

Q3：4 → 3 active 策略後集中度風險真的觸 P0/P1 風控門檻嗎？
├─ 是 → B（補位）
└─ 否 → C ✓
```

**目前可決狀態**：Q1 答 「否」（Wave 3 主軸擠壓清晰）→ **C ✓**

---

## 5. 落地計劃（決策後 E1 任務拆分）

### E1 子任務清單（4 子任務）

| # | 子任務 | 檔案 isolation | 工時 | 依賴 |
|---|---|---|---|---|
| **G2-06-E1a** | TOML flip 三環境 `[bb_breakout].active=false` | 主樹（3 TOML 檔，互不衝突） | 0.1d | — |
| **G2-06-E1b** | healthcheck `[12]` 改判邏輯（active=false → PASS skip）+ `[18]` disabled inventory check | 主樹（passive_wait_healthcheck.py 單檔） | 0.2d | E1a |
| **G2-06-E1c** | CLAUDE.md §三 + TODO L294 + 已完成里程碑索引同步 | 主樹（meta-doc，per `feedback_git_commit_only_for_metadoc` 用 `git commit --only`） | 0.1d | E1a + E1b |
| **G2-06-E1d** | （deferred）BbBreakoutProfile + sweep 工具保留物 audit 註解 | 主樹（純 comment） | 0.1d | E1a |

**並行性**：E1a 完成後 E1b/E1c/E1d 三軌可並行（per PA profile §35-39 派發 isolation：3 個 sub-agent 操作互不重疊檔，**NOT** 需要 worktree isolation）。

### 強制工作鏈
PA RFC ✅ → **@E1**（4 子任務並行）→ **@E2 代碼審查**（必看：TOML 三環境同方向、healthcheck 改判正確性、CLAUDE.md drift 規則 §三衛生）→ **@E4 回歸測試**（demo restart 後驗 [12] PASS、bb_breakout 不再進 on_tick、其他 3 active 策略不受影響）→ **@QA**（healthcheck full sweep）→ PM Sign-off。

**E2 必查 3 點**：
1. TOML 三環境（demo/live/paper）`active=false` 同方向（避免某環境漏改 → 該環境仍跑 dormant 策略）
2. healthcheck `[12]` 改判邏輯**不能改 PASS 條件以外的部分**（避免「順便」鬆綁其他 dormancy check）
3. CLAUDE.md §三 數值更新含「採集時間 + healthcheck id」（per §三 drift 規則 G6-04）

**E4 回歸 3 點**：
1. `cargo test --release -p openclaw_engine --lib` baseline 1980 不變（C 路徑不動 Rust 碼，必綠）
2. 重啟後 demo engine 5min 內 0 個 bb_breakout 進 on_tick（log 抓 `strategy=bb_breakout` 應只剩 set_active false 啟動 log）
3. healthcheck 17 check 全跑：[12] PASS（disabled skip）、其他 16 check 不受影響

### 派發 isolation 評估（per PM.md §35-39）

| 子任務 | isolation | 理由 |
|---|---|---|
| E1a (TOML × 3) | NOT | 3 檔互不重疊，主樹 |
| E1b (healthcheck 1 檔) | NOT | 單檔，主樹 |
| E1c (meta-doc) | NOT | `git commit --only` 隔絕 index race |
| E1d (comment) | NOT | 純註解 |
| 整體 | **無需 worktree isolation** | 4 軌互不衝突 + 無 destructive 動作 |

---

## 6. 回滾路徑（選 B 用，C 路徑無回滾需求）

**僅當 PM/operator override PA 推薦改選 B 時適用**：

### Trigger：5m 升級後 7d 仍 dormant → 自動轉 C
**條件（任一觸發）**：
1. 5m 部署後第 8 個自然日 healthcheck `[12]` `bb_breakout` fills < 10 → **自動觸發 C**（passive_wait_healthcheck `[19] bb_breakout_5m_viability_check` 新增，cron 6h 跑）
2. 5m 部署後第 8 日 fills ∈ [10, 30] 但 fee-net mean ≤ 0 → **觸發 PM 人工決議**（不自動）
3. 5m 部署後 14d 仍未達 fills ≥ 30 + fee-net mean ≥ +5 bps + DSR > 0 全部條件 → **強制轉 C**

### 自動轉 C 流程
1. healthcheck `[19]` FAIL × 連 2 cycle（12h）→ 報警 operator + Slack/log
2. operator confirm 後 → `[bb_breakout].timeframe = "5m" → "1m"`（恢復 baseline schema）+ `active = false`（disable）
3. 對應 git revert：B impl commits 不回滾（Rust per-strategy timeframe 接線保留為 future investment），僅 TOML flip
4. 走 §5 E1 子任務（同 C 路徑）

### 永不再啟（B 失敗後）
B 失敗 + 自動轉 C 後 6 個月內**禁止再啟 bb_breakout**（無論 1m / 5m），任何重啟提案需 QC 帶新外部證據（regime 證據 / 文獻 backtest）+ PM 簽核新 RFC。

---

## PA 推薦結論

**選項 C（永久 disable）**。

| 維度 | C | B |
|---|---|---|
| 工時 | 0.5d | 10d wall-clock |
| 風險 | 低（無 Rust diff） | 高（5 檔改動 + bit-identical 失） |
| 上行 | 釋出 budget 給 EDGE-P3/P1b/G2-02 | 35% 機率拿回 1 個策略 |
| 下行 | 30% 機率錯失 5m edge | 35% 機率 10d budget 全費 |
| Wave 3 主軸對齊 | ✓ 不擠 | ✗ 擠 |
| 5/23 樂觀 Live | ✓ 不影響 | ⚠ 邊緣 |
| §6 reversibility | ✓（重啟條件清楚） | ✓ + 自動轉 C |

C 是 **dominated strategy** — 上行小但下行也小，B 上行大但下行同樣大，且 B 上行**有條件機率（5m 真有 edge 才實現）**，C 下行**有反悔機制（重啟條件）**。架構決策原則「fail-closed + 可逆優先」推 C。

---

## PM Action Items

1. **PM 拍板**：approve C / 推 B / 改 RFC scope（必須選一）
2. 若 approve C → 派發 §5 4 個 E1 子任務（並行，無 isolation），E2 + E4 強制鏈
3. 若推 B → PA 補 B 詳細 spec（per-strategy timeframe Rust 接線 design + sweep 工具改造 + TOML schema 完整版），重派 sub-agent
4. 更新 TODO L294：`G2-06` 條目從「PA RFC」進到「impl 派發 / disable approved」狀態
5. healthcheck `[12]` 改判生效後，下次 6h cron 報應為 PASS（驗 E1b 落地）
6. CLAUDE.md §三「Wave 3 主體」進度同步（C 完成日期 ~2026-04-27 樂觀，~2026-04-29 中位）
7. 6 個月後（~2026-10-26）QC 重評是否啟動 5m / 15m re-evaluation RFC（per §2 重啟條件）

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md
