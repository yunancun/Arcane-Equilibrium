# E1 Report: WP-10 Bybit Integration Fixes

Date: 2026-05-16
Task: BB-M-1 (hardcoded mainnet URL) + BB-A-1 (missing ReduceOnlyReject 110017)
Status: IMPL DONE, awaiting E2 review

## 1. Task Summary

Two Bybit integration findings from BB (Bybit Broker Auditor):

- **BB-M-1**: `backtest_routes.py` line 107 hardcoded `_BYBIT_BASE_URL = "https://api.bybit.com"` (mainnet). Although this is ONLY used for the public `/v5/market/kline` endpoint (read-only, unauthenticated), replaced with env-var lookup defaulting to demo per PA instruction.

- **BB-A-1**: `BybitRetCode` enum in `bybit_rest_client.rs` missing error code `110017` (ReduceOnlyReject). Added as a terminal error (not retryable, not noop).

## 2. Changes

| File | Change |
|---|---|
| `backtest_routes.py` L42 | Added `import os` |
| `backtest_routes.py` L107-109 | Replaced hardcoded URL with `os.getenv("OPENCLAW_BYBIT_BACKTEST_URL", "https://api-demo.bybit.com")` + comment |
| `bybit_rest_client.rs` enum | Added `ReduceOnlyReject = 110017` variant |
| `bybit_rest_client.rs` from_code | Added `110017 => Some(Self::ReduceOnlyReject)` |
| `bybit_rest_client_tests.rs` | Added 7 assertions for ReduceOnlyReject (from_code + 5 classifiers) |

## 3. Key Diff

### backtest_routes.py
```diff
 import asyncio
 import json as _json
 import logging
+import os
 import threading
 import urllib.parse
 import urllib.request
```
```diff
-_BYBIT_BASE_URL = "https://api.bybit.com"
+# 歷史 K 線為公開 API，mainnet 和 demo 返回相同數據；
+# 默認 demo 避免回測模組意外指向 mainnet。
+_BYBIT_BASE_URL = os.getenv("OPENCLAW_BYBIT_BACKTEST_URL", "https://api-demo.bybit.com")
```

### bybit_rest_client.rs
```diff
     InsufficientBalance = 110012,
+    /// Reduce-only 訂單被拒（倉位不存在或方向不匹配）— 終態錯誤，重試無意義。
+    ReduceOnlyReject = 110017,
     LeverageNotModified = 110043,
```
```diff
     110012 => Some(Self::InsufficientBalance),
+    110017 => Some(Self::ReduceOnlyReject),
     110043 => Some(Self::LeverageNotModified),
```

### bybit_rest_client_tests.rs
```diff
+    // BB-A-1: ReduceOnlyReject (110017) — 終態錯誤，不可重試、不是 noop
+    assert_eq!(BybitRetCode::from_code(110017), Some(BybitRetCode::ReduceOnlyReject));
+    assert!(!BybitRetCode::ReduceOnlyReject.is_retryable());
+    assert!(!BybitRetCode::ReduceOnlyReject.is_noop());
+    assert!(!BybitRetCode::ReduceOnlyReject.is_exchange_backoff());
+    assert!(!BybitRetCode::ReduceOnlyReject.is_instrument_filter());
+    assert!(!BybitRetCode::ReduceOnlyReject.is_balance_block());
```

## 4. Governance Check

| Rule | Status |
|---|---|
| Comments Chinese-only (2026-05-05) | PASS |
| No hardcoded paths | PASS |
| bybit_rest_client.rs LOC | ~480 (under 800 warning) |
| backtest_routes.py LOC | unchanged + 3 lines |
| is_retryable = false | PASS (ReduceOnlyReject is terminal) |
| is_noop = false | PASS (real rejection, not idempotent) |
| Scope limited to PA spec | PASS (3 files only) |

## 5. Verification

- `cargo check -p openclaw_engine` -> 0 errors (2 pre-existing warnings)
- `cargo test -p openclaw_engine -- test_bybit_ret_code` -> 2 passed, 0 failed
- `python3 -c "import ast; ast.parse(...)"` -> syntax OK

## 6. Scope Not Touched

- No other Bybit-related files modified
- `bybit_api_reference.md` does not document 110017; no reference doc update needed
- Existing `is_retryable/is_noop/is_exchange_backoff/is_instrument_filter/is_balance_block` classifiers all correctly return `false` for ReduceOnlyReject without modification (ReduceOnlyReject is not in any match arm)
