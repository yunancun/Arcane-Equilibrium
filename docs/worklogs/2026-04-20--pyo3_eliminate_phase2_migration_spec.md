# PYO3-ELIMINATE-1 Phase 2 · BybitClient Migration Spec

> **Task**: 切換 3 個 Python call sites 由 `openclaw_core.BybitClient` (PyO3 cdylib)
> 遷移到純 Python `httpx` 版 `BybitClient`（同仓另一 agent 實作於
> `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py`）。
>
> **Audience**: Main-session PM 負責 apply patches；E4 負責回歸驗收。
> 每個 call site 包含：method 調用盤點、response shape 依賴、Edit patch（old/new 對）、風險分析、rollback 指引。
>
> **Date**: 2026-04-20 · **Phase**: 2 of 3 · **Blocking**: 等實作 agent 交付 `bybit_rest_client.py` 後即可 apply。
>
> 配套：`program_code/.../tests/test_bybit_rest_client_parity.py` + `tests/fixtures/bybit_v5_responses/*.json`

---

## 0. 新 BybitClient 契約（實作 agent 必須遵守）

### 0.1 模組位置與 import 路徑
```python
# 新 (Phase 2)
from .bybit_rest_client import BybitClient  # for live_session / strategy_ai (同 app/ 套件)
# OR
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.bybit_rest_client import BybitClient
# for helper_scripts/ (跨套件)
```

與舊 PyO3 `from openclaw_core import BybitClient` **類名必須完全一致**（`BybitClient`）
—— 這樣 3 個 call sites 的 import line **只改一行**，無需改動使用方的變數名（`rc` / `client`）。

### 0.2 Constructor signature（必須 byte-compatible）

```python
class BybitClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        environment: str = "demo",   # "demo" | "testnet" | "mainnet" | "live_demo"
    ) -> None: ...
```

**keyword name 必須是 `environment`**（不是 `env`）— `clean_restart_flatten.py:45` 和
`live_session_routes.py:221` 都用 `BybitClient(environment=args.env)` / `BybitClient(environment=environment)`。

憑證解析行為與 Rust 一致：
- 顯式參數 > env var (`BYBIT_API_KEY` / `BYBIT_API_SECRET`) > slot file (`$OPENCLAW_SECRETS_DIR/<slot>/api_key` etc.)
- **Mainnet 下 env var fallback 必須封閉**（LIVE-GUARD-1 Gate #4a，`bybit_rest_client.rs:386-497`）
- Mainnet 下 `OPENCLAW_ALLOW_MAINNET=1` 檢查（LIVE-GUARD-1 Gate #3）— 缺失時 ctor raise
- Mainnet/LiveDemo 缺憑證時 ctor raise（不 silent fallback）

### 0.3 Method surface（12 必須實作）

所有 method 語意與 PyO3 bridge 1:1；**返回值必須是 Python native `dict` / `list[dict]` / `bool` / `int` / `float`**，不得回傳 custom class / Pydantic model / namedtuple（pythonize 產 dict，httpx json() 也產 dict；保持不變）。

| # | Method | Signature | 返回 |
|---|--------|-----------|------|
| 1 | `has_credentials()` | `() -> bool` | `True/False` |
| 2 | `base_url()` | `() -> str` | e.g. `"https://api-demo.bybit.com"` |
| 3 | `instrument_count()` | `() -> int` | cache size |
| 4 | `refresh_balance()` | `() -> dict` | WalletState dict（見 §0.4） |
| 5 | `refresh_instruments(category="linear")` | `(str) -> int` | 載入的 symbol 數量 |
| 6 | `get_instrument(symbol)` | `(str) -> dict | None` | SymbolSpec dict or None |
| 7 | `get_positions(category="linear", symbol=None, settle_coin="USDT")` | → `list[dict]` | PositionInfo list |
| 8 | `get_active_orders(category="linear", symbol=None, settle_coin="USDT")` | → `list[dict]` | OrderInfo list |
| 9 | `get_executions(category="linear", symbol=None, limit=None, settle_coin="USDT")` | → `list[dict]` | ExecutionInfo list |
| 10 | `round_qty(symbol, qty)` | `(str, float) -> float | None` | rounded qty or None if not cached |
| 11 | `place_order(symbol, side, order_type, qty, price=None, category="linear", reduce_only=None, time_in_force=None, order_link_id=None, trigger_price=None, trigger_direction=None, take_profit=None, stop_loss=None)` | → `dict` | OrderResponse `{order_id, order_link_id}` |
| 12 | `cancel_order(symbol, order_id, category="linear")` | `(str, str, str) -> dict` | OrderResponse |

**不需要實作**（盤點後 3 call site 都沒用）：`set_leverage` / `set_trading_stop` /
`get_order_history` / `get_closed_pnl` / `get_klines` / `get_tickers` / `get_orderbook` /
`get_funding_history` / `get_open_interest` / `get_long_short_ratio` / `get_recent_trades` /
`get_server_time` / `amend_order` / `cancel_all_orders` / `get_borrow_history` /
`get_account_info` / `refresh_fee_rates` / `get_fee_rate` / `taker_fee` / `maker_fee` /
`usdt_equity` / `usdt_wallet_balance` / `usdt_available` / `wallet_snapshot` / `round_price` /
`validate_order` / `instrument_symbols` / `rate_limit_remaining`。

**建議策略**：為留 future-proof 可以空架所有 method（raise `NotImplementedError("not required by Phase 2")`），但 parity test 只打上面 12 個。實作 agent 可選。

### 0.4 返回 dict 的 key shape（pythonize snake_case 契約）

**最關鍵項**：pythonize 序列化 Rust struct 時用 **snake_case field name**（Rust struct field 名字原樣保留，沒有 rename_all）。新 httpx 版必須**手動**把 Bybit V5 camelCase → snake_case 映射 —— 這是新版 vs 舊版最容易出分歧的地方。

