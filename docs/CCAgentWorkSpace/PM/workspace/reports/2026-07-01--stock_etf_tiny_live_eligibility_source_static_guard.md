# PM Report — Stock/ETF Tiny-Live Eligibility Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF tiny-live ADR eligibility source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_tiny_live_eligibility.rs` 的 source-only 姿態；不是 tiny-live/live authorization、
不是 IBKR contact、不是 connector construction、不是 secret access、不是 evidence clock、
不是 Bybit gate lowering。

## Completed

- 新增 `tests/structure/test_stock_etf_tiny_live_eligibility_source_static.py`。
- Guard 要求 `stock_etf_tiny_live_eligibility.rs` 低於 800 行 governance cap。
- Guard 要求 ADR/AMD/spec release paths、tiny-live ADR eligibility contract id、decision enum、
  request/verdict/blocker surface 保持在 source 中。
- Guard 要求 default 仍 fail-closed：NotEligible、paper-shadow window incomplete、LCBs/observation/
  divergence threshold 為 0、secret serialization false、sealed false。
- Guard 要求 accepted fixture 仍只允許 AdrDiscussionOnly，並保留 phase5 release packet、
  scorecard derivation/verdict/manifest、paper-shadow reconciliation、DQ manifest、statistical
  preregistration、QC/MIT/QA review hashes，paper-shadow window complete、positive LCBs、
  independent observation gate、divergence gate、labels/reviews passed、sealed=true。
- Guard 要求 contract/path/hash/stat/review gates 不得消失。
- Guard 要求 decision matrix 保持：AdrDiscussionOnly 可通過，TinyLiveAuthorized 必須回
  TinyLiveAuthorizationRequested，LiveAuthorized 必須回 LiveAuthorizationRequested，NotEligible
  必須回 DecisionNotAdrDiscussionOnly。
- Guard 要求 secret serialization denial 與 sealed requirement 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_tiny_live_eligibility_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_tiny_live_eligibility_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_tiny_live_eligibility_acceptance -- --nocapture`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：tiny-live/live authorization、IBKR contact、IBKR SDK import、secret
access/creation、connector runtime、socket/HTTP、read probe、result import、collector、
market-data ingestion、DQ writer、paper order/cancel/replace、broker fill import、scorecard
writer、DB apply、evidence writer/clock、Bybit gate lowering、GUI fanout、或任何 Bybit
behavior change。
