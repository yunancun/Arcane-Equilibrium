# P2-ORDERS-INTENT-ID-BACKFILL-1（design memo only）

Date: 2026-05-19
Role: E1
Status: **DESIGN ONLY — DO NOT EXECUTE**（需 operator + MIT review）
Trigger: dispatch §「Step 5 — backfill diagnostic（optional, design only）」

## 1. 目的

恢復 E3 baseline（2026-05-15 commit `b98706d5`）揭露的 7d 1394 demo orders +
1021 live_demo orders 之 `trading.orders.intent_id` 100% NULL，使
`trading.intents → trading.orders` JOIN 可重建 Guardian-pass-rate 業務 KPI。

writer 修復見另一份報告（同日 wave 1.5 ticket P2-ORDERS-INTENT-ID-WRITER-GAP-1
施工）；本 memo 只處理「歷史已寫入但 intent_id NULL」的補回。

## 2. 可行性分析

### 2.1 同 tick 確定性 id 規則

寫入器修復前後，entry path 的 intent_id 構造均為：

```text
intent_id = format!("intent-{em}-{symbol}-{ts_ms}")
```

`em` ∈ {paper, demo, live, live_demo}，`symbol` ∈ {BTCUSDT, ETHUSDT, ...}，
`ts_ms` = `event.ts_ms`（tick 時間）。

`trading.intents.intent_id` 與 entry order 的 `trading.orders.ts`
（毫秒精度 = `po.sent_ts_ms`，由 dispatch.rs:534 `now_ms = openclaw_core::now_ms()`
而非 event.ts_ms）**並非完全相等**：

- `trading.intents.ts` = `event.ts_ms`（tick 時間）→ 由 `make_intent_id` 編碼
- `trading.orders.ts` = `po.sent_ts_ms = openclaw_core::now_ms()`（dispatch
  排入 channel 的 wall clock）

兩 ts 之間有處理延遲（μs ~ ms 級）。因此：

- `intent_id` 字串本身可以**獨立**重建（從 intents 抓 intent_id token）
- 用 `intents.intent_id` 的 ts 部分 + symbol + engine_mode 對齊 orders
  必須採「±N ms 視窗」+「最近鄰匹配」+「strategy_name 過濾」

### 2.2 候選 JOIN key（按嚴格度遞減）

| 方案 | JOIN 邏輯 | 風險 |
|---|---|---|
| **A：order_id-prefix 強匹配** | orders.order_id 形如 `oc_{em_tag}_{ts}_{seq}`，從 order_link_id 反推 dispatch ts；但 prefix 不含 symbol → 仍須 symbol JOIN | 安全 |
| **B：時間視窗最近鄰** | `WHERE intents.symbol = orders.symbol AND intents.engine_mode = orders.engine_mode AND orders.ts BETWEEN intents.ts AND intents.ts + interval '5 seconds' AND orders.strategy_name = intents.strategy_name` 選最早一筆 orders | 可能 multi-match：同 symbol 同 strategy 1 秒內若有兩筆 intent → 第二筆 order 可能誤匹配第一筆 intent |
| **C：JOIN by closely-tagged event ts** | 從 `orders.ts` 推 `event.ts_ms` 不可靠（無前向映射） | 不可行 |

**推薦 B + 約束**：5 秒視窗 + strategy_name 必相等 + 同 symbol 同 em；
multi-match 由 `ORDER BY (orders.ts - intents.ts) ASC LIMIT 1` 解（最早匹配優先）。

### 2.3 SQL 草稿（不執行）

