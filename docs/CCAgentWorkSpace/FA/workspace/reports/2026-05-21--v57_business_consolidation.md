# v5.7 Dispatch-Safe Patch — FA 業務功能規劃匯總
**日期**：2026-05-21
**Verdict**：BUSINESS-NEEDS-FIX
**One-line summary**：v5.7 thesis 與 6 個 reviewer 修復通過 FA 業務視角審查，但 5 strategy acceptance criteria / Stage gate / Earn governance 三條業務鏈未閉合，跨 14 agent 共識 11 個 must-fix（含 ADR 號碼衝突、TODO hard precondition 未解除、liquidation writer 事實錯誤、C10 demo 不可行、Sprint 1B 跳 Stage gate）；business-ready 條件 = 派發前完成 11 個 must-fix + 收口 5 strategy entry/exit 業務規格 + 統一 v5.6/v5.7 矛盾。

---

## 0. 14 份審核 business angle 匯總

### FA 自己第一輪 verdict
GO-WITH-CONDITIONS — 5 strategy acceptance 4 PARTIAL / 2 MISSING；Stage gate 全外掛 AMD-2026-05-15-01；Earn governance "manual initially" vs "auto-redeem trigger" 內部矛盾。

### 與其他 13 agent 共識

| 共識點 | 認可 agent 數 | 共識結論 |
|---|---|---|
| Thesis + 6 reviewer fix 邏輯通過 | 14/14 | v5.7 邏輯層通過所有審查 |
| Sprint 1A 60-80 hr 嚴重低估 | 11/14 (FA / A3 / AI-E / BB / CC / E2 / E3 / E4 / E5 / MIT / QA / QC / TW) | 真實 90-150 hr，差 30-50% |
| V103/V104 schema 為 placeholder 不可派 | 7/14 (FA / E2 / CC / MIT / E4 / R4 / TW) | 派發前必須先寫 schema spec |
| Earn governance 5-gate boundary 未明文 | 6/14 (FA / CC / E3 / QA / E2 / BB) | live_reserved / OPENCLAW_ALLOW_MAINNET / authorization.json 是否適用未定 |
| ADR-0028/0029 號碼衝突 | 4/14 (R4 / TW / CC / E2) | 已被 close-maker / trade tape storage 占用 |
| Counterfactual evaluation t-stat threshold 缺失 | 4/14 (FA / CC / MIT / QA) | "+2%" 怎麼算未定 |
| C10 demo 不可行（Bybit demo 不支援 spot lending）| 3/14 (BB / QC / FA) | Sprint 1B C10 minimal viable 路徑需重定 |
| Liquidation writer §6 事實錯誤 | 2/14 (BB / E2) | 30k+ rows 是 2026-04-05 之前舊資料；C1 BLOCKED |
| Sprint 1B C10 跳過 Stage 1-3 直 live | 1/14 (QA) | 違反 v5.6 §12 governance |
| 工時 5-10x underestimate 系統性 | 1/14 (E5) | 1190-1590 hr 應重估為 3570-4770 hr |
| GUI 工時缺失 ~104-151 hr | 1/14 (A3) | Earn stake form / Allocator viewer / Counterfactual dashboard |
| LLM API budget 缺失 | 1/14 (AI-E) | ~$365-565/yr 未列 |
| TW doc 工時缺失 ~68-95 hr | 1/14 (TW) | ADR draft / runbook / SCRIPT_INDEX |
| 測試 / SLA / 1e-4 容差規劃缺失 | 1/14 (E4) | ~100-150 hr 測試工時被吞 |

### 業務鏈核心 gap（FA 視角綜合）

1. **5 strategy 從 thesis 到代碼之間缺最小 acceptance criteria 表**（FA Round 1 標 4 PARTIAL / 2 MISSING；QC 驗 4/5 樣本量未驗證）
2. **Stage gate 業務 PASS/FAIL 全部外掛 AMD-2026-05-15-01**（FA Round 1 + QA 共識）
3. **Earn governance 業務鏈未閉合**（5 hard gate 適用範圍 + manual vs auto-redeem 內部矛盾 + ADR-0030 number 衝突 + Bybit Earn API endpoint 未驗 + demo 是否支援未驗）
4. **C10 Sprint 1B 業務路徑斷裂**（demo 不支援 spot lending + 直 live 違反 Stage gate + Earn $800 與 C10 spot $2,000 資金路徑衝突）
5. **Counterfactual logging 業務邊界 Y1 vs Y2 未鎖**（"+2%" 統計顯著性閾值缺；macro/on-chain Y1 vs v5.6 §6 Sprint 3 macro overlay activation 直接衝突）

---

## 1. Sprint 1A 業務鏈完整度

