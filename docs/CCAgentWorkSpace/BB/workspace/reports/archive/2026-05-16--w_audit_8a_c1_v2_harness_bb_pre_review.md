# BB Pre-Review — W-AUDIT-8a C1 v2 Resilient Harness

**Ticket**：`P1-W-AUDIT-8A-C1-RETRY-PLAN-1` Phase 2 IMPL adversarial review
**Date**：2026-05-16
**Owner**：BB (Bybit Broker Compatibility Auditor)
**Worktree branch**：`worktree-agent-a58d99ef4ea1a440b` HEAD `5983f955`
**Source**：
- v2 probe `helper_scripts/bybit/liquidation_topic_probe_v2.py` (942 LOC)
- v2 tests `helper_scripts/bybit/test_liquidation_topic_probe_v2.py` (656 LOC，36/36 PASS non-flaky)
- E1 self-report `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_impl_self_report.md`
- v1 evidence `trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_latest.json`
- Design plan `docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md`

**Scope**：Bybit-side 5 focus pre-deploy review。100% read-only。0 production change。0 second-tier sub-agent spawn。

**Verdict**：**APPROVE-CONDITIONAL**（5 focus 全通過，3 條 advisory follow-up，0 ship-stop blocker）。

---

## §1 Focus 1 — Bybit V5 `allLiquidation.{symbol}` Real Payload Schema

### 1.1 Bybit V5 官方 docs verify

從 `https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation` 直 fetch (2026-05-16)：

| 層級 | Field | Type | 說明 |
|---|---|---|---|
| Envelope | `topic` | string | `allLiquidation.{symbol}` |
| Envelope | `type` | string | `snapshot`（**官方僅標 snapshot；無 delta type**） |
| Envelope | `ts` | number | System generation ms |
| Envelope | `data` | Object[] | Liquidation records 陣列 |
| Inner | `T` | number | Updated timestamp ms |
| Inner | `s` | string | Symbol（如 `ROSEUSDT`） |
| Inner | `S` | string | `Buy` / `Sell` |
| Inner | `v` | string | Executed quantity |
| Inner | `p` | string | Bankruptcy price reference |

**Push frequency**：**500ms**（官方明示）— **非實時 per-event，而是 500ms 累積批次**。Bybit 在 500ms 內若有 N 個 liquidation event，會一次塞 `data: [{...}, {...}, ...]` 推一個 frame。

**官方覆蓋範圍**：USDT / USDC / Inverse perpetual + futures 全 supported。

### 1.2 v1 15 messages 對照 verify

從 `trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_latest.json` `candidate_samples` 抽 5 個 frame（含 9 個 inner liquidation entry）：

| 觀察 vs 官方 schema | 結論 |
|---|---|
| 5 frame 全部 `topic="allLiquidation.BTCUSDT"` ✅ | 對齊 |
| 5 frame 全部 `type="snapshot"` ✅ | 對齊（無 `delta` 觀察到） |
| 9 inner entry 全部 5 field (`T/s/S/v/p`) ✅ | 對齊 |
| `S` 全為 `"Buy"` ✅ | 對齊（觀察期 BTC 偏多倉清算） |
| `v` 範圍 `0.001 ~ 0.077` BTC（small lot） ✅ | 合理（500ms 批次內單筆 liquidation 可能小） |
| `p` 範圍 `78575.80 ~ 78673.30` USD ✅ | 對齊 BTC 觀察期價位（前文 `event_time` 顯示 2026-05-15 ~20:00 UTC，與 v1 起跑時間 19:53 UTC 對齊） |
| Single-frame data 陣列長度：3 個 frame 為 1 entry / 1 個 frame 為 3 entry / 1 個 frame 為 3 entry | 證實 batch buffer 500ms 模式 |

**Verdict (Focus 1)**：✅ **PASS** — Bybit V5 docs schema 與 v1 觀察樣本 1:1 對齊。
- Field name `T/s/S/v/p` 仍 current（**字典 v1.3 應在 §2.1 補錄此 schema 供未來 production builder 參考；本 task 不直接改字典**）
- Push frequency 500ms batch buffer 確認
- Type 僅 `snapshot`（無 delta type 觀察到，與 docs 對齊）
- Cross-symbol multiplexing：v1 只訂 BTCUSDT 不可驗多 symbol；future 訂多 symbol（如 25-sym W-AUDIT-8c）需獨立驗證

