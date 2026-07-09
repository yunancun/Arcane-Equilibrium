# EDGE-P2-3 Phase 1B — Maker Limit Timeout & Paper Fill Simulation

> QC（Quantitative Consultant）
> 日期：2026-04-20
> 範圍：Phase 1a 後 2 項 judgment call — maker_limit_timeout_ms default / Paper Limit fill simulation
> 結論：**Q1 = 45s base + scale with effective cooldown；Q2 = (a) touch-based，加 4 項 bias 保護**

---

## Q1 — maker_limit_timeout_ms default

**Call：`maker_limit_timeout_ms = 0.75 × effective_cooldown_ms`（A3 trend-adjusted），base = 45_000 ms，hard cap 300_000 ms。**

**一句理由：grid entry 信號 = 「price touched this level *now*」，其 half-life 顯著短於 cooldown 本身；timeout 應 ≤ cooldown 而非 ≥ cooldown，否則下一輪信號到達時舊單還掛著＝雙重 exposure。**

### 逐題：

1. **1.5× 是錯的方向。** 1.5× cooldown 意味 timeout > 下一個信號週期 — 舊未成交單會與新 tick 的重新評估重疊，造成 stale order 與 fresh intent 競爭。正確關係是 `timeout < cooldown`，建議 **0.5×–0.75×**。取 0.75× 保留尾部 fill 機會；0.5× 太激進會放棄本來會 fill 的單。

2. **Scale with A3 effective cooldown，不是 base。** A3 的邏輯是「趨勢越強，信號越不該頻繁觸發」— 同理，趨勢中 maker 單被甩開的速度也更快（單邊行情 at 1 bps offset 幾乎不會回探），timeout 應同比例拉長給 resting order 一個 fill 窗口。Base 45s × 3.5× boost = 157s，仍 < 210s effective cooldown，安全。

3. **Fill rate ballpark（mid-liquidity USDT perps, 1 bps offset, 90s window）：估計 40–55%。** 依據：(i) 1 bps ≈ mid-tier perp 典型 bid-ask spread 的 0.3–0.5 倍，理論上 passive order 需等反向流；(ii) crypto perp tick-level 回測文獻顯示 1 bps passive fill rate 在 30s-2min 窗內約 35–60%，mid-tier 比 BTC/ETH 低；(iii) grid 觸發時序 = 價格已「穿越」level，passive 單在 level 上等反彈，crypto perp mean-reversion 在 1-2min 尺度上條件概率 ~50%。**這個數字必須靠 Phase 1b 真實 demo fills 校準，不要 hard-code 任何 edge estimate 基於我的估計。**

4. **Signal decay 框架：grid entry 的 alpha half-life ≈ few ticks（秒級）**，因為觸發邏輯 = 瞬時價格穿越而非 regime。Timeout 不應從「signal 還有效嗎」角度設計（答案是：45s 後幾乎無效），而應從「order 還在 book 上提供選擇性嗎」角度 — passive maker 本質上是 **賣出一個看跌期權（price comes back）**。Timeout 決定這個隱含期權的 tenor。建議附帶 metric：追蹤 `(fill_count × maker_rebate) - (cancel_count × adverse_move_bps × position_size)`，若為負 → timeout 偏長 / offset 太窄。

**結論：`maker_limit_timeout_ms` config 加 `base = 45_000` + runtime `effective = min(0.75 × effective_cooldown_ms, 300_000)`。Phase 1b 部署後 2 週收集 fill ratio + adverse move，再校準。**

---

## Q2 — Paper Limit fill simulation

**Call：(a) Touch-based。** (b) optimistic 會系統性高估 edge 5-8 bps/RT（maker rebate 全吃 + 零 adverse selection 成本），Phase 5 edge 估計會再次被污染，重演 paper 噪音墮落循環（見 `project_edge_data_isolation.md`）。

### Day-1 必須 code-in 的 4 項 bias 保護：

1. **Queue position 折扣（fill rate penalty）：** 即使 tick 穿越 limit_price，真實 exchange 不保證 fill — 你在 queue 後面。建議 paper 以 **50% 機率 fill when `tick_price == limit_price`**（touch but no cross），**100% fill when `tick_price < limit_price` for buy（true cross）**。這避免 paper 假設「touch = fill」的樂觀偏誤，與真實 maker queue 動態對齊。

2. **Partial fill：Phase 1b 不模擬，但 reserve schema 欄位。** grid 單筆 size 在 mid-tier perp 上通常 one-shot filled，引入 partial 只增加複雜度不增加 realism。**但 fill_record 必須含 `filled_qty`，預留未來接真實 exchange partial fills 的 schema 一致性。**

3. **Funding boundary bias：** 若 limit order 跨越 funding settlement（每 8h），demo/live 會收 funding fee 但 paper 若只 simulate fill 不 simulate funding 會系統性偏樂觀（或偏悲觀，取決於 funding 方向）。建議 paper 的 P&L engine 對 resting limit 期間應用 funding — 即使未 fill，這決定了「等待成本」的真實度。Grid 策略若 resting orders 多，funding drag 會顯著。

4. **Adverse selection marker：** 對每個 filled maker 單，記錄 `mid_price_at_submit` vs `mid_price_at_fill` — 若 fill 時 mid 已反向移動，此單被「toxic flow」撿走。Paper 必須記這個 metric，否則 edge estimate 看起來乾淨但實質 filled 單全是 adversely-selected 的子集。Phase 1b 第一週就能看出 paper fill 分佈是否比 demo 更「乾淨」— 若是，說明 paper 的 touch rule 仍太樂觀。

**附加建議：paper→demo 一致性 KPI。** 部署後每週對齊 `paper_fill_rate / demo_fill_rate` — 若比例 >1.3 或 <0.7，paper 模型偏離真實 microstructure，禁止用 paper fills 餵 edge_estimates（這條 `project_edge_data_isolation.md` 已有原則，再次重申）。

---

**Total: ~395 words.**
