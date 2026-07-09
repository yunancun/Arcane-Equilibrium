# v5.8 13-Module Autonomy Expansion 執行性審核 — BB 視角

**日期**：2026-05-21
**Auditor**：BB（Bybit Broker Compatibility Auditor）
**Verdict**：**GO-WITH-CONDITIONS**
**One-line summary**：v5.8 13-module autonomy track 的 Bybit / 多 venue 整合面在 8 項 must-fix 未補前不能 dispatch（M12 maker-fill SOP 5 條 / M13 Binance trade Y2 條件 7 條 / M11 nightly replay funding-history endpoint coverage / Bybit Pro Trader tier OpenClaw 不申 + 不需申 / M4 self-supervised data mining 不違 ToS 但 Tokenomist trial expiry 須續 / Copy Trading subaccount + M1 Tier 2 ToS 不衝突但 Bybit BD onboarding 程序未啟 / M2 macro overlay Bybit Earn auto-redeem rate limit 5 req/s 嚴格但 Y2 觸發頻率 ≤ 10/day 可接 / M9 A/B test live trading 在 Bybit ToS fair execution 條款下合規但需顯式 audit log）。

---

## 0. M12 + M13 Bybit/Binance API 支援度

### 0.1 M12 Adaptive Order Routing — Bybit endpoint 支援度

| 維度 | Bybit V5 endpoint 真實支援 | 字典 ref handbook 對齊 | OpenClaw 現狀 |
|---|---|---|---|
| **PostOnly maker** | `/v5/order/create` + `timeInForce=PostOnly` | ✅ 字典 line ~870-890 已記 | EDGE-P2-3 Phase 1B-1 demo / paper 已啟 |
| **IOC** | `/v5/order/create` + `timeInForce=IOC` | ✅ 字典已記 | OpenClaw 部分策略用 |
| **FOK** | `/v5/order/create` + `timeInForce=FOK` | ✅ 字典已記 | OpenClaw 暫未用，M12 可加 |
| **Conditional order**（stop / take_profit / trailing） | `/v5/order/create` + `triggerPrice` + `triggerDirection` | ⚠️ 字典僅基線記，5 個 strategy 適配度未全驗 | Live SL 已用，但 5 策略全覆蓋未驗 |
| **TWAP / iceberg / dark slicing** | **Bybit V5 公開 API 無原生 TWAP / iceberg / dark slicing**；只能 client-side 切片 | N/A | OpenClaw Sprint 7-8 自製 TWAP / iceberg 邏輯，**非 Bybit-native** |

**重大發現 1**：v5.8 §M12 寫「TWAP for unlock SHORT entry, iceberg for pairs」**設計可行**，但必須 client-side rust 自製（不是 Bybit-native），Sprint 7-8 工時 60-100 hr 是 IMPL client-side 切片邏輯（合理估算）。

**重大發現 2**：Bybit Conditional order 5 策略覆蓋度需 Sprint 6 IMPL 前 verify：
- C10（funding harvest）：long spot + short perp，stop loss / take profit 用 Conditional 合理
- Unlock SHORT：需 take profit + trailing stop，Bybit V5 trailing stop 在 perp 支援（字典需補錄具體 endpoint flag）
- Pairs / Mean-Revert：兩腿同步 stop 不能用 single Conditional order，需 client-side coupled SL logic（OpenClaw 已有）
- C13 VRP（options short）：Bybit options 的 stop / conditional 是否同 perp 一致**未驗**（**must-fix**）
- Funding short：與 C10 反向，同樣可用 Conditional

**重大發現 3**：reverse-snipe defense（v5.8 §M12「maker default; switch to taker only on confirmed signal」）在 Bybit Copy Trading subaccount **不能直接 apply**：
- Copy Trading subaccount 的 order 是 Bybit 自動 mirror master 倉位，follower 不能改 order type / timeInForce
- 但 **OpenClaw 是 master**（self-trade），所以 reverse-snipe defense 是 on master account；follower 自動跟單，無關
- ✅ 結論：M12 reverse-snipe 設計在 OpenClaw 端可行，但 Copy Trading 文檔必說明「followers cannot apply custom order routing」

### 0.2 Bybit Pro Trader tier — rate limit / fee impact

| Tier | Default rate | Order group | Fee tier |
|---|---|---|---|
| Standard | 600 req/5s | 20 req/s | 0.10% / 0.10% |
| **Pro Trader** | 600 req/5s（**不升**） | **75 req/s**（升 3.75x） | VIP-1 起步（0.08% / 0.04%）|
| VIP-1 to VIP-5 | 升 | 升 | maker -0.0050% rebate（VIP-5） |

