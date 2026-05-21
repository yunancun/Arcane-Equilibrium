# v5.7 Dispatch-Safe Patch 執行性審核 — BB 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.7 修了 6 個 v5.6 邏輯漏，但 Bybit 整合面有 4 個 must-fix 在 Sprint 1A 派發前必補（含 §6 liquidation writer 與字典 + 8a-C1 BLOCKED state 直接矛盾、§4 Earn API 在 ref handbook 無對應 endpoint、§8 options recorder 工時 underestimate、§4 Earn 資產移動可能觸發 withdraw permission gate）。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：§6 Liquidation Writer claim 與字典 + 8a-C1 BLOCKED state 直接矛盾

- **嚴重度**：CRITICAL
- **位置**：v5.7 §6（"Healthcheck/extend existing writer, not new build"；"30k+ rows in DB"）
- **描述**：
  - v5.7 §6 寫「`market.liquidations` writer 已在 production 運行 30k+ rows」
  - **字典 ref handbook line 1088 + 1092**（2026-05-15 W-AUDIT-8a C1 note）：「`liquidation.{symbol}` 已於 2026-04-05 移除避免 handler-not-found 毒化整條 WS 連線」「`allLiquidation.{symbol}` 隔離 24h BB proof + MIT schema mapping sign-off **前**，禁止恢復 production 訂閱」
  - **字典 line 1105**：`MarketDataMsg::Liquidation` + `flush_liquidations` writer + `extended_subscription_list` 2026-04-06 已一併清除；`market.liquidations` 表保留為 **reserved-for-future**（即空表）
  - **8a-C1 plan**（`docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md` §Verdict）：`C1 remains BLOCKED until a 24h isolated WebSocket proof passes`；2026-05-15 19:53 才啟動 isolated 24h proof，**production 訂閱列表至今未恢復**
  - 代碼面 `market_writer.rs` 仍有 `flush_liquidations` + `MarketDataMsg::Liquidation` validator + tests（line 333-475），但 `ws_client/dispatch.rs` + `main_ws.rs` 的 `allLiquidation` handler 對接到 production `full_subscription_list` 的 path 未完成（C0 guard 仍 forbidding `allLiquidation*`）
  - **結論**：「30k+ rows in DB」是**事實錯誤**。`market.liquidations` 表 2026-04-05 之後不再 ingestion；30k 若有，是 2026-04-05 之前的舊資料（reserved 期間），不是 v5.7 §6 假設的「正在 production 運行的 writer」
- **為何屬「執行性」（非邏輯）**：邏輯思路（重用而非重建）正確；錯在事實核驗 — v5.6 / v5.7 reviewer 沒交叉查字典 + 8a-C1 BLOCKED state；造成 Sprint 1A scope 嚴重低估（healthcheck 假設變成 unblock C1 + revive writer + 重做 schema mapping）
- **Must-fix 建議**：
  1. Sprint 1A scope 修為「等 8a-C1 24h proof 結果（已於 2026-05-15 19:53 啟動，預計 2026-05-16 19:53 結束）+ MIT schema mapping sign-off」；不能假設 writer 已 healthy
  2. 工時補估：8a-C1 unblock + parser revive + writer mapping + `LiquidationPulseProvider` in-memory 60s buffer + healthcheck = +30~50 hr（不是「-15~20 hr engineering save」，**應為 +30~50 hr 新增工時**）
  3. 若 8a-C1 24h proof FAIL → §6 整段重寫，sub-plan A：BB MD-only DEX scrape；sub-plan B：drop liquidation cascade signal feature；不能 ship Sprint 1A 假設

### Risk 2：§4 Bybit Earn API 在 ref handbook **無對應 endpoint**，工時 + 可行性雙未驗

