---
name: Track P 物理層 runtime 接線（2026-04-21 Linux audit 揭露 dead → 同日 T4 接線 commit e95c779）
description: DUAL-TRACK-EXIT-1 Track P Phase 1b 代碼路徑完整（v1+v2 pure fn + Priority 6 callsite），2026-04-21 Linux audit 揭露 tick_pipeline::on_tick 硬編碼 |_| None 使 Priority 6 從未 fire；同日 TRACK-P-T4-WIRING-1 commit e95c779 接線完成，engine lib 1839 passed（Mac/Linux 均驗）；待 --rebuild 部署後 Priority 6 才開始 runtime 評估
type: project
---

# Track P 物理層 runtime 接線演進（2026-04-21）

**演進時序**：
- 晚 2（Linux audit）：揭露 `tick_pipeline/on_tick.rs:1677` 硬編碼 `|_| None` → Priority 6 PHYS-LOCK 從未 fire，Track P 全部 commits（`aee96b9` v2 pure fn / `d0f0c21` hotfix A / MICRO-PROFIT-FIX-1）runtime 影響 = 0
- 晚 3（T4 接線）：`commit e95c779` 替換 `|_| None` 為實際 `ExitFeatures` builder closure；新 pure fn `exit_features::build_exit_features_for_tick`；Mac + Linux release 均驗 engine lib 1827 → 1839 passed（+12 new builder tests）
- 待部署：Linux `restart_all.sh --rebuild` 後 Priority 6 runtime 才實際跑起來

**TL;DR**：dead 狀態 2026-04-21 同日解除。v1 (linear PhysLockConfig) runtime 已接，v2 (non-linear ExitConfig) swap 為後續 `TRACK-P-V2-SWAP-1` TODO。

## 原證據鏈（Linux CC 2026-04-21 晚 2 audit，已在 commit `e95c779` 解除）

1. `tick_pipeline/on_tick.rs:1670-1679`（舊）：
   ```rust
   let decisions = crate::position_risk_evaluator::evaluate_positions(
       &position_rows, daily_loss, session_drawdown, event.ts_ms,
       cost_edge_max_ratio, min_profit_to_close_pct,
       |_| None,   // ← T4 接線點 ← 已於 e95c779 替換
       &risk_config,
   );
   ```
2. `position_risk_evaluator.rs:153` docstring 明文：「當前傳 `|_| None`」 — 仍在（docstring 描述 caller 歷史選擇，new caller 已改餵實際 closure）
3. `risk_checks.rs:244-250`（Priority 6 block）：`if let Some(features) = exit_features { /* PHYS-LOCK 路徑 */ }` — 只有 Some 才跑
4. Engine log `grep phys_lock /tmp/openclaw/engine.log` = 0 matches（全時段，直到 `--rebuild` 部署前）
5. `trading.fills` 歷史有 `risk_close:COST EDGE` (550 rows, 2026-04-16 前舊管線) + `risk_close:fast_track` (1030) 等 → wrapping 路徑結構 OK，PHYS-LOCK 被 fire 會寫 `risk_close:phys_lock_gate4_*`，實際 0 筆 → 不是 tag 丟失，是根本沒 fire（T4 接線前）

## 2026-04-21 晚 3 接線後（commit `e95c779`）

`tick_pipeline/on_tick.rs` T4 hook 已改為：
```rust
let paper_state_ref = &self.paper_state;
let price_tracker_ref = &self.price_tracker;
let edge_estimates_ref = self.intent_processor.edge_estimates();
let tick_ts_ms = event.ts_ms;
let exit_features_fn = |row: &PositionRow| -> Option<ExitFeatures> {
    let snap = paper_state_ref.position_exit_snapshot(&row.symbol)?;
    let price_roc_short = price_tracker_ref.compute_roc(&row.symbol, 300);
    let est_net_bps = edge_estimates_ref
        .get_cell(&snap.owner_strategy, &row.symbol)
        .map(|c| c.shrunk_bps as f32);
    Some(build_exit_features_for_tick(&snap, row.current_price, row.atr_pct,
                                       price_roc_short, est_net_bps, tick_ts_ms))
};
let decisions = evaluate_positions(..., exit_features_fn, &risk_config);
```

部署後（`--rebuild`）：Priority 6 每 tick 評估活躍持倉，合法 Lock 唯二：
- `phys_lock_gate4_giveback`（v1 linear threshold giveback ≥）
- `phys_lock_gate4_stale_roc_neg`（peak 陳舊 ≥ `stale_peak_ms` AND `price_roc_short < 0`）

edge_estimates 冷啟動（`is_populated()=false`）→ `est_net_bps=None` → Gate 1 全 Hold（預期 fail-safe，Phase 5 edge 收斂後自然解鎖）。

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
