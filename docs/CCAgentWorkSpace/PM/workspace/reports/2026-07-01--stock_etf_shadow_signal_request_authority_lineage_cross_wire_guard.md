# Stock/ETF Shadow Signal Request Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；shadow signal request authority / lineage hardening

## 結論

已補強 `stock_etf_shadow_signal_request` 的 lane/broker/environment/method/operation/authority、
evidence-clock/PIT-universe/strategy/instrument/market-data/cost/event/source lineage 與 no-side-effect
boundary coverage。這次只改 acceptance 與 source-static guard，不改 Rust production validator、IPC method、
runtime、IBKR connector、secret、DB/evidence writer、shadow collector 或 paper order route。

## 變更

- Rust acceptance 新增 `shadow_signal_request_rejects_each_authority_gap_independently`。
- Rust acceptance 新增 `shadow_signal_request_rejects_each_lineage_gap_independently`。
- Rust acceptance 新增 `shadow_signal_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 contract/source/lane/broker/environment/method/operation/authority/effect gaps 可獨立
  產生精確 blocker。
- Acceptance 證明 request/evaluation/signal ids、evidence clock、PIT universe、strategy hypothesis、
  instrument identity、market-data provenance、cost model、asset-lane event 與 source artifact lineage gaps
  可獨立阻斷。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、shadow signal emission、shadow fill
  generation、scorecard writer、DB apply、order route、Bybit path reuse、live/tiny-live、margin/short/options/
  CFD、Python direct broker write flags 可獨立阻斷。
- Python source-static guard 新增 `Default` / `accepted_fixture` block parsers，直接鎖住 accepted fixture
  不可硬編 crypto/Bybit/paper/read-only/live/wrong method/wrong operation/effectful/empty-lineage/runtime/
  secret/order posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_shadow_signal_request_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_shadow_signal_request_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_shadow_signal_request_acceptance`：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 shadow signal emission、shadow fill generation、shadow collector、DB/evidence writer、scorecard writer、
  paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
