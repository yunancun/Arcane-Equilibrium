# Stock/ETF Paper Shadow Reconciliation Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；paper-shadow reconciliation boundary hardening

## 結論

已補強 `stock_etf_paper_shadow_reconciliation` 對 scope / AuthorityScope /
effect-capable posture 的 coverage。這次只改 acceptance 與 source-static guard，不改 Rust production
code、IPC method、runtime、IBKR connector、secret、DB/evidence writer 或 paper order route。

## 變更

- Rust acceptance 新增 `reconciliation_rejects_scope_authority_and_effect_cross_wire`。
- 證明 reconciliation scope 混入 `shadow_signal` 會被 `ScopeMismatch` 擋下，且不誤報 authority /
  effect blocker。
- 證明 authority 混入 `ShadowOnly` 會被 `AuthorityScopeMismatch` 擋下，且不誤報 scope /
  effect blocker。
- 證明 paper-write scope、`PaperRehearsal` scope 與 `effect_capable=true` 污染會同時產生 scope /
  authority / effect blockers。
- 證明 shadow-only scope / authority 污染會產生 scope / authority blockers，且不誤報 effect
  blocker。
- Python source-static guard 新增 cross-wire 禁止清單，拒絕 `PaperRehearsal`、`ShadowOnly`、
  `effect_capable=true`、paper-order scope 與 shadow-signal scope 混入 reconciliation source。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_paper_shadow_reconciliation_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_paper_shadow_reconciliation_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_paper_shadow_reconciliation_acceptance`：`6 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、fill import execution。
- 無 shadow fill generation、reconciliation writer、result import、DB/evidence writer、paper order route。
- 無 tiny-live/live authorization、Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