| 工作鏈 | 業務輸出 | 端到端閉合 |
|---|---|---|
| **governance amend（ADR-0006/0030/0031/0032）** | 邊界明文：Bybit primary + Binance MD only + DEX 不允；Earn asset write 受 Guardian + Decision Lease + 5-gate | **否** — ADR-0028/0029 號碼衝突；ADR-0006 amendment 無對應文件；ADR-0024-lite 命名漂移；AMD-01..05 命名漂移 |
| **V### migration（V097/V098/V103/V104）** | hypotheses + hypothesis_preregistration + trading.fills.track + earn_movement_log 4 表落地，pre-registration framework 可被 Sprint 2 Alpha Tournament 使用 | **否** — V103/V104 schema 為 placeholder（無 column list / type / Guard / index）；與 V101 trading.fills.track 字段衝突未解；PG dry-run mandatory 規範未寫入 dispatch brief |
| **Tier 0 sensor（liquidation healthcheck + options chain + Tokenomist + macro feed + Binance perp WS + Earn APR recorder）** | 6 個數據源接通；macro/on-chain Y1 counterfactual logging 起步；options chain 為 Sprint 4 C13 預收 6-9 mo 歷史 | **部分** — liquidation writer §6 事實錯誤（C1 BLOCKED 至 2026-05-16 24h proof 結果出爐）；Tokenomist trial license + ToS 未確認；Binance perp WS ADR-0006 amendment pending；Bybit options API access + KYC tier 未確認；外部 sensor secret slot 治理未明文 |
| **Earn API（read-only APR recorder）** | Bybit Earn API tier APR 每 rebalance query；Sprint 1B governance policy + first stake $200-400 之 prerequisite | **否** — Bybit Earn v5 REST endpoint 在 docs/references/2026-04-04--bybit_api_reference.md **0 hit**；API key scope（withdraw vs transfer）未驗；demo endpoint 是否支援 Earn 未驗 |
| **C10 prep（Sprint 1B 啟動 prerequisite）** | Sprint 1B minimal viable 在主帳 $2,000 部署 | **否** — demo 不支援 spot lending → Stage 1-3 demo 灰度不可行；Sprint 1B 直 live 違反 v5.6 §12 governance；C10 spot $2,000 與 Earn $800 USDT 資金路徑衝突 |

**端到端閉合？否（5/5 全部未閉合）**

理由：5 工作鏈每條都有 1-3 個 must-fix；任何一條不收口 Sprint 1A 無法派 PA。

---

## 2. 5 strategy acceptance criteria 完整化計畫

### C10 funding harvest（PARTIAL → CLEAR）— Sprint 1B 派發前完成

- **入場條件**：BTCUSDT funding rate annualized > 5%（per FA Round 1 Risk 3 + QC backtest），spot 流動性 OI > $X USDT
- **size formula**：spot leg = min($2,000, 80% of available margin headroom) × 1.0；perp short leg = matched notional with 1:1 hedge ratio
- **平倉條件**：funding annualized < 2%（OR）spot-perp basis drift > 0.5% absolute（OR）operator manual halt
- **rebalance 觸發**：quarterly（calendar trigger）OR delta drift > 2% from neutral
- **異常退出**：D2 portfolio loss $2,500 trip / Bybit Earn product withdrawal trigger auto-redeem / Stage 4 → Stage 0R demotion / Bybit API 連續 5 retCode != 0
- **C10 vs Earn 資金路徑解**：C10 spot $2,000 先到位（從 trading wallet 直接 spot buy），剩餘 trading wallet 餘額餘 $4,700 - C13 reserve $1,500 - Unlock $1,500 = $1,700；Earn $800 從這 $1,700 抽離；先 spot deploy 後 Earn stake，per 「先底層 strategy 後 yield enhancement」業務序

### Unlock SHORT（PARTIAL → CLEAR）— Sprint 3 派發前完成（W8-11）

- **入場條件**：Tokenomist unlock event T-3d（日曆日不交易日）AND unlock value > $5M（避免噪音）AND funding rate < 0.05%/8h（避免擁擠）
- **macro state 在 Y1 不觸發**：per v5.7 §5 counterfactual-only Y1；v5.6 §6 Sprint 3 「Multi-condition triggers (T-3d + microstructure + funding state + macro state)」**作廢 macro state 條件**，only T-3d + microstructure + funding state
- **size formula**：position = min(unlock_value × 0.001, $1,500 × 0.5)；max single position $750
- **入場路徑**：Stage 4 LIVE 後限價 short perp
- **平倉條件**：T+3d（unlock event 後 3 日交易日）OR price 從入場 +5%（stop loss）OR -10%（take profit）
- **異常退出**：Sharpe < 0.5 over 15 events → strategy retire；Tokenomist API down > 24h → halt new entry；funding rate flip > 0.1%/8h → close existing
- **樣本量驗收**：Sprint 2 Alpha Tournament must 提交 SSRN 24mo event study N ≥ 30 unlock events，post-2020 vs post-2024 sub-period stability test PASS

### Pairs trading（MISSING → CLEAR）— Sprint 5 派發前完成（W16-19）

- **pair 選擇**：BTC/ETH（Phase 1），ETH/SOL（Phase 2 dependent on Phase 1）；非 stable 不選；非 perp 不選
- **cointegration test**：Engle-Granger 15m + 1h timeframe rolling 30d window，t-stat ≤ -2.86 PASS；2020-2026 sub-period stability ≥ 70% 通過
- **z-score 入場**：z-score > 2.0 short overpriced + long underpriced；hedge ratio 用 rolling 30d OLS β
- **z-score 平倉**：z-score within ±0.5 close（mean reversion 完成）
- **max holding period**：5d，超時無條件 close（cointegration breakdown 保護）
- **correlation breakdown 退出**：30d rolling correlation < 0.6 → halt new entry + close existing
- **異常退出**：Sharpe < 0.5 over 30 trades → strategy retire；single pair drawdown > 20% → pair-level kill

