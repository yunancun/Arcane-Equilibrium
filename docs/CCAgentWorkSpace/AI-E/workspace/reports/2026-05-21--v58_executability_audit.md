# v5.8 LLM cost 執行性審核 — AI-E

**日期**：2026-05-21
**Verdict / One-liner**：**GO-WITH-CONDITIONS（與 v5.7 同性質但 token 預算放大 ~2.0-2.3x）** — v5.8 加 13 個 module 全文 0 字提及 LLM API cost / Claude token budget / Ollama latency / ContextDistiller 升級；M4 self-supervised pattern miner + M11 nightly counterfactual replay + M6 Bayesian reward weight tuning + M8 anomaly autoencoder 是隱藏 LLM cost 主要新源頭，§3/§4 工時表 2,780-3,930 hr 全為人時，**LLM 月度 budget 未拆**；ContextDistiller 從 v5.7 ~520→700-900 → v5.8 加 anomaly+health+lease+replay context 後 ~1,200-1,500 tokens / 推理，**直接撞 DOC-08 每日 $2.00 cap 與 L1 < 3s SLA 兩條紅線**。

---

## 0. 13 module LLM cost 矩陣（Y1 / Y2 per module 預估）

| # | Module | Y1 LLM cost | Y2 LLM cost | 主要 LLM 觸發路徑 | DOC-08 cap 風險 |
|---|---|---|---|---|---|
| M1 | Decision Lease Tier | $20-35 | $60-100 | Tier 1/2 auto-approval eligibility judge（Claude Sonnet ~3-5k token × 30/month） | LOW Y1 / MID Y2 |
| M2 | Overlay state machine | $5-10 | $40-80 | Auto-enable 評估 narrative（Y2 only），自 disable trigger 純 numeric | LOW |
| M3 | Self-monitoring/health | $0-5 | $10-30 | 純規則 + statistical detector，**0 LLM**；異常 narrative 1/週 | NIL |
| M4 | Self-supervised hypothesis | $40-80 | **$200-400** | 6 種 cross-correlation/event-window stage 1 純 numpy；**stage 2 + DRAFT writeback 給 Cowork LLM review = 主成本** | **HIGH Y2** |
| M5 | Online learning | $0 | $0 | Interface stub only Y1；Y3+ IMPL 才有 cost | NIL |
| M6 | Bayesian reward weight | $5-10 | $20-40 | Gaussian Process **純 scikit-learn**；月度 narrative 1 次 Claude Sonnet ~$1-2 | LOW |
| M7 | Decay detection | $5-15 | $20-50 | 純 statistical signal；retirement decision narrative 1/decay × Claude Sonnet | LOW |
| M8 | Anomaly detection | $10-25 | **$80-200** | Y1 statistical + isolation forest 純 numeric；**Y2 autoencoder 訓練 GPU cost ≠ LLM cost**；alert narrative ~50/month × Sonnet | MID Y2 |
| M9 | A/B testing | $5-15 | $40-80 | mSPRT 純 numeric；preregistration narrative + variant verdict ~10-20/month | LOW |
| M10 | Discovery pipeline | $15-30 | $60-150 | Tier A Optuna 純 numeric；**Tier B 依賴 M4 → 跟 M4 雙重計**；Tier C/D symbol/regime discovery narrative | MID Y2 |
| M11 | Counterfactual replay | $25-50 | $60-120 | **Nightly 24h × 5 strategy replay = 純 numeric 無 LLM**；divergence narrative ~1-3/天 × Sonnet | **MID** (cap risk via narrative 頻率) |
| M12 | Adaptive order routing | $5-15 | $30-60 | Maker-vs-taker 純規則；routing profile audit narrative 月度 | LOW |
| M13 | Multi-asset/venue | $5-10 | $20-50 | Y1 interface stub only；Y2 Binance perp 規則路由 | NIL Y1 |
| **Total v5.8 add** | | **$140-300** | **$640-1,360** | | |
| **v5.7 baseline** | | **$365-565** | $700-1,200 (estimate) | | |
| **v5.8 grand total** | | **$505-865** | **$1,340-2,560** | | **Y2 月均 $112-213 vs DOC-08 $60/月 cap** |

