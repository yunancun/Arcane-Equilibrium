# v80 Cold Audit — P1/P2/P3 Closure Archive

**Date**: 2026-05-29
**Source plan**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--cold_audit_validated_fix_plan.md`
（PA validated：P0=0 / P1=17 / P2=17 / P3=7 + 10 rejected/downgraded）
**Closure**: all 17 P1 + 15/17 P2 + 7/7 P3 修復 source-landed；P2-06/07 design-complete impl-deferred（未來 ML wave）。
**Status**: SOURCE checkpoint 完成；runtime deploy/rebuild 見 TODO §0 deploy-gate 殘留。

本檔將已關閉的 cold-audit 明細移出 active TODO（per TODO maintenance：DONE detail 停止幫助 handoff 即歸檔）。Active TODO 僅保留一行 pointer + deploy-gate 殘留 + P2-06/07 deferred 參照。

---

## Commit Map（Mac `main`，未 push 時序，後由本 session 三端同步）

| Wave | Commit | 範圍 |
|---|---|---|
| 1 | `b93d3210` | PkgA/B — live-auth 真實性 + exchange 授權硬化（P1-01/02/03/04/05/06/07/08/17 + P2-02/03）|
| 2 | `11b9531f` | PkgC/D — evidence-gate 完整性 + AI cost/lineage 真實性（P1-09/10/12/13/14 + P2-01/08；P1-11 reclassified）|
| 3 | `7909ca3d` | GUI/async 真實性 + guardian config + SoT docs（P1-15/16 + P2-04/09/12/14/15/16/17）|
| 4 | `dc2a15aa` | 剩餘 P2 cleanup + ML-maturity 設計 ticket（P2-05/10/11/13；P2-06/07 design）|
| P3 | `f2b020e5` | 7 P3 cleanup — conservative gates + honest comments/UX |
| TODO | `a6dccc6d` (+本歸檔 commit) | TODO 收口 + 歸檔 |

---

## P1（17/17 DONE）

| ID | 修復摘要 | Commit | Review |
|---|---|---|---|
| P1-01 | Executor live-auth verifier 改用 `OPENCLAW_LIVE_AUTH_SIGNING_KEY`（非 IPC secret），集中於新 `live_preflight.py`，雙鍵皆空 fail-closed | b93d3210 | E2/E3/E4 |
| P1-02 | live start/resume/grant 必經 gate→IPC→Rust readback 才 active/granted；精確 `live_reserved`（非子串）；IPC resume 失敗不吞 | b93d3210 | E2/A3/E4 |
| P1-03 | Python live cancel-all REST 移除 → 改 Rust IPC `cancel_all_orders` + PipelineCommand authority（operator 決策）| b93d3210 | E2/E4/BB APPROVE |
| P1-04 | live close-all/emergency GUI partial-failure 持久紅 banner（orphan_sweep.skipped 靜默路徑亦判紅）| b93d3210 | A3/E2 |
| P1-05 | safe-recheck/demo-validate 降為誠實 manual-mark；蓋章狀態不滿足 readiness gate（state_compiler 驗證無 reader 解鎖）| b93d3210 | E2/A3 |
| P1-06 | exchange trading-stop 用 side-aware tick normalizer，缺 instrument spec fail-closed（保留本地 StopManager dual-rail）| b93d3210 | E2/E4/BB |
| P1-07 | order-create 嚴格 fail-closed：timeout/parse/transport/非0 retCode 單次嘗試（operator 決策）；reduce-only close 保留 bounded retry（survival 例外）| b93d3210 | E2/E4/BB |
| P1-08 | live secret slot（含 LiveDemo）禁 process-env credential fallback | b93d3210 | E2/E3/BB |
| P1-09 | edge cost gate 准入要 fresh(≤48h TTL `risk.slippage.edge_estimate_ttl_secs`) + runtime-derived + validated；live=reject / demo=exploration（避 Phase-5 dead-loop）；now≤0 fail-closed guard | 11b9531f | E2/QC/E4 |
| P1-10 | paper PAPER_SHADOW→DEMO_ACTIVE promotion 凍結於 promote() chokepoint；inert named reopen seam；regression test 證 paper 不能 promote demo | 11b9531f | E2/E4 |
| P1-11 | **reclassified spec-drift（無代碼）** — canonical close-maker evidence 已在 `trading.fills` V094 columns（MIT 親驗 14396 fills 100% populated, fresh today, 0 writer/reader for `learning.close_maker_audit`）；不建 dead table | — | MIT verify |
| P1-12 | policy_state/route_plan enum 端到端正規化（policy_ready_standard；binder 接受 route_c_escalated_standard）；e2e fixtures | 11b9531f | E2/AI-E/E4 |
| P1-13 | provider-native paid call 寫 durable `agent.ai_invocations`+`learning.ai_usage_log`（既有表，無 migration），deterministic event_ts → ON CONFLICT 去重防重複計費；paid ledger-write 失敗 fail-closed | 11b9531f | E2(MED-1/2 cleared)/E4 |
| P1-14 | model registry 對 should_ship/shadow_only artifact 強制登記；DB 不可用 fail-loud；no_ship 豁免 | 11b9531f | E2/MIT |
| P1-15 | SPECIFICATION_REGISTER ADR-0036..0041 死路徑修正（0 missing）；Operator-mirror cmp=0 | 7909ca3d（+ v83 prior）| R4 APPROVE |
| P1-16 | Alpha/M11 Stage-A-smoke vs Stage-B-divergence doc 切分（SSOT+register+SCRIPT_INDEX）；`attribution_daily` `promotion_evidence=false` scaffold marker | 7909ca3d | R4/E2 |
| P1-17 | global mode switch IPC 異常不吞 → partial_failure + rust_synced=false；live mode 要 Rust readback | b93d3210 | A3/E2/E4 |

## P2（15/17 DONE + 2 design-deferred）

| ID | 摘要 | Commit |
|---|---|---|
| P2-01 | backtest API 標 stub；stub 輸出禁注入 promotion/cost-gate evidence | 11b9531f |
| P2-02 | amend 缺 instrument cache fail-closed（無 off-tick/off-step）| b93d3210 |
| P2-03 | rate-limit preflight path/group aware | b93d3210 |
| P2-04 | bybit_api_reference 對齊 source（pre_check_order removed / demo dcp removed / 10→20 r/s comment）| 7909ca3d |
| P2-05 | scheduled supervised/quantile training 刻意維持 demo-only（reopen 條件 sequenced）；ADR-0004 addendum + comment marker | dc2a15aa |
| P2-08 | Route A 預設 local/free（Ollama），paid 僅 env opt-in；unpriced paid call blocked；daily spend 累計讀取 | 11b9531f |
| P2-09 | Guardian scoring 權重/門檻抽為 invariant named const + rationale + lock tests（含 position_count==reject 零裕度不變量）；GuardianConfig 閾值欄位仍 RiskConfig-tunable | 7909ca3d |
| P2-10 | replay full-chain duplicate-spawn 並發測試（驅動真 dedup：PG advisory lock + cap，非 mock）+ 分離 Linux PG empirical gate | dc2a15aa |
| P2-11 | Rust 超 2000-cap 檔搬 inline tests 出去（step_4_5_dispatch 2020→1803；intent_processor/tests 2170→1838）；3599 tests 不變。Python strategy_ai_routes.py(2536) split 留 follow-up | dc2a15aa |
| P2-12 | async GUI route 不再在 event loop 呼 blocking Bybit client（asyncio.to_thread）；2 PG read 加 tx-scoped statement_timeout | 7909ca3d |
| P2-13 | Stage 0R 8-D sweep 一次性快取 row-derived features + 短路確定性失敗；~3x extraction 加速；exact-vs-fast 輸出 byte-identical 證明 | dc2a15aa |
| P2-14 | dead scheduled-restart UI 停用 + fail-closed console.warn guard（HTTP 410）；governance refresh loadGovernance()→loadAll() | 7909ca3d |
| P2-15 | paper stop/stop-all residual error → partial_failure；GUI 經 classifyLiveMutation（residual 不顯綠）| 7909ca3d |
| P2-16 | CLAUDE/README「Bybit-only execution；ADR-approved 非 Bybit read-only data 例外」 | 7909ca3d |
| P2-17 | docs/README dead M13/V116 links repointed to archive + 補 TODO archive entries | 7909ca3d |

**Design-complete impl-deferred（未來 ML wave，acceptance + 無 migration 需求；設計見 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--cold_audit_pkgE_ml_maturity_p2_05_06_07.md`）**：
- **P2-06** `observability.model_performance` evaluator-writer — rolling Brier/AUC/calibration（exit_features + realized outcome join，5 leakage guards，mode-scoped），+ live-packet fail-closed gate（mode-scoped evidence 空時 defer）。表已存在（V004），無 migration；MIT Linux dry-run + 啟用 deploy-gated。
- **P2-07** Stage-B cohort replay — completion/veto materialization（vs 現 Stage-A smoke）；promotion-grade evidence 判據定義。無 migration。