```sql
-- DRY-RUN ONLY — review by MIT + operator before any UPDATE。
-- 預期：1394 + 1021 = 2415 candidate rows；實際匹配率視 strategy/symbol/ts
-- 視窗稀疏度而定，預估 80-95% 可補（無 intent 對應的孤兒 order 來自 close /
-- ipc / orphan 路徑 → 屬正常 NULL，不需補）。

WITH candidates AS (
    SELECT
        o.order_id,
        o.ts AS order_ts,
        o.symbol,
        o.engine_mode,
        o.strategy_name AS order_strategy,
        i.intent_id,
        i.ts AS intent_ts,
        i.strategy_name AS intent_strategy,
        ROW_NUMBER() OVER (
            PARTITION BY o.order_id, o.ts
            ORDER BY (o.ts - i.ts) ASC
        ) AS match_rank
    FROM trading.orders o
    JOIN trading.intents i
      ON i.symbol = o.symbol
     AND i.engine_mode = o.engine_mode
     AND i.strategy_name = o.strategy_name
     AND o.ts >= i.ts
     AND o.ts <= i.ts + interval '5 seconds'
    WHERE o.intent_id IS NULL
      AND o.engine_mode IN ('demo', 'live_demo')  -- 對齊 E3 baseline 範圍
      AND o.ts >= NOW() - interval '8 days'        -- 給 E3 7d 視窗加 1 天 buffer
      -- 排除 close / ipc / orphan order：strategy_name prefix 篩
      AND o.strategy_name NOT LIKE 'strategy_close:%'
      AND o.strategy_name NOT IN (
          'ipc_close_all',
          'risk_close:ipc_close_symbol',
          'risk_close:halt_session',
          'unattributed:bybit_auto'
      )
)
SELECT
    COUNT(*) FILTER (WHERE match_rank = 1) AS matched,
    COUNT(*) FILTER (WHERE match_rank = 1 AND intent_id IS NOT NULL) AS will_backfill,
    COUNT(DISTINCT (order_id, order_ts)) AS unique_orders,
    -- 多匹配揭露（debug）
    MAX(match_rank) AS max_dup_count
FROM candidates;
```

### 2.4 UPDATE 草稿（DO NOT EXECUTE）

```sql
-- ⚠️ DO NOT EXECUTE — design only。
-- 必須先跑 SELECT 確認 matched count 合理、max_dup_count = 1 或近 1，
-- 再經 operator + MIT review；建議分批執行 (LIMIT 100) + 完整 logging。
-- TimescaleDB hypertable UPDATE 須測試 chunk-level lock 行為。

BEGIN;
WITH candidates AS (
    SELECT
        o.order_id,
        o.ts AS order_ts,
        i.intent_id,
        ROW_NUMBER() OVER (
            PARTITION BY o.order_id, o.ts
            ORDER BY (o.ts - i.ts) ASC
        ) AS match_rank
    FROM trading.orders o
    JOIN trading.intents i
      ON i.symbol = o.symbol
     AND i.engine_mode = o.engine_mode
     AND i.strategy_name = o.strategy_name
     AND o.ts >= i.ts
     AND o.ts <= i.ts + interval '5 seconds'
    WHERE o.intent_id IS NULL
      AND o.engine_mode IN ('demo', 'live_demo')
      AND o.ts >= NOW() - interval '8 days'
      AND o.strategy_name NOT LIKE 'strategy_close:%'
      AND o.strategy_name NOT IN (
          'ipc_close_all',
          'risk_close:ipc_close_symbol',
          'risk_close:halt_session',
          'unattributed:bybit_auto'
      )
)
UPDATE trading.orders o
SET intent_id = c.intent_id
FROM candidates c
WHERE o.order_id = c.order_id
  AND o.ts = c.order_ts
  AND c.match_rank = 1;
-- ROLLBACK; -- safe default until reviewed
COMMIT; -- 經 review 後手動切換
```

## 3. 風險與限制

### 3.1 已知限制

1. **5 秒視窗**：若有極端慢 dispatch（網路抖動 + retry），實際延遲可能 >5s；
   建議先以 SELECT-only 跑「視窗放寬至 30s」做 sensitivity check。

2. **strategy_name 嚴格相等**：dispatch.rs:402 構造 PendingOrder 時 `strategy:
   req.strategy.clone()`，直接複製 `OrderDispatchRequest.strategy`；而
   step_4_5_dispatch.rs:868 同樣寫 `strategy: intent.strategy.clone()`，故
   strategy_name 在 entry path 完全一致。但 W1-T2 normalisation 後可能有
   normalize 差異（`build_close_tags_from_legacy`），需 spot-check。

3. **multi-match**：若 ROW_NUMBER OVER 揭露 max_dup_count > 1，代表同
   symbol/strategy/em 在 5s 內有多 intent；此時最早匹配規則仍可能配錯（intent1
   被 cancel、intent2 是真正成交）。MIT 應跑 `count by max_dup_count` 評估
   pollution rate。