**重大發現 4**：Bybit Pro Trader tier 申請門檻（snapshot 2026-04，verify with Bybit BD）：
- 30d volume ≥ $10M（perp + spot 合計）
- 或 institutional onboarding（Bybit BD review）
- OpenClaw $10k AUM × 15% APR × Y1 ≈ $1.5k 利潤，volume 在 Y1 末估 $50k-$200k（5-20x turnover），**遠未達 $10M 門檻**

**結論**：**OpenClaw Y1-Y2 不申 + 不需申 Pro Trader tier**。Y3+ AUM > $100k 後 30d volume 可能達 $2-5M，仍不達 $10M。**v5.8 §M12 rate limit 估算須假設 standard tier**。

### 0.3 M13 Binance perp trade enable Y2 條件

v5.8 §M13 + ADR-0033 Bybit-Binance amendment 的 Y2 enable 條件未明確列。BB 補完整條件：

| # | 條件 | 證據 / 來源 |
|---|---|---|
| 1 | OpenClaw 在 Bybit 上 ≥ 18 月 Live track record | AMD-2026-05-15-01 Stage gate 4 「sustained 90d + 90d operator review」延伸 |
| 2 | Counterfactual replay 在 Binance perp data 持續 ≥ 6 月（Sprint 1A Binance MD 已建） | v5.8 §M11 continuous validation 邏輯延伸 |
| 3 | operator KYC tier 2 + Binance 帳戶 + 地理 OK | Binance ToS 禁 USA / Canada / Crimea / Iran 等；operator 地理需驗 |
| 4 | Binance API key 發行 + non-withdraw scope + IP whitelist | `CLAUDE.md` D1d 對 Binance 同樣 apply |
| 5 | Binance perp 與 Bybit perp 同 symbol price-equivalent 驗證（Stage 0R 並行 replay） | v5.8 §M13「price-equivalent symbols only」 |
| 6 | Bybit 與 Binance 跨 venue arbitrage / pairs **未列為策略目標**（避免 ToS 衝突） | `CLAUDE.md` Product Boundary「Bybit 為唯一交易所」+ 跨所 out of scope |
| 7 | Y2 末 AUM ≥ $50k 才觸發 Y3+ Binance trade enable | v5.8 §5 capital tier ladder |

**重大發現 5**：v5.8 §M13 「Y2: Binance perp trade enable」**與 `CLAUDE.md` Product Boundary 衝突**：
- `CLAUDE.md` 寫「Bybit 為唯一交易所」+ ADR-0033 amendment 已寫「Bybit primary, trade secondary」
- v5.8 §M13 寫 「Y2: Binance perp trade enable」**升級為實際下單**
- **必須 must-fix**：v5.8 §M13 措辭修正為「Y3+ 評估，Y2 僅 market-data-only + counterfactual」；或 ADR-0033 amendment 進一步明確「Binance trade enable Y3+，AUM > $50k + 18-month Bybit Live track record + Stage 4 operator approval」

### 0.4 Bybit options + Binance options 完備性

| 項目 | Bybit options | Binance options |
|---|---|---|
| 公開 API | `/v5/market/option/*` 完整（已字典記） | Binance options API 完備（`/eapi/v1/*`） |
| 交易 endpoint | `/v5/order/create` + `category=option` | `/eapi/v1/order` |
| Greeks / IV / OI | Bybit REST + WS 提供 | Binance REST + WS 提供 |
| Settlement | USDC settlement | USDT / USDC settlement |
| Live Y1 部署 | ✅ C13 Y1 Bybit options 已 verified | ❌ Y3+ 才考慮 |

**結論**：v5.8 §M13 「Y3+ Binance options」不在 Y1-Y2 scope，Y3+ 部署前再 BB review。

---

## 0.5 Bybit ToS 對 13 module 衝突

### 0.5.1 Copy Trading subaccount + M1 Tier 2 auto-approve

| 維度 | Bybit ToS / Copy Trading 程序 |
|---|---|
| Master Trader 啟用 | KYC tier 2 + 90d 連續 P&L OR 100k+ ROI（Cadet tier）|
| Copy Trading 程序面 | Bybit 平台自動 mirror master → follower，**master 可全程自動化** |
| Follower 體驗 | 即時跟單，master 任何 order 即時 copy；無 manual approval needed by follower |
| Master 端 ToS 對 AI 自動化 | **Bybit ToS 不禁止 master 用 algo / AI 自動化**；只要 KYC OK + API 用戶協議簽署 |