#### `refresh_balance()` 返回（來自 `parse_wallet_response` / `account_manager.rs:445-514`）
```python
{
    "account_type": "UNIFIED",
    "total_equity": 10000.0,              # f64
    "total_wallet_balance": 10000.0,
    "total_available_balance": 9500.0,
    "total_unrealised_pnl": 0.0,
    "coins": {
        "USDT": {
            "coin": "USDT",
            "wallet_balance": 10000.0,
            "available_to_withdraw": 9500.0,
            "equity": 10000.0,
            "unrealised_pnl": 0.0,
            "cum_realised_pnl": 0.0,
        },
        # ... 其他幣
    },
    "updated_at_ms": 1745123456789,         # u64，非 Bybit API 給的，本地填的 SystemTime now
}
```

**注意**：
- Bybit API response 下 `"totalEquity": "10000"`（字串）→ `parse_f64` → Python `float`。
- `total_unrealised_pnl` 是**本地 sum** over coins，不是 API 返回。Python 版必須也這麼算。
- `updated_at_ms` 是**本地生成**的（`time.time()*1000`），不是 Bybit 返回；Mode A parity test 需 mock 時鐘或允許 ±1s 漂移。

#### `get_positions(...)` 返回（list of dict；`parse_position_item` / `position_manager.rs:479-498`）
每個 item:
```python
{
    "symbol": "BTCUSDT",         # str
    "side": "Buy" | "Sell" | "None",
    "size": 0.001,               # f64，Bybit 回字串 → f64
    "avg_price": 65432.1,
    "mark_price": 65500.0,
    "unrealised_pnl": 6.79,
    "leverage": 10.0,
    "liq_price": 58000.0,
    "take_profit": 0.0,
    "stop_loss": 0.0,
    "position_idx": 0,           # i32
    "trailing_stop": 0.0,
    "position_value": 65.432,
    "cum_realised_pnl": 123.45,
    "created_time": "1699999999999",   # Bybit 給 ms str
    "updated_time": "1700000000000",
}
```

#### `get_active_orders(...)` / `get_order_history(...)` 返回（`parse_order_info_item` / `order_manager.rs:748-765`）
```python
{
    "order_id": "...",
    "order_link_id": "...",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "order_type": "Market" | "Limit",
    "price": 0.0,
    "trigger_price": 0.0,
    "qty": 0.001,
    "cum_exec_qty": 0.0,
    "cum_exec_value": 0.0,
    "avg_price": 0.0,
    "order_status": "New" | "PartiallyFilled" | "Filled" | "Cancelled" | "Untriggered" | ...,
    "created_time": "...",
    "updated_time": "...",
}
```

**GUI 依賴的補充 camelCase keys**（`_normalize_order` 在 call site 處補的）：
`orderId`/`orderLinkId`/`orderStatus`/`orderType`/`triggerPrice`/`createdTime`/`updatedTime`
—— 新 httpx 版**不必**自行補 camelCase；`_normalize_order` 會 fallback。但實作如果願意**額外**返回 Bybit 原始 camelCase keys（使 `.get("orderId")` 也有值），向 GUI 更友好。**parity test 只比對 snake_case keys**（舊版 PyO3 從來沒吐 camelCase）。

#### `get_executions(...)` 返回（`parse_execution_list` / `order_manager.rs:784-798`）
```python
{
    "exec_id": "...",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "exec_price": 65432.1,
    "exec_qty": 0.001,
    "exec_value": 65.4321,
    "exec_fee": 0.036,
    "fee_currency": "USDT",
    "order_id": "...",
    "order_link_id": "...",
    "exec_type": "Trade" | "Funding" | "BustTrade",
    "exec_time": "1700000000000",
    "closed_pnl": 0.0,               # f64，開倉 0，平倉非 0。關鍵欄位：GUI 用它決定 PnL 色。
}
```

#### `get_instrument(symbol)` 返回（`SymbolSpec` / `instrument_info.rs:22-50`）
```python
{
    "symbol": "BTCUSDT",
    "base_currency": "BTC",          # 注意：Bybit 原字段叫 baseCoin；Rust struct 叫 base_currency
    "quote_currency": "USDT",        # Bybit: quoteCoin
    "contract_type": "LinearPerpetual",
    "qty_step": 0.001,
    "min_qty": 0.001,
    "max_qty": 100.0,
    "tick_size": 0.10,
    "min_price": 0.10,
    "max_price": 999999.0,
    "min_notional": 5.0,
    "qty_decimals": 3,                # u32，本地推導
    "price_decimals": 1,
}
```
未緩存時返回 `None`（不 raise）。caller `_fetch_min_notional` 和
`_rest_close_position_reduce_only` 都 `isinstance(spec, dict)` 檢查後才用。

#### `place_order(...)` 返回（`parse_order_response` / `order_manager.rs:682-695`）
```python
{"order_id": "1234567890", "order_link_id": "client-id-xxx"}
```
**只有 2 個 key**。新版保持一致。

#### `cancel_order(...)` 返回
同 `place_order`（OrderResponse）。

#### `round_qty(symbol, qty)` / `refresh_instruments(category)` / `instrument_count()` / `has_credentials()` / `base_url()`
純 scalar；不需 shape 詳述。

### 0.5 錯誤語意（必須一致）

PyO3 版：`retCode != 0` → `RuntimeError("Bybit API error: retCode=XXX, retMsg=YYY")`（`mod.rs:29-38`）。
網路錯誤 → `RuntimeError("Bybit error: ...")`。

新 httpx 版應 raise 相同類型（或子類化 `BybitApiError(RuntimeError)`），call sites 都 catch 寬泛的 `except Exception as exc`，所以只要不是 `SystemExit` 類都不會破壞語意。推薦：
- `retCode != 0` → `raise RuntimeError(f"Bybit API error: retCode={code}, retMsg={msg}")`
- network/timeout/json parse → `raise RuntimeError(f"Bybit error: {e}")`

### 0.6 Signature signed REST 要求

- HMAC-SHA256 per Bybit V5 spec（`bybit_rest_client.rs:607-631`, 委派至 `common::bybit_signer::sign_rest_v5`）
  - GET: `sign_str = timestamp + api_key + recv_window + sorted_query_string`
  - POST: `sign_str = timestamp + api_key + recv_window + body_json_str`
  - Header: `X-BAPI-API-KEY`, `X-BAPI-SIGN`, `X-BAPI-TIMESTAMP`, `X-BAPI-RECV-WINDOW`, `Content-Type: application/json`
  - `recv_window` 預設 `"5000"`（5s）