**關鍵**：
- M4 + M11 + M8 三個 module Y2 占新增 LLM cost ~$340-720 / 年（72% 集中度）
- M5/M13 interface stub Y1 0 cost 是正確設計
- M3 / M6 / M7 / M9 / M12 純 numeric path 設計健全
- **Y2 $1,340-2,560 / 12 月 = $112-213 / 月，超 DOC-08 月 $60 cap 約 1.9-3.5x**；operator 須在 Y2 Q1 重評 cap 或 LLM narrative 降頻

---

## 1. Top 3 風險（按嚴重度）

### Risk 1：ContextDistiller token budget 雪崩 ~520 → ~1,200-1,500 tokens — **直接撞 L1 < 3s SLA**

- **嚴重度**：CRITICAL
- **位置**：v5.8 §1（13 module 全部需要 context 注入）、AI-E profile.md ContextDistiller V3 ~520 tokens、v5.7 audit Risk 2 已警告 700-900
- **描述**：
  v5.7 audit 已估 counterfactual logger（macro + on-chain）把 ContextDistiller 從 ~520 → ~700-900 tokens。v5.8 在此基礎上 13 module 再加：
  1. **M1 Decision Lease Tier state**：5 tier × strategy state ≈ +80-120 tokens
  2. **M3 Health domain state**：6 health 維度（WS latency / REST / DB / Disk / CPU / 策略指標）≈ +100-150 tokens
  3. **M7 Decay signal state**：rolling Sharpe / DD / consec loss / replay delta ≈ +60-100 tokens
  4. **M8 Anomaly current state**：market regime + own behavior 共 8 維 z-score ≈ +120-180 tokens
  5. **M11 Last replay divergence summary**：PnL/decision count/slippage delta per strategy ≈ +80-120 tokens
  6. **M6 current reward weights**：5 λ 值 + bound + last change ≈ +40-60 tokens
  
  累計：700-900 (v5.7) + 480-730 (v5.8) = **1,180-1,630 tokens / 推理**
  
  **撞兩條 DOC-08 紅線**：
  - **L1 < 3s SLA**：Ollama 9B 在 ~1,500 tokens context P50 ~3.5-4.5s / P95 ~6-9s（Linux trade-core RTX/CPU 推估，Mac Apple Silicon 略快但仍超）；27B 模型 P50 直接 ~6-9s
  - **每日 $2.00 cap**：若 Y2 升 L2 Claude Sonnet 路徑（auto-allocator gate 必經）：$0.003/1k input × 1.5k × 1,152 cycle/day = **$5.2/day = 2.6x cap**

- **為何屬「執行性」**：
  邏輯上 13 module 都應有 context 注入；執行性問題是 *沒有任何 module spec 提及 ContextDistiller 升級* + *沒有派 token budget recompute 工時* + *Sprint 1A-β/γ/δ/ε 7 週都假設 V3 520-token 預算成立*

- **Must-fix 建議**：
  Sprint 1A-α 末（即 v5.7 sign-off 點 W1.5）安排 ContextDistiller v4 spec：
  1. **分層 context**：macro/on-chain/health/anomaly 5-min snapshot 共用快取（不 per-strategy 重組）；ContextDistiller 從「per-cycle 全量」改「snapshot ref + 策略 delta」
  2. **token budget 硬限**：每推理 ≤ 800 tokens（含所有 module state），超出 → 自動降級到 statistical-only path（無 LLM judge）
  3. **Ollama 27B 仍 < 3s**：Linux trade-core 上量測 800 token context 的 27B P95；若 > 3s → 降回 9B + L2 升級路徑（Sprint 7 才用）
  4. ADR-0041（new）：ContextDistiller v4 + token budget governance

---

### Risk 2：M11 Nightly Counterfactual Replay 對全 5 策略 24h × 多月歷史 = LLM narrative burst 撞每日 cap

