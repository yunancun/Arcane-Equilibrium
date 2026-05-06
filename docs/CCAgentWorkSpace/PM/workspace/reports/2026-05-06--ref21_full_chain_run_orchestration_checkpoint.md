# REF-21 Full-Chain Run Orchestration Checkpoint

**Date:** 2026-05-06  
**Owner:** PM  
**Status:** P0-REF21-7 closed; P0-REF21-6 split into 6a closed and 6b still blocking R3 completeness

## Summary

This checkpoint lands two REF-21 replay execution blockers without changing
live/demo trading authority:

- `ReplayBybitPublicClient` is a replay-only Bybit public-data client with a
  50 req/s global ceiling, lower per-kline endpoint budget, endpoint allowlist,
  and bounded retry/backoff on 429/5xx.
- `POST /api/v1/replay/full-chain/run` now prepares one multi-symbol S2 fixture,
  registers one V049 manifest per requested strategy, and starts the existing
  dedicated Rust `replay_runner` subprocess through the REF-20 PG run path.

The new full-chain run route is orchestration only. It does not run scanner,
strategy, risk, exchange, or Decision Lease logic inside the uvicorn worker.

## Implemented

- `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/bybit_public_client.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_bybit_public_client.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py`
- Additional static guard in `test_replay_full_chain_routes.py`

## Verification

Mac:

```text
python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_bybit_public_client.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_routes.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py -q
=> 16 passed

python3 -m py_compile \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/bybit_public_client.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_quick_routes.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py
=> passed

git diff --check
=> passed
```

Linux `trade-core` verification is required after push/sync for the second
checkpoint commit.

## Remaining Gap

The endpoint is not yet the final REF-21 historical scanner timeline runner.
Current scope is:

```text
current/historical requested universe fixture -> strategy/risk replay_runner subprocess -> report/finalize
```

Remaining R3 blocker:

```text
historical symbol universe + historical edge snapshots + replay-safe ScannerCore
-> scan-cycle timeline -> strategy/risk replay_runner report
```

Therefore TODO now splits:

- `P0-REF21-6a` closed: API orchestration and subprocess handoff.
- `P0-REF21-6b` open: true scanner timeline completeness.

