# Track E3 — Maker Fill Rate Empirical Baseline (entry path, 7d)

- 日期: 2026-05-15
- Wave: PM Wave 1 並行 5/N — read-only PG audit
- Author: PA
- Scope: EDGE-P2-3 Phase 1b close-maker-first refactor 4-agent review BB-SF-2 證據基礎；entry maker（已實裝）真實 baseline
- Mode: read-only PG query on `trade-core` Linux runtime；不動 paper_state / config / TOML
- Context window: `ts >= NOW() - INTERVAL '7 days'`，`engine_mode IN ('demo', 'live_demo')`，entry-only（`fills.entry_context_id IS NULL`）

---

## §1 Query 範圍 + Source tables

### Source schema 真實採樣
從 PG 直接 reflect 確認：

| 表 | 用途 | 關鍵欄位 |
|---|---|---|
| `trading.intents` | strategy → intent | `intent_id, ts, engine_mode, strategy_name, symbol, side, qty, price, order_type` |
| `trading.orders` | dispatched orders | `order_id, ts, intent_id, symbol, side, order_type, time_in_force, status, engine_mode, strategy_name, category, is_paper` |
| `trading.fills` | actual fills | `fill_id, order_id, ts, qty, price, fee, fee_rate, liquidity_role, fill_latency_ms, slippage_bps, entry_context_id, exit_source, exit_reason, engine_mode, strategy_name` |
| `trading.order_state_changes` | order state machine transitions | `order_id, ts, from_status, to_status, reason, engine_mode` |
| `trading.risk_verdicts` | Guardian per-intent verdict | `intent_id, verdict, risk_level, reason` |

### 重大 schema caveat（影響後續 measurement）
- **`orders.intent_id` 100% NULL** in 7d window：1394 demo orders / 1021 live_demo orders 全部 `intent_id IS NULL`。`orders` writer 沒回填 intent_id。意味：無法走 `intents → orders` join 算 Guardian-pass-rate；只能從 `orders.order_id` 起點往下算。
- **`orders.status` 100% `Working`**：sql 直查 `Working` 1394 (demo) / 1021 (live_demo)，但 `order_state_changes.to_status` 有完整 `Filled / Cancelled / Rejected / PartiallyFilled / Failed`。`orders.status` 是 fire-and-forget 初始狀態，沒回寫；真實終態須從 `order_state_changes` 拿。
- **`details` jsonb null**: `orders.details = null`，沒 client-side metadata 可區分 entry/close。改用 `fills.entry_context_id` 區分（entry → NULL、close → NOT NULL）。
- **Order ID pattern 區分**: `oc_dm_*` = demo entry PostOnly Limit（grid/ma/bb 本體）；`oc_risk_dm_*` = risk-driven Market（多為 close / 停損）。
- 環境覆蓋：`live` engine_mode 7d 內 0 orders / 0 fills（正確 — 真 live 未授權）；只有 `demo` + `live_demo`。

### 查詢窗口內統計（7d）

| engine_mode | orders | fills | order_state_changes |
|---|---|---|---|
| demo | 1394 | 571 (entry 292, close 279) | 多 transition rows |
| live_demo | 1021 | 415 (entry 209, close 197) | — |

---

## §2 Entry maker funnel（entry-only PostOnly Limit）

### Per-status terminal classification（同一 order 可同時跑過 Filled+Partial）

#### demo PostOnly Limit entry 1057 submitted
| Outcome 邏輯組合 | n | % |
|---|---|---|
| Filled-only（true full-fill）| 255 | 24.1% |
| Filled + Partial（先部分後全填）| 7 + 1 = 8 | 0.8% |
| Filled + Cancelled（race / 多次嘗試）| 2 | 0.2% |
| PartiallyFilled-only（不完全成交終止）| 48 | 4.5% |
| **Cancelled-only**（PostOnly timeout self-cancel）| **741** | **70.1%** |
| 無 transition（writer race / 未終結）| 3 | 0.3% |
| **Total** | **1057** | 100% |