## P3（7/7 DONE）

| ID | 摘要 | Commit |
|---|---|---|
| P3-01 | DSR component 低 N（<DEFAULT_DSR_MIN_OBSERVATIONS=30）DEFER（verdict defer_data，passes=False），conservative-only；composite block precedence 保留；doc 註明 30 是 degenerate-floor 非 power line（power 由上游 trade-count gate 負責）| f2b020e5 |
| P3-02 | grid_helpers OU residual-sigma 註釋對齊代碼（compute_ou_step 已用 OLS-residual σ；OuResidualSigma 為保留 cross-validation estimator）；comments only | f2b020e5 |
| P3-03 | synthetic replay evidence opt-in（allow_synthetic=False default），排除於 demo-applier allowlist，不靜默當真 evidence；DB CHECK enum SoT 不變（無 migration）| f2b020e5 |
| P3-04 | openclaw_core backtest/portfolio exports 標為 reserved library API（golden_extreme test-covered，非 dead）— KEEP，未刪 | f2b020e5 |
| P3-05 | generic FailsafeWatcher 標 test-only（production 用 SharedFailsafeWatcher）；dispatcher dedup declined（3 個不同 secret-path env var）；doc only | f2b020e5 |
| P3-06 | autonomy-posture GUI 白話 enum/stat 映射（中文優先）+ raw enum 保留（括號 + title tooltip 維持 audit truth）+ 技術細節收 collapsible；presentation-only | f2b020e5 |
| P3-07 | agent reports/archive 系統化索引 — **本歸檔檔 + docs/README archive index entry 即為 cold-audit 範疇的 systematic archive 實踐**；literal-vs-generated 全域 index policy 仍 PM backlog | 本 commit |

