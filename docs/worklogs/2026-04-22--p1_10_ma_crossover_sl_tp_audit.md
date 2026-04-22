---
title: P1-10 下一步 (2) ma_crossover SL/TP 比率 audit
date: 2026-04-22
status: audit complete — hypothesis identified, TOML change deferred to counterfactual replay
related: TODO §P1-10 · `docs/worklogs/2026-04-22--counterfactual_replay_audit_spec.md`
---

# P1-10 ma_crossover SL/TP 比率 audit（ATR mult / R:R gate）

## 背景 / Background

2026-04-20 R1 驗收：demo ma_crossover 24h 37 exits · win rate **64% → 37.8% 崩** · net −$6.39 · asym 2.54× → 0.88 翻轉（虧損側變小，問題從「不對稱」轉為「勝率」）。P0-3 Phase 5 edge 重評阻塞之一，另一是 grid fee drag（EDGE-P2-3 PostOnly 2026-04-21 部署處理中）。

## 審計範圍 / Scope

`rust/openclaw_engine/src/strategies/ma_crossover.rs` 1835 行 +
`rust/openclaw_engine/src/risk_checks.rs::check_position_on_tick` +
三環境 `settings/risk_control_rules/risk_config_{demo,paper,live}.toml`。

## 結構發現 / Findings

### 1. ma_crossover 無策略層 SL/TP

策略層**僅**設 entry/exit 信號（KAMA 交叉 + ADX ≥ 20 + confluence + higher-TF alignment + ER-scaled 反向交叉 persistence 窗口）。**無 SL/TP 欄位、無 ATR multiplier、無 min_risk_reward_ratio gate**。

Entry 後的倉位由 Rust `risk_checks.rs::check_position_on_tick` 統一管 SL/TP：
- `stop_loss_max_pct` HARD STOP（絕對硬頂）
- `compute_dynamic_stop_pct(base=max×base_ratio, ATR×atr_stop_mult, cap=max×cap_ratio)` DYNAMIC STOP
- `take_profit_enforced=true` 才強制 TP（**三環境全設 false**）→ 實質無硬 TP
- `trailing_enabled` + `trailing_activation_pct` + `trailing_distance_pct` TRAILING STOP

⚠️ 所有策略（ma/grid/bb/bb_reversion/funding_arb）共用此 SL/TP 邏輯，**非 per-strategy**。

### 2. 三環境 risk_config 對照

| 參數 | demo | paper | live | 說明 |
|---|---:|---:|---:|---|
| `stop_loss_max_pct` | **25.0** | 50.0 | 15.0 | HARD STOP 硬頂 |
| `take_profit_max_pct` | 25.0 | 30.0 | 20.0 | TP 硬頂（但 enforced=false 所以不啟） |
| `take_profit_enforced` | false | false | false | 三環境全關 → 無硬 TP |
| `trailing_activation_pct` | **0.8** | 0.5 | 0.5 | peak 達此值後 trailing 啟動 |
| `trailing_distance_pct` | **3.5** | 2.0 | 2.0 | peak − current ≥ 此值即觸發 |
| `base_ratio` (dyn stop base) | 0.4 | 0.30 | 0.5 | base = max×ratio（demo=10%） |
| `cap_ratio` (dyn stop cap) | 0.85 | 0.95 | 0.75 | cap = max×ratio（demo=21.25%） |
| `trailing_min_rr` | 0.3 | 0.2 | 0.8 | 鎖定利潤底線 = dyn_stop × 此值 |
| `atr_stop_mult` | 2.0 | 2.5 | 1.5 | ATR 乘數 |

### 3. demo 勝率崩潰結構性假設

**核心假設**：**demo `trailing_distance_pct=3.5` 相對 ma_crossover 典型 move size 過寬**。

推導：
- 典型 symbol ATR ~1-1.5%（1m timeframe）
- 1-ATR move = 1-1.5% pnl
- demo trailing 活化門檻 +0.8%（早於 paper/live 的 0.5% 反向）
- 一旦活化，給回 3.5% 才觸發 → peak +1% → 必須跌到 **−2.5% 才 trailing stop**（peak − distance = 1 − 3.5 = −2.5）
- 結果：活化後的倉位往往從「名義 peak 正利潤」反轉成「確認負 pnl 才出場」= **winner 變 loser**

**比較 live**（activation 0.5 / distance 2.0）：
- 活化更早（peak +0.5%）
- 給回 2.0% → peak +1% 跌到 −1% 即出場（仍負但浅）
- live asym 僅 1.21×（vs demo 2.54× before R1、0.88 after R1 翻轉）+ win rate 67%