**Bybit-side risk**：LOW（schema 對齊已驗證；future 字典手冊更新只是 docs hygiene，非 hot path）

### 1.3 v2 probe schema 處理

v2 probe `classify_payload()` 對 candidate 訊息僅做：
- `stats.candidate_messages_seen += 1` counter
- 前 N 個 frame 寫入 `stats.candidate_samples`（default N=20）— **整 frame 原樣保存**，無 schema parsing

**結論**：v2 probe 不依賴 schema 內部 field，純做 raw count + sample collection。schema delta 完全 deferred 給 MIT pre-review（design §4，正確設計）。

---

## §2 Focus 2 — WS Endpoint + Rate Limit + Connection ToS

### 2.1 Mainnet endpoint 24h continuous 連線合法性

**官方文檔結論**（fetch `https://bybit-exchange.github.io/docs/v5/ws/connect`）：

| 項目 | 官方規定 | v2 probe 行為 | 評估 |
|---|---|---|---|
| Public WS auth | **無需 auth**（`Public topics do not require authentication`） | v2 不送 auth | ✅ |
| 連線上限 | **500 connection / 5 min per IP** | v2 = 1 連線（reconnect 算同 IP slot 重用） | ✅ 99.8% headroom |
| Idle timeout | 默認 **10 min** without ping-pong or data；可用 `max_active_time` 客製化（30s ~ 600s） | v2 ping interval 10s + 持續收訊息 → 永不 idle | ✅ |
| 24h continuous policy | **無明文 24h 限制**；anti-abuse 主要對「frequent connect/disconnect」 | v2 1 connection 跑 24h + 累計 ≤ 3 restart | ✅ |
| Subscribe 上限 | **10 args per subscribe**（spot）；linear 未明示但業界經驗 10 args 安全 | v2 訂 5 topics（1 candidate + 4 control） | ✅ 50% headroom |
| Subscribe args 字符長度上限 | **21000 chars**（全 topics 合計） | v2 5 topic × ~30 chars ≈ 150 chars | ✅ 0.7% 利用率 |

**ToS / API User Agreement 評估**：Bybit V5 docs / ToS / API user agreement **未明確禁止** read-only monitoring / replay 用途，且 public WS 為公開市場數據。v2 probe 用於 audit + research，非繞過任何 fee tier / KYC / rate limit；無 ToS 違規風險。

**Verdict (Focus 2)**：✅ **PASS**
- 24h continuous 連線完全合法（idle timeout 10min 默認，主動 ping 避開）
- IP connection budget 99.8% headroom
- Subscribe args 99.3% headroom
- ToS 0 違規（read-only public stream，audit/research 用途）

### 2.2 Server-side idle timeout 與 v2 ping interval 互動

| 場景 | Bybit V5 默認 | v2 設計 |
|---|---|---|
| Idle timeout | 10 min | 10s ping interval（過 60x 安全餘裕） |
| Ping 推薦間隔 | **20s**（官方明示） | **10s**（v2 縮短半） |

**Bybit-side push back**：v2 ping=10s 對 Bybit 來說是 **2x 推薦頻率**。雖然技術上合法（未觸 ping-storm 限制），但：
- **無實際好處**（Bybit V5 ping 主要是「客戶端證明 alive」+「Server 不切連線」用，10s 並不會更早偵測 server-side close — 因 server close 是 TCP-level 而非 ping-level）
- **資源浪費**：24h × 8640 個多餘 ping = 對 Bybit 邊際 0 但對 NAT translation 維持是好事
- **不違規但 over-aggressive**

**Advisory A-1 (LOW)**：v2 ping_interval=10s 可改 20s（符合官方推薦），同等效果 + 對 Bybit 友好。**非 ship-stop**；若 operator 偏好 10s 因 NAT translation buffer 更短，accept trade-off。

### 2.3 多 connection 同時跑（production engine + v2 probe）

**Production engine WS**（`ws_client/run_loop.rs`）：mainnet `wss://stream.bybit.com/v5/public/linear` 訂閱 9 topic × 25 symbol = 225 topic 在 **1 connection**（split into 23 subscribe call × 10 args each）。