- **嚴重度**：HIGH
- **位置**：v5.7 §4（"Bybit API query for current tiered APR at each rebalance decision"；"Earn API integration: ~15 hr"；"Manual stake initially; auto after proven"）
- **描述**：
  - 字典 ref handbook `grep -i earn|stake|redeem|savings|flexible` 結果：**0 entries**
  - 最接近的是 `spot-lever-token/purchase` + `spot-lever-token/redeem`（line 953） — 但這是**槓桿代幣**（leveraged token），不是 Earn flexible savings
  - Bybit V5 公開 API doc 中 Earn / flexible savings / on-chain staking 的 programmatic stake/redeem **不是公開 endpoint**；通常只有 read-only 的 product info（如 `GET /v5/asset/coin-info`）+ 用戶必須走 Bybit Web UI / App stake；部分 institutional 用戶有 private endpoint 但需 BD 申請
  - v5.7 §4 寫「Bybit API query for current tiered APR」**未驗 endpoint 是否存在**；「first 3 months manual stake, auto after proven」假設未來會接 programmatic stake API，但 endpoint 可能不公開
  - 字典 line 1255 顯示 `/v5/asset/*` 在 Asset rate limit group **5 req/s**（最嚴）— 即使 Earn endpoint 存在，rate 也最低
- **為何屬「執行性」（非邏輯）**：思路（dynamic APR + governance）正確；錯在沒查 Bybit Earn 是否有 API 接口。若沒有 → Sprint 1A `Bybit Earn API APR recorder (read-only, no stake yet)` 直接 dead，整個 §4 governance design 改為「Web UI manual operator」（不能 programmatic）
- **Must-fix 建議**：
  1. Sprint 1A 派發前先驗 Bybit Earn API 公開 endpoint 是否存在：
     - 命令：`curl -s 'https://api.bybit.com/v5/asset/coin-info' | jq` + Bybit V5 doc grep `earn|flexible|savings`
     - 或直接問 Bybit BD（operator level）
  2. 若 endpoint 不存在 → §4 改為「manual stake operator-only forever；read APR 改 Bybit Web scrape 或 Tokenomist 替代」
  3. 若 endpoint 存在但需 institutional onboarding → §4 標 `[BLOCKED on Bybit BD]`，Sprint 1A scope 移除 Earn live，Sprint 1B 也不能上 Earn
  4. 字典必更新：若 endpoint 存在 → ref handbook 加 `/v5/earn/*` 章節 + 列入 Asset rate limit group

### Risk 3：§4 Earn 資產移動潛在踩 API key withdraw permission gate

- **嚴重度**：HIGH
- **位置**：v5.7 §4（"Asset movement governance"；"stake intent → guardian → execute → audit log"；"Auto-redeem trigger: trading margin headroom < 30%"）
- **描述**：
  - `CLAUDE.md` Hard Boundaries：API key withdraw permission **永遠 false**（架構級硬規）+ D1d「API no withdraw permission」
  - Bybit Earn 的 stake / redeem 是否需要 withdraw permission（即 `wallet`/`asset` scope 是否足夠 vs 需 `withdraw`）**未驗**：
    - 從 spot wallet → Earn product = `transfer` scope（內部轉帳 = 不需 withdraw）— 推測但未驗
    - Earn 內部 stake / redeem 操作 scope = 不確定
    - 跨 sub-account（master → sub）資產移動 = `transfer` scope（不需 withdraw）— 字典 line 832 `POST /v5/asset/transfer/inter-transfer` 已記錄
  - 若 Earn stake/redeem 需要 `withdraw` scope → 整個 §4 governance design **fundamentally infeasible**（OpenClaw 永遠不開 withdraw）
  - v5.7 §4 假設「Guardian-checked = 風險 envelope 等同 trading」 — 但 governance 不能解決 permission scope 缺失
- **為何屬「執行性」（非邏輯）**：governance design 邏輯正確（Decision Lease + audit log）；錯在 permission scope 未驗
- **Must-fix 建議**：
  1. Sprint 1A 派發前驗 Bybit Earn stake/redeem 所需 API key scope
  2. 若需 `withdraw` → §4 整段重寫為「100% manual Bybit Web UI operator-only；OpenClaw 只 read APR + 提建議；不接 stake/redeem programmatic」
  3. 若 `transfer` scope 足夠 → 加註明：「stake/redeem 不過 withdraw gate，但仍需 Guardian + Decision Lease」+ `learning.earn_movement_log` 表加 `api_scope_used` column 留證據

