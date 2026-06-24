# 2026-06-24 -- False-Negative Bounded Probe Preflight Bridge

STATUS: DONE_WITH_CONCERNS

已把 selected candidate `grid_trading|AVAXUSDT|Sell` 接進 bounded Demo
preflight 的 no-authority source path：

- 新增 `false_negative_bounded_probe_preflight.py`。
- `bounded_probe_touchability_preflight.py` 與
  `bounded_probe_operator_authorization.py` 現在接受 false-negative preflight
  schema，不再只吃 sealed-horizon preflight。
- 實際 AVAX artifact smoke 輸出 `OPERATOR_REVIEW_REQUIRED`，candidate
  alignment 已過，唯一 blocker 是 false-negative operator review 仍為
  `defer`。

這不是下單授權：

- `probe_authority_granted=false`
- `order_authority_granted=false`
- `main_cost_gate_adjustment=NONE`
- `promotion_evidence=false`
- 未改 runtime / cron / service / PG / Bybit / live。

驗證：

- `py_compile` pass
- focused bounded/false-negative tests：`19 passed`
- broader Cost Gate bounded suite：`142 passed`
- `git diff --check` clean

下一步仍是 exact false-negative preflight review approval；之後才可進
candidate-matched touchability、placement、bounded authorization review。

