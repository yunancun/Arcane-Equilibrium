# BB v3 對抗性核實 — 5 commits Bybit 影響 + PA Alpha Surface Bundle 真實可行性

**Auditor**: BB · baseline `1bd55689` → `da2aba11`（5 commits）
**v2 baseline**: ✅6/⚠3/❌7/🆕2；技術 97% / 政策 70%

**Tally：✅ 7 / ⚠️ 3 / ❌ 7 / 🆕 4 · 技術 97% / 政策 70% · Alpha Surface Bundle 可行性: MEDIUM**

## §A — 5 commits Bybit 影響核實

### A.1-A.5 各 commit Bybit endpoint impact

| commit | Bybit impact | verdict |
|---|---|---|
| `ad14db07` Donchian guard | **0**（本地 indicator 算法 fix）| ✅ Bybit endpoint compatibility intact |
| `c2ab7b1a` strategist wide skill | **0**（純 internal Agent 通信）| ✅ Bybit-orthogonal |
| `48227607` promotion evidence | **0**（ML pipeline + governance plane）| ✅ Bybit-orthogonal |
| `c081029d` blocked symbols freeze | **0**（strategy-side filter）；副作用：增強對 Bybit listing/delisting 的防護 | ✅ Bybit-orthogonal，治理面 +1pp |
| `da2aba11` f08 cron scope | **0**（ML training 維護 job）| ✅ Bybit-orthogonal |

**5 commits 累計**：對 Bybit 全部 orthogonal。技術合規度維持 97%。

### A.6 funding_arb retire 後殘倉風險（v3 重檢）

**Linux PG 直查**：
```
live_demo |  2859 | 2026-05-03 21:01:35.117+02
demo      |  9327 | 2026-05-04 14:34:31.244+02
```
**= 12186 條 BUSDT snapshot，與 v2 完全一致。最後寫入 5-6 天前。NEW-1 殘倉 0 進展**。

**Bybit-side push back**：W-AUDIT-6 risk_config layer 已清乾，**但** operator 仍未跑 `/v5/position/list?symbol=BUSDT` 實測。從 Bybit 立場：funding_arb 已從 risk_config 撤掉 → **若 Bybit 端真實 BUSDT 倉位仍在，現在無 risk cap 監管它了**。

M5-2 IP whitelist 仍 outstanding（`helper_scripts/preflight/` 目錄不存在）。M5-1 ToS / KYC / 地理禁區 仍 0 進展。

## §B — PA Alpha Surface Bundle Bybit 真實可行性

| Alpha source | Bybit V5 真實 | 可行性 |
|---|---|---|
| **funding_rate** | `/v5/market/funding/history` Demo+Mainnet 都支援；rate limit 充裕 | **HIGH** — 已在 rest_poller.rs:62 拉取，但 7d 只 42 條（thin） |
| **basis (perp - spot)** | Demo 支援 spot category 行情拉取；**但 demo 無 spot lending execution**（funding_arb v2 retire 同因）| **MEDIUM** — Demo 限 observation；execution 需 mainnet |
| **open_interest** | `/v5/market/open-interest` + WS ticker 含 openInterest | **HIGH** — 已在 rest_poller.rs:91 拉取，但 7d 只 2 symbols（thin！） |
| **orderflow (microprice / queue)** | **Bybit V5 WS 真實 levels: linear 1/50/200/1000；NO 「L25」**；REST 1-500 levels | **MEDIUM** — PA spec「L25+」不準（Bybit WS 沒 25），但 orderbook.50 已預設訂閱，bids5/asks5 已 parser extract |
| **cross_asset (25 symbols funding curve)** | `/v5/market/tickers` **NOT batch**；funding history 必須 25 separate calls | **MEDIUM** — 25 calls/8h ≈ 75 call/24h，Market 限 120 req/s 充裕；但 cross-section snapshot 需自行 buffer |
| **liquidation_pulse** | WS allLiquidation public stream 真實存在 | **LOW** — **OpenClaw 已刪除 liquidation handler**（字典 line 990：「2026-04-06 已刪除」）；要恢復需重接 WS handler |

### B.2 對抗性核實逐條

#### B.2.1 funding_curve（25 symbols cross-section）— **MEDIUM 可行**

- 沒 batch endpoint，必須 25 calls × N intervals
- Market rate limit 120 req/s，25 calls/8h = 0.0009 req/s 預算
- 7d empirical 只 42 條 funding_rate snapshot（顯然當前 polling 頻率低）
- **Push back**: PA 沒指出「需要 25 symbols × 8h cycle = 525 calls/week」— Bybit-side 確認 **rate limit 不是 blocker**，只是當前 OpenClaw rest_poller.rs 沒對全 25 symbols 拉