#### live_demo PostOnly Limit entry 770 submitted
| Outcome | n | % |
|---|---|---|
| Filled-only | 166 | 21.6% |
| Filled + Partial | 4 | 0.5% |
| PartiallyFilled-only | 50 | 6.5% |
| **Cancelled-only** | **544** | **70.6%** |
| 無 transition | 6 | 0.8% |
| **Total** | **770** | 100% |

### 從 fills 表 cross-check
| env | fills entry maker | fills entry taker | fills entry unknown | maker / total |
|---|---|---|---|---|
| demo | 276 | 15 | 1 | **94.5%** |
| live_demo | 195 | 13 | 1 | **93.3%** |

> 解讀：**fill 出來的 entry 確實 ~94% 是 maker**（spec §1.2 假設成立 conditional on fill），但 **per submitted PostOnly Limit 只有 26% 真的 fill**（含 partial）；剩下 70% PostOnly 是 self-cancel timeout。Spec 4.5 bps 假設用的是 fill-conditional rate 還是 submitted rate 影響很大；下節計算。

### Entry Market（taker，少數 risk-close path 入帳此分類）
| env | submitted | filled |
|---|---|---|
| demo | 65 | 62 (95.4%) |
| live_demo | 64 | ≈63 |

---

## §3 Latency 統計

### Entry maker fill latency（order create → first fill ack）
| env | p50 | p90 | p99 | avg | n |
|---|---|---|---|---|---|
| demo | **6,617 ms** | 35,699 ms | 46,115 ms | 12,234 ms | 276 |
| live_demo | **8,117 ms** | 33,842 ms | 43,303 ms | 12,391 ms | 195 |

`fill_latency_ms` column（API 上報）和 timestamp diff 一致 → trust 高。

### Cancel latency（Working → Cancelled，包含 self-cancel timeout）
| env | p50 | p90 | p99 | avg | n |
|---|---|---|---|---|---|
| demo | **45,192 ms** | 49,445 ms | 50,032 ms | 36,546 ms | 743 |
| live_demo | **45,190 ms** | 49,500 ms | 50,054 ms | 37,516 ms | 547 |

> 強烈訊號：**engine 用 ~45s timeout 自然 cancel PostOnly**。p50/p90/p99 高度集中 ~45-50s 一致 → 是 timer 觸發，不是 exchange-driven。

### 意涵
- 70% 的 PostOnly Limit 等 45s 沒 fill，被 engine 自取消
- 26% 在 ~6.6s p50 內 fill 成功
- p90 fill 35s（接近 cancel timeout）→ **timeout 實際上 cut off 了 ~10% 本來可能 fill 但慢的 order**

---

## §4 Reject category breakdown（demo + live_demo 7d）

| Reason | n | % of cancels/rejects |
|---|---|---|
| `EC_PerCancelRequest \| category=self_cancel` | 1054 | **78.6%** |
| `EC_PostOnlyWillTakeLiquidity \| category=post_only_cross` | 268 | **20.0%** |
| `OrderLinkedID is duplicate` (retCode=110072) | 19 | 1.4% |
| `close dispatch timed out after 500ms` (retCode=10019) | 1 | <0.1% |
| **Total** | **1342** | 100% |

關鍵：
- `EC_PerCancelRequest|self_cancel` = engine 主動 cancel（45s timeout 為主，可能含 risk-close 撤單），**最大宗**
- `EC_PostOnlyWillTakeLiquidity` = exchange 拒絕 PostOnly 因會跨 spread → 真正的 PostOnly cross reject，**~20%**
- `OrderLinkedID duplicate` = client_order_id race，邊角

→ 沒有 `TooManyPending` / `ReachMaxOpenOrderQty`（spec §1.2 假設可能 exposure）→ 不是當前 bottleneck

---

## §5 Per-strategy table（demo + live_demo PostOnly Limit entry 7d）

| strategy | env | submitted | filled (incl. partial) | fill rate | self-cancel | PO cross |
|---|---|---|---|---|---|---|
| grid_trading | demo | 936 | 253 | **27.0%** | 674 (72.0%) | 109 (11.6%) |
| ma_crossover | demo | 117 | 55 | **47.0%** | 62 (53.0%) | 47 (40.2%) |
| bb_breakout | demo | 4 | 2 | 50.0% | 2 | 2 |
| grid_trading | live_demo | 703 | 190 | **27.0%** | 507 (72.1%) | 75 (10.7%) |
| ma_crossover | live_demo | 67 | 28 | **41.8%** | 39 (58.2%) | 29 (43.3%) |