**v2 probe**：**獨立 connection** 走同 endpoint `wss://stream.bybit.com/v5/public/linear` 訂 1 candidate + 4 control = 5 topic。

**同 IP 並存風險評估**：
- 2 connection 同 IP × 0 frequent reconnect = **0.002 / 5min utilization**（5min 內最多 2 connect events vs 500 cap）→ ✅ 99.99% headroom
- 訂閱 args 字符長度：production engine 23 batch × ≤ 21000 chars + v2 probe 1 batch ≤ 21000 chars = 24 獨立 frames 互不影響（per-connection 計算）

**Verdict (Focus 2 sub)**：✅ **PASS** — production engine + v2 probe 並存 0 衝突；trade-core IP 從未接近 500 conn/5min cap。

---

## §3 Focus 3 — Bybit V5 Control Topics 共存

### 3.1 5 topic / 1 connection 合法性

v2 訂閱清單：
```
1. allLiquidation.BTCUSDT      (candidate)
2. tickers.BTCUSDT             (control)
3. orderbook.50.BTCUSDT        (control)
4. publicTrade.BTCUSDT         (control)
5. kline.1.BTCUSDT             (control)
```

| 評估維度 | 官方規定 | v2 actual | 結論 |
|---|---|---|---|
| 單 connection topic 數 | linear 未明示上限；spot 10 args/subscribe | 5 (1 subscribe call) | ✅ |
| 全部公開 topic | Public WS 不需 auth | 5 全公開 | ✅ |
| 跨 topic group 是否計入 Market group 20 r/s | Public WS 與 REST rate limit 解耦 | N/A | ✅ |
| 連線層 backpressure | 業界經驗：orderbook.50 + publicTrade 流量高（v1 觀察 orderbook.50.BTCUSDT 5h 收 454010 frame = ~25 msg/s） | v2 同設計 | ✅ |

**v1 5h 實證**：5 topic 同 connection 全活躍，raw_message_count=592046（5h），約 **33 msg/s avg**。v2 同設計，無 backpressure 證據。

### 3.2 Control topic 與 candidate topic 共連線是否有 backpressure

v1 5h 觀察：
- `orderbook.50.BTCUSDT`：454010 messages（76.7% 流量）
- `tickers.BTCUSDT`：85580 (14.4%)
- `publicTrade.BTCUSDT`：43161 (7.3%)
- `kline.1.BTCUSDT`：8458 (1.4%)
- `allLiquidation.BTCUSDT`：**15 (0.0025%)** — 極稀疏

**結論**：candidate topic（liquidation）流量極小（5h 內 15 frames，4 control 流量 ~592031），candidate 完全不會被 backpressure；control topic 主導 connection bandwidth。

**Verdict (Focus 3)**：✅ **PASS**
- 5 topic per connection 完全合法（per-IP 500 conn/5min 限制是 connection 計數，不是 topic 計數）
- 0 group quota 觸發（public WS 與 REST rate limit 解耦）
- v1 5h 實證 backpressure 0 跡象（candidate 流量極小）

---

## §4 Focus 4 — Reconnect 策略 vs Bybit-side ToS

### 4.1 連續 6 attempt reconnect vs Bybit-side IP throttle

**v2 設計**：
- 連續 6 attempt fail = 一個 RestartEvent
- 每 attempt 退避 1→2→4→8→16→32s = 63s 累計
- max_restart=3 → 整個 24h proof 最多 4 × 6 = **24 個 fresh connection** (含 initial)
- 24 connection / 24h = **0.001 connection/min** << 500/5min cap = ✅ 99.97% headroom

**Verdict**：v2 reconnect 預算遠低於 IP throttle 觸發點。

### 4.2 1→2→4→8→16→32→60s exp backoff vs Bybit 推薦

Bybit V5 docs（fetch `https://bybit-exchange.github.io/docs/v5/ws/connect`）對 reconnect 僅指引：
- "reconnect as soon as possible if disconnected"
- "do not frequently connect and disconnect"

**未提供明確 exponential backoff 範式**。

**v2 vs production engine baseline**：
- v2: 1-32-60s cap（first 6 attempts）
- production engine `ws_client/run_loop.rs::BACKOFF_POLICY = ws_public_default(0)`: **3-60s** exp backoff（base 3s）

