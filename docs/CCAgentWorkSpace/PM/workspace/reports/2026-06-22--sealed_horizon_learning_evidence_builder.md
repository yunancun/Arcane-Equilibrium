# 2026-06-22 — Sealed Horizon Learning Evidence Builder

## VERDICT

PASS_WITH_BOUNDARY：已把 `ma_crossover|BTCUSDT|Sell` 240m sealed horizon candidate 從「離線 replay 可疑似有 edge」推進到「可重跑的 scratch learning evidence」。這不是下單授權、不是 Cost Gate lowering、不是 promotion proof；它是 operator-review 前的 blocked-signal outcome evidence。

## 事實

- 新增 `helper_scripts/research/cost_gate_learning_lane/sealed_horizon_learning_evidence.py`。
- 它只接受 plan 中 `source_kind=horizon_specific_sealed_replay` 的 side-cell。
- 流程：read-only mature rejects -> scratch `probe_admission_decision` ledger -> candidate-horizon blocked outcomes -> blocked-outcome review -> compact `sealed_horizon_learning_evidence_v1` packet。
- Mac 驗證：
  - py_compile passed
  - 新 focused test `3 passed`
  - learning-lane focused `73 passed`
  - related sealed/learning/profitability/alpha suite `124 passed`
  - `git diff --check` passed
- Linux source fast-forward 到 `72ae1055fdeab099b5a2686881f29927c57c444c`，未 deploy/restart。
- Linux smoke packet：
  - `/tmp/openclaw/profitability_refresh/20260622T031320Z/sealed_horizon_learning_evidence_tool/sealed_horizon_learning_evidence_latest.json`
  - rejects：16,515 mature `ma_crossover|BTCUSDT|Sell`
  - materialization：16,515 `ORDER_AUTHORITY_NOT_GRANTED`
  - outcomes：16,515 blocked outcomes at 240m
  - avg gross：`7.0511bp`
  - avg net after 4bp cost：`3.0511bp`
  - net-positive：`68.56%`
  - review：`DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`

## 判斷

這條證據支持「side-cell / horizon specific 的 bounded demo probe review」，不支持全局 lowering Cost Gate。現在最有價值的盈利路徑不是把 gate 放鬆，而是把 gate 從單一全局 blocker 改造成可學習的候選選擇器：

1. 對 sealed side-cell 累積 blocked-signal outcome。
2. 對通過 review 的 side-cell 開 operator-gated tiny bounded demo probe。
3. 用 fill / slippage / realized demo outcome 驗證 markout edge 是否可執行。
4. 只在 Rust authority 下做 side-cell / horizon / budget constrained 放行，不改主 Cost Gate。

## 邊界

- No PG write / schema migration
- No Bybit private/signed/trading call
- No deploy/rebuild/restart
- No env/auth/risk/order/strategy mutation
- No main Cost Gate lowering
- No probe/order authority
- No promotion proof

## 下一步

1. Operator review 是否允許把此 packet 作為 bounded demo probe review input。
2. 若允許，下一個工程 gate 不是直接下單，而是把 production learning lane writer/cron/prod ledger 啟用到能持續產生同類 evidence。
3. 再設計 Rust-authority 下的 tiny demo-only side-cell probe lease，使用 240m horizon outcome writer 做 realized validation。
