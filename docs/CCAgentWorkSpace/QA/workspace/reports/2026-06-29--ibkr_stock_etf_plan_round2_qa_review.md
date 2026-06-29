STATUS: DONE_WITH_CONCERNS
VERDICT: CONDITIONAL|FINDINGS=8(C:1/H:4/M:3/L:0)

# QA 二輪 release-readiness 審計 — IBKR Stock/ETF Paper + Shadow patched plan

日期：2026-06-29
角色：QA(worker)
範圍：release readiness、端到端 acceptance、sign-off gates。Report-only；未改 runtime/code/TODO，未呼叫 IBKR/Bybit，未觸碰 Linux `trade-core`、PG、services、secrets 或 network。

## 總判定

QA 不能確認「按排程後 scheduled functionality 可 fully go online 且無遺漏」。patched plan 已把第一輪主要 blocker 收斂進正文與第 11 節，但它仍是 Phase 0 ADR/spec packet，不是可簽核的 Phase 1+ implementation / paper-shadow launch / evidence-clock release package。

可批准：Phase 0 ADR/spec packet。
不可批准：Phase 1+ code implementation、IBKR read-only healthcheck、secret slot、fill import、paper order rehearsal、GUI runtime activation、6-8 週 evidence clock、任何 live/tiny-live。

## Findings

### C-01 — 當前 acceptance criteria 不能支撐 release sign-off，只能支撐 Phase 0

證據：
- plan 開頭明確說第一輪對抗審查只批准 Phase 0 ADR/spec；Phase 1+、IBKR API、secret slot、paper order rehearsal、GUI runtime enablement、evidence clock 都需先補 blocker：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:14-17`。
- §11 共識寫明唯一可立即前進的是 Phase 0，Phase 1+ / IBKR API / secret slot / paper order / GUI runtime / evidence clock 均 BLOCKED，且 PM 判定有效性只限 Phase 0：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:670-707`。
- PM integration 不批准 Phase 1+、IBKR API、secret、paper order、GUI rollout、evidence clock 或 any IBKR live/tiny-live：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:18-28`。
- FA round2 同樣判定 release-readiness 結論不能成立，PM 對 operator 應回答可進 Phase 0、不能確認 go-online readiness：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_fa_review.md:19-29`。

Required resolution：
- Phase 0 產物必須升級為 accepted ADR/AMD + functional/technical/security/data/evidence acceptance matrix。
- PM/operator 摘要不得使用「完整上線」「fully online」「live ready」措辭；只能說 Phase 0 可開。

### H-01 — 缺 per-phase E2/E4/QA gate matrix，後續角色無法直接驗收

證據：
- Phase 1-5 驗收仍多為結果描述，例如 tests pass、可重建、scorecard row 可追溯、GUI screenshot、6-8 週報告：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:523-528`、`:544-550`、`:568-573`、`:590-595`、`:610-615`。
- 首批 acceptance criteria 是全局 bullet list，未拆成 test command、fixture、artifact schema、negative cases、owner、handoff gate：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:638-651`。
- FA round2 要求 per-phase acceptance matrix，並指出當前 criteria mostly prose：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_fa_review.md:66-77`。
- PA round2 指出 Phase 0/Phase 1 邊界仍自相矛盾，E1 會被迫發明 Interface：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_pa_review.md:20-30`。

Required resolution：
- Phase 0 前置 packet 必須列出每 phase 的 E2 adversarial review、E4 regression/test execution、QA acceptance gate。
- 每個 gate 必須有 precondition、命令/fixture、expected artifact path/schema、negative cases、owner、report path、block/unblock rule。

### H-02 — Rust types/IPC、Python no-write、DB migration、GUI、evidence、安全、kill switch、crypto regression 測試面仍未明確