- **嚴重度**：HIGH
- **位置**：v5.8 §M11（"Nightly job: 24h of market data × all live strategies"）、§7 Y3 income 估計依賴 M11
- **描述**：
  M11 是「Stage 0R 一次性 gate → continuous validation」的升級。設計上每晚跑：
  1. 5 個 live strategy × 24h × replay engine = **純 numeric**（無 LLM）
  2. Divergence flag → **narrative 解釋**（"為何 replay 與 production 偏離 $50"）= 每 divergence 1 個 narrative
  3. 每日「replay quality report → Slack」= 至少 1 個 daily narrative
  
  保守估計：
  - 5 策略 × 平均 1-2 divergence/天 × Claude Sonnet 3-5k token narrative ≈ $0.15-0.30/天
  - + daily Slack report 1 × 5k token summary ≈ $0.05/天
  - = **$0.20-0.35/天 = $6-10.5/月**（單 M11 占 DOC-08 月 $60 cap 的 10-18%）
  
  + 若高 volatility 週 divergence 暴增到 5-10/天 → 月 cost $30-50 → **單 module 占 cap 50-83%**
  
  **更嚴重**：v5.8 §6 「Y1 末 60→66% 自主學習」 + 「Y2 Q2 85→88%」依賴 M11 mature。Y2 起 5 → 10+ strategy（含 Top-2 至 Top-5 + Earn + Options stack）replay narrative cost 翻倍。

- **為何屬「執行性」**：
  v5.8 §M11 工程估 140-200 hr 但 **0 LLM cost 估計**；narrative 頻率/policy 未定；Slack 報告 token 預算未拆

- **Must-fix 建議**：
  Sprint 1A-β ADR-0038（v5.8 已列）必須含：
  1. **narrative 觸發 threshold**：divergence > $X 才產 narrative（避免 noise narrative）
  2. **Daily Slack report 用 L1 Ollama 9B**：不升 L2 Sonnet；report template 預先設計 cache_read ≥ 70%
  3. **週度 burst budget**：每週 narrative 預算 ≤ $5；超出 → 降級為 weekly digest（非 daily）
  4. **M11 narrative 路由設限**：仅高 severity divergence 才走 L2；中低 severity 走 L1 + 規則模板

---

### Risk 3：M4 Self-Supervised Pattern Miner Stage 2 → DRAFT 給 Cowork LLM review = 月度 LLM cost 黑洞

- **嚴重度**：HIGH
- **位置**：v5.8 §M4（"Bot CAN propose hypotheses (write DRAFT row)" + "Hypothesis stays DRAFT until operator + Cowork review"）、AMD-2026-05-09-02 §4（Layer 2 manual-only）
- **描述**：
  M4 stage 1（cross-correlation + event-window）是純 numpy / statsmodels，**0 LLM**；
  M4 stage 2（clustering + regime）涉及 unsupervised clustering 純 sklearn，**0 LLM**；
  
  **但 DRAFT → Cowork review = LLM**：
  1. DRAFT hypothesis 寫進 `learning.hypotheses` table 包含「pattern + supporting stats + suggested setup」
  2. Cowork (operator-assistant LLM) 必須讀 DRAFT + supporting data → 給 review verdict（"統計顯著但未控 multiple comparisons" / "事件樣本太少 n=8"）
  3. v5.8 §M4 估「Y1 末 first 5-10 self-generated DRAFT」 → 後續每月 ~10-30 個 DRAFT（Y2 active 階段）
  4. 每個 DRAFT review = Cowork **長 context 讀取**（pattern stats 表 + 樣本回測曲線 + supporting events）≈ 8-15k input token × Claude Sonnet ≈ $0.024-0.045/DRAFT
  5. + operator approve / reject / edit → 二輪對話 + 5-10k token feedback writeback = 額外 $0.015-0.030
  
  保守估計 Y2：
  - 20 DRAFT/月 × ($0.045 review + $0.030 followup) = **$1.5/月 純 M4**（看似低）
  - 但 §M4 提「Y2-Y3 active loop」: 50-100 DRAFT/月 = $3.75-7.5/月
  - + DRAFT 中通過率 ~5-10% → 進 Alpha Tournament 要再評估 narrative ≈ +$2-4/月
  - **M4 Y2 LLM cost $5-12/月**（占 DOC-08 月 $60 cap 8-20%）
  
  **隱藏依賴**：Cowork LLM 是 operator-assistant，不是自動推理。但 ADR-0024-lite 允許 Cowork 提建議。v5.8 §M4 沒明確「Cowork 是 LLM-based 還是純規則」。若 Cowork 純規則 → review 質量差；若 LLM-based → 月 cost 真實累積。

