# Source Stability Guard Blocker Binding Done

## 結論

狀態：`DONE_WITH_CONCERNS`

Active blocker 仍是 `P0-CURRENT-CANDIDATE-NOORDER-REFRESH-CURRENT-HEAD-E3-BB-REQUEST`。本輪修正的是前置 source artifact review 問題：`source_stability_window_guard_v1` 不再只能輸出歷史 order-capable blocker id；它現在可由 function/CLI 明確綁定當前 no-order refresh blocker id。

沒有執行 Control API GET、Bybit public/private call、Decision Lease、PG、service/env/risk mutation、Cost Gate change、live/mainnet、order/fill/PnL/proof。

## Source Change

- Source commit: `07592ea70445e1e5e1b3b55389e3d16cdcdcda9d`
- Files:
  - `helper_scripts/research/cost_gate_learning_lane/source_stability_window_guard.py`
  - `helper_scripts/research/tests/test_source_stability_window_guard.py`
- Behavior:
  - Default remains `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE` for compatibility.
  - New `active_blocker_id` builder arg and CLI `--active-blocker-id` can bind `P0-CURRENT-CANDIDATE-NOORDER-REFRESH-CURRENT-HEAD-E3-BB-REQUEST`.
  - Blank override falls back to the compatibility default.
  - Authority/risk answers remain false; this artifact grants no approval or runtime/order authority.

## Verification

- PM local: `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_source_stability_window_guard.py` -> `14 passed`
- PM local: `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/source_stability_window_guard.py helper_scripts/research/tests/test_source_stability_window_guard.py` -> pass
- PM local: `git diff --check` for touched files -> pass
- PM local CLI smoke with `--active-blocker-id P0-CURRENT-CANDIDATE-NOORDER-REFRESH-CURRENT-HEAD-E3-BB-REQUEST` confirmed JSON `active_blocker_id` matches and all authority/runtime/proof flags remain false.
- E2(explorer): `DONE`, no blocking findings; confirmed compatibility default, blank fallback, CLI wiring, test coverage, and unchanged authority/risk semantics.
- E4(worker): `DONE`, independently ran focused tests, py_compile, diff-check, and CLI smoke.

## Next Action

After this source/docs checkpoint is pushed, fetch current `origin/main`, create a clean source-stability first sample with `--active-blocker-id P0-CURRENT-CANDIDATE-NOORDER-REFRESH-CURRENT-HEAD-E3-BB-REQUEST`, wait the quiet window, and only then regenerate the no-order E3/BB request. Since v711 equity sha `db0c68bf028df42429d92583306b5ca8b0d5dd51b17661c2240dbf11b4ea16a4` is stale under 900s, the request must include or first obtain an E3-approved one-GET fast-balance refresh path before any public Demo quote or downstream envelope/plan preview.
