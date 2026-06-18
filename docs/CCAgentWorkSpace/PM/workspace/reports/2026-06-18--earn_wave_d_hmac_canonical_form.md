# Earn Wave D HMAC Canonical-Form Checkpoint

**Date**: 2026-06-18
**Scope**: Source/test checkpoint for `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM`

## Decision

Closed `TODO.md` §5 `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM`.

Rust and Python already used the same Bybit V5 REST signing formula: `timestamp + api_key + recv_window + params`. This checkpoint adds fixed golden-vector tests on both sides so the canonical bytes for Earn GET and POST signing cannot silently drift.

## Implementation

- Rust: added Earn-specific golden vectors to `rust/openclaw_engine/src/common/bybit_signer.rs`.
- Python: added matching `BybitClient._sign()` parity tests to `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_bybit_rest_client_parity.py`.

The two vectors cover:

- GET sorted query string: `category=FlexibleSaving&coin=USDT&productId=USDT001`
- POST compact JSON body for `/v5/earn/place-order` Stake payload.

## Verification

```bash
cargo test -p openclaw_engine test_sign_rest_v5_earn --lib
python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_bybit_rest_client_parity.py -k 'rest_signer_earn'
git diff --check
```

Result: Rust 2 passed; Python 2 passed; diff whitespace clean.

## Remaining Work

This does not close Wave D end to end. `TODO.md` §5 still carries `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` for the full frontend -> backend -> Rust IPC integration test.

## Boundary

No true Bybit call, no credential/key/secret mutation, no full CI, no deploy/rebuild/restart, and no production runtime/DB/auth/risk/order/trading mutation.