### C13 defined-risk put spread（PARTIAL → CLEAR）— Sprint 6 派發前完成（W20-23）

- **default mode entry**：short put @ 8-12% OTM + long put @ 15-20% OTM；strike 選擇 = 用 IV smile midpoint 算 expected slippage 後選 delta -0.20 / -0.10 strike pair
- **DTE 範圍**：7-21 day（避免 0DTE volatility + 避免 > 30DTE 流動性問題）
- **contract size**：position notional = $1,500 / max_loss_per_spread；典型 = 1-3 contracts
- **roll 條件**：DTE < 3d AND short strike not breached → roll same delta 14d out
- **advanced naked put 觸發 4-confluence**：（a）IV-RV gap > 15 vol points（Bybit BTC options 過去 12mo distribution > 90th percentile）AND（b）BTC 30d return > +5% AND（c）cash buffer ≥ 2× potential assignment value AND（d）portfolio margin headroom > 50%；4/4 全達才 naked
- **異常退出**：portfolio margin headroom < 30% → halt new；short put 履約價 breached → defined-risk 自動觸 max loss exit；Sharpe < 0.5 over 20 spreads → strategy retire
- **業務 prerequisite**：Bybit options demo 是否支援 sign-off（BB Sprint 1A 必驗）；Bybit options 過去 12-24mo IV-RV gap empirical distribution 已收集

### Funding short-only（MISSING → CLEAR）— Sprint 6 派發前完成（W20-23）

- **high-threshold 定義**：annualized funding rate > 30%（即 8h funding rate > 0.082%）AND symbol 24h volume > $50M USDT
- **與 C10 業務隔離**：C10 是 funding 正常區間（5-15% annualized）long spot + short perp delta-neutral；Funding short-only 是 funding 極端區間（> 30% annualized）pure short perp（無 spot leg），無 delta neutral；同一 symbol 同時觸發兩條件時 funding short-only 優先（C10 暫退出該 symbol）
- **size formula**：position = min($700 × 0.4, $50M × 0.0001)；max single position $280
- **入場路徑**：限價 short perp（PostOnly maker）
- **平倉條件**：funding annualized < 20%（normalize）OR funding flip 負（funding 反轉）OR T+2d 強制平倉
- **異常退出**：Sharpe < 0.5 over 15 events → retire；funding short-only events < 30/yr → power 不足，sample size 不夠 → re-evaluate Sprint 8 retire
- **memory G-2 結案 NEGATIVE 校驗**：v2 n=13 -36.76 bps / 0勝率 → v5.7 變體與 G-2 應為不同設計（high-threshold 而非 baseline）；Sprint 2 Alpha Tournament 必複現 historical N events count 並做 power analysis

---

## 3. Stage gate 業務規格化計畫

**業務規格 inline 化原則**：v5.7 patch v5.8 應 inline 抄 AMD-2026-05-15-01 對應條文 5-10 行；不再純外掛文件。

### Stage 0R Replay Preflight

- **業務 PASS 條件**：strategy 對 30d 歷史 fill 路徑做 replay；attribution_chain_ok 100%；replay 計算的 PnL 與 historical fills PnL 偏離 < 1%（允許 fees / slippage drift）
- **業務 FAIL 條件**：replay 計算與 historical fills 偏離 > 5%；attribution_chain_ok < 95%；strategy module 啟動失敗 / panic / 連續 3 cycle 無 decision emit
- **業務 acceptance**：replay 數據窗口 = 30d；replay PASS 後 strategy entry Stage 1 Demo Micro-Canary；FAIL → strategy retire 或 重新 build

### Stage 1 Demo Micro-Canary

- **業務 PASS 條件**：1 strategy × 1 symbol × 7d real fills（demo env）；fills 數 ≥ 5；attribution_chain_ok 100%；無 panic；無 P0 risk envelope breach；7d 內 cumulative PnL ≥ -0.5% capital（允許小幅 drawdown）
- **業務 FAIL 條件**：fills < 5（樣本太少）；attribution_chain_ok < 100%；P0 breach；7d cumulative PnL < -2% capital
- **rollback 流程**：Stage 1 FAIL → strategy demote to SHADOW；engineer debug；24h cooldown；resubmit Stage 0R
- **size**：fixed micro，per strategy capital × 5%（C10 = $100；Unlock SHORT = $75；Pairs = $50；C13 = $75；Funding short = $35）

### Stage 2 Demo Extended（14d）

- **業務 PASS**：fills 數 ≥ 15；Sharpe > 0.5（diagnostic only，非 promote gate）；attribution_chain_ok 100%；P0 breach 0；P1 breach ≤ 1
- **業務 FAIL**：fills < 15；attribution_chain_ok < 100%；P0 breach ≥ 1；P1 breach ≥ 3；14d cumulative PnL < -3% capital
- **size**：Stage 1 × 2，per strategy capital × 10%

### Stage 3 Demo Full（21d）