**push back**：
- v2 1s base 比 production engine 3s base **更激進前段**
- 1s reconnect 在某些 edge case（如 server-side load shedding）可能加劇 Bybit-side stress
- 但 v2 max 6 attempts/session + 3 restart budget = 整 24h 最多 24 connect events，遠低於 IP throttle 風險

**Advisory A-2 (LOW)**：v2 base backoff 1s 與 production engine 3s 不對稱。建議 v2 統一用 `3s` 起步（與 production 對齊），保持「probe 是 production 同設計 + 額外 checkpoint」。**非 ship-stop**；當前 1s base 也合法不會 throttle。

### 4.3 24h cycle 內 reconnect 上限合理性估算

| 場景 | 24h reconnect 預估 | 結論 |
|---|---|---|
| Best case（無中斷） | 0 reconnect | ✅ |
| Typical case（1-2 中斷） | 2-4 reconnect | ✅ |
| Worst case（restart budget 用盡） | 24 connect (4 sessions × 6 attempts) | ✅ 99.97% headroom |

**Verdict (Focus 4)**：✅ **PASS** — Reconnect 預算對 Bybit IP throttle 完全安全；exp backoff 序列合法但 base 1s 偏激進（A-2）。

### 4.4 Connection-rate ToS 風險評估

Bybit V5 docs 「do not frequently connect and disconnect」屬 **soft guidance**，未明確 threshold。500 conn/5min hard cap 才是 enforceable。v2 24h 最壞 24 connection << 500/5min × 288 = 144000 24h cap = ✅。

**結論**：v2 reconnect 預算對 ToS / IP throttle 0 風險。

---

## §5 Focus 5 — v1 15 Messages JSON Schema Delta 預檢

### 5.1 v1 candidate_samples 抽取（已從 `trade-core` read-only 拿）

從 `trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_latest.json` 抓 `candidate_samples[]`：

**5 個 frame 含 9 個 inner liquidation entry**（v2 default `max_candidate_samples=20` 但 v1 default 也是 20，5h 內僅 5 frame 因 BTCUSDT liquidation 流量極稀疏）：

| frame # | type | ts ms | data 陣列長度 | inner entry sample |
|---|---|---|---|---|
| 1 | snapshot | 1778875542288 | 1 | `{T:1778875541877, s:BTCUSDT, S:Buy, p:78673.30, v:0.001}` |
| 2 | snapshot | 1778878129788 | 3 | `{T:1778878129534, s:BTCUSDT, S:Buy, p:78599.70, v:0.005}` + 2 more |
| 3 | snapshot | 1778878130788 | 3 | `{T:1778878130456, s:BTCUSDT, S:Buy, p:78607.20, v:0.015}` + 2 more |
| 4 | snapshot | 1778878133788 | 1 | `{T:1778878133583, s:BTCUSDT, S:Buy, p:78580.60, v:0.006}` |
| 5 | snapshot | 1778878136788 | 1 | `{T:1778878136713, s:BTCUSDT, S:Buy, p:78575.80, v:0.077}` |

`topic_message_counts.allLiquidation.BTCUSDT=15` 代表 v1 5h 觀察到 **15 個 message frame**，但只儲存前 5 個 + 9 inner entry。

### 5.2 與 design plan §4.2 預估 delta 對照

design §4.2 預估 schema delta：

| Bybit V5 field | Design 預估 `market.liquidations` column | v1 觀察 | Delta risk |
|---|---|---|---|
| `T` | `event_time` / `liquidation_time_ms` | ✅ ts in ms | LOW |
| `s` | `symbol` | ✅ "BTCUSDT" | LOW |
| `S` | `side` | ✅ "Buy" enum | LOW |
| `v` | `qty` | ✅ "0.001" string decimal | LOW |
| `p` | `price` | ✅ "78673.30" string decimal | LOW |
| 無 USD value | （needs `qty * price` calc） | 9 entry 全無 value column | MED — writer 需 derive |
| Snapshot vs delta type | （needs `event_type` mapping） | 9 entry 全 `type=snapshot`，無 delta 觀察 | LOW — 全 snapshot |

