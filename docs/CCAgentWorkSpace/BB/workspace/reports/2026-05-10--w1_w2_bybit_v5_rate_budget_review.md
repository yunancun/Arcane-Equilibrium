# BB W1 + W2 Bybit V5 Rate Budget Review

**Auditor**: BB (Bybit Broker Compatibility Auditor)
**Date**: 2026-05-10
**Scope**: Sprint N+1 W1 (W-AUDIT-8a Phase B Tier 2 collector) + W2 (A4-C BTC→Alt Lead-Lag) + W3 Stage 1 cohort observation rate budget feasibility audit
**Source verification**:
- Bybit V5 official rate-limit doc — `https://bybit-exchange.github.io/docs/v5/rate-limit`（fetched 2026-05-10）
- 字典手冊 `srv/docs/references/2026-04-04--bybit_api_reference.md` v1.2 §4.1
- Source code `rust/openclaw_engine/src/{bybit_rest_client.rs,database/rest_poller.rs,ws_client/}`

---

## §1 — Bybit V5 真實 cap

### 1.1 IP-level cap（涵蓋所有 unauthenticated `/v5/market/*` 公共端點）

| 維度 | 真實 cap | 來源 |
|---|---|---|
| **Per IP HTTP** | **600 req / 5s = 120 req/s** | Bybit V5 doc rate-limit page |
| 違反 | 403 + 10 min cooldown | Bybit V5 doc |
| **Per IP WS connection** | 500 conn / 5min；market data 1000/IP（Spot/Linear/Inverse 分計）| Bybit V5 doc |

### 1.2 UID-level cap（authenticated `/v5/order/*`、`/v5/position/*`、`/v5/account/*` 等）

| Group | 字典 v1.2 §4.1 cap | 適用 | 來源 |
|---|---|---|---|
| Order | **20 req/s**（VIP 升） | `/v5/order/*` `/v5/execution/*` | rust `RateLimitGroup::from_path` |
| Position | **20 req/s** | `/v5/position/*` | 同 |
| Account | **20 req/s** | `/v5/account/*` | 同 |
| Market | **120 req/s** | `/v5/market/*` `/v5/spot-lever-token/*` | 同 |
| Asset | **5 req/s** | `/v5/asset/*` `/v5/spot-margin*` | 同 |
| Other | 10 req/s | 其餘 | 同 |

### 1.3 Burst behavior

- Bybit IP cap 是 **5s rolling window**，非 per-second。瞬時 600 req 在 5s 內可發完，但需平均 ≤120 req/s 不被切。
- WS topic 訂閱 **不計入** REST rate；topic 一次 subscribe = 0 req/s 持續 cost。

---

## §2 — 既有 baseline + W1/W2/W3 預期 rate

### 2.1 既有 baseline（`rust/openclaw_engine/src/database/rest_poller.rs` HEAD）

| Task | 端點 | 25 sym 頻率 | req/s | Rate group |
|---|---|---|---|---|
| Funding poller | `/v5/market/funding/history` | 15min cycle | 25 / 900 = **0.028** | Market |
| OI poller | `/v5/market/open-interest` | 5min cycle | 25 / 300 = **0.083** | Market |
| LSR poller | `/v5/market/account-ratio` | 15min cycle | 25 / 900 = **0.028** | Market |
| WS public（kline.1 + tickers + orderbook.50 × 25 sym） | WS not REST | broadcast | **0**（subscribe 後 0 持續 cost）| n/a |
| Authenticated（wallet/position/order REST cycle）| `/v5/account/*` `/v5/position/*` | ~5min cycle | < **0.5** est | Account/Position |
| Healthcheck snapshot scrape | `/v5/market/time` etc | per cycle | < **0.1** est | Market |
| **Baseline 合計**（保守）| | | **~0.7 req/s** | — |

dispatch v3.3 提的「per-strategy ticker scan」實際走 WS broadcast，**不消耗 REST rate**（W-C MAG-082 IPC bus 推送 ticker）。

### 2.2 W1 W-AUDIT-8a Phase B Tier 2 collector

