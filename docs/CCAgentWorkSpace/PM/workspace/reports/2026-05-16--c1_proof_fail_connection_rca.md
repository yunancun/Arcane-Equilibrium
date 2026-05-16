# C1 Proof FAIL_CONNECTION — RCA + Next Step

## 一、任務摘要

W-AUDIT-8a Phase C1 isolated 24h Bybit WS probe (PID `4100789`, start `2026-05-15T19:53:09Z`) **FAIL_CONNECTION** at `2026-05-16T00:37:25Z`，跑了 `17055.2s / 86400s` (~4.7h / 24h)。

本 RCA 從 trade-core probe report + nohup log 確認真實原因，建議下一步。

## 二、修改清單

- 本 report：`.claude_reports/20260516_c1_proof_fail_connection_rca.md`（新建）
- 不重啟 probe（需 operator 確認 + 確認 root cause 是 client-side 還是 Bybit-side 才可重跑）
- 不改 production WS subscription（C1 revival 待 BB/MIT sign-off）

## 三、關鍵 diff / 真實狀態

### 3.1 Probe verdict 全文

```
Verdict: FAIL_CONNECTION
C1 proof eligible: False
C1 blocker: The isolated WS connection did not complete the requested window.
URL: wss://stream.bybit.com/v5/public/linear
Candidate topic: allLiquidation.BTCUSDT
Requested duration sec: 86400
Observed duration sec: 17055.2
Subscribe success/failure: 822 / 0
Ping/pong: 851 / 821
```

### 3.2 Topic Counts（觀察期 4.7h）

| Topic | Count | Last seen UTC |
|---|---:|---|
| `allLiquidation.BTCUSDT` | **15** | `2026-05-16T00:04:41Z` |
| `kline.1.BTCUSDT` | 8458 | `2026-05-16T00:27:31Z` |
| `orderbook.50.BTCUSDT` | 454010 | `2026-05-16T00:27:32Z` |
| `publicTrade.BTCUSDT` | 43161 | `2026-05-16T00:27:31Z` |
| `tickers.BTCUSDT` | 85580 | `2026-05-16T00:27:32Z` |

### 3.3 唯一 Connection Error

```
recv failed: WebSocketConnectionClosedException: Connection to remote host was lost.
```

### 3.4 Candidate sample 證實 topic 真實 alive

```json
{
  "topic": "allLiquidation.BTCUSDT",
  "type": "snapshot",
  "ts": 1778875542288,
  "data": [{"S":"Buy","T":1778875541877,"p":"78673.30","s":"BTCUSDT","v":"0.001"}]
}
```

15 個事件含正確 Bybit V5 schema：`S` (Side) / `T` (timestamp) / `p` (price) / `s` (symbol) / `v` (volume)。

## 四、RCA — Root Cause 三層判定

### Layer 1: Topic & Subscription — ✅ PASS

- subscribe 成功 822 次 / 失敗 0 次
- `allLiquidation.BTCUSDT` 真實有 15 個事件入 buffer
- 數據格式 100% 符合 Bybit V5 spec
- **topic 本身有效，subscription 機制正常**

### Layer 2: Connection Stability — ❌ FAIL

- Ping/pong 851/821（pong < ping 30 次差距 = 部分心跳被遠端 swallow）
- 4.7h 後 `recv` 拋 `WebSocketConnectionClosedException: Connection to remote host was lost`
- 屬於 Bybit 端主動斷或網路瞬斷
- 探針本身**無 auto-reconnect 邏輯**（探針是 single-attempt single-connection design per spec — 為了「proof eligibility」要求 24h 單一連接連續無中斷）

### Layer 3: Bybit demo / mainnet 政策 — 未確認

- URL `wss://stream.bybit.com/v5/public/linear` 是 **mainnet public WS**（非 demo `stream-demo.bybit.com`）
- Bybit V5 public WS 無 24h hard limit 文件記載，但實務上週期性 disconnect 常見
- 字典手冊 `docs/references/2026-04-04--bybit_api_reference.md` 未提及 24h 連續上限

**綜合 verdict**：**Layer 2 connection drop 是 root cause**。Bybit 端主動關閉 long-lived public WS 是已知行為（無 SLA 保證 24h 單一 connection），探針設計上強要 single-connection 24h 無中斷與 Bybit 實務不符。

## 五、治理對照

- CLAUDE.md §三：W-AUDIT-8a Phase C1 24h proof running → 已 **FAIL 2026-05-16T00:37:25Z**，§三 已 stale
- TODO §11.5 EDGE-P2-3 Phase 1b 3-gate 之 W-AUDIT-8a C1 → **未解 + 重跑前 root cause 待 BB 確認**
- BB authority：Bybit-side WS 政策由 BB agent 審查；C1 revival 仍待 BB/MIT sign-off

## 六、不確定之處

1. **Bybit demo vs mainnet WS 上限差異**：`stream-demo.bybit.com` 是否有 24h 限制不確；本探針用 mainnet 而非 demo（topic 在 mainnet 有 funding；demo 是否提供 `allLiquidation` 不確）
2. **`recv` 拋的具體 close code**：log 未捕 WS close frame（如 1006 = abnormal closure / 1011 = server error / 1012 = service restart），無法判 Bybit 主動 vs 中間網路斷
3. **Probe 是否該加 reconnect 是 spec 問題**：probe 原 spec `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md` 要求 single-connection 24h；若改成 reconnect-aware proof 需重審 acceptance criteria

## 七、建議下一步

### Option A — Spec-revised probe（建議）

1. BB review：`single-connection 24h` 是否合理 acceptance（vs Bybit 實務 connection lifecycle）
2. 若 BB 允許 reconnect-aware proof：改 probe 加 auto-reconnect + 累計 86400s 觀察時間 + 記錄每段 disconnect duration / cause
3. 重跑

### Option B — 切 Bybit demo WS 重跑

1. 改 URL `wss://stream-demo.bybit.com/v5/public/linear`
2. 若 demo 不提供 `allLiquidation` topic → revert mainnet
3. 重跑 24h

### Option C — 接受 4.7h partial sample 為 evidence

1. 15 個 `allLiquidation` 事件 + 0 subscribe failure + 0 schema error 為 **partial PASS evidence**
2. 與 BB 商議降 acceptance 至「8h cumulative + topic schema verified」
3. 若 BB 同意 → C1 可標 CONDITIONAL PASS pending acceptance amendment

### Option D — Wave delay

C1 revival defer Sprint N+3+，先做 W-AUDIT-8b read-only Stage 0R query/report packet（CLAUDE.md §三 / TODO §11.5 already next step）

### Operator 下一步

選 A/B/C/D 之一 → BB review → 派 E1 改 probe 或關閉 ticket。

**建議優先 A**（reconnect-aware probe）— acceptance 改後重跑成本小，仍能對齊「24h cumulative observation」之原意。
