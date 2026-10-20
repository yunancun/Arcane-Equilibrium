"""固定的 LEAN 轉接類別；只在容器內載入，P4-D0/P4-D 驗收。"""
from AlgorithmImports import *
import csv
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, "/r8/src")
from program_code.research.r8_engine.lean_algo import rules
from program_code.research.r8_engine.lean_algo.rules import R8Hypothesis
from program_code.research.r8_engine.lean_runner import serialize_model, deserialize_model
from program_code.research.r8_ledger.ledger import canonical


def d(value):
    return rules.decimal(str(value))


class R8FillModel(FillModel):
    """每個原生 leg 對應一個邏輯複合訂單的片段。"""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def market_fill(self, asset, order):
        event = OrderEvent(order, self.owner.utc_time, OrderFee(CashAmount(0, "USDT")))
        metadata = self.owner._legs.get(order.tag)
        if metadata is None:
            self.owner._fail("lean_error")
            return event
        bar = asset.get_last_data()
        if bar is None or not isinstance(bar, TradeBar):
            return event
        if bar.is_fill_forward:
            self.owner._emit("fill_forward_bars", {"t": rules.milliseconds(bar.end_time),
                                                  "symbol": metadata["symbol"]})
            self.owner._fail("fill_forward_bar")
            return event
        change_t = rules.next_open(order.time, bar.time, bar.end_time)
        delivery = self.owner._info["delistings"].get(metadata["symbol"], {}).get("deliveryTime")
        if change_t is None or delivery is not None and change_t >= delivery:
            return event
        price = rules.fill_price(d(bar.open), metadata["quantity"], metadata["slippage_bps"])
        fee = rules.fee(metadata["quantity"], price, self.owner._config["cost"]["taker_fee_rate"])
        metadata["change_t"] = change_t
        event.fill_price = float(price)
        event.fill_quantity = float(d(metadata["quantity"]))
        event.order_fee = OrderFee(CashAmount(float(fee), "USDT"))
        event.status = OrderStatus.FILLED
        return event