### 4. ma_crossover 反向交叉出場（獨立路徑）

- 反向交叉 + ER-scaled persistence 窗口（clean trend ER→1 → 窗口 ≈ 0 瞬間出；choppy ER→0.5 → 等待確認）
- **與 risk_checks SL/TP 並行**，不互斥
- 若反向交叉 persistence 信號慢於 trailing stop → trailing 先觸發、記為 loss；若反向交叉先觸發 → 記為 `strategy_close:ma_reverse_cross`
- 實測數據未分家 2026-04-20 R1 37 exits 中哪些是 strategy_close vs stop_trigger:trailing — 需 counterfactual replay 分解

### 5. 無 R:R gate（entry-time）

entry 決策純信號機械，**沒有**「預估 SL 距離 vs TP 距離」的驗證。任何信號過 confluence + regime + higher-TF 閘就入場，不管後續 R:R 劣勢。→ 低質量交叉被全量入場拉低勝率。

### 6. E5-P2-4b 大文件狀態

- `ma_crossover.rs` **1835 行** 🛑 超 §七 1200 硬上限（與 engine lib 測試數 1835 為巧合同值）
- `bb_breakout.rs` **2412 行** 🛑
- `grid_trading.rs` **1729 行** 🛑

全部超標。E5-P2-4b TODO 已登記，非本 audit 結論。

## 可行改動選項 / Options

### A. 純觀察（推薦，低風險）

不動 TOML，交給 counterfactual replay audit（`docs/worklogs/2026-04-22--counterfactual_replay_audit_spec.md`，最早 2026-04-29）。**新增特定 grid cell**：`trailing_distance_pct ∈ {2.0, 2.5, 3.0, 3.5}` sensitivity scan on demo ma_crossover 7d tick-level replay，驗證假設是否成立。

### B. 降 demo `trailing_distance_pct` 3.5 → 2.0（對齊 paper/live）

**風險**：
1. 違反 `feedback_env_config_independence.md`（三環境故意獨立，禁純衛生合併）
2. 未經 counterfactual 驗證 → 若 ma_crossover 實際平均 move size > 2%（强 trend 階段），提前 trailing stop 反而割 winner
3. demo 已在 P0-2 21d 觀察期（2026-05-07 解鎖）；TOML hot-reload 不重置時鐘但改變策略行為污染觀察結果

**收益**（假設正確）：win rate 可能從 37.8% 回升到 50%+，net 從 −$6.39 轉正

→ **駁回此 option**，改走 A。

### C. 加 min_risk_reward_ratio entry gate

在 `ma_crossover` 加 ATR-based 入場 R:R 預估 + ≥ 1.5 gate。避免低質量交叉入場。

**風險**：code change、新 field、需 E2+E4；當前無準確 ATR→future-move 對應數據，gate 閾值是 hack

→ 延後到 counterfactual replay 結束後，若 A 確認 trailing distance 是主因，則不需要 C；若 trailing distance 無關，C 作為下一個假設

## 判決 / Decision

**選 A**：不動 TOML，把 `trailing_distance_pct` sensitivity 並入 counterfactual replay spec 的 grid search。

理由：
1. 三環境獨立原則（`feedback_env_config_independence.md`）
2. demo 21d 穩定觀察期未到（2026-05-07）
3. 假設尚未驗證 — A + replay 是乾淨路徑

## 下一步 / Next steps

1. ✅ Audit 完成（本文件）
2. 更新 `docs/worklogs/2026-04-22--counterfactual_replay_audit_spec.md` §7.1 grid search 範圍加 `trailing_distance_pct ∈ {2.0, 2.5, 3.0, 3.5}` sensitivity scan（獨立於 `ExitConfig` 3 參數，但共用 7d demo replay 資料）
3. TODO P1-10 下一步 (2) mark ✅，link 本文件
4. Counterfactual replay 2026-04-29+ 執行時一併驗

## 關聯 / Related

- `feedback_env_config_independence.md`（三環境獨立）
- `project_agent_p2_dynamic_sl_tp.md`（SL/TP 默認 ATR 動態 + agent_adjust 可覆蓋 + P1 max 硬頂）
- `docs/worklogs/2026-04-22--counterfactual_replay_audit_spec.md`（counterfactual replay spec v2）
- TRACK-P-V2-SWAP-1（2026-04-22 `306993e` + 20:55 CEST `--rebuild` 部署 v2 non-linear giveback，runtime live）
