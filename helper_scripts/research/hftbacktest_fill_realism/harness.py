"""hftbacktest 離線 maker fill 模擬核心（passive maker 限價單反 cascade）。

MODULE_NOTE:
  模塊用途：對一組「掛單規格」（每個 cascade 事件一張反向 passive maker 限價單）
    在 hftbacktest 重放上模擬：是否成交、queue position、成交後逆選擇 bps、
    time-based exit 收斂——回每事件 outcome + 聚合 fill_rate / 逆選擇 / net。
    **未成交的單必計入 fill_rate 分母**（D2 non-harvestable 假說核心）。
  依賴：numpy + numba + hftbacktest（2.x）。
  關鍵 API 形態（hftbacktest 2.4.4，PA design §2.2 假設的 ProbQueueModel 頂層類
    在 2.x 已改為 BacktestAsset builder method——本實作對齊真實 2.x API）：
    - queue model：BacktestAsset.log_prob_queue_model() / power_prob_queue_model(n)
      / risk_adverse_queue_model()（非頂層 ProbQueueModel 類）。
    - fee model：trading_value_fee_model(maker_fee, taker_fee)（比例 fee）。
      **本 harness 的 net 不靠引擎 fee model 算最終 bps**（引擎 fee 只供模擬內
      撮合參考）；最終 net 在 Python 端由 ``__init__.MAKER_FEE_BPS_PER_LEG`` 與
      ``MAKER_REBATE_BPS=0`` 顯式計算（rebate 鐵則執行點集中於一處）。
    - 下單：submit_buy_order/submit_sell_order(..., GTX, LIMIT, ...)；GTX =
      post-only（maker-only，被動掛單），確保模擬的是 maker 行為非 taker。
    - 重放：njit 函數內 hbt.elapse(ns) 推進、hbt.depth(0).best_bid/ask 取 BBO、
      hbt.orders(0).get(id) 查單狀態。
  leak hot-spot：entry 必落事件後——掛單推進 = 事件 detect 時戳起算（caller
    bridge_d2 已把 cascade 對齊到事件後第一個 tick + feed latency），harness 只
    在「elapse 到事件時戳之後」才 submit，逐單斷言 entry_ts >= event_ts。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MakerOrderSpec:
    """單張反 cascade passive maker 限價單規格（由 bridge_d2 依事件構造）。

    side：'buy'（接被 Sell-清算的下殺，掛 bid 反 cascade）/ 'sell'（接被 Buy-清算
      的上衝，掛 ask 反 cascade）。
    event_ts_ns：cascade 事件 detect 時戳（ns）；entry 必須 >= 此值（leak guard）。
    peg_offset_bps：相對「事件當時 live BBO」的掛單偏移（bps，>=0）。
      0 = 貼 BBO（buy 貼 best_bid / sell 貼 best_ask，最積極的被動 maker）；
      >0 = 退到 BBO 更深處接超調（buy 掛 bid 下方 / sell 掛 ask 上方）。
      **必須相對 live BBO 而非 cascade 的 stale liquidation price**——清算執行價
      在 cascade 偵測時已偏離現價數十 bps，用它定錨會把掛單推到簿外永不成交
      （peg artifact，非真 non-harvestable）。peg 在 harness 內以事件當時 BBO 算。
    exit_horizon_ns：time-based exit 窗（半衰期內收斂）。
    """

    event_id: str
    side: str
    event_ts_ns: int
    peg_offset_bps: float
    qty: float
    exit_horizon_ns: int


@dataclass
class FillOutcome:
    """單事件模擬結果（未成交也記，計入 fill_rate 分母）。"""

    event_id: str
    side: str
    submitted: bool
    filled: bool
    entry_ts_ns: int
    fill_ts_ns: int
    fill_px: float
    # 逆選擇：成交後 exit 窗末的中價相對成交價的不利位移（bps，對 maker 不利為正）。
    adverse_selection_bps: float
    # convergence：exit 窗末中價相對成交價的有利收斂（bps，maker 角度毛利）。
    convergence_bps: float
    reason: str = ""


@dataclass
class SimResult:
    outcomes: list[FillOutcome] = field(default_factory=list)
    n_events: int = 0
    n_submitted: int = 0
    n_filled: int = 0
    errors: list[str] = field(default_factory=list)


def _to_ns(value_us_or_ns: int) -> int:
    """Tardis 時戳是微秒；hftbacktest event array 已由 converter 轉成 ns，此處留作守衛。"""
    return int(value_us_or_ns)


def simulate_maker_fills(
    event_array,
    specs: list[MakerOrderSpec],
    *,
    tick_size: float,
    lot_size: float,
    entry_latency_ns: int = 10_000_000,
    resp_latency_ns: int = 10_000_000,
    maker_fee_rate: float = 0.0002,
    taker_fee_rate: float = 0.000275,
    queue_model: str = "log_prob",
) -> SimResult:
    """對每張掛單規格跑一次獨立 hftbacktest 重放，回逐事件 fill outcome。

    每事件獨立重放（而非單次重放掛多單）的理由：D2 事件是反事實「若當時掛這張單
    會不會成交」，事件間不應互相影響對方的 queue/depth（我們從未真的同時掛這些
    單）；獨立重放隔離每事件的 counterfactual fill。

    hftbacktest 不可用 → SimResult.errors 記錄，caller 導向 BLOCKED（不偽造 fill）。
    """
    try:
        import hftbacktest as h
        import numpy as np  # noqa: F401
        from numba import njit
    except Exception as exc:  # noqa: BLE001 —— 套件缺席導向 BLOCKED，不自製近似。
        return SimResult(errors=[f"hftbacktest_unavailable:{exc!r}"], n_events=len(specs))

    result = SimResult(n_events=len(specs))

    # 把 event_array 切成 initial snapshot（首 timestamp 的 depth 行）+ feed。
    # converter 產出的 array 已含完整 depth/trade 序列；hftbacktest 需一份
    # initial_snapshot（同 dtype）。最簡正確做法：用空 snapshot + 完整 data 重放，
    # 讓引擎自 data 內首批 depth 行建簿（與官方 tardis example 一致）。
    empty_snap = np.empty(0, dtype=h.event_dtype)

    def _build_hbt(data):
        asset = h.BacktestAsset().data(data).linear_asset(1.0).tick_size(tick_size).lot_size(lot_size)
        asset = asset.constant_order_latency(entry_latency_ns, resp_latency_ns)
        if queue_model == "power_prob":
            asset = asset.power_prob_queue_model(3)
        elif queue_model == "risk_averse":
            asset = asset.risk_adverse_queue_model()
        else:
            asset = asset.log_prob_queue_model()
        asset = asset.no_partial_fill_exchange()
        asset = asset.trading_value_fee_model(maker_fee_rate, taker_fee_rate)
        asset = asset.initial_snapshot(empty_snap)
        return h.HashMapMarketDepthBacktest([asset])

    GTX = h.GTX
    LIMIT = h.LIMIT
    FILLED = h.FILLED

    @njit(cache=False)
    def _run_one(hbt, event_ts_ns, is_buy, peg_offset_bps, qty, exit_horizon_ns):
        # 關鍵：hftbacktest 的 elapse(duration) 吃「相對時長 ns」非「絕對時戳」。
        # 推進到事件絕對時戳 = 先 elapse 1ns bootstrap 讓 current_timestamp 落在資料
        # 首事件時戳，再 elapse (event_ts − current_timestamp) 補到事件時戳。
        # leak guard：entry 必落事件後，entry_ts >= event_ts 才算合法。
        if hbt.elapse(1) != 0:
            return (0, 0, 0, 0, 0.0, 0.0, 0.0)
        now0 = hbt.current_timestamp
        if event_ts_ns < now0:
            # 事件落在 L2 tape 起點之前（同窗但 tape 未覆蓋此刻）→ 無法 replay，
            # 視為未提交（非 leak、非成交；不偽造 fill）。
            return (0, 0, now0, 0, 0.0, 0.0, 0.0)
        to_event = event_ts_ns - now0
        if to_event > 0:
            if hbt.elapse(to_event) != 0:
                # 資料在抵達事件前用盡（事件落在 tape 尾後）→ 未提交。
                return (0, 0, hbt.current_timestamp, 0, 0.0, 0.0, 0.0)
        entry_ts = hbt.current_timestamp
        depth = hbt.depth(0)
        bb = depth.best_bid
        ba = depth.best_ask
        if bb <= 0.0 or ba <= 0.0:
            # 簿尚未建立（無 BBO）→ 視為未成交。
            return (0, 0, entry_ts, 0, 0.0, 0.0, 0.0)
        # 掛單價：相對「事件當時 live BBO」算 peg（非 stale liquidation price）。
        # buy 掛 best_bid 下方 peg_offset_bps（接下殺超調）；sell 掛 best_ask 上方。
        # peg_offset_bps=0 即貼 BBO（最積極被動 maker）。GTX(post-only) 保證 maker。
        order_id = 1
        if is_buy:
            px = bb * (1.0 - peg_offset_bps / 1e4)
            hbt.submit_buy_order(0, order_id, px, qty, GTX, LIMIT, False)
        else:
            px = ba * (1.0 + peg_offset_bps / 1e4)
            hbt.submit_sell_order(0, order_id, px, qty, GTX, LIMIT, False)
        submitted = 1
        # 在 exit 窗內推進，偵測成交。
        deadline = event_ts_ns + exit_horizon_ns
        filled = 0
        fill_ts = 0
        fill_px = 0.0
        while hbt.current_timestamp < deadline:
            if hbt.elapse(1_000_000_000) != 0:
                break
            o = hbt.orders(0).get(order_id)
            if o is not None and o.status == FILLED:
                filled = 1
                fill_ts = hbt.current_timestamp
                # post-only(GTX) maker 單成交價 = 我們掛的 maker 價（px），不會 taker 穿價。
                fill_px = px
                break
        # 取 exit 窗末中價算收斂/逆選擇。
        d2 = hbt.depth(0)
        eb = d2.best_bid
        ea = d2.best_ask
        mid_end = (eb + ea) * 0.5 if (eb > 0.0 and ea > 0.0) else fill_px
        return (submitted, filled, entry_ts, fill_ts, fill_px, mid_end, px)

    for spec in specs:
        try:
            data = event_array
            hbt = _build_hbt(data)
            is_buy = spec.side == "buy"
            (submitted, filled, entry_ts, fill_ts, fill_px, mid_end, used_px) = _run_one(
                hbt,
                _to_ns(spec.event_ts_ns),
                is_buy,
                float(spec.peg_offset_bps),
                float(spec.qty),
                int(spec.exit_horizon_ns),
            )
            hbt.close()
            # leak guard 逐單斷言：**只對真正提交的單**檢查 entry 必落事件後。
            # 未提交（事件落在 tape 窗外/無 BBO）的 entry_ts 是 tape 起點，合法地
            # 早於 event_ts，不算 leak（我們根本沒掛單）。提交了卻 entry<event = 真 leak。
            if submitted and entry_ts and entry_ts < spec.event_ts_ns:
                result.errors.append(f"leak:{spec.event_id}:entry_ts<{spec.event_ts_ns}")
            adverse_bps = 0.0
            conv_bps = 0.0
            if filled and fill_px > 0.0 and mid_end > 0.0:
                # maker 角度：buy 後價漲=收斂(有利)、價跌=逆選擇(不利)；sell 反之。
                signed = (mid_end - fill_px) / fill_px * 1e4
                if not is_buy:
                    signed = -signed
                if signed >= 0.0:
                    conv_bps = signed
                else:
                    adverse_bps = -signed
            result.outcomes.append(
                FillOutcome(
                    event_id=spec.event_id,
                    side=spec.side,
                    submitted=bool(submitted),
                    filled=bool(filled),
                    entry_ts_ns=int(entry_ts),
                    fill_ts_ns=int(fill_ts),
                    fill_px=float(fill_px),
                    adverse_selection_bps=float(adverse_bps),
                    convergence_bps=float(conv_bps),
                    reason="filled" if filled else "not_filled",
                )
            )
            result.n_submitted += int(submitted)
            result.n_filled += int(filled)
        except Exception as exc:  # noqa: BLE001 —— 逐事件隔離，單事件崩潰不毀整批。
            result.errors.append(f"sim_error:{spec.event_id}:{exc!r}")
            logger.warning("事件模擬失敗 event=%s：%s", spec.event_id, exc)

    return result
