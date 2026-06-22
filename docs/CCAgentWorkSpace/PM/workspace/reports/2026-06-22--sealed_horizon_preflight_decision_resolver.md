# Sealed Horizon Preflight Decision Resolver

## 結論

v394 修掉 sealed-horizon preflight 的一個 artifact routing drift：如果 explicit `profit_learning_decision_packet_latest.json` 是舊 generic packet，preflight 現在可以在 operator 提供的 search root 裡選中 fresh aligned sealed decision packet。

這不降低 Cost Gate，也不讓任何 probe/order 通過。它只避免 sealed candidate 因讀錯 latest pointer 而被錯誤降級成 decision-packet mismatch。

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/sealed_horizon_probe_preflight.py`
  - 抽出原有 decision alignment predicate，保持條件不變。
  - 新增 `resolve_decision_packet_for_sealed_horizon_preflight(...)`。
  - 新增 CLI `--decision-packet-search-root`。
  - 如果 explicit packet 已 fresh aligned，照常使用 explicit。
  - 如果 explicit packet 不 aligned，會掃 search root 裡的 `profit_learning_decision_packet*.json`，只選 fresh、schema 正確、同 side-cell/horizon、sealed evidence ready、authority boundary clean 的 packet。
  - 找不到 aligned packet 時仍使用 explicit/missing source，讓 preflight fail closed。

- `helper_scripts/research/tests/test_cost_gate_sealed_horizon_probe_preflight.py`
  - 新增 regression：generic latest 是 `ACTIVATE_OR_REPAIR_LEARNING_STACK`，但 search root 內存在 sealed v389 packet 時，resolver 選 sealed packet，preflight `decision_packet_aligned=true`。

- `helper_scripts/SCRIPT_INDEX.md`
  - 登記新 CLI option 與 artifact-only 邊界。

## Verification

- Mac py_compile passed.
- Mac focused preflight pytest：`5 passed`.
- Mac related Cost Gate/profitability/alpha/worklist suite：`80 passed`.
- Mac `git diff --check` passed.
- Linux `trade-core` fast-forwarded source to `3fd4825b`.
- Linux py_compile passed.
- Linux same related suite：`80 passed`.

Linux artifact smoke:

- Explicit packet intentionally old/generic：
  `/tmp/openclaw/profitability_refresh/20260622T031320Z/cost_gate_learning_lane/profit_learning_decision_packet_latest.json`
- Search root：
  `/tmp/openclaw/profitability_refresh/20260622T031320Z`
- Resolver selected sealed packet：
  `/tmp/openclaw/profitability_refresh/20260622T031320Z/profit_learning_decision_packet_v389/profit_learning_decision_packet_v389_latest.json`
- Output：
  `/tmp/openclaw/profitability_refresh/20260622T031320Z/preflight_resolver_v394/sealed_horizon_probe_preflight_latest.json`
- sha256：
  `6bd70df6c09753f1acf135990387968f655021f16cab94e514f699ebe3f7f8e9`
- status：
  `OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED`
- decision gate：
  `decision_packet_aligned=true`
- remaining blocking gates：
  `operator_sealed_horizon_review_recorded`, `production_learning_lane_accumulating`

## Boundary

- No PG write/schema migration.
- No Bybit private/signed/trading call.
- No deploy/rebuild/restart.
- No env/auth/risk/order/strategy/runtime mutation.
- No Cost Gate lowering.
- No probe/order authority.
- No promotion proof.

## Remaining Work

The preflight routing drift is closed. The current leading path still needs actual operator approval review and production learning-lane ledger/outcome accumulation before any separate bounded demo-probe authorization should be considered.
