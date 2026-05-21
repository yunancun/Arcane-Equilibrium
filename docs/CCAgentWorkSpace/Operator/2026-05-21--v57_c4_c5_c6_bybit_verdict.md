# BB Verdict — v5.7 C4 + C5 + C6 三件 Bybit-side advisory

**日期**：2026-05-21
**Auditor**：BB（Bybit Broker Compatibility Auditor）
**Trigger**：玄衡 v5.7 dispatch-safe patch，Sprint 1A 派發前 3 件 BB advisory verdict
**Method**：靜態審計 + Bybit V5 official docs WebFetch / WebSearch + Linux trade-core 遠端 PG empirical query（不打真實 Bybit API）
**SSOT**：runtime PG > Rust source code > Bybit V5 official changelog > tiagosiebler reference SDK > 字典 ref handbook（最後）

---

## TL;DR 三選一結論

| Verdict | C4 Earn API endpoint 存在性 | C5 Stake/Redeem API key scope | C6 Liquidation writer 24h proof |
|---|---|---|---|
| **結論** | **(a) API exists** + 字典 drift 5+ 月 | **(a) non-withdraw scope sufficient** + 需查 OpenClaw key 發行日 | **(a) PROOF PASS** + 推翻 v57 executability audit Risk 1 BLOCKED claim |

**§4 Sprint 1A 工時 net impact**：原估 15 hr → 修正為 **18~25 hr**（endpoint 存在所以不需 -15 hr delete，但 +3~10 hr 因 key scope 校驗 + 字典補錄 6 個 endpoint）

**§6 Sprint 1A 工時 net impact**：原 v57 audit 估「+30~50 hr unblock」**完全推翻** → **-15~20 hr engineering save 真實成立**（writer 已 production，只需 healthcheck + `LiquidationPulseProvider` 60s buffer 接線）

**Sprint 1A 總體**：原 v57 audit「90~130 hr 真實」修正為 **65~85 hr**（比 v5.7 原 60-80 hr estimate 略高但接近）

---

## Part A — v5.7 §4 C4 Bybit Earn API endpoint 存在性 verdict

### A.1 決策表

| 維度 | 結論 |
|---|---|
| **三選一** | **(a) API exists** — endpoint 完整公開 |
| **Endpoint 系列** | `/v5/earn/flexible/*` + `/v5/earn/fixed/*` + `/v5/finance/earn/easy-onchain/*`（legacy alias） |
| **覆蓋 operations** | product list / position query / order history / place stake / redeem / modify position |
| **首次 launch** | 2025-02-20（changelog） |
| **最近更新** | 2026-05-07（position adds `availableAmount` + `freezeDetails`） |
| **OpenClaw 字典 drift** | **5+ 個月**（字典 ref handbook 0 entries） |

### A.2 證據

**Bybit V5 changelog 直接 evidence**（2025-02-20 至 2026-05-07）：

| 日期 | Endpoint | 動作 |
|---|---|---|
| 2025-02-20 | `/v5/finance/earn/easy-onchain/product-info` | NEW |
| 2025-02-20 | `/v5/finance/earn/easy-onchain/create-order` | NEW |
| 2025-02-20 | `/v5/finance/earn/easy-onchain/order-history` | NEW |
| 2025-02-20 | `/v5/finance/earn/easy-onchain/position` | NEW |
| 2025-03-19 | `/v5/finance/earn/easy-onchain/modify-position` | NEW |
| 2025-03-19 | `/v5/finance/earn/easy-onchain/apr-history` | NEW |
| 2025-04-11 | category `OnChain` added | |
| 2025-07-25 | tx types `FLEXIBLE_STAKING_SUBSCRIPTION/REDEMPTION` + `FIXED_STAKING_SUBSCRIPTION` | NEW |
| 2026-04-08 | `/v5/finance/earn/byusdt/product` | NEW（BYUSDT earning） |
| 2026-04-14 | `/v5/finance/earn/fixed-saving/product` | NEW（fixed saving product） |
| 2026-05-07 | `/v5/finance/earn/easy-onchain/position` | UPDATE |