5 textbook 策略中 7d entry 統計：
- `grid_trading` — 主力（demo 936 / live_demo 703 PostOnly entry）
- `ma_crossover` — 次要（demo 117 / live_demo 67），但 fill rate 高 41-47%（grid 是 27%）
- `bb_breakout` — 4 sample，提示性低
- `bb_reversion` — 7d 無 entry（per §三 sample 4）
- `funding_arb` — dormant（per §三）

### 觀察
1. **grid_trading fill rate 27%** vs **ma_crossover 47%**：grid 在更窄價差網格放 PostOnly，cross 概率高 → 更易 timeout；ma_crossover 訊號更稀疏，掛在更深 level，反而成交率高
2. PO cross 比例：ma_crossover 40%+ 是 strategy issue（價格定太貼），值得分析；grid 11% 較合理
3. Per-symbol（demo grid_trading top 10）fill rate 8.9%（ICPUSDT）to 44.4%（SUIUSDT）— 9-50% 高 variance，依 spread / depth / volatility 不同顯著差異

---

## §6 Effective savings 計算

### Bybit fee tier 0 baseline（per W-AUDIT-8a + Bybit official）
- Maker (PostOnly fill): **2.0 bps**
- Taker (Market): **5.5 bps**
- Spread saving (potential): 5.5 - 2.0 = **3.5 bps per side**

### 公式
```
effective_savings_per_attempted_entry =
    fill_rate × (taker_bps - maker_bps)         // ← saving when filled
  - fallback_taker_cost                         // ← if cancelled then re-dispatch as taker
  - missed_alpha_cost                           // ← if cancelled with no re-attempt: opportunity loss
```

### 兩種解讀

#### 解讀 A — Conditioned on fill（spec §1.2 隱含的最樂觀讀法）
- maker fill rate per fill (entry) = 94.5% (demo) / 93.3% (live_demo)
- savings per filled entry = 0.945 × 3.5 = **3.31 bps** (demo)
- savings per filled entry = 0.933 × 3.5 = **3.27 bps** (live_demo)

→ Spec 4.5 bps **overstates by 1.0-1.2 bps** under best-case interpretation

#### 解讀 B — Per submitted attempt（更接近 portfolio realized impact）
- demo grid: 27% fill rate × 3.5 bps = **0.95 bps per attempt**（73% 沒 fill 等於沒 saving 也沒 cost，但 missed entry 機會）
- demo overall（grid + ma weighted）: ~28% × 3.5 = **0.98 bps per attempt**

→ Spec 4.5 bps **overstates by 4.5x** under conservative interpretation

#### 解讀 C — 折中（assume engine 有 fallback to taker）
**注意**：empirical 沒看到 fallback to taker（per intent_id 1:1 對應 1 order，無「Limit cancelled → 同 intent 後續 Market」pattern；當前 engine 似乎沒有 timeout-fallback 機制，只有 ipc_close_symbol risk-close 用 Market）

如未來實作 fallback:
- 假設 27% maker fill (saving 3.5 bps) + 73% taker fallback (cost 0 vs taker baseline)
- savings per attempt = 0.27 × 3.5 - 0 = **0.95 bps**
- 雖然 fill 率提升至 100%，但 saving 限縮在 27%

如保留 70% no-fill（當前 behavior）:
- 27% PostOnly fill + 73% no-fill (entry abandoned) = 0.95 bps **plus** opportunity cost（無法量化）

---

## §7 對照 spec §1.2 「4.5 bps」估算

### 證實 / 修正
**Spec §1.2 4.5 bps overstates**。修正建議：

