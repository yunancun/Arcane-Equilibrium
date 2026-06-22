# Cost Gate Learning-Lane Accumulation Gate

## 結論

v396 關掉了 sealed preflight chain 的 production learning-lane evidence blocker。

之前狀態是：sealed evidence 和 aligned decision packet 都存在，但 preflight 仍卡在 `production_learning_lane_accumulating=false`。本輪先跑 4h default refresh，結果 materializer 是 0 row，暴露問題不是 source 缺失，而是 extraction cadence/lookback 太窄。隨後用受控 168h lookback 做 artifact-only refresh，成功把已記錄 demo rejects 轉成 ledger/outcome/review evidence。

現在 sealed preflight 狀態已從 `OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED` 變為 `OPERATOR_REVIEW_REQUIRED`。剩下的 gate 是實際 operator review，不是工程資料鏈。

## Source Change

- `helper_scripts/research/cost_gate_learning_lane/status.py`
  - 新增 `--json-output`，可把 activation preflight 寫成 canonical artifact。
  - 本輪使用位置：`/tmp/openclaw/cost_gate_learning_lane/activation_preflight_latest.json`

- `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`
  - 新增 regression：CLI 可寫出 activation preflight JSON，schema/status/boundary 可讀。

- `helper_scripts/SCRIPT_INDEX.md`
  - 登記 `--json-output` 用法。

## Runtime Evidence

Manual default 4h refresh:

- `reject_materializer_latest.json` status：`NO_NEW_REJECT_ROWS`
- ledger rows：`0`
- interpretation：default cadence/lookback 不足，不能證明 production lane 正在累積。

Manual controlled 168h refresh:

- `probe_ledger.jsonl`：40,000 rows, 57 MiB
- `reject_materializer_latest.json`
  - status：`MATERIALIZED_REJECT_ROWS_PRESENT`
  - input rows：20,000
  - materialized/appended：20,000 / 20,000
  - decision counts：`ORDER_AUTHORITY_NOT_GRANTED=8663`, `SIDE_CELL_NOT_SELECTED=11337`
- `outcome_refresh_latest.json`
  - windows：20,000
  - price observations：341
  - blocked-signal outcomes：20,000
  - appended outcomes：20,000
- `blocked_outcome_review_latest.json`
  - sha256：`f84743e74433936d4622e419578f657e078e94da133a0d3bd18964f130033faf`
  - status：`DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`
  - top candidate：`ma_crossover|ETHUSDT|Sell`
  - wrongful-block score：`17.32115075884182`
  - net cost cushion：`8.66057537942091bp`

Canonical activation preflight:

- path：`/tmp/openclaw/cost_gate_learning_lane/activation_preflight_latest.json`
- sha256：`4d0aa4a005a4de0dd821b6fdd5da41d9543b3af141e6617aeb8987bb737a0cb3`
- status：`REVIEW_CANDIDATE_OPERATOR_REVIEW`
- `currently_accumulating_evidence=true`
- blocked-signal outcomes：20,000
- `silent_drop_risk=false`

Canonical sealed preflight:

- path：`/tmp/openclaw/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json`
- sha256：`c3e943e595cf982eedac9a7e45ad738a5876a93e2a5b3c809666b1f1b05a78ce`
- status：`OPERATOR_REVIEW_REQUIRED`
- `decision_packet_aligned=true`
- `production_learning_lane_accumulating=true`
- remaining blocking gate：`operator_sealed_horizon_review_recorded`

Alpha discovery latest:

- path：`/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- sha256：`ac8b9bb7448afe236f597f95ebb2a2993ded2945792542ade33c368c666ba1a8`
- Cost Gate arm：`probe_ready/operator_required`
- primary blocker：`sealed_horizon_probe_preflight_requires_operator_review`

## Verification

Mac:

- py_compile passed.
- Focused activation tests：`3 passed`.
- Sealed preflight/static suite：`10 passed`.
- Full cost-gate policy/status suite：`71 passed`.
- `git diff --check` passed.

Linux:

- Source fast-forwarded to `ab9b7dc9`.
- py_compile passed.
- Focused activation tests：`2 passed`.
- Runtime artifact refreshes completed with exit 0.

## Boundary

- No CI run.
- No PG write/schema migration.
- No Bybit private/signed/trading call.
- No deploy/rebuild/restart.
- No crontab install.
- No writer/env enablement.
- No auth/risk/order/strategy/runtime mutation.
- No Cost Gate lowering.
- No probe/order authority.
- No promotion proof.

## Interpretation

This is not a profitability proof and not execution/fill evidence. It is blocked-signal markout evidence: existing demo rejects can now be converted into a learning ledger, outcomes, and review candidates.

The practical improvement is important: the system no longer needs to guess whether Cost Gate is silently discarding useful signals. It now has a local evidence loop showing which blocked side-cells appear profitable after markout and which remain correctly blocked.

The next hard gate is operator review. Codex cannot self-approve this because approval would be a governance action in front of bounded demo-probe authority.