- **業務 PASS**：fills 數 ≥ 30（QC 要求 t-stat power 0.8 minimum）；attribution_chain_ok 100%；MIN_SAMPLES per strategy 達標 200（per Sprint N+0 closure ml_training cron weekday gate）；P0/P1 breach 全 0
- **業務 FAIL**：fills < 30；attribution_chain_ok < 100%；MIN_SAMPLES < 200；P0/P1 breach ≥ 1
- **size**：Stage 2 × 2，per strategy capital × 25%

### Stage 4 Live Pending

- **業務 PASS**：operator approval（Console 點按） + 5-gate boundary PASS（live_reserved=true / Operator role auth / OPENCLAW_ALLOW_MAINNET=1 / valid secret slot / signed authorization.json with env_allowed match）
- **業務 FAIL**：5-gate 任一缺 → 拒絕；operator override 無效
- **size**：Stage 3 × 4，per strategy capital × 100%（即 strategy 完整 capital）
- **異常自動降回 Demo**：portfolio cum loss > $2,500 → 全策略 demote to Stage 3 demo；single strategy 7d Sharpe < -1.0 → 該 strategy demote to Stage 3
- **Live size 起始額**：C10 $500 initial（per v5.6 §7 Sprint 4 line）；Unlock $500；Pairs $300；C13 $500；Funding short $200
- **Live 階段觀察期**：90d 連續 P&L track 才視為「mature」strategy（與 v5.6 §10 Copy Trading 4-gate 之「90+ days live」一致）

---

## 4. Earn governance 業務鏈閉合

### v5.7 §4 矛盾解
- **First 3 months（Sprint 1B-3）**：100% manual stake AND manual redeem；auto-redeem trigger **disabled**
- **After operator sign-off（Sprint 4+ earliest）**：auto-redeem trigger enabled；先要求 90d operator 觀察 + ADR-0030 從 Proposed → Accepted

### 業務 flow（manual mode Sprint 1B-3）

```
1. Operator → Console (governance tab → Earn sub-section) stake form
   - 輸入 amount ($200-$400 first stake)
   - 系統顯示 current tier APR（Bybit API real-time）
   - 系統顯示 Guardian policy 預檢結果
   - operator 打字確認「I authorize Earn stake $X」（modal Lv 3）
   
2. Frontend → IntentProcessor.submit_intent(
      intent_type='earn_stake',
      amount=X,
      direction='stake',
      symbol='USDT'
   )
   
3. IntentProcessor → DecisionLease.acquire(lease_type='earn_stake', ttl=30s)
   - 5-gate 檢查：live_reserved / Operator role / OPENCLAW_ALLOW_MAINNET / secret slot / authorization.json env_allowed includes 'earn-write'
   - 任一 fail → reject + audit log
   
4. DecisionLease → Guardian.check_risk_envelope(
      operation='earn_stake',
      amount=X,
      portfolio_margin_state=current
   )
   - Guardian 確認 stake 後 trading account margin headroom ≥ 50%
   
5. Guardian PASS → BybitRestClient.earn_stake(amount=X, product='USDT-flexible')
   - retCode != 0 → fail-closed（不重試）→ audit log → operator 通知
   - retCode == 0 → 繼續
   
6. learning.earn_movement_log INSERT
   - columns: ts, direction='stake', amount=X, apr_at_time=apr, decision_lease_id, guardian_envelope_hash, bybit_ret_code, account_balance_before, account_balance_after
   
7. Daily reconciliation cron (02:00 UTC)
   - GET /v5/asset/wallet-balance + GET /v5/earn/balance
   - 比對 learning.earn_movement_log cumulative
   - diff > 0.01 USDT → audit log warn + disable Earn stake/redeem 48h until manual review
```

### 失敗 fail-closed 鏈
- Bybit retCode != 0 → 不重試 → audit log → operator notification（Console toast + LINE）
- DecisionLease acquire fail → reject + audit log
- Guardian fail → reject + audit log
- Daily reconciliation fail → auto-disable Earn stake/redeem 48h until manual review

### Bybit Earn API surface 待驗（BB Sprint 1A 派發前 must-fix）
- v5 REST 是否提供 stake / redeem / tier APR query endpoint
- API key scope 是否需要 `withdraw`（如需則 Earn 整段 fallback 為 manual Web UI only）
- demo endpoint 是否支援 Earn product（影響 Sprint 1B first stake 是否能 demo 灰度）

### ADR-0030（rename Earn governance）內容
- 業務目標：USDT idle cash → Bybit Earn flexible savings；4-8% baseline + tier 1 promotional 10% first $200
- 5-gate 適用範圍：4/5 適用（OPENCLAW_ALLOW_MAINNET 不適用，因 Earn 用同一 Bybit endpoint demo + live）
- Decision Lease lease_type='earn_stake' / 'earn_redeem' 新增
- audit table learning.earn_movement_log append-only（V103/V104 之一）
- daily reconciliation 失敗 → 48h disable
- 替代降級路徑：如 Bybit Earn API 不公開 → Console only Web UI manual operator + read-only APR scrape

---

## 5. Counterfactual logging 業務邊界

### Y1 模式（Sprint 1A → Sprint 10）

