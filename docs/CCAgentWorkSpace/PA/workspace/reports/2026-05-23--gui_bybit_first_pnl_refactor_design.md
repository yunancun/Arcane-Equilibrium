# GUI Bybit-first PnL Refactor Design

- **作者**: PA
- **日期**: 2026-05-23
- **狀態**: DISPATCH READY (4 phase)
- **前置驗證**: PM 已驗 Bybit Demo `/v5/position/closed-pnl` 30/30 valid；OPUSDT GUI -41.03/-18.38 USD = GUI FIFO hallucination；Bybit 真實 -2.61 USD
- **參考**:
  - `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py:1226-1320`（demo/fills 既有實作）
  - `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html:500-840`（demo 前端 PnL 計算）
  - `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:728-744`（既有 get_executions pattern）
  - `srv/rust/openclaw_engine/src/position_manager.rs:424-526`（Rust 端 closed-pnl 既有 parser，可參考字段）
  - `srv/sql/migrations/V003__trading_agent_tables.sql:270-286`（trading.fills schema）
  - `srv/sql/migrations/V005__indexes_views.sql:126`（idx_fills_order_id 存在）
  - `srv/helper_scripts/restart_all.sh:411-480`（engine spawn race）
  - `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--edge_estimate_snapshots_writer_rca.md`（PA report style）

---

## 0. TL;DR

把 PnL ground truth 從「GUI FIFO + PG DB-only」翻轉為「Bybit closed-pnl 為 truth / PG 為 audit trail + 反查 strategy_name + Bybit 故障 fallback」。GUI 從「計算者」降為「純 renderer」。配套 fix restart race、GUI fail-silent、stale data 三軸 UX 防呆。

四 phase 解耦 deploy：

| Phase | 内容 | LOC | 風險 | 獨立性 |
|---|---|---|---|---|
| 1 | restart_all.sh wait_for_engine_socket | ~40 bash | 低 | 完全獨立 |
| 2 | Backend 新 endpoint + TTL cache + reconcile join | ~280 Python | 中 | 完全獨立 |
| 3 | Frontend PnL render 切 Bybit-first | ~120 JS | 中 | 依賴 Phase 2 |
| 4 | Frontend UX 防呆 (stale banner + decay class + ocApi toast + render guards) | ~150 JS | 低 | 可獨立 / 可與 Phase 3 同 batch |

完整 4 phase 預計 ~600 LOC 變動、~12-16 hr E1 IMPL + ~3-4 hr E2 review + ~2 hr QA dry-run + ~1 hr deploy。

---

## 1. 架構決策（top-level）

### 1.1 Bybit 為 PnL ground truth source
- Round-trip PnL：Bybit `/v5/position/closed-pnl`（per-symbol per-close fully attributed by exchange）
- Wallet PnL：Bybit `/v5/account/wallet-balance`（totalEquity, totalPerpUPL, cumRealizedPnl）
- 理由：交易所對自己的成交配對是唯一真實的 single source；OPUSDT 案例證明 GUI 端 FIFO 配對在多策略共享 symbol、部分成交、跨 session 重啟時必然 drift

### 1.2 PG `trading.fills` 為 audit trail + strategy_name 來源 + Bybit 故障 fallback
- 保留所有寫入路徑（audit / replay / ML 訓練必要）
- 對外暴露 `strategy_name` 反查（Bybit 不知 OpenClaw 策略名）
- Bybit 5xx / timeout / retCode!=0 時降級為 stale display + 警告 banner

### 1.3 GUI 刪重算邏輯，純 render（zero computation）
- 刪 `_demoBuildProfitRows`（FIFO 配對源頭）
- 刪 `_buildDemoStratMap`（strategy hack，由 backend join 提供）
- 刪 `_calcRoundTrips`（已 dead code 但保證沒被誤用）
- 保留 `_demoFillPnl` 用於 per-fill 顯示（仍走 PG realized_pnl）

### 1.4 Cache layer 在 backend（in-memory 5-10s TTL）
- 不引入 Redis（CLAUDE.md 原則 14：零外部成本可運行）
- per-process Python dict + monotonic timestamp（FastAPI 進程內共享）
- 不引入 PG materialized view（reconcile 太慢 / refresh cron 複雜度爆）

---

## 2. 新接口 spec

### 2.1 `GET /api/v1/strategy/demo/closed-pnl`