---

## Review chain（全程無跳關）

每 wave：PA spec → E1/E1a impl → 並行 E2(對抗性) + A3(GUI) + R4(docs) + QC(quant) + MIT(data) + BB(exchange) → E4 regression → PM commit。

關鍵 catch（皆退回修好）：
- A3：live partial-failure toast 3.5s 自動消失 → 改持久 banner；autonomy-posture title=raw audit-truth gap。
- E2：AI ledger `ON CONFLICT DO NOTHING` 因每次 now() 失效 → 預算重複計費 bug（MED-1）→ deterministic event_ts 修復 + 去重 test。
- QC：guardian position_count==reject 零裕度不變量未鎖 → 補 lock test；DSR 30-obs 是 fail-closed 地板非 power line（doc）。
- MIT：P1-11 close_maker「缺表」實為 stale spec drift（證據已在 trading.fills V094）→ 不建 dead table。

最終 regression：Rust openclaw_engine 3599/0 + openclaw_core 468/0；Python control_api_v1 + ML/AI 全綠；node --check 全過；無 test-count regression。

## Deploy gates（runtime，operator/Linux-gated — 見 active TODO §0）

1. **PkgD Linux PG empirical** — ledger ON CONFLICT/deterministic event_ts 真 PG 語義驗證（Mac 為 mock）。
2. **Linux rebuild + restart** — `restart_all.sh --rebuild --keep-auth`；engine binary 套用新碼。
3. **PkgB Linux IPC end-to-end probe** — `cancel_all_orders` IPC 實際達 engine（不可 provoke live cancel）。
