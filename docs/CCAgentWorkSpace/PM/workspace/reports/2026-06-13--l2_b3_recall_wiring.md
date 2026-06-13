# 2026-06-13 — L2 B3 recall wiring

## Verdict

`PASS / SOURCE-WIRED / DEFAULT-OFF / NO-RESTART`.

B3 recall is now wired at source level for both the main L2 agent loop and the ml_advisory guest cascade. Runtime behavior remains unchanged unless `OPENCLAW_L2_MEMORY_RECALL` is set.

## Scope

Implemented:

- new helper `app/l2_memory_recall_context.py`
- mainline `layer2_engine` B3 wiring at the existing lesson-retrieval prompt boundary
- guest-line `l2_ml_advisory_executor` B3 wiring for diagnose/interpret and hypothesize paths
- D3 ledger metadata injection through existing `input_context`
- focused tests for default-off, shadow, active prompt injection, and fail-open behavior

Flag contract:

```text
OPENCLAW_L2_MEMORY_RECALL=0       # default: no import, no DB read
OPENCLAW_L2_MEMORY_RECALL=shadow  # compute recall bundle; ledger metadata only
OPENCLAW_L2_MEMORY_RECALL=1       # inject stable/recent blocks into prompt + ledger metadata
```

`shadow` writes only:

```json
{"memory_recall_shadow":{"mode":"shadow","record_ids":["..."],"total_chars":123,"degraded_level":"fts"}}
```

It does not send recalled text to the model. Active mode `1` appends stable rule/system-trait memory to the system prompt and prepends recent incident memory to the user message. Both modes fail open to unchanged prompt if recall import/DB/timeout fails.

## Files

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/l2_memory_recall_context.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_engine.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/l2_ml_advisory_executor.py`
- `program_code/learning_engine/memory_distiller/recall.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_memory_recall_context.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_d3_ledger.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_p3a_ml_advisory.py`

## Verification

Focused Mac regression:

```text
92 passed in 2.53s
```

Covered:

- `program_code/learning_engine/memory_distiller/tests/test_recall.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_memory_recall_context.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_d3_ledger.py::TestEngineWiring`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_p3a_ml_advisory.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_p3b_hypothesize.py`

`py_compile` also passed for the touched app modules and `memory_distiller/recall.py`.

## Boundaries

No CI, no deploy, no rebuild/restart, no DB write, no cron change, no persistent runtime flag enablement, no Gate-B probe, and no auth/risk/order/trading mutation.

Engine PID on Linux remains `3607315`; this source change requires the next operator-approved restart/deploy before the running API process can execute it.

## Remaining

- Optional next low-risk runtime step: after deploy/restart window, set `OPENCLAW_L2_MEMORY_RECALL=shadow` for an audit window and verify D3 `input_context.memory_recall_shadow` rows.
- Active mode `1` should wait for shadow evidence review.
- First non-empty L2 material day still needs true distillation/model-call evidence.