**檔案位置**: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`（與既有 `/demo/fills` 同檔，phase2_router 前綴已是 `/api/v1/strategy`）

**Query params**:

| 名 | type | required | default | constraint |
|---|---|---|---|---|
| limit | int | no | 50 | 1-200 |
| offset | int | no | 0 | 0-1000（Bybit cursor pagination；offset > 100 警示） |
| start_time | int | no | now-24h | ms epoch；可選 |
| end_time | int | no | now | ms epoch；end - start ≤ 7d（Bybit 硬約束） |
| symbol | str | no | null | 可選；單 symbol 過濾 |
| force_refresh | bool | no | false | 跳過 cache 立即 hit Bybit（rate limit 慎用） |

**Auth**: `actor: base.AuthenticatedActor = Depends(base.current_actor)`（同 `/demo/fills`，read-only viewer 可訪問）

**Response shape**（中文鍵說明，camelCase 對齊 Bybit raw 慣例）:
```json
{
  "data": {
    "list": [
      {
        "symbol": "OPUSDT",
        "side": "Buy",                // 開倉方向（Bybit 原樣）
        "qty": "100.0",
        "avgEntryPrice": "0.4123",
        "avgExitPrice": "0.4051",
        "closedPnl": "-0.72",         // Bybit 權威 round-trip PnL（USDT）
        "openFee": "0.0825",
        "closeFee": "0.0810",
        "closedSize": "100.0",
        "fillCount": "2",
        "updatedTime": "1737651234567", // ms epoch
        "orderId": "abc-123-...",
        "orderLinkId": "openclaw-grid-OPUSDT-001",
        "leverage": "10",
        "execType": "Trade",
        "strategy_name": "grid",       // PA 注入：PG join 結果
        "strategy_source": "pg_fill"   // PA 注入：bybit_unknown / pg_fill / pg_link_id / pg_missing_unknown_external
      }
    ],
    "count": 1,
    "limit": 50,
    "offset": 0,
    "has_more": false,
    "next_offset": null,
    "source": "bybit_api",            // bybit_api / bybit_cached / pg_fallback
    "source_ts": 1737651300123,       // 此份資料 fetch / cache 寫入時間 (ms epoch)
    "reconcile": {                    // 可選；若後端有 reconcile sample 則回
      "checked_n": 30,
      "match_n": 28,
      "diff_n": 2,
      "max_abs_diff_usdt": 0.05,
      "alert_level": "ok"           // ok / warn / critical
    }
  }
}
```

**Error semantics**:
- Bybit timeout / 5xx：先 try cache；cache miss 且 stale > 60s → 降級走 PG fallback（source=`pg_fallback` + 加 `degraded_reason` field）；PG 也失敗 → 502
- Bybit retCode != 0：fail-closed 不重試（per CLAUDE.md hard boundary）；422 + sanitized detail
- 重要：絕不返回 `{}` 偽成功（fail-silent）；缺 data 必有 source + degraded_reason

**性能 SLO**:
- p50：< 50ms（cache hit）/ < 800ms（cache miss + Bybit fetch + PG join 30 rows）
- p99：< 2s

### 2.2 `GET /api/v1/strategy/demo/wallet-truth`（可選 / 同 phase 2 一起 land）

**Query params**: 無（Bybit wallet-balance 接口無時間參數）

**Response shape**:
```json
{
  "data": {
    "totalEquity": "10523.45",
    "totalAvailableBalance": "9876.23",
    "totalWalletBalance": "10500.00",
    "totalPerpUPL": "23.45",          // 未實現
    "cumRealizedPnl": "523.45",       // 帳戶累計已實現（覆蓋所有 session）
    "coin_usdt": {                    // USDT subset
      "walletBalance": "10500.00",
      "availableBalance": "9876.23",
      "unrealisedPnl": "23.45",
      "cumRealizedPnl": "523.45"
    },
    "source": "bybit_api",
    "source_ts": 1737651300123,
    "engine_initial_balance": 10000.0  // PA 注入：從 Rust paper_state.engine_initial_balance；計算「本 session 收益」用
  }
}
```

**理由**: GUI 既有 `demoB.totalEquity / totalPerpUPL` 已直接走 `/demo/balance` Bybit wallet snapshot。新接口好處：(a) 明確分 wallet-truth vs session-relative；(b) 加 `cumRealizedPnl` 讓 GUI 可顯「帳戶開戶以來累計」(c) 加 `source_ts` 讓 GUI 算 staleness。

**Phase 2 可不做此接口**（既有 `/demo/balance` 已部分覆蓋），標 OPTIONAL。

---

## 3. Cache 策略

### 3.1 Layer 1：In-memory TTL cache（per-process）

**實作**: 純 dict + monotonic timestamp，輕量無依賴

**檔案**: 新建 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_pnl_cache.py`（~80 LOC）

```python
import time
import threading
from typing import Any, Optional

_CACHE: dict[tuple, tuple[float, Any]] = {}  # key → (write_monotonic, payload)
_LOCK = threading.RLock()
_DEFAULT_TTL_SEC = 8.0

def cache_get(key: tuple, ttl_sec: float = _DEFAULT_TTL_SEC) -> Optional[Any]:
    with _LOCK:
        rec = _CACHE.get(key)
        if rec is None:
            return None
        write_ts, payload = rec
        if time.monotonic() - write_ts > ttl_sec:
            del _CACHE[key]
            return None
        return payload

def cache_put(key: tuple, payload: Any) -> None:
    with _LOCK:
        _CACHE[key] = (time.monotonic(), payload)

def cache_invalidate(prefix: tuple | None = None) -> int:
    """SIGHUP / manual refresh 時清掉特定 prefix（或全清）。"""
    with _LOCK:
        if prefix is None:
            n = len(_CACHE); _CACHE.clear(); return n
        keys = [k for k in _CACHE if k[:len(prefix)] == prefix]
        for k in keys: del _CACHE[k]
        return len(keys)

def cache_stats() -> dict:
    with _LOCK:
        return {"entries": len(_CACHE), "default_ttl_sec": _DEFAULT_TTL_SEC}
```

**Cache key**: `("closed_pnl", category, symbol_or_null, start_time, end_time, limit, offset)`

**TTL**: 8 秒（GUI 15s refresh，留 2x 餘量；Bybit rate limit 50 req/sec demo 帳戶不會炸）

**Eviction**: 純 TTL 過期 lazy delete；無 size cap（key 數有限：GUI 只開幾種 query 組合）

**理由**：
- 不用 `cachetools.TTLCache` — 純 stdlib，避新依賴
- 不用 PG materialized view — refresh latency 不可控
- 不用 Redis — 違 CLAUDE.md 原則 14

### 3.2 Layer 2：PG `trading.fills` 長期 fallback

**觸發條件**：
- Bybit timeout（已內建 8s）
- Bybit HTTP 5xx
- Bybit HTTP 200 但 retCode != 0
- Bybit 連續 3 次失敗（後端內部 counter，重啟 reset）

**Fallback query**:
```sql
SELECT
    EXTRACT(EPOCH FROM ts)*1000 AS updatedTime,
    symbol,
    side,
    qty::text,
    price::text,
    realized_pnl::text AS closedPnl,
    fee::text AS closeFee,
    order_id AS orderId,
    strategy_name,
    engine_mode
FROM trading.fills
WHERE engine_mode IN ('demo', 'live_demo')      -- ★ 同時撈兩個 tag
  AND realized_pnl != 0                          -- 只撈平倉腿（open fill 寫 0）
  AND ts >= NOW() - INTERVAL '24 hours'
ORDER BY ts DESC
LIMIT %s OFFSET %s;
```

