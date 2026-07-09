# QC Wave 3 策略審計

**日期**：2026-04-26 CEST
**範圍**：G2-06 bb_breakout threshold recalibrate / G2-02 ma_crossover R:R counterfactual / G2-04 grid disable triggers
**判定**：Q1 推 C 為主 + B 備援 → Q2 推 (c) 並行 → Q3 給定量化 disable 表

---

## Q1: G2-06 bb_breakout — 三選項排序

### 結構性事實確認

P1-11 Phase 1 多輪 audit + healthcheck [12] ≥7d 0 fills 已 CONFIRM 1m TF 下 bandwidth distribution 與 thresholds 不匹配（squeeze_bw=0.03 100% 觸發 / expansion_bw=0.04 永不達），FIX-26-DEADLOCK-1 部署後 0 fill 證偽「殘留 deadlock」假設。Rust enum `BbBreakoutProfile::{Conservative,Balanced,Aggressive}` 已就緒，TOML hot-reload 路徑可用。

### 三選項從 alpha 顯著性 / replication crisis / 微結構三角度排序

| 選項 | Alpha 顯著性 | Replication risk | 微結構（slippage/liquidity） | QC 排序 |
|---|---|---|---|---|
| **C. Disable** | 4 active 策略集中度↑，但移除 3 個月已知 dormant 噪音 | 0（不開倉無 publication bias） | 釋出策略 slot + cognitive budget 給 grid PostOnly + ma R:R 修復 | **首選** |
| **B. 升 5m TF** | 5m bandwidth 自然較寬 → squeeze/expansion separation 結構性改善；半衰期可能拉到 1-7d 區間（OpenClaw 主流量化棧） | 中 — squeeze cooldown / persistence_ms 需同步重 calibrate（5m 1 bar = 1m 5 bars） | 5m fills 比 1m 厚 → maker fill rate 改善；但 entry 慢 | **次選（C 等待期間並行 prep）** |
| **A. 1m + 重 sweep bw** | F2 已揭「signals ≠ edge」— 找到能觸發的 bw 不等於有正 edge；DSR deflation 後機率高 < 0；rolling-max 系列已知 lookahead 風險（leak-free shift(1) 對比強制） | **高** — replication crisis 紅旗：「sweep K 個參數找最佳」典型 publication bias 路徑（Harvey-Liu-Zhu 2016） | 1m SNR 為 OpenClaw 已知敵人（CLAUDE.md §三 P1-11 F1） | **末位** |

### QC 推薦路徑

**C 為主 + B 為備援**。

**量化 viable 判據**（建議起點，非治理硬規範）：升 5m 後若連 7d demo 累積 ≥ 30 fills + leak-free 確認 cost_edge_ratio < 0.5 + DSR(K=Conservative/Balanced/Aggressive 三 profile A/B test) > 0，才算可重新接回策略池；否則 disable 永久。

「signals/day」單一指標不足以判 viable — **必須 IC > 0.05 + half-life ∈ [1d, 30d]** 並列才信。

---

## Q2: G2-02 ma_crossover R:R post-G7-09 重評

### memory 既有事實

ma_crossover win rate 64% → 37.8%（QC 2026-04-24 audit），R:R = 0.45 🔴（avg_win 1.2 bps vs avg_loss 4.7 bps），G7-09 fee fix（maker 2bps + taker 5.5bps 共存）已 live。

### G7-09 能否救 R:R？

**結論：不能**。R:R = 0.45 是 **alpha 結構問題**，不是 fee 結構問題：

1. **數學上**：R:R 由 avg_win / avg_loss 決定，**fee 改變的是 net_pnl 分佈兩端的平移量（同方向同幅度）**，不改變 |win|/|loss| 比例的結構。fee 從 5.5 bps → 2 bps 約省 7 bps RT，會把 avg_win 從 1.2 → ~4.7 bps（提升明顯）+ avg_loss 從 -4.7 → -1.2 bps（縮小同量），R:R 名義上會 → ~3.9 看似翻轉。

2. **但**：MA cross 信號半衰期短 + 訊號退潮（cross 太晚進場 → 已錯過 momentum 最強段）才是 win rate 從 64% → 37.8% 的根因。fee 改 R:R 帳面好看 ≠ 結構性 alpha 回來。等 1w post-G7-09 demo 數據，**最可能看到 R:R ~對稱（0.9-1.1）但 win rate 仍 < 50%**，淨 PnL 仍負（行為偏差類 alpha 在 fee 救活的訊號頻率下會被 selection bias 反噬）。

