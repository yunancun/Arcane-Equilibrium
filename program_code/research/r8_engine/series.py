"""U6 的獨立 Decimal 重算；不匯入 U4 物化或 U5 成交規則。"""

from decimal import Decimal, InvalidOperation, ROUND_DOWN, localcontext


class SeriesError(ValueError):
    """輸入或重算證據不符合研究契約。"""


def decimal_value(value):
    """只接收原始十進位字串或已解析的 Decimal，避免浮點數污染。"""
    if not isinstance(value, (str, Decimal)):
        raise SeriesError("數值必須是十進位字串")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise SeriesError("無效十進位數值") from exc
    if not result.is_finite():
        raise SeriesError("數值必須有限")
    return result


def decimal_text(value):
    """依 §3.9 輸出一般小數，零統一為 0。"""
    value = decimal_value(value)
    with localcontext() as ctx:
        ctx.prec = max(28, len(value.as_tuple().digits))
        return "0" if not value else format(value.normalize(), "f")


def target_quantity(equity, weight, decision_price, qty_step):
    """目標權重按決策收盤價換算，數量向零取整。"""
    equity, weight, price, step = map(
        decimal_value, (equity, weight, decision_price, qty_step)
    )
    if equity <= 0 or price <= 0 or step <= 0:
        raise SeriesError("權益、價格及數量步長必須為正")
    with localcontext() as ctx:
        ctx.prec = 50
        return (equity * weight / price / step).to_integral_value(
            rounding=ROUND_DOWN
        ) * step


def fill_cost(quantity, reference_price, slippage_bps, fee_rate):
    """滑價作用於價格，手續費作用於含滑價的成交名目。"""
    quantity, price, bps, rate = map(
        decimal_value, (quantity, reference_price, slippage_bps, fee_rate)
    )
    if not quantity or price <= 0 or not 0 <= bps < 10000 or rate < 0:
        raise SeriesError("成交數量、價格、滑價或費率不合法")
    with localcontext() as ctx:
        ctx.prec = 50
        fill_price = price * (1 + (bps if quantity > 0 else -bps) / 10000)
        return fill_price, abs(quantity) * fill_price * rate


def funding_amount(q_before, q_after, price, rate, delta, *, estimated=False):
    """結算點前後取較不利現金流；估計的資金費一律為支付。"""
    before, after, price, rate, delta = map(
        decimal_value, (q_before, q_after, price, rate, delta)
    )
    if price <= 0 or not 0 <= delta <= 1 or (estimated and rate < 0):
        raise SeriesError("資金費價格、調整或估計費率不合法")
    with localcontext() as ctx:
        ctx.prec = 50
        if estimated:
            return -max(abs(before), abs(after)) * price * rate * (1 + delta)
        amount = min(-before * price * rate, -after * price * rate)
        return amount * (1 + delta if amount < 0 else 1 - delta)


def delisting_cost(position, last_bar, previous_complete_bar, penalty_bps, fee_rate):
    """下架時以最後兩根的不利極值平倉，部分 K 線仍可用於結算。"""
    quantity = decimal_value(position)
    if quantity > 0:
        price = min(decimal_value(last_bar["low"]),
                    decimal_value(previous_complete_bar["low"]))
    else:
        price = max(decimal_value(last_bar["high"]),
                    decimal_value(previous_complete_bar["high"]))
    return fill_cost(-quantity, price, penalty_bps, fee_rate)


def order_segments(position, target, decision_price, min_qty, min_notional,
                   daily_turnover, hourly_turnover, history_sufficient, cost):
    """按單一標的拆反手；減曝險段與增曝險段分別檢查。"""
    position, target, price, minimum, notional, daily, hourly = map(
        decimal_value, (position, target, decision_price, min_qty,
                        min_notional, daily_turnover, hourly_turnover)
    )
    if price <= 0 or min(minimum, notional, daily, hourly) < 0:
        raise SeriesError("訂單價格、最小門檻或成交額不合法")
    with localcontext() as ctx:
        ctx.prec = 50
        multiplier = decimal_value(cost["slippage_multiplier"])
        penalty = decimal_value(cost["forced_reduce_penalty_bps"]) * multiplier
        threshold = decimal_value(cost["untradeable_below_turnover"])
        cap = hourly * decimal_value(cost["order_cap_fraction"])
        tiers = [
            (decimal_value(t["min_turnover"]), decimal_value(t["bps"]))
            for t in cost["slippage_tiers_bps"]
        ]
        if (multiplier < 0 or threshold < 0 or cap < 0 or
                not tiers or tiers != sorted(tiers, reverse=True) or
                any(level < 0 or bps < 0 for level, bps in tiers)):
            raise SeriesError("流動性與滑價設定不合法")
        bps = next((bps * multiplier for level, bps in tiers if daily >= level), None)
        pieces = [-position, target] if position * target < 0 else [target - position]
        result = []
        current = position
        for change in pieces:
            if not change:
                continue
            closing = bool(current) and change == -current
            reducing = bool(current) and current * change < 0 and abs(change) <= abs(current)
            reason = None
            if not closing and abs(change) < minimum:
                reason = "min_qty"
            elif not closing and abs(change) * price < notional:
                reason = "min_notional"
            liquidity_reason = (
                "insufficient_history" if not history_sufficient else
                "untradeable" if daily < threshold or bps is None else
                "order_cap" if abs(change) * price > cap else None
            )
            if reason is None and not reducing:
                reason = liquidity_reason
            if reason:
                result.append({"quantity": decimal_text(change), "reason": reason})
            else:
                result.append({
                    "quantity": decimal_text(change),
                    "slippage_bps": decimal_text(penalty if liquidity_reason else bps),
                    "kind": "forced_reduce_penalty" if liquidity_reason else "normal",
                })
                current += change
        return result