| 解讀層 | empirical 數字 | 說明 |
|---|---|---|
| 最樂觀（fill-conditional, baseline maker rate）| **3.27-3.31 bps** | 條件成立：當 fill 發生時 ~94% 是 maker；spec 4.5 vs empirical 3.3 = overstate 1.2 bps（27%）|
| 中性（per submitted, with fallback assumption）| **0.95 bps** | 當前 engine 27% PostOnly fill rate；無 fallback to taker；剩 73% 等於 missed entry |
| 悲觀（per submitted with realistic taker fallback）| **0.95 bps** | 同上，加 fallback 也只回到 27% × 3.5 = 0.95 |

### BB-SF-2 修正建議
**接受 BB-SF-2「effective saving ≤ 3.5 bps」結論。修正後上限為 3.31 bps（demo fill-conditional 最樂觀）**，且該數字**只在「close 與 entry fill behavior 類似」假設下成立**——下節 §8 對此 push back。

### 推薦 spec patch
```diff
-§1.2: maker fill saving ≈ 4.5 bps (assumed 95% maker fill rate)
+§1.2: maker fill saving ≈ 3.0-3.3 bps (empirical: 94% of close fills will be maker
+   conditional on fill; per Bybit fee tier 0 maker 2.0 bps vs taker 5.5 bps).
+   PostOnly per-submitted fill rate = 27% (entry baseline, demo grid_trading 7d);
+   if 70% of close PostOnly attempts get cancelled by 45s timeout, missed-exit
+   alpha decay must be subtracted before claiming any net saving.
```

---

## §8 對 close path 的 prediction（與 entry 的差異）

### 結構性差異
| 維度 | Entry (existing) | Close (close-maker-first proposal) |
|---|---|---|
| 方向 | 開倉，無持倉壓力 | 已持倉，有 P&L 風險 |
| 時效敏感 | 中（grid 等網格訊號可錯過下根 K-line）| **高**（exit signal 慢一點 = alpha 反向 / stop-out）|
| 信號性質 | 主動入場 | 信號驅動（regime shift / signal exit / stop） |
| 成本類別 | bps 可量化 | bps + missed exit alpha decay（不易量化）|
| 流動性方向 | bid-side（買）/ ask-side（賣）任一可選 | 通常**和當前 trend 同向**（多單平→賣盤、空單平→買盤）|

### Empirical close-path 當前狀態
- 100% close fills 是 taker（demo 272 / live_demo 192）
- demo close avg slippage = **2.26 bps**，p50 = 1.14 bps
- live_demo close avg slippage = **4.20 bps**，p50 = 2.07 bps

→ close path 已付出 ~5.5 bps taker fee + ~2-4 bps 滑點 = **~7-10 bps total close cost**。close-maker-first 若能省 3-3.5 bps，**relative impact 為 30-40%**，這是顯著的；但須減去 close timeout missed alpha。

### Conservative discount 建議（YES）
**強烈推薦 close-maker-first 改動採用 25-40% conservative discount**，理由：

1. **45s timeout 對 close 致命**：entry 的 PostOnly 若 45s 沒 fill 就 timeout 丟棄，問題是 missed entry，無持倉風險；close 若 45s 沒 fill，**持倉繼續暴露**，alpha 可能反向（mean revert exit signal 等 45s = 信號可能失效）

2. **Trend-side liquidity 差**：grid 平多單 = 賣 ask-side maker，當趨勢向下（觸發 exit reason 之一）時 ask-side 流動性更稀，PO cross 可能 >20%（vs entry 的 11%）

3. **Empirical 估計範圍**：`grid` entry maker rate **27%**；close 預測在 **15-25%**（更難 fill），對應每次 close attempt savings ≈ 0.20 × 3.3 = **0.66 bps**（per submitted）

4. **不確定性**：close path empirical = 0（從未 close maker）；任何估算都是 entry baseline 推論。**先驗**：close fill rate 不會比 entry 好；可能等於或差。

### 推薦 spec/AMD 修正
```diff
-§1.2 maker fill saving 4.5 bps net per close
+§1.2 maker fill saving:
+   - upper bound (fill-conditional, Bybit fee saving): ~3.3 bps
+   - empirical entry baseline: 27% PostOnly fill rate over 45s timeout (demo grid 7d)
+   - close-path conservative: assume 20% PostOnly fill rate (close worse than entry by ~25%)
+   - effective per-attempt close saving: ~0.66 bps (vs 4.5 bps spec assumption: 6.8x overstate)
+   - Pre-fail-closed gating: require 14d empirical close-maker fill rate >= 30%
+     before declaring close-maker-first net positive.
```