| Wave | dispatch v3.3 spec | BB 推薦 IMPL pattern | req/s 估 |
|---|---|---|---|
| **W1 B-1 funding_curve** | "25 × 60 = 1500 req/h" = 0.42 req/s spec assumes 1m REST polling | **WS `tickers` topic `fundingRate` field 已 broadcast**（字典 line 974）；REST polling **0 sym new poll**，僅 cold-start backfill 25 calls × 1 batch ｜ **0**（WS-first） |
| **W1 B-2 oi_delta_panel** | "25 × 60 = 1500 req/h" = 0.42 req/s spec assumes 1m REST polling | **WS `tickers` topic `openInterest` field 已 broadcast**（字典 line 974）；如需 5m/15m granular OI 改用 cron poll 25 sym × 12次/h = **0.083**（同既有 baseline 不疊加，可改為頻率提升至 1m = 25 sym / 60s = **0.42 req/s**） | **0** ~ **0.42** |
| **W1 合計**（WS-first 推薦）| | | **0** ~ **0.5 req/s** |

### 2.3 W2 A4-C BTC→Alt Lead-Lag

| Wave | dispatch v3.3 spec | BB 確認 | req/s |
|---|---|---|---|
| **W2 C-IMPL-2 btc_lead_lag** | "BTCUSDT 1m kline + spot orderbook 60+60 = 120 req/h" | **WS kline.1.BTCUSDT + orderbook.50.BTCUSDT 已預設訂閱**（W-AUDIT-8d spec 確認 0 新 endpoint）| **0** |

### 2.4 W3 Stage 1 cohort observation

| 場景 | endpoint | req/s |
|---|---|---|
| Stage 1 paper × 7d × 1 strategy × 1 symbol | 0 真實 Bybit API call（Stage 0/1 完全 shadow + paper simulator）| **0** |

### 2.5 總和（WS-first IMPL）

| 來源 | req/s |
|---|---|
| Baseline | 0.7 |
| W1 (WS-first) | 0 ~ 0.5 |
| W2 | 0 |
| W3 Stage 1 | 0 |
| **合計** | **0.7 ~ 1.2 req/s** |

**Bybit IP cap 120 req/s** → 利用率 **0.6% ~ 1.0%**

---

## §3 — Rate burst 風險評估

### Verdict：**PASS（充裕餘裕，~99% headroom）**

| 評估維度 | 狀態 |
|---|---|
| Per-endpoint Market cap (120 req/s) | ✅ < 1% 利用 |
| Per-IP cap (600/5s) | ✅ < 1% 利用 |
| Per-UID Order/Position/Account cap (20 req/s each) | ✅ baseline < 0.5 req/s |
| WS connection cap (500/5min, 1000 market) | ✅ 當前 ~6 conn (4 public + 2 private)，遠低於 cap |

**多 writer 同時 launch burst 風險**：W1 collector 啟動瞬間若 25 sym × 3 endpoint REST cold-start backfill 並發 = 75 req 瞬發 ≪ 600/5s = **PASS**（無需 jitter）。

---

## §4 — Mitigation 建議

### M-1（必）WS-first IMPL pattern（Phase B 強制）

W1 B-1 / B-2 spec 寫「1500 req/h REST polling」為**不必要 over-engineering**：

- `tickers` topic 已 broadcast `fundingRate` + `nextFundingTime` + `openInterest`（字典 line 974）；25 sym × 1 subscribe 後即時推送，**0 REST cost**
- REST `/v5/market/funding/history` 僅在 cold-start backfill / WS reconnect gap fill 時用
- REST `/v5/market/open-interest` 僅在需要 5min/15min/1h/4h granular OI 時用（WS 提供即時 snapshot 無 grain 區分）

**spec 應改為**：
- "WS `tickers` topic 為主，1m snapshot from WS rolling buffer"
- "REST 僅 cold-start backfill (25 calls × 1 batch wait, ~0.21s)"

### M-2（推薦）若 spec 必須 REST polling → aggregator pattern

若 PA Phase B spec 拍板必走 REST polling，則：
- 25 symbol 必須在 collector 內合併 batch wait（而非並發 25 separate calls）
- 1m grain 合理；不需 staggered start（瞬時 25 req ≪ 600/5s）
- monitoring：`is_group_near_limit(Market, 30)` 預警 ≤25% headroom（當前 ~99% headroom 不會觸發）

