# v5.7 Dispatch-Safe Patch 執行性審核 — AI-E 視角

**日期**：2026-05-21
**Verdict**：**GO-WITH-CONDITIONS**
**One-line summary**：v5.7 §9 工時表完全沒列 LLM/AI 月度 budget 與 token 開銷，counterfactual logger + macro feed + on-chain signals 三新 sensor 進入 ContextDistiller 後 L2 token budget 需重估，且 Sprint 9-10 Y1 counterfactual evidence 評估的 LLM 計算負擔被 §5 隱藏在 70-95 hr 工程裡未拆，Sprint 1A 60-80 hr 含不含 LLM 必須在派 PA 前由 operator 釘死。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：v5.7 §9 工時表「無 AI/LLM 成本欄」— Sprint 1A 60-80 hr 是否含 LLM 月度 budget 未澄清

- **嚴重度**：HIGH
- **位置**：v5.7 §9（Engineering Total 工時表），§8（Sprint 1A 拆分）
- **描述**：
  v5.7 §9 工時表 1,190-1,590 hr 全部是「Engineering hours」（人時），對比 v5.6 §7（1,180-1,570 hr）只調 ±10 hr，但 v5.6 → v5.7 加了 3 個動作（macro counterfactual logger / on-chain counterfactual logger / Earn governance）+ §13 提到 Plan Mode「Sprint 1-5 $30/mo API cap」這條 v5.6 還在、v5.7 §0-12 全部沒重申也沒更新。
  Sprint 1A 60-80 hr 包不包括：
  1. operator 接下來 1.5 週使用 Claude Code / sub-agent dispatch 的 token cost（estimate $30-60）
  2. 5 個新 sensor（liquidation healthcheck + options chain + Tokenomist + macro feed + Binance WS + Earn APR）的 prompt 設計 / LLM 驗證調用
  3. AI-E 自己對 Sprint 1A artifact 的 audit token cost（前 15 輪每輪 5-20k tokens）

- **為何屬「執行性」（非邏輯）**：
  邏輯上 macro/on-chain 是 counterfactual-only Y1（v5.7 §5 verdict 正確）；執行性問題是 *engineering hours ≠ AI cost*，operator 拿到 60-80 hr 派 PA 後若 LLM budget 不分開列 → 月底 Anthropic console 帳單超 DOC-08 每日 $2.00 cap 才會被 AI-E 捕捉，太晚。

- **Must-fix 建議**：
  v5.7 §9 工時表加 1 欄「Est LLM cost (USD)」或在 §13 加一節「v5.7 LLM Budget Recompute」明列：
  - Sprint 1A (60-80 hr) LLM cost：~$25-40（operator + sub-agent 配置）
  - Sprint 2 (110-150 hr) LLM cost：~$45-70（Alpha Tournament 需密集 sub-agent dispatch）
  - Sprint 9-10 (170-240 hr) LLM cost：~$60-100（Y1 評估 counterfactual evidence 需大 context window）
  - Y1 total：~$350-550 vs v5.6 §13「$350-550 hosting + API + minor」 — 需明確區分 hosting/infra vs LLM API
  在派 PA 前 operator 釘 Sprint 1A 60-80 hr 是否含 LLM token budget。

---

### Risk 2：Counterfactual logger（macro + on-chain）會把 ContextDistiller token budget 從 ~520 → ~700-900 tokens / 推理

- **嚴重度**：HIGH
- **位置**：v5.7 §5（Macro / On-Chain counterfactual logger），AI-E profile.md §「ContextDistiller token 預算 V3 報告 ~450 tokens + 認知 SPEC +70 tokens = ~520 tokens」
- **描述**：
  v5.7 §5 macro overlay + on-chain signals counterfactual logger 是 Y1 read-only 記錄器，邏輯正確；但執行性盲點：
  1. ContextDistiller 必須在 Strategist / Analyst 推理時把「當前 macro 狀態 + on-chain signal 狀態」放進 context，否則 counterfactual A/B 無法 reproducibility
  2. macro state 至少 5 維（FOMC proximity / CPI proximity / ETF flow direction / halving cycle phase / unlock cluster proximity）≈ +50-80 tokens
  3. on-chain signal state 至少 4 維（exchange flow / stablecoin mint / whale wallet / TVL flow）≈ +60-100 tokens
  4. counterfactual log entry 寫 PG 也需 schema（5+ columns），但 ContextDistiller 預算只關心 *推理輸入* 不關心 *寫入*

  ContextDistiller V3 預算原為 ~520 tokens（profile.md 引用），加 macro+on-chain context 後 ~700-900 tokens。
  Strategist 5-min cycle × 4 strategy × 24h = 1,152 cycle/天，per-cycle Ollama L1 9B 推理 + counterfactual logging:
  - L1（Ollama 本地）：token 多 0 邊際 USD，但延遲從 ~3s → ~4.5s（27B 模型更敏感）；可能撞 DOC-08 L1 < 3s SLA
  - L2（Claude Sonnet 升級時）：~$0.003/1k input × 0.7-0.9k × 1,152 = ~$2.5-3.1/day，**超 DOC-08 $2.00 cap**