- 時間戳：ms epoch
- query string 按 key 排序（GET 簽名必須與 URL 順序一致）

Python 實作可直接用 `hmac.new(secret.encode(), sign_str.encode(), hashlib.sha256).hexdigest()`。

---

## 1. Call Site A — `strategy_ai_routes.py`（~900 LOC）

**檔案**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`

### 1.1 Method 使用點盤點

透過 `_get_rust_client()` singleton（line 37-54）拿 client，下游稱 `rc`：

| Line | Call | Args | Consumer reads |
|---|---|---|---|
| 99 | `rc.has_credentials()` | — | `bool` → envelope |
| 100 | `rc.base_url()` | — | `str` → envelope |
| 142 | `rc.refresh_balance()` | — | dict → `{**wallet, **session_baseline}`（unpacked）→ **所有 wallet keys 暴露給 GUI** |
| 291 | `rc.get_instrument(symbol)` | str | `.get("min_notional")` in `_fetch_min_notional` |
| 376 | `rc.get_positions("linear")` | "linear" | list → passed to `_attach_owner_strategy` → `p.get("symbol")` / `p.get("size")` / `p.get("qty")` / `p.get("markPrice")` / `p.get("avgPrice")` / `p.get("entry_price")` / `p.get("side")` |
| 415 | `rc.get_active_orders("linear")` | "linear" | list → `_normalize_order` reads `o.get("orderId"|"order_id")` / `o.get("orderStatus"|"order_status")` / `o.get("orderType"|"order_type")` / `o.get("triggerPrice"|"trigger_price")` / `o.get("createdTime"|"created_time")` / `o.get("updatedTime"|"updated_time")` |
| 488 | `rc.get_positions("linear")` | "linear" | for hint lookup — reads `p.get("symbol")` / `p.get("size")` / `p.get("qty")` / `p.get("side")` |
| 617 | `rc.get_positions("linear")` | "linear" | orphan sweep — reads `p.get("size")` / `p.get("qty")` / `p.get("symbol")` / `p.get("side")` |
| 843 | `rc.get_executions("linear", limit=50)` | "linear", 50 | list → `_normalize_execution` reads `f.get("execQty"|"exec_qty")` / `f.get("execPrice"|"exec_price")` / `f.get("execFee"|"exec_fee")` / `f.get("execTime"|"exec_time")` / `f.get("side")` / `f.get("closedPnl"|"closed_pnl")` / `f.get("is_long")` |

**關鍵觀察**：`_normalize_order` / `_normalize_execution` 的 fallback chain `f.get("camelCase") or f.get("snake_case")` 意味著**舊 PyO3 返回純 snake_case 就 OK**—— `.get("camelCase")` 返回 `None`，`or` 走到 snake_case 路徑。**新 httpx 版只要保持 snake_case，fallback chain 繼續工作**。

### 1.2 `_get_rust_client()` singleton 的改造

目前（line 30-54）：
```python
_RUST_BYBIT_CLIENT = None
_RUST_BRIDGE_AVAILABLE = None

def _get_rust_client():
    global _RUST_BYBIT_CLIENT, _RUST_BRIDGE_AVAILABLE
    if _RUST_BRIDGE_AVAILABLE is False:
        return None
    if _RUST_BYBIT_CLIENT is not None:
        return _RUST_BYBIT_CLIENT
    try:
        from openclaw_core import BybitClient
        _RUST_BYBIT_CLIENT = BybitClient()
        _RUST_BRIDGE_AVAILABLE = True
        logger.info("Rust BybitClient initialized (PyO3 bridge active) / Rust BybitClient 已初始化")
        return _RUST_BYBIT_CLIENT
    except Exception as e:
        _RUST_BRIDGE_AVAILABLE = False
        logger.warning(f"Rust BybitClient unavailable, using Python fallback: {e}")
        return None
```

遷移後：**singleton 語意保留**（call sites 依賴懶初始化 + fail-soft None），只換 import 和日誌文案。
變數名 `_RUST_BYBIT_CLIENT` / `_RUST_BRIDGE_AVAILABLE` 保留是可接受的（重命名風險大於收益 — 跨 module ref 不存在，grep 驗證過）。

### 1.3 Edit patch A1 — replace import + singleton factory

**file**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`

```python
# OLD (lines 29-54)
# ---------------------------------------------------------------------------
# Rust PyO3 bridge (PYO3-BYBIT) — lazy singleton
# Rust PyO3 橋接 — 懶加載單例
# ---------------------------------------------------------------------------
_RUST_BYBIT_CLIENT = None
_RUST_BRIDGE_AVAILABLE = None  # None = not checked yet / None = 尚未檢查


def _get_rust_client():
    """Get or create the Rust BybitClient singleton. Returns None if unavailable.
    獲取或創建 Rust BybitClient 單例。不可用時返回 None。"""
    global _RUST_BYBIT_CLIENT, _RUST_BRIDGE_AVAILABLE
    if _RUST_BRIDGE_AVAILABLE is False:
        return None
    if _RUST_BYBIT_CLIENT is not None:
        return _RUST_BYBIT_CLIENT
    try:
        from openclaw_core import BybitClient
        _RUST_BYBIT_CLIENT = BybitClient()
        _RUST_BRIDGE_AVAILABLE = True
        logger.info("Rust BybitClient initialized (PyO3 bridge active) / Rust BybitClient 已初始化")
        return _RUST_BYBIT_CLIENT
    except Exception as e:
        _RUST_BRIDGE_AVAILABLE = False
        logger.warning(f"Rust BybitClient unavailable, using Python fallback: {e}")
        return None
```