**Fallback 局限**（必須在 response.degraded_reason 揭露）：
- PG 不存 `avgEntryPrice / avgExitPrice`（fills 是逐筆 not aggregated）
- PG 不存 `closedSize / fillCount`
- 顯示為「估算 round-trip」加標籤

### 3.3 Cache invalidation triggers

| 觸發 | invalidate scope | 實作 |
|---|---|---|
| SIGHUP | 全清 | signal handler 註冊 `cache_invalidate()` |
| 手動 refresh | 全清 | 新 `POST /api/v1/strategy/demo/closed-pnl/refresh` |
| force_refresh=true query | 該 query 跳過 cache | 函數內 check |
| 時間自然過期 | per-key | TTL check |

**不做**：DB trigger / Bybit webhook driven invalidation（過度設計；TTL 8s 對 GUI 15s refresh 已足夠新鮮）

---

## 4. strategy_name reconcile

### 4.1 Join 邏輯

每個 Bybit closed-pnl record 帶 `orderId` + `orderLinkId`：

```sql
SELECT order_id, strategy_name, engine_mode
FROM trading.fills
WHERE order_id = ANY(%s::text[])                 -- batch 30-50 IDs 一次撈
  AND engine_mode IN ('demo', 'live_demo')       -- ★ live_demo 修法
ORDER BY ts DESC;
```

**注意**: `trading.fills.order_id` 是 Bybit `orderId` 來源（per Rust `trading_writer.rs:431` 寫入路徑確認）。PG schema 無 `order_link_id` column（per V003 line 273-286 確認）— 所以 only join key 是 `order_id`。

### 4.2 缺失 case handling

| 情況 | strategy_name 值 | strategy_source field |
|---|---|---|
| PG join 命中 | 真實策略名 | `pg_fill` |
| Bybit 有 orderLinkId 含 `openclaw-` prefix 但 PG 無 record（race）| 從 orderLinkId 解析（如 `openclaw-grid-OPUSDT-001` → `grid`）| `pg_link_id` |
| Bybit 有 orderLinkId 但無法 parse | `unknown` | `bybit_unknown` |
| Bybit 無 orderLinkId（手動下單）| `unknown_external` | `pg_missing_unknown_external` |

**前端標示**（per A3 spec）：strategy=`unknown` / `unknown_external` 顯示時加 `(估算)` 後綴 + 灰色字。

### 4.3 Race window 處理

PG `trading.fills` writer 在 Rust 端 buffered batch flush（per `trading_writer.rs:368`），最壞情況 fills 寫入 PG 比 Bybit 早可見 5-30s。對策：
- backend cache TTL 8s 自然會 retry join；下次 GUI refresh（15s 後）必中
- 若 5 分鐘後仍 `pg_missing` ratio > 5% → reconcile 後台 task 標 WARNING（後續 audit log，不阻塞顯示）

---

## 5. Reconcile alert

### 5.1 對比邏輯

**Schedule**: 每小時跑一次（cron 或 background task；scope 控小不 IMPL 進 Phase 2，只標 carry-over）

**對比點**:
1. PG `trading.fills.realized_pnl - fee` SUM by symbol（24h window）
2. Bybit closed-pnl `closedPnl` SUM by symbol（24h window）

**Diff classification**:

| metric | OK | WARN | CRITICAL |
|---|---|---|---|
| per-symbol abs diff (USDT) | < 0.10 | 0.10-1.00 | > 1.00 |
| per-symbol relative diff | < 1% | 1-5% | > 5% |
| missing-in-PG ratio | < 1% | 1-10% | > 10% |
| missing-in-Bybit ratio | < 0.1% | 0.1-1% | > 1% |

**Output**: log line + 寫入 `learning.governance_audit_log`（reuse 既有表 / 不新增）

### 5.2 NOT 做的事

- 不阻塞顯示（per QC 4 級 lesson learned：observability 不要進 trading critical path）
- 不自動 reconcile / 自動修 PG（修法 = 人工 OPS）
- 不發 telegram alert（避誤觸發；reconcile 還需 production tuning）

### 5.3 Phase 2 是否要 IMPL

**否**。Phase 2 只 land `reconcile` field 在 closed-pnl response（從 cache lookup 最近一次 reconcile result）。實際 reconcile job 標為 Sprint 5+ carry-over，理由：
- 對 PnL refactor 核心目標非必須（render 對了即可）
- reconcile threshold 需要 production 數據 tuning
- 否則 scope creep

---

## 6. GUI 改動 spec

### 6.1 `tab-demo.html` 三段刪 + 改

**刪除（共 ~75 LOC）**：

| 行 | 函數 | 理由 |
|---|---|---|
| 506-520 | `let _demoStratMap` + `_buildDemoStratMap` | strategy 改從 backend closed-pnl 注入 |
| 710-751 | `_demoBuildProfitRows` | 整個 FIFO 配對是 hallucination 源頭 |
| 902-947 | `_calcRoundTrips` | 已 dead code 但保險刪 |

**新增 / 替換（共 ~80 LOC）**：