---

## 2. Hours sanity check（Bybit 整合工時 vs estimate）

| §  | v5.7 estimate | BB-真實 estimate | 差異 |
|---|---|---|---|
| §4 Earn API integration | 15 hr | **不可知**（先驗 endpoint）；若公開 30~40 hr；若 BD 申請 +waiting 2-6 weeks | -15hr (delete) 或 +15~25 hr |
| §4 Governance + Decision Lease | 20 hr | 20~30 hr（合理；Decision Lease 已有 retrofit pattern V028/V030） | ±5 hr |
| §4 Audit log schema + writer | 10 hr | 10 hr（已有 writer pattern） | 0 |
| §6 Liquidation writer 「healthcheck/extend」 | -15~20 hr（節省） | **+30~50 hr**（unblock 8a-C1 + parser revive + writer mapping + buffer + healthcheck） | **+45~70 hr 反向偏差** |
| §8 Sprint 1A Options chain recorder NEW | 列為 60-80 hr 一部分（未拆） | options REST/WS 字典已有 `/v5/market/option/*`（line 247-265）但 OpenClaw **沒有 options 既有訂閱**；5min poll BTC+ETH 全鏈（~30-50 contracts × Greeks/IV/OI）→ 25~40 hr（schema + writer + dispatch + healthcheck） | +25~40 hr 顯化 |
| §8 Sprint 1A Binance market-data-only WebSocket NEW | 列為 60-80 hr 一部分 | Binance 公開 WS（無 auth）：connection + reconnect + parser + schema mapping to internal Rust types = 25~35 hr；Sprint 1A 列 NEW 合理 | ±5 hr |
| §8 Sprint 1A Tokenomist trial integration | 列為 60-80 hr 一部分 | 第三方 API（外部 vendor）：onboarding + key + rate limit + scrape + schema = 15~25 hr | ±5 hr |

**Sprint 1A 60~80 hr 真實估算**：若 §6 修為 **+30~50 hr** 反向 + §4 endpoint 不存在風險 + options recorder + Binance WS + Tokenomist + macro feed + Earn 基線 = **真實 90~130 hr**

**結論**：v5.7 Sprint 1A 60~80 hr 整體 underestimated **約 30~50%**（不致命；可吸收 Sprint 1B → 1A 滑動）。

---

## 3. 未識別的依賴 / 阻塞（Bybit ToS / API endpoint / rate limit）

### D1：Master Trader subaccount 啟用流程（v5.6 §10 evidence gate）

- v5.6 §10 列 4-gate（alpha + moat + operator + Bybit-side），其中 Bybit-side gate 含「Cadet tier qualified」
- Bybit Cadet tier 要求（snapshot 2026-04，verify 以官方為準）：90d 連續 P&L 或 100k+ ROI；個人帳戶 + KYC tier 2
- v5.6 §10 沒列 90d 連續 P&L 必須在 **同一 sub-account** 上累積 — OpenClaw 主帳 self-trading 90d 不能直接 transfer 給 Master Trader sub（兩者獨立計分）
- **Must-fix 建議**：Sprint 9 末 evidence gate review 時 BB 必驗：(a) sub-account 已開 + Cadet tier 已申 + 90d 計分窗口開始；(b) self-trading 績效不能 transfer 到 Master Trader 評分；(c) Bybit BD 可能要求 KYC tier 2 + 影片面審

### D2：Binance market data 用 ToS

- v5.6 D1a + v5.7 D12「Binance market data Y1, trading Y2 review」
- Binance V5 公開 WS（`wss://fstream.binance.com/ws/...`）**不需 auth + 不需 API key + ToS 上允許 read-only feed**（個人 + 非營利用途）
- **但**：Binance V5 公開 doc 允許 read-only 但「不得**轉售**或公開重新發布」— OpenClaw 內部使用 + counterfactual 屬合規範圍；若未來 Copy Trading 公開 follower → Binance feed 可能不能用於對外展示
- **Must-fix 建議**：v5.7 §8 加註：「Binance MD 限 OpenClaw 內部分析 + counterfactual；Copy Trading follower-facing display 前先過 Binance ToS review」