```python
# NEW
# ---------------------------------------------------------------------------
# Bybit REST client (PYO3-ELIMINATE-1 Phase 2) — lazy singleton
# httpx-based Python client replacing former PyO3 bridge.
# Bybit REST 客戶端 — 已從 PyO3 橋接遷移為純 Python httpx 實作。
# ---------------------------------------------------------------------------
_BYBIT_CLIENT = None
_BYBIT_CLIENT_AVAILABLE: bool | None = None  # None = not checked yet / None = 尚未檢查


def _get_rust_client():
    """Get or create the BybitClient singleton. Returns None if unavailable.
    Name `_get_rust_client` retained for call-site stability (grep-safe); the
    implementation is now pure-Python httpx (not Rust/PyO3).
    獲取或創建 BybitClient 單例。不可用時返回 None。函數名保留以降低改動面。"""
    global _BYBIT_CLIENT, _BYBIT_CLIENT_AVAILABLE
    if _BYBIT_CLIENT_AVAILABLE is False:
        return None
    if _BYBIT_CLIENT is not None:
        return _BYBIT_CLIENT
    try:
        from .bybit_rest_client import BybitClient
        _BYBIT_CLIENT = BybitClient()
        _BYBIT_CLIENT_AVAILABLE = True
        logger.info("BybitClient initialized (httpx) / BybitClient 已初始化（httpx）")
        return _BYBIT_CLIENT
    except Exception as e:
        _BYBIT_CLIENT_AVAILABLE = False
        logger.warning(f"BybitClient unavailable: {e}")
        return None
```

**Rationale 備註**：
- 函數名 `_get_rust_client` **保留** — grep 過所有 call sites 都在本檔內（9 處）+ `live_session_routes.py:224`（在 `_get_rust_client_safe()` fallback 中 `from .strategy_ai_routes import _get_rust_client`），改名風險 >> 收益。
- 舊 singleton 變數 `_RUST_BYBIT_CLIENT` / `_RUST_BRIDGE_AVAILABLE` 改名為 `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE`（無跨模塊 ref，確認過）。**CLAUDE.md §九 singleton 表**需同步改記錄（如有）。
- `Rust BybitClient initialized (PyO3 bridge active)` 日誌文案改為 `BybitClient initialized (httpx)` — 避免誤導生產運維判讀。

### 1.4 其他 call site 無需改動
第 99/100/142/291/376/415/488/617/843 行的 `rc.xxx()` 調用**完全不變**，因為新 client 契約與舊 API 方法簽名 / 返回 shape 嚴格一致（§0 已約束）。

### 1.5 Response shape 依賴 — E4 回歸 checklist（A 檔）

新 BybitClient 必須保證下列 key 存在且類型一致：

- **`refresh_balance()`** dict 必含：`total_equity` / `total_wallet_balance` / `total_available_balance` / `total_unrealised_pnl` / `coins[*].equity` / `coins[*].unrealised_pnl` / `account_type` / `updated_at_ms`
- **`get_instrument(sym)`** dict 必含：`min_notional`（`_fetch_min_notional` 依賴）
- **`get_positions(...)`** 每 item 必含：`symbol` / `side`（`"Buy"`/`"Sell"`）/ `size` 或 `qty` / `markPrice` 或 `avgPrice` 或 `entry_price`
- **`get_active_orders(...)`** 每 item 必含：`order_id` / `order_link_id` / `order_status` / `order_type` / `trigger_price` / `created_time` / `updated_time`（`_normalize_order` 的 camelCase fallback 繼續工作）
- **`get_executions(...)`** 每 item 必含：`exec_qty` / `exec_price` / `exec_fee` / `exec_time` / `side` / `closed_pnl`（0.0 for opens）

---

## 2. Call Site B — `live_session_routes.py`（1449 LOC）

**檔案**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py`

### 2.1 Method 使用點盤點

透過 `_get_rust_client_safe()` factory（line 196-227）拿 client，下游稱 `rc`：

| Line | Call | Purpose |
|---|---|---|
| 220-221 | `from openclaw_core import BybitClient` / `return BybitClient(environment=environment)` | Live slot factory（顯式 env 參數，非 singleton；每次 `_get_rust_client_safe()` 可能新建） |
| 224-225 | `from .strategy_ai_routes import _get_rust_client` / `return _get_rust_client()` | Demo fallback（共用 singleton） |
| 937 | `rc.refresh_balance()` | /live/balance |
| 972 | `rc.get_positions("linear")` | /live/positions |
| 1009 | `rc.get_active_orders("linear")` | /live/orders |
| 1091 | `rc.get_executions("linear", limit=50)` | /live/fills (Bybit fallback path) |
| 1135 | `rc.get_positions("linear")` | /live/positions/{symbol}/close — hint lookup |
| 1246 | `rc.instrument_count()` | LIVE-GATE-FALLBACK-1 prewarming check |
| 1247 | `rc.refresh_instruments("linear")` | LIVE-GATE-FALLBACK-1 warm cache |
| 1258 | `rc.round_qty(symbol, qty)` | LIVE-GATE-FALLBACK-1 step alignment |
| 1261 | `rc.place_order(...)` | **LIVE-GATE-FALLBACK-1 reduce_only close — the critical path** |
| 1305 | `rc.get_positions("linear")` | `_sweep_live_orphan_positions` — orphan sweep |

### 2.2 `_get_live_bybit_client` — `_get_rust_client_safe()` factory（line 196-227）

**關鍵**：這個 factory 不是 singleton — 它可能**每次調用都 new 一個 `BybitClient`**（當 live slot 存在時）。新 httpx 版如果每次 new 且 httpx client 有明顯構造成本（TCP pool 建立 / TLS handshake），會降低每個 /live/\* endpoint 性能。

**建議實作策略**（給另一個 agent 參考，非本 spec 強制）：
- 新 `BybitClient.__init__` 內持有一個 **module-level lazy `httpx.Client` pool**，或
- 按 `(environment, api_key)` tuple cache 實例（`functools.lru_cache`）

但 **本 spec 不強制** — parity test 只對響應 shape 下契約。性能調優可 Phase 2 後單獨做。

### 2.3 Edit patch B1 — factory import/construction swap

**file**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py`