**Delta 預檢結論**：
1. **Schema 1:1 對齊** Bybit V5 docs（5 inner field 完全相同 name/type）
2. **無 USD value field** — production writer 需 `value_usd = qty * price` 動態 derive（如果 schema 有此 column；MIT 必驗）
3. **僅 snapshot type** 觀察到 — design plan 預估 「Snapshot vs delta type」mapping 需處理；v1 數據顯示 Bybit 當前實作只推 snapshot，無 delta（與 docs 對齊）

### 5.3 Bybit-side 重要 OBSERVATION

**v1 15 message / 5h 觀察期 = BTCUSDT 流量 ~3 msg/h**。如果未來 production builder 訂 25 symbol × 24h，估算：
- 25 sym × 24h × ~3 msg/h average = ~1800 msg/day
- 流量極低（BTC 偏多倉時 + altcoin 更稀疏）
- 0 backpressure 風險
- DB writer 流量 ~21 row/h × 25 sym = 525 row/h ≈ 12600 row/day

**結論**：production 觀察是 valid use case；low-frequency 資料源；無 storage explosion 風險。

**Verdict (Focus 5)**：✅ **PASS** — v1 15 messages 與 design plan §4 預估 delta 一致；MIT pre-review 可基於 v1 數據直接做 schema mapping 而不需等 24h。

---

## §6 BB-side Critical / Advisory Findings

### 6.1 Critical / High Findings：**0 / 0** ✅

無 ship-stop blocker，無高優先 push back。

### 6.2 Medium Findings：**0** ✅

### 6.3 Advisory Findings (3 LOW)

**A-1 LOW — v2 ping_interval 10s 偏 Bybit 推薦 20s 半**

- 位置：`liquidation_topic_probe_v2.py:88` `DEFAULT_PING_INTERVAL_SEC = 10.0`
- 影響：邊際 0；不違規 / 不 throttle / 不 backpressure；2x ping 頻率對 Bybit 邊際成本 0
- 建議：若 NAT translation buffer 需 10s 短檢 keep alive accept，否則改 20s 對 Bybit 友好（與 Bybit docs / production engine 對齊）
- Priority：non-blocking，operator 決定

**A-2 LOW — v2 reconnect base 1s 與 production engine `3s` 不對稱**

- 位置：`liquidation_topic_probe_v2.py:77` `RECONNECT_BACKOFF_SEC = (1, 2, 4, 8, 16, 32)`
- 對照：`ws_client/run_loop.rs::BACKOFF_POLICY = ws_public_default(0)` = `3s base`
- 影響：v2 前 3 attempts 比 production 更激進但 max 6 attempts/session 整體 budget 完全安全
- 建議：未來 v2 → production builder kickoff 期統一 base 3s（保持 probe 與 production 同設計風險模型）
- Priority：non-blocking，accept v2 1s base 因 probe 是 ephemeral tool

**A-3 LOW — 字典手冊 §2.1 `allLiquidation.{symbol}` 條目補錄需 V09X 字典 update**

- 位置：`docs/references/2026-04-04--bybit_api_reference.md` §2.1 當前僅標 `~~liquidation.{symbol}~~ 已移除` + 2026-05-15 W-AUDIT-8a C1 note 標 「Bybit official V5 docs now list the full liquidation stream as `allLiquidation.{symbol}`」
- 缺：完整 schema entry（topic 名 / type / push frequency 500ms / 5 field 表 / coverage USDT/USDC/Inverse）
- 建議：W-AUDIT-8a C1 v2 PASS 後（Phase C IMPL kickoff 前）BB1 字典 update 補錄 §2.1 新條目，與 §1.10 close-maker dispatch 同性質 spec-level reference
- Priority：deferred；C1 24h proof PASS 後再做（per BB frontmatter「不直接改 dict」rule）

---

## §7 v2 設計 Bybit-side 強項

### 7.1 v2 對 Bybit 整體影響 (24h cycle)

| 維度 | v1 5h baseline | v2 24h 預估 worst case | Bybit-side IP cap | 利用率 |
|---|---|---|---|---|
| IP connection budget | 1 connection | 24 connections（4 session × 6 attempts max） | 500 / 5min | 0.0003% |
| Per-conn topic count | 5 topic | 5 topic | linear 未明示上限 | N/A |
| WS public bandwidth | 33 msg/s avg | 33 msg/s avg | 純客戶端讀取 | N/A |
| Subscribe args 字符 | ~150 chars | ~150 chars | 21000 chars/conn | 0.7% |
| Ping rate | 0.05 ping/s（20s） | 0.1 ping/s（10s） | 無 hard cap | N/A |