- **為何屬「執行性」（非邏輯）**：
  counterfactual-only 是正確設計（v5.7 §5 邏輯 OK）；執行性問題是 *ContextDistiller token 預算未升級* + *Ollama 27B 在 ~900 tokens 是否仍 < 3s 未驗* + *L2 升級路徑撞 $2/day cap 未評*。

- **Must-fix 建議**：
  Sprint 1A 後、Sprint 2 開始前，安排 1-day mini-spike：
  1. 量測 Ollama 9B / 27B 在 700/900 token context 下的 P50/P95 延遲（Mac LM Studio dev 即可）
  2. 評估 ContextDistiller 是否能拆「macro/on-chain 狀態 = 5-min snapshot 共用」+「strategy-specific feature = per-cycle 重組」減少重複 token
  3. 若 27B P95 > 3s → counterfactual logging downgrade 為 hourly snapshot（非 per-cycle）；A/B 評估顆粒度損失
  4. 釘 L2 升級條件：若 Y1 末 counterfactual evidence 強 → Y2 啟用 macro overlay 真進產 → 屆時 token budget + L2 cost 重評

---

### Risk 3：Sprint 9-10 Y1 counterfactual evidence 評估的 LLM 計算負擔被 §5 隱藏 — A/B framework 15-20 hr 嚴重低估

- **嚴重度**：MEDIUM
- **位置**：v5.7 §5（"A/B evaluation framework: 15-20 hr"），§9（Sprint 10 = 70-100 hr）
- **描述**：
  v5.7 §5 把 A/B evaluation framework 估 15-20 hr。但實際 Sprint 10 W36-39 評估 Y1 counterfactual evidence 需要：
  1. **Counterfactual replay**：4-5 個策略 × 36 週 × per-cycle data ≈ 數百萬條 macro/on-chain context vs actual strategy decision pair
  2. **Statistical test**：t-stat / Wilcoxon / bootstrap CI on counterfactual P&L delta — pure numpy/statsmodels 不需 LLM
  3. **Pattern 解釋**：「why FOMC overlay would have helped C13 in 2026-06」這類 narrative 報告需 LLM（Claude Sonnet 等級）— 預估 50-100 個 narrative × ~3k token = ~$15-30 一次性
  4. **Operator decision support**：Y1 末「macro overlay 是否進 Y2 production」決策需要 deep audit — 至少 2-3 次 Claude Opus 級 long-context review

  v5.7 §5 「15-20 hr A/B framework」**只覆蓋了 #1 + #2**，#3 + #4 的 LLM cost + 工時藏在 Sprint 10 「70-100 hr Y1 Review」裡。

  另：v5.6 §7 Sprint 10 含「Copy Trading Evidence Gate evaluation」（4 個 gate × 4 個策略 audit）；v5.7 §9 Sprint 10 仍 70-100 hr 但又加 Y1 overlay verdict。**工時無調**。

- **為何屬「執行性」（非邏輯）**：
  邏輯上 counterfactual evidence Y1 末評估正確；執行性問題是 *工時 + LLM cost 未拆解 + 未對齊*。Sprint 10 在 W36-39 落地時若發現 70-100 hr 不夠 → Y1 review 延期 → Y2 overlay 是否啟用的決策窗口被擠壓。

- **Must-fix 建議**：
  v5.7 §9 Sprint 10 工時拆兩段：
  - Sprint 10a (W36-37) Y1 strategy review + Copy Trading Evidence Gate：40-50 hr
  - Sprint 10b (W38-39) Overlay verdict (macro + on-chain counterfactual)：40-60 hr + LLM cost ~$30-60
  總 80-110 hr（vs v5.7 §9 70-100 hr，+10 hr）
  並在 Sprint 8（W28-31）預埋「counterfactual 摘要快照」（每 4 週滾動產 narrative），減 Sprint 10 末 LLM burst cost。