class R8Algorithm(QCAlgorithm):
    """LEAN 物件不傳給假說；策略只回傳目標，所有下單由框架處理。"""

    def initialize(self):
        self._output = Path("/r8/output")
        self._events = (self._output / "events.jsonl").open("ab", buffering=0)
        self._failure = None
        self._t = None
        self._config = json.loads(Path("/r8/algorithm_config.json").read_bytes())
        self._info = json.loads(Path("/r8/framework.json").read_bytes())
        self._legs, self._pending, self._fills = {}, {}, []
        self._symbols, self._data, self._bars = {}, {}, {}
        self._counter = 0
        self._closed, self._delivered, self._funded = set(), set(), set()
        self._fitted, self._active_fold, self._instance, self._artifact = {}, None, None, None
        self._last_decision_prices, self._last_decision_equity = {}, None
        self._account_positions, self._average = {}, {}
        self._expected_cash = d(self._config["initial_cash"])
        self._windows = rules.merge_windows(self._config["score_windows"])
        if not self._windows and self._info["validation_example"]:
            self._windows = [self._info["window"]]
        self.set_time_zone(TimeZones.UTC)
        self.set_account_currency("USDT")
        self.set_cash(float(self._expected_cash))
        start = datetime.fromtimestamp(self._info["warmup"]["start"] / 1000, timezone.utc)
        end = datetime.fromtimestamp(self._info["window"]["end"] / 1000, timezone.utc)
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self._load_custom()
        for name in self._info["symbols"]:
            security = self.add_crypto_future(name, Resolution.HOUR, Market.BYBIT,
                                              fill_forward=False, leverage=float(d(self._config["leverage"])))
            security.set_fee_model(ConstantFeeModel(0))
            security.set_margin_interest_rate_model(MarginInterestRateModel.NULL)
            security.set_fill_model(R8FillModel(self))
            self._symbols[name] = security.symbol
            self._bars[name] = []
        path = Path("/r8/src") / self._config["algorithm"]["path"]
        spec = importlib.util.spec_from_file_location("r8_hypothesis", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._hypothesis_class = getattr(module, self._config["algorithm"]["class"])
        if not issubclass(self._hypothesis_class, R8Hypothesis):
            raise ValueError("假說必須繼承 R8Hypothesis")
        model = self._config["model_artifact"]
        if model is not None and (self._config["folds"] or not self._info["validation_example"]):
            raise ValueError("模型不得跳過逐折擬合")
        self._loaded_model = None if model is None else deserialize_model(
            (Path("/r8/models") / model["path"]).read_bytes(), model["sha256"])
        self._funding_schedule = {}
        for name in self._info["symbols"]:
            records = [{"t": r["t"], "rate": r["value"]} for r in self._data[name].get("funding", [])]
            self._funding_schedule[name] = rules.funding_schedule(
                records, self._info["warmup"]["start"], self._info["window"]["end"],
                self._info["funding_interval_ms"][name], self._config["cost"]["funding_blank_min_rate"],
                delivery=self._info["delistings"].get(name, {}).get("deliveryTime"))

    def _load_custom(self):
        for name in self._info["symbols"]:
            datasets = {}
            for dataset in ("kline_day", "funding", "open_interest", "turnover_hour", "turnover_day"):
                path = Path("/r8/custom") / dataset / (name.lower() + ".csv")
                rows = []
                with path.open() as f:
                    for row in csv.reader(f):
                        value = {"known_at": int(row[0]), "t": int(row[1])}
                        if dataset == "kline_day":
                            value.update(dict(zip(("open", "high", "low", "close", "volume"), row[2:])))
                        else:
                            value["value"] = row[2]
                        rows.append(value)
                datasets[dataset] = rows
            datasets["kline_hour"] = []
            self._data[name] = datasets

    def _emit(self, section, record):
        self._events.write(canonical({"section": section, "record": record}) + b"\n")

    def _fail(self, reason):
        if self._failure is None:
            self._failure = {"status": "failed", "failure_reason": reason, "failure_t": self._t}
            self.quit(reason)

    def _positions(self):
        return {s: rules.number(d(self.portfolio[symbol].quantity))
                for s, symbol in self._symbols.items() if d(self.portfolio[symbol].quantity) != 0}

    def _visible(self, t, strict=False):
        result = []
        for s in self._info["strategy_symbols"]:
            first = self._info["first_bar"].get(s)
            delivery = self._info["delistings"].get(s, {}).get("deliveryTime")
            if first is not None and (first + rules.HOUR < t if strict else first + rules.HOUR <= t) and (
                    delivery is None or t < delivery):
                result.append(s)
        return result

    def _cash_add(self, amount):
        self.portfolio.cash_book["USDT"].add_amount(float(amount))
        self._expected_cash += amount

    def _book_fill(self, fill):
        symbol, qty, price = fill["symbol"], d(fill["quantity"]), d(fill["price"])
        current = self._account_positions.get(symbol, Decimal(0))
        average = self._average.get(symbol, Decimal(0))
        new, new_average, realized = rules.apply_fill(current, average, qty, price)
        self._account_positions[symbol], self._average[symbol] = new, new_average
        self._expected_cash += realized - d(fill["fee"])
        self._fills.append(fill)
        self._emit("fills", fill)
        return realized

    def on_order_event(self, event):
        self._t = rules.milliseconds(self.utc_time)
        if event.status == OrderStatus.INVALID:
            self._fail("lean_error")
        if event.status != OrderStatus.FILLED:
            return
        order = self.transactions.get_order_by_id(event.order_id)
        leg = self._legs.get(order.tag)
        if leg is None:
            self._fail("lean_error")
            return
        fill = {k: leg[k] for k in ("order_id", "decision_t", "symbol", "quantity", "slippage_bps", "kind", "change_t")}
        fill.update(quantity=rules.number(d(event.fill_quantity)), price=rules.number(d(event.fill_price)),
                    fee=rules.number(d(event.order_fee.value.amount)))
        self._book_fill(fill)
        self._emit("orders", {k: leg[k] for k in ("order_id", "decision_t", "symbol", "quantity")} |
                   {"kind": leg["order_kind"], "status": "filled"})
        leg["done"] = True

    def _cancel(self, name, reason, replaced_by=None):
        for tag in self._pending.pop(name, []):
            leg = self._legs[tag]
            if leg.get("done"):
                continue
            response = leg["ticket"].cancel(reason)
            if not response.is_success:
                self._fail("lean_error")
                return
            record = {k: leg[k] for k in ("order_id", "decision_t", "symbol", "quantity")}
            record.update(kind=leg["order_kind"], status="cancelled", cancel_t=self._t, cancel_reason=reason)
            if replaced_by is not None:
                record["replaced_by"] = replaced_by
            self._emit("orders", record)
            leg["done"] = True

    def _settle(self, name, kind, change_t):
        quantity = d(self.portfolio[self._symbols[name]].quantity)
        if quantity == 0:
            return
        bars = self._bars[name]
        if not bars:
            raise ValueError("平倉缺價格")
        cost = self._config["cost"]
        last = bars[-1]
        previous = next((b for b in reversed(bars[:-1]) if b["end"] - b["t"] == rules.HOUR), None)
        price = (rules.delisting_price(quantity, last, previous, cost["forced_reduce_penalty_bps"],
                                       cost["slippage_multiplier"]) if kind == "delisting_settlement"
                 else rules.score_end_price(quantity, last["close"], cost))
        fee = rules.fee(quantity, price, cost["taker_fee_rate"])
        self._counter += 1
        record = {"order_id": self._counter, "decision_t": change_t, "symbol": name,
                  "quantity": rules.number(-quantity), "kind": kind, "status": "filled"}
        fill = {k: v for k, v in record.items() if k != "status"}
        fill.update(change_t=change_t, price=rules.number(price), fee=rules.number(fee),
                    slippage_bps=rules.number(d(cost["forced_reduce_penalty_bps"]) * d(cost["slippage_multiplier"])))
        realized = self._book_fill(fill)
        # 結算沒有下一根；同步改變 LEAN 現金與持倉，成本只扣一次。
        self.portfolio.cash_book["USDT"].add_amount(float(realized - fee))
        self.portfolio[self._symbols[name]].set_holdings(0, 0)
        self._emit("orders", record)

    def _boundaries(self):
        for name in sorted(self._info["delistings"]):
            delivery = self._info["delistings"][name]["deliveryTime"]
            if name not in self._delivered and delivery <= self._t:
                self._cancel(name, "delivery")
                self._settle(name, "delisting_settlement", delivery)
                self._delivered.add(name)
        for window in self._windows:
            end = window["end"]
            if end <= self._t and end not in self._closed:
                for name in sorted(self._symbols):
                    self._cancel(name, "score_end")
                for name in sorted(self._symbols):
                    self._settle(name, "score_end_liquidation", end)
                self._closed.add(end)

    def _fit_and_activate(self):
        folds = self._config["folds"]
        fit_only = not folds and "fit_window" in self._config and self._loaded_model is None
        if fit_only:
            folds = [{"fit_window": self._config["fit_window"],
                      "score_window": {"start": self._info["window"]["end"],
                                       "end": self._info["window"]["end"]}}]
        for index, fold in enumerate(folds):
            end = rules.milliseconds(fold["fit_window"]["end"])
            if index not in self._fitted and end <= self._t:
                if self._loaded_model is not None:
                    self._fitted[index] = {"artifact": self._loaded_model, "selection": None}
                else:
                    visible = self._visible(end, strict=True)
                    fit_data = {s: self._data[s] for s in visible}
                    result = rules.fit_fold(self._hypothesis_class, self._config["random_seed"],
                                            fold["fit_window"], fit_data, self._config["strategy"], self._config["cost"])
                    self._fitted[index] = result
                    artifact = result["artifact"]
                    raw, digest = serialize_model(artifact) if artifact is not None else (None, None)
                    if raw is not None:
                        (self._output / "model.json").write_bytes(raw)
                    elif (self._output / "model.json").exists():
                        (self._output / "model.json").unlink()
                    self._emit("fits", {"fold": index, "fit_window": fold["fit_window"],
                                       "selection": result["selection"],
                                       "params": None if artifact is None else artifact["params"],
                                       "model_sha256": digest})
        active = next((i for i, f in enumerate(folds)
                       if rules.milliseconds(f["score_window"]["start"]) <= self._t <
                       rules.milliseconds(f["score_window"]["end"])), None)
        if not folds:
            if self._instance is None:
                self._instance = self._hypothesis_class(self._config["random_seed"])
                self._artifact = self._loaded_model or {"params": self._config["strategy"], "model": None}
            return False
        if active is not None and active != self._active_fold:
            self._active_fold = active
            self._instance = self._hypothesis_class(self._config["random_seed"])
            self._artifact = self._fitted[active]["artifact"]
            return self._artifact is None
        return False

    def _submit_targets(self, targets, visible, kind):
        if not isinstance(targets, dict) or set(targets) != set(visible):
            raise ValueError("invalid_decision")
        prices = {s: self._bars[s][-1]["close"] for s in visible}
        equity = rules.number(d(self.portfolio.total_portfolio_value))
        proposed = self._positions()
        plans = []
        for name in sorted(targets):
            target = targets[name]
            props = self._info["properties"][name]
            if set(target) == {"weight"}:
                quantity = rules.target_quantity(target["weight"], equity, prices[name], props["qty_step"])
            elif set(target) == {"quantity"} and self._info["validation_example"]:
                quantity = d(target["quantity"])
            else:
                raise ValueError("invalid_decision")
            current = d(self.portfolio[self._symbols[name]].quantity)
            reason, bps = rules.liquidity(self._t, self._info["first_bar"][name],
                                          self._data[name]["turnover_day"], self._config["cost"])
            hour = next((r["value"] for r in reversed(self._data[name]["turnover_hour"])
                         if r["known_at"] == self._t), "0")
            segments = rules.order_segments(current, quantity, prices[name], props["qty_step"], props["min_qty"],
                                            self._info["min_notional"][name], reason, bps, hour, self._config["cost"])
            proposed[name] = rules.number(rules.effective_target(current, segments))
            plans.append((name, segments))
        # 未交給策略但仍有部位的標的也納入檢查。
        all_prices = {s: self._bars[s][-1]["close"] for s in proposed}
        all_prices.update(prices)
        # 失敗的目標也須保留，供 U6 重建觸發曝險上限的決策。
        self._emit("decisions", {"t": self._t, "targets": targets})
        rules.exposure(proposed, all_prices, equity, self._config["gross_exposure_cap"])
        self._last_decision_prices, self._last_decision_equity = all_prices, equity
        for name, segments in plans:
            if not segments and not any(not self._legs[tag].get("done") for tag in self._pending.get(name, [])):
                continue
            if not segments:
                self._cancel(name, "replaced")
                continue
            self._counter += 1
            order_id = self._counter
            self._cancel(name, "replaced", order_id)
            self._pending[name] = []
            for index, segment in enumerate(segments):
                record = {"order_id": order_id, "decision_t": self._t, "symbol": name,
                          "quantity": segment["quantity"]}
                if segment["reason"] is not None:
                    self._emit("voided", record | {"reason": segment["reason"]})
                    self._emit("orders", record | {"kind": kind, "status": "voided"})
                    continue
                tag = "r8:" + str(order_id) + ":" + str(index)
                leg = record | {"slippage_bps": segment["slippage_bps"], "kind": segment["kind"], "order_kind": kind}
                self._legs[tag] = leg
                self._pending[name].append(tag)
                leg["ticket"] = super().market_order(self._symbols[name], float(d(segment["quantity"])), True, tag)
                if leg["ticket"].status == OrderStatus.INVALID:
                    self._fail("lean_error")

    def _funding(self, endpoint=False):
        for name in sorted(self._symbols):
            for record in self._funding_schedule[name]:
                t = record["t"]
                key = (name, t)
                if key in self._funded or (t != self._t if endpoint else t >= self._t):
                    continue
                before, after = rules.positions_at(self._fills, name, t)
                self._funded.add(key)
                if before == 0 and after == 0:
                    continue
                price, _ = rules.funding_price(self._bars[name], t)
                amount = rules.funding_amount(before, after, price, record["rate"],
                                               self._config["cost"]["funding_delta"], record["estimated"])
                entry = {"t": t, "symbol": name, "q_before": rules.number(before), "q_after": rules.number(after),
                         "price": rules.number(price), "rate": record["rate"], "amount": rules.number(amount),
                         "estimated": record["estimated"]}
                self._emit("endpoint_funding" if endpoint else "funding", entry)
                if not endpoint:
                    self._cash_add(amount)

    def on_data(self, data):
        if self._failure is not None:
            return
        self._t = rules.milliseconds(self.utc_time)
        try:
            for name, symbol in self._symbols.items():
                if symbol not in data.bars:
                    continue
                bar = data.bars[symbol]
                if bar.is_fill_forward:
                    self._emit("fill_forward_bars", {"t": self._t, "symbol": name})
                    self._fail("fill_forward_bar")
                    return
                delivery = self._info["delistings"].get(name, {}).get("deliveryTime")
                record = {"t": rules.milliseconds(bar.time), "end": rules.milliseconds(bar.end_time),
                          "known_at": rules.milliseconds(bar.end_time),
                          **{key: rules.number(d(getattr(bar, key))) for key in ("open", "high", "low", "close", "volume")}}
                if delivery is not None and record["t"] < delivery < record["end"]:
                    record["end"] = delivery
                self._bars[name].append(record)
                if delivery is None or rules.milliseconds(bar.end_time) <= delivery:
                    self._data[name]["kline_hour"].append(record)
            if self._last_decision_equity is not None:
                rules.exposure(self._positions(), self._last_decision_prices, self._last_decision_equity,
                               self._config["gross_exposure_cap"])
            self._boundaries()
            flatten = self._fit_and_activate()
            in_window = any(w["start"] <= self._t < w["end"] for w in self._windows)
            visible = self._visible(self._t)
            if in_window and visible and (flatten or rules.decision_due(self._config["decision_resolution"], self._t)):
                if flatten:
                    targets = {s: {"weight": "0"} for s in visible}
                elif self._artifact is not None:
                    targets = rules.decide(self._instance, self._t, self._data, self._artifact, visible)
                else:
                    targets = None
                if targets is not None:
                    self._submit_targets(targets, visible, "no_trade_flatten" if flatten else "strategy")
            self._funding()
            cash = d(self.portfolio.cash_book["USDT"].amount)
            residual = cash - self._expected_cash
            if residual != 0:
                self._emit("cash_residual", {"t": self._t, "residual": rules.number(residual)})
            self._emit("steps", {"t": self._t, "equity": rules.number(d(self.portfolio.total_portfolio_value)),
                                 "cash": rules.number(cash), "positions": self._positions()})
        except ValueError as exc:
            self._fail("gross_exposure_cap" if "gross_exposure_cap" in str(exc) else "invalid_decision")
        except Exception:
            self._fail("algorithm_exception")

    def on_end_of_algorithm(self):
        if self._failure is None:
            try:
                self._funding(endpoint=True)
                if self._positions() or any(not leg.get("done") for leg in self._legs.values()):
                    self._fail("lean_error")
            except Exception:
                self._fail("algorithm_exception")
        self._emit("finished", self._failure or {"status": "completed", "failure_reason": None, "failure_t": None})
        self._events.close()

    def on_margin_call_warning(self):
        self._fail("lean_error")

    def on_margin_call(self, requests):
        self._fail("lean_error")
        return []

    def market_order(self, *args, **kwargs):
        self._fail("invalid_decision")
        raise ValueError("只允許框架內部下單")

    order = market_order
    buy = market_order
    sell = market_order
    limit_order = market_order
    stop_market_order = market_order
    stop_limit_order = market_order
    set_holdings = market_order
    liquidate = market_order
