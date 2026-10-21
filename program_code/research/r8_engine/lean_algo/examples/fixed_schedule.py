"""記錄者 P4 構造檢查用；不是研究假說。"""
from program_code.research.r8_engine.lean_algo.framework import R8Hypothesis


class FixedSchedule(R8Hypothesis):
    def score(self, params, train_window, validation_window, data, cost):
        if "no_trade_at" in params and validation_window["end"] >= params["no_trade_at"]:
            return "-1"
        return params["score"]

    def fit(self, fit_window, data, params):
        return {"fit_end": fit_window["end"]}

    def on_decision(self, time, data, model, params):
        targets = None
        for item in params.get("schedule", ()):
            if item["t"] == time:
                targets = {symbol: dict(item["targets"].get(symbol, {"weight": "0"}))
                           for symbol in data}
                break
        # visibility_probe 須宣告為 neighborhood.categorical 的類別軸。
        probe = params.get("visibility_probe")
        if probe is not None and probe["t"] == time:
            # 僅讀 on_decision 的公開視圖；缺列、欄位或 map 值直接拋例外。
            row = data[probe["symbol"]][probe["dataset"]][-1]
            quantity = probe["map"][row[probe["field"]]]
            # 其他可見標的照原 schedule；該時刻未排程者目標 0，完整涵蓋 §7。
            if targets is None:
                targets = {symbol: {"weight": "0"} for symbol in data}
            targets[probe["symbol"]] = {"quantity": quantity}
        return targets