`_demoBuildProfitRowsFromBybit(closedPnlList)` 替換 `_demoBuildProfitRows`：
```javascript
function _demoBuildProfitRowsFromBybit(records) {
  if (!Array.isArray(records)) return [];
  return records.map(r => {
    const qty = parseFloat(r.closedSize || r.qty || 0);
    const entryPrice = parseFloat(r.avgEntryPrice || 0);
    const exitPrice = parseFloat(r.avgExitPrice || 0);
    const pnl = parseFloat(r.closedPnl || 0);
    const updatedMs = parseInt(r.updatedTime || 0, 10);
    const sym = r.symbol || '';
    const strategy = r.strategy_name || '';
    const strategySource = r.strategy_source || '';
    const sideOpen = r.side || '';
    const sideClose = sideOpen === 'Buy' ? 'Sell' : 'Buy';
    return {
      sym,
      strategy,
      strategySource,
      open: { side: sideOpen, price: entryPrice },
      close: { side: sideClose, price: exitPrice, time: updatedMs },
      qty,
      pnl,
      holdMs: null,           // Bybit 不提供 open time；UI 顯 "--"
      paired: true,
      fillCount: parseInt(r.fillCount || 0, 10)
    };
  }).sort((a, b) => (b.close.time || 0) - (a.close.time || 0));
}
```

`loadDemoFills` 走 Bybit-first 路徑：
```javascript
// profit tab 走新接口
if (_demoFillState.tab === 'profit') {
  const qs = '?limit=' + _demoFillState.limit + '&offset=' + _demoFillState.offset;
  const d = await ocApi('/api/v1/strategy/demo/closed-pnl' + qs);
  const payload = d && d.data;
  const records = (payload && payload.list) || [];
  if (!records.length) { /* empty render */ return; }
  const html = _demoBuildProfitRowsFromBybit(records).map(_demoProfitRow).join('');
  ocSetHtml('demo-fills', html);
  // source banner: bybit_api / bybit_cached / pg_fallback
  _updateDataSourceBanner(payload.source, payload.source_ts);
} else {
  // aggregate / buy / sell tab 維持 /demo/fills（per-fill 顯示走 PG audit）
  // ...既有邏輯
}
```

`_demoProfitRow` 微改加 strategy_source 標示：
```javascript
const sourceTag = r.strategySource === 'pg_fill' ? ''
                : r.strategySource === 'pg_link_id' ? ' <span class="oc-tag-dim">(估算)</span>'
                : ' <span class="oc-tag-dim">(估算)</span>';
// strategy cell:
'<td style="font-size:11px">' + (r.strategy ? _ocRenderOwnerStrategy(r.strategy, r) + sourceTag : '--') + '</td>'
```

### 6.2 strategy 映射來源切換

`loadPositions` 第 544 行：
```javascript
// 舊：_demoStratMap = _buildDemoStratMap(_demoFillsCache);
// 新：strategy 從 /demo/positions 後端 owner_strategy 已有；下面 strat = p.owner_strategy || '--' 即可
// 完全移除 _demoStratMap 依賴
```

`loadDemoOrders` 第 642 行同樣移除 `_demoStratMap[sym]` 依賴；改顯 `--`（active orders 通常 < 10 條，operator 容忍）。
**待 Phase 5+ carry-over**：給 `/demo/orders` 後端加 strategy join（用 `trading.orders` 表 join）。

---

## 7. restart_all.sh race fix（Phase 1）

### 7.1 新增 helper function

在 `restart_all.sh` line 410 之前（`restart_engine` 函數內或之前）：

```bash
# Wait for engine IPC socket to be ready before returning from restart_engine().
# 等 engine IPC unix socket ready 才返回，避免 API 立即 spawn 撞 race。
wait_for_engine_socket() {
    local socket_path="${OPENCLAW_IPC_SOCKET:-/tmp/openclaw/engine.sock}"
    local max_wait_sec=30
    local waited=0
    local interval=0.5
    echo ">>> Waiting for engine IPC socket: $socket_path (max ${max_wait_sec}s)..."
    while [[ "$waited" -lt $((max_wait_sec * 2)) ]]; do
        if [[ -S "$socket_path" ]]; then
            # Socket exists. Also probe with timeout via python (no nc dependency).
            if python3 -c "
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2.0)
try:
    s.connect('$socket_path')
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
                echo ">>> Engine IPC socket ready after ${waited}x500ms"
                return 0
            fi
        fi
        sleep $interval
        waited=$((waited + 1))
    done
    echo "ERROR: engine IPC socket not ready after ${max_wait_sec}s — abort restart" >&2
    return 1
}
```

### 7.2 主流程接線

L654 修改：
```bash
case "$SCOPE" in
    --engine-only) restart_engine; wait_for_engine_socket || exit 1; wait_and_verify ;;
    --api-only)    restart_api; sleep 3; echo "API server restarted" ;;
    all)           restart_engine
                   wait_for_engine_socket || exit 1
                   restart_api
                   wait_and_verify ;;
esac
```

**fail-loud**：socket 30s 未 ready → 退出 code 1，不繼續 spawn API（避雪崩）

**fallback path**：若 operator 真的要強行繼續（極罕見 dev case），加 `--skip-socket-wait` flag（不在 phase 1 IMPL，純占位）

### 7.3 不改動

- 既有 `wait_and_verify` 的 `sleep 10` 保留（engine 內部初始化、PG migration 自動 run、subagent spawn 等仍需慢慢起）
- 既有 `graceful_stop_engine` SIGTERM 5s + SIGKILL fallback 保留

---

## 8. GUI UX 防呆（Phase 4）

### 8.1 Stale banner（per A3 spec）

在 `tab-demo.html` `oc-control-bar` 之後插入：
```html
<div id="demo-stale-banner" style="display:none;padding:6px 12px;background:#fde68a;color:#92400e;font-size:12px;border-radius:4px;margin:4px 0">
  <span id="demo-stale-banner-text">資料 30s+ 未更新</span>
</div>
```

