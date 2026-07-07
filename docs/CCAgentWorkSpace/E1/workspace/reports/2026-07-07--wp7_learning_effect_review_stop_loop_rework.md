# WP7 Learning Effect Review Stop Loop Rework

Date: 2026-07-07
Role: E1(worker)
Status: DONE

## Scope

針對 E2 `RETURN_TO_E1` 的三個 finding 做 source-only 修補。未觸碰 runtime、DB、exchange/private read、MCP/secret、order/probe、Cost Gate、deploy、live/mainnet、model reload、symlink、registry persistence 或 bounded Demo outcome ingestion。

## Files Changed

- `program_code/ml_training/learning_effect_review.py`
- `program_code/ml_training/tests/test_learning_effect_review.py`
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp7_learning_effect_review_stop_loop_rework.md`
- `docs/CCAgentWorkSpace/E1/memory.md`

## E2 Findings Closed

- MED-1 refs integrity：validator 現在從 embedded `source_artifacts.reward_records` 重建 canonical reward ref set，並從每筆 reward record lineage 重建 proof / mutation hash sets；supplied refs 必須與 expected sets 完全相等。新增 dropped reward ref、extra reward ref、forged proof ref、forged mutation ref 且重算 `review_hash` 的 regression tests。
- MED-2 authority aliases：authority scanner 增加 `trade_allowed`、`trading_enabled`、`enable_trading`、`execution_authority_granted` 等 trading/execution alias；`execution_identity` 這類 inert identity 欄位不因沒有 action token 被誤擋。新增 nested metadata/source-artifact alias regression tests。
- MED-3 loss controls：`loss_limits` 現在要求 `max_cumulative_loss_bps`、`max_cumulative_loss_usdt`、`max_single_record_loss_bps`、`max_consecutive_negative_windows`、`breach` 全部存在且型別正確；`breach="true"` 或任何 truthy breach alias 先 fail closed 到 `stop_loss_control`。新增 `breach="true"`、missing `max_cumulative_loss_usdt`、missing/bad `max_consecutive_negative_windows` tests。

## Verification

```text
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/learning_effect_review.py program_code/ml_training/reward_ledger.py program_code/ml_training/proof_packet_contract.py program_code/ml_training/demo_mutation_envelope.py
```

Result: passed with no output.

```text
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_learning_effect_review.py program_code/ml_training/tests/test_reward_ledger.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_demo_mutation_envelope.py -p no:cacheprovider
........................................................................ [ 55%]
.........................................................                [100%]
129 passed in 3.11s
```

`git diff --check` is run after this report and memory update; final output is reported to PM/operator.

## Residual Concerns

- This remains source-only validation. It grants no promotion/order/runtime authority.
- Existing unrelated dirty files under memory, IBKR, and Bybit `control_api_v1` were not touched.
