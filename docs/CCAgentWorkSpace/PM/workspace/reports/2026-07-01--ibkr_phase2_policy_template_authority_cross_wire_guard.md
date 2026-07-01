# IBKR Phase2 Policy Template Authority Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase 2 policy template authority hardening

## 結論

已補強 `ibkr_phase2_policies` 的 redaction、rate-limit、audit-event、paper-attestation、
Python write-guard source templates。這次只新增 acceptance 與 source-static guard，不改 Rust
production code、IPC method、runtime、IBKR connector、secret lookup、redaction writer、rate limiter、
audit writer、broker routing、paper order route 或 tiny-live/live authority。

## 變更

- Rust acceptance 新增 redaction exact-blocker cases：missing payload hashes、account/secret/path/
  cookie/token/raw-payload/stack-trace log leaks 都必須 fail closed。
- 新增 rate-limit exact-blocker cases：non-per-action scope、missing spacing/concurrency/per-action
  buckets/pacing circuit breaker/read budget/market-data budget/paper-write budget 都必須 fail closed。
- 新增 audit-event exact-blocker cases：append-only、lane/broker/environment/operation、allow/deny reason、
  source/raw/redacted hashes、account-fingerprint-only、raw-payload-storage posture 都不可漏開。
- 新增 paper-attestation / Python write-guard exact-blocker cases：Phase 2 gate、session、Rust IPC、
  scoped authorization、Decision Lease、Guardian、risk/instrument/idempotency/lifecycle/reconciliation、
  paper-only、live/margin denial、max notional、Python no-write/no-secret/GUI no-override/Bybit unchanged
  posture 都不可漏開。
- Python source-static guard 新增 source-template/default block parser，鎖住 source template 安全 posture
  與 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/ibkr_phase2_policy_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_policies_source_static.py --tb=short`：`4 passed`。
- `cargo test -p openclaw_types --test ibkr_phase2_policy_acceptance`：`13 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 redaction runtime、rate-limit runtime、audit writer、broker routing、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