JS helper（新加在 `common.js` 或 inline tab-demo.html）：
```javascript
function _updateStaleBanner(sourceTsMs) {
  if (!sourceTsMs) return;
  const ageMs = Date.now() - sourceTsMs;
  const banner = $('demo-stale-banner');
  const text = $('demo-stale-banner-text');
  if (ageMs > 120000) {
    banner.style.display = 'block';
    banner.style.background = '#fecaca';
    banner.style.color = '#991b1b';
    text.textContent = '資料 ' + Math.floor(ageMs/1000) + 's 未更新（嚴重 stale）';
  } else if (ageMs > 30000) {
    banner.style.display = 'block';
    banner.style.background = '#fde68a';
    banner.style.color = '#92400e';
    text.textContent = '資料 ' + Math.floor(ageMs/1000) + 's 未更新';
  } else {
    banner.style.display = 'none';
  }
}
```

### 8.2 Visual decay CSS

在 `common.js` `ocInjectBaseCSS()` 既有 style block 加：
```css
.oc-stale { background: #f3f4f6; color: #6b7280; opacity: 0.8; }
.oc-tag-dim { font-size: 10px; color: #9ca3af; padding: 0 4px; border-radius: 3px; background: #f3f4f6; }
```

GUI 在每次 render 完後 check `_updateStaleBanner(payload.source_ts)`；> 120s 對 PnL 卡片 add class `oc-stale`。

### 8.3 ocApi GET 失敗也彈 toast（限頻）

`common.js` line 213 既有 catch block 加：
```javascript
} catch (e) {
  console.warn('[ocApi] Network error: ' + path, e);
  // Phase 4: GET 失敗也彈 toast（per-path 限頻 30s）
  _ocToastRateLimit(path, '網路錯誤: ' + path);
  return null;
}
```

加 helper：
```javascript
const _ocToastLastShow = {};
function _ocToastRateLimit(key, msg, type = 'error') {
  const now = Date.now();
  if (_ocToastLastShow[key] && now - _ocToastLastShow[key] < 30000) return;
  _ocToastLastShow[key] = now;
  if (typeof ocToast === 'function') ocToast(msg, type);
}
```

### 8.4 `ocStartRefresh` 加 in-flight guard

`common.js` line 428:
```javascript
let _ocRefreshTimer = null;
let _ocRefreshFn = null;
let _ocRefreshInFlight = false;

function ocStartRefresh(fn, interval) {
  _ocRefreshFn = fn;
  if (_ocRefreshTimer) clearInterval(_ocRefreshTimer);
  _ocRefreshTimer = setInterval(async () => {
    if (_ocRefreshInFlight) {
      console.warn('[ocStartRefresh] previous tick still in-flight, skip');
      return;
    }
    _ocRefreshInFlight = true;
    try { await fn(); } finally { _ocRefreshInFlight = false; }
  }, interval || 15000);
}
```

**注意**：`loadAll` 既有 `_demoRefreshInFlight` guard，但其他 tab（live / system）可能沒 — 統一在 `ocStartRefresh` 加是更穩的位置。

### 8.5 `tab-system.html loadQuickStatus` sequential → parallel

L886-920 改：
```javascript
async function loadQuickStatus() {
  const [paperD, feedD, demoD, scannerD] = await Promise.allSettled([
    ocApi('/api/v1/paper/session/status'),
    ocApi('/api/v1/paper/market-feed/status'),
    ocApi('/api/v1/strategy/demo/balance'),
    ocApi('/api/v1/strategy/scanner/opportunities'),
  ]);
  // 各自處理（既有邏輯保留，只把每段包到 if status === 'fulfilled' 內）
  // ...
}
```

省下 ~3x latency（4 sequential 8s timeout = 最壞 32s → parallel 最壞 8s）

### 8.6 demo-badge 強制可降級

`tab-demo.html` L247 + L389 的 `_demoConnectedOnce` 守門邏輯：當 balance 失敗時不 reset badge 到 offline。應改成「失敗則更新 badge 為「斷線中（最後成功 Xs 前）」+ 開放 fall through 到 showOffline()」。具體：
```javascript
async function loadDemoStatus() {
  // ...
  const balD = await ocApi('/api/v1/strategy/demo/balance?fast=1');
  if (!balD || !balD.data) {
    if (_demoConnectedOnce) {
      // 不再 silent return；改顯示 stale 警告
      _updateStaleBanner(_lastSuccessfulFetchTs);
      _updateDataSourceBanner('disconnected', _lastSuccessfulFetchTs);
    } else {
      showOffline();
    }
    return;
  }
  _demoConnectedOnce = true;
  _lastSuccessfulFetchTs = Date.now();
  // ...既有
}
```

### 8.7 每 metric 加 timestamp 角標

PnL Overview / Account Balance 等 card 標題右側加：
```html
<span style="font-size:9px;color:#9ca3af;float:right" id="d-pnl-card-ts">--</span>
```
每次 render 後 `ocSetText('d-pnl-card-ts', '更新於 ' + new Date(payload.source_ts).toLocaleTimeString())`

### 8.8 engine-calc vs exchange-confirmed PnL 加 icon

`_demoProfitRow`：
```javascript
'<td class="' + pnlCls + '">' +
  '<span title="Bybit exchange-confirmed">✅</span> ' +
  sign + r.pnl.toFixed(4) +
'</td>'
```

對 `loadComparison` 的 PaperPNL：
```javascript
'<td>⚙ ' + ocMoney(paperPnl.realized_pnl || 0) + '</td>'  // engine-calc
'<td>✅ ' + ocMoney(demoRealized) + '</td>'                // exchange-confirmed
```

---

## 9. Deploy 4 phase

### Phase 1: restart_all.sh race fix

**Scope**: 純 bash；不需 engine / API 重建
**改動檔**: `srv/helper_scripts/restart_all.sh`（~40 LOC 新增 + L654 修改）
**Acceptance**:
- `bash helper_scripts/restart_all.sh` 全程不報 IPC race；engine 起後等 socket 才 spawn API
- 故意 break socket（chmod 000 /tmp/openclaw）→ 30s 後 abort + exit 1
- 既有 `--engine-only` / `--api-only` / `all` 三 path 行為對齊
**Rollback**: 單 commit revert；無 schema / config / runtime 副作用