- **為何屬「執行性」**：
  v5.8 §M4 估 170-240 hr 工程，**0 LLM cost**；Cowork 介入 DRAFT 流程的成本完全沒拆

- **Must-fix 建議**：
  Sprint 1A-γ M4 schema 設計時定：
  1. **Cowork review path 明確定義**：純規則 (template) + 必要時 escalate L2 LLM；不是每 DRAFT 都走 LLM
  2. **DRAFT 預先 summary**：M4 Pattern miner 自己用模板產 1-page summary（純規則），Cowork LLM 只看 summary 不看 raw data → input token 從 15k → 3k
  3. **DRAFT 月度 cap**：每月 ≤ 30 DRAFT（避免 pattern miner 噪音淹沒 review）
  4. **operator final review 走 Console GUI**：不走 Claude Code → 不計 LLM cost

---

## 2. ContextDistiller token 影響（詳算 v5.7 → v5.8 累積）

| 層級 | v5.6 baseline | v5.7 加 counterfactual | v5.8 加 13 module | 累積 |
|---|---|---|---|---|
| 基底 V3 report | 450 | 450 | 450 | 450 |
| 認知 SPEC | 70 | 70 | 70 | 70 |
| Macro state 5 維 | 0 | +50-80 | +50-80 (共用 snapshot) | 50-80 |
| On-chain signal 4 維 | 0 | +60-100 | +60-100 (共用 snapshot) | 60-100 |
| **v5.7 subtotal** | 520 | **630-700** | **630-700** | — |
| M1 Lease tier state | — | — | +80-120 | +80-120 |
| M3 Health 6 維 | — | — | +100-150 | +100-150 |
| M6 Reward weights 5 λ | — | — | +40-60 | +40-60 |
| M7 Decay signal 4 維 | — | — | +60-100 | +60-100 |
| M8 Anomaly 8 維 z-score | — | — | +120-180 | +120-180 |
| M11 Last replay summary | — | — | +80-120 | +80-120 |
| **v5.8 subtotal** | — | — | **+480-730** | **+480-730** |
| **GRAND TOTAL** | **520** | **630-700** | **1,110-1,430** | — |

**延遲推估**（Ollama 推理，含 context 載入）：
| Context tokens | Ollama 9B P50 | Ollama 9B P95 | Ollama 27B P50 | DOC-08 SLA |
|---|---|---|---|---|
| 520 (v5.6) | ~1.5s | ~2.8s | ~3.5s | < 3s |
| 700 (v5.7) | ~2.2s | ~4.0s | ~5.5s | **9B P95 撞 SLA** |
| 1,200 (v5.8) | ~3.8s | ~6.5s | ~9.0s | **9B P50 撞 SLA** |
| 1,500 (v5.8 high) | ~4.5s | ~8.0s | ~11s | **全撞** |

**結論**：v5.8 不僅延遲撞線，**snapshot 共用 + 分層 context** 是 Sprint 1A 必交付否則 Sprint 2 開始就出問題。

---

## 3. cost_edge_ratio gate 擴展（DOC-08 §12 第 13 條）

DOC-08 Root Principle 13：「cost_edge_ratio ≥ 0.8 → 建議關倉」

v5.8 13 module 對 cost_edge_ratio 計算的影響：