**重大發現 6**：v5.6 §10 Master Trader subaccount 啟用「90d 連續 P&L 必須在同一 sub-account 累積」，operator 主帳的 self-trading 90d 不能 transfer 給 Master Trader sub。**v5.8 § Copy Trading 仍保留 v5.6 框架**（沒在 v5.8 重述），but BB advisory 還是：
- Sprint 9 末 Copy Trading evidence gate review 前，Bybit BD onboarding **應 Sprint 6-7 即啟動**（不是 Sprint 9）
- Bybit BD review 時間 typical 2-6 weeks
- BD onboarding 啟動 = manual operator action（不 programmatic）

**結論**：M1 Tier 2 auto-approve 與 Copy Trading ToS **不衝突**（OpenClaw 是 master，自動化 self-trade，follower 跟單；不需 follower-side approval）。

### 0.5.2 M9 A/B test live trading ToS 合規

Bybit ToS / Trading Rules 對 A/B test：
- 不禁止 user-side variant test（個人帳戶內）
- **可能違反**：若 A/B test 在 Master Trader → follower 環境執行（A 變體成本 follower 承擔），可能違 「fair execution」原則
- OpenClaw v5.8 §M9 寫「A/B test 在 self-trade live trading」**沒延伸到 follower 端** → ✅ 合規

**重大發現 7**：v5.8 §M9 active gate Y2 enable 時，**must-fix**：
- 加 audit log `learning.ab_assignments` 顯式記錄「variant assigned to which trial」+ 「test does not affect Copy Trading follower allocation」
- ADR-0037 須明文：「A/B test 只在 OpenClaw 本身 self-trade；Copy Trading follower 永遠拿 control variant」
- 若 A/B test 結果觸發 strategy promotion / size 變動 → variant adoption 之後 followers 才看到變化（非 A/B 期間）

### 0.5.3 M4 self-supervised data scraping ToS

v5.8 §M4 寫「market.kline / trading.fills / market.liquidations / market.funding / token unlocks 24mo backfill」+「pattern mining」:

| 數據來源 | ToS 風險 |
|---|---|
| Bybit market.kline | ✅ 公開 API + 公開 historical endpoint；個人 user 用合規 |
| Bybit trading.fills（user own data） | ✅ user own data 用合規 |
| Bybit market.liquidations | ✅ 公開 WS feed + historical via Bybit API；個人合規 |
| Bybit market.funding | ✅ `/v5/market/funding/history` 公開 endpoint；OpenClaw 已用 |
| Tokenomist unlock calendar | **第三方 vendor**；ToS 限於 trial / paid subscription；Sprint 1A trial 啟用後 expire 時間需追蹤 |

**重大發現 8**：M4 「self-supervised pattern miner」是內部 ML 分析，**不是公開重新發布 / 對外展示** → ✅ 不違 Bybit ToS data scraping 條款（個人用合規）。

**Tokenomist trial expiry must-fix**：
- v5.7 §8 Sprint 1A NEW「Tokenomist trial」
- Trial 期 typical 30-90 day；v5.8 §M4 Sprint 8 active 觸發 Y2 Q2-Q3 — trial **必已 expire**
- **must-fix**：operator 在 Sprint 6-7 必 evaluate Tokenomist 付費 subscription 或 fallback vendor（Token Unlocks / Messari / 自建 unlock calendar）
- Sprint 1A 派發前 advisory：trial cost 與 expire 時間預估記入 §8

---

## 1. Top 3 執行性風險（排序）

### Risk 1：M13 Y2 Binance perp trade enable 與 `CLAUDE.md` Product Boundary 衝突（CRITICAL）

- **位置**：v5.8 §M13「Y2: Binance perp trade enable (with Stage 0R replay using Binance data) (200-300 hr)」+ §5「$50-75k (Y2 末 - Y3 Q1) : M13 Binance perp trade enable」
- **CLAUDE.md 衝突**：Product Boundary「Bybit 為唯一交易所」+ ADR-0033 amendment 寫「Bybit primary, Binance trade secondary」(secondary 是 Y3+，不是 Y2)
- **為何 critical**：
  - Y2 Q2-Q3 Auto-Allocator activation 時 operator AUM ~$25k，AUM 還沒到 Y3+ Binance enable 條件（$50-75k）
  - v5.8 §M13 Y2 enable 措辭與 Product Boundary + ADR-0033 不對齊
  - ADR-0033 是 Sprint 1A-α v5.7 12-CRITICAL prefix DONE 期的 explicit amendment，**v5.8 不能反向修正**