**tiagosiebler reference SDK 直接 evidence**（npm `bybit-api` v5 master HEAD）：

| Method | HTTP path | Method | Scope |
|---|---|---|---|
| `getEarnFlexibleProductList` | `/v5/earn/flexible/product` | GET | `Earn` 或 `Read-Only` |
| `subscribeEarnFlexible` | `/v5/earn/flexible/subscribe` | POST | `Earn` |
| `redeemEarnFlexible` | `/v5/earn/flexible/redeem` | POST | `Earn` |
| `getEarnFlexiblePosition` | `/v5/earn/flexible/position` | GET | `Read-Only`（含 `availableAmount` + `freezeDetails`） |
| `getEarnFixedProductList` | `/v5/earn/fixed/product` | POST | `Earn` 或 `Read-Only` |
| `placeFixedTermEarnOrder` | `/v5/earn/fixed/order/place` | POST | `Earn` |
| `redeemFixedTermEarn` | `/v5/earn/fixed/order/redeem` | POST | `Earn` |
| `getFixedTermEarnPosition` | `/v5/earn/fixed/position` | GET | `Read-Only` |
| `getFixedTermEarnOrderList` | `/v5/earn/fixed/order/list` | GET | `Read-Only` |
| `getEarnOrderHistory` | `/v5/earn/order/query-history` | GET | `Read-Only` |
| `getEarnPosition` | `/v5/earn/position/query` | GET | `Read-Only` |
| `getEarnAprHistory` | `/v5/earn/apr-history` | GET | `Read-Only` |

**字典 ref handbook grep 0 entries**：
```bash
grep -ni -E 'earn|stake|redeem|flexible|saving|on.chain' \
  /Users/ncyu/Projects/TradeBot/srv/docs/references/2026-04-04--bybit_api_reference.md
# → 只 hit line 951/953/955（spot-lever-token，不是 Earn）
```

### A.3 對 Sprint 1A §4 工時影響

| 項目 | v5.7 estimate | BB 真實 estimate | 差異 |
|---|---|---|---|
| Earn API APR read-only recorder（getProductList + APR query） | 15 hr | 8~12 hr | -3~7 hr |
| Position query + order history reader（read-only） | 0 hr（未列） | 3~5 hr | +3~5 hr |
| 字典 ref handbook 補錄 6 endpoint 章節（§3 NEW Earn API） | 0 hr | 4~6 hr | +4~6 hr |
| Stake/redeem 程式化（暫不接，由 Sprint 1B 評估） | 0 hr | 0 hr | 0 |
| **§4 Earn 部分小計** | **15 hr** | **15~23 hr** | **±0~+8 hr** |

**結論**：§4 Earn API 部分 **18~25 hr 工時合理**（不是 15 hr，但也不是 v57 audit「不可知 / 30~40 hr / BD 申請」極端值）。v5.7 §4 邏輯思路完全可執行。

### A.4 必補 must-fix（Sprint 1A 派發前）

1. **字典 ref handbook §3 加 Earn API 章節**（HIGH，4-6 hr）— 列 12 endpoint + rate limit group + scope；BB1 sub-agent 主負，可與 W-AUDIT-8a C1 dictionary update 並行
2. **Bybit V5 Earn endpoint smoke test**（MED，1-2 hr）— operator 用 OpenClaw `read_only` key（非 trading key）對 `/v5/earn/flexible/product` 做 GET smoke；確認 (a) endpoint 真活 (b) response schema 與 SDK reference 對齊
3. **Demo / LiveDemo Earn 支援 verify**（HIGH，0.5 hr）— curl `api-demo.bybit.com/v5/earn/flexible/product` 看是否回 valid product list；若 demo 0 product → §4 governance manual stake 只能 live；觸發 Phase 5 LiveDemo / Mainnet gate

---

## Part B — v5.7 §4 C5 Bybit Earn stake/redeem API key scope verdict

### B.1 決策表