| 計算組件 | v5.7 baseline | v5.8 新增 | gate 邏輯 |
|---|---|---|---|
| **AI_cost_per_trade 分子** | L1 + L2 trade decision | + M1 lease auto-approval LLM judge (Y2) + M11 divergence narrative apportioned per策略 | 分子放大 ~20-40% Y2 |
| **expected_edge_per_trade 分母** | strategy alpha 估計 | + M6 reward weight tuning improvement claim (Y2) + M10 Tier C/D regime alpha | 分母也放大（但更 speculative） |
| **per-strategy attribution** | 5 策略 evenly | + M11 replay verifies per-strategy → 真實 attribution | **改善 attribution 精度** |

**新風險**：M4 self-supervised DRAFT 進 Alpha Tournament 後若被 promote 為 live strategy → 該 strategy 的 AI_cost 包含 DRAFT review 累積成本 (~$5-15/年) → 新策略首 6 個月 cost_edge_ratio 可能虛高 → 觸發誤關倉

**建議擴展**：
1. cost_edge_ratio v2 公式：分母用 *過去 60d 真實 net PnL*（非 expected_edge claim）
2. 新策略（M4 origin）首 90d **不適用 cost_edge_ratio gate**（Stage 1 Demo period grace）
3. M11 nightly replay → 提供 per-strategy *counterfactual edge*，作為 expected_edge 的下限對齊

---

## 4. 對 PA+PM 必收 top 3

1. **§3 工時表加「Est LLM cost (USD) per Sprint」欄**：13 module DESIGN 階段 LLM cost 約 $25-45（DRAFT 設計 + ADR review）；IMPL 階段 Y2 cost peak 月 ~$150-250；operator 須在派 Sprint 1A-β 前明確接受「Y2 LLM cost ~$1,340-2,560 vs DOC-08 月 $60 cap」或調整 cap

2. **Sprint 1A-α 末加 ADR-0041「ContextDistiller v4」**：分層 snapshot + token 硬 cap ≤ 800/推理；Sprint 1A-α PM signoff 已 done 但 v5.8 須補一個 sub-task ADR-0041 落在 Sprint 1A-β（與 ADR-0034 一起設計）；7 ADR (0034-0040) 已列但漏掉 **ContextDistiller v4 不寫 ADR = v5.8 最大 governance 盲點**

3. **§M4 + §M11 narrative budget 政策**：v5.8 §M4 必須明列「Cowork review path 純規則 vs LLM 比例」；§M11 必須明列「daily/weekly narrative 頻率 + L1/L2 routing」；兩者合計 Y2 月 cost $11-20 占 DOC-08 月 $60 cap ~18-33%，operator 須在 Sprint 1A-β 派發前釘死

---

## 5. v5.8 派發前 must-fix

1. ✅ **ADR-0041 ContextDistiller v4 補入 Sprint 1A-β**（7→8 ADR）— 否則 Sprint 2 起所有 Strategist L1 推理撞 3s SLA
2. ✅ **§3 工時表加 LLM cost 欄**（每 Sprint $ + 累積）— operator 必須看到 Y2 月均 $112-213 vs $60 cap 的 gap
3. ✅ **§M4 Cowork review path 明確** — 純規則 / LLM / 混合三選一，影響 M4 Y2 cost $1.5/月 → $7.5/月差距
4. ✅ **§M11 narrative 政策** — daily Slack report 用 L1 Ollama (0 LLM cost) 或 L2 Sonnet（$0.05/天）；divergence threshold 釘
5. ✅ **AI-E memory 2026-05-09 v3 E.1 writer path** — v5.7 audit 已列；v5.8 加碼：M1/M4/M6/M11 都會新觸發 LLM call，**writer path 不修則 13 module 全部沒有 cost 可量測**
6. ✅ **DOC-08 月 $60 cap 重估或保留** — Y2 預估 $112-213 月顯然超 cap；operator 三選一：(a) 接受超 cap 並付費 (b) 砍 M4/M11 narrative 頻率 (c) Y2 Q1 重評 cap 升至 $200-300/月

---

## 6. Sprint 1A-β-ε should-fix