**Must-fix（CRITICAL）**：
1. v5.8 §M13 措辭修正為「Y3+ enable Binance perp trade，前提 AUM > $50k + 18-month Bybit Live track + Stage 4 operator approval + ADR-0033 amendment further refinement」
2. v5.8 §5 capital tier ladder「$50-75k (Y2 末 - Y3 Q1) : M13 Binance perp trade enable」修正為「M13 Binance trade enable 評估啟動（不立刻 enable）」
3. Sprint 1A-δ M13 ADR-0040 interface stub 必明文 reserve「Binance trade enable Y3+ at earliest」
4. **operator 必拍板**：Y2 enable Binance trade 是否 override Product Boundary → 若 override 須補 ADR-0041 + 5-gate hard boundary review

### Risk 2：M12 Sprint 6 maker-vs-taker adaptive logic IMPL 缺 maker-fill-rate SOP（HIGH）

- **位置**：v5.8 §M12 Sprint 6「Maker-vs-taker adaptive logic IMPL (Bybit only) (80-120 hr)」
- **問題**：
  - v5.8 §M12 adaptive logic 只寫「spread tightness / rejection rate / reverse-snipe defense」，**缺 maker-fill-rate 閾值 SOP**
  - EDGE-P2-3 Phase 1B-1 PostOnly demo / paper 已啟，但 OpenClaw 當前 maker fill rate 統計**未顯式記 SSOT**
  - crypto-microstructure-knowledge skill §5.1 起步建議 maker fill rate ≥ 60%；低於此 PostOnly 反吃 missed-trade opportunity cost
- **must-fix（HIGH）**：
  1. Sprint 1A-β M12 interface stub 必須加 `maker_fill_rate_30d` 為 OrderRouter trait 必要 metric
  2. Sprint 6 IMPL 前 BB / QC 共同 review per-strategy 當前 maker fill rate（Linux PG empirical query），定 per-strategy 閾值 baseline
  3. M12 routing decision logic 包含 maker fill rate fallback：若 fill rate < threshold 自動 switch to IOC（非 reverse-snipe 場景）
  4. 字典 ref handbook §1 加 PostOnly maker fill rate SOP 章節（與 EDGE-P2-3 Phase 1B-1 SF-1 補錄對齊）
  5. M12 ADR-0039 必明 routing decision audit log schema：`routing_decisions(decision_id, strategy_id, symbol, intent, order_type, time_in_force, rationale, ...)`

### Risk 3：M11 nightly counterfactual replay funding-history endpoint coverage（HIGH）

- **位置**：v5.8 §M11「每日重 replay 5 策略所有 fills」+ Sprint 3 IMPL
- **問題**：
  - M11 nightly replay 需要精確 historical 數據：5min/1h kline / funding rate / liquidations
  - Bybit `/v5/market/funding/history` rate limit (Asset rate group 5 req/s 最嚴 — 字典 line 1255)
  - 每日 25 symbol × funding history 至少 1 request/symbol = 25 requests，5 req/s 完成需 5 秒（OK，但若 retroactive 24mo 需 batch 處理）
  - Bybit historical kline 5min `/v5/market/kline` 不在 Asset group（Market group 120 req/s 充足）
  - **liquidations history**：Bybit V5 公開無 historical liquidations REST endpoint（只有 live WS feed + 字典 line 1092 復生的 `allLiquidation.*` event feed）
- **must-fix（HIGH）**：
  1. Sprint 1A-β M11 ADR-0038 必明：nightly replay 用 `market.liquidations` PG table（自家累積，from 2026-05-17 ~23:12 起）作為 historical source；不依賴 Bybit historical liquidations API（不存在）
  2. M11 replay 對 funding rate 用 Bybit `/v5/market/funding/history`，每 symbol query 加 batch + caching（同一日 query 1 次 cache 24h）
  3. M11 replay 對 historical kline 用 Bybit `/v5/market/kline`，24mo backfill 一次性執行（M4 Sprint 8 active 前後），rate 充足
  4. v5.7 §6 liquidation writer 持續 production（C6 verdict PASS，PG 31k+ rows / 3.7d）— M11 直接消費，**must-fix 之前 v57 audit Risk 1 「30k+ rows 事實錯誤」claim 已推翻**，M11 在 PG 已有充足數據