- **read-only logging**：macro events + on-chain signals + strategy decisions 三向 log 到 learning.counterfactual_log（V103/V104 之衍生 spec missing - MIT must-fix）
- **A/B counterfactual computation**：對每 strategy 每 decision，計算「if macro/on-chain overlay applied」vs「actual decision」的 hypothetical PnL delta
- **不觸發 strategy**：Y1 期間 counterfactual layer 100% read-only，不修改 strategy entry/exit/size
- **不計入 Y1 income**：per v5.7 §1 honest recompute，macro = $0 + on-chain = $0
- **訪問控制**：counterfactual_log schema 不含 strategy decision raw payload（只含 macro/on-chain raw value + outcome aggregate delta）；GUI viewer 角色禁讀；Copy Trading export pipeline reject counterfactual_log join

### Y1 末 evaluation（Sprint 10 W36-39）

- **業務 PASS 條件 → Y2 enable**：
  - macro overlay：counterfactual_uplift_bps avg ≥ +200bps (i.e., +2%) over ≥ 3 strategies AND t-stat ≥ 1.5 AND minimum sample 30+ macro events
  - on-chain signals：counterfactual_uplift_bps avg ≥ +100bps over ≥ 3 strategies AND t-stat ≥ 1.5 AND minimum sample 60+ on-chain events
- **業務 FAIL → retire layer**：
  - t-stat < 1.0 OR uplift_bps < +50bps → retire
  - 1.0 ≤ t-stat < 1.5 → defer 3 months re-evaluate
- **memorialize**：retire 後寫 `docs/archive/2026-XX-XX--macro_overlay_retired.md` + ADR amendment

### Y2 enable 業務 flow（Sprint 11+ earliest）

- 獨立 governance proposal：ADR-0034（新號）「Macro / On-chain overlay Y2 activation」
- ADR-0024-lite 修訂（若 Tier 5 LLM-assisted hypothesis 涉及）
- operator sign-off（Console approve）
- 進入 Stage 0R replay preflight（用 overlay-enabled strategy 對 historical 數據 replay）→ Stage 1 → Stage 2 → Stage 3 → Stage 4 Live

---

## 6. 5 策略 × Stage gate 矩陣

| Strategy \ Stage | 0R Replay Preflight | 1 Demo Micro-Canary 7d | 2 Demo Extended 14d | 3 Demo Full 21d | 4 LIVE |
|---|---|---|---|---|---|
| **C10 funding harvest** | replay 30d historical funding harvest fills；attribution_chain_ok=100%；PnL 偏離 < 1% | fills ≥ 5；7d cum PnL ≥ -0.5%；P0 breach=0；size $100；**spot leg paper-only**（demo 不支援 spot lending）| fills ≥ 15；Sharpe > 0.5；size $200 | fills ≥ 30；MIN_SAMPLES ≥ 200；size $500 | 5-gate PASS + operator approve；size $2,000 initial |
| **Unlock SHORT** | replay 24mo unlock events；event sample N ≥ 30；post-2020 sub-period stability PASS | fills ≥ 3 unlock events；7d cum PnL ≥ -0.5%；size $75 | fills ≥ 6 events；Sharpe > 0.5；size $150 | fills ≥ 12 events；Sharpe > 1.0；size $375 | 5-gate PASS；size $1,500 initial $500 |
| **Pairs trading** | replay 30d BTC/ETH pair；cointegration t-stat ≤ -2.86；rolling 30d stability ≥ 70% | fills ≥ 5 round-trip trades；7d cum PnL ≥ -0.5%；size $50 | fills ≥ 12 trades；Sharpe > 0.5；size $100 | fills ≥ 24 trades；MIN_SAMPLES ≥ 200；size $250 | 5-gate PASS；size $1,000 initial $300 |
| **C13 defined-risk** | replay 12mo Bybit BTC options put spreads；IV-RV gap distribution sampled；Bybit options demo support 確認 | fills ≥ 2 spreads；7d cum PnL ≥ -0.5%；size $75 | fills ≥ 5 spreads；Sharpe > 0.5；size $150 | fills ≥ 10 spreads；MIN_SAMPLES ≥ 200；size $375 | 5-gate PASS；size $1,500 initial $500 |
| **Funding short-only** | replay 24mo high-threshold funding events；N ≥ 30 events / yr 驗證；power analysis ≥ 0.5 | fills ≥ 2 events；7d cum PnL ≥ -0.5%；size $35 | fills ≥ 5 events；Sharpe > 0.5；size $70 | fills ≥ 10 events；Sharpe > 1.0；size $175 | 5-gate PASS；size $700 initial $200 |

---

## 7. 資金路徑流圖

