# Stock/ETF Phase3 Frozen Inputs Readiness Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase3 frozen-input readiness hardening

## 結論

已補強 `StockEtfFrozenEvidenceInputsV1` artifact 對 frozen source hash、corporate-action/FX/fee
as-of、paper-shadow divergence threshold、GUI evidence view readiness、daily scorecard regeneration
readiness posture 的 coverage。這次只改 acceptance 與 source-static guard，不改 Rust production code、
IPC method、runtime、IBKR connector、secret、DB/evidence writer、scorecard writer、paper order route
或 tiny-live/live authority。

## 變更

- Rust acceptance 新增
  `frozen_inputs_reject_source_readiness_cross_wire_independently`。
- 證明 `universe_hash`、`benchmark_hash`、`cost_model_hash`、`strategy_hypothesis_hash`、
  `reference_data_sources_contract_hash`、`paper_shadow_divergence_threshold_hash` 缺失時，都只產生
  單一對應 blocker。
- 證明 `corporate_action_fx_fee_asof_ms=0` 只產生 `CorporateActionFxFeeAsOfMissing`。
- 證明 `gui_evidence_view_available=false` 只產生 `GuiEvidenceViewMissing`。
- 證明 `daily_scorecard_regeneration_passed=false` 只產生 `ScorecardRegenerationMissing`。
- Python source-static guard 新增 frozen-input `source_fixture()` body parser，拒絕 missing hash、
  zero as-of、missing GUI evidence view、missing scorecard regeneration 被 hardcoded 到 source fixture，
  並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_phase3_evidence_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_phase3_evidence_source_static.py --tb=short`：`15 passed`。
- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance`：`24 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 market-data ingestion、evidence writer、scorecard writer、DB/evidence writer、paper order route、
  tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
