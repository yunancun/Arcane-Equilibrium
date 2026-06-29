STATUS: DONE_WITH_CONCERNS
VERDICT: CONDITIONAL|FINDINGS=7(C:1/H:4/M:2/L:0)

# FA 二輪功能覆蓋審計 — IBKR Stock/ETF Paper + Shadow Plan

日期：2026-06-29
角色：FA(default)
範圍：二輪對抗性 functional coverage / release-readiness audit；只審計文檔與既有報告，不改 runtime / code / TODO，不呼叫 IBKR / Bybit。
審計對象：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md` patched version。

## 總判斷

不能確認「無遺漏」；也不能確認「scheduled functionality 可在計劃工作後完整 go online」。patched plan 已把多個一輪 blocker 補進正文和第 11 節，但目前形式仍是 blocker register / design proposal，不是可直接交給 PA/E1 的 product workflow + acceptance packet。

可批准的是 Phase 0 ADR/spec packet。Phase 1+、IBKR API/session、secret slot、paper order rehearsal、GUI runtime enablement、6-8 週 evidence clock 仍應 blocked，直到下列 finding 被轉成可測試 acceptance。

## Findings

### C-01 — release-readiness 結論不能成立；計劃自己仍限定 Phase 0

Evidence:
- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:14`-`17` 明確說 Phase 1+、IBKR API、secret slot、paper order、GUI runtime enablement、evidence clock 都需先補 blocker。
- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:670`-`707` 將 Phase 1 前與 Phase 3/evidence clock 前條件列為 hard blocker，最後判定「有效性只限於 Phase 0」。
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:18`-`28` 明確不批准 Phase 1+、IBKR API、secret、paper order、GUI rollout、evidence clock。

Required resolution:
- PM 對 operator 回答必須改成：可進 Phase 0，不能確認 go-online readiness。
- Phase 0 產物必須是 accepted ADR/AMD + functional spec + acceptance matrix，而不是把第 11 節 blocker 原樣留給 E1。

### H-01 — operator workflow coverage 仍不完整：視圖欄位有了，操作流、disabled/error/recovery/export 不足

Evidence:
- plan 只列 Stock/ETF 視圖欄位：overview / universe / paper / shadow / risk / evidence，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:321`-`357`。
- weekly review / operator brief 只作為工作名詞出現，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:597`-`608`。
- 一輪 FA 已指出缺 market closed、delayed data、no subscription、connector down、paper account unavailable、stale scorecard、reconciliation unknown、divergence、corporate action pending、instrument blocked、live-disabled reason 等 view states，見 `docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_fa_review.md:107`-`117`。

Required resolution:
- Phase 0 spec 為每個 stock tab 增加 acceptance table：inputs、empty/loading/stale/error states、allowed actions、blocked actions、audit events、evidence links、export artifact。
- 補 operator workflows：lane login/status、universe freeze/change request、paper rehearsal review、shadow-only review、risk freeze、evidence export、weekly PM/QC/MIT review、paper-vs-shadow divergence quarantine、manual recovery/escalation。
- CFD / live disabled surface 必須有可測試原因碼與 no-write/no-secret/no-route negative tests。

### H-02 — IBKR API/session/paper-account 狀態仍未定義到可實作

Evidence:
- plan 把 exact IBKR API baseline、paper attestation、secret contract、API allowlist、flag matrix 列為 Phase 0 必補項，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:292`-`301`。
- 第 11 節仍要求 TWS API / IB Gateway / Client Portal Web API 三選一，並定義 runtime owner、host/port、session lifecycle、market data tier，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:680`-`685`。
- E3 指出缺 broker-reported paper-account attestation、secret exact contract、API allowlist、runtime/deploy topology，見 `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md:41`-`47`。

Required resolution:
- Phase 0 必須選定第一個 IBKR API/session baseline，或明確新增 no-order spike 並阻斷 connector implementation。
- 定義 paper account attestation：broker response、account fingerprint、host/port、environment、secret fingerprint 全部匹配後，才允許任何 paper-order intent construction。
- 定義 session states：not installed、gateway down、auth expired、paper verified、live detected、market-data delayed/no entitlement、maintenance、reconnect backoff、manual review。

### H-03 — evidence/data contract 仍不足以支撐可審計 after-cost scorecard

Evidence:
- plan 的 DB section 已要求 atomic facts、instrument identity、universe version、corporate actions、market-data provenance、FX/cash ledger、cost model、benchmark、paper/shadow reconciliation，但仍是要求清單，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:219`-`245`。
- plan 自己禁止 Phase 3 啟動，除非 vendor/tier、PIT universe、corporate action、FX/cost、benchmark、statistical validation design machine-checkable，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:551`-`557`。
- MIT 判定 DB plan 是 table names, not schema，且 market data tier、PIT universe、cost/tax/FX、benchmark、statistical design 都是 blocker，見 `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:18`-`29`、`:33`-`47`、`:80`-`96`、`:112`-`160`。

Required resolution:
- Phase 0/1 handoff 需要 DDL-level evidence contract：keys、constraints、lineage、hashes、append-only policy、source-of-truth ownership、migration guards。
- Scorecard 必須明確是 derived artifact；atomic facts 才是 evidence SSOT。
- `stock_etf_evidence_clock_v1` 必須包含 universe / benchmark / cost model / hypothesis / collector / data-quality hashes，以及 pause/reset/quarantine rules。