---

## 2. Hours sanity check（AI cost 工時 vs estimate）

| Sprint | v5.7 §9 hr | LLM token (隱) | LLM cost (est) | 工時是否含 LLM |
|---|---|---|---|---|
| 1A | 60-80 | ~150k tokens | $25-40 | **未明示** |
| 1B | 50-70 | ~80k tokens | $15-25 | 未明示 |
| 2 (Tournament) | 110-150 | ~400k tokens | $60-90 | **未明示** |
| 3 (Top-1 build) | 130-160 | ~250k tokens | $40-60 | 未明示 |
| 4 (peak) | 160-210 | ~350k tokens | $50-80 | 未明示 |
| 5-7 (mid build) | 400-530 | ~600k tokens | $90-140 | 未明示 |
| 8-9 (decay+infra) | 210-290 | ~300k tokens | $45-70 | 未明示 |
| 10 (Y1 review) | 70-100 | ~250k tokens | $40-60 | **§5 框架 15-20 hr 未含這部分 cost** |
| **Total** | **1,190-1,590** | **~2.4M tokens** | **~$365-565** | **0 明示** |

對比 v5.6 §13「Marginal project cost Y1: $350-550 (hosting + API + minor)」— 數字相近但 v5.7 沒重申也沒更新口徑。

**結論**：v5.7 Y1 LLM API cost 約 $365-565，與 v5.6 §13 範圍一致；但 v5.7 文本層面 0 提及。Sprint 派 PA 前 operator 必須明確「§9 工時不含 LLM」+ 公布 LLM 月度 budget。

---

## 3. 未識別的依賴 / 阻塞

1. **AI-E memory 2026-05-09 v3 finding**：ai_invocations writer path 完全沒接 Strategist L1 9B 流量，DOC-08 4 KPI 中 3 個本質不可量測。v5.7 派 Sprint 1A 前必須先修 E.1 writer path（否則 counterfactual logger 寫了等於沒寫 — 無 KPI 可比較）。

2. **AMD-2026-05-09-02 §4**：Layer2 永久 manual-only by design。v5.7 §5 macro/on-chain counterfactual logger 若依賴 Strategist 5-min cycle 自動寫 → 與 AMD 衝突；若 operator 每次 manual trigger → Sprint 1A 60-80 hr 不夠（每天 ~50+ trigger）。需釐清「counterfactual logger 屬 Layer 1 自動 or Layer 2 manual」。

3. **profile.md 過期 spec 引用**：ContextDistiller token 預算 / 雙進程 AI 路徑 / DreamEngine 零成本 三條（2026-05-09 v2 verdict）已被建議廢止。v5.7 沒提任何「ContextDistiller 升級」工時 — 是默認沿用 V3 ~520 tokens 還是包含在 §5 70-95 hr？派 PA 前釘死。

4. **Ollama 27B 在 Mac dev 不可量測**：CLAUDE.md §六「Mac 是 dev 機器」+「真實 engine/DB 跑 Linux」。Sprint 1A 派 PA 後若需 Ollama 27B 延遲測試 → 必須 ssh trade-core 預約 GPU 時間，加排程依賴。

5. **Earn API integration 45 hr 含不含 LLM**：v5.7 §4 Earn 45 hr 拆 (15 + 20 + 10)，純 engineering，**無 LLM 開銷估計**。governance 整合（Guardian + Decision Lease）需要 LLM 嗎？若是 Decision Lease pattern 內含 LLM judge → 工時遺漏；若純規則 → 可接受但需明示。

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **§9 工時表加 1 欄「Est LLM cost (USD)」或新增 §X「v5.7 LLM Budget」**：列每 Sprint LLM 月度 budget，並與 DOC-08 每日 $2.00 / 月 $60 cap 對齊；超 cap 的 Sprint（2、4、10）明列「accepted overshoot 理由」或「降頻 mitigation」。

2. **§5 macro/on-chain counterfactual logger 釐清 Layer 1 自動 vs Layer 2 manual**：對齊 AMD-2026-05-09-02 §4；若 Layer 1 自動 → 寫 PG 而非 Layer 2 推理觸發；若 Layer 2 manual → Sprint 1A 60-80 hr 不夠且需 operator 手動介入頻率估計。