### Phase 2: Backend 新 endpoint + TTL cache + reconcile join

**Scope**: Python；新 file + 2 既有 file edit；不需 engine 重建（只 API restart）
**改動檔**:
- 新 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_pnl_cache.py`（~80 LOC）
- 編輯 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py`（加 `get_closed_pnl` method，~50 LOC）
- 編輯 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`（加新 endpoint + 修 `/demo/fills` engine_mode 包含 live_demo，~150 LOC）
- 編輯 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/trading_true_metrics.py`（已是 IN ('demo', 'live_demo')，**不需改**）
- 可選 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py` 註冊 SIGHUP handler（如已存在則不重複）
**Acceptance**:
- `curl /api/v1/strategy/demo/closed-pnl?limit=30` 返回 source=bybit_api + 30 record + strategy_source 分布合理
- `curl /api/v1/strategy/demo/closed-pnl?limit=30` 連續 3 次：第 2/3 次 source=bybit_cached
- 故意斷 Bybit（防火牆 block api-demo.bybit.com）→ 8s 後 source=pg_fallback + degraded_reason
- `/demo/fills` 既有 endpoint engine_mode 改 `IN ('demo', 'live_demo')` 後不破 ML 訓練 / dust panel / 其他 caller（grep 確認）
- 30 record p50 < 1s（cache miss）/ < 50ms（cache hit）
- OPUSDT 的 closedPnl SUM ≈ -2.61 USD（已驗 ground truth）
**Rollback**: 移除新 endpoint 註冊 + revert `/demo/fills` engine_mode；新 file 留下不影響運行
**前端不依賴**：Phase 2 deploy 後前端仍走舊 path；新 endpoint 走 GUI dev / curl 驗證即可

### Phase 3: Frontend PnL render 切 Bybit-first

**Scope**: 純 JS；不需 backend 改（必須 Phase 2 已 deploy）
**改動檔**: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html`（刪 ~75 LOC + 新 ~80 LOC）
**Acceptance**:
- profit tab 顯示 OPUSDT round trip 為 -2.61 USD 合理數字（不是 -41.03 / -18.38）
- profit tab 每 row 帶 ✅ 圖標 + 來源標籤
- aggregate / buy / sell tab 維持 PG 原樣
- 無 console error；`node --check tab-demo.html`（per CLAUDE.md feedback_gui_node_check_sop）通過
- 多策略共享 symbol 場景：strategy_name 來自 backend join 而非 hack
**Rollback**: 單 commit revert；無 backend 副作用

### Phase 4: GUI UX 防呆