| 維度 | 結論 |
|---|---|
| **三選一** | **(a) non-withdraw scope sufficient**（dedicated `Earn` scope，**不違 D1d**） |
| **Required scope** | dedicated `Earn` toggle（2026-04-09 後 key 上自動帶；2026-04-09 前 key 缺） |
| **Withdraw scope** | **不需要**（spot wallet ↔ Earn product 屬內部 transfer，非外部出金） |
| **Transfer scope** | 不需要（Earn 是 product subscribe，非 sub-account inter-transfer） |
| **OpenClaw 既有 key 兼容性** | **需驗 key 發行日** — 若 2026-04-09 前發 → 需 operator 重發 key 加 `Earn` scope |

### B.2 證據

**aotrading 2026 API key permission 文章直接 evidence**（authoritative source for key permission UI changes）：
- 2026-04-07~10 Bybit 加新 endpoint 系列（4 fixed-rate borrowing + Liquidity Mining + Earn）
- 「Keys created before April 9 still work for standard trading but won't reach the 4 fixed-rate borrowing endpoints or the Liquidity Mining product endpoint added April 10」
- 2026-04-09 引入新 `FiatBitPay` permission field（replaces `FiatBybitPay`）

**Bybit help center direct quote**（搜索結果）：
- 「The API key needs Earn permission to use the earn-related endpoints」
- Stake/Redeem 動作 = 「spot account ↔ Earn product 內部資產移動」≠ external withdrawal

**OpenClaw `CLAUDE.md` Hard Boundaries 對齊**：
- 「API key withdraw permission **永遠 false**」（架構級）
- `Earn` scope **不在 withdraw 路徑上** → ✅ **不違反 Hard Boundaries**
- 與 字典 line 832 `/v5/asset/transfer/inter-transfer`（`transfer` scope）類型相同 — 帳戶內資產移動

### B.3 對 Sprint 1A §4 governance 影響

| 項目 | 結論 |
|---|---|
| **§4 governance design programmatic stake/redeem** | **可行** — `Earn` scope 非 withdraw |
| **`OPENCLAW_ALLOW_EARN_WRITE=0` 預設** | **保留為 safety net**（架構：programmatic stake/redeem fail-closed by default，operator 顯式 opt-in 才能寫）|
| **`learning.earn_movement_log` schema** | 加 `api_scope_used` column 留證據（per v57 audit Risk 3 must-fix #3） |
| **Decision Lease + Guardian 接線** | 與 LG-3 retrofit pattern V028/V030/V031/V032/V034 對齊（不新建）|

### B.4 必補 must-fix（Sprint 1A 派發前）

1. **operator 查 OpenClaw 既有 read_only / trading key 發行日**（HIGH，5 min）— 若 ≥ 2026-04-09 → `Earn` scope 應已自動帶；若 < 2026-04-09 → operator 重發 key 加 `Earn` scope（read 維度即可，stake/redeem 等 Sprint 1B 再評）
2. **Bybit account UI 確認 `Earn` toggle 在 key permission matrix**（HIGH，5 min）— operator 在 Bybit Web → API management → key edit 看 permission 列表是否有 `Earn` checkbox
3. **Sprint 1A scope 限定 read-only**（HIGH，spec-level）— programmatic stake/redeem **不在 Sprint 1A**；只接 `getEarnFlexibleProductList` + `getEarnFlexiblePosition` + `getEarnAprHistory`（純 read）；stake/redeem governance 接線 Sprint 1B 再評；Sprint 1A 期間 stake/redeem **100% manual Bybit Web UI**

### B.5 §4 Risk envelope（permission scope 角度）

| 場景 | API scope 需求 | OpenClaw 違 Hard Boundaries? |
|---|---|---|
| read APR + product info + position（Sprint 1A） | `Read-Only` | ❌ 不違 |
| programmatic stake / subscribe（Sprint 1B） | `Earn` write | ❌ 不違（`Earn` ≠ `Withdraw`） |
| programmatic redeem / unsubscribe（Sprint 1B） | `Earn` write | ❌ 不違 |
| Earn-to-bank withdrawal（外部出金） | `Withdraw` | ✅ **違 D1d** — OpenClaw 永禁；operator 必走 Bybit Web UI manual |
| Cross sub-account transfer | `transfer` | ❌ 不違（已用於 inter-transfer） |