```
$10,000 total
├─ off-exchange $2,500 (D1c: bot 不碰銀行)
│  ├─ Revolut EUR/USD $1,500 — 3-4% interest
│  └─ Wise multi-currency $1,000 — 3-4% interest
│
└─ Bybit $7,500 (Bybit primary D1a)
   │
   ├─ Bybit Earn (USDT savings, governance-controlled) $800
   │  └─ tiered APR Bybit API real-time query
   │     ├─ first $200 @ ~10% tier 1 (introductory verify QC must-fix)
   │     └─ remaining $600 @ ~3% tier 2
   │  業務鏈：Operator → Console (governance/earn) → 
   │           IntentProcessor.submit_intent(earn_stake) → 
   │           DecisionLease(earn_stake, 5-gate exc. mainnet) →
   │           Guardian.check_risk_envelope →
   │           BybitRestClient.earn_stake →
   │           learning.earn_movement_log →
   │           Daily reconciliation cron 02:00 UTC
   │
   ├─ C10 funding harvest $2,000 (spot+perp delta-neutral)
   │  ├─ spot leg long $2,000 BTCUSDT (DEMO PAPER-ONLY, LIVE 後啟用)
   │  └─ perp leg short $2,000 BTCUSDT (matched notional)
   │
   ├─ Unlock SHORT $1,500 (perp-only event-driven)
   │  └─ Tokenomist T-3d signal + microstructure + funding state（no macro Y1）
   │
   ├─ Pairs trading $1,000 (perp-perp market-neutral)
   │  ├─ BTC/ETH Phase 1
   │  └─ ETH/SOL Phase 2 (depend on Phase 1 evidence)
   │
   ├─ C13 defined-risk put spread $1,500
   │  └─ default put spread 8-12% / 15-20% OTM
   │     + advanced naked (4-confluence gated)
   │
   └─ Funding short-only $700
      └─ high-threshold > 30% annualized funding (rare events)

啟動順序（Sprint timeline）：
W0-1.5 Sprint 1A    : governance + V### + sensor + Earn API recorder (read-only)
W1.5-3 Sprint 1B 末 : Earn $200-400 first manual stake + C10 BTCUSDT minimal viable $2,000 (DEMO Stage 1)
                       (FA must-fix: C10 demo spot 用 paper-only leg; live spot 等 Sprint 4)
W8-11 Sprint 3      : Top-1 strategy (likely Unlock SHORT) build + Stage 0 shadow + counterfactual logger 上線
W12-15 Sprint 4     : Unlock SHORT Stage 1-3 完成 Stage 4 LIVE $500;
                       Top-2 (Pairs 或 Funding short) build + Stage 0 shadow;
                       C13 Options Stack Phase 1 build start;
                       Auto-redeem trigger 啟用評估（earliest）
W16-19 Sprint 5     : Top-2 Stage 4 LIVE; Top-3 build; C13 Phase 2
W20-23 Sprint 6     : Top-4 + C13 Stage 1-3; Funding short build
W24-27 Sprint 7     : Top-5 + Advisory Allocator + Live promos
W28+ Sprint 8-10    : Decay + Discovery + Counterfactual evaluation + Y1 Review

Auto-redeem trigger（Sprint 4+ after operator sign-off, ADR-0030 從 Proposed → Accepted）：
- Trading margin headroom < 30% → 自動從 Earn redeem 到 trading account
- Daily reconciliation 失敗 → disable stake/redeem 48h until manual review
- Bybit Earn product 撤回（exchange-side announce）→ 自動 redeem 全部
```

---

## 8. v5.6 → v5.7 殘留矛盾清單

1. **v5.6 §6/§7 Sprint 3 "Macro overlay activation for active strategies" vs v5.7 §5 "counterfactual only Y1"** → Sprint 3 改為「Macro counterfactual logger activation」；不接 strategy trigger
2. **v5.6 §6 "Stage 0 shadow Sharpe > 1.0 → Sprint 4 promotion" vs v5.6 §12 "NO paper Sharpe gates / Shadow is diagnostic only"** → 統一為 shadow diagnostic + Stage 0R replay preflight gate；Sharpe gate 不 promotion，replay PASS 才 promotion
3. **Unlock SHORT v5.6 §6 "Multi-condition triggers (T-3d + microstructure + funding state + macro state)" vs v5.7 §5 "macro state Y1 counterfactual only"** → Unlock SHORT 在 Y1 不能用 macro state trigger；只用 T-3d + microstructure + funding state
4. **v5.6 §2 Earn $800 "USDT savings 4-8% APR" vs v5.7 §1 tiered APR 計算（first $200 @ 10%, remaining @ 3%）** → v5.6 4-8% 描述 deprecate；v5.7 tiered APR 為準
5. **v5.6 §2 capital structure 與 v5.7 §1 calendar-weighted income 對齊性** → capital structure 不變（$2k C10 + $1.5k Unlock + $1k Pairs + $1.5k C13 + $700 Funding short + $800 Earn）；income 重算 v5.7 為準
6. **ADR-0024-lite 命名漂移（v5.6 §11 + v5.7 §12 都用）** → 實際 ADR-0024 file 為 `0024-cowork-subscription-operator-assistant.md` 不含 "lite"；統一為 ADR-0024（或於該 ADR 補 "lite" 命名 amendment）
7. **AMD-01..05 命名漂移（v5.6 §15 + v5.7 §13）** → 統一為 AMD-2026-05-20-01..05 + 標 AMD-2026-05-20-05 retract
8. **ADR-0028/0029 提案號衝突** → ADR-0028 已被 close-maker / ADR-0029 已被 trade tape storage 占用；v5.7 §12 三 ADR 順移 ADR-0030/0031/0032，或 PA dispatch 時 final 鎖定 0030+
9. **v5.7 §11 "14 hard problems from rounds 12-15" 無 audit trail** → 改為「6 hard problems from round 15」或補 round 12-14 audit log path（R4 must-fix）
10. **v5.7 主檔位置 `srv/2026-05-20--*.md` 不在 `docs/execution_plan/`** → 違反 docs/README.md §強制規則；搬到 `docs/execution_plan/2026-05-20--execution-plan-v5.7.md`（R4 must-fix）
11. **v5.6 §7 Sprint 1B "C10 minimal viable on 主帳 $2,000" vs v5.7 §8 + QA gap "Sprint 1B 直 live 違反 Stage gate"** → Sprint 1B 改為 C10 Stage 1 Demo Micro-Canary 啟動（spot leg paper-only），live 真實時間落 Sprint 4
12. **v5.6 §7 Sprint 9 "Auto-Allocator activation" vs v5.7 §7 "Auto-Allocator defer to Y2"** → v5.7 為準；v5.6 Sprint 9 「Auto-Allocator activation」deprecate；Sprint 9-10 為「Continue Advisory Allocator」+「Copy Trading Infra build」
13. **v5.7 §1 與 §2 Y2 income range 內部不一致** → §2 $850-1,150 vs §10 $850-1,050；overlay verified §2 $1,043-1,097 vs §10 $1,050-1,250；統一 single anchor `Y2 honest no-overlay: $850-1,050 median $935; Y2 overlay verified: $1,040-1,100 median $1,070`（QC must-fix）
14. **TODO §-0 Hard precondition "路線敲定前不啟動 V101/V102 / dispatch wave" vs v5.7 §11 "Sprint 1A ready for PA dispatch"** → operator 在 TODO §-0 填入 v5.7 為路線 + 解除 V101/V102 Hard precondition（R4 + E2 must-fix）