4. **TimescaleDB chunk lock**：trading.orders 是 hypertable（V003 line 232），
   大批量 UPDATE 可能 lock 多 chunk；建議分批（per-symbol 或 per-day）。

### 3.2 為何不在 writer 端做 retroactive backfill

- 違反「fail-loud not silent」原則；writer-side 合成 fake id 會遮蓋未來
  upstream bug（PA dispatch 已明令）。
- backfill 屬一次性 data cleanup，不應進 hot path。

## 4. 推薦執行流程（review 後）

1. **MIT review**（quant 視角）：5s 視窗 + strategy 篩選是否會引入 attribution
   bias；ROW_NUMBER tie-break 是否符合「最早匹配」語意。
2. **Operator review**：UPDATE 範圍（demo + live_demo）、不影響 live (現無
   live row 但安全前提)；TimescaleDB UPDATE 對 hot writer 是否需 freeze 窗。
3. **E2 review**：SQL safety（`BEGIN/COMMIT` block / 索引利用情況 /
   `pg_locks` 觀測）。
4. **dry-run**：`EXPLAIN ANALYZE` 在 staging 跑一次；確認 plan 合理。
5. **execute**（運維執行）：optional 分批 + per-batch log 到
   `learning.governance_audit_log`（reason: `P2-ORDERS-INTENT-ID-BACKFILL-1`）。

## 5. 度量

post-backfill 健檢：

```sql
SELECT
    engine_mode,
    COUNT(*) AS total,
    COUNT(intent_id) AS with_intent_id,
    ROUND(100.0 * COUNT(intent_id) / NULLIF(COUNT(*), 0), 2) AS coverage_pct
FROM trading.orders
WHERE ts >= NOW() - interval '8 days'
  AND engine_mode IN ('demo', 'live_demo')
  AND strategy_name NOT LIKE 'strategy_close:%'
  AND strategy_name NOT IN (
      'ipc_close_all',
      'risk_close:ipc_close_symbol',
      'risk_close:halt_session',
      'unattributed:bybit_auto'
  )
GROUP BY engine_mode;
```

預期 entry path coverage_pct >= 80%；若 <80% 反映 (a) intent emit 漏接、
(b) 5s 視窗不足、(c) strategy normalisation drift，需 RCA。

post-writer-fix（go-forward）：

```sql
SELECT engine_mode, COUNT(*) total,
       COUNT(intent_id) with_id,
       ROUND(100.0 * COUNT(intent_id) / NULLIF(COUNT(*), 0), 2) coverage_pct
FROM trading.orders
WHERE ts >= ${writer_fix_deploy_ts}
  AND engine_mode IN ('demo', 'live_demo')
  AND strategy_name NOT LIKE 'strategy_close:%'
  AND strategy_name NOT IN (...)
GROUP BY engine_mode;
```

預期 entry path coverage_pct >= 95%（剩餘 NULL 應是 race / WS retry，
非系統性漏接）。

## 6. 後續

- 本 memo 不執行；需 operator + MIT review 後立 P2-ORDERS-INTENT-ID-BACKFILL-1
  獨立 ticket。
- writer fix（P2-ORDERS-INTENT-ID-WRITER-GAP-1）部署後，至少跑 24h 監測再決定
  是否啟動 backfill；防止「同時改寫 + 補回」造成審計混淆。
- backfill 完成後 `learning.governance_audit_log` 寫單一 marker row：
  `reason='P2_orders_intent_id_backfill_done', ts, rows_updated, max_dup, ...`。

## 7. 不確定 / 求 review 點

1. 5 秒視窗是否合理？需 production trace（intent emit ts → order emit ts
   實際延遲分布）。
2. multi-match tie-break 用「最早匹配」是否會 bias 某些 strategy？需 MIT
   評估。
3. TimescaleDB UPDATE on hypertable 是否影響 live writer 寫入；需 BB
   review chunk_lock 行為。
4. 是否需要為 backfill 標一個 audit flag（如 `details.backfilled_at`）以區分
   原始寫入 vs 補回？目前 design 為純 UPDATE intent_id（不加 details）；若需
   區分可改 `UPDATE ... SET intent_id = c.intent_id, details =
   jsonb_set(COALESCE(details, '{}'::jsonb), '{backfilled_at}',
   to_jsonb(NOW()))`。
