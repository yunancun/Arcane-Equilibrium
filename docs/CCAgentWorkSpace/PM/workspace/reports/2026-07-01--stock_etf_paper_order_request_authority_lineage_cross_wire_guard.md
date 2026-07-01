# Stock/ETF Paper Order Request Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；paper order request authority / lineage hardening

## 結論

已補強 `stock_etf_paper_order_request` 的 common surface、method/operation/authority/effect matrix、
preview hash/order-intent gates、effect lifecycle lineage、submit/cancel/replace shape gates 與 no-side-effect
boundary flags。這次只改 acceptance 與 source-static guard，不改 Rust production validator、IPC method、
runtime、IBKR connector、secret、DB/evidence writer、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 新增 `paper_order_request_rejects_each_common_surface_gap_independently`。
- Rust acceptance 新增 `paper_order_request_rejects_each_method_authority_and_effect_gap_independently`。
- Rust acceptance 新增 `paper_order_request_rejects_each_preview_hash_and_order_intent_gap_independently`。
- Rust acceptance 新增 `paper_order_request_rejects_each_effect_lifecycle_and_submit_gap_independently`。
- Rust acceptance 新增 `paper_order_request_rejects_each_cancel_and_replace_gap_independently`。
- Rust acceptance 新增 `paper_order_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 contract/source/lane/broker/environment/request method/request id/account hash gaps 可獨立
  阻斷；`LiveReservedDenied` environment 維持 `LiveEnvironmentDenied + EnvironmentNotPaper` 雙重阻斷。
- Acceptance 證明 preview/submit/cancel/replace method surface 的 operation、authority scope、effect flag
  drift 可各自只產生單一對應 blocker。
- Acceptance 證明 preview hash lineage、symbol/instrument/side/order type/quantity/limit policy/TIF gates 可
  獨立阻斷；invalid limit price 維持 policy+price 雙重阻斷。
- Acceptance 證明 effect lifecycle hashes、decision lease、audit id、local/idempotency ids、submit broker-order
  pollution、cancel/replace shape pollution、replacement fields 與 boundary flags 可獨立阻斷。
- Python source-static guard 新增 `fixtures.rs` coverage 與 fixture/default block parsers，鎖住 accepted
  preview/submit/cancel/replace fixtures 的 StockEtfCash/IBKR/Paper 分離、no-runtime、no-secret、no-Bybit
  posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_paper_order_request_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_paper_order_request_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_paper_order_request_acceptance`：`17 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、cancel/replace routing、DB/evidence writer、scorecard writer、broker session、
  tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