證據：
- Rust lane-scoped IPC/order lifecycle 只是計劃項，且禁止復用既有 `submit_paper_order`，但 request/response schema 尚未列出：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:143-146`、`:162-171`。
- Python connector no-write 只列負面約束和 static tests 需求，還不是具體 AST/route/allowlist suite：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:212-217`；E3 round2 指出 obvious method-name grep 不足，generic writer 也要阻斷：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_e3_review.md:69-85`。
- DB schema 仍是 table/requirement list，缺 DDL-level packet、migration guards、indexes、retention：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_mit_review.md:19-32`。
- GUI Phase 4 仍偏 `node --check`/screenshot，不足以證明 route/cache/auth negative behavior：`docs/CCAgentWorkSpace/CC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_cc_review.md:69-79`。
- crypto non-regression 只有「crypto tabs 不回歸」一條，FA round2 要求 Bybit routes/tabs/auth/risk/Decision Lease/scorecard baseline：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_fa_review.md:78-88`。

Required resolution：
- Phase 0 packet 必須納入 named test surfaces：`lane_scoped_ipc_v1` contract tests、Rust deny tests、Python no-write AST/grep/route tests、Linux PG dry-run/double-apply plan、GUI route/cache/auth tests + screenshots、evidence DQ checker tests、redaction fixtures、kill-switch/degraded-mode tests、crypto regression suite。

### H-03 — rollout/rollback/disable procedures 不足；failed evidence-clock days 沒有可執行處置

證據：
- plan 只說若無 after-cost edge 則關閉或降級 stock/ETF lane，未列 disable/cleanup/runbook：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:653-658`。
- PA round2 要求 `stock_etf_disable_cleanup_runbook_v1`，包含 no-stock state、live slot absent/empty、evidence archival、GUI surface shutdown、DB forward-only retention：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_pa_review.md:104-115`。
- E3 round2 要求 broker process topology、degraded states、kill switch，且 kill switch 高於普通 feature flag：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_e3_review.md:52-68`。
- MIT round2 指出 evidence-clock 沒有 deterministic day-count algorithm、coverage threshold、pause/reset/quarantine action：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_mit_review.md:103-115`。

Required resolution：
- 每 phase 必須有 disable/rollback posture：Phase 1 forward-only schema/cleanup policy；Phase 2 connector/secret/session disable；Phase 3 failed day PASS/FAIL/QUARANTINED + pause/reset；Phase 4 GUI cache/route rollback；Phase 5 evidence archival/kill/degrade。
- 缺 runbook 時 QA gate 一律 BLOCK。

### H-04 — release artifacts / manifests / command outputs / report locations 尚不足以審計

證據：
- plan 要求 `stock_etf_evidence_clock_v1` manifest 和若干 frozen hashes，但沒有 manifest schema、checker output、command output、artifact storage convention：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:373-388`、`:696-705`。
- E3 round2 要求 gate artifacts 必須是 immutable report/artifact files with hashes，不靠 chat approval：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_e3_review.md:117-130`。
- MIT round2 要求 atomic facts/hash-chain 或 immutable artifact refs，scorecard 不能成為唯一證據源：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_mit_review.md:33-46`。

Required resolution：
- 定義 release packet layout：ADR/spec paths、role reports、E2/E4/QA report paths、manifest JSON schemas、hash list、command transcript paths、screenshots、redaction fixture outputs、PG dry-run logs、GUI screenshots、daily DQ manifests、final scorecard regeneration output。
- QA 不接受「report says pass」作為 artifact；必須能由 manifest hash 反查原始 evidence。

### M-01 — Phase 3 / Phase 5 evidence gate 已改善，但 profitability / tiny-live wording 仍可能造成產品債

證據：
- patched plan 已把 6-8 週降級為 engineering shakedown + preliminary feasibility screen，低頻樣本不足不得輸出 durable-alpha proof：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:471-473`。
- 但 Phase 5 仍寫「判斷 IBKR stock/ETF lane 是否存在 after-cost edge」和「是否有繼續 tiny-live 探索價值」：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:597-615`、`:653-658`。
- QC round2 要求 `tiny_live_adr_eligibility_v1` 與 Phase 5 scorecard 分離，positive point estimate 不得寫成 go-live candidate：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_qc_review.md:19-30`。

Required resolution：
- Evidence report verdict labels 必須 machine-checkable：`engineering_ready`、`research_promising`、`profitability_feasible`、`insufficient_evidence`、`execution_model_invalid`、`kill`。
- `profitability_feasible` 不得觸發 live/tiny-live；最多觸發 separate ADR discussion，且需 independent sample、benchmark LCB、PSR/DSR、cost stress、paper-shadow divergence、regime/concentration gates 全 PASS。

### M-02 — Operator workflow / GUI acceptance 還缺 disabled/error/recovery/export 和 weekly review 閉環

證據：
- stock views 列出了欄位，但不是 operator-grade states/workflows：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:321-357`。
- FA round2 要求每個 stock tab 增加 inputs、empty/loading/stale/error states、allowed/blocked actions、audit events、evidence links、export artifact，並補 weekly review/recovery/quarantine workflows：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_fa_review.md:30-41`。
- PA round2 指出 login selector 與 badge/readiness-first 時序衝突：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_pa_review.md:92-103`。

