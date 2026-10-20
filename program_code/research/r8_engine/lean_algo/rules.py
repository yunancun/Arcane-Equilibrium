"""增補指令 §3、§9 的確定性規則；不存取資料檔或 LEAN。"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from statistics import median
from collections.abc import Mapping
from types import MappingProxyType
import hashlib
import json

from program_code.research.r8_ledger.ledger import canonical

HOUR = 3600000
DAY = 24 * HOUR
IMAGE_DIGEST = "sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6"
RUNTIME_METADATA = {
    "cost_model": {"id": "r8_cost_rules", "version": "r8-p4-v1"},
    "fill_model": {"id": "r8_next_open_fill", "version": "r8-p4-v1"},
    "engine": {"id": "lean", "version": IMAGE_DIGEST},
    "dependencies": {"lean_image_digest": IMAGE_DIGEST},
    "time_semantics": {"known_at": "bar_end", "fill_at": "next_bar_open",
                       "simulated_latency_ms": 0},
}


def decimal(value):
    """只接受原始十進位字串或 Decimal，拒絕二進位浮點。"""
    if not isinstance(value, (str, Decimal)):
        raise ValueError("須為十進位字串")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("無效十進位數值") from exc
    if not result.is_finite():
        raise ValueError("須為有限數值")
    return result


def number(value):
    return format(decimal(value).normalize(), "f")


def target_quantity(weight, equity, price, qty_step):
    equity, price, step = map(decimal, (equity, price, qty_step))
    if min(equity, price, step) <= 0:
        raise ValueError("權益、價格與數量步長須為正")
    quantity = decimal(weight) * equity / price
    return (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step


def fill_price(open_price, quantity, bps):
    price, qty, slip = map(decimal, (open_price, quantity, bps))
    if price <= 0 or not 0 <= slip < 10000 or qty == 0:
        raise ValueError("成交價格、數量或滑價不合法")
    return price * (1 + (1 if qty > 0 else -1) * slip / 10000)


def fee(quantity, price, rate):
    qty, price, rate = map(decimal, (quantity, price, rate))
    if price <= 0 or rate < 0:
        raise ValueError("手續費輸入不合法")
    return abs(qty) * price * rate


def funding_amount(q_before, q_after, price, rate, delta, estimated=False):
    before, after, price, rate, delta = map(
        decimal, (q_before, q_after, price, rate, delta))
    if price <= 0 or not 0 <= delta <= 1 or estimated and rate < 0:
        raise ValueError("資金費輸入不合法")
    if estimated:
        return -max(abs(before), abs(after)) * price * rate * (1 + delta)
    amount = min(-before * price * rate, -after * price * rate)
    if amount == 0:
        return Decimal(0)
    return amount * (1 + delta if amount < 0 else 1 - delta)


def delisting_price(quantity, last, previous, penalty_bps, multiplier):
    qty = decimal(quantity)
    bars = [last] + ([previous] if previous is not None else [])
    extreme = min(decimal(b["low"]) for b in bars) if qty > 0 else max(
        decimal(b["high"]) for b in bars)
    return fill_price(extreme, -qty, decimal(penalty_bps) * decimal(multiplier))


def order_segments(current, target, decision_price, qty_step, min_qty,
                   min_notional, liquidity_reason, tier_bps, hour_turnover, cost):
    """反手先減至零，再增加；每段分別判最小值與單筆上限。"""
    current, target, price, step = map(decimal, (current, target, decision_price, qty_step))
    if price <= 0 or step <= 0:
        raise ValueError("決策價或步長不合法")
    target = (target / step).to_integral_value(rounding=ROUND_DOWN) * step
    quantities = [-current, target] if current * target < 0 else [target - current]
    position, result = current, []
    for quantity in quantities:
        if quantity == 0:
            continue
        reducing = position * quantity < 0 and abs(quantity) <= abs(position)
        flatten = reducing and quantity == -position
        reason = None
        if not flatten:
            if abs(quantity) < decimal(min_qty):
                reason = "min_qty"
            elif abs(quantity) * price < decimal(min_notional):
                reason = "min_notional"
        cap = max(Decimal(0), decimal(hour_turnover)) * decimal(cost["order_cap_fraction"])
        liquidity_block = liquidity_reason or ("order_cap" if abs(quantity) * price > cap else None)
        if not reducing:
            reason = reason or liquidity_block
        penalty = reducing and bool(liquidity_block)
        bps = decimal(cost["forced_reduce_penalty_bps"] if penalty else tier_bps)
        bps *= decimal(cost["slippage_multiplier"])
        result.append({"quantity": number(quantity), "reason": reason,
                       "slippage_bps": number(bps),
                       "kind": "forced_reduce_penalty" if penalty else "normal"})
        if reason is None:
            position += quantity
    return result


def effective_target(current, segments):
    return decimal(current) + sum((decimal(s["quantity"]) for s in segments
                                   if s["reason"] is None), Decimal(0))


def milliseconds(value):
    """摺表保留 ISO 8601，運算統一成 UTC 毫秒。"""
    if type(value) is int:
        return value
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("無效時間")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = value.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * DAY + delta.seconds * 1000 + delta.microseconds // 1000


def next_open(decision_t, bar_start, bar_end):
    """只在下一根送達時成交；缺漏自然延到第一根存在的開盤。"""
    decision, start, end = map(milliseconds, (decision_t, bar_start, bar_end))
    return start if start >= decision and end > decision else None


def decision_due(resolution, t):
    if resolution not in ("hour", "day"):
        raise ValueError("無效決策頻率")
    return milliseconds(t) % (DAY if resolution == "day" else HOUR) == 0


def exposure(positions, prices, equity, cap=None):
    eq = decimal(equity)
    if eq <= 0:
        raise ValueError("gross_exposure_cap: 非正權益")
    value = sum((abs(decimal(q) * decimal(prices[s])) for s, q in positions.items()
                 if decimal(q) != 0), Decimal(0)) / eq
    if cap is not None and value > decimal(cap):
        raise ValueError("gross_exposure_cap")
    return value


def liquidity(t, first_bar, daily_turnover, cost):
    days = cost["liquidity_window_days"]
    if type(days) is not int or days <= 0:
        raise ValueError("流動性日數須為正整數")
    end = milliseconds(t) // DAY * DAY
    tiers = cost["slippage_tiers_bps"]
    fallback = decimal(tiers[-1]["bps"])
    # 上市當日不完整時不計為完整日。
    if first_bar is None or end - ((milliseconds(first_bar) + DAY - 1) // DAY * DAY) < days * DAY:
        return "insufficient_history", fallback
    values = {milliseconds(r["t"]): decimal(r["value"]) for r in daily_turnover
              if milliseconds(r["known_at"]) <= milliseconds(t)}
    mid = median([values.get(end - i * DAY, Decimal(0)) for i in range(1, days + 1)])
    if mid < decimal(cost["untradeable_below_turnover"]):
        return "untradeable", fallback
    for tier in tiers:
        if mid >= decimal(tier["min_turnover"]):
            return None, decimal(tier["bps"])
    return "untradeable", fallback


def score_end_price(quantity, close, cost):
    return fill_price(close, -decimal(quantity),
                      decimal(cost["forced_reduce_penalty_bps"]) * decimal(cost["slippage_multiplier"]))


def positions_at(fills, symbol, t):
    before = sum((decimal(f["quantity"]) for f in fills
                  if f["symbol"] == symbol and f["change_t"] < t), Decimal(0))
    after = before + sum((decimal(f["quantity"]) for f in fills
                          if f["symbol"] == symbol and f["change_t"] == t), Decimal(0))
    return before, after


def funding_price(bars, t):
    available = [b for b in bars if milliseconds(b["end"]) <= t]
    if not available:
        raise ValueError("資金費缺少可知計價")
    last = max(available, key=lambda b: milliseconds(b["end"]))
    return decimal(last["close"]), milliseconds(last["end"]) != t


def funding_schedule(records, start, end, interval_ms, minimum_rate, delivery=None):
    """只由可讀紀錄重建空白；邊界含入，結算後再由成交重建部位。"""
    start, end = milliseconds(start), milliseconds(end)
    if type(interval_ms) is not int or interval_ms <= 0 or start > end:
        raise ValueError("資金費區間不合法")
    minimum = decimal(minimum_rate)
    if minimum < 0:
        raise ValueError("估計費率不可負")
    rows = sorted(({"t": milliseconds(r["t"]), "rate": number(r["rate"]),
                    "estimated": False} for r in records if start <= milliseconds(r["t"]) <= end),
                  key=lambda r: r["t"])
    times = [r["t"] for r in rows]
    if len(set(times)) != len(times):
        raise ValueError("重複資金費時刻")
    result = {r["t"]: r for r in rows}

    def estimate(t, rate):
        if start <= t <= end and t not in result:
            result[t] = {"t": t, "rate": number(max(minimum, abs(decimal(rate)))),
                         "estimated": True}

    intervals = [b - a for a, b in zip(times, times[1:])]
    for i, gap in enumerate(intervals):
        neighbors = intervals[max(0, i - 1):i] + intervals[i + 1:i + 2]
        if not neighbors:
            continue
        delta = min(neighbors)
        if gap > delta:
            count = max(1, int((Decimal(gap) / delta).to_integral_value(rounding=ROUND_HALF_UP)) - 1)
            rate = max(abs(decimal(rows[i]["rate"])), abs(decimal(rows[i + 1]["rate"])))
            for k in range(1, count + 1):
                estimate(times[i] + k * delta, rate)
    if rows:
        left = intervals[0] if intervals else interval_ms
        right = intervals[-1] if intervals else interval_ms
        for t in range(times[0] - left, start - 1, -left):
            estimate(t, rows[0]["rate"])
        for t in range(times[-1] + right, end + 1, right):
            estimate(t, rows[-1]["rate"])
    else:
        for t in range((start + interval_ms - 1) // interval_ms * interval_ms, end + 1, interval_ms):
            estimate(t, minimum)
    return [result[t] for t in sorted(result) if delivery is None or t <= milliseconds(delivery)]


def merge_windows(windows):
    result = []
    for window in windows:
        start, end = milliseconds(window["start"]), milliseconds(window["end"])
        if start >= end or result and start < result[-1]["end"]:
            raise ValueError("計分窗重疊或順序不合法")
        if result and start == result[-1]["end"]:
            result[-1]["end"] = end
        else:
            result.append({"start": start, "end": end})
    return result


def select_grid_point(scores, grid, neighborhood):
    """鄰域以預登記的數值軸序號與類別軸取值計算。"""
    if not 1 <= len(grid) <= 20 or len(scores) != len(grid):
        raise ValueError("網格或成績數目不合法")
    values = [decimal(s) for s in scores]
    numeric, categorical = neighborhood["numeric"], neighborhood["categorical"]
    for axis, options in numeric.items():
        numbers = [decimal(str(x)) for x in options]
        if numbers != sorted(set(numbers)):
            raise ValueError("數值軸須遞增且無重複")
    for axis, options in {**numeric, **categorical}.items():
        if not options or any(point[axis] not in options for point in grid):
            raise ValueError("網格未落在預登記軸")
    means, qualified = [], []
    for i, point in enumerate(grid):
        neighbors = [j for j, other in enumerate(grid)
                     if all(abs(options.index(point[axis]) - options.index(other[axis])) <= 1
                            for axis, options in numeric.items())
                     and all(point[axis] == other[axis] for axis in categorical)]
        means.append(sum((values[j] for j in neighbors), Decimal(0)) / len(neighbors))
        qualified.append(values[i] > 0 and sum(values[j] > 0 for j in neighbors) * 2 > len(neighbors))
    candidates = [i for i in range(len(grid)) if qualified[i]]
    selected = max(candidates, key=lambda i: (means[i], -i)) if candidates else None
    if selected is not None and means[selected] <= 0:
        selected = None
    return {"grid_scores": [number(s) for s in values],
            "neighborhood_means": [number(m) for m in means],
            "qualified": qualified, "selected": selected,
            "selected_minus_neighborhood": None if selected is None else number(values[selected] - means[selected]),
            "no_trade": selected is None}


def freeze(value):
    """遞迴複製後給唯讀視圖，不把完整資料或原始可變容器傳給假說。"""
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


def data_view(data, cutoff, strict=False, symbols=None):
    cutoff = milliseconds(cutoff)
    visible = {}
    for symbol in (list(data) if symbols is None else symbols):
        datasets = {}
        for name, rows in data.get(symbol, {}).items():
            selected = [r for r in rows if (milliseconds(r["known_at"]) < cutoff
                                            if strict else milliseconds(r["known_at"]) <= cutoff)]
            if selected:
                datasets[name] = selected
        if datasets:
            visible[symbol] = datasets
    return freeze(visible)


class R8Hypothesis:
    """假說只取得種子、唯讀資料、模型與參數。"""

    def __init__(self, random_seed):
        if type(random_seed) is not int:
            raise ValueError("random_seed 須為整數")
        self._random_seed = random_seed

    @property
    def random_seed(self):
        return self._random_seed

    def score(self, params, train_window, validation_window, data, cost):
        raise NotImplementedError

    def fit(self, fit_window, data, params):
        raise NotImplementedError

    def on_decision(self, time, data, model, params):
        raise NotImplementedError


def serialize_model(artifact):
    if not isinstance(artifact, dict) or set(artifact) != {"params", "model"}:
        raise ValueError("模型須含 params 與 model")
    raw = canonical(artifact)
    return raw, hashlib.sha256(raw).hexdigest()


def deserialize_model(raw, expected_sha256):
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("模型雜湊不符")
    value = json.loads(raw)
    if serialize_model(value)[0] != raw:
        raise ValueError("模型非標準化 JSON")
    return value


def fit_fold(hypothesis_class, seed, fit_window, data, strategy, cost):
    start, end = milliseconds(fit_window["start"]), milliseconds(fit_window["end"])
    validation_days = strategy["internal_validation_days"]
    gap_days = strategy["internal_gap_days"]
    if type(validation_days) is not int or type(gap_days) is not int or min(validation_days, gap_days) <= 0:
        raise ValueError("內部窗長須為正整數")
    validation_start = end - validation_days * DAY
    train_end = validation_start - gap_days * DAY
    if start >= train_end:
        raise ValueError("內部訓練窗為空")
    instance = hypothesis_class(seed)
    view = data_view(data, end, strict=True)
    grid = strategy["grid"]
    scores = [instance.score(freeze(params), freeze({"start": start, "end": train_end}),
                             freeze({"start": validation_start, "end": end}), view, freeze(cost))
              for params in grid]
    selection = select_grid_point(scores, grid, strategy["neighborhood"])
    if selection["no_trade"]:
        return {"selection": selection, "artifact": None}
    params = grid[selection["selected"]]
    model = instance.fit(freeze(fit_window), view, freeze(params))
    artifact = {"params": params, "model": model}
    serialize_model(artifact)
    return {"selection": selection, "artifact": artifact}


def decide(instance, t, data, artifact, symbols=None):
    return instance.on_decision(t, data_view(data, t, symbols=symbols),
                                freeze(artifact["model"]), freeze(artifact["params"]))


def apply_fill(position, average, quantity, price):
    """期貨不扣開倉名目；以已實現損益驗證現金恆等式。"""
    position, average, quantity, price = map(decimal, (position, average, quantity, price))
    if price <= 0 or quantity == 0:
        raise ValueError("成交輸入不合法")
    new = position + quantity
    if position == 0 or position * quantity > 0:
        new_average = (abs(position) * average + abs(quantity) * price) / abs(new)
        return new, new_average, Decimal(0)
    realized = min(abs(position), abs(quantity)) * (price - average) * (1 if position > 0 else -1)
    new_average = Decimal(0) if new == 0 else price if new * position < 0 else average
    return new, new_average, realized
