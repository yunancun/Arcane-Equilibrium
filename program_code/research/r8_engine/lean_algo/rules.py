"""增補指令 §3、§9 的確定性規則；不存取資料檔或 LEAN。"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from statistics import median
from collections.abc import Mapping, Sequence
from bisect import bisect_left, bisect_right
from types import MappingProxyType

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


def next_open(decision_t, bar_start, bar_end, score_end=None):
    """只在下一根送達時成交；缺漏自然延到第一根存在的開盤。"""
    decision, start, end = map(milliseconds, (decision_t, bar_start, bar_end))
    return start if (start >= decision and end > decision
                     and (score_end is None or start < milliseconds(score_end))) else None


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
    indexed = daily_turnover if isinstance(daily_turnover, KnownRows) else KnownRows(daily_turnover)
    recent = indexed.between(end - (days - 1) * DAY, end)
    values = {milliseconds(r["t"]): decimal(r["value"]) for r in recent
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
    index = bisect_right(bars, t, key=lambda b: milliseconds(b["end"]))
    if index == 0:
        raise ValueError("資金費缺少可知計價")
    last = bars[index - 1]
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


def validate_grid(grid, neighborhood):
    """執行前與折內選擇共用同一份預登記軸檢查。"""
    if not isinstance(grid, list) or not 1 <= len(grid) <= 20:
        raise ValueError("網格數目不合法")
    if not isinstance(neighborhood, dict) or set(neighborhood) != {"numeric", "categorical"}:
        raise ValueError("鄰域須含且只含 numeric、categorical")
    numeric, categorical = neighborhood["numeric"], neighborhood["categorical"]
    if (not isinstance(numeric, dict) or not isinstance(categorical, list)
            or any(not isinstance(axis, str) for axis in [*numeric, *categorical])):
        raise ValueError("鄰域軸定義不合法")
    if len(set(categorical)) != len(categorical) or set(numeric).intersection(categorical):
        raise ValueError("鄰域軸名重複或重疊")
    axes = set(numeric) | set(categorical)
    if any(not isinstance(point, dict) or set(point) != axes for point in grid):
        raise ValueError("網格須恰含全部已宣告的軸")
    for axis, options in numeric.items():
        if not isinstance(options, list) or not options:
            raise ValueError("數值軸須為非空清單")
        numbers = [decimal(str(x)) for x in options]
        if any(a >= b for a, b in zip(numbers, numbers[1:])):
            raise ValueError("數值軸須遞增且無重複")
        for point in grid:
            value = point[axis]
            # bool 與 0/1 相等，須在清單成員比較之前拒絕。
            if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
                raise ValueError("數值軸的網格值須為數值")
            decimal(str(value))
            if value not in options:
                raise ValueError("網格未落在預登記軸")
    return numeric, categorical


def select_grid_point(scores, grid, neighborhood):
    """鄰域以預登記的數值軸序號與類別軸取值計算。"""
    numeric, categorical = validate_grid(grid, neighborhood)
    if len(scores) != len(grid):
        raise ValueError("網格或成績數目不合法")
    values = [decimal(s) for s in scores]
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


class RowSlice(Sequence):
    """固定可見範圍的唯讀切片；切片和取前綴都不複製資料列。"""

    def __init__(self, rows, indices):
        self._rows, self._indices = rows, indices

    def __len__(self):
        return len(self._indices)

    def __getitem__(self, index):
        selected = self._indices[index]
        return RowSlice(self._rows, selected) if isinstance(index, slice) else self._rows[selected]


class KnownRows:
    """靜態資料只排序與凍結一次；小時線依到達順序追加。"""

    def __init__(self, rows=()):
        ordered = sorted(rows, key=lambda r: milliseconds(r["known_at"]))
        self._times = [milliseconds(r["known_at"]) for r in ordered]
        self._rows = [freeze(r) for r in ordered]

    def append(self, row):
        t = milliseconds(row["known_at"])
        if self._times and t < self._times[-1]:
            raise ValueError("資料追加時刻倒退")
        self._times.append(t)
        self._rows.append(freeze(row))

    def prefix(self, cutoff, strict=False):
        end = (bisect_left if strict else bisect_right)(self._times, milliseconds(cutoff))
        return RowSlice(self._rows, range(end))

    def between(self, start, end):
        return RowSlice(self._rows, range(bisect_left(self._times, milliseconds(start)),
                                         bisect_right(self._times, milliseconds(end))))


def index_data(data):
    return {s: {name: rows if isinstance(rows, KnownRows) else KnownRows(rows)
                for name, rows in datasets.items()} for s, datasets in data.items()}


def data_view(data, cutoff, strict=False, symbols=None, *, family=None):
    cutoff = milliseconds(cutoff)
    if family not in (None, "ordinary", "listing"):
        raise ValueError("HYPOTHESIS_BINDING_INVALID")
    visible = {}
    for symbol in (list(data) if symbols is None else symbols):
        datasets = {}
        source = data.get(symbol, {})
        regimes = source.get("listing_regime", ())
        regimes = regimes if isinstance(regimes, KnownRows) else KnownRows(regimes)
        known = regimes.prefix(cutoff, strict)
        current_day = (cutoff - (1 if strict else 0)) // DAY * DAY
        if family is not None and known and known[-1]["day_start"] != current_day:
            raise ValueError("LISTING_CURRENT_DAY_MISSING")
        ordinary = next((r for r in known if r["stage"] == "ordinary"), None) if family == "ordinary" else None
        for name, rows in source.items():
            if family is not None and name not in {
                    "kline_hour", "kline_day", "turnover_hour", "turnover_day",
                    "funding", "open_interest", "listing_regime"}:
                continue
            indexed = rows if isinstance(rows, KnownRows) else KnownRows(rows)
            selected = indexed.prefix(cutoff, strict)
            if family is not None and name == "listing_regime":
                selected = tuple(freeze({k: row[k] for k in
                    ("known_at", "day_start", "stage", "reason_code", "cooling")}) for row in known)
            elif family == "ordinary" and name in {
                    "kline_hour", "kline_day", "turnover_hour", "turnover_day"}:
                # Use the bar's own UTC day, never the new phase learned at its close.
                selected = tuple(row for row in selected if ordinary is not None
                    and ordinary["day_start"] <= row["t"] and ordinary["known_at"] <= row["known_at"])
            if selected:
                datasets[name] = selected
        if datasets or family is not None:
            visible[symbol] = MappingProxyType(datasets)
    return MappingProxyType(visible)


class PositionHistory:
    """每個標的按變動時刻保存累計部位，結算查詢不掃描成交史。"""

    def __init__(self):
        self._times, self._totals = {}, {}

    def append(self, fill):
        symbol, t, qty = fill["symbol"], fill["change_t"], decimal(fill["quantity"])
        times, totals = self._times.setdefault(symbol, []), self._totals.setdefault(symbol, [])
        index = bisect_right(times, t)
        times.insert(index, t)
        totals.insert(index, (totals[index - 1] if index else Decimal(0)) + qty)
        # 延後記帳的結算可能回填歷史；正常依序成交只有常數追加成本。
        for i in range(index + 1, len(totals)):
            totals[i] += qty

    def at(self, symbol, t):
        times, totals = self._times.get(symbol, []), self._totals.get(symbol, [])
        before, after = bisect_left(times, t), bisect_right(times, t)
        return (totals[before - 1] if before else Decimal(0),
                totals[after - 1] if after else Decimal(0))


def turnover_at(rows, t):
    indexed = rows if isinstance(rows, KnownRows) else KnownRows(rows)
    selected = indexed.between(t, t)
    return selected[-1]["value"] if selected else "0"


class HypothesisError(RuntimeError):
    """假說回呼本身的例外；不與 LEAN 邊界或輸出格式混淆。"""


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


def fit_fold(hypothesis_class, seed, fit_window, data, strategy, cost, *, family=None):
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
    view = data_view(data, end, strict=True, family=family)
    grid = strategy["grid"]
    try:
        scores = [instance.score(freeze(params), freeze({"start": start, "end": train_end}),
                                 freeze({"start": validation_start, "end": end}), view, freeze(cost))
                  for params in grid]
    except Exception as exc:
        raise HypothesisError("假說 score 執行失敗") from exc
    if any(not isinstance(score, str) for score in scores):
        raise ValueError("invalid_decision: score 須為十進位字串")
    try:
        for score in scores:
            decimal(score)
    except ValueError as exc:
        raise ValueError("invalid_decision: score 須為有限十進位字串") from exc
    selection = select_grid_point(scores, grid, strategy["neighborhood"])
    if selection["no_trade"]:
        return {"selection": selection, "artifact": None}
    params = grid[selection["selected"]]
    try:
        model = instance.fit(freeze(fit_window), view, freeze(params))
    except Exception as exc:
        raise HypothesisError("假說 fit 執行失敗") from exc
    artifact = {"params": params, "model": model}
    return {"selection": selection, "artifact": artifact}


def decide(instance, t, data, artifact, symbols=None, *, family=None):
    view = data_view(data, t, symbols=symbols, family=family)
    try:
        return instance.on_decision(t, view, freeze(artifact["model"]), freeze(artifact["params"]))
    except Exception as exc:
        raise HypothesisError("假說 on_decision 執行失敗") from exc


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


def decision_symbols(info, t, bar_ends):
    """小時與日線決策都只交出當步完整小時線已送達的標的。"""
    return [s for s in info["strategy_symbols"]
            if info["first_bar"].get(s) is not None
            and info["first_bar"][s] + HOUR <= t and bar_ends.get(s) == t
            and (info["delistings"].get(s, {}).get("deliveryTime") is None
                 or t < info["delistings"][s]["deliveryTime"])]


def decision_record(t, targets, kind):
    """decisions 只保存假說輸出；框架的折界平倉另記 orders。"""
    return {"t": t, "targets": targets} if kind == "strategy" else None


def replacement_order(counter, segments):
    """零差額只取消原單，不消耗訂單編號。"""
    return (counter + 1, counter + 1) if segments else (counter, None)


def cancellation_record(leg, t, reason, replaced_by=None):
    record = {k: leg[k] for k in ("order_id", "decision_t", "symbol", "quantity", "_leg_index")}
    record.update(kind=leg["order_kind"], status="cancelled", cancel_t=t, cancel_reason=reason)
    if reason == "replaced":
        record["replaced_by"] = replaced_by
    return record


def lean_decimal(value, invariant_culture):
    """只接受 System.Decimal 的精確格式；自動轉成 float 時拒絕猜測。"""
    if not hasattr(value, "GetType") or value.GetType().FullName != "System.Decimal":
        raise ValueError("NEEDS_CONTEXT: LEAN 邊界未提供 System.Decimal")
    return decimal(value.ToString("G29", invariant_culture))


def account_equity(cash, positions, averages, prices):
    """框架十進位現金加期貨未實現損益；零部位不需要價格。"""
    return decimal(cash) + sum((decimal(q) * (decimal(prices[s]) - decimal(averages[s]))
                                for s, q in positions.items() if decimal(q) != 0), Decimal(0))


def settlement_bars(bars, end):
    """終點只使用不晚於界線的價格，含下架時的最後不完整線。"""
    index = bisect_right(bars, end, key=lambda b: b["end"])
    if index == 0:
        raise ValueError("平倉缺價格")
    last = bars[index - 1]
    previous = next((bars[i] for i in range(index - 2, -1, -1)
                     if bars[i]["end"] - bars[i]["t"] == HOUR), None)
    return last, previous


def due_boundaries(windows, delistings, t, closed, delivered):
    events = [(w["end"], "score_end", None) for w in windows
              if w["end"] <= t and w["end"] not in closed]
    events += [(value["deliveryTime"], "delivery", symbol) for symbol, value in delistings.items()
               if value["deliveryTime"] <= t and symbol not in delivered]
    return sorted(events, key=lambda event: (event[0], event[1], event[2] or ""))


def turnover_liquidity(row, t, first_bar, cost):
    """DV5 independent §6.2 consumer; no U6 imports and no hypothesis access."""
    from fractions import Fraction
    keys = set('schema_version symbol decision_utc_day known_at policy_sha256 history_sufficient inputs m_d m_e m_h tier_d tier_e tier_h triggered selected_source selected_median selected_tier status reason_codes'.split())
    input_keys = set('day_start exchange_reported effective_reported sum_hourly_reported daily_status hourly_status source_refs'.split())
    def reject():
        raise ValueError('TURNOVER_DECISION_INVALID')
    def amount(value):
        if not isinstance(value, str):
            reject()
        try:
            parsed = decimal(value)
            if parsed < 0:
                reject()
            return Fraction(parsed)
        except (ValueError, ArithmeticError):
            reject()
    def tier(value):
        return next((name for threshold, name in (
            (100000000, 'GE_100M'), (10000000, 'GE_10M'), (1000000, 'GE_1M'))
            if value >= threshold), 'NO_OPEN')
    if not isinstance(row, dict) or set(row) != keys:
        reject()
    day = milliseconds(t) // DAY * DAY
    sufficient = first_bar is not None and day - ((milliseconds(first_bar)+DAY-1)//DAY*DAY) >= 12*DAY
    if (row['schema_version'] != 'r8_turnover_decision_v1'
            or type(row['decision_utc_day']) is not int or row['decision_utc_day'] != day
            or type(row['known_at']) is not int or row['known_at'] != day
            or type(row['history_sufficient']) is not bool or row['history_sufficient'] != sufficient
            or type(row['triggered']) is not bool
            or not isinstance(row['inputs'], list) or len(row['inputs']) != 12
            or row['status'] not in ('READY', 'BLOCKED')
            or not isinstance(row['reason_codes'], list)
            or any(not isinstance(r, str) or not r for r in row['reason_codes'])
            or row['reason_codes'] != sorted(set(row['reason_codes']))):
        reject()
    values = {key: [] for key in ('exchange_reported', 'effective_reported', 'sum_hourly_reported')}
    for i, source in enumerate(row['inputs']):
        if (not isinstance(source, dict) or set(source) != input_keys
                or type(source['day_start']) is not int or source['day_start'] != day-(12-i)*DAY
                or not isinstance(source['source_refs'], list)):
            reject()
        for key, status in (('exchange_reported','daily_status'), ('effective_reported','daily_status'),
                            ('sum_hourly_reported','hourly_status')):
            state, value = source[status], source[key]
            if state not in ('VALID','MISSING','INVALID','NOT_EVALUATED'):
                reject()
            if key == 'sum_hourly_reported' and state == 'NOT_EVALUATED' and not row['triggered']:
                if value is not None:
                    reject()
                continue
            if state == 'NOT_EVALUATED' or (key != 'exchange_reported' and state == 'VALID' and value is None):
                reject()
            # Original amount can survive isolation of the effective row.
            if key == 'effective_reported' and state != 'VALID' and value is not None:
                reject()
            if key == 'sum_hourly_reported' and state != 'VALID' and value is not None:
                reject()
            values[key].append(Fraction(0) if value is None else amount(value))
    md, me = (median(values[k]) for k in ('exchange_reported','effective_reported'))
    trigger = any(abs(me-threshold)*20 <= threshold for threshold in (1000000,10000000,100000000))
    mh = median(values['sum_hourly_reported']) if len(values['sum_hourly_reported']) == 12 else None
    if row['triggered'] != trigger:
        reject()
    for suffix, value in (('d',md),('e',me),('h',mh)):
        if value is None:
            if row['m_'+suffix] is not None or row['tier_'+suffix] is not None:
                reject()
        elif amount(row['m_'+suffix]) != value or row['tier_'+suffix] != tier(value):
            reject()
    selected = mh if trigger and tier(mh) != tier(me) else me
    selected_source = 'hourly_sum' if trigger and tier(mh) != tier(me) else 'effective_daily'
    if row['status'] == 'BLOCKED':
        if not row['reason_codes'] or any(row[k] is not None for k in ('selected_source','selected_median','selected_tier')):
            reject()
        raise ValueError('TURNOVER_DECISION_BLOCKED')
    selected_tier = tier(selected) if sufficient else 'NO_OPEN'
    if (row['selected_source'] != selected_source or amount(row['selected_median']) != selected
            or row['selected_tier'] != selected_tier):
        reject()
    reason = 'insufficient_history' if not sufficient else ('untradeable' if selected_tier == 'NO_OPEN' else None)
    bps = {'GE_100M':'5','GE_10M':'10','GE_1M':'20','NO_OPEN':'20'}[selected_tier]
    return reason, decimal(bps)