#### B.2.2 basis (perp - spot) — **MEDIUM**

- Demo 支援 category=spot 拉 kline + tickers ✅
- 但「Bybit demo 不支援 spot lending」早在 funding_arb v2 retire 時已驗證
- PA 主張的「basis trading」如果只做觀察 → Demo 全 OK
- 如果做真 cash-and-carry execution → Demo **不可行**

**Push back**: PA 草案沒區分「basis observation」vs「basis execution」。R-1 spec 必須明文「basis = observation-only signal until mainnet」否則跟 funding_arb v2 同陷阱。

#### B.2.3 open_interest panel — **HIGH 可行**

- `/v5/market/open-interest` + WS tickers 都 OK
- 25 symbols × WS subscription = 0 額外 REST cost
- 但**當前 7d 只 2 symbols 在 market.open_interest 表寫入**

**Push back**: 在 Bybit-side 是**真免費的**（WS 已含），但 OpenClaw 當前寫入路徑 thin。R-1 必須先驗 ws_client → market_writer 對 25 symbols 真實 throughput。

#### B.2.4 orderflow (microprice / queue depth) — **MEDIUM（spec 改 L50）**

- **Bybit V5 WS levels: linear 1/50/200/1000；NO 「25」**
- PA 草案「L25/L50 orderbook」**寫錯**了 Bybit 真實 levels
- OpenClaw 當前已訂 orderbook.50.{symbol}
- microprice / queue imbalance 已實裝（bybit_public_microstructure_builder.py:232）

**Push back**: PA spec **必須改寫**「L25 → L50」否則 R-1 IMPL 會撞 Bybit endpoint validation。

#### B.2.5 cross_asset BTC/ETH 跨幣 — **MEDIUM 可行**

- `/v5/market/tickers` **NOT batch**
- 25 symbols 通過 WS 已**事實上**送來 funding rate snapshot
- ws_client/parsers.rs:226 funding_rate 已 parse

**Push back**: PA「batch query」在 Bybit-side **不存在**。R-1 IMPL 不需要 batch endpoint，只需要在 cross-section level **buffer + aggregate** 25 symbols WS ticker funding_rate。

#### B.2.6 liquidation_pulse — **LOW（已刪除）**

- WS topic `allLiquidation` 真實存在
- 但 **OpenClaw 4 weeks ago 已刪除 liquidation handler**
- `market.liquidations` 表保留 reserved-for-future
- PA 主張需要 → R-1 必須 **revert** 4-weeks-old 刪除 + 重接 WS handler + 重啟 writer

**Push back**: PA 草案沒提 liquidation_pulse 已 deleted；R-1 IMPL 需要 +1 sprint 重接。

### B.3 ToS / KYC / 地理 / 高級策略合規

| 策略 | Bybit ToS | OpenClaw 風險 |
|---|---|---|
| Funding skew spread | ✅ legal | demo 不可 execution |
| Orderflow imbalance | ✅ legal | 觸 anti-spoofing 紅線需 Strategy 設計時規避 |
| Liquidation cascade detection | ✅ legal (read-only signal) | execution 走當前路徑無新風險 |
| Cross-asset basis arb | ✅ legal | Bybit only → 跨所 arb out of scope |
| 25 symbols funding curve | ✅ legal (read-only) | rate limit 充裕 |

**M5-1 仍 outstanding 對 PA 影響**: 即使 R-1/R-2/R-3 全 IMPL，**M5-1 governance 沒建檔 → mainnet 真綁前無 audit trail**。R-1 alpha bundle IMPL 是技術 enabler，**不替代** M5-1/M5-2 ship-stop blocker。

## §C — Verification tally（v3 final）

| Status | Count | Findings |
|---|---:|---|
| ✅ closed | 7 | L5-1/2/3/4 + A5-4 + W-AUDIT-6 risk config + 🆕 NEW-3 [56] healthcheck PASS resolved（auth.json renewed 16:45 UTC） |
| ⚠ partially-closed | 3 | A5-2 retCode 110017 enum 未補 / A5-6 fee_drop 仍受 funding_arb 樣本污染 / NEW-4 §三 [56] PASS 已 5h drift |
| ❌ unchanged | 7 | M5-1 ToS / M5-2 IP whitelist / A5-1 04-30 新欄位 / A5-3 settleCoin / A5-5 broker_id / A5-7 rate_limit / A5-9 V3 預檢 |
| 🆕 NEW v3 | 4 | NEW-5 PA spec L25 levels 不存在 / NEW-6 PA liquidation_pulse 已 deleted / NEW-7 25-symbol funding curve 7d 只 42 條 thin / NEW-8 PA basis demo 限 observation 沒分 |

