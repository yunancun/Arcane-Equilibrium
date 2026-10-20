"""記錄者 P4 構造檢查用；不是研究假說。"""
from program_code.research.r8_engine.lean_algo.framework import R8Hypothesis


class FixedSchedule(R8Hypothesis):
    def score(self, params, train_window, validation_window, data, cost):
        return params["score"]

    def fit(self, fit_window, data, params):
        return {"fit_end": fit_window["end"]}

    def on_decision(self, time, data, model, params):
        for item in params.get("schedule", ()):
            if item["t"] == time:
                return {symbol: dict(item["targets"].get(symbol, {"weight": "0"}))
                        for symbol in data}
        return None
