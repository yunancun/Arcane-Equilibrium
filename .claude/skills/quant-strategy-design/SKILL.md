---
name: quant-strategy-design
description: 量化交易策略「設計」視角 — Alpha 來源 framework、信號融合、衰減分析、多時間框架、行為金融異常、replication crisis 警覺；與 math-model-audit（audit 視角）互補。QC agent 主用。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Quant Strategy Design（量化策略設計手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- QC 收到「新策略提案」「alpha hypothesis」「信號設計」「多源訊號融合」「策略升級規劃」
- Operator 提出「我看到某 paper / 某 KOL 推薦 X 異常」要評估
- 5 策略（grid / ma_crossover / bb_breakout / bb_reversion / funding_arb）edge 衰減後的接班候選

## ★ Alpha 8 來源 framework

任何策略提案必須先指出 alpha 來源屬於哪一類。**無法歸類 = 沒有 edge，直接 Reject**：

| # | 來源類別 | crypto 例子 | 風險 |
|---|---|---|---|
| 1 | **行為偏差**（herd / FOMO / panic）| momentum、breakout 後追單 | regime 切換時反向 |
| 2 | **結構性低效**（市場分割、監管套利）| CEX↔DEX basis、funding rate spike | 隨資金流入消失 |
| 3 | **流動性提供**（spread + rebate）| market making、PostOnly 主動報單 | inventory risk |
| 4 | **資訊不對稱**（鏈上、新聞、訂單流）| whale tracking、large order 領先 | 資訊源消失即 dead |
| 5 | **波動率錯定價**（implied vs realized）| variance risk premium、gamma scalping | crypto IV 市場淺 |
| 6 | **時間框架套利**（短期均回 / 長期動量）| pairs trading、co-integration | 半衰期短 |
| 7 | **跨資產溢出**（BTC↔altcoin 動量）| BTC dominance regime → alt rotation | 相關性結構性轉變 |
| 8 | **微結構 / queue position**（HFT 邊緣）| order book imbalance、queue jumping | latency war，個人玩家難 |

OpenClaw 5 策略對照：
- `grid_trading`：類別 6（短期均回，需區間 regime）
- `ma_crossover`：類別 1（趨勢追隨）
- `bb_breakout`：類別 1（突破延續）
- `bb_reversion`：類別 6（短期均回，需 squeeze 後 mean revert 假設）
- `funding_arb`：類別 2（結構性 funding 不平衡）

## 信號衰減 / 半衰期分析

每個策略上線前必算「edge half-life」— alpha 隨時間衰減速度：

```
half_life = ln(2) / λ   ， λ 從 PnL_t = PnL_0 · e^(-λt) 擬合
```

**判讀**：
- `< 1 day` → HFT 級，OpenClaw 棧（每 tick 跑、~ms 延遲）打不到
- `1-7 day` → 短期 alpha，需動態 regime gate
- `7-30 day` → 中期 alpha，主流量化棧
- `> 30 day` → 長期 factor，配置型而非交易型

**OpenClaw 適用範圍**：1-30 day。短於 1d 不接（latency 不夠）；長於 30d 給配置層不給策略層。

## 信號融合與 IC/IR

多源信號融合時必算：

- **Information Coefficient (IC)**：信號 vs 未來 N 期收益的 Spearman 相關
  - 單信號 IC > 0.05 算可用，> 0.10 算強
- **Information Ratio (IR)**：`mean(IC) / std(IC)` — IC 穩定性
- **Cross-signal correlation**：信號間 ρ > 0.7 → 退化為單信號，融合無價值

**融合方法**（按複雜度排）：
1. Equal weight average — baseline
2. IR-weighted（按各信號歷史 IR 加權）
3. Mean-variance optimal blend（min variance subject to expected IC）
4. Bayesian model averaging（含先驗信心）

**反模式**：把 5 個高度相關信號 (ρ > 0.8) 平均當「集成」— 等同單信號，但複雜度翻倍。

## 多時間框架融合

OpenClaw 已用 1m kline，補方法：
- **Higher TF gate**：1h trend filter + 1m entry
- **Multi-TF confirmation**：1m signal + 5m confirmation + 1h regime
- **Adaptive TF**：低波動用長 TF（穩定），高波動用短 TF（捕捉）

警告：TF 越短 SNR 越低，1m 的 noise floor 是 OpenClaw 主要敵人（見 P1-11 BB-BREAKOUT）。

## 行為金融 / 市場異常（crypto specific）

值得納入策略設計：
- **Funding payment cycle**：8h 結算前 / 後價格動態（mean-revert 偏向）
- **Weekend effect**：週五 → 週日交易量低 + 波動 + 少量 mean-revert
- **CME futures gap**：週末 BTC 現貨 vs CME 期貨 gap，週一回補
- **Halving effect**：BTC halving 前 6m / 後 12m 不同 regime
- **Listing pump**：Bybit 新 listing 後 24h pump-dump 已知 pattern

不值得納入（噪音 > 訊號）：
- 月份 / 季節 effect（樣本太小）
- Twitter / sentiment（OpenClaw 無此數據源）
- 鏈上 metric（OpenClaw 不接 chain RPC）