---

## 9. 跨語言保留 / 刪除分類

| Module | Language Ownership | Sprint | LOC est | 保留 / 新建 |
|---|---|---|---|---|
| Earn API client (Bybit /v5/earn) | Python (Bybit SDK extension) | 1A-1B | ~300 | 新建（前提 BB 驗 endpoint）|
| Earn governance (IntentProcessor extension lease_type='earn_stake') | Python | 1B | ~200 | 擴展既有 IntentProcessor |
| Earn audit log writer (learning.earn_movement_log) | Python | 1B | ~100 | 新建 |
| Earn manual stake GUI (governance tab sub-section) | Vanilla JS (E1a) | 1B | ~150 | 新建（A3 must-fix 8-12 hr）|
| Earn auto-redeem trigger | Python | 4+ | ~150 | 新建（Sprint 4 啟用評估後）|
| Bybit options chain recorder | Rust | 1A | ~400 | 新建（zero baseline）|
| Binance perp WS client | Rust | 1A | ~300 | 新建（zero baseline 但 ADR-0006 amend pending）|
| Macro calendar feed | Python | 1A | ~250 | 新建（FRED API or trading-economics vendor 待選）|
| Tokenomist unlock calendar | Python | 1A | ~200 | 新建（trial license 待確認）|
| market.liquidations writer healthcheck | Rust (existing) | 1A | minor | 保留（已 30k+ rows，但 C1 BLOCKED 至 2026-05-16 24h proof）|
| funding rate aggregator healthcheck | Rust (existing) | 1A | minor | 保留 |
| Counterfactual logger (macro) | Python | 2 | ~400 | 新建（layer 1 自動 5-min snapshot, AI-E memory must-fix）|
| Counterfactual logger (on-chain) | Python | 2 | ~500 | 新建（free tier rate limit 預算需 BB 審）|
| C10 funding harvest strategy | Rust | 1B + 4 | ~500 | 新建（spot leg DEMO paper-only Phase 1）|
| Unlock SHORT strategy | Rust | 3 | ~400 | 新建 |
| Pairs trading | Rust | 5 | ~600 | 新建 |
| C13 defined-risk | Rust + Python | 6 | ~800 | 新建（Phase 1 600 LOC + Phase 2 600 LOC 拆 4 module）|
| Funding short-only | Rust | 6 | ~300 | 新建 |
| Advisory Allocator | Python | 7 | ~400 | 新建 |
| Allocator monthly proposal viewer GUI | Vanilla JS (E1a) | 7 | ~200 | 新建（A3 must-fix 20-30 hr）|
| Decay Detector | Python | 8 | ~300 | 新建 |
| Discovery Pipeline | Python | 8 | ~400 | 新建 |
| Multi-strategy aggregate dashboard | Vanilla JS (E1a) | 5-6 | ~250 | 新建（A3 must-fix 25-35 hr）|
| Counterfactual A/B viewer GUI | Vanilla JS (E1a) | 8 | ~150 | 新建（A3 must-fix 15-20 hr）|
| Copy Trading infrastructure | Python | 9 | ~600 | 新建（build only, not enable; Y2 evidence-gated）|
| V103 hypotheses + hypothesis_preregistration | sqlx migration | 1A | ~150 | 新建（schema spec 缺；MIT must-fix）|
| V104 trading.fills.track | sqlx migration | 1A | ~80 | 新建（可能與 V101 同字段衝突，PA dispatch consolidate）|

---

## 10. 業務功能 readiness verdict

### Sprint 1A 派發 business readiness：BUSINESS-NEEDS-FIX

### 業務 must-fix（FA 視角，缺一不派 Sprint 1A）：