**結論**：v2 對 Bybit 整體影響 << 任何 ToS / rate limit / IP throttle 觸發點。

### 7.2 v2 vs Bybit V5 docs 推薦 best practice 對照

| Bybit V5 docs 推薦 | v2 設計 | Match |
|---|---|---|
| reconnect immediately if disconnected | exp backoff 1→2→4→8→16→32s | ⚠️ partial — backoff 序列符合「avoid frequent reconnect」 |
| do not frequently connect and disconnect | max_restart=3 + 60s wait between sessions | ✅ |
| ping every 20s | ping every 10s | ⚠️ A-1（過密但合法） |
| max 500 conn / 5min per IP | worst case 24 conn / 24h | ✅ |
| idle timeout 10min default | 10s ping interval + 持續收訊息 | ✅ 60x 安全餘裕 |
| max 21000 chars subscribe args | ~150 chars | ✅ 0.7% 利用率 |

**Verdict**：✅ A-grade 對齊（2 advisory non-blocking deviations）。

---

## §8 BB Sign-off Block

### 8.1 5 Focus Verdict 總表

| Focus | Verdict | 風險評分 |
|---|---|---|
| 1. allLiquidation payload real schema | ✅ PASS | LOW |
| 2. WS endpoint + rate limit + ToS | ✅ PASS | LOW |
| 3. Control topics 共存 | ✅ PASS | LOW |
| 4. Reconnect 策略 vs ToS | ✅ PASS | LOW |
| 5. v1 15 messages schema delta 預檢 | ✅ PASS | LOW |

**5/5 PASS。0 Critical / 0 High / 0 Medium / 3 Advisory LOW。**

### 8.2 4 待答 BB-side Answers

per design §5.3 + E1 self-report §5.3：

| # | 待答 | BB-side answer |
|---|---|---|
| 1 | `market.liquidations` 現實際 PG schema | **MIT 主負**（BB out-of-scope；E1 self-report §5.3 標 MIT 自取，正確設計） |
| 2 | v1 15 messages JSON dump path | ✅ **`trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_latest.json`** `candidate_samples[]` 路徑（已驗證 5 frame 含 9 inner entry，§5.1 完整列出） |
| 3 | Schema delta 是否需 V09X migration | **MIT 主負**（BB advisory：v1 觀察與 docs 1:1 對齊；若 `market.liquidations` 既有 schema 已有 `event_time/symbol/side/qty/price` column，delta=0；若需 `value_usd` 或 `event_type`，需 V09X；MIT pre-review 後最終決定） |
| 4 | Bybit V5 `allLiquidation.{symbol}` payload type field | ✅ **`type` 僅 `snapshot`**（per official docs + v1 9 entry 全 snapshot 觀察）。**無 delta type 在當前 Bybit V5 實作中觀察到**；future 若 Bybit 加 delta type，schema 解析需加 enum guard（advisory only，當前 0 影響） |

### 8.3 BB Sign-off

**Verdict**：**APPROVE-CONDITIONAL**

**Conditions（non-blocking）**：
1. A-1 / A-2 / A-3 列入後續 W-AUDIT-8a Phase C IMPL kickoff 期 BB review 清單
2. C1 24h v2 proof PASS 後 BB1 字典更新 §2.1 補錄 `allLiquidation.{symbol}` 完整 schema
3. C1 PASS 後 production builder revival 必經 BB review + UnknownHandlerGuard 串接（per 2026-05-08 memory v1.10 follow-up）

**Out of BB scope**：
- MIT schema delta pre-review（design §4，正確 deferred）
- A3 / E2 / E4 對抗審查（design §10）
- PM unified sign-off（design §10）

### 8.4 16 根原則 + 硬邊界 合規

