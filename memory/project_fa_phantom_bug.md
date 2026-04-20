---
name: FA-PHANTOM-1 ROOT CAUSE — fast_track margin_util 忽略 leverage，系統性誤觸 CloseAll
description: 2026-04-14 追查定案 + 2026-04-14 晚 FUP 校正 — on_tick.rs 計算「margin_utilization_pct」時用 total_notional/balance 未除 leverage；閾值 90% 遠低於運行配置 200% 設計上限，倉位堆滿必觸 CloseAll。修復已部署（commit 7eef87f）+ on_tick 整合測試（commit 6c8b1a1）+ DB 污染標記（769 fills paper+demo）
type: project
originSessionId: 258747c1-ad4c-4e68-89b4-57dab2c6a8e0
---
**狀態（2026-04-14 晚）**：FIX COMPLETE + TESTED + CONTAMINATION FLAGGED。等 operator 批准 `restart_all.sh --rebuild` 部署，之後 canary ≥1h。

**ROOT CAUSE（2026-04-14 22:30 定案）**：

`rust/openclaw_engine/src/tick_pipeline/on_tick.rs` 原公式（pre-fix）：
```rust
let margin_utilization_pct = {
    let balance = self.paper_state.balance();
    let total_notional: f64 = positions.iter().map(|p| p.qty * latest_price).sum();
    (total_notional / balance * 100.0).min(999.0)
};
```
**缺陷**：`total_notional / balance` 是 notional 比率，不是 margin 比率。真正 margin_used = `total_notional / leverage`。fast_track.rs 閾值 90% 同時 `total_exposure_max_pct` 設計上限為 **200%**（實際運行配置）— 閾值遠低於設計上限，倉位堆滿必觸發。

**實際運行配置**（2026-04-14 `/tmp/openclaw/pipeline_snapshot_paper.json` risk_manager_config.limits，**非 Rust 預設值**）：
- `leverage_max = 100.0`（Rust default=20.0）
- `total_exposure_max_pct = 200.0`（Rust default=100.0）
- `position_size_max_pct = 50.0`（Rust default=20.0）
- `open_positions_max = 25`
- balance ≈ $615（paper），起始 $620

**修正後的觸發數學（用實際 config）**：
- 每倉 notional ≤ balance × 50% = ~$307
- 2 倉達 100% balance → pre-fix 公式 = 100% margin_util → 觸 90% 閾值
- 實際 engine.log 顯示 `positions=5` 時觸發，因策略 sizing 依 Kelly/confidence 調小到 ~20% 實際值，5×$124 ≈ $620 = 100%
- Post-fix：同樣 5 倉 $620 notional / 100x leverage = $6.2 margin_used / $615 balance = **1.0%** → 遠遠低於 90%
- Design 極限：200% exposure / 100x leverage = 2% margin → 永不達 90%（→ 見 FUP-7 設計層議題）

**triggered cycle**（DB forensics + engine.log WARN 22 次 17:01-20:19 全部 `risk_level=Normal`）：
1. 策略 sizing 按 Kelly/confidence 壓到 ~20% 實際 notional，5 倉累積 ~100% balance
2. pre-fix 公式 = 100% → 過 90% 閾值
3. `evaluate_fast_track(Normal, <5, ≥90)` → `CloseAll`
4. on_tick 迴圈 `close_position_at_symbol_market` + `emit_close_fill(..., "risk_close:fast_track")`
5. paper_state.close_position 後 `on_external_close(sym)` 被呼叫到每個策略
6. 策略內部 `positions[sym]` 清空但 `last_trade_ms[sym]` cooldown 保留（funding_arb 60min / ma 5min / bb 10min）
7. cooldown 過 → 重入 → 重複

**證據鏈**：
- engine.log 22 次 WARN 全部 `risk_level=Normal` + `positions=5/10` → 排除 CB/閃崩
- DB fills 窗口（paper 17:33-22:19）每 entry 約 $124 notional，每 close 價 ≈ entry 價 ± 0.3% → 排除 flash crash
- `pipeline_snapshot_paper.json` balance=$619.80，實際運行 5 倉時 notional=$620 = 100%
- **demo 也被擊中**：同窗口 58 fast_track_close fills，bug 對稱存在，非 paper 專屬
- 非 funding_arb 策略（ma_crossover/grid_trading/bb_*）DB 顯示**完全相同**的 entry→risk_close:fast_track 對

**衝擊範圍定量**（FUP-6 校正 QC 量化，2026-04-14 窗口 17:00-20:30 paper）：
- strategy_open=263 / fast_track_close=105 / strategy_close=94 / other_risk_close=63
- fast_track = **105/525 ≈ 20% 總 fills**，105/262 ≈ **40% 所有 closes**
- **結論**：**貢獻者，非主因**。剩 60% closes 的 edge 問題獨立存在（見 project_phase5_promotion_edge_crisis.md）

**FIX（已部署，commit 7eef87f）**：`on_tick.rs` leverage-aware：
```rust
let leverage = self.intent_processor.risk_config().limits.leverage_max.max(1.0);
let margin_used = total_notional / leverage;
let margin_utilization_pct = (margin_used / balance * 100.0).min(999.0);
```

**後續修補（同日）**：
- commit `6c8b1a1`：`stress_integration.rs` +2 on_tick 端到端回歸測試（20x 不觸發 + 1x 觸發）。bite-check 驗證：移除 `/leverage` 使 20x 測試從 pass→fail
- DB 污染標記：`UPDATE trading.fills SET details.contaminated=true + details.contamination_reason='fa_phantom_1'` 於 2026-04-14 17:00-20:30+02 所有 paper+demo 769 fills

**替代方案（當時評估，不推薦）**：
- Option B: 閾值從 90% 抬到 500%+ — 仍是 patch，且設計語意不對（稱 "margin" 卻是 notional）
- Option C: Paper 模式 skip fast_track — 破壞 paper 與 live 對齊
- Option D: paper_state 補 `margin_used` 欄位 — 大改動，與 Option A 等效

**測試基準線**：engine lib 1146 + core 372 + stress_integration 35（含 FA-PHANTOM 2 新 + prior `test_fa_phantom_1_regression_full_notional_no_action` 單元測試）。

**FUP 留尾**：
- FUP-7（P2）：post-fix 90% 閾值對實際配置（leverage=100 × exposure=200% → 真實 margin 最多 2%）是 **dead code masquerading as safety** — 需 operator 決策降閾值 / 刪除 / 保留為極端 fail-safe
- FUP-8（獨立 bug）：窗口內 `trading.intents.details` 100% NULL（grid 176 / ma 91 / funding_arb 21 / bb_reversion 1），IntentProcessor.process() 未寫入策略 edge/rate/basis/confidence，違反根原則 #8「交易可解釋」
- 部署後 canary ≥1h 觀察 `FAST_TRACK CloseAll fired` on `risk_level=Normal` 是否徹底消失