**Scope**: 純 JS / CSS；不需 backend 改
**改動檔**:
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js`（~50 LOC：refresh guard + ocApi toast + decay CSS）
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html`（~70 LOC：stale banner + timestamp 角標 + icon）
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-system.html`（~30 LOC：sequential → parallel）
**Acceptance**:
- 故意停 API 60s + 恢復：banner 由黃變紅 / 恢復後 banner 消失
- 故意 API 慢 6s：refresh guard skip second tick
- 4 個 GET 失敗：每個都彈 toast 但 30s 內不重複彈
- node --check 三 file 通過
**Rollback**: 三 file 各自獨立 revert；任一回退不影響 PnL truth

**Phase 3 + 4 可同 batch deploy**（前端共一個 release window），但 Phase 4 可獨立 Phase 3 之前 ship（純 UX 改進）

---

## 10. 邊界 case + risk

| Case | 處理策略 |
|---|---|
| Bybit API 5xx / timeout 8s | 8s 內 cache miss → 試 PG fallback；> 60s 連續失敗 → 標 stale banner red + ocToast 警告 |
| Bybit rate limit hit (HTTP 429) | 後端 `_get` 已 raise BybitTransportError；走同 fallback 路；後加 5 min cooldown 避雪崩 |
| strategy_name reconcile 失敗 | strategy_source = `bybit_unknown` / `pg_missing_unknown_external`；前端 `(估算)` 標 |
| engine_mode 漏 live_demo 修法破其他 consumer | grep 確認：trading_true_metrics.py 已 IN clause / parquet_etl.py 已支持 / strategist_history_routes.py 已支持 / 三個 caller 已 ready |
| 跨環境 mode-aware | 新 endpoint 寫死 `engine_mode IN ('demo', 'live_demo')`；未來 live mainnet 走另一個 `/strategy/live/closed-pnl`（Sprint 5+ carry-over） |
| Bybit 7d query 限制 | Phase 2 只支援 ≤ 7d；GUI 預設 24h；> 7d 前端分頁多次呼叫（Phase 5+ feature；本 Sprint 不做） |
| GUI 在 console 環境只能訪問 demo tab | 既有 `_demoTabVisible` guard 保留；無變動 |
| cache pollution（fake data 寫進去）| 不可能：cache write 只在 successful Bybit response；Bybit 200 + retCode==0 才 cache_put |
| TTL 太短 GUI 連續 30s 刷不來 | 後端 cache 8s + GUI refresh 15s → 50% 機率命中；最壞 GUI 等 800ms（Bybit p99 < 800ms） |
| Multi-FastAPI worker（uvicorn workers > 1） | per-process cache 各算各的；對 PnL 一致性不影響（cache 只是減 Bybit call rate） |
| OPUSDT 修好後其他 symbol 也有類似 GUI hallucination？ | 是的，本 fix 對 ALL symbol 統一生效（架構性修法） |

---

## 11. 跟 NEARUSDT cost_gate fix chain 解耦驗證

| 項目 | 是否觸碰 | 證據 |
|---|---|---|
| cost_gate logic | 否 | 改動全在 PnL display / cache / restart bash，無 strategy / risk 路徑 |
| `cost_gate_min_n_trades_for_block` config | 否 | TOML 全程不動 |
| `ma_crossover NEARUSDT 1978 deny` 觀察期 | 否 | strategy gating 完全獨立路徑（risk_routes.py） |
| Rust engine binary 變動 | 否 | Phase 1-4 全 Python + JS + bash；engine 不重 build |
| strategy / engine_mode 寫入路徑 | 否 | engine_mode 修法只在 GUI read 端 SELECT，writer 不動 |
| 既有 cost_edge_advisor cron | 否 | 完全獨立 cron 路徑 |

**結論**：4 phase 與 NEARUSDT cost_gate 觀察期完全解耦；可同期 parallel 進行。

---

## 12. 跟其他 PA 已 land design 解耦驗證

| 對 | 衝突？ | 說明 |
|---|---|---|
| Sprint 5 §4.3.1 StrategyQualityEmitter | 否 | 全在 Rust 端 / V106 telemetry；本 design 完全 Python + JS |
| Sprint 5 BybitPrivateWs supervisor (Wave C) | 否 | private WS 是 trading critical path；本 design 純 REST 讀 |
| Sprint 4 first Live carry-over 8 條 | 否 | 本 design 只動 demo / live_demo；不動 live |
| Track A engine_runtime / sysinfo | 否 | 不同層；本 design 不動 V106 emitter |

---

## 13. 16 根原則合規

| # | 原則 | 評估 |
|---|---|---|
| 1 | 單一寫入口 | PASS — 本 design 純讀（GET endpoint），不新增寫路徑 |
| 2 | 讀寫分離 | PASS — GUI 仍純讀；新 endpoint 純 read |
| 3 | AI 輸出 ≠ 命令 | N/A — 不涉 AI 路徑 |
| 4 | 策略不繞風控 | N/A — 不涉 strategy |
| 5 | 生存 > 利潤 | N/A — observability 改進 |
| 6 | 失敗默認收縮 | PASS — Bybit 失敗 → PG fallback；PG 失敗 → 502；不偽成功 |
| 7 | 學習 ≠ 改寫 Live | PASS — 不動 live state |
| 8 | 交易可解釋 | PASS — 強化 audit trail（Bybit 直連 vs PG 對賬） |
| 9 | 災難保護 | N/A — 不動 stop 路徑 |
| 10 | 認知誠實 | PASS — strategy_source field 明確區分 pg_fill / pg_link_id / unknown |
| 11 | Agent 最大自主 | N/A |
| 12 | 持續進化 | PASS — reconcile carry-over 為後續學習鋪路 |
| 13 | AI 成本感知 | N/A |
| 14 | 零外部成本可運行 | PASS — cache 純 stdlib；無 Redis / 外部服務 |
| 15 | 多 Agent 協作 | N/A |
| 16 | 組合級風險 | N/A |

**Hard boundary**: 全部不觸（不改 live_execution_allowed / max_retries / system_mode / authorization）

---

## 14. E1 派發計劃（4 packet 可並行）

### Packet A — restart_all.sh fix（E1 #1，~2 hr）
- 改動：`srv/helper_scripts/restart_all.sh`
- 對 dep：無
- 對 deploy：Phase 1 immediate
- 並行性：完全獨立

### Packet B — Backend endpoint + cache + reconcile（E1 #2 或 E1a，~6-8 hr）
- 改動：
  - 新 `bybit_pnl_cache.py`
  - 編 `bybit_rest_client.py`（加 `get_closed_pnl`）
  - 編 `strategy_ai_routes.py`（加 endpoint + 修 `/demo/fills` engine_mode 包含 live_demo）
- 對 dep：無（Phase 2 內全自洽）
- 對 deploy：Phase 2
- 並行性：與 Packet A 完全並行；與 Packet C 必序列（C 依 B）

### Packet C — Frontend PnL render 切 Bybit-first（E1 #3，~3-4 hr）
- 改動：`tab-demo.html`（刪 + 加）
- 對 dep：Packet B 已 land 才能驗
- 對 deploy：Phase 3
- 必跑 `node --check`

### Packet D — Frontend UX 防呆（E1 #4 或 E1a，~3-4 hr）
- 改動：`common.js` / `tab-demo.html` / `tab-system.html`
- 對 dep：無（與 C 互不衝突；都改 tab-demo.html 但區段不同）
- 對 deploy：Phase 4
- 必跑 `node --check` 三 file

**衝突點**：Packet C 與 Packet D 都改 `tab-demo.html`，但區段不同（C 改 L500-840 函數體；D 改 L1-50 banner + L1095 refresh + per-card timestamp）。建議派 C 先 land 再 D；或同一 E1 連做兩 packet 避 merge conflict。

### 並行最大化路徑

- T+0：dispatch Packet A + B（2 E1 並行）
- T+2hr：Packet A done → Phase 1 deploy；Packet B 持續
- T+8hr：Packet B done → Phase 2 deploy；dispatch Packet C
- T+12hr：Packet C done → Phase 3 deploy；dispatch Packet D
- T+16hr：Packet D done → Phase 4 deploy
- 整體 wall-clock ~16 hr / core E1 effort ~14-18 hr

---

## 15. E2 重點審查 3 點（必須對抗性核驗）

### E2-1：engine_mode 修法的 caller blast radius
- grep `engine_mode\s*=\s*['\"]demo['\"]` 全 codebase；確認還有沒有遺漏處（已知 trading_true_metrics 已 IN clause / ML 已支持）
- 重點確認 `/demo/fills` 改成 `IN ('demo', 'live_demo')` 對 dust panel / orphan_frozen / 既有 strategy filter 不破壞（dust frozen 也應該 demo + live_demo 都帶）
- 對賬：改前 vs 改後 demo+live_demo 的 24h fills count 比例（live_demo 預期占 ≥ 95%；改前的 demo only 是嚴重 undercount）

### E2-2：Cache TTL + concurrency 競態
- 多 FastAPI worker 並發 hit Bybit 是否觸發 rate limit（demo 50 req/sec 看似充裕，但 GUI 用戶 5 人 × 4 worker × 15s = 80 req/min 仍遠低）
- cache.put 寫競爭：threading.RLock 是否夠（asyncio FastAPI 端是 single-thread per worker，RLock 對 mixed sync/async 安全）
- SIGHUP handler 是否與 uvicorn `--workers` 模式衝突（uvicorn worker SIGHUP 重啟，cache 自然清空；不需自定義 handler）

### E2-3：GUI `_demoBuildProfitRowsFromBybit` 對抗 OPUSDT case
- 必須 E2 在 dev 環境拉真實 Bybit demo closed-pnl 30 record，用本函數轉換並比對「總 PnL 合計 ≈ Bybit wallet cumRealizedPnl session delta」
- 必須測 strategy_source field 4 種 case 都有合理 UI 表現（pg_fill / pg_link_id / bybit_unknown / pg_missing_unknown_external）
- 必須測 empty list / partial fill / multi-strategy 同 symbol 三 case

---

## 16. Open question（需 operator 拍板）

### Q1：reconcile alert 是否本 Sprint IMPL，還是 carry-over？
- **PA 推薦**：carry-over to Sprint 5+。理由：Phase 2 只 land response field；reconcile job 需 production threshold tuning。
- **若 operator 要本 Sprint IMPL**：+ ~4 hr 給 Packet B；BB 視角必審 alert 是否阻塞 trading（必須完全不阻）

### Q2：`/demo/wallet-truth` 是否同 Phase 2 一起 land，還是延後？
- **PA 推薦**：延後。既有 `/demo/balance` 已部分覆蓋；新接口主要好處是 `cumRealizedPnl` + `source_ts`，GUI 端 nice-to-have 不阻 PnL render fix。
- **若 operator 要一起 land**：+ ~1.5 hr 給 Packet B

### Q3：strategy_source field 是 4 種還是更少？
- **PA 推薦 4 種**：pg_fill / pg_link_id / bybit_unknown / pg_missing_unknown_external，讓 audit 能清晰追溯
- **替代 2 種**：only `pg_fill` / `estimated`，UX 簡化但失去細粒度
- 操作員拍板影響 Phase 3 前端標籤設計

---

## 17. 完整檔案改動清單

| Phase | Path | 操作 | LOC |
|---|---|---|---|
| 1 | `srv/helper_scripts/restart_all.sh` | edit | ~40 |
| 2 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_pnl_cache.py` | new | ~80 |
| 2 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py` | edit | ~50 |
| 2 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py` | edit | ~150 |
| 3 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html` | edit | -75 / +80 |
| 4 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js` | edit | ~50 |
| 4 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html` | edit | ~70 |
| 4 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-system.html` | edit | ~30 |

**總計**：~600 LOC（-75 / +675）

---

## 18. 反模式（明確不做）

| 反模式 | 為什麼不做 |
|---|---|
| GUI 重寫成 React/Vue | CLAUDE.md §七 hard rule：Vanilla JS only |
| 拆 control_api_v1 微服務 | 過度設計；本 PnL refactor 不需要 |
| 移除 PG `trading.fills` 寫入 | audit trail 必要；ML 訓練依賴 |
| 改 Rust 端 closed-pnl 既有 parser | 既有 Rust parser 是 Rust 內部用；Python 端走 httpx 不依賴 |
| 在 GUI 端 cache（localStorage） | PnL 是 server-side truth；多窗口會 drift |
| 為 reconcile 加 telegram alert | 需要 production tuning；先沉澱數據再決定 |
| 改 `cost_gate` / strategy / engine | 完全解耦 NEARUSDT 觀察期 |
| 把 cache 換 Redis | 違 CLAUDE.md 原則 14 |

---

## 19. 驗證證據（pre-design）

- 已讀 `strategy_ai_routes.py:1226-1320`（demo/fills 既有路徑確認 engine_mode = 'demo' 是 bug）
- 已讀 `bybit_rest_client.py:728-744`（既有 get_executions pattern；新 get_closed_pnl 完全對齊）
- 已讀 `tab-demo.html:500-840`（FIFO + strategy hack 確認位置）
- 已讀 `restart_all.sh:411-654`（race window 確認 spawn engine 後立即 spawn API）
- 已讀 `V003__trading_agent_tables.sql:270-286`（trading.fills schema 確認 order_id 是唯一 join key）
- 已讀 `V005__indexes_views.sql:126`（idx_fills_order_id 存在，join 效能 OK）
- 已 grep `engine_mode = 'live_demo'` caller（4 既有 caller 全 IN clause / 已支持）
- 已讀 `trading_writer.rs:431` 確認 Rust 寫 fills.order_id = Bybit orderId
- 已讀 `ipc_client.py:49` 確認 socket path DEFAULT = `/tmp/openclaw/engine.sock`

---

## Verdict

**DISPATCH READY**：4 phase spec 完整、E1 packet 拆分清晰、邊界 case 全覆蓋、與 NEARUSDT cost_gate 完全解耦、16 原則 + 9 安全不變量 + 8 hard boundary 0 觸碰、A 級合規。

E1 可立即派發 Packet A + B 並行。

Risk 等級：**中**（涉 production GUI 改動 + 新 Python endpoint）；mitigations 全列。

Confidence:
- HIGH for 接口 spec / cache 策略 / strategy join 邏輯
- HIGH for restart race fix（純 bash 加 wait helper）
- HIGH for 解耦驗證 + 16 原則合規
- MEDIUM for reconcile alert（threshold 需 production tuning，但本 Sprint 不 IMPL）
- HIGH for E2 重點審查 3 點覆蓋 blast radius
