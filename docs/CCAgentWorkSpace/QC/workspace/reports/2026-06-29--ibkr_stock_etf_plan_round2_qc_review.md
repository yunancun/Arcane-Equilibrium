STATUS: DONE_WITH_CONCERNS
VERDICT: CONDITIONAL|FINDINGS=6(C:0/H:3/M:3/L:0)

# 第二輪 QC 量化/盈利可行性審查 — IBKR Stock/ETF Paper + Shadow patched plan

日期：2026-06-29
角色：QC(default)
範圍：對 patched `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md` 做第二輪 adversarial quant audit。
邊界：report-only；未改 runtime/code/TODO，未觸碰 Linux `trade-core`、PG、service、secret，未呼叫 IBKR/Bybit。

## 總結

patched plan 已經修掉第一輪最大誤讀：它把 6-8 週明確降級為 `engineering shakedown + preliminary feasibility screen`，並明說低頻樣本不足時不能輸出 durable-alpha proof（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:471-473`）。它也把 universe、benchmark、cost model、strategy hypothesis、paper-vs-shadow divergence、sample-size 和 ADR-0047 label 放入 evidence-clock 前置 blocker（同檔 `:373-388`, `:696-705`）。

但第二輪 QC 仍不批准 Phase 1 或 evidence clock。現在的方案能支持 Phase 0 ADR/spec，把盈利驗證框架寫清楚；它不能支持「功能 fully online」或「方法有效」的結論。6-8 週最多可產生 preliminary screen；任何 positive 但 underpowered 的結果都必須被 PM 寫成 `research_promising` 或 `insufficient_evidence`，不得變成 tiny-live 候選敘事。

## Findings

### H-1 — `profitability_feasible` 與 tiny-live wording 仍可能把 preliminary screen 誤讀成 live ADR 候選

Evidence:
- patched plan 已正確說 6-8 週只能作 shakedown / preliminary feasibility screen，不能輸出 durable-alpha proof（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:471-473`）。
- 但 Phase 5 仍以「判斷 IBKR stock/ETF lane 是否存在 after-cost edge」為目標，並在 6-8 週後要求「明確判斷是否有繼續 tiny-live 探索價值」（同檔 `:597-615`, `:653-658`）。
- repo profit proof 要求 candidate-matched orders/fills、actual fees/slippage、matched controls、execution realism、proof-exclusion pass、repeat/OOS path；Paper/replay/single-window positives 永遠不是 proof（`docs/agents/profit-first-autonomy-loop.md:132-144`）。

Required resolution:
- Phase 0 必須新增 `tiny_live_adr_eligibility_v1`，與 Phase 5 scorecard 分離。
- 只有在 all pre-registered gates pass、保守成本下 after-cost benchmark excess 的 lower confidence bound > 0、paper-vs-shadow 未隔離、無 beta/regime/concentration veto，且有 repeat/OOS 或同一資料契約的 PIT historical cross-regime 補證後，PM 才能寫「可討論 tiny-live ADR」。
- 若只是 6-8 週 positive point estimate 或 single-regime positive，PM wording 必須是 `research_promising` / `needs_more_data` / `insufficient_evidence`，不得寫 `go-live candidate`。

### H-2 — independent sample / power gate 已被命名，但還沒有可審核的數值門檻

Evidence:
- plan 要求 independent observation count，且說原始 100+ trade rows 不等於 100+ independent observations（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:444`, `:458-460`）。
- Phase 3 / evidence clock blocker 也要求 pre-registered sample-size / independent observation rules（同檔 `:696-705`）。
- 第一輪 QC/MIT 已指出 6-8 週對 daily/weekly momentum、sector rotation、ETF trend/risk-off 等策略通常 underpowered，bootstrap 不能創造獨立資訊（`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_qc_review.md:48-55`; `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:226-237`）。

Required resolution:
- 每個 hypothesis 必須在 evidence clock 前定義 `n_independent_min`、block unit、cluster rule、最小 calendar span、最小 event/week count、effect size / MDE、K count、DSR deflation universe。
- 同日多 symbol、同 sector、同 event week 的 rows 必須 cluster；不能 iid 計數。
- 未達 pre-registered power threshold 時，唯一允許的 profitability verdict 是 `insufficient_evidence` 或 `research_promising`，不是 PM go/no-go。

### H-3 — cost wall 已進入 scorecard，但缺少數值 veto，仍可製造 false after-cost positivity

Evidence:
- plan 要求 commission、spread、slippage、FX、tax placeholder、net expectancy、cost-edge ratio 等 scorecard 欄位（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:426-449`）。
- promotion-like 條件說成本吃掉 gross edge 主要部分時不能 positive，但沒有定義「主要部分」或 conservative/punitive cost 數值門檻（同檔 `:452-455`）。
- MIT 已把 fee/slippage/FX/FTT/tax model versioning 判為 Phase 3 blocker，要求 immutable cost model、component table、estimated vs realized cost 分離，且 known tax/fee path 不能只有 placeholder（`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:112-127`）。

Required resolution:
- Phase 0/3 前必須凍結 scorecard formula appendix：base / conservative / punitive cost、spread/slippage/adverse-selection、FX、tax/FTT、realized commission report、source as-of。
- 建議預設 `cost_edge_ratio <= 0.5` 作 promotion-like 強 gate；若 PM 選其他值，必須 pre-register 並解釋。
- conservative 或 punitive cost 任一把 net expectancy / benchmark excess 翻負，verdict 不得為 positive。
- `FTT/tax placeholder` 要改成 fail-closed component；未知成本不得默認 0。

### M-1 — paper-vs-shadow divergence 有 blocker 位置，但缺少最小 quarantine math

