# WP7 Learning Effect Review Stop Loop Rework 2

Date: 2026-07-07
Role: E1(worker)
Status: DONE

## Scope

針對 E2 re-review RETURN 的 authority grant string finding 做第二次 source-only 窄修。未觸碰 runtime、DB、exchange/private read、MCP/secret、order/probe、Cost Gate、deploy、live/mainnet、model reload、symlink、registry persistence 或 bounded Demo outcome ingestion。

## Files Changed

- `program_code/ml_training/learning_effect_review.py`
- `program_code/ml_training/tests/test_learning_effect_review.py`
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp7_learning_effect_review_stop_loop_rework2.md`
- `docs/CCAgentWorkSpace/E1/memory.md`

## Finding Closed

- Authority expansion key values now use `_authority_value_grants(...)` instead of generic `_truthy(...)`.
- For authority expansion keys, booleans and numeric grants keep existing semantics, while string values fail closed unless they are explicit false tokens such as `false`, `0`, `off`, `disabled`, or `denied`.
- This closes forged packets using nested `metadata.trade_allowed="allowed"`, `"allow"`, or execution authority aliases such as `"active"` / `"approved"` after recomputing `review_hash`.
- Explicit false string tokens remain safe and do not create authority boundary violations.

## Verification

```text
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/learning_effect_review.py program_code/ml_training/reward_ledger.py program_code/ml_training/proof_packet_contract.py program_code/ml_training/demo_mutation_envelope.py
```

Result: passed with no output.

```text
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_learning_effect_review.py program_code/ml_training/tests/test_reward_ledger.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_demo_mutation_envelope.py -p no:cacheprovider
........................................................................ [ 53%]
..............................................................           [100%]
134 passed in 3.46s
```

`git diff --check` is run after this report and memory update; final output is reported to PM/operator.

## Residual Concerns

- This remains source-only validation and grants no promotion/order/runtime authority.
- Existing unrelated dirty files under memory, IBKR, and Bybit `control_api_v1` were not touched.