---

## 2. Bybit API rate limit aggregate（v5.7 + v5.8 加總）

### 2.1 Rate group 用量推估（per second peak）

| Rate Group | Default limit | v5.7 baseline | v5.8 13-module add | 加總 peak | 用量比例 |
|---|---|---|---|---|---|
| **Market**（120 req/s） | 120 req/s | ~30 req/s（kline / orderbook / funding / liquidation WS / options chain poll） | M11 nightly replay batch（rate-limited）+ M4 pattern miner historical query（peak ~50 req/s in spike） | **~80 req/s** | 67% |
| **Order**（20 req/s shared quota） | 20 req/s | ~3 req/s（5 策略 × 平均 0.6 order/s） | M12 adaptive routing 不增 order rate（替換 order type，不加 order count） | **~3 req/s** | 15% |
| **Asset**（5 req/s 最嚴） | 5 req/s | ~0.5 req/s（occasional balance / wallet query） | M2 macro overlay auto-redeem Y2 Q2+：trigger 頻率 ≤ 10/day → peak < 0.01 req/s；M11 nightly funding history batch（5 req/s × 5s burst once/day）| **peak 5 req/s burst once/day, ~0.5 req/s average** | 10% avg, 100% burst |
| **Account / Position**（50 req/s） | 50 req/s | ~5 req/s（position list / order list） | M3 healthcheck 每 30s 1 query；M7 decay detector 每日 query 1 次；M11 replay 每晚 batch | **~10 req/s** | 20% |

**重大發現 9**：Asset group 5 req/s 是最緊張的 rate group：
- M11 nightly funding history 25 symbol × 1 req = 25 req，**5 秒完成**（OK）
- M2 Y2 Earn auto-redeem 觸發頻率 ≤ 10/day → 完全可容
- M11 + M2 + M9 同時觸發 burst 在 Sprint 9-10 Y2 期 可能達 ~6 req/s（瞬間超限） → **must-fix（MED）**：M11 nightly job 與 M2 auto-redeem coordination，不同步觸發；或 retry with exponential backoff
- Order group 20 req/s 不會成為 bottleneck

**結論**：v5.7 + v5.8 加總 Bybit rate limit **不會超 standard tier**；但 Asset group 在 Y2 Q2+ 多模塊 active 時需 coordinator 避免 burst collision。

### 2.2 WS connection / topic 上限

| Item | Bybit V5 限制 | v5.7 + v5.8 用量 |
|---|---|---|
| WS connection 數 | 50 per IP（snapshot 2026-04）| 6 connection（public market / public option / private / liquidations / funding / Binance Y2+） |
| WS topic 數 per connection | 50（snapshot 2026-04） | 主 connection ~30 topic（25 symbol × 3 topic）；options chain ~30 contract × 2 topic |
| Connection 重連 / heartbeat | 20s heartbeat | 已 implemented |

**結論**：WS 配額充足。M13 Y3+ Binance perp WS connection 新加會繼續餘裕（Binance limit 不同）。

---

## 3. 對 PA + FA + PM 匯總必收 top 3

1. **v5.8 §M13 Y2 Binance trade enable 措辭修正**（CRITICAL）— 與 `CLAUDE.md` Product Boundary + ADR-0033 不對齊。Sprint 1A-δ ADR-0040 必明 reserve「Y3+ at earliest」+ §5 capital tier ladder Y2 末措辭改「評估啟動」非「enable」。Operator 必拍板：是否 override Product Boundary（若 override 需補 ADR-0041 + 5-gate review）。

2. **Sprint 1A-β M12 OrderRouter trait 必含 maker_fill_rate metric + ADR-0039 routing audit log schema**（HIGH）— v5.8 §M12 Sprint 6 maker-vs-taker IMPL 缺 maker fill rate 閾值 SOP；Sprint 1A-β interface stub 即須含 `maker_fill_rate_30d` + per-strategy fallback；字典補 PostOnly fill rate SOP 章節。

3. **M4 Tokenomist trial expiry 在 Sprint 6-7 觸發 paid subscription / fallback vendor 決策**（HIGH）— v5.7 §8 Sprint 1A NEW Tokenomist trial 30-90d；v5.8 §M4 Sprint 8 active Y2 Q2-Q3 trial 必已 expire；operator 在 Sprint 6-7 必 evaluate Tokenomist paid subscription 或 fallback（Token Unlocks / Messari / 自建 unlock calendar）；§8 工時加 Sprint 6-7 dependency note。

