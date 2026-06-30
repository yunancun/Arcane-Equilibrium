# Operator Brief - IBKR Stock/ETF Scorecard Verdict Contract

日期：2026-06-30
結論：新增 scorecard verdict source contract；不授權 runtime。

## 完成內容

- 新增 `stock_etf_scorecard_verdict_v1` Rust validator 與 default-blocked
  TOML template。
- Verdict labels 覆蓋：
  `engineering_ready`、`research_promising`、`profitability_feasible`、
  `insufficient_evidence`、`execution_model_invalid`、`kill`。
- Positive verdict 需要 formula appendix / statistical preregistration hashes、
  sample/window thresholds、paper-vs-shadow divergence、PSR/DSR-style
  thresholds、after-cost LCB、quality labels、QC/MIT/QA review hashes。
- Negative verdict 可被正式封存，不要求 positive profitability，避免 biased
  scorecard acceptance。
- Validator 明確拒絕 IBKR contact、connector runtime、broker fill import、
  scorecard writer、DB apply、evidence clock、secret serialization、
  tiny-live/live authority、Bybit regression。

## 驗證

- New scorecard verdict acceptance: `8 passed`
- Adjacent scorecard inputs / tiny-live / phase0 manifest: `12 + 7 + 6 passed`
- Full `openclaw_types`: `35` unit/golden + `206` integration/acceptance +
  `0` doc-tests passed
- `rustfmt --check` on new Rust files passed
- `git diff --check` passed

## 邊界

這不是 IBKR healthcheck，也不是 paper/live 啟動。Linux runtime 未 sync、未 restart、
未 fast-forward。

仍然沒有：

- IBKR contact / process startup
- secret read/create/serialization
- connector runtime / broker fill import / scorecard writer / DB apply
- evidence clock / GUI lane authority / paper order
- tiny-live / live
- Bybit live behavior change