| 維度 | 評估 |
|---|---|
| 原則 1 單一寫入口 | N/A（read-only WS probe） |
| 原則 4 策略不能繞過風控 | N/A |
| 原則 6 失敗默認收縮 | ✅ reconnect/restart budget 用盡 → FAIL verdict（非 silent continue） |
| 原則 8 交易可解釋 | ✅ per-hour checkpoint + ReconnectEvent + RestartEvent 全紀錄 |
| 原則 10 認知誠實 | ✅ 8 verdict 分類顯式區分 |
| 原則 14 零外部成本 | ✅ 0 paid API |
| DOC-08 §12 9 不變量 | 0 觸碰 |
| 硬邊界 5 gate | 0 觸碰（不動 live_execution / max_retries / execution_authority / authorization.json / OPENCLAW_ALLOW_MAINNET） |

**合規評級**：A 級（16/16 + 硬邊界 0 觸碰 + 5-gate live boundary 0 觸碰）

---

## §9 Bybit changelog 最近 30d (2026-04-16 ~ 2026-05-16)

從 `https://bybit-exchange.github.io/docs/changelog/v5` 直 fetch：

| Date | 變動 | OpenClaw 影響 |
|---|---|---|
| 2026-05-14 | Bybit Card & Affiliate updates / SBE Order Entry XML template / `retMsg` varString8→varString16 / Removed `createAt` from BatchCreateRespV5 | 0（OpenClaw 不用 Bybit Card / SBE binary protocol） |
| 2026-05-07 | Earn Get Staked Position 新增 `availableAmount` / `freezeDetails` field | 0（OpenClaw 不用 Earn product） |
| 2026-05-06 | Crypto Loan Create Supply 新增 `availableSource` / Cancel Supply 新增 `refundedAccount` | 0（OpenClaw 不用 Crypto Loan） |

**0 breaking changes** to public WebSocket topics（allLiquidation / connection limits / idle timeout / rate limits）。

**Verdict**：30d changelog 對 v2 proof + W-AUDIT-8a C1 路徑 0 影響。

---

## §10 政策合規度 + Bybit-side Overall

### 10.1 技術合規度：**97%**（Sprint N+0/N+1 baseline 持平）

W-AUDIT-8a C1 v2 harness 0 endpoint 改動 / 0 字典 drift / 0 retCode handler 改動。

### 10.2 政策合規度：**70%**（與 v3 持平）

M5-1 / M5-2 12+ day 0 進展（per 2026-05-10 / 2026-05-11 memory）。Mainnet 解鎖前 mandatory。**對 C1 v2 proof 0 影響**（純 read-only public WS）。

### 10.3 0 ship-stop blocker

### 10.4 Bybit-side 整體評級

**APPROVE-CONDITIONAL** with 3 LOW advisory (A-1 / A-2 / A-3)。E1 IMPL 設計符合 Bybit V5 docs 推薦 best practice 主軸，2 個 deviation（ping=10s + base=1s）均非 ToS 觸碰 / 非 IP throttle 觸碰 / 非 backpressure 觸發。

---

## §11 下次啟動需查驗項

1. C1 24h v2 proof 結果（PASS_C1_PROOF_CANDIDATE / FAIL_*） — operator 啟動後 BB sign-off invariant 4 條驗
2. v2 ping_interval = 10s（A-1）是否 operator 偏好維持或改 20s
3. v2 reconnect base = 1s（A-2）是否 v2.1 改 3s 統一 production
4. W-AUDIT-8a Phase C IMPL kickoff 期字典 §2.1 `allLiquidation.{symbol}` 完整補錄（A-3）
5. Future 訂多 symbol（W-AUDIT-8c 25-sym liquidation cluster）時 cross-symbol multiplexing 跨 connection 行為驗證

---

## §12 完成序列 checklist

- ✅ 啟動序列：BB profile + memory + 最新 report + design plan + v1 source + v2 source + 字典 §2.1 + §4.1 + V5 official docs（連接 + allLiquidation + changelog 30d）
- ✅ 5 focus pre-review 全跑
- ✅ 100% read-only（0 改 dict / 0 改 代碼 / 0 改 config / 0 spawn 第二層 sub-agent / 0 啟動 real probe）
- ✅ 4 待答 BB-side answers 全給
- ✅ Sign-off block + 3 advisory + 0 ship-stop
- ✅ 30d changelog 補錄
- ✅ 16 根原則 + 硬邊界 0 觸碰確認

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_bb_pre_review.md