---

## 4. v5.8 派發前 must-fix（8 項）

### M1（CRITICAL ↔ Risk 1）
1. **§M13 Y2 enable 措辭 → Y3+ at earliest + capital ladder Y2 末措辭修正**（CRITICAL，spec edit）— 修正 v5.8 文檔 §M13 + §5 capital tier ladder；operator 拍板 override OR keep
2. **ADR-0040 AssetClass + Venue interface stub 必明 reserve Binance trade Y3+ at earliest**（HIGH，Sprint 1A-δ work）

### M12（HIGH ↔ Risk 2）
3. **Sprint 1A-β M12 OrderRouter trait 必含 maker_fill_rate_30d metric**（HIGH，interface design）
4. **ADR-0039 必含 routing_decisions audit log schema + per-strategy maker fill rate threshold**（HIGH，Sprint 1A-β work）
5. **字典 ref handbook §1 加 PostOnly maker fill rate SOP 章節**（MED，BB1 sub-agent Sprint 1A 期內並行）

### M11（HIGH ↔ Risk 3）
6. **Sprint 1A-β M11 ADR-0038 必明：nightly replay 用 PG `market.liquidations` table (自家累積) 為 historical source，不依賴 Bybit historical liquidations API（不存在）**（HIGH，Sprint 1A-β work）
7. **M11 funding history Asset rate group 5 req/s coordinator 設計**（MED，Sprint 3 IMPL 前 spec 即須明）

### M9 A/B test（MED）
8. **ADR-0037 必明文：A/B test 只在 OpenClaw self-trade；Copy Trading follower 永遠拿 control variant**（MED，Sprint 1A-γ work）

---

## 5. Sprint 1A-β-ε 期間 should-fix（5 項）

1. **M4 Tokenomist trial expiry must-fix**（Sprint 6-7 trigger）— operator 必 evaluate paid subscription / fallback vendor；§8 工時加 Sprint 6-7 dependency note。

2. **M2 macro overlay auto-redeem rate coordination**（Sprint 9-10 IMPL 前）— M11 nightly replay + M2 auto-redeem 在 Asset group 5 req/s 需 coordinator；用 priority queue 或 exponential backoff retry pattern。

3. **Bybit Pro Trader tier 不申 + 不需申 確認**（Sprint 5 IMPL 前）— v5.8 §M12 / §M13 / §M10 IMPL 前確認 OpenClaw rate limit 估算 always assumes standard tier（不假設 Pro tier 升級）。Y3+ AUM > $100k 仍不達 $10M Pro tier 門檻。

4. **M13 Y3+ Binance trade onboarding 程序評估**（Y1 末 spec）— operator 地理 / KYC / API key 申請 / IP whitelist / non-withdraw scope 全套 Bybit-mirror 設計；ADR-0041 Sprint 10 / Y1 末 出 draft。

5. **M9 manual A/B test Sprint 7-8 啟用**（Sprint 4 read-only logging → Sprint 7-8 manual A/B → Y2 auto-gate）— Sprint 1A schema 設計時即考慮 audit log + treatment / control 標記 + 不影響 Copy Trading follower。

---

## 6. v5.8 完整 verdict

- **GO-WITH-CONDITIONS**
- 8 項 must-fix（M1 + M12×3 + M11×2 + M9×1 + 字典×1）必補
- 5 項 should-fix 在 Sprint 1A-β-ε 期內 schedule
- 0 ship-stop blocker
- 0 hard boundary 違反（修正 M13 措辭後）
- 0 ToS 違反（M4 / M9 / Copy Trading 均合規）
- Bybit rate limit standard tier 充足（無需申 Pro Trader）
- Binance Y2 enable trade 須 operator 拍板 override Product Boundary，否則維持 Y3+

**Sprint 1A-β-ε 派發前最終必收**：
1. §M13 措辭修正 + ADR-0040 reserve Y3+
2. M12 OrderRouter trait maker_fill_rate metric + ADR-0039 audit log
3. M11 ADR-0038 PG liquidations as historical source
4. M9 ADR-0037 fair execution audit log clause
5. M4 Tokenomist trial expiry Sprint 6-7 decision deadline

---

**BB AUDIT DONE**: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v58_executability_audit.md