### D3：Tokenomist 第三方數據合規 + API rate limit

- v5.7 §8 Sprint 1A NEW「Tokenomist unlock calendar」
- Tokenomist 是付費 / 試用 vendor；ToS + Free tier rate limit 需先核：
  - 是否允許 programmatic scrape vs 僅 Web UI
  - Trial 後付費門檻（影響 Sprint 後續）
  - Data freshness（unlock event T-7d / T-3d / T-0 需確認）
- **Must-fix 建議**：Sprint 1A 派發前 operator 申 Tokenomist trial + 確認 ToS + rate limit；不能 dispatch 假設「Tokenomist trial 一定通」

### D4：Order group rate limit 共享 quota 不變

- 字典 line 1241（2026-05-16 EDGE-P2-3 Phase 1b BB-SF-1 補錄）：`/v5/order/*` 在 20 req/s shared quota；create + cancel + cancel-all + amend + batch 全在內
- v5.7 §8 Sprint 1A 加新 Bybit options polling 5min + Binance WS（不影響 Bybit order quota）+ funding rate aggregator extend → 不會增加 order group 用量
- 但 **C10 funding harvest live deploy（Sprint 1B）**：long spot + short perp + quarterly rebalance ≈ 2 orders/quarter / pair × 5 symbols → 不會觸 rate
- **無 must-fix**；BB advisory：Order group 餘裕充足，新增 options polling 在 Market group（120 req/s）

### D5：Bybit Demo Endpoint Earn / Lever-Token / Spot Margin 支援

- 字典 line 719：demo + live_demo validate against `https://api-demo.bybit.com`；live validate against `https://api.bybit.com`
- **Bybit demo doc** 明文「not a complete function」（字典 line 1333 W-AUDIT EDGE-P2-3 Phase 1b BB-MF-5 補錄）
- v5.7 §4 Earn 在 **哪個 endpoint 部署**未指定：
  - Live env Earn = 真實資金（high stake）
  - Demo env Earn = **大概率不存在**（demo 一向是 partial mock）
  - LiveDemo（demo endpoint with live-grade control）= 也不存在
- **Must-fix 建議**：Sprint 1A 派發前驗 `api-demo.bybit.com` 是否支援 Earn endpoint；若 demo 不支援 → §4 governance manual stake 只能 live 上做 → 風險顯著抬升 + 須 Phase 5 LiveDemo / Mainnet gate

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **§6 liquidation writer claim FACTUAL ERROR**：8a-C1 BLOCKED + production 訂閱不含 `allLiquidation.*`；30k+ rows 是 2026-04-05 之前舊資料；Sprint 1A scope 反向 +30~50 hr 不是節省。**PA dispatch 必先 wait 8a-C1 24h proof verdict（2026-05-16 結束）**。
2. **§4 Bybit Earn API endpoint 存在性未驗**：字典 0 entries；Sprint 1A 派發前 operator + BB 共同驗 endpoint；不存在則 §4 整段 fallback 為「Web UI manual + read scrape」。
3. **§4 Earn 資產移動 API key withdraw permission 風險**：若需 `withdraw` scope → 違 D1d + `CLAUDE.md` Hard Boundaries → §4 fundamentally infeasible programmatic；先驗 scope 才能 sign §4。

---

## 5. Sprint 1A 派發前 must-fix