```python
# OLD (lines 207-227)
    try:
        import os
        from pathlib import Path
        secrets_base = os.environ.get("OPENCLAW_SECRETS_DIR") or str(
            Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"
        )
        live_key_file = Path(secrets_base) / "live" / "api_key"
        if live_key_file.exists() and live_key_file.read_text(encoding="utf-8").strip():
            # Live slot configured — use it with correct server
            # Live 槽已配置 — 使用正確伺服器
            ep_file = Path(secrets_base) / "live" / "bybit_endpoint"
            endpoint = ep_file.read_text(encoding="utf-8").strip() if ep_file.exists() else "mainnet"
            environment = "live_demo" if endpoint == "demo" else "mainnet"
            from openclaw_core import BybitClient
            return BybitClient(environment=environment)
        # No live slot — fall back to demo
        # 無 live 槽 — 回退到 demo
        from .strategy_ai_routes import _get_rust_client
        return _get_rust_client()
    except Exception:
        return None
```

```python
# NEW
    try:
        import os
        from pathlib import Path
        secrets_base = os.environ.get("OPENCLAW_SECRETS_DIR") or str(
            Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"
        )
        live_key_file = Path(secrets_base) / "live" / "api_key"
        if live_key_file.exists() and live_key_file.read_text(encoding="utf-8").strip():
            # Live slot configured — use it with correct server
            # Live 槽已配置 — 使用正確伺服器
            ep_file = Path(secrets_base) / "live" / "bybit_endpoint"
            endpoint = ep_file.read_text(encoding="utf-8").strip() if ep_file.exists() else "mainnet"
            environment = "live_demo" if endpoint == "demo" else "mainnet"
            from .bybit_rest_client import BybitClient
            return BybitClient(environment=environment)
        # No live slot — fall back to demo
        # 無 live 槽 — 回退到 demo
        from .strategy_ai_routes import _get_rust_client
        return _get_rust_client()
    except Exception:
        return None
```

**只改 1 行**：`from openclaw_core import BybitClient` → `from .bybit_rest_client import BybitClient`。
其餘 factory 邏輯（slot 偵測 / `environment` 派生 / fallback 到 demo singleton）**完全保留** — Live 憑證讀取策略是跨平台 invariant，不屬於 PyO3→httpx 遷移範疇。

### 2.4 LIVE-GATE-FALLBACK-1 — 關鍵風險路徑（lines 1221-1276）

這是**最關鍵的 call site**。LIVE-GATE-FALLBACK-1 在 Live IPC channel 不可用時（Live pipeline 因 authorization.json 缺失/過期被 LIVE-GATE-BINDING-1 拒絕 spawn）直接通過 REST 發 reduce_only Market order 繞過 Rust engine。這是根原則 #6「失敗默認收縮」的**最後防線**。

**順序契約**（新 client 必須保證這個順序的語義等價）：
1. `rc.instrument_count()` == 0 → `rc.refresh_instruments("linear")` warm cache
2. `rc.round_qty(symbol, qty)` → aligned qty（None 時 fallback raw）
3. `rc.place_order(symbol, side, "Market", qty_aligned, category="linear", reduce_only=True)` → dict `{"order_id": ..., "order_link_id": ...}`

**risk**：如果新 httpx 版 `place_order` 改變了 kwargs 位置或返回 key，LIVE-GATE-FALLBACK-1 會在 authorization 失效時**無聲失敗**（`result.get("order_id")` 拿 None），operator 手動平倉按鈕顯示 closed=True 但實際 REST 沒下單。

**Mitigation**：
- §0.3 #11 `place_order` signature 嚴格鎖定（kwargs 位置與舊 PyO3 bridge `orders.rs:89-110` 一字不差）。
- parity test 對 mocked `/v5/order/create` 成功 response 斷言 `{"order_id", "order_link_id"}` 兩個 key 且值類型 `str`。
- E4 回歸需加一個 **LIVE-GATE-FALLBACK-1 整合測試**（mock `_is_live_channel_unavailable_error` = True，斷言 `place_order` 被調用且 kwargs 完全符合預期）。建議 E4 派發時同步加。

**No code change needed** in `_rest_close_position_reduce_only()` 本身 — 所有 method call 都通過 §0.3 契約保證。

### 2.5 Edit patch B2 — no change to LIVE-GATE-FALLBACK-1 body

**lines 1221-1276 不改**（除了頂部 import — 已在 B1 涵蓋）。

### 2.6 Response shape 依賴 — E4 回歸 checklist（B 檔）

比 A 檔多的依賴：
- **`instrument_count()`** → `int` （line 1246：`hasattr(rc, "instrument_count") and rc.instrument_count() == 0`）— 新 client 必須暴露這個 method，不得用 property。
- **`refresh_instruments("linear")`** → 不 raise → OK（返回值未使用）
- **`round_qty(symbol, qty)`** → `float` 或 `None`；line 1258 `float(rc.round_qty(symbol, qty))` 會在 None 時 raise `TypeError` 被 line 1260 `except Exception` 吞掉 → fallback raw qty。**保持 None 返回語意至關重要**。
- **`place_order(...)`** 返回 dict 含 `order_id` / `order_link_id`。

---

## 3. Call Site C — `helper_scripts/clean_restart_flatten.py`（182 LOC）

**檔案**: `helper_scripts/clean_restart_flatten.py`

### 3.1 Method 使用點盤點

| Line | Call | Purpose |
|---|---|---|
| 35 | `from openclaw_core import BybitClient` | import |
| 45 | `client = BybitClient(environment=args.env)` | direct construction, no singleton |
| 49 | `client.has_credentials()` | guard |
| 53 | `client.base_url()` | print |
| 58 | `client.refresh_instruments("linear")` | warm cache before place_order |
| 66, 146 | `client.get_positions("linear")` | list positions + verify loop |
| 79 | `client.get_active_orders("linear", None, "USDT")` | list orders（**注意 signature**：positional `category="linear", symbol=None, settle_coin="USDT"`） |
| 108 | `client.cancel_order(sym, oid, "linear")` | cancel order |
| 124, 165 | `client.place_order(symbol=..., side=..., order_type="Market", qty=..., category="linear", reduce_only=True)` | flatten |

### 3.2 Signature positional/keyword 注意

`get_active_orders("linear", None, "USDT")` 用**3 個 positional args** — 對應 `get_active_orders(category="linear", symbol=None, settle_coin="USDT")`。新 httpx 版必須接受 positional 形式（不能改成 kwargs-only）。