1. **V103/V104 schema spec 完整 column list / type / Guard / index / engine_mode CHECK** — 對應 `docs/execution_plan/2026-05-21--v103_v104_schema_spec.md`（仿 v101_v102 spec 範式）；MIT + E2 + E4 共識
2. **ADR 號碼順移 + ADR-0006 amendment file 落地 + AMD 命名規範化 + v5.7 主檔搬 docs/execution_plan/** — R4 + TW + CC must-fix；ADR-0030/0031/0032 number 鎖定；ADR-0033 新建 ADR-0006 amend
3. **TODO §-0 操作員填入 v5.7 為路線 + 解除 V101/V102 Hard precondition** — R4 + E2 must-fix；無此 unblock，dispatch 撞 TODO active state
4. **Bybit Earn API endpoint 存在性 + API key scope + demo support 三項驗證** — BB Sprint 1A 派發前 driver 查 Bybit V5 doc + curl probe + 必要時 BD 詢問；若 endpoint 不存在 → §4 整段 fallback 為 Console-only manual + read APR scrape；若 demo 不支援 → Sprint 1B first stake 路徑需 risk 升級
5. **Earn governance 5-gate 適用範圍明文** — v5.7 §4 加 「Earn 沿用 4 gate（live_reserved + Operator role + secret slot + authorization.json env_allowed includes 'earn-write'），OPENCLAW_ALLOW_MAINNET 不適用（demo + live 同 endpoint）」；CC + E3 + QA must-fix
6. **v5.6 §6 Sprint 3 "Macro overlay activation" deprecate → "Macro counterfactual logger activation"** — Unlock SHORT 在 Y1 不能用 macro state trigger；FA + AI-E + CC consensus
7. **8a-C1 liquidation writer 24h proof verdict** — 2026-05-16 19:53 結束的 24h isolated WS proof 結果出爐前不能 dispatch；§6 healthcheck claim 假設「writer 已 healthy」事實錯誤；BB + E2 must-fix
8. **Sprint 1B C10 改為 Stage 1 Demo Micro-Canary（spot leg paper-only），不 live $2,000** — QA + FA + QC consensus；live 真實時間 Sprint 4；違反 Stage gate 是 governance breach
9. **External sensor secret slot 政策明文（Tokenomist trial + Glassnode/Etherscan/DeFiLlama free tier API key）** — E3 must-fix；secret slot path / 過期管理 / fail-closed default / outbound 域名白名單
10. **Counterfactual evaluation t-stat / sample size threshold 定義（"+2% on strategies" 統計顯著性）** — CC + MIT + QC + FA consensus；t-stat ≥ 1.5 + 30+ macro / 60+ on-chain；寫入 v5.7 §5 或新 spec
11. **5 strategy acceptance criteria 草案（C10 完整 / 其餘 Sprint 派發前完成 inline）** — FA must-fix；C10 派 Sprint 1B 前；Unlock 派 Sprint 3 前；Pairs / C13 / Funding short 派各 Sprint 前

### Sprint 1A 派發後業務 should-fix：

1. **Sprint 1A 工時 60-80 hr 上修為 90-130 hr**（E2 + E5 + MIT + QC + TW consensus）
2. **TW 工時 ~68-95 hr 加入 §9 Sprint table**（ADR draft / runbook / SCRIPT_INDEX / MODULE_NOTE）
3. **A3 工時 ~104-151 hr 加入 §9 Sprint table**（5 個 operator-facing GUI surface）
4. **LLM budget ~$365-565/yr 明列**（AI-E must-fix；§9 新增 Est LLM cost USD 欄）
5. **Y2 income range single source of truth in §2，§10 cite**（QC must-fix；統一為 $850-1,050 / $1,040-1,100）
6. **Sprint 1A baseline profiling task**（E5 + E4 should-fix；H0/tick/IPC P50/P95/P99 + RAM/CPU/PG buffer baseline）
7. **Linux PG empirical dry-run mandatory 規範寫入 dispatch brief**（MIT + E4 + CC must-fix）
8. **Earn runbook `docs/runbooks/earn_governance_manual_stake_sop.md`**（TW must-fix；Sprint 1A 末 land draft）
9. **5 strategy × Stage gate 矩陣寫入 v5.7 §12 或 appendix**（FA must-fix）

### 派發後 30 day 內業務 chain 閉環時間表：

- **W0-1.5（Sprint 1A）**：上述 11 個 must-fix 全 land；governance amend（ADR-0030/0031/0032/0033） + V103/V104 schema spec + sensor 6 sub-track 並行 + Earn API APR read-only 接通 + Linux PG empirical dry-run 完成
- **W1.5-3（Sprint 1B）**：C10 Stage 1 Demo Micro-Canary（spot leg paper-only） + Earn first manual stake $200-400 + Alpha Tournament dataset readiness check
- **W4-7（Sprint 2）**：5 strategy Alpha Tournament evidence rebuild（5 sub-agent QC + MIT 並行）+ on-chain counterfactual setup + microstructure feature library + pre-registration table seeded with verified hypotheses
- **W8-11（Sprint 3）**：Top-1 strategy（likely Unlock SHORT）build + Stage 0 shadow + macro counterfactual logger 開始記錄
- **W12-15（Sprint 4）**：Unlock SHORT Stage 1-4 全程完成 → LIVE $500；Top-2 build start；C13 Options Stack Phase 1；Auto-redeem trigger 啟用評估（earliest）
