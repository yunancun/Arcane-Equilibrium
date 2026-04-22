---
name: MICRO-PROFIT-FIX-1 設計意圖澄清 + 2026-04-22 runtime 狀態校正
description: MICRO-PROFIT-FIX-1 應該是「有微利就套」；2026-04-22 發現 T3 deprecation 後 runtime 已 2.5d 無實作
type: feedback
originSessionId: 07d18dec-5d35-44d7-8c6f-2a37e462ab5d
---

## 🔴 2026-04-22 runtime 狀態校正（新增，操作前必讀）

**實測**：2026-04-19 Track P T3 deprecation commit 把 `risk_checks.rs:250-264` 的 COST EDGE gate 整個註解掉，**MICRO-PROFIT-FIX-1 narrow-band gate 已無 runtime 實作**。後續本應由 Priority 6 PHYS-LOCK + ExitFeatures 取代但：
- 2026-04-19 晚 T3 rebuild → 2026-04-21 晚 T4 接線 rebuild：Priority 6 features=None 永遠 Hold（**2.5 天退場層完全空窗**）
- 2026-04-21 晚 T4 接線後：Gate 1 `est_net_bps` 99.1% NULL + P0-13 ATR scale bug → PHYS-LOCK **7 天 0 fire**

**因此本 feedback 的設計意圖**（「有微利就套」）**目前在 runtime 完全未實作**。任何基於此 memory 的決策（P0-3 Phase 5 edge 重評、P1-10 R1 驗收結論）都需先修 P0-13/P0-14 才能真正執行設計意圖。

詳 `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md` §3.4 + TODO §P0-15。

---

## 原設計意圖（保留）

MICRO-PROFIT-FIX-1 的設計初衷是「**每次有微利（扣完 fee 後仍為正）就套利**」，不是「低收益條件下 cost_edge_ratio 夠大才套現」的 gate 判斷。

**Why:** 2026-04-18 operator 澄清：當前規則 `pnl_pct >= 0.30% AND cost_edge_ratio in [0.2, ...]` 語意錯了 — 它把「微利套現」包裝成「某些成本條件下才放行的例外」，結果漏掉大量 < 0.30% 的真實微利機會。正確語意應該是：**只要 net_pnl（扣完手續費後）為正且達到最小套利門檻（可能遠低於 0.30%），就立即平倉落袋**。cost_edge_ratio 不應成為「能否套現」的 gate，最多是「套現優先級」參考。

**How to apply:**
- 重新設計時，核心條件應是 `realized_pnl_estimate - fee_estimate > min_profit_usdt_or_bps`，而不是 `pnl_pct >= X% AND ratio >= Y`
- 門檻參數可以是絕對值（$0.02 淨利）或 bps（5 bps 淨利），但不應是 0.30% pnl_pct 這種「偏高」值
- `cost_edge_ratio` 可作為「是否仍有持倉動機」的輔助信號（ratio 很高 = AI 成本吃掉預期利潤），但不應作為「能否鎖微利」的 hard gate
- 重新審視時，需核實當前 `cost_edge_max_ratio=0.2` 是否把大量微利機會卡在門外（原實證：24h demo 309 筆 narrow-band 獲利 avg $0.20 — ⚠️ 2026-04-22 P0-15 推翻：該數字為 T3 rebuild 前 cached，當前 runtime 0 rows）
- 命名上避免用「cost_edge」作為套利規則名稱，容易誤讀為「成本邊界檢查」。建議語義重構為 `micro_profit_lock` 或 `take_profit_on_micro_gain`
- **實作路徑**：待 P0-13（ATR scale）+ P0-14（edge_estimates miss）修好 + PHYS-LOCK v2 runtime fire 驗證後，在 `exit_features/v2.rs` 或新 gate 內重新實作本 memory 的設計意圖