`cancel_order(sym, oid, "linear")` 也是 positional — 對應 `cancel_order(symbol, order_id, category="linear")`。

§0.3 已涵蓋 signature 約束；此處僅註記不要讓實作 agent 誤用 `*` 禁 positional。

### 3.3 Cross-package import path

`helper_scripts/` 不在 FastAPI app 套件內。import path 必須 absolute：
```python
# 新 import（assume repo root 在 PYTHONPATH 或 shell 已 activate .venv）
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.bybit_rest_client import BybitClient
```

這要求 `.venv/bin/activate` 後 `PYTHONPATH` 含 repo root，或 `program_code/...` 是 installable package。

**替代方案**（更穩 — 無 PYTHONPATH 依賴）：在 `helper_scripts/` 新建一個薄 proxy `bybit_rest_client.py` 或通過 `sys.path.insert(0, '...')` 手動加入。但這**增加了維護負擔**。

**推薦**：保持 absolute import，並在 docstring 改寫提示 activate 的 venv 即可：
```python
# line 39-41 現有 hint 已合適：
#     source program_code/exchange_connectors/bybit_connector/
#     control_api_v1/.venv/bin/activate
```
該 venv activate 會把 `site-packages` 加入，但仍需 app 套件可 import。若 activate 後 `from program_code.exchange_connectors...` import 失敗，可 `cd` 到 `/home/ncyu/BybitOpenClaw/srv/` 再運行 script（此時 `program_code/` 在 cwd，自動 on path）。

### 3.4 Edit patch C1 — script import + error message

**file**: `helper_scripts/clean_restart_flatten.py`

```python
# OLD (lines 34-41)
    # ── Import PyO3 bridge ───────────────────────────────────────────────
    try:
        from openclaw_core import BybitClient
    except ImportError as exc:
        print(f"[ERR] openclaw_core not importable: {exc}", file=sys.stderr)
        print("      Activate API venv first:", file=sys.stderr)
        print("      source program_code/exchange_connectors/bybit_connector/"
              "control_api_v1/.venv/bin/activate", file=sys.stderr)
        return 2
```

```python
# NEW
    # ── Import Python BybitClient (PYO3-ELIMINATE-1 Phase 2) ────────────
    # ── 使用純 Python httpx 版 BybitClient（已從 PyO3 遷移）
    try:
        from program_code.exchange_connectors.bybit_connector.control_api_v1.app.bybit_rest_client import BybitClient
    except ImportError as exc:
        print(f"[ERR] BybitClient not importable: {exc}", file=sys.stderr)
        print("      Activate API venv and cd to repo root:", file=sys.stderr)
        print("      cd /home/ncyu/BybitOpenClaw/srv  # or \\$OPENCLAW_BASE_DIR", file=sys.stderr)
        print("      source program_code/exchange_connectors/bybit_connector/"
              "control_api_v1/.venv/bin/activate", file=sys.stderr)
        return 2
```

並把 MODULE_NOTE（lines 5-11）改：
```python
# OLD
MODULE_NOTE (EN): Uses PyO3 openclaw_core.BybitClient to close every open
  position with reduce_only market orders and cancel every open order, for a
  given environment ("demo" or "mainnet"). Safe to run with the Rust engine
  stopped — talks to Bybit REST directly.
MODULE_NOTE (中): 使用 PyO3 openclaw_core.BybitClient 對指定環境（demo 或
  mainnet）的每個未平倉持倉下 reduce_only 市價單，並取消所有未成交訂單。
  Rust 引擎停止時可安全運行 — 直接透過 Bybit REST 通訊。
```
```python
# NEW
MODULE_NOTE (EN): Uses httpx-based BybitClient (PYO3-ELIMINATE-1 Phase 2) to
  close every open position with reduce_only market orders and cancel every
  open order, for a given environment ("demo" or "mainnet"). Safe to run with
  the Rust engine stopped — talks to Bybit REST directly.
MODULE_NOTE (中): 使用 httpx 版 BybitClient（PYO3-ELIMINATE-1 Phase 2 後）
  對指定環境（demo 或 mainnet）的每個未平倉持倉下 reduce_only 市價單，
  並取消所有未成交訂單。Rust 引擎停止時可安全運行 — 直接透過 Bybit REST 通訊。
```

### 3.5 Response shape 依賴 — E4 回歸 checklist（C 檔）

- `client.has_credentials()` → `bool`
- `client.base_url()` → `str`
- `client.refresh_instruments("linear")` → `int`（verify loop 不讀，只 print）
- `client.get_positions("linear")` 每 item：`.get("symbol")`, `.get("side")`, `.get("size")`, `.get("unrealisedPnl")` 或 snake_case `unrealised_pnl` → **⚠️ 注意 line 75**：
  ```python
  f"  • {p.get('symbol')} {p.get('side')} size={p.get('size')} "
  f"unrealPnL={p.get('unrealisedPnl')}"
  ```
  舊 PyO3 返回 `unrealised_pnl`（snake_case），`p.get("unrealisedPnl")` 返回 **None** → print 顯示 `unrealPnL=None`。這是**既存 bug**（PyO3 時代就有），**新版保持原樣**，不在 Phase 2 範疇修復。或趁機補 `p.get("unrealisedPnl") or p.get("unrealised_pnl")`（建議作為 follow-up，不阻塞遷移）。
- `client.get_active_orders("linear", None, "USDT")` → list；item 讀 `.get("symbol")`, `.get("orderId") or .get("order_id")`（line 104 fallback chain — OK）
- `client.cancel_order(sym, oid, "linear")` → dict（返回不讀，只 count）
- `client.place_order(...)` → `.get("order_id") or .get("orderId")`（line 134 fallback chain — OK）

---

## 4. 全域風險分析

### 4.1 LIVE-GATE-FALLBACK-1 會不會因切換破壞？

**結論：不會**，**前提**是 §0.3 契約嚴格執行。