1. **§6 等 8a-C1 24h proof verdict + MIT schema mapping sign-off**（2026-05-16 19:53 之後評估）— 不能 dispatch 假設 writer 已 healthy
2. **§4 驗 Bybit Earn API endpoint 是否公開存在**（grep V5 doc + curl probe + 可能需 Bybit BD 詢問）
3. **§4 驗 Earn stake/redeem 所需 API key scope**（必須非 `withdraw` 才可 programmatic；否則改 manual Web UI）
4. **§8 Tokenomist trial onboarding + ToS confirm**（programmatic scrape 是否允；rate limit；trial 後付費門檻）
5. **§8 options chain recorder schema review**：字典已有 `/v5/market/option/*`，但內部 schema mapping（contract / strike / DTE / IV / Greeks / OI）必須 Sprint 1A 內 MIT sign + writer pattern aligned
6. **工時校正**：Sprint 1A 60~80 hr → **90~130 hr 真實**；operator 確認 buffer 或拆更小 chunk
7. **§4 driver endpoint 環境決策**：Live vs Demo vs LiveDemo — 若 demo 不支援 Earn → §4 live 上做需 Phase 5 LiveDemo / Mainnet gate 全套

---

## 6. Sprint 1B-3 should-fix

- **Sprint 1B C10 minimal viable on 主帳 $2,000**：BB advisory — Bybit demo 不支援 spot lending（已記字典 §九） → 「long spot + short perp」delta-neutral 在 demo 不可行；C10 Sprint 1B 上線必 Live env，但 8a-C1 + Earn endpoint 未解 → C10 Sprint 1B 可能 wait
- **Sprint 2 alpha tournament**：Unlock SHORT 24mo event study 需 Tokenomist 真實 data → 若 Tokenomist trial 失敗 → Sprint 2 部分阻塞
- **Sprint 3 macro overlay activation**：Sprint 3 才接 macro 但 Sprint 1A 已建 macro calendar feed → 1A 建好之後 1B/2 wait 直到 3 整合，feed 期間 dormant 不影響
- **Sprint 4 C13 Options Stack Phase 1**：Sprint 1A 已建 options recorder（5min poll），Sprint 4 加 REST + WS client + Greeks/IV/OI struct → BB advisory：Bybit options WS 是 `wss://stream.bybit.com/v5/public/option`（與 linear/spot 分開），訂閱 + auth + 心跳 + parsing pattern 全新；Sprint 4 工時 160~210 hr 看似充足但 options micro 複雜度高
- **Sprint 6 funding short-only build**：BB advisory — funding 短倉策略歷史結案 NEGATIVE（G-2 -36.76 bps / 0勝率），項目 memory 已 deprecate path；v5.7 Sprint 6 再列必先過 QC 重評三參數 + EDGE-DIAG-2 樣本

---

## 7. 可優化 / 拆分 / 並行

1. **§4 Earn endpoint 驗證可外移至 D-1 派發前**（operator + BB 1 hr probe），不影響 Sprint 1A 啟動
2. **§6 8a-C1 24h proof 2026-05-16 19:53 結束**：BB + MIT 立即 review；若 PASS → Sprint 1A §6 healthcheck path 可派；若 FAIL → §6 整段 fallback design 並行設計（不阻塞其他 1A 部分）
3. **§8 Sprint 1A 拆 5 並行 track**（已合理拆）：(a) governance + migration（V103/V104） / (b) liquidation healthcheck（wait 8a-C1） / (c) options recorder NEW / (d) Tokenomist + macro feed / (e) Binance WS + Earn read-only — 互不阻塞，PA 可派 5 sub-agent
4. **§9 engineering total 1,190-1,590 hr**：Sprint 4 peak 160-210 hr 太集中（C13 options + Top-2 build + Top-1 live），建議拆 Sprint 3.5 緩衝 1 week
5. **§4 Earn governance Decision Lease**：與 LG-3 Decision Lease retrofit pattern V028/V030/V031/V032/V034 對齊（已有 migration pattern）；可重用 — 不需新建

---

**BB 立場 final**：v5.7 邏輯思路（dispatch-safe + 6 corrections + Sprint split）正確；事實核驗不足（liquidation writer + Earn API + scope + ToS）。Sprint 1A 派發前必修 7 個 must-fix；修完後 GO，不修則 HOLD。Sprint 1B-10 should-fix 不阻塞 dispatch 但需 PM 追蹤。

**BB AUDIT DONE**: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_executability_audit.md
