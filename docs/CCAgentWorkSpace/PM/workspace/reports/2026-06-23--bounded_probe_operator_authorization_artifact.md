# Bounded Probe Operator Authorization Artifact

日期：2026-06-23
PM checkpoint：`bbb5c51f`

## 結論

本輪補上 v425 authorization contract 前面的 operator-review artifact。現在不需要手寫 runtime authorization JSON：`bounded_probe_operator_authorization.py` 會把 sealed preflight、placement repair plan、authority-path readiness 三個上游 no-authority artifacts 合成 `bounded_demo_probe_operator_authorization_packet_v1`，並且只有在所有 gate 通過與 operator typed-confirm 精確匹配時，才會內嵌 runtime 可讀的 `bounded_demo_probe_operator_authorization_v1`。

這不是下單，也不是降低主 Cost Gate。它的價值是把「翻越 cost gate 的第一次真實 Demo 學習探針」變成 bounded、side-cell-specific、可過期、可限量、可審計、可回放的 operator 授權物件。

## Source 改動

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization.py`
  - 新增 artifact-only builder。
  - 檢查 sealed preflight、placement repair、authority-path readiness 是否 fresh/schema-ready/status-ready/authority-preserving。
  - 檢查三個 artifact 是否對齊同一 side-cell / strategy / symbol / side / horizon。
  - `authorize` 決策必須提供 operator id、authorization id、bounded max orders、future expiry、exact typed confirm。
  - 僅在所有 gate 通過時輸出 `operator_authorization`。
- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization_cli.py`
  - 提供 Markdown/JSON packet CLI。
- `helper_scripts/research/cost_gate_learning_lane/contract.py`
  - 集中 bounded probe authorization schema/status/readiness constants。
- `helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py`
  - 改為引用 shared constants，避免 contract string drift。
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py`
  - 覆蓋 missing input、review-only、wrong typed confirm、happy authorization、budget/expiry fail、candidate mismatch、authority-granting input fail-closed。

## Profitability Path

這一步不是盈利本身，但它把盈利系統缺的一段閉環補上：

1. blocked-signal / sealed-horizon / multi-horizon evidence 找到可能被 Cost Gate 錯擋的 side-cell。
2. near-touch placement repair 讓 future Demo probe 有機會產生 fill-backed data，而不是 deep passive no-touch。
3. authorization artifact 把 operator 的一次性小額試探授權做成機器可驗證 contract。
4. runtime 只在匹配該 contract 時允許 bounded Demo learning probe。
5. 後續用 order-to-fill / fill-fee-slippage / matched blocked controls / result-review / execution-realism review 判斷 alpha 是否真實、是否可捕捉、是否應調整 Cost Gate。

這比直接全局 lower cost gate 更好，因為它降低了錯誤放行面，同時提供真實市場標籤來訓練/修正系統。

## Verification

Mac:

- `python3 -m py_compile ...bounded_probe_operator_authorization.py ...bounded_probe_operator_authorization_cli.py ...runtime_adapter.py ...contract.py ...test_cost_gate_bounded_probe_operator_authorization.py` -> passed
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py` -> 7 passed
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -k "operator_authorization or authority_patch or runtime_adapter_admits"` -> 8 passed, 70 deselected
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> 71 passed
- related bounded/preflight/operator-review suite -> 36 passed

Linux `trade-core` after ff-only sync to `bbb5c51f`:

- py_compile same files -> passed
- authorization focused tests -> 7 passed
- full policy suite -> 71 passed
- related bounded/preflight/operator-review suite -> 36 passed

## Boundary

No CI was run. No PG query/write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no active probe/order authority, no actual order, and no promotion proof.