風險窗口：
- 若新 `place_order` 對 `reduce_only=True` kwarg 解析有差（例如新版把 `reduce_only` 放到 body 的 `"reduceOnly": true`，但舊 PyO3 經 Rust 轉成了 `"reduceOnly": true` — 實際上 Bybit V5 body 就是這個 key，兩邊一致）。
- 若新版默認添加 `time_in_force="IOC"` 而舊版沒加 → 行為差（Market+IOC 正常；Market+GTC 可能 Bybit 拒絕，但舊 Rust 不填也通過）。
- 若新版在 `retCode != 0` 時 raise 而不 return empty dict → caller `except Exception as rest_exc` 會捕，走 503 HTTPException — 行為與舊版一致。

**Gate**：parity test 明確驗證 `place_order` 對同一 mocked response 返回的 dict key 集合。E4 回歸加 LIVE-GATE-FALLBACK-1 端到端 mock。

### 4.2 `refresh_instruments` paginate 行為變化

**舊 PyO3 (Rust `instrument_info.rs:162-200`)**：**單次 GET** `/v5/market/instruments-info?category=linear`，**不 paginate cursor**。Bybit V5 單次返回所有 linear perpetuals（~500 個），實測從來不分頁。

**新 httpx 版**：若實作 agent 決定主動支援 `nextPageCursor`（以防未來 symbol 數量 > 1000），新增 GET 次數會增加。
- **契約約束**：pagination 語意對 caller 透明（返回值仍是 `int` 總數）；caller 只讀 `instrument_count()` 做 warm check。
- **parity test**：用單頁 mock fixture（因 Rust 舊版行為）；多頁 fixture 可另行驗證新版能力，但**不作為 parity 必要條件**（新版能力超集 OK）。
- **風險**：若新版在單頁時行為與舊版差（例如老 fixture 有 501 symbols 但舊版其實只讀前 500 — 這種行為分歧 parity test 抓不到）。**不阻塞**。

### 4.3 HMAC 簽章時序差異

**舊 PyO3**：`common::bybit_signer::sign_rest_v5` Rust 實作 — C 級性能，微秒級。
**新 httpx**：`hmac.new(..., hashlib.sha256).hexdigest()` Python stdlib — 百微秒級。

簽章**值**在 Python/Rust 之間 byte-identical（HMAC-SHA256 是密碼學 primitive，兩端輸出相同 hex string）。**只有時序**不同。

風險：
- 若新 Python 版從 `timestamp_ms()` 到 `client.post().send().await` 之間耗時 >5s（`recv_window` 默認），Bybit 拒簽名 `retCode=10002`。
- Python 端測試：在 `_live_contraction_monitor` 等 async 任務高壓下（ThreadPool 耗盡 / asyncio 阻塞），`httpx` client 建 TCP 可能慢。
- Mitigation：`recv_window="5000"` 通常足夠；如觀察到 10002 可調整為 `"20000"`。這是**運行時調優**，不阻塞 Phase 2 合併。

### 4.4 FastAPI async 上下文中阻塞調用

**舊 PyO3**：`rc.refresh_balance()` / `rc.get_positions(...)` 都是 **sync Python calls**（由 PyO3 內部 tokio runtime 橋接）— 會**阻塞 asyncio event loop**。`strategy_ai_routes.py` 原有 callers 也**都是 `async def`**（`get_demo_balance` / `get_demo_positions` 等），在同一 event loop 下。

**既存問題**：舊版每次 Bybit REST 查詢都 **blocks 整個 uvicorn worker 的 event loop ~200ms-2s**。這是繼承的 poor practice。

**新 httpx**：若實作 agent 用 `httpx.Client().get(...)` 同步版本，**保持相同阻塞語意**，parity 維持，部署無回歸。
若改用 `httpx.AsyncClient` + `async def` methods，caller 必須改 `await`，**破壞 §0.3 signature 契約**。

**Spec 決策**：**要求 sync API**（與 PyO3 對等）。AsyncClient 升級留給 Phase 3 或 post-migration 優化，**不列入本 Phase**。如果實作 agent 已實作 async，必須另外暴露 sync facade。

### 4.5 Singleton vs per-instance resource leak

`strategy_ai_routes._get_rust_client()` 返回**單例** — 所有 demo endpoint 共用同一 `BybitClient`，其內部 `httpx.Client` TCP pool 跨 request 共用。
`live_session_routes._get_rust_client_safe()` **每次可能 new**（live slot 存在時） — 如果新 httpx client 每次 new 且**不 `close()`**，TCP socket 會 leak。

**Mitigation**：
- 建議實作 agent 在 `BybitClient.__init__` 內持有 module-level `httpx.Client` pool 單例（按 `(env, key)` cache）。
- 若做不到，`live_session_routes` 也需要 singleton 化 — 但這**超出本 spec 範疇**，可作為 follow-up 工單。

### 4.6 跨平台依賴

新 `bybit_rest_client.py` 依賴：
- `httpx>=0.28.0` — 已在 `requirements.txt` line 27 確認
- `hmac` / `hashlib` — stdlib
- 無平台特定依賴 → Mac 部署乾淨

---

## 5. Parity test coverage matrix

| Method | Fixture | Mode A (both) | Mode B (new only) |
|---|---|---|---|
| `has_credentials` | — (stub env) | ✅ | ✅ |
| `base_url` | — (env) | ✅ | ✅ |
| `refresh_balance` | `wallet_balance.json` | ✅ key/type | ✅ snapshot |
| `refresh_balance` (retCode!=0) | `wallet_balance_error.json` | ✅ raise | ✅ raise |
| `refresh_instruments` | `instruments_info_linear.json` | ✅ count | ✅ snapshot |
| `get_instrument(cached)` | (post refresh) | ✅ shape | ✅ shape |
| `get_instrument(uncached)` | — | ✅ None | ✅ None |
| `get_positions` | `positions_list.json` | ✅ item shape | ✅ snapshot |
| `get_active_orders` | `order_realtime.json` | ✅ item shape | ✅ snapshot |
| `get_executions` | `execution_list.json` | ✅ item shape | ✅ snapshot |
| `place_order` (success) | `order_create_success.json` | ✅ 2-key | ✅ 2-key |
| `cancel_order` | `order_cancel_success.json` | ✅ 2-key | ✅ 2-key |
| `round_qty(cached)` | (post refresh) | ✅ float | ✅ float |
| `round_qty(uncached)` | — | ✅ None | ✅ None |
| `instrument_count` | (pre/post refresh) | ✅ int | ✅ int |