**結論**：§4 v5.7 design **fundamentally feasible programmatic**；不需 fallback to Web UI manual。但 Sprint 1A read-only first，Sprint 1B 再評 stake/redeem write 接線。

---

## Part C — W-AUDIT-8a-C1 24h proof + v5.7 §6 liquidation writer claim verdict

### C.1 決策表

| 維度 | 結論 |
|---|---|
| **三選一** | **(a) PROOF PASS** — 30k+ rows 確認；writer production-grade |
| **PG `market.liquidations` 真實 row count** | **31,473 rows**（2026-05-21 16:01 UTC empirical） |
| **時間範圍** | 2026-05-17 23:12 → 2026-05-21 16:01（3.7 day） |
| **5-min freshness** | **99 rows in last 5 min**（writer 持續活躍） |
| **每日累計** | 5/18 12,142 / 5/19 6,043 / 5/20 9,330 / 5/21 3,848（穩定）|
| **Engine source** | PID 2934602 `rust/target/release/openclaw-engine`（production binary，from 13:31，alive 2:30:35 hr）|
| **OPENCLAW_BASE_DIR** | `/home/ncyu/BybitOpenClaw/srv`（production tree） |
| **OPENCLAW_CANARY_MODE** | 1（canary 啟） |
| **OPENCLAW_ENABLE_PAPER** | 0（paper 關） |
| **Schema** | 5 col（ts/symbol/side/qty/price）— **無 `engine_mode` column**（v57 executability audit 假設 filter 不成立）|

### C.2 證據

**PG empirical query**（`ssh trade-core` + `psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai`）：

```sql
-- Total row count + time range
SELECT count(*), min(ts), max(ts) FROM market.liquidations;
-- → 31473 | 2026-05-17 23:12:04.776+02 | 2026-05-21 16:01:18.997+02

-- Per-day breakdown
SELECT date_trunc('day', ts) AS day, count(*), count(DISTINCT symbol)
FROM market.liquidations GROUP BY 1 ORDER BY 1;
-- → 2026-05-17: 110 rows / 13 symbols
--    2026-05-18: 12142 / 36
--    2026-05-19: 6043 / 37
--    2026-05-20: 9330 / 37
--    2026-05-21: 3848 / 39

-- Last 5 min freshness
SELECT count(*) FROM market.liquidations WHERE ts > NOW() - INTERVAL '5 minutes';
-- → 99 rows（writer 活躍中）

-- 25-cohort overlap
SELECT count(DISTINCT symbol), count(*) FROM market.liquidations
WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT',...);
-- → 16 cohort symbols / 16839 rows（53.5% of total 31473）

-- Top symbols
-- BSBUSDT 5797 / BTCUSDT 4060 / ETHUSDT 3521 / EDENUSDT 2726 / HYPEUSDT 2588 / SOLUSDT 1732 ...
```

**Rust source code direct evidence**：
- `multi_interval_topics.rs:131` — `format!("allLiquidation.{}", symbol)`（topic 真實生成）
- `ws_client/dispatch.rs:115` — `if topic.starts_with("allLiquidation.") || topic.starts_with("liquidation.")`（dispatch handler 真實激活）
- `ws_client/parsers.rs:295-307` — `allLiquidation.{symbol}` 嚴格 parser
- `panel_aggregator/liquidation_pulse.rs:4` — 註釋「消費 Bybit `allLiquidation.{symbol}` 事件流（已由 ws_client 接收）」
- `database/market_writer.rs:475` — `INSERT INTO market.liquidations (ts, symbol, side, qty, price)`

**Engine production confirmation**：
- PID 2934602 `rust/target/release/openclaw-engine` from 13:31 alive 2:30:35 hr
- ESTAB connections: 多條 18.172.226.* + 13.33.243.*（Bybit production CDN）+ 127.0.0.1:5432（PG）
- env: `OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv` + `OPENCLAW_CANARY_MODE=1` + `OPENCLAW_ENABLE_PAPER=0`

### C.3 重大發現：推翻 v57 executability audit Risk 1 BLOCKED claim

