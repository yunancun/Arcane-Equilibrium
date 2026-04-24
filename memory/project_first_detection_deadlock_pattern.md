---
name: First-detection-only state guard 死鎖反模式 (FIX-26-DEADLOCK-1 等)
description: Rust 策略中「只在 None 時記錄狀態 + 過期/超時無自動清除路徑」的反模式 → 一旦過期該 symbol 永久 dormant；2026-04-24 bb_breakout 確認；查其他策略
type: project
originSessionId: dc1c922e-d7a7-48f1-a251-1b3d6ddb3049
---
**Pattern**：策略 state field 用「`if state.field.is_none() { state.field = Some(...) }`」guard 寫入，僅在「條件達成執行成功路徑」（如入場、平倉等）時才 `state.field = None` 清除 — **沒有時序/過期 auto-clear 路徑**。

**Failure mode**：若 first-detection window 內成功路徑沒走（任何下游 gate 失敗），stored 值永遠保留；後續同條件來時 `is_none()=false` 無新記錄；任何讀取此 field 的 expiry check（`now < stored + window`）永遠 false → 該 symbol 對該策略**永久 dormant**，直到某種 manual reset / 重啟。

**已知案例**：
- 2026-04-24 **bb_breakout `squeeze_detected_ms`**：sweep tool 自審發現；首次 squeeze 45min 窗口若無 expansion+vol+%B+Donchian 全部對齊 → 永久 dormant。修：commit `bcc5401` (`auto-clear on expiry, before is_none() guard`) + 7 regression tests。

**Why**：
- 設計者通常想要「記第一次偵測時間」(FIX-26 註釋意圖) 但忽略「沒成功就永遠不重來」的 degenerate case
- Production 看起來是「策略不活躍」(zero fills)，operator 通常歸因於閾值或市場條件，不會懷疑邏輯死鎖
- E2 code review 不易看出 — single-tick 邏輯都對；要看 multi-tick 整體 lifecycle 才浮現
- pure-replay sweep / offline backtest 是發現工具：跑長序列觀察 strategy state 卡住

**How to apply**：
1. **每個策略 audit**：grep `is_none()` guard 的 state field，逐一檢查清除路徑數量。only-on-success-path = 高風險。
2. **新策略 design rule**：first-detection state field 必須有 expiry-based auto-clear 或 explicit reset trigger（不能只依賴 success path）
3. **regression test pattern**：寫 `test_*_deadlock_*` — register state at t=0；無入場讓窗口過期；驗 state 自動清除 + 後續 fresh state 能 re-register
4. **Rust 寫 state 的 saturating_add 對稱性**：若 auto-clear 用 `saturating_add(window)`，所有讀取 expiry 的地方（in_squeeze 等檢查）也必須用 `saturating_add`，否則 release 下 wrap → degenerate

**待 audit 候選**（grep 結果）：
- `bb_reversion.rs` — 同 BB family，可能有類似 squeeze_detected pattern
- `grid_trading/` — 有多個 per-symbol state field
- `ma_crossover/` — 有 cooldown/cross_detected 類欄位
- `funding_arb.rs` — funding window state
- 其他策略 first_xxx_ms / xxx_detected_ms / xxx_started_at_ms 模式

**接手指南**：用 `grep -n "_detected_ms\|_started_at\|_first_seen" rust/openclaw_engine/src/strategies/` 開一個 sweep。每個 hit 確認 (a) 寫入用 is_none() guard 嗎？(b) 清除路徑數？(c) 過期 auto-clear 嗎？

**驗 deploy effectiveness**：bb_breakout 修復對應 healthcheck `[12] bb_breakout_post_deadlock_fix`（commit `c8a2a2c`）— `--rebuild` 後 cron 6h 報 7d entries 數 0/1-5/≥6 三態，FAIL→WARN→PASS 階梯標 dormancy 真否解除。