---

## 6. Rollback plan

如 Phase 2 apply 後發現 parity 破洞 / live 路徑異常，單次 revert 即可回到 PyO3 狀態：

```bash
# Scenario A: 尚未合併到 main — 直接丟 commit
git reset --hard <commit-before-phase-2>

# Scenario B: 已合併到 main — 產 revert commit
git revert <phase-2-commit>
```

**revert 後狀態**：
- 3 個 call sites 的 `from openclaw_core import BybitClient` 恢復 → 需確認 PyO3 cdylib 仍存在
- 新建的 `bybit_rest_client.py` 會被 revert 刪除 → 引擎運行時無副作用
- parity test 文件（`test_bybit_rest_client_parity.py` + `tests/fixtures/bybit_v5_responses/*.json`）會同時被 revert 刪除 — 如要保留，從 revert commit 裡挑這部分單獨 cherry-pick

**注意**：Phase 1（dead-code deletion）**不需要 rollback** — `ContextDistiller` / `HedgingEngine` 有 0 callers；Phase 1 可獨立保留。

**部署回退檢查清單**：
- [ ] `openclaw_pyo3` crate 編譯仍通過（`cargo build -p openclaw_pyo3 --release`）
- [ ] `openclaw_core.so` 在 active venv 的 `site-packages/` 存在
- [ ] pytest `test_bybit_demo_sync.py` 綠
- [ ] GUI `/api/v1/strategy/demo/balance` 返回 `enabled: true`

---

## 7. Deployment order（給 PM 參考）

1. **實作 agent 完成** `bybit_rest_client.py` → commit `feat(connector): PYO3-ELIMINATE-1 Phase 2 httpx client`
2. **本 spec 產出** parity test harness + fixtures → commit `test(connector): PYO3-ELIMINATE-1 parity test harness`
3. **PM 本地跑** parity test Mode A（並排新舊）→ **必須全綠** → 決策 gate
4. **PM apply migration patches**（A1 / B1 / C1）→ commit `refactor(connector): PYO3-ELIMINATE-1 Phase 2 — migrate BybitClient callers to httpx`
5. **E4 回歸** — pytest 全量 + engine lib + `helper_scripts/clean_restart_flatten.py --env demo --dry-run` 實測
6. **Deployment** — `./helper_scripts/restart_all.sh --rebuild`（PyO3 binary 仍會被編譯，但不再被 Python import）
7. **Phase 3** — 2-3 天觀察期後刪 `openclaw_pyo3` crate（詳 TODO.md §PYO3-ELIMINATE-1 Phase 3）

---

## 8. Signature 偏離 / 合作衝突點（給實作 agent）

1. **函數名**：`BybitClient` 保留；`_get_rust_client()` 不改（調用方已 grep-lock）。
2. **錯誤類型**：實作 agent 若用 `httpx.HTTPError` 原樣拋出，caller 全是 `except Exception`，OK。若套 custom `BybitApiError(RuntimeError)`，parity test 需同時驗證 error message 含 `"retCode="`（舊 PyO3 格式）。
3. **`round_qty` 未緩存返回值**：必須 `None`，不得返回 raw `qty` — caller 的 `float(None)` TypeError 是預期路徑。
4. **`get_positions` 無持倉返回值**：必須 `[]`（empty list），不得 `None`。caller `for p in positions:` 會 TypeError。
5. **`environment="demo"` 預設**：必須保留（LIVE-GUARD-1 安全默認；clean_restart_flatten.py:27 argparse 默認也是 "demo"）。
6. **`refresh_balance` updated_at_ms**：必須填當前時間（ms epoch），不得 0；GUI 讀這個判新鮮度。
7. **signature**：sign_str 格式必須是 `timestamp + api_key + recv_window + params`（GET: sorted query string；POST: body JSON string）—— 順序、拼接方式不可變。
8. **`get_active_orders` positional**：必須支援 `get_active_orders("linear", None, "USDT")` 形式（clean_restart_flatten.py:79）。不可用 `*` 強制 kwargs-only。

---

## 9. 完成驗收 checklist

- [ ] 實作 agent 交付 `bybit_rest_client.py`
- [ ] Parity test Mode A 全綠（`OPENCLAW_PYO3_PARITY_MODE=both pytest tests/test_bybit_rest_client_parity.py -v`）
- [ ] 本 spec A1 / B1 / C1 三個 patch apply 完成
- [ ] pytest 全量綠 + engine lib 1629+ passed / 0 failed
- [ ] `helper_scripts/clean_restart_flatten.py --env demo --dry-run` 能正常 list positions
- [ ] GUI `/api/v1/strategy/demo/balance` 返回 `enabled: true` + `balance` > 0
- [ ] `/api/v1/live/positions` endpoint 在 live slot 配置時能拉到 Bybit 數據
- [ ] grep 驗證 `from openclaw_core` 零結果（3 call sites 全清乾淨）
- [ ] CLAUDE.md §九 singleton 表（若有 `_RUST_BYBIT_CLIENT` 條目）同步改名

---

## 10. 附錄：migration 後 TODO.md §PYO3-ELIMINATE-1 Phase 2 更新

```markdown
**Phase 2 · `BybitClient` 3 call sites Python 化（~0.5-1 day）✅ 2026-04-20**
- [x] 先分析 3 call sites 實際調用的 `BybitClient` 方法集（12 methods 盤點完）
- [x] 決策：Python httpx 重寫（理由見 Phase 2 method surface 實測段）
- [x] 實作 + 單測對等（`tests/test_bybit_rest_client_parity.py`, 12 methods full matrix）
- [x] 3 call sites 遷移（strategy_ai_routes.py / live_session_routes.py / clean_restart_flatten.py）
- [x] 刪除 `from openclaw_core import BybitClient`（grep 零結果驗證）
- [x] commit：`refactor(connector): PYO3-ELIMINATE-1 Phase 2 — migrate BybitClient callers to httpx`
```

— END OF SPEC —
