---
name: MICRO-PROFIT-FIX-1 設計意圖澄清
description: MICRO-PROFIT-FIX-1 應該是「有微利就套」，而不是「低收益條件下是否套現」的 gate
type: feedback
originSessionId: 07d18dec-5d35-44d7-8c6f-2a37e462ab5d
---
MICRO-PROFIT-FIX-1 的設計初衷是「**每次有微利（扣完 fee 後仍為正）就套利**」，不是「低收益條件下 cost_edge_ratio 夠大才套現」的 gate 判斷。

**Why:** 2026-04-18 operator 澄清：當前規則 `pnl_pct >= 0.30% AND cost_edge_ratio in [0.2, ...]` 語意錯了 — 它把「微利套現」包裝成「某些成本條件下才放行的例外」，結果漏掉大量 < 0.30% 的真實微利機會。正確語意應該是：**只要 net_pnl（扣完手續費後）為正且達到最小套利門檻（可能遠低於 0.30%），就立即平倉落袋**。cost_edge_ratio 不應成為「能否套現」的 gate，最多是「套現優先級」參考。

**How to apply:**
- 重新設計時，核心條件應是 `realized_pnl_estimate - fee_estimate > min_profit_usdt_or_bps`，而不是 `pnl_pct >= X% AND ratio >= Y`
- 門檻參數可以是絕對值（$0.02 淨利）或 bps（5 bps 淨利），但不應是 0.30% pnl_pct 這種「偏高」值
- `cost_edge_ratio` 可作為「是否仍有持倉動機」的輔助信號（ratio 很高 = AI 成本吃掉預期利潤），但不應作為「能否鎖微利」的 hard gate
- 重新審視時，需核實當前 `cost_edge_max_ratio=0.2` 是否把大量微利機會卡在門外（實證：24h demo 309 筆 narrow-band 獲利 avg $0.20，但可能還有更多 <0.30% 的微利被丟掉）
- 命名上避免用「cost_edge」作為套利規則名稱，容易誤讀為「成本邊界檢查」。建議語義重構為 `micro_profit_lock` 或 `take_profit_on_micro_gain`