## ★ Replication Crisis & Public Anomaly Graveyard

**任何策略提案如引用學術論文 / KOL 異常 → 必先查 graveyard**。50% 已發表 anomaly 不能 replicate。

### 已知 dead anomalies（不要重新發明）
| 來源 | 異常 | 為何 dead |
|---|---|---|
| Harvey, Liu, Zhu (2016) JFE | 296 個 cross-sectional factor，~50% 不能 replicate | publication bias + multiple testing |
| Hou, Xue, Zhang (2020) RFS | 全 anomaly replication study，>50% t < 1.96 | 同上 |
| McLean, Pontiff (2016) JF | post-publication decay 研究：published 後 50%+ alpha 消失 | 學術 paper 一發 → 大家做 → arbitrage 掉 |

### 紅旗（看到立即懷疑）
- 「我用 ML 找到了 X feature 預測未來收益」→ 通常是 leakage
- 「Sharpe 3.0+ 的 backtest」→ 通常是過擬合 / look-ahead bias
- 「沒有交易成本的回測 PnL 圖」→ 真實 fee 後可能 -50%
- 「rolling window N 內最大值突破」→ rolling-max 含 current bar 必 mean-revert（你 memory `feedback_indicator_lookahead_bias.md`）

### 評估流程（看到 claim 必跑）
1. ArXiv / SSRN search 看是否已 published + 多少引用
2. Google「<anomaly> replication」/「<anomaly> dead」
3. 對照本檔 graveyard
4. 實證檢測：在 OpenClaw 的 demo 數據跑 OOS 能不能 replicate

## 設計 → 驗證 → 部署 SOP（10 步）

1. **Alpha 來源歸類**（8 來源 framework）— 答不出 = Reject
2. **學術文獻 check**（已 published? graveyard 內?）
3. **數學模型化**（公式 + 假設）
4. **半衰期估算**（< 1d → 拒，OpenClaw 打不到）
5. **資料準備**（demo 數據，engine_mode 隔離；feedback `demo_over_paper_for_edge`）
6. **In-sample backtest**（leak-free shift(1)，注意 P1-11 F3 RETRACT 教訓）
7. **Walk-forward OOS**（用 `walk-forward-validation-protocol` skill）
8. **成本驗證**（cost_edge_ratio < 0.5 → 過；用 `crypto-microstructure-knowledge` skill）
9. **組合相容**（與現有 5 策略 ρ < 0.7；用 `portfolio-construction-protocol` skill）
10. **Demo 21d gross > 0**（CLAUDE.md §三 Phase 5 reframed 標準）

任一步 fail = pause 直到修。

## OpenClaw 特定核心

- **Phase 5 reframed**：當前所有活躍策略 gross edge 為負（PNL-FIX-1/2 後揭露）。新策略上線標準：demo 21d gross > 0 + cost_edge_ratio < 0.5
- **edge_estimator JSON 結構**：`strategy::symbol` top-level key，不是 `cells{}` nested（memory `project_edge_scheduler_stalled.md`）
- **engine_mode IN ('live','live_demo')**：filter 必含兩者，歷史 43k live 條多為 LiveDemo（memory `project_engine_mode_tag_live_demo.md`）
- **bb_breakout F3 RETRACT 教訓**：Donchian 含 current bar 是 measurement bias，必並列 `shift(1)`
- **5 策略 fee drag**：grid 過交易、ma_crossover R:R 不對稱（CLAUDE.md §三 P1-10）— 新策略前先確認 fee model 不犯同樣錯
- **PostOnly maker rebate**：EDGE-P2-3 部署後 fee ↓5.5 bps，新策略可考慮 PostOnly entry（但要驗 fill rate）

## 反模式（見即 Reject）

- Alpha 來源「答不出 / 多種混合 / 跟感覺有關」
- 半衰期 < 1 day（OpenClaw 打不到）
- 引用 anomaly 但沒查 replication crisis
- 「ML 找到 feature」沒驗 leakage
- IC < 0.02 但堅稱有用
- 5 個高相關信號（ρ > 0.8）平均當集成
- 1m timeframe 設計但沒驗 SNR
- 沒對照 OpenClaw graveyard（HMM / GARCH / VPIN / vol mean-rev / 獨立 Donchian）

## 輸出格式

```markdown
# QC 策略設計評估 — <strategy_name> · <date>

判定：Approve / Conditional（待 N 條件）/ Reject

## Alpha 來源
類別 #X（行為偏差 / 結構性低效 / ...）— 一句話為何屬此類

## 學術 / Anomaly check
（是否 published、graveyard 命中、replication 狀態）

## 半衰期估計
λ ≈ X，half_life ≈ Y day

## 信號 IC / IR（如多源融合）
| 信號 | IC | IR | 與其他 ρ |

## 設計 → 部署 10 步 status
| 步 | 狀態 | 證據 |

## OpenClaw 適配
- engine_mode 隔離 ...
- 與現有 5 策略 ρ ...
- fee model ...

## 條件 / 拒絕理由
1. <具體 + 修正路徑>
```
