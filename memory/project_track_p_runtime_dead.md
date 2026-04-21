---
name: Track P 物理層在 runtime 層 dead (T4 未接線 2026-04-21)
description: DUAL-TRACK-EXIT-1 Track P Phase 1b 代碼路徑完整（v1+v2 pure fn + Priority 6 callsite）但 tick_pipeline::on_tick 硬編碼 |_| None，exit_features 永遠 None，Priority 6 從未 fire；hotfix A 運行時影響 0；TRACK-P-T4-WIRING-1 為主軸解阻塞 P1
type: project
---

# Track P 物理層在 runtime 層 dead（2026-04-21 Linux CC audit 揭露）

**TL;DR**：DUAL-TRACK-EXIT-1 Track P 的代碼路徑（v1 + v2 + Gate 1 反轉 + Priority 6 callsite）**全部完成並測試綠**，但 `tick_pipeline::on_tick.rs:1677` 硬編碼 `|_| None` 從未被替換，`exit_features` 永遠是 `None`，Priority 6 PHYS-LOCK 進入 `if let Some(features) = exit_features {...}` 分支的條件從未滿足 → **從未 fire 過**。

## 證據鏈（Linux CC 2026-04-21 audit，`audit/decision-outcomes-bugs` branch）

1. `tick_pipeline/on_tick.rs:1670-1679`：
   ```rust
   let decisions = crate::position_risk_evaluator::evaluate_positions(
       &position_rows, daily_loss, session_drawdown, event.ts_ms,
       cost_edge_max_ratio, min_profit_to_close_pct,
       |_| None,   // ← T4 接線點，從未替換
       &risk_config,
   );
   ```
2. `position_risk_evaluator.rs:153` docstring 明文：「當前傳 `|_| None`」
3. `risk_checks.rs:244-250`（Priority 6 block）：`if let Some(features) = exit_features { /* PHYS-LOCK 路徑 */ }` — 只有 Some 才跑，None → skip
4. Engine log `grep phys_lock /tmp/openclaw/engine.log` = 0 matches（全時段）
5. `trading.fills` 歷史有 `risk_close:COST EDGE` (550 rows, 2026-04-16 前舊管線) + `risk_close:fast_track` (1030) + 其他前綴 → wrapping 路徑結構完全 OK，若 PHYS-LOCK 被 fire 會寫 `risk_close:phys_lock_gate4_*`，實際 0 筆 → 不是 tag 丟失，是根本沒 fire

## 影響範圍

### 歷史 commits runtime 影響 = 0
- `aee96b9` DUAL-TRACK-EXIT-1 Phase 1b Track P v2 pure fn + `ExitConfig` + 31 單測
- `d0f0c21` GATE1-REVERSAL-1 hotfix A v1 Gate 1 Lock→Hold 反轉
- 2026-04-17 MICRO-PROFIT-FIX-1 (Priority 6 替換 COST EDGE 重命名 PHYS-LOCK)

三個 commit 代碼對齊設計意圖、單測綠、Linux release build 1816/0 passed，但 runtime 執行路徑在 tick_pipeline 入口就被 `|_| None` 切斷。**代碼品質不是問題，架構接線是問題**。

### 2026-04-18 設計文件遺漏
`docs/worklogs/2026-04-18--dual_track_exit_design.md` §七「實施排程」Phase 1（W23 Day 4-7）軌道 1 列的 4 項（peak_reached_ts_ms / compute_roc / 7 維規則 / ConfigStore 綁定）**遺漏 T4 builder**。設計日誌 §七 Phase 1 有「並行 1 — Track P 實作」但沒把「位置 tick 時 assemble ExitFeatures snapshot 傳給 Priority 6」列為獨立交付項。這是設計階段 scope 漏項。

## TRACK-P-T4-WIRING-1 (P1) 實作規格

### 任務
替換 `on_tick.rs:1677` 的 `|_| None` closure 為真實 `ExitFeatures` builder。

### Builder 輸入來源（全部已就緒）
| 維度 | 來源 | 計算方式 |
|---|---|---|
| `est_net_bps` | `pnl_pct` + fee_rate | `pnl_pct - 2 × fee_rate × 100` 或 JS shrunk_bps |
| `peak_pnl_pct` | `PaperPosition.best_price` | `(best - entry) / entry × 100`（side-signed） |
| `atr_pct` | `price_tracker::compute_atr_pct` | 已存在（v2 未接線，本 TODO 接） |
| `giveback_atr_norm` | peak_pnl_pct + current_pnl_pct + atr_pct | `(peak - current) / atr_pct` |
| `time_since_peak_ms` | `PaperPosition.peak_reached_ts_ms`（2026-04-19 加） | `event.ts_ms - peak_reached_ts_ms` |
| `price_roc_short` | `price_tracker::compute_roc`（2026-04-19 加） | `compute_roc(symbol, 300ms)` |
| `entry_age_secs` | `PaperPosition.entry_ts_ms` | `(event.ts_ms - entry_ts_ms) / 1000` |

### 估工程量
~500 LOC builder + 20 integration tests + 灰度部署（保守閾值先上，觀察 1-3d fee/edge 變化）= **~3 天**。

### 灰度部署策略
1. T4 實裝後 `cargo test` 綠 → rebuild engine
2. Demo 環境跑 24h，engine log grep `phys_lock` 應非 0（至少 Gate 1 Hold 頻繁）
3. fills 看 `risk_close:phys_lock_gate4_*` 累積
4. 24h demo 無 fee 惡化 → 接受 live

## 處置紀錄

- **2026-04-21 本 commit**：記錄認知錯誤 + 新 TODO TRACK-P-T4-WIRING-1 (P1) + doc-only 關 GATE1-REVERSAL-OBSERVABILITY-1
- **不 rollback** 先前 3 commits（`aee96b9` / `d0f0c21`）— 代碼本身對齊設計，只是等 T4 接線才激活；rollback 等於放棄設計
- **不加 Prometheus counter**（Linux CC 分析方向 2）— upstream `None` 使 counter 永遠 0，無意義

## 未來 session 避免誤判

- 看到 `Priority 6 callsite 存在 + 測試綠` ≠ 「runtime 有效」；必查輸入源是否真的非 None / 閉包是否硬編碼 fallback
- 設計文件的「軌道 1 實作」要展開成「pure fn + builder + callsite + wrapping」4 塊獨立驗收，而非混為一體
- T4 / T5 etc. 接線點命名在 code 有 comment 但未必在 TODO — 定期 `grep "T[0-9]+ 接線點"` 審視遺漏