---

## §9 Sign-off 必交付摘要

### 證實
- Entry fills **conditional on filling** are 94% maker（spec §1.2 假設成立 conditional）
- Bybit fee saving cap = 3.5 bps（5.5 taker - 2.0 maker）

### 修正
- Spec §1.2 「4.5 bps net saving per close」**overstated**：
  - Best case (fill-conditional + close = entry behavior): **3.31 bps**
  - Realistic (close fill rate = entry × 0.75 conservative): **0.66 bps per attempt**
  - 跟 spec 4.5 bps 對比 overstate 27%-680%（看解讀層）

### 範圍給多少 bps（per BB-SF-2）
**0.5-3.3 bps per close attempt**，建議 spec 改用 **conservative range 0.5-2.0 bps net** 並要求**真實 close-maker pilot 14d empirical 30%+ fill rate gate** 後才能 declare positive。

### 對 close path prediction
- Close 比 entry 更難 maker fill（trend-side liquidity 偏弱、45s timeout 對 exit 致命）
- 建議採 25-40% conservative discount
- **強烈推薦 close-maker-first 部署需有 fallback to taker 機制**（避免 45s 持倉暴露）+ 較短 timeout（建議 5-15s）+ pilot 14d 觀察期再 promote

---

## §10 附錄：execution evidence

### Healthcheck-style 直查 SQL（供後續 reproduce）
```sql
-- entry PostOnly funnel per strategy
WITH ord AS (
  SELECT order_id, strategy_name, engine_mode
    FROM trading.orders
   WHERE ts >= NOW() - INTERVAL '7 days'
     AND engine_mode IN ('demo','live_demo')
     AND order_type = 'Limit' AND time_in_force = 'PostOnly'
),
sc AS (
  SELECT order_id,
         BOOL_OR(to_status = 'Filled') AS filled,
         BOOL_OR(to_status = 'PartiallyFilled') AS partial,
         BOOL_OR(to_status = 'Cancelled') AS cancelled
    FROM trading.order_state_changes
   WHERE ts >= NOW() - INTERVAL '7 days'
     AND engine_mode IN ('demo','live_demo')
   GROUP BY order_id
)
SELECT ord.engine_mode, ord.strategy_name,
       COUNT(*) AS submitted,
       SUM(CASE WHEN sc.filled OR sc.partial THEN 1 ELSE 0 END) AS any_fill,
       100.0 * SUM(CASE WHEN sc.filled OR sc.partial THEN 1 ELSE 0 END) / COUNT(*) AS fill_rate
  FROM ord LEFT JOIN sc ON sc.order_id = ord.order_id
 GROUP BY ord.engine_mode, ord.strategy_name
 ORDER BY submitted DESC;
```

### 確認 sample row
```
demo PostOnly entry: oc_dm_1778882760518_22 → ts=now-Xms, intent_id=NULL
demo Market risk-close: oc_risk_dm_1778881738502_19 → ts=now-Xms, intent_id=NULL
demo Cancelled reason: 'exchange_status:Cancelled|reject=EC_PerCancelRequest|category=self_cancel'
```

---

## 完成序列 trail

1. 啟動：讀 PA profile + reports listing；memory 過大（299KB）skip 全載
2. SSH bridge 驗證 PG schema → 16 個 trading tables 確認
3. funnel 5 round query：status × type × is_close × strategy × symbol
4. latency 2 round：fill / cancel
5. reject 2 round：reason × strategy
6. saving formula 計算（fee tier 0 + 3 解讀層）
7. close-path differential analysis + conservative discount 推薦
8. Report 寫入 → commit 走 `git commit --only`（per `feedback_git_commit_only_for_metadoc`）

## 不在此 scope（後續 task）
- close path actual implementation（not yet implemented；本報告為 entry baseline only）
- IMPL fix（read-only audit）
- AMD / spec patch（Track A1 PA 並行 — 本報告提供建議供其引用）
- 未來 14d close-maker pilot 觀察期（需另開 ticket）
