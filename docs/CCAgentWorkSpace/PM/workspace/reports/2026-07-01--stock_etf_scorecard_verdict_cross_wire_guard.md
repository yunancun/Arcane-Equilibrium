# Stock/ETF Scorecard Verdict Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；scorecard verdict boundary hardening

## 結論

已補強 `stock_etf_scorecard_verdict` artifact 對 derived-only / paper-shadow separation / live-fill /
Bybit unchanged / writer-runtime authority posture 的 coverage。這次只改 acceptance 與 source-static
guard，不改 Rust production code、IPC method、runtime、IBKR connector、secret、DB/evidence writer 或
paper order route。

## 變更

- Rust acceptance 新增
  `scorecard_verdict_rejects_evidence_live_bybit_and_writer_cross_wire_independently`。
- 證明 `scorecard_is_derived_only=false` 只產生 `ScorecardNotDerivedOnly`。
- 證明 `paper_and_shadow_fills_separate=false` 只產生 `PaperShadowFillSeparationMissing`。
- 證明 `live_fill_claimed=true` 只產生 `LiveFillClaimed`。
- 證明 `bybit_live_execution_unchanged=false` 只產生 `BybitLiveExecutionNotProtected`。
- 證明 IBKR contact / connector runtime / broker fill import / scorecard writer / DB apply /
  evidence clock / secret serialization / tiny-live/live authority 污染會產生各自 blocker，且不誤報
  verdict evidence posture blockers。
- Python source-static guard 新增 fixture cross-wire 禁止清單，拒絕 live fill、IBKR contact、
  connector runtime、broker fill import、scorecard writer、DB apply、evidence clock、secret
  serialization、tiny-live/live authority 被 hardcoded 成 true，並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_scorecard_verdict_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_verdict_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_scorecard_verdict_acceptance`：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、scorecard writer execution。
- 無 DB/evidence writer、paper order route。
- 無 tiny-live/live authorization、Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