## §D — Push back（5 條）

### #1 5 commits 全 Bybit-orthogonal — Bybit 端 0 退化、0 進步
**v2 → v3 跨 24h 仍 0 進展 M5-1/M5-2**（仍 ship-stop blocker）。

### #2 BUSDT 殘倉 12186 條仍未動 — operator action 9 天拖延
funding_arb policy retire 後若帳戶上仍有 BUSDT 倉，**現在沒 risk cap**。

### #3 PA Alpha Surface spec 部分不準
- 「L25/L50 orderbook」**Bybit 真實 levels = 1/50/200/1000，沒有 25**
- basis 沒區分 observation vs execution
- liquidation_pulse 已 4 weeks ago deleted

### #4 25-symbol funding curve「結構性 thin baseline」
從 Bybit 立場 25 symbols × WS funding rate **真免費**，但 PG empirical 證明 **OpenClaw 當前 funding_rate 寫入路徑 thin**（7d 42 條，預期應有 ~525 條）。R-1 IMPL 前必須先驗。

### #5 PA R-1/R-2/R-3 不替代 M5-1/M5-2 ship-stop
從 Bybit 立場：即使 PA architectural redesign 全完，**Live mainnet 真綁前 M5-1/M5-2 仍是 hard prerequisite**。建議**並行**而非「先 R-1 後 M5-1/M5-2」順序。

## §E — Bybit-side 結論

### 技術合規度：**97%**（與 v2 持平）
- Bybit V5 endpoint 100%
- HMAC + Rate limit + LIVE-GUARD 100%
- 字典 SSOT 100% align
- LiveDemo healthcheck 回升至 100%（auth.json 16:45 UTC 重簽，[56] PASS snapshot 27s fresh）
- A5-2 110017 enum + A5-6 fee_drop asymmetry 仍 -3pp

### 政策合規度：**70%**（與 v2 持平，0 進展）
- M5-1 governance entry 0
- M5-2 IP whitelist preflight 0
- 30d Bybit changelog 0 breaking

### Alpha Surface Bundle Bybit 可行性 verdict：**MEDIUM**

| Tier | Alpha source | Feasibility |
|---|---|---|
| 1 | TA 1m/5m | ✅ HIGH |
| 2 | funding_rate cross-section | ✅ HIGH（需 fix thin baseline） |
| 2 | basis (perp-spot) | ⚠️ MEDIUM（demo 限 observation） |
| 2 | open_interest panel | ✅ HIGH（需 fix thin baseline） |
| 3 | orderflow microprice | ✅ HIGH（PA spec L25 改 L50） |
| 3 | liquidation_pulse | ⚠️ LOW（4w ago deleted，需 revert） |
| 4 | event_alerts (Scout) | ⚠️ MEDIUM |
| 4 | sentiment_panel | ⚠️ LOW（依賴 L2 cloud reasoning） |

**Bybit-side 對 PA R-1/R-2/R-3 投票**: **CONDITIONAL APPROVE**：
- R-1 Alpha Surface IMPL 在 Bybit-side **真有 endpoint 支援**
- 但 PA spec 必須先**修 3 條 NEW finding**（L25→L50 / liquidation revive / basis observation-only 區分）
- 必須**並行** M5-1/M5-2 修復
- 必須先**驗 thin baseline**

## §F — Operator Actions（按優先序）

| 優先 | Action | Owner |
|---|---|---|
| **P0** (9d delayed) | operator BUSDT empirical query → 決定 PG 清 vs dust clear | operator |
| **P0** (11d delayed) | M5-2 IP whitelist preflight IMPL | E1 |
| **P0** (11d delayed) | M5-1 ToS / KYC governance entry 框架建檔 | PM |
| **P0 BB v3 NEW** | PA R-1 spec 改寫 L25 → L50/L200 | PA |
| **P0 BB v3 NEW** | PA R-1 spec 加 liquidation_pulse 復活路徑（+1 sprint cost） | PA |
| **P0 BB v3 NEW** | PA R-1 spec 區分 basis observation vs execution | PA |
| **P0 BB v3 NEW** | R-1 IMPL 前驗 funding/oi 25 symbols 真實寫入 throughput | E1 + PA |
| P1 | Rust BybitRetCode enum 加 SpotLendingUnavailable=110017 | E1 |
| P2 | 字典 v1.3 補 04-30 新欄位 catalog | TW |

---

**BB VERIFICATION v3 DONE** · ✅ 7 / ⚠️ 3 / ❌ 7 / 🆕 4 · 技術 97% / 政策 70% · Alpha Surface Bundle 可行性: MEDIUM