3. **Sprint 10 工時拆 10a/10b**：Y1 strategy review (40-50 hr) + Overlay verdict (40-60 hr + ~$30-60 LLM)；並在 Sprint 8 預埋「counterfactual 4-週滾動摘要快照」減 Sprint 10 末 burst。

---

## 5. Sprint 1A 派發前 must-fix

1. ✅ operator 釘 Sprint 1A 60-80 hr 是否含 LLM token cost（建議：含 ~$25-40，明示在派 PA prompt 中）
2. ✅ 修 AI-E memory 2026-05-09 v3 E.1 writer path（不修則 counterfactual logger 無 KPI 可比）— 雖然 v5.7 §3 V103/V104 schema 是新表不依賴 ai_invocations，但 *任何 LLM 推理計成本* 仍需 writer path
3. ✅ 釐清 v5.7 §5 counterfactual logger 是 Layer 1 自動還是 Layer 2 manual（AMD-2026-05-09-02 §4 衝突）
4. ✅ 釘 ContextDistiller 是否升級為 700-900 token 預算（影響 Ollama 9B/27B 延遲 SLA）

---

## 6. Sprint 1B-3 should-fix

1. ✅ Sprint 1B 50-70 hr 含 Bybit Earn 第一次 manual stake $200-400 — 需 Decision Lease pattern；如果 LLM 參與 → 工時 + LLM cost 需估計
2. ✅ Sprint 2 Alpha Tournament 是 LLM 密集週（5 策略 × evidence ranking + pre-registration drafts）— LLM cost ~$60-90 應明示
3. ✅ Sprint 3 Top-1 build 第一次接 macro overlay → 必須在 Stage 0 shadow 確認 ContextDistiller token budget 不破 SLA
4. ✅ §6 liquidation writer healthcheck 確認後，把舊 v5.6 假設「NEW Sprint 1」的工時 ~15-20 hr 釋出來放哪 — v5.7 §6 寫「engineering save ~15-20 hr」但 §9 工時表沒明顯減
5. ✅ v5.7 §4 Earn governance 45 hr 是否含 LLM judge — 釐清 Decision Lease pattern 內外

---

## 7. 可優化 / 拆分 / 並行

1. **Counterfactual snapshot 共用 macro/on-chain state 拆分**：5-min 一次 snapshot 寫 PG，per-策略 cycle 只 join 不重組 → ContextDistiller token 預算 +50-100 而非 +150-200，可能保住 < 3s SLA
2. **Sprint 1A sensor 6 個並行派**：existing liquidation healthcheck + options chain + Tokenomist + macro feed + Binance WS + Earn APR 可派 6 個 sub-agent E1a 並行，60-80 hr 壓縮到 1.5 週的人時不變但 wall-clock 縮短
3. **Sprint 8 counterfactual 4-週滾動快照**：減 Sprint 10 末 burst LLM cost；narrative report 每 4 週 ~10-15 個小 narrative × $3 = $30-45/month 比 Sprint 10 末 50-100 個 $1.5-3 × narrative = $75-300 一次性更划算
4. **Sprint 2 Alpha Tournament prompt template 化**：5 個策略 evidence ranking 用同一 prompt 模板可節 30-40% input tokens（cache_read hit rate 提升）
5. **AI-E 自己的 audit cadence**：v5.7 Sprint 1-10 共 39 週，AI-E 至少 4 次 audit（Sprint 1A 末 / Sprint 5 末 / Sprint 8 末 / Sprint 10 末），每次預算 ~$15-20 token cost，年度 ~$60-80 對 operator 透明

---

## 結論

v5.7 邏輯層面（thesis + 6 reviewer corrections）健全；執行性層面唯一系統性缺失是 **AI/LLM 月度 budget 完全沒入 §9 工時表**，且 counterfactual logger 對 ContextDistiller token 預算的 downstream 影響未評。

**派 PA 不應阻塞**，但須在 Sprint 1A 派 PA prompt 中強制 operator 釘 4 個 must-fix（§5 第 1-4 點）。Sprint 1A 完成後、Sprint 2 開始前安排 1-day LLM budget mini-spike，產出後 v5.8（或 v5.7.1）增補 §X LLM Budget 一節即可。

**GO-WITH-CONDITIONS**：條件 = §5 4 個 must-fix 派 PA 前釘死。

---

**End of report — AI-E executability audit on v5.7**