### H-04 — acceptance criteria 仍偏 prose，不能讓 E4/QA 逐 phase 直接驗收

Evidence:
- Phase 0 驗收只寫 ADR accepted、是否同步 memory/TODO、禁止 chat-only approval，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:497`-`503`。
- Phase 1-5 驗收多為「tests pass」「可重建」「scorecard row 可追溯」「crypto tabs 不回歸」「6-8 週完整報告」等結果描述，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:523`-`528`、`:544`-`550`、`:568`-`573`、`:590`-`595`、`:610`-`615`。
- 首批 acceptance criteria 是全局 bullet list，未分解為測試、fixture、artifact schema、negative cases，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:638`-`651`。

Required resolution:
- 增加 per-phase acceptance matrix：precondition、test command / fixture、expected artifact path/schema、negative cases、owner、handoff gate。
- 每個 effect-capable surface 必須有 fail-closed tests：lane disabled、broker disabled、live reserved、missing/mismatched auth、secret missing/live material present、Python write path attempted、unknown instrument、market closed、cost model missing。
- GUI slice 必須包含 screenshot/smoke + route contract tests + disabled state tests，而不只 `node --check`。

### H-05 — crypto/Bybit unchanged regression acceptance 不足

Evidence:
- plan 說 `crypto_perp` 保持現有 Bybit governance，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:61`。
- plan 只在 GUI Phase 4 驗收列「crypto tabs 行為不回歸」，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:590`-`595`。
- first-round FA 已指出沒有 acceptance criteria 證明 Bybit Demo/LiveDemo/Live surfaces 仍走原 Rust authority、risk config、Decision Lease display、scorecard semantics，見 `docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_fa_review.md:189`-`200`。

Required resolution:
- 加入 explicit crypto regression suite：default lane remains `crypto_perp`；existing Bybit routes/tabs/auth/risk/Decision Lease/scorecard behavior unchanged；stock lane disabled 時 Bybit baseline 全可用。
- 加入 instrument identity collision tests：Bybit `Symbol` 不可與 stock ticker / `EquityInstrumentId` 混 join、混 cache、混 scorecard。

### M-01 — operator decision checklist 仍不足以支撐 Phase 0 handoff

Evidence:
- plan 的開工前 operator decisions 只有五項：是否接受方向、是否 IBKR baseline、是否啟動 ADR 評審、eToro/Saxo 是否 challenger、是否接受工期，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:660`-`668`。
- first-round FA 已列出缺 API surface、paper jurisdiction/account id、market data subscription、universe owner、benchmark owner、base currency、data cost、risk/loss caps、shadow-only lift criteria、paper-order allowance、weekly format 等決策，見 `docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_fa_review.md:178`-`187`。

Required resolution:
- Phase 0 ADR/spec 增加 decision matrix：decision、default conservative answer、who decides、artifact where recorded、what phases it gates、revisit condition。
- 在所有 product decisions 完成前，不應把工作標成 PA/E1 implementation-ready。

### M-02 — legacy Paper / broker-paper / shadow 術語仍需更硬隔離

Evidence:
- repo 已接受舊 Paper pipeline archived，且不是 promotion evidence，見 `docs/adr/0003-paper-pipeline-disabled-by-default.md:16`-`20`。
- plan 說 `demo` tab 要把 crypto demo 與 stock paper 分開，見 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:362`-`366`。
- PA 指出 IBKR paper 必須命名為 broker-paper/rehearsal evidence，不是重啟 legacy Paper promotion lane，見 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_pa_review.md:167`-`169`。

Required resolution:
- UI / schema / reports 用 `broker_paper_rehearsal` 或等價術語，不用會與 legacy `paper` promotion lane 混淆的裸 `paper`。
- 所有 scorecard 和 export artifact 必須標 `broker_paper` vs `synthetic_shadow`，並帶 proof-exclusion labels：不能自動升級到 IBKR live、Bybit live、或現有 promotion gates。

## Review Questions Direct Answers

1. Operator workflows: not complete. Login lane、status、universe、paper、shadow、risk、evidence、disabled CFD/live 有方向；export、weekly review checklist、error recovery、view-level states、operator actions 未成 acceptance-ready。
2. API/session/data states: not complete. Plan lists what must exist, but API baseline、session lifecycle、paper attestation、market-data tier、corporate actions、FX/cost、benchmark、evidence-clock reset/pause states still need contracts.
3. Acceptance criteria: partially testable, mostly prose. It needs per-phase artifact/test/negative-case matrix before PA/E1 handoff.
4. Crypto/Bybit unchanged regression: insufficient. There is one GUI bullet, but no route/API/Rust authority/risk/Decision Lease regression suite.
5. Phase 0 handoff: add accepted ADR/AMD, expanded operator decision matrix, API/session baseline, paper lifecycle state machine, DB/evidence DDL contract, feature flag + secret invariant matrix, GUI workflow acceptance tables, crypto regression suite, and evidence-clock manifest schema.

PM-facing gate decision: APPROVE_PHASE0_ONLY
