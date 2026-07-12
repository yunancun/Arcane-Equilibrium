"""
MODULE_NOTE (中文):
  模塊用途：為手動/定時對賬提供「伺服器端」快照組裝，回傳 ReconciliationEngine
    契約形狀 {orders:list, positions:dict-by-symbol, fills:list, snapshot_ts_ms:int,
    balances:dict}。取代前端偽造 paper_state 的死路徑（governance.js 的 L1/L2/L3）。
  主要函數：
    - build_local_reconcile_snapshot(engine="demo")：讀 Rust 引擎 IPC 快照 → 契約形狀。
      engine 為一級參數，因對賬「哪一對」尚未 Linux runtime 證實（UNKNOWN-1）；預設 "demo"
      表示比對「demo 引擎本地鏡像 vs api-demo 交易所」，未來確認 paper 也鏡像到 api-demo
      時可無改寫地翻轉為 engine="paper"。
    - build_demo_reconcile_snapshot()：以 httpx BybitClient(env=demo, api-demo, 只讀) 拉取
      交易所真實狀態 → 契約形狀。RE-POINT 自 bybit_demo_sync.get_current_snapshot 的孤兒邏輯。
  依賴：ipc_state_reader.get_rust_reader（Rust IPC 快照）、strategy_ai_routes._get_rust_client
    （只讀 httpx demo client，複用既有 slot/env 憑證解析）、bybit_rest_client 的錯誤型別。
  硬邊界：
    - build_demo 的任一原語 raise / retCode≠0 / 憑證缺 / 槽位缺 → 拋 DemoSnapshotUnavailable，
      呼叫端必 fail-closed（route 回 STALE_DATA，絕不進 engine.reconcile）。**絕不回空 {}**：
      空 demo 會讓 reconcile 把每個本地持倉判為 FATAL POSITION_MISSING → 誤凍結。
    - 只連 api-demo；永不 mainnet（沿用 _get_rust_client 預設 environment="demo",
      mainnet 仍由 OPENCLAW_ALLOW_MAINNET 門把守）。不新增任何明文憑證路徑。
    - 本模塊為 Python 控制面「讀取/組裝」邏輯，不下單、不改交易狀態。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .ipc_state_reader import get_rust_reader

logger = logging.getLogger(__name__)


class DemoSnapshotUnavailable(Exception):
    """demo 端不可信（憑證缺 / 槽位缺 / httpx raise / retCode≠0）。呼叫端必須 fail-closed。

    為什麼是獨立型別：route 需要能與其他錯誤區分,以便「demo 不可達」永遠短路為
    STALE_DATA 而**不**呼叫 engine.reconcile —— demo 不可達永遠不得凍結交易。
    """


def _infer_category(symbol: str) -> str:
    """從 symbol 推斷合約品類（鏡像 demo_snapshot_payloads.py:240-242）。

    為什麼：Bybit inverse 合約以 USD 結尾（如 BTCUSD）、linear 以 USDT 結尾;
    對賬持倉需帶 category 以便下游辨識。
    """
    return "inverse" if symbol.endswith("USD") and not symbol.endswith("USDT") else "linear"


def build_local_reconcile_snapshot(engine: str = "demo") -> Optional[dict[str, Any]]:
    """讀 Rust 引擎 IPC 快照,轉為 ReconciliationEngine 契約形狀;引擎不可用回 None。

    Args:
        engine: Rust 引擎鍵（"demo"/"paper"/"live"）。預設 "demo" = 綁定 Bybit Demo
            錢包的引擎。保留為一級參數以便 UNKNOWN-1 定案後翻轉比對對象而不改寫。

    Returns:
        契約 dict {orders, positions(dict), fills, snapshot_ts_ms, balances(dict)},
        或 None（引擎不可用 / reader 缺失 → 呼叫端 fail-closed，不對賬）。

    形狀轉換（IPC → 契約）:
        - positions: LIST → DICT-by-symbol,side=("Buy" if is_long else "Sell"),
          size=float(size or qty),drop size==0,category 由 symbol 推斷。
        - balances: SCALAR → {"USDT": float(balance)}。
        - fills: get_recent_fills(mode=engine),缺 side 時由 is_long 補。
        - orders: [] （v2.B 範圍排除：交易所是掛單唯一權威,引擎 exchange 模式無權威本地掛單簿,
          比對只是滯後回音 → race 誤報;對應 ReconciliationConfig.reconcile_orders 預設 False)。
    """
    reader = get_rust_reader()
    # fail-closed：reader 缺失或該引擎快照過期/不可用 → None,呼叫端短路為 STALE_DATA。
    if reader is None or not reader.is_engine_available(engine):
        return None

    paper_state = reader.get_paper_state(engine=engine)
    if paper_state is None:
        return None

    # positions LIST → DICT-by-symbol
    positions: dict[str, Any] = {}
    for p in paper_state.get("positions", []) or []:
        if not isinstance(p, dict):
            continue
        symbol = str(p.get("symbol") or "")
        if not symbol:
            continue
        try:
            size = float(p.get("size") or p.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if size == 0:
            continue  # 空倉不入對賬,避免噪音
        positions[symbol] = {
            "side": "Buy" if p.get("is_long", True) else "Sell",
            "size": size,
            "avg_entry_price": p.get("entry_price", p.get("avg_entry_price", 0)),
            "category": _infer_category(symbol),
        }

    # balance SCALAR → {"USDT": float}
    try:
        balance = float(paper_state.get("balance", 0) or 0)
    except (TypeError, ValueError):
        balance = 0.0
    balances = {"USDT": balance}

    # fills：複製後補 side（不原地污染 reader 快照）
    fills: list[dict[str, Any]] = []
    for f in reader.get_recent_fills(mode=engine) or []:
        if not isinstance(f, dict):
            continue
        row = dict(f)
        if "side" not in row:
            row["side"] = "Buy" if row.get("is_long") else "Sell"
        fills.append(row)

    return {
        # 訂單刻意排除於對賬範圍外(v2.B 決策):交易所是掛單唯一權威,引擎在 exchange 模式
        # 不保留權威本地掛單簿(paper_state/mod.rs:129-137);與交易所比對只是滯後回音,必然
        # 製造 race 誤報。對應 ReconciliationConfig.reconcile_orders 預設 False。
        # 未來若要開本地訂單對賬,務必在 orderLinkId 配對「之前」先濾掉空 orderLinkId 的條件單
        # (Untriggered 條件停損),否則它們會全部塌成 key "" 互相誤報(v2.B.3 綁定約束)。
        "orders": [],
        "positions": positions,
        "fills": fills,
        "snapshot_ts_ms": int(time.time() * 1000),
        "balances": balances,
    }


def build_demo_reconcile_snapshot() -> dict[str, Any]:
    """以只讀 httpx BybitClient（env=demo, api-demo）拉取交易所狀態 → 契約形狀。

    RE-POINT 自 bybit_demo_sync.get_current_snapshot 的孤兒邏輯,改用 httpx client 的
    RAW-LIST 回傳 + retCode≠0 直接 raise 的語意。

    Returns:
        契約 dict {orders, positions(dict), fills, snapshot_ts_ms, balances(dict)}。

    Raises:
        DemoSnapshotUnavailable: client 不可用（憑證/槽位缺）、任一原語 raise、
            或任一 retCode≠0。**絕不回空 {}**（空 demo 會偽造 FATAL POSITION_MISSING
            → 誤凍結）。
    """
    # 延遲匯入避免與 strategy_ai_routes 的循環匯入（沿用 paper_trading_routes 的模式）。
    from .strategy_ai_routes import _get_rust_client

    client = _get_rust_client()
    if client is None:
        # 憑證缺 / 槽位缺 / client 構造失敗 → _get_rust_client 回 None → fail-closed。
        raise DemoSnapshotUnavailable("bybit_demo_client_unavailable")

    try:
        # ── 持倉：linear（settleCoin=USDT）+ inverse。RAW-LIST,retCode≠0 會 raise。──
        positions: dict[str, Any] = {}
        # 為什麼分兩類：現貨故意排除（現貨體現為餘額變動非持倉列,見孤兒邏輯註解）。
        # v1 已知限制：inverse 為幣本位（結算幣非 USDT）,settleCoin=USDT 之 full-scan
        #   對 inverse 回空列 → inverse 幣本位持倉在 v1 未捕捉,待 Linux runtime 確認
        #   demo 帳戶實際持有後再擴。linear USDT 為主要資產類,優先保證正確。
        for category in ("linear", "inverse"):
            rows = client.get_positions_full_scan(category, settle_coin="USDT")
            for pos in rows or []:
                if not isinstance(pos, dict):
                    continue
                symbol = str(pos.get("symbol") or "")
                try:
                    size = float(pos.get("size") or 0)
                except (TypeError, ValueError):
                    continue
                if symbol and size > 0:
                    positions[symbol] = {
                        "side": pos.get("side"),
                        "size": size,
                        "avg_entry_price": float(pos.get("avgPrice") or 0),
                        "category": category,
                    }

        # ── 掛單：linear 活躍掛單（full-scan cursor,fail-closed）。──
        orders = client.get_active_orders_full_scan("linear", settle_coin="USDT") or []

        # ── 成交：linear 最近成交（Bybit camelCase,reconcile 引擎容錯讀 execQty/execPrice）。──
        # 只保留真實成交 execType∈{Trade,AdlTrade,BustTrade};濾掉 Funding/Settle 等非成交事件。
        # 為什麼:Bybit get_executions 會混入資金費結算(execType=Funding)列,虛增遠端成交數 →
        # 誤報 FILL_COUNT。缺 execType 的列(真實 API 恆帶,僅極簡 stub 才缺)保守視為 Trade 保留,
        # 避免誤丟合法成交(v2.C 遠端資料衛生)。
        _TRADE_EXEC_TYPES = {"Trade", "AdlTrade", "BustTrade"}
        raw_fills = client.get_executions("linear", limit=50) or []
        fills = [
            f for f in raw_fills
            if isinstance(f, dict) and f.get("execType", "Trade") in _TRADE_EXEC_TYPES
        ]

        # ── 餘額：refresh_balance()["coins"] = {coin: {wallet_balance, ...}} → {coin: bal}。──
        balances: dict[str, float] = {}
        coins = client.refresh_balance().get("coins") or {}
        for coin_name, coin_data in coins.items():
            if not isinstance(coin_data, dict):
                continue
            try:
                bal = float(coin_data.get("wallet_balance") or 0)
            except (TypeError, ValueError):
                continue
            if coin_name and bal > 0:
                balances[coin_name] = bal

        return {
            "orders": list(orders),
            "positions": positions,
            "fills": list(fills),
            "snapshot_ts_ms": int(time.time() * 1000),
            "balances": balances,
        }
    except DemoSnapshotUnavailable:
        raise
    except Exception as e:
        # 任一原語 raise（BybitBusinessError retCode≠0 / BybitTransportError / 憑證缺）
        # → 一律 fail-closed 為 DemoSnapshotUnavailable。絕不吞成空 demo。
        logger.warning("Demo reconcile snapshot unavailable: %s", e)
        raise DemoSnapshotUnavailable(str(e)) from e