Required resolution：
- Phase 4A 只應做 default `crypto_perp` badge/readiness + stock read-only status page。
- 完整 selector 必須等 backend contract、auth/flag matrix、route/cache partition、disabled-lane tests 全 PASS 後再開。

### M-03 — Security/redaction/API/session gate 必須前移到首次 healthcheck 前

證據：
- plan 把 exact IBKR API baseline、paper attestation、secret contract、non-Bybit API allowlist、feature flag matrix 列為 Phase 0 必補：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:292-301`。
- E3 round2 明確列出首次 IBKR read-only healthcheck 前 mandatory gates：accepted ADR/AMD、chosen API baseline/topology、read-only secret slot contract、API allowlist、redaction regression、rate limits、audit event：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_e3_review.md:132-147`。

Required resolution：
- Read-only healthcheck 也算非 Bybit external contact；缺任一 E3 gate 時 BLOCK，不得先用 healthcheck 當探索。
- Secret/session/redaction 合約需覆蓋 TWS / IB Gateway / Client Portal 的 credentials、cookies、client id、logs、2FA/session renewal、account id masking。

## 逐 phase 缺失 gate

| Phase | E2 gate 缺口 | E4 gate 缺口 | QA gate 缺口 |
|---|---|---|---|
| Phase 0 ADR/spec | 需要 E2/CC/FA/PA/E3/QC/MIT 對 accepted ADR/spec packet 做二輪 closeout；現在只有 blocker register。 | 不適用 code run，但需 schema/test-manifest lint 或 docs consistency check。 | accepted ADR/AMD、operator decision matrix、source-of-truth sync check、per-phase acceptance matrix、no Phase 1 authority statement。 |
| Phase 1 type/config/schema/IPC | E2 review `AssetLane/Broker/Environment`、no catch-all、`lane_scoped_ipc_v1`、deny reasons、no legacy IPC reuse。 | Rust focused tests、Python parser tests、static deny tests、DDL packet review、Linux PG dry-run/double-apply only if migration apply is in scope。 | no runtime mutation proof、default-off manifest、crypto baseline unchanged、artifact hash manifest。 |
| Phase 2 IBKR readonly/fill/paper rehearsal | E2/E3 review `phase2_ibkr_external_surface_gate_v1`、API allowlist、paper attestation、Rust order lifecycle。 | Redaction fixtures、Python no-write AST/route tests、idempotent fill import tests、order lifecycle fixture tests。 | First healthcheck gate, first fill-import gate, first paper-order-rehearsal gate; each with immutable manifest and no live/tiny-live authority. |
| Phase 3 shadow collector/scorecard | E2/MIT/QC review DDL/DQ/evidence-clock specs and statistical preregistration. | Collector fixture tests、DQ checker tests、scorecard deterministic regeneration、paper/shadow quarantine tests。 | `stock_etf_evidence_clock_v1` PASS after 5 trading days, day-count/quarantine manifest, no profitability claim beyond preregistered labels。 |
| Phase 4 GUI | E2 review lane display/filter-only, route/cache/auth partition, disabled lane semantics。 | `node --check` plus route contract tests, Playwright/screenshot desktop+mobile, JS regression, crypto route smoke。 | GUI E2E: client lane state untrusted, stock live denied, CFD disabled no-write, crypto tabs unchanged, evidence links/export visible。 |
| Phase 5 evidence window | E2/QC/MIT review post-window proof packet and wording. | Regenerate scorecard from atomic facts, hash verification, DQ day inclusion checker replay。 | QA final evidence audit: artifact completeness, independent sample and cost/stat gates, paper-vs-shadow quarantine, PM go/no-go wording; live/tiny-live excluded。 |