Evidence:
- plan 已要求 evidence clock 前 frozen paper-vs-shadow divergence thresholds，scorecard 每日記錄 divergence，Phase 3 blocker 要 thresholds and quarantine action（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:387`, `:443`, `:702`）。
- 第一輪 QC 指出 paper 與 shadow 不能 pooled；若 disagreement material，verdict 應是 `execution_model_invalid`，不是取較好結果（`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_qc_review.md:108-120`）。

Required resolution:
- pre-registration 必須至少定義 fill-rate ratio band、median/tail slippage band、timing lag band、partial/unfilled/cancel bucket、commission/FX/tax mismatch bucket。
- 若 divergence band breach，該 strategy/hypothesis 當期結果自動 quarantine，最多輸出 `execution_model_invalid` 或 `insufficient_evidence`。
- paper row、shadow row、broker paper fill、synthetic fill 必須永遠分表/分標記，不能用 pooled PnL 修飾 profitability。

### M-2 — universe / benchmark / regime labels 方向足夠，但必須變成 non-null machine gate

Evidence:
- plan 已把初始 universe 收斂為 `US_LARGE_100_v1` 與 sector/liquid ETF cohort，並把 UCITS 放到第二批或要求 source contract（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:389-397`）。
- plan 要求 frozen universe/benchmark/cost/hypothesis hash、strategy-specific benchmark/matched controls、ADR-0047 labels（同檔 `:699-704`）。
- ADR-0047 要求每個 candidate evidence matrix 至少包含 regime、breadth、freshness、survivorship、execution realism、statistical gates（`docs/adr/0047-alpha-edge-regime-evidence-governance.md:42-52`）。

Required resolution:
- `stock_etf_evidence_clock_v1` manifest 必須把上述欄位做成 machine-checkable non-null gate；任何 unknown / stale / not-applicable 未解釋欄位都應 block clock 或把 verdict 降為 `insufficient_evidence`。
- Benchmark 要鎖定 total-return vs price-return、currency、calendar、rebalance、source vendor；不能只有 benchmark name。
- Regime classifier thresholds 必須先於 alpha scoring 固定；positive 但單一 bull/risk-on regime 結果只能是 `regime-bet / learning-only`。

### M-3 — schedule 可支持工程就緒估算，不支持盈利可行性承諾

Evidence:
- plan 估算工程前置中位 4-5 週、悲觀 6-8 週，evidence collection 另算 6-8 週且只在 Phase 3/4 穩定後開始（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:617-636`）。
- 同一 plan 又明確說 Phase 1+、IBKR API、secret slot、paper order、GUI runtime activation、evidence clock 全部 blocked，唯一可立即前進是 Phase 0（同檔 `:670-678`）。
- PM integration 也只批准 Phase 0，明確不批准 Phase 1+、IBKR API、secret slot、paper rehearsal、GUI rollout、evidence clock 或 tiny-live（`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:12-27`, `:120-128`）。

Required resolution:
- PM 對 operator 的排期必須分三層寫：Phase 0 governance/spec、Phase 1-4 engineering readiness、Phase 5 preliminary evidence screen。
- 不應說「排期後 required functionality can fully go online」。準確說法是：若 Phase 0 通過且後續 blocker 逐項解，工程上可逐步到 paper/shadow collection；盈利有效性仍需 empirical evidence 且很可能超過 6-8 週。
- 任何 positive 但 underpowered 結果都不得創建產品債：不得開 live UI promise、不得加入 TODO live ladder、不得把 `profitability_feasible` 當 roadmap commitment。

## Review questions direct answers

1. 是否防止 6-8 週 shakedown 被誤讀為 durable alpha proof？
   大幅改善，但不完全。`engineering shakedown + preliminary feasibility screen` wording 是正確的；剩餘風險在 `profitability_feasible` 與 tiny-live discussion wording，需要 H-1 的分離 gate。

2. universe、benchmark、cost wall、sample-size、independent observation、paper-vs-shadow divergence、regime labels、verdict labels 是否 sufficient？
   作為 Phase 0 blocker 清單，方向 sufficient；作為可以啟動 clock 的規格，仍 insufficient。最弱的是 cost wall 數值 veto、sample/power calibration、paper-vs-shadow quarantine math、benchmark/label 的 machine non-null enforcement。

3. future tiny-live ADR 前還需要哪些 gate？
   需要 `tiny_live_adr_eligibility_v1`：all pre-registered Phase 5 gates pass、保守成本下 LCB > 0、matched benchmark alpha positive、PSR/DSR/deflation pass、n_independent pass、paper-shadow divergence pass、無 concentration/regime veto、repeat/OOS 或同資料契約 PIT cross-regime 補證、且 CC/E3/BB 對 broker live boundary 另行審查。

4. schedule realistic for profitability feasibility, or only engineering readiness？
   只對 engineering readiness / preliminary evidence screen 有參考價值。盈利可行性取決於 realized independent sample、regime breadth、paper-shadow validity、cost wall 和 OOS/repeat path；不能由 4-5 週工程 + 6-8 週 clock 自動得出。

5. PM go/no-go wording 應如何避免 product debt？
   建議用：`APPROVE_PHASE0_ONLY`; `NO_PHASE1_UNTIL_ADR_AND_SPEC_GATES`; `PHASE5_POSITIVE_UNDERPOWERED = RESEARCH_PROMISING/INSUFFICIENT_EVIDENCE`; `PAPER/SHADOW_GO_ONLY_OPENS_SEPARATE_TINY_LIVE_ADR_DISCUSSION, NOT LIVE READINESS`。

PM-facing gate decision: APPROVE_PHASE0_ONLY