3. **學術佐證**：McLean-Pontiff (2016) post-publication decay：trend-following / momentum 在 crypto 已大規模 ETF + perp 化後 alpha 半衰期 < 1y；2026 仍指望 EMA cross 有 edge 屬於 anomaly graveyard 類別。

### 啟動時間建議：(c) 並行（不是 a 或 b）

- E1 立即寫 counterfactual replay code（用 `decision_outcomes` + `exit_features` 重算「若 fee=2 bps 會如何」）— 這是 **1-2d code work，不阻塞數據累積**
- 同時 passive wait ~05-01+ 等真實 1w demo G7-09 後數據
- 兩條 ~05-03 對齊 → **counterfactual 理論值 vs realized 實際值**雙軌驗證
- 若兩軌 R:R 收斂在 ~1.0 但 win rate 仍 < 50% → 確認 alpha 退潮，**G2-03 SL/TP Option B 治標不治本**，建議轉 G2-04 同層次 disable 議程

---

## Q3: G2-04 Grid disable 決策量化門檻

### Triggering condition

G7-09 PostOnly + fee fix 後 **≥1w demo 累積（≥ 200 RT 或 ≥ 7d，較嚴）** 才有統計 power。樣本 < 200 → power < 0.5，**禁下 disable 結論**（CLAUDE.md walk-forward §1.3 / Step 0）。

### Disable 量化門檻表

**all 須 simultaneously fail 才 disable，避免單指標噪音誤殺**：

| 指標 | 健康門檻 | Disable 門檻 | 統計檢定 |
|---|---|---|---|
| 7d **gross edge / RT** (bps, fee 前) | ≥ +1.0 | < 0 | bootstrap 95% CI lo |
| 7d **net edge / RT** (bps, PostOnly fee 後) | ≥ +0.5 | < 0 且 95% CI 不含 0 | t-test (ddof=1) + PSR(0) ≥ 0.95 |
| **cost_edge_ratio** | < 0.5 | ≥ 0.8 | CLAUDE.md §二 原則 13 硬規則 |
| **Maker fill rate** (PostOnly) | ≥ 60% | < 40%（PostOnly 反吃 missed-trade cost） | 描述統計 + 7d 滾動 |
| 7d **Sharpe**(crypto ×365 年化) | ≥ 0.5 | < 0 | DSR deflate（K = grid 部署 symbol 數） |
| **R:R** (avg_win / avg_loss) | ≥ 0.8 | < 0.5（不對稱結構性） | 直接看比 |

### Disable 決策邏輯

- **net edge < 0 且 PSR(0) < 0.95** ⊕ **cost_edge_ratio ≥ 0.8** ⊕ **maker fill rate < 40%** → 三指標 ≥ 2 個觸發 = disable
- 若僅 1 個觸發（如 maker fill rate < 40% 但 net edge ~0）→ **延長至 14d 再評**（執行優化路徑：擴大 PostOnly offset / 改 timeout，不直接 disable）
- **win rate 不入決策表**（grid 本質高頻低 edge，win rate 不是有效信號；只看 edge × frequency）

### 推薦執行

G2-01 PostOnly 1-2w 驗收（passive, ~05-01~05-07）+ G2-04 disable 決策會（~05-08）走上表，PM+FA 共同 sign-off。

---

## QC 對 PM 的建議優先級

1. **立即**（W20 內）：派 E1 寫 G2-02 counterfactual code（不阻塞數據累積）
2. **~05-01**：執行 G2-04 量化表評 grid disable / 延期；同期 G2-06 bb_breakout 接 disable（C 選項）+ 5m profile 工具 prep（B 備援）
3. **~05-08**：grid disable 決策會 + ma_crossover counterfactual 對齊 G7-09 真實數據
4. **不做**：A 選項（1m sweep bw）— replication crisis 紅旗 + memory `feedback_indicator_lookahead_bias` 已禁

---

## 關鍵檔案路徑

- `srv/rust/openclaw_engine/src/strategies/bb_breakout/params.rs`（DEFAULT_SQUEEZE_BW=0.03 / DEFAULT_EXPANSION_BW=0.04 + Profile enum）
- `srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs`（per-symbol state + on_tick 核心）
- `srv/helper_scripts/research/bb_breakout_threshold_sweep.py`（P1-11 Phase 1 sweep 工具，含 ddof=1 + df-aware t_crit）
- `srv/TODO.md` 第 287-294 行 Wave 3 G2 表

---

**QC AUDIT DONE** — 2026-04-26 CEST