### M-3（建議）W3 Stage 2 / Stage 3 預警

W-AUDIT-9 Stage 2 (1 sym demo × 14d) + Stage 3 (5 strategy × full universe demo × 21d) 啟動時：
- Stage 2 = 1 sym × 既有 OrderManager / IntentProcessor 真送 demo endpoint = ~ +0.05 req/s Order group 增量
- Stage 3 = 25 sym × 5 strategy × peak ~10 intent/min = ~ 0.83 req/s Order group = 4% Order cap → **PASS**

---

## §5 — Bybit ToS / KYC / 地理風險

### 5.1 25 symbol cohort KYC tier 風險：**0**

Bybit demo + LiveDemo (api-demo) **不要求 KYC tier**；Stage 4 LIVE_PENDING 才觸 KYC。25 symbol 全為 USDT-perp linear（無 spot lending、無 options、無 leveraged token），**不觸 tier 3 限制**。

### 5.2 anti-spam / market maker rebate 觸發風險：**0**

- W1/W2 全為 **read-only market data fetch**，**不創建 order**，**不上報 quote**
- 不觸發 wash trading filter（無 self-cross）
- 不觸發 spoofing filter（無 large limit cancel）
- 不影響 broker rebate 30d volume tally（當前 $45K vs $10M threshold 222× gap，與本 wave 無關）

### 5.3 公告 / changelog 風險：**0**

30d Bybit V5 changelog (2026-04-09 ~ 2026-05-09) **0 breaking change**（繼承 Sprint N+0 audit），25 symbol perp universe **0 listing/delisting** 影響。

---

## §6 — W1 + W2 dispatch update 建議

### CRITICAL recommendation to PM：

**W1 spec line "25 × 60 = 1500 req/h" 為過度估算，建議改為 WS-first**：

1. **W1 B-1 funding_curve**：改 spec "**WS `tickers.{symbol}` topic 為主**（已預設訂閱），REST `/v5/market/funding/history` 僅 cold-start backfill (25 calls 1 batch)"
2. **W1 B-2 oi_delta_panel**：改 spec "**WS `tickers.{symbol}` topic 即時 openInterest field 為主**；如需 5min granular history 則改為 cron 1次/5min × 25 sym = 0.083 req/s"
3. **W2 C-IMPL-2 btc_lead_lag**：spec 已寫對（WS kline + orderbook 已預設訂閱），**0 新 REST poll 需求**

如 PA spec 採納此 WS-first pattern → **真實 W1+W2 增量 = 0 ~ 0.5 req/s**，W1+W2+W3+baseline 合計 < **1.2 req/s**，餘裕 ~99%。

如 PA spec 堅持 REST polling → 維持 PASS verdict 但浪費 ~3 req/s 的 WS broadcast 既有資源。

### 不需 cohort 縮減 / grain 拉長 / staggered start

當前 25 symbol cohort + 1m grain + 同時 launch 全部 PASS Bybit cap，**不需任何縮減**。

### Stage 1 cohort symbol 排除（v3 carry-over，仍適用）

W-AUDIT-9 Stage 1 cohort 拍板時 BUSDT **必排除**（funding_arb retire 殘倉風險，與 rate budget 無關但 BB 政策面持續 flag）。

---

## §7 — Final Verdict

**Verdict: PASS — W1 + W2 + W3 + baseline 合計 < 1.2 req/s, ~99% Bybit IP cap headroom，無 rate burst 風險，無 ToS / KYC / geographic 觸發風險。**

**主要 push back（HIGH）**：
- W1 spec "1500 req/h REST polling" 是 over-engineering — `tickers` WS topic 已 broadcast funding rate + openInterest field，REST polling 多餘。建議 PA Phase B IMPL **WS-first pattern**，REST 僅作 cold-start backfill。

**次要 push back（MEDIUM）**：
- 若 PA spec 維持 REST polling，須在 collector 加 `is_group_near_limit(Market, 30)` 預警（防未來 cohort scale 至 100+ sym 時觸 cap）
- W3 Stage 1 cohort 拍板必排除 BUSDT（v3 carry-over）

**LOW**：
- 無

---

**BB AUDIT DONE**: srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-10--w1_w2_bybit_v5_rate_budget_review.md