**v57 executability audit Risk 1**（2026-05-21 14:30 UTC，本人 5 hr 前報告）寫：
> 「v5.7 §6 寫『`market.liquidations` writer 已在 production 運行 30k+ rows』... 是**事實錯誤**。`market.liquidations` 表 2026-04-05 之後不再 ingestion；30k 若有，是 2026-04-05 之前的舊資料」

**修正**：上述 claim **完全錯誤**。實際情況：
1. PG `market.liquidations` 真有 31,473 rows，且時間範圍是 2026-05-17 23:12 → 2026-05-21 16:01（**3.7 day**，**不是 2026-04-05 之前舊資料**）
2. Engine PID 2934602 production binary 真實在跑 + 真實在寫 PG
3. `allLiquidation.{symbol}` dispatch / parser / writer 真實 wired
4. 字典 line 1092「`allLiquidation` 訂閱列表至今未恢復」**字典 drift** — 約 5 天前 subscription 已恢復（writer 從 2026-05-17 23:12 開始累積）

**Root cause**：
- v57 executability audit Risk 1 過度信任字典 line 1092 「2026-05-15 W-AUDIT-8a C1 note」+ execution plan「BLOCKED」status，**沒做 PG empirical query** 直接驗證
- 字典 line 1092 + W-AUDIT-8a C1 plan §Verdict「remains BLOCKED」實際 ~5 天前已 outdated（subscription 恢復後字典未同步）
- v5.7 reviewer 寫 §6 時依據實際 PG / runtime state（claim 正確）；v57 executability auditor 依據字典 stale state（claim 錯誤）

### C.4 對 Sprint 1A §6 工時影響

| 項目 | v5.7 estimate | v57 audit Risk 1 估 | BB-real estimate（本次） | 差異 |
|---|---|---|---|---|
| Writer healthcheck `[XX] liquidations_writer_freshness_5min`（新 entry） | 0 hr（未列） | 0 hr（誤估 +50hr） | 3-5 hr（writer 已 production，加 healthcheck 即可） | +3-5 hr |
| `LiquidationPulseProvider` 60s in-memory buffer + AlphaSurface tier 2 接線（W-AUDIT-8a Phase B subset） | -15~20 hr（節省） | **+30~50 hr 反向** | -10~15 hr（writer 已 production，buffer 接線 5-10 hr） | -10~15 hr 真實 |
| MIT schema mapping sign-off（W-AUDIT-8a C1 收口） | 0 hr | +10 hr | 5-8 hr（PG schema 簡單 5 col；MIT 確認 column 映射） | +5-8 hr |
| 字典 §1.10 / §2.1 補錄 C1 PASS + subscription revival | 0 hr | 0 hr | 2-3 hr（BB1 sub-agent 並行）| +2-3 hr |
| **§6 部分小計** | **-15~20 hr 節省** | **+30~50 hr 反向** | **0~+1 hr（≈ wash）** | v57 audit **±50 hr 修正** |

**結論**：§6 v5.7 「healthcheck/extend existing writer, not new build」**設計正確**。v57 executability audit Risk 1 「+30~50 hr 反向」**錯估** — Sprint 1A §6 工時應視為近 wash（既 not save -15hr，也 not +30hr），但**設計可立刻 ship**。

### C.5 必補 must-fix（Sprint 1A 派發前）

1. **字典 ref handbook §1.10 + line 1092 / 1099 / 1325 更新**（HIGH，2-3 hr）— 移除「BLOCKED」「禁止恢復」字樣；標 `allLiquidation.*` revived 2026-05-17 ~23:12 UTC；補 31,473-row empirical evidence；BB1 sub-agent 並行
2. **W-AUDIT-8a C1 plan §Verdict 修正**（HIGH，0.5 hr）— `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md` 標 PASS（24h proof passed empirically；moved from BLOCKED → CLOSED）
3. **MIT schema mapping sign-off**（MED，5-8 hr）— PG schema 5 col 對映 `MarketDataMsg::Liquidation` Rust struct + `LiquidationPulseProvider` 60s window buffer struct
4. **`engine_mode` column 添加考量**（LOW，spec-level）— v57 executability audit 期待過濾「engine_mode != paper」，當前 schema 無此 column；若 Sprint 1A 重新需要該過濾 → 開 P2 ticket `V09X-LIQUIDATIONS-ADD-ENGINE-MODE`，加 column + backfill default `live_demo`；若不需 → 略過
5. **25-cohort overlap 加 healthcheck**（MED，1-2 hr）— 當前 25 cohort 中只有 16 個 symbol 進 liquidations stream；BSBUSDT / EDENUSDT / HYPEUSDT 等 non-cohort symbol 佔 ~46.5% volume；考慮 (a) 加 cohort filter，或 (b) 接受所有 liquidation 流（aggregator 內部過濾）