1. ✅ **Sprint 1A-β (M1+M3+M6+M7+M11)**：220-320 hr — 含 ADR-0041 ContextDistiller v4 設計（額外 20-30 hr）總 240-350 hr
2. ✅ **Sprint 1A-γ (M2+M4+M8+M9+M10)**：190-290 hr — M4 schema 含 Cowork review path 設計（額外 15-25 hr）
3. ✅ **Sprint 1A-δ (M5+M12+M13 stub)**：58-82 hr — 0 LLM cost 影響（純 interface）
4. ✅ **Sprint 1A-ε (Integration)**：40-60 hr — 加「LLM cost cross-module audit」（額外 10-15 hr）量測 ContextDistiller v4 在 5-min cycle × 4 strategy 的真實 P50/P95
5. ✅ **Sprint 3-5 M11 nightly replay 試運行期間限縮 narrative**：first 60 day 只產 weekly digest（不 daily），驗證 narrative quality 再升 daily
6. ✅ **Sprint 8 M4 first DRAFT 試運行限縮 ≤ 5 DRAFT/月**：避免 Cowork review 黑洞；Y2 Q2 active 階段才升 20-30 DRAFT/月
7. ✅ **Sprint 1B+2 cache_read 比例量測**：v5.7 audit §7 建議 Tournament prompt template 化 → v5.8 13 module 系統性 prompt cache 設計，目標 cache_read / total_input ≥ 60%（節 ~40% input token cost）

---

## 7. 與 v5.7 audit 對比 / 修正

| 項目 | v5.7 audit 估 | v5.8 audit 修正 |
|---|---|---|
| Y1 LLM cost | $365-565 | **$505-865**（+$140-300 for 13 module DESIGN/early IMPL） |
| Y2 LLM cost | ~$700-1,200 (估) | **$1,340-2,560**（+$640-1,360 for 13 module active IMPL） |
| ContextDistiller token | ~700-900 | **1,110-1,430** (v5.8 累積) |
| L1 SLA risk | 27B in 900 token 可能撞 3s | 9B in 1,200 token P50 直接撞 3s |
| ADR 數 | 4 (0030-0033) | 7 (0034-0040) + 應加 **ADR-0041 ContextDistiller v4** |
| Sprint 1A 工時 | 60-80 hr (v5.7 baseline) | **543-797 hr** (v5.7 75-105 + v5.8 468-692) |
| 必收 top 3 | LLM 欄 / counterfactual layer / Sprint 10 拆 | **+ContextDistiller v4 / M4 Cowork path / M11 narrative policy** |

**v5.8 GO-WITH-CONDITIONS 條件**：
- 派 Sprint 1A-β 前釘 6 個 must-fix（§5）
- 加 ADR-0041 ContextDistiller v4 進 1A-β
- operator 接受 Y2 月 $112-213 LLM cost 超 DOC-08 $60 cap 或調整 cap

---

## 結論

v5.8 13 module 邏輯層面（operator 駁回 5 module push-back 後的 autonomy 設計）健全；執行性層面 **唯一系統性缺失依舊是 LLM 月度 budget 未拆**，且 v5.7 audit 警告的 ContextDistiller token 雪崩在 v5.8 加 6 個 module state 後變成 **L1 P50 直接撞 3s SLA**（不是 P95 邊緣）。

**M4 + M11 + M8** 三個 module 是 Y2 主要 LLM cost 源頭（72% 集中度），其中 M4 Cowork review path 未定義是「自由發揮」黑洞，M11 nightly narrative 頻率未定義是「每日 cap 違規」高風險，M8 anomaly autoencoder 屬 GPU 訓練成本（非 LLM API）但 alert narrative 仍有 LLM cost。

**v5.7 audit 給 GO-WITH-CONDITIONS（4 條件）；v5.8 audit 給 GO-WITH-CONDITIONS（6 條件 + ADR-0041 新加）**。Sprint 1A-α (v5.7 PM signed 2026-05-21) 不阻塞；Sprint 1A-β 派發前必須完成 §5 6 條 must-fix。

---

**End of report — AI-E executability audit on v5.8**