## 最小 QA launch checklist（`stock_etf_cash` paper/shadow only；排除 live/tiny-live）

1. Accepted ADR/AMD：只批准 `stock_etf_cash` read-only / broker-paper rehearsal / shadow research；明確禁止 live、tiny-live、margin、short、options、CFD、transfer。
2. Phase 0 spec packet 已接受：`broker_capability_registry_v1`、`lane_scoped_ipc_v1`、`ibkr_paper_order_lifecycle_v1`、`stock_etf_db_evidence_ddl_v1`、`feature_flag_secret_auth_matrix_v1`、`gui_lane_contract_v1`、`stock_etf_evidence_clock_v1`、disable/cleanup runbook。
3. Source-of-truth sync：ADR / README / CLAUDE / `.codex/MEMORY.md` / TODO 的變更或不變更理由已由 PM 記錄；無 chat-only approval。
4. All flags default OFF；`crypto_perp` 仍是 default；stock lane disabled 時 Bybit baseline 全可用。
5. Rust focused tests green：new enums no catch-all、live/CFD/margin/short/options/unknown typed-deny、legacy `submit_paper_order` 不被 stock path 復用、lane-scoped IPC schema/version tests green。
6. Python no-write guard green：無 direct IBKR submit/cancel/replace、無 generic authenticated write helper bypass、routes 只能 read/import 或 thin Rust IPC caller。
7. DB packet accepted：DDL/ERD、PK/FK/CHECK/index、hypertable/retention、Guard A/B/C、Linux PG dry-run/double-apply evidence；scorecard derived-only。
8. E3 external-surface gate green before any IBKR call：chosen API baseline、local topology、secret files/modes/fingerprints/no-env fallback、live slot absent/empty, API allowlist, redaction suite, rate limits, audit event.
9. IBKR paper/session attestation green before any paper order rehearsal：broker-reported paper env、expected account/session/host/port/secret fingerprint、fresh scoped envelope、Decision Lease、Guardian/risk、cost model、market session、audit sink in same final window。
10. Evidence-clock preregistration complete：universe hash、benchmark hash、cost model hash、hypothesis hash、collector/schema versions、corporate-action/FX/fee/tax source as-of、sample/power gates、ADR-0047 labels、paper-shadow divergence thresholds。
11. Five trading-day pre-clock shakedown PASS：calendar-aware coverage、symbol-level completeness、latency/DQ checks、daily scorecard regeneration from atomic facts、GUI reconstructability view。
12. GUI gate green：badge/readiness first, client lane untrusted, route/cache/auth partition tests, disabled CFD/live states, stock evidence export links, desktop/mobile screenshots, existing crypto tabs unchanged。
13. Kill switch / disable cleanup verified: lane disable blocks new broker calls, preserves read-only status/audit, handles stale/unknown broker state, archives evidence, proves live slot absent/empty。
14. Release packet assembled：manifests with hashes, command outputs, screenshots, role reports, QA report, E4 logs, E3 security artifacts, QC/MIT evidence specs, rollback/disable runbook paths。

## Direct answers

1. QA 不能在當前 acceptance criteria 下簽核「按排程後 fully online」。Phase 0 可批准；Phase 1+ 必須等上表 gate 成為 accepted spec 並由 E2/E4/QA 逐 phase 驗收。
2. 明確 test plan 仍不足。Rust/IPC、Python no-write、DB migration、GUI regression、evidence pipeline、security/redaction、runtime kill switch、crypto non-regression 都已被命名，但還不是完整命令/fixture/artifact/negative-case gate。
3. Rollout/rollback/disable procedures 不足。特別缺 failed evidence-clock day 的 deterministic PASS/FAIL/QUARANTINED、pause/reset、quarantine、artifact retention、GUI cleanup、secret/session disable。
4. Release artifacts 還不夠審計。需要固定 manifest schema、hashes、command transcript paths、screenshot paths、role report paths、daily DQ artifacts、scorecard regeneration outputs。
5. 最小 QA launch checklist 見上；它只覆蓋 `stock_etf_cash` paper/shadow，不授權 live/tiny-live。

PM-facing gate decision: APPROVE_PHASE0_ONLY