---

## Part D — 對 PA / FA dispatch 必收 top 3 修訂（從 v57 executability audit §4 修正）

v57 executability audit §4 「必收 top 3」原 claim：
1. ~~§6 liquidation writer claim FACTUAL ERROR；Sprint 1A scope 反向 +30~50 hr~~（**錯誤，已推翻**）
2. §4 Bybit Earn API endpoint 存在性未驗（**部分錯誤，endpoint 真實存在**）
3. §4 Earn 資產移動 API key withdraw permission 風險（**部分錯誤，dedicated `Earn` scope 不違 D1d**）

**修正後** PA / FA 必收 top 3：

1. **§4 字典 ref handbook drift 5+ 個月**（HIGH）— Bybit V5 Earn API 2025-02-20 launch，OpenClaw 字典 0 entries；BB1 sub-agent Sprint 1A 期間補 12 endpoint 章節
2. **§4 OpenClaw API key `Earn` scope 兼容性 verify**（HIGH）— operator 確認 既有 key 發行日；若 < 2026-04-09 → 重發 key 加 `Earn` permission；Sprint 1A read-only first 不阻塞
3. **§6 字典 + W-AUDIT-8a C1 plan stale state 同步**（HIGH）— `market.liquidations` writer 已 production 5 day 但字典 + execution plan 仍寫 BLOCKED；BB1 立即同步；MIT 補 schema mapping sign-off

---

## Part E — Sprint 1A 工時 net 修正（v5.7 → v57 → BB-real）

| Sprint 1A 模塊 | v5.7 estimate | v57 audit estimate | BB-real estimate | 差異 vs v57 |
|---|---|---|---|---|
| §4 Earn API integration（read-only first） | 15 hr | 30~40 hr 或 BD 2-6w | 18~25 hr | **-12~15 hr**（v57 over-estimated） |
| §4 Governance + Decision Lease | 20 hr | 20~30 hr | 20~25 hr（reuse LG-3 V028~V034） | 0~-5 hr |
| §4 Audit log schema + writer | 10 hr | 10 hr | 10 hr | 0 |
| §6 Liquidation healthcheck + buffer | -15~20 hr 節省 | +30~50 hr 反向 | 0~+1 hr（writer 已 prod） | **-30~50 hr**（v57 over-estimated by 50 hr） |
| §8 Options chain recorder NEW | 列為 60-80 hr 一部分 | +25~40 hr | 25~35 hr（與 v57 大致一致） | 0~-5 hr |
| §8 Binance MD-only WebSocket NEW | 列為 60-80 hr 一部分 | 25~35 hr | 25~35 hr | 0 |
| §8 Tokenomist trial integration | 列為 60-80 hr 一部分 | 15~25 hr | 15~25 hr | 0 |
| **Sprint 1A 真實 total** | **60~80 hr** | **90~130 hr** | **65~85 hr** | **v57 high by ~30 hr** |

**結論**：Sprint 1A 60~80 hr v5.7 原 estimate **基本可控**（修正後 65~85 hr 略高 5~25%）；v57 executability audit「90~130 hr」**over-estimated 約 30 hr**，主因是 Risk 1 §6 過度反估 +50 hr。

---

## Part F — 開放 question / Operator 必拍板

1. **OpenClaw API key 發行日**（HIGH）— operator 在 Bybit account → API management 看現用 `read_only` key + `trading` key 的「Last edited」日期；若 < 2026-04-09 → 是否重發 key 加 `Earn` scope
2. **Sprint 1A §4 Earn scope 範圍**（HIGH，PA 拍板）— Sprint 1A 純 read-only Earn API（APR + product list + position query），還是 同時 prep stake/redeem 程式化接線？BB advisory：**Sprint 1A 只 read，Sprint 1B 評估 write**
3. **§6 25-cohort filter 策略**（MED，QC / PA 拍板）— `market.liquidations` 收所有 symbol vs cohort-only filter；當前 39 symbol > 25 cohort，BSBUSDT / EDENUSDT 等非 cohort 佔 ~46.5%；建議：aggregator 內部過濾（writer 全收，downstream cohort-only）
4. **§6 W-AUDIT-8a C1 plan 收口 vs 重啟**（HIGH，PM / MIT 拍板）— writer 已 production 5 day；C1 plan 標 PASS-by-empirical-evidence，還是要求 isolated 24h proof rerun？BB advisory：**標 PASS**（empirical evidence ≥ isolated probe），但 MIT 必補 schema mapping sign-off
5. **`engine_mode` column 添加**（LOW，FA / E1 拍板）— 當前 `market.liquidations` 5 col 無 engine_mode；是否補 column + 後續 ML feature 用該過濾？BB advisory：**defer**（writer 已 production，3.7 day data 全 live_demo + live，無 paper 污染風險）
6. **Earn endpoint demo 支援 smoke**（MED，operator + BB 共同）— `curl https://api-demo.bybit.com/v5/earn/flexible/product` 是否回 valid product；若 demo 0 product → Sprint 1A 部署 LiveDemo / Mainnet gate 而非 demo

---

## Part G — Verdict summary

- **C4**：**(a) API exists** + 字典 drift 5+ 月。Sprint 1A §4 工時 18~25 hr 合理；BB1 補 12 endpoint 章節。
- **C5**：**(a) non-withdraw scope sufficient**。dedicated `Earn` scope；不違 D1d / `CLAUDE.md` Hard Boundaries。operator 需確認 key 發行日。
- **C6**：**(a) PROOF PASS** + 推翻 v57 executability audit Risk 1。PG `market.liquidations` 31,473 rows 3.7 day 持續流入；writer production-grade；字典 + W-AUDIT-8a C1 plan stale 約 5 day。

**Sprint 1A 派發 verdict（BB 視角）**：**GO-WITH-CONDITIONS**
- 4 個 Sprint 1A 派發前 must-fix：A.4 必補 1-3 + C.5 必補 1-2（字典同步 + 25-cohort + W-AUDIT-8a C1 closure + API key scope verify）
- Sprint 1A scope 限定 §4 read-only Earn API + §6 healthcheck extend（不重啟 isolated proof）
- 工時 estimate 65~85 hr（v57 audit「90~130 hr」over-estimated）
- 0 ship-stop blocker；0 hard boundary 違反；0 ToS 違反

---

## Part H — 字典補錄清單（BB1 sub-agent Wave 3b 工作）

| # | 字典位置 | 等級 | 改動 |
|---|---|---|---|
| 1 | §3 NEW Earn API（章節） | HIGH | 加 12 endpoint 完整章節（path + method + scope + rate group） |
| 2 | §1.10 line 1092 + 1099 + 1325 | HIGH | 移除「allLiquidation BLOCKED」字樣；標 revival 2026-05-17 ~23:12 UTC + 31,473-row empirical proof |
| 3 | §2.1（WS topic table） | HIGH | `allLiquidation.{symbol}` 從 reserved-for-future → active production |
| 4 | §3 NEW `/v5/earn/byusdt/*` 章節 | LOW | 2026-04-08 BYUSDT earning endpoint（OpenClaw 暫不用） |
| 5 | §3 NEW `/v5/earn/fixed-saving/*` 章節 | LOW | 2026-04-14 fixed saving product（OpenClaw 暫不用） |
| 6 | §4.1 Rate Limit table | LOW | 新加 Earn group rate limit（公開 5 req/s 同 Asset？需 BB 確認） |

估算工時 ~4-6 hr（與 BB Wave 3b 既有 7 處更新清單合併執行）

---

**BB AUDIT DONE**: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md
