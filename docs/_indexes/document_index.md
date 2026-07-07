# Document Index

> **ROUTER / HISTORICAL INDEX**
>
> 本文件由 `docs/README.md` 長索引機械遷出，用於保存近期與歷史文檔入口。
> 它不是 active dispatch queue；當前 blocker、owner、gate、runtime evidence 一律讀根目錄 `TODO.md`。
> 新增重要文檔時優先更新本索引或 `initiative_index.md`，不要把長表重新塞回 `docs/README.md`。

### 2026-07 冷審計 R2 + soak dispatch / drift-gate 設計批（2026-07-04 TW per R4 補登）

> 本節補回 R4 cold-audit R2 指認的「_indexes/document_index.md 零 2026-07 條目」缺口，收 operator 已批准之設計 spec、冷審計主線報告與 E4 回歸報告；IBKR stock_etf 2026-07-01 大批 source-static-guard checkpoint（100+ 份）不逐條展開，主題導航見 `initiative_index.md`。

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-07-02--soak_dispatch_edge_containment_and_drift_gate_design.md` | operator 已批准之 soak dispatch edge-containment + standing-envelope post-approval drift-gate 設計（Impl A/B 錨；`d0eeafb41` drift gate 判準側落地來源）。 |
| `CCAgentWorkSpace/PA/workspace/reports/2026-07-03--cold_audit_validated_fix_plan.md` | PA 冷審計 R2 validated fix plan：D1-D9 裁決依據 + P1/P3 修復批次來源。 |
| `CCAgentWorkSpace/PA/workspace/reports/2026-07-04--overgate_residual_unified_design_p11.md` | PA over-gate 殘留統一設計（P11）：drift-gate/exact-head/plan-age 疊加拒真率治理。 |
| `CCAgentWorkSpace/PA/workspace/reports/2026-07-04--cold_audit_remaining_122_unverified.md` | PA 冷審計剩餘 122 未複核項清單。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-03--cold_audit_pm_final.md` | PM 冷審計 R2 最終整合（12 軸閉環 + D1-D9 裁決）。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-03--cold_audit_baseline.md` | PM 冷審計 R2 baseline（凍結 SHA + 軸範圍）。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-05--legacy_todo_mag083_phase5_resolution.md` | PM legacy TODO 判定：AgentTodo MAG-083/MAG-084 已由 2026-05-11 W-D sign-off 解決；Signal Diamond Phase 5 strategy params 已由 per-engine TOML + Rust loader/factory 接線解決；不授權 live/Stage3/Executor/Cost Gate。 |
| `CCAgentWorkSpace/Operator/2026-07-05--legacy_todo_mag083_phase5_resolution.md` | Operator mirror：legacy TODO MAG-083/MAG-084 + Phase 5 strategy params resolved 判定，同 PM 報告 byte-identical。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-05--legacy_todo_remaining_work_audit.md` | PM legacy TODO 剩餘工作核實：AgentTodo MAG-002/MAG-003 由 MAG-015 歷史閉合；Signal Diamond 舊 ModeState/fan-out 限制由 3E-4 per-pipeline 架構取代；無可直接派工剩餘項。 |
| `CCAgentWorkSpace/Operator/2026-07-05--legacy_todo_remaining_work_audit.md` | Operator mirror：legacy TODO remaining-work audit，同 PM 報告 byte-identical。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_trade_engineering_roadmap_after_maker_challenge.md` | PM 挑戰 maker-first NO-GO 後的 AI/ML 交易工程路線圖：保留 mature-perp maker-first NO-GO，將主線收斂為 ProofPacket/evidence loop、PIT manifest、supervised advisory、controlled Demo bandit、new-listing/event screen、M12 cost-reduction、MCP source-only matrix。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_trade_engineering_roadmap_after_maker_challenge.md` | Operator 摘要：挑戰 maker-first 後的 90 天 AI/ML 交易工程路線圖與不做清單；下一實際 blocker 仍是 standing Demo loss-control envelope refresh。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_adversarial_audit.md` | PM 對 AI/ML 交易工程路線圖的對抗性審計：`PASS-WITH-CONDITIONS`，確認方向有效但必須 gate-based；收緊 ProofPacket、PIT manifest、registry serving、DemoMutationEnvelope、new-listing 防挑窗、M12 cost-reduction、MCP pinned source-only 條件。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_adversarial_audit.md` | Operator 摘要：AI/ML 路線圖對抗性審計通過但附條件；下一安全工程入口限 `proof_packet_v1`、PIT manifest contract、或 current-head standing envelope refresh。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_autonomous_completion_loop_design.md` | PM 自治工程推進 loop 設計（continuous-state v2）：將 AI/ML roadmap 轉為 gate-based backlog/state machine/work-item/effect-review/mandatory state-packet 流程；`ADVANCED` 也必寫 state packet 並自動進下一輪，自動停止於 loss-control/runtime/MCP/order/live/no-delta 邊界。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_autonomous_completion_loop_design.md` | Operator 摘要（continuous-state v2）：自治工程 loop 只授權工程推進與驗收，不授權 runtime、order、MCP credential、Cost Gate 或 live；每輪都寫 `roadmap_loop_state_packet_v1`，WP1 dry-run 後應補 recovery state 再進 WP2。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp1_proof_packet_contract.md` | PM 第一輪 AI/ML roadmap autonomous completion loop checkpoint：選 `WP1-PROOF-PACKET-V1`，新增 source-only `proof_packet_v1` validator/hash/extractor/tests，將 candidate-matched after-cost proof 與 no-fill blocker artifact 機器可檢；work-item/effect-review JSON 隨報告落盤。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_loop_wp1_proof_packet_contract.md` | Operator 摘要：ProofPacket contract 第一輪已 source-only 落地，focused/adjacent tests PASS；不授權 runtime、DB、exchange/private read、MCP、order/probe、Cost Gate、deploy 或 live/mainnet；下一 source-only item 為 PIT dataset manifest。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp1_chain_closure.md` | PM continuous loop recovery closure：補派 E2/E4/QA 審查 commit `b9867ac9e`；E4/QA PASS，E2 留 1 個 medium proof-provenance concern，短鏈 concern 關閉並以 `ADVANCED_WITH_CONCERNS` carry 到 WP2。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_loop_wp1_chain_closure.md` | Operator 摘要：WP1 closure 已補完整 review/regression/acceptance 鏈；下一步仍是 source-only `WP2-PIT-DATASET-MANIFEST`，且需補 named PIT manifest/rebuild/hash/feature-lineage 以關閉 E2 concern。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.md` | PM continuous loop WP2 checkpoint：新增 source-only `pit_dataset_manifest_v1` validator/builder/rebuild/hash tests，ProofPacket `PROOF_READY` 必須帶 valid 且 candidate-bound 的 PIT manifest；E2/E4/QA fixed pass，state=`ADVANCED`。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.md` | Operator 摘要：WP2 PIT dataset manifest 已可機器檢查，unpinned now/max_age query 降為 research-only，ProofPacket provenance 不再只靠 generic hashes；下一 source-only item 為 `WP3-REGISTRY-SERVING-PARITY`。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.md` | PM continuous loop WP3 checkpoint：新增 source-only `registry_serving_contract_v1`，將 registry advisory metadata 綁到 PIT/feature/label/split/leakage/serving hash、q10/q50/q90 artifact hash 與 no-authority boundary；E2/E4 PASS、QA ACCEPT_WITH_CONCERNS，state=`ADVANCED_WITH_CONCERNS`。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.md` | Operator 摘要：WP3 registry serving parity source contract 已可機器檢查；direct reload capability 仍 fail-closed，未授權 promotion-serving/runtime reload；下一 source-only item 為 `WP4-ADVISORY-DREAMENGINE-ROLE-HARDENING`。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp4_advisory_dreamengine_role_hardening.md` | PM continuous loop WP4 checkpoint：新增 source-only `advisory_review_packet_v1`，讓 L2/LLM/MLDE/DreamEngine/thought-gate outputs 變成 input-hash-bound inactive review packets；E2 findings 全部 closed，E4 PASS，QA ACCEPT_WITH_CONCERNS，state=`ADVANCED_WITH_CONCERNS`。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_loop_wp4_advisory_dreamengine_role_hardening.md` | Operator 摘要：WP4 advisory/DreamEngine role hardening 已可機器檢查；不授權 LLM 交易、策略/config mutation、Demo mutation、Cost Gate 或 runtime；下一 source-only item 為 `WP5-DEMO-MUTATION-ENVELOPE-CONTRACT`。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp5_demo_mutation_envelope_contract.md` | PM continuous loop WP5 checkpoint：新增 source-only `demo_mutation_envelope_v1` + `mlde_demo_applier` record mapping，讓 future Demo mutation countability 必須具備 previous/proposed/bounded delta/governance/rollback/review/proof；E2 findings closed，E4 PASS，QA ACCEPT，state=`STOPPED`/`STOP_LOSS_CONTROL`。 |
| `CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_loop_wp5_demo_mutation_envelope_contract.md` | Operator 摘要：WP5 DemoMutationEnvelope contract 已可機器檢查；不授權 bandit runtime、DB/IPC execution、Demo mutation、order/probe、Cost Gate 或 live/mainnet；下一步停在 `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp4_strict_adversarial_audit.md` | PM strict adversarial audit over completed WP1-WP4：focused regressions PASS、source-only boundary held；downgrades WP1/WP4 to P1 hardening-required because ProofPacket accepts malformed `sha256:` provenance and AdvisoryReviewPacket accepts truthy provider/private/exchange/MCP contact aliases。 |
| `CCAgentWorkSpace/Operator/2026-07-07--ai_ml_roadmap_wp1_wp4_strict_adversarial_audit.md` | Operator mirror：WP2 PASS、WP3 known concern only、WP1/WP4 require hash strictness/no-contact alias fixes before downstream authority-grade use；不授權 runtime/MCP/order/probe/Cost Gate/live。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp4_fixes_and_trading_adversarial_audit.md` | PM fix-and-audit report：修掉 WP1/WP4 P1、WP3 P2、WP4 P3；ProofPacket strict hash、Advisory self-hash/no-contact、Registry trio atomic transaction；第二輪 trading-focused adversarial payload 21/21 fail-closed。 |
| `CCAgentWorkSpace/Operator/2026-07-07--ai_ml_roadmap_wp1_wp4_fixes_and_trading_adversarial_audit.md` | Operator mirror：WP1-WP4 修復後條件通過；有效 candidate-matched after-cost proof 仍可通，order/probe/live/private/MCP/Cost Gate/promotion 仍無權。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp4_training_profit_evolution_cold_audit.md` | PM cold audit of stronger training/profit/evolution claim：WP1-WP4 are necessary prerequisites but not sufficient closed-loop learning; training pipeline is not yet PIT/registry/proof/advisory-contract gated; venv dry-run trained/exported ONNX but ended at registry DB precheck and produced no WP contract binding fields。 |
| `CCAgentWorkSpace/Operator/2026-07-07--ai_ml_roadmap_wp1_wp4_training_profit_evolution_cold_audit.md` | Operator stub：指向 PM full report；裁決 `FAIL-STRICT-AS-STATED / PASS-AS-PREREQUISITES`；下一步需 WP2.1 training PIT gate、WP3.1 registry contract emission、WP5 mutation envelope、WP6 reward-ledger ProofPacket bridge、WP7 effect-review stop loop。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp5_completion_assessment.md` | PM completion assessment：WP1-WP5 source-contract layer passes, but full AI/ML training/profit/evolution closure fails until training PIT/registry binding, ProofPacket-backed reward ledger, effect-review stop loop, and standing Demo loss-control runtime path are implemented。 |
| `CCAgentWorkSpace/Operator/2026-07-07--ai_ml_roadmap_wp1_wp5_completion_assessment.md` | Operator stub：指向 PM full report；裁決 `PASS-SOURCE-CONTRACT-LAYER / FAIL-FULL-TRAINING-PROFIT-EVOLUTION-CLOSURE`。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_closure_loop_design.md` | PM downstream closure loop design：source-first/runtime-gated loop for WP2.1 training PIT gate、WP3.1 registry contract emission、WP6 reward-ledger ProofPacket bridge、WP7 effect-review stop loop；含自動循環與自動退出邏輯及 launcher prompt。 |
| `CCAgentWorkSpace/Operator/2026-07-07--ai_ml_downstream_closure_loop_design.md` | Operator stub：指向 PM full report；裁決 `DESIGN_READY_SOURCE_FIRST_RUNTIME_GATED`。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_loop_wp2_1_training_run_pit_manifest_gate.md` | PM downstream closure loop WP2.1 checkpoint：contract-bound quantile training now requires valid `pit_dataset_manifest_v1` before train/export/registry; acceptance reports carry canonical PIT manifest/binding; PA→E1→E2→E4→QA PASS; state=`ADVANCED` and next source-safe item is WP3.1 registry contract emission。 |
| `CCAgentWorkSpace/Operator/2026-07-07--ai_ml_downstream_loop_wp2_1_training_run_pit_manifest_gate.md` | Operator summary：WP2.1 source-only training PIT gate advanced; no runtime/DB/exchange/secret/order/Cost Gate/deploy/live action; runtime/loss-control remains blocked and unconsumed。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_loop_wp3_1_training_registry_contract_emission.md` | PM downstream closure loop WP3.1 checkpoint：contract-bound quantile training now emits/persists canonical `registry_serving_contract_v1` from acceptance/PIT/binding/feature hashes and exact q10/q50/q90 ONNX bytes; PA→E1→E2→E4→QA PASS; state=`ADVANCED` and next source-safe item is WP6 reward-ledger ProofPacket bridge。 |
| `CCAgentWorkSpace/Operator/2026-07-07--ai_ml_downstream_loop_wp3_1_training_registry_contract_emission.md` | Operator summary：WP3.1 source-only registry contract emission advanced; no runtime/DB/exchange/secret/order/Cost Gate/deploy/live/model reload/symlink action; runtime/loss-control remains blocked and unconsumed。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-07-07--standing_demo_loss_control_authorization_blocked_by_engine_env.md` | PM standing Demo loss-control refresh attempt：source `798843f2` request sha `62f2a9cc...` got E3/BB approval and one fast-balance READY artifact, but stopped before guardrail/materialization because engine env `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0` made readiness `BLOCKED_BY_ENGINE_ENV`。 |
| `CCAgentWorkSpace/Operator/2026-07-07--standing_demo_loss_control_authorization_blocked_by_engine_env.md` | Operator summary：standing Demo loss-control refresh remains blocked by engine adapter env; no standing envelope materialized, no order/probe/Cost Gate/live action。 |
| `CCAgentWorkSpace/E4/workspace/reports/2026-07-03--part2_post_approval_drift_gate_regression.md` | E4 回歸：standing-envelope post-approval drift-gate（Impl B）測試矩陣。 |
| `CCAgentWorkSpace/E4/workspace/reports/2026-07-03--soak_dispatch_edge_containment_impl_a_regression.md` | E4 回歸：soak dispatch edge-containment（Impl A）測試矩陣。 |
| `CCAgentWorkSpace/E4/workspace/reports/2026-07-04--e4_test_matrix_blindspot_audit.md` | E4 測試矩陣盲點審計。 |
| `governance_dev/amendments/2026-07-04--AMD-2026-07-04-01-doc06-runtime-mutation-record-rule.md` | AMD-2026-07-04-01：DOC-06 Runtime Mutation 紀錄規則泛化（RM-1..RM-4：before/after + manifest + 持久位置 + 移除裁決 + pin-by-reference），泛化 FA F2 crontab 治理規則為 DOC-06 通用條款。 |
| `archive/2026-07-04--script_index_changelog_prose_archive.md` | SCRIPT_INDEX.md 頭部「最新補充/歷史補充」229 段 run-on changelog prose 歸檔（R4-2026-IDX-04 收斂）；per-batch SSOT 仍在 SCRIPT_INDEX `## YYYY-MM-DD` 區塊，本檔存派生歷史層 + 確定性提取命令。 |
| `references/2000_line_exception_registry.md` | 2000 行硬上限 documented pre-existing exception 正本（冷審計 R2 CC-2）：登記 10 個超標生產檔（路徑+行數+拆分歸屬）；CLAUDE.md §七/§九 指針指向此檔，冷審計據此不再重複觸發 retroactive finding。禁在登記波實際拆檔。 |

### 2026-06-29 IBKR Stock/ETF paper + shadow feasibility lane

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md` | 正式開發安排：在 AE 既有治理、風控、審計、PnL scorecard 上新增隔離 `stock_etf_cash` research lane；先做 IBKR paper/shadow evidence collection，live/non-Bybit execution 仍禁止，開工前需 ADR/治理解鎖。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md` | PM 對抗性審查整合：CC/FA/PA/E3/QC/MIT 一致批准 Phase 0 ADR/spec only，Phase 1+ / IBKR API / secret slot / paper order / GUI runtime / evidence clock 均需先補硬 blocker。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md` | Operator 摘要：IBKR `stock_etf_cash` 方案方向有效，但未 implementation-ready；下一步只能開 Phase 0 ADR/spec packet。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_pm_integration.md` | PM 第二輪整合：CC/FA/PA/E3/E5/QC/MIT/QA 均為 `APPROVE_PHASE0_ONLY`；Phase 0 擴展為 ADR + interface/security/data/GUI/evidence/QA release packet，不能承諾 scheduled full online。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_plan_round2_pm_integration.md` | Operator 二輪摘要：下一步仍只允許 Phase 0 contract packet；IBKR healthcheck、secret、paper order、GUI runtime、evidence clock、tiny-live/live 仍禁止。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md` | PM 第三輪 launch-certification：CC/FA/PA/E3/E5/QC/MIT/QA 均為 `CERTIFIABLE_IF_GATES_PASS`，只在 Phase 0 packet accepted 且 Phase 1-5 gates 全通過後可簽核 paper/shadow lane 完整上線。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md` | Operator 三輪摘要：`paper_shadow_only` 範圍內 all-gates-pass 後可簽核完整上線；仍不代表現在上線、IBKR live/tiny-live、盈利證明或絕對無遺漏。 |
| `adr/0048-ibkr-stock-etf-paper-shadow-lane.md` | Phase 0 ADR：接受 `stock_etf_cash` IBKR read-only / paper / shadow research lane；保留 Bybit active live execution 唯一性，明確禁止 IBKR live/tiny-live/margin/short/options/CFD/transfer。 |
| `governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md` | Phase 0 AMD：把 Bybit-only wording 修正為 active live execution 邊界 + ADR-0048 IBKR paper/shadow 例外；定義 API baseline、secret boundary、runtime/evidence boundary。 |
| `execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md` | Phase 0 named contract packet：列出 broker capability registry、external-surface gate、IBKR session attestation、lane-scoped IPC、risk policy、paper lifecycle、DDL/evidence、GUI、storage、kill/disable、release packet 等 v1 contract。 |
| `execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json` | Phase 0 machine-readable manifest：記錄 accepted contract list、global denials、API baseline、phase unlock status；不授權 runtime/API/secret/order。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_phase0_manifest_contract_checkpoint.md` | PM Phase 0 manifest checkpoint：新增 `stock_etf_phase0_contract_packet_manifest_v1` Rust source validator，鎖定 schema/status/scope、authority paths、API baseline、global denials、contract list、phase unlock table；不授權 runtime。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_phase0_manifest_contract_checkpoint.md` | Operator Phase 0 manifest 摘要：Phase 0 machine-readable manifest 已可由 Rust test 驗證；IBKR contact/release/evidence clock/tiny-live/live 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_python_no_write_static_guard_checkpoint.md` | PM Python no-write guard checkpoint：新增 AST static test，掃描 Stock/ETF/IBKR route 與 future connector files，拒絕 Python broker write API、直接 IBKR broker module import、非 GET route；不掃描既有 Bybit modules。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_python_no_write_static_guard_checkpoint.md` | Operator Python no-write 摘要：Python/FastAPI IBKR surface 仍 display/readiness only；future IBKR connector 若暴露 `place_order/cancel_order/replace_order` 會被測試擋下。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_instrument_identity_contract_checkpoint.md` | PM instrument identity checkpoint：新增 `instrument_identity_contract_v1` Rust source validator + blocked template；要求 PIT symbol/listing/primary-exchange/currency/tradability/PRIIPs/calendar/corporate-action hash，不授權 contract-details call。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_instrument_identity_contract_checkpoint.md` | Operator instrument identity 摘要：future IBKR stock/ETF symbol identity 可 machine-check；IBKR contact/market data/contract details/paper order 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_pit_universe_contract_checkpoint.md` | PM PIT universe checkpoint：新增 `stock_etf_pit_universe_contract_v1` Rust source validator + blocked template；要求 PIT universe membership、成分身份、screen hashes、survivorship controls，不授權 collector/evidence clock。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_pit_universe_contract_checkpoint.md` | Operator PIT universe 摘要：future stock/ETF universe membership 可 machine-check；IBKR contact/market data/collector/scorecard/evidence clock 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_strategy_hypothesis_contract_checkpoint.md` | PM strategy hypothesis checkpoint：新增 `stock_etf_strategy_hypothesis_contract_v1` Rust source validator + blocked template；要求 preregistered low/medium-turnover hypothesis、PIT universe/benchmark/cost/rule/statistical hashes，不授權 profitability claim。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_strategy_hypothesis_contract_checkpoint.md` | Operator strategy hypothesis 摘要：future stock/ETF strategy hypothesis 可 machine-check；IBKR contact/collector/scorecard/evidence clock/profitability/tiny-live/live 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_risk_policy_contract_checkpoint.md` | PM risk policy checkpoint：新增 `stock_etf_risk_policy_v1` Rust source validator + blocked template；驗證 dormant Stock/ETF paper risk config、cash-only caps/universe/cost/order gates，不授權 runtime。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_risk_policy_contract_checkpoint.md` | Operator risk policy 摘要：future Stock/ETF paper/shadow risk policy 可 machine-check；IBKR contact/connector/paper order/scorecard/evidence clock/live 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_reference_data_sources_contract_checkpoint.md` | PM reference-data sources checkpoint：新增 `stock_etf_reference_data_sources_v1` Rust source validator + blocked template；驗證 corporate-action/FX/fee/tax source-as-of，不授權 collector/runtime。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_reference_data_sources_contract_checkpoint.md` | Operator reference-data sources 摘要：future Stock/ETF Phase 3/scorecard reference data source 可 machine-check；IBKR contact/connector/collector/scorecard/live 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_market_data_provenance_contract_checkpoint.md` | PM market-data provenance checkpoint：加硬 `stock_market_data_provenance_v1` Rust source validator + blocked template；驗證 lane/broker/env、vendor/entitlement、hash/time/calendar/source artifact 與 no-contact/no-secret 邊界。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_market_data_provenance_contract_checkpoint.md` | Operator market-data provenance 摘要：future Stock/ETF market-data facts/quote-bar source hashes 可 machine-check；IBKR contact/connector/collector/evidence clock/scorecard/live 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_lane_scoped_ipc_contract_checkpoint.md` | PM lane-scoped IPC checkpoint：新增 `lane_scoped_ipc_v1` Rust source validator + blocked template；鎖定 `stock_etf.*` IPC method/gate/field/typed-denial matrix，不授權 IPC runtime 或 paper order。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_lane_scoped_ipc_contract_checkpoint.md` | Operator lane-scoped IPC 摘要：future Stock/ETF paper IPC 與 Bybit paper path 分離可 machine-check；IBKR contact/connector/runtime/paper order/live 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_broker_capability_registry_contract_checkpoint.md` | PM broker capability registry checkpoint：新增 `broker_capability_registry_v1` Rust source validator + blocked template；完整驗證 read/paper/shadow/scorecard/denied operation matrix 與 Bybit/IBKR 分離，不授權 runtime。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_broker_capability_registry_contract_checkpoint.md` | Operator broker capability registry 摘要：future IBKR operation matrix 可 machine-check；IBKR contact/connector/paper order/live/tiny-live 仍 blocked。 |
| `execution_plan/specs/2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql` | Phase 1 source-only DDL draft：定義 broker/research/audit stock/ETF evidence tables and constraints；不是 active migration，Linux PG dry-run/double-apply + PM/Operator apply authorization 前不可進 `sql/migrations/`。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_db_evidence_ddl_contract_checkpoint.md` | PM DB evidence DDL contract checkpoint：新增 `stock_etf_db_evidence_ddl_v1` Rust source validator + blocked template；要求 schemas/tables/natural keys/Guard A/B/C/PG dry-run requirement，不授權 migration apply。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_db_evidence_ddl_contract_checkpoint.md` | Operator DB evidence DDL contract 摘要：future stock/ETF evidence schema boundary 可 machine-check；PG write/sqlx registration/migration apply/IBKR runtime 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase1_source_foundation_checkpoint.md` | PM Phase 1 checkpoint：closed Rust taxonomy/default-off config/lane-scoped IPC fixture/source-only DDL + denial tests 已落地；不授權 IBKR API/secret/connector/order/migration/GUI/evidence clock。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase1_source_foundation_checkpoint.md` | Operator Phase 1 摘要：source foundation done, no runtime authority；下一步仍是 Phase 2 external-surface gate PASS before first IBKR contact。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase2_precontact_gate_source_checkpoint.md` | PM Phase 2 pre-contact source checkpoint：typed external-surface gate / non-Bybit API allowlist / session attestation validator 已落地且 default BLOCKED；仍不授權 IBKR contact。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase2_precontact_gate_source_checkpoint.md` | Operator Phase 2 pre-contact 摘要：source gate foundation done；first IBKR read-only healthcheck 仍需 immutable PASS artifact。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase2_policy_prereq_source_checkpoint.md` | PM Phase 2 policy prerequisite checkpoint：redaction/rate-limit/audit/paper-attestation/Python no-write source contracts 已落地；仍不授權 IBKR contact。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase2_policy_prereq_source_checkpoint.md` | Operator Phase 2 policy 摘要：gate prerequisite source policies done；immutable PASS artifact 仍缺，first IBKR contact blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase2_ipc_precontact_status_checkpoint.md` | PM Phase 2 IPC checkpoint：既有 `stock_etf.*` fixture response 顯示 gate/policy pre-contact status，`first_ibkr_contact_allowed=false`；不新增 IBKR connector/API。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase2_ipc_precontact_status_checkpoint.md` | Operator Phase 2 IPC 摘要：stock/ETF readiness/status 可見 blocked gate 與 policy flags；immutable PASS artifact 仍缺。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase2_gate_artifact_contract_checkpoint.md` | PM Phase 2 artifact checkpoint：immutable gate artifact typed validation 已落地；要求 PM+Operator reviewer、sealed、hash、gate PASS、policy flags 一致；仍未產生 PASS artifact。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase2_gate_artifact_contract_checkpoint.md` | Operator Phase 2 artifact 摘要：artifact contract done；real PASS artifact 仍缺，first IBKR contact blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase2_runtime_contracts_checkpoint.md` | PM Phase 2 runtime contract checkpoint：secret-slot posture 與 API topology typed validation 已落地；仍未讀取 secret、未啟動 IBKR、未授權 contact。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase2_runtime_contracts_checkpoint.md` | Operator Phase 2 runtime contract 摘要：secret/topology evidence shape done；real evidence + PASS artifact 仍缺。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase2_artifact_runtime_evidence_checkpoint.md` | PM Phase 2 artifact runtime-evidence checkpoint：immutable gate artifact now embeds and validates secret-slot/topology evidence；missing or mismatched runtime evidence blocks first contact。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase2_artifact_runtime_evidence_checkpoint.md` | Operator Phase 2 artifact runtime-evidence 摘要：PASS candidate artifact can no longer rely on gate booleans alone；real evidence + PASS artifact 仍缺。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase2_feature_flag_secret_auth_matrix_checkpoint.md` | PM Phase 2 feature-flag/secret/auth matrix checkpoint：Rust source contract separates read-only, paper, shadow-only, GUI display, and denied live/account authority；仍不授權 IBKR contact。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase2_feature_flag_secret_auth_matrix_checkpoint.md` | Operator Phase 2 feature-flag/secret/auth matrix 摘要：flags alone cannot grant paper/live authority；secret/artifact/session/envelope evidence remains required and first contact blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase2_paper_lifecycle_event_log_checkpoint.md` | PM Phase 2 paper lifecycle/event-log checkpoint：append-only lifecycle event validation、transition rules、STATE_UNKNOWN recovery、restart recovery classifier 已落地；仍不授權 paper order。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase2_paper_lifecycle_event_log_checkpoint.md` | Operator Phase 2 paper lifecycle 摘要：paper order lifecycle evidence shape done；no connector/no paper order/no IBKR contact。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_asset_lane_audit_event_contract_checkpoint.md` | PM asset-lane audit event checkpoint：新增 `audit.asset_lane_events_v1` immutable event-reference validator + blocked template；不寫 audit row、不 apply DDL、不授權 runtime。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_asset_lane_audit_event_contract_checkpoint.md` | Operator asset-lane audit event 摘要：future gate/DQ/scorecard/release references 可 machine-check；audit writer/runtime 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase3_evidence_contracts_checkpoint.md` | PM Phase 3 evidence checkpoint：market-data provenance、frozen inputs、DQ/quarantine manifest、evidence-clock day checker source contracts 已落地；不啟動 evidence clock。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase3_evidence_contracts_checkpoint.md` | Operator Phase 3 evidence 摘要：PASS_DAY/QUARANTINED_DAY/WINDOW_COMPLETE checker semantics done；runtime Phase 3 still blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_evidence_clock_contract_hardening_checkpoint.md` | PM evidence-clock hardening checkpoint：`stock_etf_evidence_clock_v1` day checker now requires contract id/source version, lane/broker/env, provenance hashes, and checker-side no-contact/no-runtime/no-writer/no-DB/no-live denials。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_evidence_clock_contract_hardening_checkpoint.md` | Operator evidence-clock hardening 摘要：future evidence-clock day packets are stricter but still source-only；IBKR contact/connector/runtime clock/scorecard writer/DB apply/live remain blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_scorecard_input_contracts_checkpoint.md` | PM scorecard input contracts checkpoint：新增 cash ledger / cost model / benchmark / shadow fill / storage capacity / derived-only scorecard bundle validators；不啟動 collector 或 evidence clock。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_scorecard_input_contracts_checkpoint.md` | Operator scorecard input 摘要：future scorecard atomic inputs 可 machine-check；live account/fill proof、collector、scorecard writer 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_scorecard_input_contract_hardening_checkpoint.md` | PM scorecard input hardening checkpoint：scorecard atomic inputs now require exact contract ids/source versions，bundle requires upstream contract hashes and explicit no-contact/no-runtime/no-writer/no-DB/no-live side-effect denials。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_scorecard_input_contract_hardening_checkpoint.md` | Operator scorecard hardening 摘要：future scorecard input packets are stricter and remain source-only；IBKR contact/connector/fill import/scorecard writer/DB apply/evidence clock/live still blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase4_gui_readiness_checkpoint.md` | PM Phase 4 GUI readiness checkpoint：新增 display-only `/api/v1/stock-etf/readiness`、console `Stock/ETF IBKR` tab、`lane crypto_perp` badge；不新增 POST/order/secret/IBKR contact/lane selector。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase4_gui_readiness_checkpoint.md` | Operator Phase 4 GUI readiness 摘要：Stock/ETF IBKR 狀態可見，IPC down fail-closed；IBKR runtime、paper order、evidence clock、GUI lane authority 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_gui_lane_contract_checkpoint.md` | PM GUI lane contract checkpoint：新增 `gui_lane_contract_v1` Rust source validator + blocked template；要求 GET-only display、client lane untrusted、route/cache/auth partition、crypto regression，仍不授權 GUI lane authority。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_gui_lane_contract_checkpoint.md` | Operator GUI lane contract 摘要：future Stock/ETF GUI boundary 可 machine-check；POST/order/secret/contact/lane selector、IBKR runtime、paper order、evidence clock 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-30--ibkr_stock_etf_disable_cleanup_runbook_contract_checkpoint.md` | PM disable-cleanup runbook checkpoint：新增 `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` Rust source validator + blocked template；要求 kill flags、collector stop、GUI disabled/hidden、secret absence、forward-only archive/DB retention、Bybit unchanged proof，仍不授權 release/runtime。 |
| `CCAgentWorkSpace/Operator/2026-06-30--ibkr_stock_etf_disable_cleanup_runbook_contract_checkpoint.md` | Operator disable-cleanup 摘要：future IBKR Stock/ETF shutdown/disable proof 可 machine-check；contact/connector/paper order/destructive cleanup/release/tiny-live/live 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_phase5_release_packet_contract_checkpoint.md` | PM Phase 5 release packet contract checkpoint：新增 `stock_etf_release_packet_v1` typed release/shakedown evidence validator + blocked template；不授權 release/tiny-live/live。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_phase5_release_packet_contract_checkpoint.md` | Operator Phase 5 release packet 摘要：future release evidence 可 machine-check；real release、IBKR contact、paper order、evidence clock 仍 blocked。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_tiny_live_adr_eligibility_contract_checkpoint.md` | PM tiny-live ADR eligibility checkpoint：新增 `tiny_live_adr_eligibility_v1` discussion-only validator + blocked template；positive paper/shadow 不能直接授權 tiny-live/live。 |
| `CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_tiny_live_adr_eligibility_contract_checkpoint.md` | Operator tiny-live ADR eligibility 摘要：future ADR discussion gate 可 machine-check；`tiny_live_authorized` / `live_authorized` 仍被拒絕。 |

### 2026-06-22 Shadow placement alpha ingestion

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-22--shadow_placement_impact_alpha_ingestion.md` | PM checkpoint: wires bounded probe shadow placement impact into alpha runtime v9, worklist v6, and profitability closure while preserving result-review precedence and no authority. |
| `CCAgentWorkSpace/Operator/2026-06-22--shadow_placement_impact_alpha_ingestion.md` | Operator note: shadow placement evidence now drives a bounded probe placement repair task, but it still grants no Cost Gate lowering or probe/order authority. |

### 2026-06-22 Bounded probe shadow placement impact

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-22--bounded_probe_shadow_placement_impact.md` | PM checkpoint: shadow-applies the near-touch repair plan to current Demo order-flow and proves mechanical touchability improvement while marking the sample as not candidate-matched alpha proof. |
| `CCAgentWorkSpace/Operator/2026-06-22--bounded_probe_shadow_placement_impact.md` | Operator note for the current shadow replay: 6/6 current no-fill orders would be near-touch submits, but 0/6 match `ma_crossover|BTCUSDT|Sell`; no authority granted. |

### 2026-06-22 Bounded probe placement repair plan

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-22--bounded_probe_placement_repair_plan.md` | PM checkpoint: converts the bounded Demo touchability failure into a no-authority near-touch-or-skip placement repair plan and cron status stage before any Cost Gate/probe/order authority change. |
| `CCAgentWorkSpace/Operator/2026-06-22--bounded_probe_placement_repair_plan.md` | Operator note for the current repair gate: post-only near-touch-or-skip plan is review-ready but inactive, requires separate operator authorization, and grants no Cost Gate/order/probe authority. |

### 2026-06-22 Bounded probe touchability preflight

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-22--bounded_probe_touchability_preflight.md` | PM checkpoint: converts the Demo order-to-fill no-touch finding into a fail-closed bounded Demo probe touchability preflight and cron status stage before any Cost Gate/probe authority change. |
| `CCAgentWorkSpace/Operator/2026-06-22--bounded_probe_touchability_preflight.md` | Operator note for the current gate: 6/6 reviewed Demo orders are deep passive no-touch, max best-touch gap 1530.6074bp versus 75bp initial passive gap requirement; no authority granted. |

### 2026-06-22 Demo order-to-fill touchability audit

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-22--demo_order_to_fill_gap_touchability_audit.md` | PM checkpoint: read-only Demo order-to-fill touchability audit classifies the 48h no-fill sample as deep passive no-touch, making touchability-aware bounded Demo probe design the next engineering gate before any Cost Gate change. |
| `CCAgentWorkSpace/Operator/2026-06-22--demo_order_to_fill_gap_touchability_audit.md` | Operator note for the no-fill conclusion: 6 PostOnly buys, 0 fills, 0 BBO touches, 6 deep passive no-touch orders; no Cost Gate lowering or probe/order authority. |

### 2026-06-21 Cost-Gate learning lane runtime activation runbook

| 文件 | 内容 |
|------|------|
| `runbooks/2026-06-21--cost_gate_learning_lane_runtime_activation.md` | Operator-gated runtime activation SOP for the Cost Gate demo-learning lane: read-only audit, source reconcile/sync gate, activation preflight, cron dry-run/install, optional hot-path writer, observation and rollback boundaries. Runbook only; not runtime approval. |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-21--cost_gate_learning_scorecard_refresh_chain.md` | PM checkpoint: cost-gate learning cron refreshes the read-only reject counterfactual scorecard before plan/materializer/outcome/review, and surfaces scorecard rc/status in status/killboard. |
| `CCAgentWorkSpace/Operator/2026-06-21--cost_gate_learning_scorecard_refresh_chain.md` | Operator note for the complete scorecard-to-review self-refresh chain and remaining runtime activation gate. |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-21--cost_gate_learning_plan_refresh_preflight.md` | PM checkpoint: cron refreshes the bounded demo-learning plan before reject materialization, and activation preflight rejects policy-not-ready plan artifacts. |
| `CCAgentWorkSpace/Operator/2026-06-21--cost_gate_learning_plan_refresh_preflight.md` | Operator note for strict plan readiness and recurring plan refresh in the cost-gate learning loop. |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-21--cost_gate_cron_installer_apply_preflight.md` | PM checkpoint: moves the cost-gate learning cron activation preflight into the installer apply path, requiring expected-head/source/plan readiness before crontab write. |
| `CCAgentWorkSpace/Operator/2026-06-21--cost_gate_cron_installer_apply_preflight.md` | Operator note for the installer apply-preflight gate and remaining explicit runtime activation approvals. |

### 2026-06-18 Codex sub-agent hygiene dispatch rules

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--codex_subagent_hygiene_dispatch_rules.md` | PM governance checkpoint: closes `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` by making the existing sub-agent hygiene SOP mandatory in Codex dispatch records for Rust/Cargo/Linux-runtime/PG/deploy work; no source/runtime mutation。 |

### 2026-06-18 H0Gate file split

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--p3_h0gate_file_split.md` | PM source/test checkpoint: closes `P3-H0GATE-FILE-SPLIT` by moving H0Gate tests into `openclaw_core/src/h0_gate/tests.rs`, reducing production `h0_gate.rs` below the 800-line review threshold with behavior preserved。 |
| `CCAgentWorkSpace/Operator/2026-06-18--p3_h0gate_file_split.md` | Operator mirror: concise result, verification commands, and boundary for the H0Gate file-split checkpoint。 |

### 2026-06-18 Apple Silicon clippy gate

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--p2_clippy_cleanup_gate.md` | PM source/test checkpoint: closes `P2-CLIPPY-CLEANUP-1` by restoring the Apple Silicon `cargo clippy --target aarch64-apple-darwin -- -D warnings` gate, fixing low-risk core/type lints, and codifying the engine historical lint baseline as explicit allowlists; no runtime/deploy mutation。 |
| `CCAgentWorkSpace/Operator/2026-06-18--p2_clippy_cleanup_gate.md` | Operator mirror: concise result, verification commands, and boundary for the clippy cleanup checkpoint。 |

### 2026-06-18 Earn Wave D IPC contract integration

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--earn_first_stake_capability_routing.md` | PM source/test checkpoint: reduces `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` source blocker by wiring Rust Earn capabilities from existing runtime handles and routing Python stake IPC explicitly to `engine=live`; OP-1/2/3, deploy/restart, and first real stake evidence remain gated。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--earn_wave_d_ipc_contract_integration.md` | PM source/test checkpoint: closes `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` by wiring Python `/earn/stake` contract to Rust `process_earn_intent` IPC dispatch, per-pipeline command handling, and fail-closed owner-task tests; first real stake remains blocked by OP-1/2/3 plus Earn capability injection。 |

### 2026-06-18 Earn Wave D HMAC canonical form

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--earn_wave_d_hmac_canonical_form.md` | PM source/test checkpoint: closes `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` by adding Rust/Python Bybit REST V5 Earn GET/POST golden-vector HMAC parity tests; full frontend -> backend -> Rust IPC integration remains active separately。 |

### 2026-06-18 TODO lifecycle hygiene

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--todo_p5_sm_completed_row_relocation.md` | PM TODO hygiene report: removes completed/stale `P5-SM-OPTION2-CONVERGENCE` from §5 after `[82]` step-ii 48h soak and later V138/V139 + L2 activation facts superseded the row; preserves step-iii cutover as §6 operator-gated sign-off。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--todo_cold_audit_p2p3_batch_archive.md` | PM TODO hygiene report: archives completed `AUDIT-2026-06-14-P2P3-BATCH` from §5 after cold-audit Batch 4/5 fix-wave and stale tails were already closed/split; remaining cost-edge / AI-pricing SSOT / BB rate-limit doc / PERF-1 1m follow-up are preserved as §7 condition triggers。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-18--todo_p2_l2_activation_owed_operator_row_archive.md` | PM TODO hygiene report: archives completed §6 `P2 batch activation owed #2-#6` operator row after V138/V139, seed, V140, cron, embedding, and B3 source wiring were already closed; remaining L2 E2E/B3-shadow/P2p/P5 gates stay in root `TODO.md` / `L2_TODO.md`。 |

### 2026-06-13 L2 embedding backfill activation

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-13--l2_embedding_backfill_activation.md` | PM runtime report: Linux `bge-m3` installed, 99 `agent.agent_memory` rows embedded with 1024-dim vectors, daily cron updated with `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1`, `[83]-[89]` PASS, no restart。 |
| `CCAgentWorkSpace/Operator/2026-06-13--l2_embedding_backfill_activation.md` | Operator mirror: concise embedding activation result, run/log/hash, DB state, remaining gates for non-empty L2 material model-call evidence, B3 recall injection, P2p/P5。 |

### 2026-06-13 L2 V140 + FTS-only pipeline activation

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-13--l2_v140_pipeline_activation.md` | PM runtime report: manual V140 applied (`vector(1024)` + HNSW), L2 FTS-only pipeline smoke no-op success, daily cron installed with `OPENCLAW_L2_MEMORY_PIPELINE=1`; embed backfill was off at this checkpoint and is superseded by the embedding activation section above。 |
| `CCAgentWorkSpace/Operator/2026-06-13--l2_v140_pipeline_activation.md` | Operator mirror: concise V140 and L2 cron activation result, remaining gates for `bge-m3`, embedding backfill, true non-empty distillation evidence, and B3 recall injection。 |

### 2026-06-13 L2 memory B2 seed apply

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-13--l2_memory_b2_seed_apply.md` | PM runtime report: operator-approved `seed_agent_memory.py --apply` after V139; inserted 99 rows, recall verify PASS, duplicate record IDs 0, L2 memory flags remain off, `[83]-[89]` PASS。 |
| `CCAgentWorkSpace/Operator/2026-06-13--l2_memory_b2_seed_apply.md` | Operator mirror: concise seed apply result, log/hash, remaining separate gates for V140, pipeline, cron, embedding, recall, and model call。 |

### 2026-06-13 L2 memory B1 seed dry-run

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-13--l2_memory_b1_seed_dry_run.md` | PM runtime report: `seed_agent_memory.py --dry-run` PASS after V139; B source 93 candidates, 6 skips, A source dead_mode count=6 via read-only SQL, `agent.agent_memory` stayed 0 rows at dry-run time; seed apply later closed by B2。 |
| `CCAgentWorkSpace/Operator/2026-06-13--l2_memory_b1_seed_dry_run.md` | Operator mirror: concise dry-run result and then-remaining gates; seed apply later closed by B2 while V140, pipeline flags, cron, embedding, and model call remain separate gates。 |

### 2026-06-13 L2 V138/V139 runtime activation

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-13--l2_v138_v139_activation_runtime.md` | PM runtime closure: operator-approved engine-only auto-migrate applied V138/V139; head=139/all_success=true/checksum drift=0/objects exist/`[83]-[89]` PASS; V140/seed/flags/model/Gate-B remain gated。 |
| `CCAgentWorkSpace/Operator/2026-06-13--l2_v138_v139_activation_runtime.md` | Operator mirror: concise applied result, log paths, migration outcome, post-checks, and remaining gated items。 |

### 2026-06-13 L2 V138/V139 activation-window packet

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-13--l2_v138_v139_activation_window_packet.md` | PM runbook/evidence packet: V138/V139 ready for explicit operator-approved engine auto-migrate window; read-only Linux baseline head=V137/checksum drift=0/objects absent/`[83]-[89]` PASS; includes exact activation and post-check sequence; not executed。 |
| `CCAgentWorkSpace/Operator/2026-06-13--l2_v138_v139_activation_window_packet.md` | Operator mirror: short decision packet; `psql -f` forbidden, only `OPENCLAW_AUTO_MIGRATE=1` + engine-only restart + restore flag after approval; V140/seed/flags/model/Gate-B remain separate gates。 |

### 2026-06-13 P5-SM [82] clean closure

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-13--p5_sm_82_clean_closure.md` | PM closure: P5-SM `[82]` 48h soak gate PASS on Linux true DB healthcheck (`window=48.1h`, `probes=1442`, `success_rate=1.0000`); step-iii cutover and V138/V139/L2 activation remain operator-gated。 |
| `CCAgentWorkSpace/Operator/2026-06-13--p5_sm_82_clean_closure.md` | Operator mirror: `[82]` blocker closed, no deploy/rebuild/restart/migration/model call/trading mutation; remaining explicit non-closures listed。 |

### 2026-06-13 A1 basis / P2 OPS / P3 forward recorder

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-13--a1_basis_p2ops_p3_forward_checkpoint.md` | PM checkpoint: A1 basis 14d formal evidence matured; A1 functional path verified but no entry-gate signals (`draft_only`, `infra_gap=false`); P2 pg_dump/passive health tests added; P3 ticker forward recorder source landed, deploy-gated。 |

### 2026-06-12 文档治理第二批索引收敛

| 文件 | 内容 |
|------|------|
| `README.md` | Router-first docs 入口已瘦身；长 Document Index 迁至本文件。 |
| `_indexes/document_inventory.json` | v2 摘要库存；`docs_markdown=2619`，只作规模/目录导航，不作删除判据。 |
| `_indexes/audit_index.md` | Audit 目录语义索引：`docs/audit/`、`docs/audits/`、`governance_dev/audits/`、role reports。 |
| `runbooks/README.md` | Runbook 目录入口；声明 runbook 不是 operator approval。 |
| `architecture/README.md` | Architecture 目录入口；区分 stable overlays 与 historical MAG ledger。 |
| `archive/README.md` | Archive 目录入口；声明 archive 不是 backlog。 |
| `healthchecks/README.md` | Healthcheck docs 入口；声明文档不是当前 runtime health。 |
| `known_issues/README.md` | Historical known issues 入口；当前 blocker 仍在 `TODO.md`。 |

### 2026-06-12 L2 root TODO tail triage

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-12--l2_root_todo_tail_triage.md` | PM triage: root `L2_TODO.md` is not completed-archive eligible；open tails mirrored into TODO v149 `P1-L2-ADVISORY-MESH-TAILS`；no runtime mutation/model call/deploy。 |
| `CCAgentWorkSpace/Operator/2026-06-12--l2_root_todo_tail_triage.md` | Operator brief mirror: V138/V139 activation, E2E-1, P2p sentinel Telegram/probe/install, and P5 remain gated; current safe action was active-state repair only。 |

### 2026-06-12 文档治理第一批降权索引

| 文件 | 内容 |
|------|------|
| `_indexes/initiative_index.md` | 主题入口索引：L2、AEG/Gate-B、P5-SM、OPS-2、incident-policy、Multi-Agent historical ledger；明确不是 active queue。 |
| `_indexes/README.md` | `docs/_indexes` 目录说明；标记 `document_inventory.json` 为 stale snapshot。 |
| `audit/README.md` | 说明 `docs/audit/` 是 legacy 62-finding audit bundle，不是当前 issue tracker。 |
| `audits/README.md` | 说明 `docs/audits/` 是 dated audit evidence，不是 active queue。 |

### 2026-06-12 AEG-S3 Gate-B watch / preflight

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-12--aeg_s3_gate_b_preflight_command_guard.md` | PM checkpoint: Gate-B preflight v0.3 adds `recommended_command` operator guard；current live artifact remains `WATCH_ONLY`, sample_count=2, `HOLD_WAIT_FOR_ACTIONABLE_WATCH`; includes P5-SM `[82]` countdown refresh。 |
| `CCAgentWorkSpace/Operator/2026-06-12--aeg_s3_gate_b_preflight_command_guard.md` | Operator brief: do not run old Gate-B full-chain command or start probe while latest artifact is wait-only；`[82]` remains accumulating until about 2026-06-13 03:59:37+02。 |

### 2026-06-12 Incident-policy producer closure

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_pm_source_closure.md` | PM source closure: `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` source chain closed after BB/E2/E4/QA；runtime activation remains operator/deploy-gated。 |
| `CCAgentWorkSpace/QA/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_qa_acceptance.md` | QA source acceptance: C4 true producer path + notify-only boundary + engine_dead watchdog closure passed on Mac/Linux focused checks；not deployed-E2E。 |
| `CCAgentWorkSpace/E4/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_e4_regression.md` | E4 source-focused regression: incident-policy planned producer set PASS_WITH_CONDITIONS on Mac+Linux focused Rust/Python matrix；QA/PM closure now recorded above；no CI/deploy/service rebuild/restart。 |
| `CCAgentWorkSpace/E2/workspace/reports/2026-06-12--incident_policy_producer_slices_re_review.md` | E2 focused re-review: `sm_halt_stuck` / `position_drift` / external `engine_dead` producer slices PASS-WITH-CONDITIONS；0 blocker/high/medium/low；E4/QA/PM follow-up now recorded above。 |
| `CCAgentWorkSpace/BB/workspace/reports/2026-06-12--incident_policy_producer_slices_bb_re_review.md` | BB focused re-review: new producer slices add no Bybit endpoint/order/market-close/direct `set_trading_stop`; APPROVE-WITH-CONDITIONS；0 blocker/high/medium。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-12--incident_policy_producer_slices_bb_e2_closure.md` | PM closure checkpoint: planned producer source coverage + BB/E2 focused review no longer block `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`; superseded by E4 regression report above for the next gate。 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-12--incident_policy_engine_dead_watchdog_producer.md` | PM report: external `engine_dead` watchdog notify-only producer source-live；stale ≥30s + failed respawn ≥1 後寫 `ENGINE_DEAD_NOTIFY_ONLY`/`ENGINE_DEAD_RESOLVED`，不餵 C4 `AllFail`、不武裝 Defensive；focused watchdog tests passed；後續 BB/E2 closure 見本節 producer slices reports。 |

### 2026-06-10 Root sweep 歸檔（cold audit rulings + INVENTORY 校準更名）

| 文件 | 内容 |
|------|------|
| `archive/2026-05-17--cold_audit_pm_final.md` | 第一輪 cold audit PM final ruling（P1 17/P2 17/P3 7；實際 5-29 完成）；原 srv 根目錄，已被 5-30 re-run 取代（closure 見 `archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`） |
| `archive/2026-05-30--cold_audit_pm_final.md` | cold audit re-run PM final ruling：prior remediation HELD，P0=0/P1=0，僅小額 P2/P3 backlog；原 srv 根目錄 |
| `execution_plan/2026-06-10--ae_runtime_rename_migration_guide.md` | AE 運行面全面改名遷移指引（GATED：Apple Silicon 遷移時強制）；353 env/~6400 代碼處/8+ systemd/IPC/repo 名波及面實測快照 + P0-P6 分階段 + 風險緩解 + DONE 定義；gate 前禁止 AE_*/ae_* 新前綴。TODO §7 `P3-AE-RUNTIME-RENAME` 指向本檔 |

> 同次 sweep：`OPENCLAW_INVENTORY_CONSOLIDATED.md`（2026-04-25 快照）經 71 條校準後更名 `AE_INVENTORY_CONSOLIDATED.md`（仍在 srv 根目錄，深歷史/RCA 按需讀）；清理 2026-04-20 占位目錄 backup_files/ research_notes/ stored_data/（README 所述子目錄從未建立）。

### 2026-06-10 SKILLS_TODO 審計歸檔

| 文件 | 内容 |
|------|------|
| `archive/2026-06-10--skills_todo_audit_closed.md` | 24-skill 安全審計 76/76 finding 全結案歸檔（2026-04-25 audit；修復 commit 鏈 `35a1b624`→`531e6d4a` 共 7 commits：P0×5 風控詞義反向/越位/捏造修正 + S1-S6 systemic + 9 對 cross-skill 互引 + C turn 2 snapshot trim）；原 `srv/SKILLS_TODO.md` 移入，根目錄不再保留；skill 現狀以 `.claude/skills/*/SKILL.md` 為準。|

### 2026-06-05 L2 Advisory Mesh (L2 Copilot)

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md` | L2 Advisory Mesh 可執行 roadmap；建置序 D3→Orchestrator/registry/contracts/guard→本地哨兵→ml_advisory→online-FDR loop→feedback/quality+GUI，每 phase E1 驗收 + sign-off + green-gate；折入 QC B1 / MIT M1 / MIT M2 ENDORSE 的 FIX/NOTE、CC carbon-layer fence、E3 auth/sanitize、V134/V13x Linux PG dry-run。設計 E1-READY，等 operator 啟 E1。 |
| `execution_plan/2026-06-05--l2-copilot-design-session-consolidated.md` | L2 copilot 設計 session 整合背景；FinceptTerminal 評估（催生 copilot 方向）、L2 角色重定義（copilot 非訊號器 / paper 退役 / L2 manual）、設計核心決策（6 lane/derived autonomy/LANE_DIRECTION/D3 provenance/人=事後法醫+稀有 live 批准/Q1 online-FDR/Q3 cascade/Q6 留存/LearningTier 融合）、四審 0 CRITICAL + 2 BLOCKER 已閉。供未來 plan audit 引用。 |

### 2026-06-01 AEG-S1 Foundation Blocker Resolution

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-06-01--aeg_s1_fnd3_side_evidence_artifact_contract.md` | AEG-S1-FND-3 side-evidence artifact contract；`side_evidence.json` 為 optional child artifact，僅 secondary-only context，需 run-id/digest linkage，明確排除 promotion gates / math verdict override / trading input。|
| `execution_plan/2026-06-01--s2_gate_b_prelaunch_phase_transition_probe_plan.md` | S2 Gate-B PreLaunch phase-transition probe plan；定義 24h isolated public REST/WS probe、BTC controls、verdict labels、capture-only collector gates；真實 phase transition PASS 前 production collector IMPL 仍 blocked。|
| `execution_plan/2026-06-01--aeg_s1_mit_storage_migration_design_packet.md` | MIT storage migration-design packet；選 `V125__aeg_alpha_history_storage.sql` 作 design reservation，建議 `research.alpha_*` storage、`market.klines` 1095d retention/provenance ledger、Guard A/B/C、rollback/dry-run；未建立 SQL file、未 apply。|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_fnd3_s2_gate_b_storage_migration_design_integration.md` | PM integration report；整合 PA/QC、BB/MIT、MIT 三路 sub-agent 結果與 Linux read-only reflection，確認 FND-3/S2 Gate-B prep/V125 design complete，列下一步 V125 review 與可選 Gate-B probe scope。|
| `CCAgentWorkSpace/Operator/2026-06-01--aeg_s1_fnd3_s2_gate_b_storage_migration_design_checkpoint.md` | Operator brief；濃縮 FND-3、S2 Gate-B prep、MIT V125 storage migration-design checkpoint、未授權事項與下一步工作排程。|
| `execution_plan/2026-06-01--aeg_s1_fnd1_storage_retention_provenance_change_control.md` | AEG-S1-FND-1 storage/retention/provenance change-control package；operator 已批准設計分支：`market.klines` 1095d + DB provenance ledger 作為 OHLCV path，funding/OI/long-short 走 dedicated research-history storage；明確保留 writer/DB mutation/backfill/scoring blocked。|
| `execution_plan/2026-06-01--aeg_s1_fnd2_pit_universe_builder_contract.md` | AEG-S1-FND-2 PIT universe builder contract；指定 `market.symbol_universe_snapshots` 為 PIT source，797-row survivorship CSV 僅作 seed/regression，current-survivor shortcut 自動 FAIL。|
| `execution_plan/2026-06-01--aeg_s1_fnd4_public_endpoint_runner_client_gap_persistence_map.md` | AEG-S1-FND-4 public endpoint runner/client-gap + persistence map；建議延伸 isolated Python public replay client，mark/index/premium price-only kline 不可重用 OHLCV parser，historical basis/index bypass `market_tickers`。|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_fnd1_storage_change_control_integration.md` | PM integration report；整合 MIT/PA 並行 read-only audit + Linux reflection，標記 FND-1 package complete / implementation still blocked；後續 operator storage decision、FND-2/FND-4、FND-3/S2/V125 設計 checkpoint 已另有記錄。|
| `CCAgentWorkSpace/Operator/2026-06-01--aeg_s1_fnd1_storage_change_control_integration.md` | Operator brief；濃縮 FND-1 storage branch、Linux runtime baseline、仍 blocked 範圍；storage branch 已由後續 operator decision brief 記錄批准。|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_operator_storage_decision.md` | PM report；記錄 operator 批准 FND-1 storage branch，並開 FND-2/FND-4 docs/design 並行。|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_s1_fnd2_fnd4_parallel_integration.md` | PM integration report；整合 MIT/BB sub-agent read-only 回報，確認 FND-2 contract + FND-4 map complete；其後 FND-3、S2 Gate-B、MIT V125 migration-design 已由下一 checkpoint 完成。|
| `CCAgentWorkSpace/Operator/2026-06-01--aeg_s1_operator_storage_decision.md` | Operator brief；記錄 FND-1 approved design branch 與 FND-2/FND-4 open scope，保留 execution blocked 邊界。|
| `CCAgentWorkSpace/Operator/2026-06-01--aeg_s1_fnd2_fnd4_parallel_integration.md` | Operator brief；濃縮 FND-2/FND-4 並行 checkpoint、`market_tickers` historical bypass 決策、仍未授權事項與下一步排程。|
| `execution_plan/2026-06-01--aeg_s1_foundation_unblock_packet.md` | AEG-S1 Foundation unblock packet；把 AEG blocked list 分成可立即派發的 docs/design/read-only FND-1..4 + S2 Gate-B prep，以及仍禁止的 backfill writer / DB retention mutation / endpoint ingestion / collector runtime / alpha scoring；FND-4 包含 index/mark ticker persistence fix-vs-bypass。|
| `CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_blocked_items_resolution_verification.md` | PM verification report；確認 blocker classification 已完成，但 runtime/DB/backfill/collector/scoring outcomes 未完成，不能標成 full implementation complete。|

### 2026-05-31 Alpha-Edge Regime Evidence Governance / AEG-S0

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-31--aeg_s0_contracts.md` | AEG-S0 formal PASS contract：Evidence Storage Contract、Regime Classifier Freeze、Bybit Endpoint Contract、TODO Archive Plan；只開 AEG-S1 Foundation limited scope，仍禁止 backfill run / DB mutation / endpoint ingestion / collector runtime / alpha scoring until scoped gates。|
| `execution_plan/2026-05-31--alpha_edge_regime_evidence_engineering_arrangement.md` | Alpha-Edge governance arrangement；現已指向 AEG-S0 formal closure，並保留 S1 limited-open 邊界。|
| `execution_plan/specs/2026-05-31--historical-kline-backfill-spec.md` | Historical kline backfill spec；原 executable posture 已被 AEG gate override，retention/backfill 只能在 AEG-S0/S1 gate 後開 scope。|
| `execution_plan/specs/2026-05-31--collector-listing-capture-spec.md` | Collector listing-capture design；原 implementation-ready posture 已被 AEG gate override，collector IMPL 仍 blocked。|
| `references/2026-04-04--bybit_api_reference.md` | Bybit API reference；AEG round-1 BB review 修正 mark/index/premium price-kline 為 price-only candles，禁止重用 standard KlineBar parser/schema。|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-31--aeg_s0_contract_sprint_pm_local.md` | PM-local AEG-S0 contract sprint report；記錄草案形成、remaining gates、no-runtime/no-DB/no-trading 邊界。|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-31--aeg_s0_formal_review_round1_integration.md` | PM integration report for PA/MIT/QC/BB/TW/CC round-1 conditional review；記錄 must-fix 已納入且 re-review 仍 required。|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-31--aeg_s0_formal_review_closure.md` | PM closure report：PA/MIT/QC/BB/TW/CC re-review PASS；AEG-S1 Foundation limited-open；backfill/DB/endpoint/collector/scoring 仍 gate-blocked。|
| `adr/0047-alpha-edge-regime-evidence-governance.md` | ADR-0047：Alpha-Edge promotion evidence 必須 math-primary；bull data 可用但必須標籤化；S4 是全局 falsification overlay；Bybit market APIs 是 raw state input。|
| `governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md` | AMD-2026-05-31-01：operator clarification；禁止把 bull data ban、Bybit trend oracle、narrative primary evidence 三種錯誤解讀帶入後續實作。|

### 2026-05-26 Sprint 2 Alpha Tournament SSOT

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-26--alpha_tournament_ssot_spec.md` | ARCH-05 / Sprint 2 Alpha Tournament SSOT：補齊 v5.8 §4 implicit Alpha slot，固定讀取順序、候選池 A0-A5/B0、scoring contract、minimum evidence gates、Stage output、最小前置、role chain、跨文檔指針；文檔補丁不授權任何新 strategy、不放鬆 P0/Stage/5-gate。|

### 2026-05-23 Sprint 1B late §4.1.1 + Sprint 5+ §4.2.1/§4.3.1 — Stage A→E + PA-DRIFT-6 catch+fix（Sprint 4+ §4.1.1/§4.2.1/§4.3.1 三條 carry-over closure）

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_late_v100_m4_hypothesis_base_table_design.md` | PA Track 1 — V99-V102 spec gap audit + V099→V100 push back + V100 M4 base table design（V099 autonomy SSOT 不可碰 + V100 重 number；3 table 13/7/10 column 設計 + earn_movement_log FK target patch `learning.governance_audit_log` + Guard A 13 base column only；DESIGN-DONE / E1-IMPL-READY）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_bybit_private_ws_supervisor_design.md` | PA Track 2 — BybitPrivateWs supervisor signature 改造 design（Option A external Arc 注入 type-level enforcement；4 caller impact + PrivateWsBindings + SharedClientsBundle + spawn_metric_emitter_scheduler 三層擴展；5 AC + 半實裝陷阱誠實揭露 lesson；DESIGN-DONE-DISPATCH-READY）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_strategy_quality_wireup_design.md` | PA Track 3 — StrategyQualityEmitter wire-up Path A design（1 big CTE join query 25 pair × 5 metric snapshot；新 file strategy_quality_probe_impl.rs ~200 LOC + update task 5 min tick + cache 1:1 對齊 PortfolioStateCache；6 AC + 16 根原則 A 級；DISPATCH-READY 8-11 hr budget）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_remaining_3_sections_audit.md` | PA Track 4 — Sprint 1B 剩 3 章節 audit（C10 Stage 1 Demo READY-TO-DISPATCH 41-62 hr / Earn first stake NEEDS-OPERATOR-DECISION + DEPENDS-ON-§4.1.1 50-78 hr / v5.7 baseline 收口 DOWNGRADE-TO-NON-WORK；PA 推薦路徑 A 先 C10 後 Earn）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_1b_late_v100_m4_hypothesis_base_table.md` | E1 B-1 V100 M4 base table IMPL（V100 SQL 663 LOC + spec doc 581 LOC；3 NEW table 30 column + 11 status enum + 4 engine_mode enum + 2 direction enum + 3 reconciliation_status enum + 4 hot-path index + 20 COMMENT；earn_movement_log FK target patch；cargo test sqlx Migrator parser 15/15 PASS；3 hr 實際 IMPL）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_bybit_private_ws_supervisor_signature_impl.md` | E1 B-2 BybitPrivateWs supervisor IMPL（6 file +164 / -60 LOC；5 caller 全 update + Wave A handle accessor 保留；E1 push back 2 條 採信 SSOT — dispatch type 描述錯 + 新發現 caller live_auth_watcher_tests.rs:103；cargo test 3971 PASS / 0 FAIL baseline +10）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_strategy_quality_wireup_phase_a_impl.md` | E1 B-3 StrategyQualityEmitter Phase A IMPL（strategy_quality_probe_impl.rs 656 LOC + main_health_emitters.rs +571 LOC + main.rs +34 LOC + mod.rs +12 LOC；STRATEGY_QUALITY_BATCH_QUERY 5 CTE join + F-2 NaN/inf sanitize + interval.tick consume first；strings binary Track E 全 symbol + 0 mock/spike；cargo test 3522 PASS）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md` | TW Stage A→E Overall Acceptance Report（PASS WITH 8 CARRY-OVER；Stage A 4 並行 PA design + Stage B 3 並行 E1 IMPL + Stage C E2 round 1×3 + Round 2 PM Edit + Stage D E4 combined regression + Stage E Linux deploy + PA-DRIFT-6 catch+fix；7/7 target table land + 9 row metadata + B-2 ws_rtt/dropout 真實採樣 + B-3 strategy_quality 5 min 126 row；§6 PA-DRIFT-6 lesson learned 完整 RCA + §8 8 carry-over routing；待 PM Phase 3e 拍板）|

**PA-DRIFT-6 核心治理 lesson**：TimescaleDB hypertable composite PK 不能作為 PostgreSQL FK target；V100 改 soft reference + Guard C 改 column check + COMMENT 中文紀錄 — 未來 V### 自動繼承。

### 2026-05-23 Sprint 5+ Wave 1 — Phase A→E full chain closure（V101/V102 + M3 follow-up + §4.4 hardening + PA-DRIFT-8 catch+fix）

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_design.md` | PA Track 1 — V101/V102 Track v3 attribution column design（V101 ENUM 3 值 + ADD COLUMN trading.fills.track + Batched UPDATE backfill + Guard A/B/C；V102 Option B trigger fallback + DEFAULT 雙保險 + 2 hot-path index；scope 嚴守 trading.fills only；7 AC；DISPATCH-READY 8-12 hr wall-clock；其他 11 表 + view + kill_events 拆 Sprint 5+ Wave 2 carry-over）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_cascade_4_2_design.md` | PA Track 2 — Sprint 5+ §4.2.2-4 cascade design（§4.2.2 PortfolioStateCache PaperState SSOT Option A disk-based JSON 讀取 4-6 hr E1；§4.2.3 archive 4 Python singleton re-ingest doc-only 1-2 hr TW+PA；§4.2.4a dispatch template + §4.2.4b PA-DRIFT lesson template；強 push back 「sandbox stub cleanup 不入 §4.2.3」分離）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_m3_follow_up_design.md` | PA Track 3 — Sprint 5+ §4.3.2-6 M3 follow-up design（§4.3.2 AC-7 cold start bench + §4.3.4 F-4 correlation lookback=1h + §4.3.5 Track B 4/5 metric real probe + §4.3.6 Track C 2 metric real probe；§4.3.3 LOC 切檔 defer Phase B IMPL-driven；4 並行 ~1175 LOC / 21-27 hr E1 / 1-1.5 day wall-clock；SSOT 校正 push back operator AC-7 描述）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_production_hardening_design.md` | PA Track 4 — Sprint 5+ §4.4 production hardening + AC-1b monthly cron design（Linux empirical 6h evidence 校準：open_fd 711 row WARN baseline 1700-1800 vs ladder OK<1024 / ws_rtt 47 row WARN baseline 162-163ms vs ladder OK<50；amend ladder open_fd OK<3072 + ws_rtt OK<170；3 helper scripts + AC-1b monthly cron crontab spec；6-8 hr E1 + 2-3 hr QA）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_impl.md` | E1 B-1 V101/V102 IMPL round 2（V101 305 LOC + V102 345 LOC；7-Step chain × 2；composite PK (fill_id, ts) 對齊；V077 trigger fallback 範式對齊；5 round 2 fix HIGH-1 ALTER SET DEFAULT EXCEPTION fallback + HIGH-2 Guard C three-way + MEDIUM-1/2/3 + LOW-2；cargo test PASS 1/0/0 filtered 3226）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_3_2_ac7_cold_start_bench_impl.md` | E1 B-2 AC-7 cold start bench IMPL（benches/m3_emitter_cold_start.rs 252 LOC + Cargo.toml +8 LOC；0 criterion dep；plain fn main + Instant + Notify + worker_threads=2 + 6 MockEmitter；Mac aarch64 p99=1ms <<50ms PASS；Linux E4 復跑；4 AC 全 PASS）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_3_4_f4_correlation_real_calculator_impl.md` | E1 B-3 F-4 correlation real calculator IMPL（risk_envelope_probe_impl.rs +546 LOC / 959→1505；2 新 const + 2 新 field per_symbol_returns_history / last_symbol_prices + update signature 加 per_symbol_mid_prices 第 5 param + Step 4 F-2 sanitize + prune_returns_history_1h helper + Pearson outer-join two-pointer + 7 新 F-4 unit test；28/28 lib test PASS）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes_impl.md` | E1 B-4 Track B + Track C real probes IMPL round 2（7 新檔 1106 LOC + 9 既有改 +275 LOC；WsStats/SignalStats/WriterQueueStats/PoolWaitStats 4 stats struct + pool_acquire_with_stats helper + RealPipelineThroughputSource + RealDatabasePoolSource；round 2 5 CRITICAL caller wire-up + signature revert mandatory Arc + 30 unit test + cargo workspace 4016/0/5 PASS）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_4_production_hardening_impl.md` | E1 B-5 §4.4 production hardening IMPL round 2（open_fd ladder OK<3072 + ws_rtt ladder OK<170 amend + rest_p50/p95/p99 注釋補 cascade gap 預期說明 + 4 新 unit test + 3 helper script land + SCRIPT_INDEX update；round 2 6 fix HIGH-1 fixture 200→350 + MEDIUM-1 env var convention + MEDIUM-2 bash fail-loud + MEDIUM-3 spec ladder amend + LOW-1 crontab abstract）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_overall_acceptance.md` | TW Sprint 5+ Wave 1 Overall Acceptance Report（PASS WITH 3 GOVERNANCE NEW + 4 OBSERVATION CARRY-OVER；Phase A 5 並行 PA design + sandbox cleanup + Phase B 5 並行 E1 IMPL combined + Phase C E2 round 1×5 + Round 2 fix + verify + Phase D E4 combined regression + Phase E Linux deploy + PA-DRIFT-8 catch+fix；12 commit chain；6 active domain × 30 min 1836 row + 53 sentinel populate + 14326 backfill + V102 trigger+index+DEFAULT；§6 PA-DRIFT-7 + PA-DRIFT-8 + signal_rate volatility 3 governance NEW；§8 8 carry-over routing closure；待 PM Phase 3e 拍板）|

**PA-DRIFT-8 核心治理 lesson**：PG/TimescaleDB UPDATE row 觸發 row-level CHECK constraint re-validation EVEN if updated column 與 constraint 無關；V101 Step 1.5 sentinel populate `legacy_pre_v083_unknown_<fill_id>` 53 row inline amend；未來 V### spec SOP 必加 forward-only constraint violator scan + ADR-0010 Guard D amend routing Sprint 5+ Wave 2。

### 2026-05-23 Sprint 4+ first Live carry-over Acceptance（Sprint 2 §4.1 4 items closure）

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_4_pa_drift_5_risk_envelope_wireup.md` | E1 Wave A PA-DRIFT-5 round 1 IMPL（RealRiskEnvelopeSourceProbe + PortfolioStateCache 24h sliding window + 4 真實 calculator + 1 correlation placeholder + 16 inline test + 11 integration test）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_pa_drift_4_bybit_instrumentation.md` | E1 Wave A PA-DRIFT-4 round 1 IMPL（RestLatencyHistogram + RetCodeCounter + WsRttHistogram + WsDropoutCounter 四 instrumentation singleton + RealApiLatencySourceProbe + 8 trait method + 4xx/5xx 對映 + 6/8 dropout 接點 + ping/pong RTT contains peek + 15 integration test）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_a_round2_combined_fix.md` | E1 Wave A round 2 combined fix（6/6 finding closure：PA-DRIFT-4 H-1 BLOCKER noop guard + H-2 60s boundary 4 test + H-3 觀測下沉 + M-1 注釋；PA-DRIFT-5 F-1 cap comment + F-3 batch read trait extension `snapshot_5_metric()`）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_main_scheduler_wireup.md` | E1 Wave B round 1 IMPL（main_health_emitters.rs 528 LOC + main.rs 接線 + 5/6 emitter spawn + PortfolioStateCache 300s update task placeholder no-op + F-2 NaN/inf sanitize + emitter sample_now batch path 切換 + OBSERVE-4 propagate Err 不 swallow + 6 integration test）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_round2_fix.md` | E1 Wave B round 2 fix（5/6 finding closure：HIGH-1 Track B placeholder 5 metric OK band 合法值 tick_rate=2.0/signal_rate=1.0/ipc_p99=1.0 + MEDIUM-2 Track D WS half doc 揭露 supervisor disconnect 副作用 + LOW-1/2/3；MEDIUM-1 SSOT 建立由 PA 走獨立 task）|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-23--sprint_4_e4_regression_wave_ab.md` | E4 Wave A+B combined regression（PASS；cargo workspace 3961/0/5 × 2 non-flaky + pytest 6042/28 × 2 + Wave A+B 42/42 + Sprint 2 51/51 + spike 3/3 + health 110 + cross-lang 12/12 + aarch64 darwin clean + AC-5 nm 0 hit + inject_* 0 leak + Linux sandbox + V106 schema + pg_hba reject + production engine PID 2934602 健康不重啟）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_wave_b_m1_singleton_registry_ssot.md` | PA Singleton Registry SSOT 建立（M-1 CLOSED；docs/architecture/singleton-registry.md 344 LOC 新建 + 6 singleton 12 欄位 + CLAUDE.md §七/§九 cross-ref + docs/README.md index + 5 deliverable + Wave C unblock 6/9 子目標 closed）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md` | TW Sprint 4+ first Live carry-over Overall Acceptance Report（PASS WITH 8 CARRY-OVER；Phase 0-3c chronology + §4.1 4 items Acceptance + cross-cutting verdict + Lessons Learned 6 條 + Sprint 1B late 3 條 + Sprint 5+ cascade IMPL 4 條 + Sprint 5+ M3 follow-up 6 條 + Production 監測 follow-up 4 條 carry-over；5 active domain row count 770 row + production V106 raw apply + engine PID 3654935 健康；待 PM Phase 3e 拍板）|

### 2026-05-23 Singleton Registry SSOT 建立（Sprint 4+ Wave B M-1 closure）

| 文件 | 内容 |
|------|------|
| `architecture/singleton-registry.md` | OpenClaw Mutable Singleton Registry SSOT（trim 後新權威位置；登記 Sprint 4+ Wave A 4 + Wave B 2 共 6 新 singleton：RestLatencyHistogram / RetCodeCounter / WsRttHistogram / WsDropoutCounter / PortfolioStateCache / HealthEventBus；§3 登記規則 + §5 lessons learned trim 反模式 + §6 4 條 Sprint 5+ carry-over）— per E2 Wave B round 2 MEDIUM-1 escalate；CLAUDE.md §七 line 165 + §九 line 196 「current authority location」 cross-ref |

### 2026-05-22 Layered Autonomy v2 設計收口（CC re-audit APPROVE A 級）

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md` | PA Layered Autonomy v2 — Autonomy Level Toggle 主 spec（1031 行；Conservative/Standard 雙層 + 5-gate switch + 24h cooldown + 三路通知 fail → 1h wait → SM-04 Defensive + 7d cooling + 6 cross-level invariant + 5 fail-safe hard requirements） |
| `execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` | M3 metric emitter Sprint 2 design spec（848 → 961 LOC；6 health domain emitter + amplification cap + cross-language window fixture + cascade reject log）— Sprint 2 Wave 1 主 dispatch target |
| `execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` | M3 emitter Sprint 2 dispatch packet（563 LOC；Track A/B/C 6 Wave 1+2 並行 stagger + D1 sysinfo + D2 並行 + D3 cascade reject log minimal） |
| `execution_plan/specs/2026-05-22--v099-autonomy-level-config.md` | V099 autonomy_level_config schema spec（568 LOC；`system.autonomy_level_config` + `_switch_audit` + PG ENUM `autonomy_level_enum` + Cache PG LISTEN/NOTIFY） — Wave 5 cascade IMPL prerequisite |
| `governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` | AMD-2026-05-21-01 v2 — Layered Autonomy with Hard-Coded Fail-Safe（684 LOC；取代 v1 protected 6 / opt-in 8 二分版；三維度並列 + Autonomy Level Toggle + 反向 attack counter-mitigation 6 條） |
| `governance_dev/amendments/2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md` | AMD-2026-05-26-01 — funding_arb V2 Deprecation Closure（Workflow F Phase 2；operator (D) 3C TOML deprecation closure；ADR-0018 status 升格 Retired closed；enforcement = TOML config-load active=false；strategy code `#[deprecated]` marker + runtime fail-closed guard 屬 D+7 E1 IMPL 未 land，per 2026-06-14 治理漂移訂正 + 5 textbook → 4 textbook reframe + D+0/D+7/D+30 cleanup 三階段；ADR-0046 future redesign slot 並存保留） |
| `adr/0046-funding-arb-v3-redesign-slot.md` | ADR-0046 — funding_arb V3 Redesign Slot（Proposed；revive-gate placeholder per AMD-2026-05-26-01；未 Accepted 不得作為 funding_arb 上線依據） |
| `governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md` | **AMD-2026-05-25-01 (Active 2026-05-27)** — Commercialization Boundary: Exchange-Native Only。Supersedes AMD-04 §1 Stream 2 (Monetization Demand Test 30% capacity)；extends AMD-05 retract scope from「IP sale only」to「all non-exchange-native commercialization」。Retire 8 路徑（IP sale / Telegram subscription「玄衡 Signal」/ Substack/Beehiiv / signal feed integration / MEV/DEX / Stripe pre-order / Cloudflare landing / Twitter outreach）。Retain 6 路徑（Bybit Copy Trading per ADR-0030 4-gate / Bybit Earn per ADR-0031-0032 / Bybit competitions / Binance Copy Trading reserve Y3+ / Binance Earn reserve Y3+ / prop firm trading capital channel 特例）。Y1 末 commercial evidence packet 只 evaluate Bybit Copy Trading；不再含 Stream 2 demand test gate。對齊 v5.5 single product 定位 + ADR-0040 venue gate + v4.4 D7 constraint AMD 化。|
| `governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md` | AMD-2026-05-25-02 — v5.5 Bot Positioning + Capital Structure Formalization（Active 2026-05-27；Decision 1 = 完整 quant bot 單一產品，主帳承載全部 strategies 不受 Bybit Copy Trading 子集限制；Decision 2 = Y1 100% 主帳 $7,500 active + Off-exchange $2,500，副帳 $0 Y1；Y2+ 副帳 enable 條件 = ADR-0030 4-gate + 本 AMD §4.2 Gate 5 Moat 全 PASS；supersedes v5.4 §2/§3/§10 dual-product + Cadet/Bronze/Silver/Gold tier ladder；Engineering Implication = Zero new work，v5.5-v5.8 已對齊）|
| `CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md` | CC re-audit verdict APPROVE A 級（7/7 HC PASS + 6/6 反模式 PASS + 2 BLOCKER 候選解除 + Hard Boundaries 5/5 PASS） |

**Wave 5 cascade IMPL roadmap**（PENDING operator final sign-off）：見 `TODO.md` §1.7（V099 schema land + GUI Autonomy Posture + Rust `RiskEvent::NotificationFailsafeTimeout` variant + 5 module ADR sync + R4 cross-ref audit）

---

### 2026-05-21 Sprint 1A-β dispatch packet + v5.7/v5.8 13-module thesis + autonomy AMD

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-20--execution-plan-v5.7.md` | v5.7 Dispatch-Safe Patch 主檔（Round 12-15 reviewer rounds 收斂、Bybit Earn Guardian / 14 hard problems 修法、§12 12-prefix 補丁；Sprint 1A dispatch baseline） |
| `execution_plan/2026-05-20--execution-plan-v5.8.md` | v5.8 13-Module Autonomy Expansion 主檔（M1-M13 module roster + ADR-0034..0041 reservation + V105-V116 schema reserve + 5 階段 Sprint 1A 拆分） |
| `execution_plan/2026-05-21--sprint_1a_dispatch_packet.md` | Sprint 1A-β PA dispatch packet（13 module spec land sub-phase + 7 必 ADR + 9 V### spec + runbook 派發排程） |
| `execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` | V103/V104 Earn Hypotheses + Allocator Proposals schema spec（Sprint 1A-α MIT 940 行 baseline；M4 Self-Supervised Hypothesis Discovery 依賴源） |
| `execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` | V103/V104 Linux PG dry-run protocol + 5-round empirical reflection + Guard A/B/C 驗證 |
| `execution_plan/2026-05-21--earn_governance_spec.md` | Bybit Earn Asset Movement Guardian 完整治理 spec（5-Gate Adapter + Decision Lease retrofit + audit log；ADR-0032 spec phase） |
| `execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md` | M4 Pattern Miner minimum bar threshold + leakage protocol（hypothesis discovery 防 data leak + null-result acceptance + shift(1) 三語言） |
| `execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md` | M11 threshold rename + M7 dedup decay enforced（continuous replay 與 model decay 接線去重；per CR-7 contract） |
| `execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md` | M1 LAL Layered Approval Lease module DESIGN spec（697 行；Tier 0-4 升降 / 24h undo / Decision Lease retrofit / ADR-0034 對應 module 行為層 spec）— SPEC-DRAFT-V0 (IMPL pending Sprint 1A-γ+；per 2026-05-21 acceptance audit) |
| `execution_plan/2026-05-21--m2_overlay_state_machine_design_spec.md` | M2 Overlay Enable / Disable state machine module DESIGN spec（macro / on-chain / regime 三類 overlay 治理；5-state FSM × 5 trigger_type；V105 schema 已 land）— DESIGN-DRAFT (Sprint 1A-γ 派發；IMPL pending E1 Sprint 5+) |
| `execution_plan/2026-05-21--m3_health_monitoring_design_spec.md` | M3 self-monitoring / auto-diagnostics / health-aware degradation module DESIGN spec（648 行；4-state ladder + 6 health domain + amplification cap；對應 V106 schema spec）— DESIGN-DRAFT (IMPL pending Sprint 1A-γ+；ADR 待 Sprint 1A-γ R4 cross-ADR audit 補) |
| `execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md` | M4 Hypothesis Discovery — self-supervised pattern mining module DESIGN spec（Cowork DRAFT-only 邊界 + V103 EXTEND + shift(1) leak-free）— SPEC-DRAFT-V0 (Sprint 1A-γ 派發；DRAFT writeback 在 protected scope 邊界) |
| `execution_plan/2026-05-21--m6_bayesian_reward_weight_design_spec.md` | M6 Bayesian Reward Weight Tuning module DESIGN spec（849 行；GP kernel + acquisition function + iter budget + 30% rollback cap；對應 V110 schema spec）— SPEC-DRAFT-V1 (IMPL pending Sprint 1A-γ+；ADR 待補) |
| `execution_plan/2026-05-21--m7_decay_enforced_design_spec.md` | M7 Decay Detection + Single Decay Authority + DECAY_ENFORCED lifecycle module DESIGN spec（463 行；4 source × 6 FSM；14d × 50% per-strategy 動態；對應 V113 schema spec；QC consultant draft + PM transcribe）— SPEC-DRAFT-V0 (IMPL pending Sprint 1A-γ+；ADR 待補) |
| `execution_plan/2026-05-21--m9_ab_framework_design_spec.md` | M9 A/B Testing Framework module DESIGN spec（4 variant cluster × i.i.d. 修正 × variant Stage 路徑 + fair execution clause；對應 V108 schema spec + ADR-0037）— SPEC-DRAFT-V1 (Sprint 1A-γ 派發；Sprint 4 read-only logging / Sprint 7-8 manual A/B / Y2 auto-gate 分階段 IMPL) |
| `execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md` | M11 Continuous Counterfactual Replay module DESIGN spec（619 行；nightly replay divergence 5-7 type × 4-level severity + self-hosted PG `market.liquidations` source；對應 V107 schema spec + ADR-0038）— SPEC-DRAFT-V0 (IMPL pending Sprint 1A-γ+) |
| `execution_plan/2026-05-21--v105_m2_overlay_state_transitions_schema_spec.md` | V105 M2 overlay state transitions schema spec（5 值 state enum + from/to + trigger_type + counterfactual_log FK + engine_mode CHECK） |
| `execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` | V106 M3 health observations schema spec（health domain 6 column + hypertable + 7d chunk + 30d compression） |
| `execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md` | V107 M11 replay divergence log schema spec（divergence_type / divergence_pnl_usdt / fill_chain_id FK + ~9k row/yr 規模） |
| `execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md` | V108 M9 A/B testing framework schema spec（preregistration FK to V103 + hash algorithm + mSPRT schema） |
| `execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md` | V109 M8 anomaly events schema spec（severity taxonomy + event_taxonomy 9 子類 FK；依賴 ADR-0036） |
| `execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md` | V110 M6 reward weight history schema spec（5 λ 值 5 column vs JSONB + bayesian_opt 算法欄位） |
| `execution_plan/2026-05-21--v111_m10_discovery_tier_config_schema_spec.md` | V111 M10 discovery tier config schema spec（Tier A-E 5 行 config + capital threshold 7 級 trigger + activation log） |
| `execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md` | V112 M1 Decision Lease LAL tiers schema spec（Tier 0-4 enum + eligibility materialized view + auto-approve toggle；依賴 ADR-0034） |
| `execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md` | V113 M7 decay signals schema spec（lifecycle 6 值 enum + 4 signal column） |
| `adr/0034-decision-lease-layered-approval-lal.md` | ADR-0034: Decision Lease Layered Approval (LAL) — M1 5 層分層治理（Tier 0-4 重命名避免 AMD-2026-05-15-01 Stage 0R-4 字面碰撞；ADR-0008 擴展不取代） |
| `adr/0035-m5-online-learning-interface-reserved.md` | ADR-0035: M5 Online Learning Interface Reserved — Trait Stub + V114 Placeholder, IMPL Deferred Y3+（Sprint 1A-δ deliverable；retirement criteria 4 條） |
| `adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md` | ADR-0036: M8 Anomaly Detection + M10 Tier D Regime — Model Blacklist + ATR-vol × Funding-state 9-cell 矩陣替代 + RV Percentile + Block Bootstrap Threshold（v5.8 §2 M8+M10 合併 ADR） |
| `adr/0037-m9-ab-framework-and-statistical-methodology.md` | ADR-0037: M9 A/B Testing Framework + Statistical Methodology — 4 Variant Cluster × i.i.d. 修正 × Variant Stage 路徑 + Fair Execution Clause（Sprint 1A-γ DESIGN 50-70 hr；Sprint 4-8 phased IMPL） |
| `adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` | ADR-0038: M11 Continuous Counterfactual Replay — Self-Hosted PG market.liquidations 作 historical source（BB 5.21 audit push back 落地） |
| `adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md` | ADR-0039: M12 OrderRouter Trait — Maker-Fill-Rate Metric + Adaptive Routing Audit Schema（V115 reserve） |
| `adr/0040-multi-venue-gate-spec.md` | ADR-0040: Multi-Venue Gate Spec — M13 Binance Trade Enable Defer Y3+ At Earliest（ADR-0033 §Decision 2 時點 amendment standalone） |
| `adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md` | ADR-0041: ContextDistiller v4 — Layered Snapshot + Token Hard Cap + DOC-08 AI Cost Amendment（ADR-0027 v4 級延伸；AI-E must-fix #1） |
| `runbooks/2026-05-21--m1_lal_operator_runbook.md` | M1 LAL — Tier 升降 / Auto-Approve / Manual Override SOP（5-tier 矩陣 + 6 hard gate + 24h undo fills 不可逆 + 6 反向 attack mitigation；ADR-0034 對應 runbook draft） |
| `runbooks/2026-05-21--m3_health_oncall_runbook.md` | M3 健康監控 On-Call Response SOP（4-state ladder + 6 domain triage + amplification cap + HEALTH_DEGRADED → LAL 降階驗收；v5.8 §2 M3 對應 runbook draft） |
| `runbooks/2026-05-21--m7_decay_alert_runbook.md` | M7 Decay Signal 告警 SOP（4 source × 6 FSM enum 響應矩陣 + 14d × 50% 強制 SUSPENDED 不被 LAL override + M11 dedup verify；CR-7 / v5.8 §2 M7 對應 runbook draft） |
| `runbooks/2026-05-21--m11_replay_divergence_triage_runbook.md` | M11 Nightly Replay Divergence Triage SOP（5-7 divergence type × 4-level severity + 4h budget + 5d unack auto-escalate H-11 + self-hosted PG fallback；ADR-0038 對應 runbook draft） |
| `runbooks/2026-05-21--earn_governance_runbook.md` | Bybit Earn Governance — Operator 介入 SOP（5-Gate Adapter + manual rebalance first 3 months + APY 異常 3 trigger + reconciliation drift；ADR-0030/0031/0032 對應 runbook draft） |
| `runbooks/2026-05-21--counterfactual_quality_report_runbook.md` | Counterfactual Quality 月報生成 SOP（cron + coverage threshold + quality metric 4 維度 + Y1 末 ADR-0030 4-gate evidence packet input prep；M11 月度 aggregation runbook draft） |
| `governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md` | AMD-2026-05-21-01 — v5.8 13-module thesis 核心治理 amendment（CLAUDE.md §二 第 5 條 human final review 拆 protected vs opt-in；5 mitigation + 6 反向 attack counter-mitigation；§四 hard boundaries 不放鬆）|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md` | PM v5.8 final verdict consolidation（5 audit + PA dispatch consolidation 整合；GO-WITH-CONDITIONS verdict） |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_autonomy_verdict.md` | PM v5.7 autonomy verdict（autonomy boundary 收斂 + opt-in path 標準化） |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md` | PM v5.7 §12 12-prefix patch sign-off（PA tech verify + FA business verify 整合 + ADR 編號順移敲定） |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_spike_overall_acceptance.md` | TW Sprint 1A-ζ IMPL Prototype Spike Overall Acceptance Report（合併 Track A/B/C + AC-1..8 verdict map + Lessons Learned 6 條 + Sprint 1A-ε/1B/4+ carry-over；PASS WITH 3 CARRY-OVER；Sprint 1B gate OPEN pending PM Phase 3e） |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3a_spec_reconcile.md` | PA Sprint 1A-ζ Phase 3a Spec Reconcile（5 spec internal conflict / drift closure — V106 6 domain naming SSOT + M11 file path drift + SCRIPT_INDEX 註冊 + Guard A schema name typo + CONCURRENTLY hypertable 兼容） |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` | PA v5.8 dispatch consolidation（13 module spec roster + 7 ADR + 9 V### + runbook 派發 + 16 CR contract） |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_dispatch_consolidation.md` | PA v5.7 dispatch consolidation（12-prefix patch + Sprint 1A scope baseline） |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md` | PA v5.7 §12 12-prefix tech verification（ADR 編號衝突解、Earn Guardian spec dispatch、router/lease 重命名安全） |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md` | FA v5.7 business consolidation（Earn APR business case + Allocator monthly business value + Bybit 14 hard problems business framing） |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v58_executability_audit.md` | FA v5.8 executability audit（13 module business chain 缺口 + 14 must-fix business framing） |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md` | FA v5.7 §12 12-prefix business verification（Bybit Earn business case + Allocator business value） |
| `CCAgentWorkSpace/A3/workspace/reports/2026-05-21--v58_executability_audit.md` | A3 v5.8 executability audit（GUI/UX 13 module surface gap 評估） |
| `CCAgentWorkSpace/AI-E/workspace/reports/2026-05-21--v58_executability_audit.md` | AI-E v5.8 executability audit（ContextDistiller v3 token 預算超 cap + Y2 LLM cost 風險；ADR-0041 must-fix #1） |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v58_executability_audit.md` | BB v5.8 executability audit（Bybit historical liquidations REST 不存在 push back + maker fill rate metric 要求；ADR-0038/0039 push back 來源） |
| `CCAgentWorkSpace/CC/workspace/reports/2026-05-21--v58_executability_audit.md` | CC v5.8 executability audit（16 根原則 vs 13 module thesis 合規檢核） |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-21--v58_executability_audit.md` | E2 v5.8 executability audit（13 module 代碼結構評估） |
| `CCAgentWorkSpace/E3/workspace/reports/2026-05-21--v58_executability_audit.md` | E3 v5.8 executability audit（13 module 安全攻擊面 + autonomy 升級風險） |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-21--v58_executability_audit.md` | E4 v5.8 executability audit（13 module 測試覆蓋預估 + CI 工時影響） |
| `CCAgentWorkSpace/E5/workspace/reports/2026-05-21--v58_executability_audit.md` | E5 v5.8 executability audit（13 module 性能 / 結構優化潛在風險） |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v58_executability_audit.md` | MIT v5.8 executability audit（9 V### schema 工時估算 ~90 MIT-hr + 跨週協調 30-50 hr buffer） |
| `CCAgentWorkSpace/QA/workspace/reports/2026-05-21--v58_executability_audit.md` | QA v5.8 executability audit（13 module 質量門控 + acceptance criteria 風險） |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-21--v58_executability_audit.md` | QC v5.8 executability audit（13 module 數學 / 統計 / 量化合理性） |
| `CCAgentWorkSpace/R4/workspace/reports/2026-05-21--v58_executability_audit.md` | R4 v5.8 executability audit（13 module 文檔 + 編號 + index 漂移分析；本 README index patch 來源） |
| `CCAgentWorkSpace/TW/workspace/reports/2026-05-21--v58_executability_audit.md` | TW v5.8 executability audit（ADR drafts + spec doc 工時 + 文檔成本） |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_business_chain_audit.md` | FA TODO business chain audit（business value chain 完整性核查） |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-21--todo_v61_restructure_proposal.md` | PA TODO v61 restructure proposal（v5.8 land 後 TODO 重組方案 — Sprint 1A-β-ε scope 分段） |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_v61_restructure_proposal.md` | FA TODO v61 restructure proposal（business framing + dispatch readiness checklist 反映 business chain） |
| `CCAgentWorkSpace/QA/workspace/reports/2026-05-21--lg1_lg2_7d_closure_phase2a_t72h_verify.md` | QA LG-1 / LG-2 7-day closure Phase 2a T+72h verify report |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p1_data_lg5_edge_status_reverify.md` | PA P1-DATA / LG-5 edge status re-verify |
| `CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md` | E5 P1-LG-1 demo SLA violation hotpath audit |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md` | BB v5.7 §12 C4/C5/C6 Bybit verdict（trade tape / Earn Guardian / 14 problems business framing review） |

### 2026-05-21 Sprint 1A-γ ADD-per-operator DESIGN + V### full DDL + 2 runbook + 3 R4 ADR

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-21--m2_overlay_state_machine_design_spec.md` | M2 Overlay State Machine DESIGN spec (904 行；5-state FSM + dwell time + flap suppression；Sprint 1A-γ PA) |
| `execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md` | M4 Hypothesis Discovery + V103 EXTEND outline + Cowork hybrid path DESIGN spec (877 行；6 attribute minimum bar + DRAFT writeback；governance authority ADR-0045 reserved per R4 C-1) |
| `execution_plan/2026-05-21--m8_anomaly_detection_design_spec.md` | M8 Anomaly Detection DESIGN spec (688 行；9 event_taxonomy + 9-cell ATR-vol × Funding state) |
| `execution_plan/2026-05-21--m9_ab_framework_design_spec.md` | M9 A/B Framework DESIGN spec (775 行；4 variant cluster + variant Stage 路徑 + mSPRT + AVI) |
| `execution_plan/2026-05-21--m10_discovery_tier_design_spec.md` | M10 Discovery Tier DESIGN spec (~990 行；Tier A-E + capital threshold 7 級 + Tier D 黑名單) |
| `execution_plan/2026-05-21--v105_m2_overlay_state_transitions_schema_spec.md` | V105 M2 overlay state transitions full DDL (1395 行) |
| `execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md` | V108 M9 A/B testing framework full DDL (1508 行；3 table) |
| `execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md` | V109 M8 anomaly events full DDL (1412 行；Guard A+C 雙重黑名單 RAISE 反模式) |
| `execution_plan/2026-05-21--v111_m10_discovery_tier_config_schema_spec.md` | V111 M10 discovery tier config full DDL (1471 行) |
| `runbooks/2026-05-21--m2_overlay_state_runbook.md` | M2 Overlay State operator runbook (421 行) |
| `runbooks/2026-05-21--m9_ab_testing_runbook.md` | M9 A/B Testing operator runbook (587 行) |
| `adr/0042-m3-health-monitoring.md` | ADR-0042: M3 Health Monitoring — Single Health Authority (222 行；R4 建議補) |
| `adr/0043-m6-bayesian-reward-weight.md` | ADR-0043: M6 Bayesian Reward Weight — Portfolio Weight Authority (246 行；R4 建議補) |
| `adr/0044-m7-decay-enforced-single-authority.md` | ADR-0044: M7 Decay + Single Authority + DECAY_ENFORCED + 14d×50% mitigation (246 行；R4 建議補) |

### 2026-05-21 Sprint 1A-δ — interface stubs (M5/M12/M13 + V114/V115/V116；dedup applied per R4)

> **註**：Sprint 1A-δ 多 session dual write 產生 5 pair dup naming；R4 audit 採 ADR-aligned 版本；3 棄置版本見 `docs/archive/2026-05-21--sprint_1a_delta_dup_artifacts/`；M13/V116 pending operator 仲裁 SPLIT vs MERGE。

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-21--m5_online_learning_design_spec.md` | M5 ModelClient Interface DESIGN spec (461 行；6 method per ADR-0035 Decision 1；Y3+ defer；KEEP per R4 dedup) |
| `execution_plan/2026-05-21--m12_order_router_design_spec.md` | M12 OrderRouter DESIGN spec (905 行；6-method trait per ADR-0039 §Decision 1 + maker_fill_rate_30d) |
| `archive/2026-05-21--sprint_1a_delta_dup_artifacts/2026-05-21--m13_multi_venue_asset_class_design_spec.md` | M13 Multi-Venue / AssetClass DESIGN spec (427 行；AssetClass + Venue enum + DEX/Hyperliquid hardcode rejection + 6 trade gate)；**已歸檔 dup artifact**（R4 dedup KEEP parallel session 版本）|
| `execution_plan/2026-05-21--m13_asset_class_venue_design_spec.md` | M13 design parallel session（624 行；5 AssetClass + AUM threshold）；**R4 dedup KEEP active 版本** |
| `execution_plan/2026-05-21--v114_m5_model_versions_streaming_schema_spec.md` | V114 M5 EXTEND `learning.model_versions` PLACEHOLDER (190 行；ADR-0035 Decision 2 對齊；KEEP per R4 dedup) |
| `execution_plan/2026-05-21--v115_m12_order_router_audit_schema_spec.md` | V115 M12 OrderRouter Adaptive Routing Audit PLACEHOLDER (288 行；ADR-0039 §Decision 3；KEEP per R4 dedup) |
| `archive/2026-05-21--sprint_1a_delta_dup_artifacts/2026-05-21--v116_m13_multi_venue_reserved_schema_spec.md` | V116 multi-venue reserved (101 行；routing.venue_lifecycle hint)；**已歸檔 dup artifact**（R4 dedup KEEP asset/venue dim 版本）|
| `execution_plan/2026-05-21--v116_m13_asset_venue_dim_schema_spec.md` | V116 asset/venue dim（288 行；reference.asset_class_dim + venue_dim + Y1 seed）；**R4 dedup KEEP active 版本** |

### 2026-05-21 Sprint 1A-ε deliverables (4 spec; R4+CC+PA+MIT 三化審計)

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md` | V099-V116 migration ordering audit + 12 V### Linux PG dry-run SOP (1223 行；18 V### overview + dependency graph + sqlx checksum repair + 1e-4 fixture harness；MIT) |
| `execution_plan/2026-05-21--mac_ci_13_module_cross_compile_verify_scope_spec.md` | Mac CI 13-module cross-compile verify scope spec (598 行；PR + 週一 cron + 2000 min/月 budget；E5) |
| `execution_plan/2026-05-21--monthly_review_wizard_and_lv3_4_modal_helper_scope_spec.md` | Monthly Operator Review Wizard + Lv 3-4 Modal Helper scope spec (520+ 行；A3 inline draft a12c302e → PM transcribed；8 surface + 7 AC + 8 INV；A3) |
| `execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md` | V103 EXTEND M4 hypothesis discovery 6 column full DDL (MIT inline a4d52063 → PM transcribed；Gap I-A patch；Guard B 6 段 + Linux PG dry-run × 2 round + 3 hot-path index；待 PM Q1 V### naming verdict + DEFAULT 'OPERATOR' vs 'M4_AUTO' 拍板) |
| `adr/0045-m4-hypothesis-discovery-governance.md` | ADR-0045 M4 Hypothesis Discovery Governance Reserved Placeholder (per R4 C-1 ADR-0042 編號衝突修；M4 Sprint 6+ IMPL 啟動前必 dispatch TW 補完整 ADR) |

### 2026-05-21 Sprint 1A-ζ planning (1 spec)

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md` | Sprint 1A-ζ IMPL Prototype Spike Phase Scope Spec (657 行 + §12 operator sign-off + §6 Phase 0 sandbox prep + V107→V113→V112→V106 sequential ordering + Q4a Track C 16-27 hr update；3 track A/B/C；W8.5-10；66-102 hr 含 buffer) |

### 2026-05-22 Sprint 1A-ζ IMPL Prototype Spike — Phase 0~3e artifact

> Sprint 1A-ζ 9 commit chain（Phase 0 sandbox `ad002617` → Phase 1 PA refine `119893d4` → Phase 2 E1×3 並行 IMPL `2f6d1761` → Phase 3a E2 review + E1 round 2 + PA reconcile `f0633002` → Phase 3a parallel AMD v2 + autonomy toggle `01e20db9` → Phase 3b E4 regression `8a15de4d` → Phase 3c QA empirical `26c813fb` → Phase 3d TW Overall Acceptance `db84b748` → Phase 3e PM sign-off）。本 section 補 spike Phase 0/1/2/3 docs/ 內 artifact；既有 spike scope spec / 3 V### schema spec / 3 design spec / Phase 3a PA reconcile / Phase 3d TW Overall Acceptance 索引條目於 Sprint 1A-β / 1A-ζ planning section 不重覆登錄。Track A E1 IMPL + 3 E2 review report 為 inline message handover，無 docs/ 內 file artifact。SQL migrations / Rust code / Python helper scripts / tests 非 docs/README.md 索引範圍。

| 文件 | 内容 |
|------|------|
| `execution_plan/2026-05-21--sprint_1a_zeta_phase0_sandbox_prep_checklist.md` | Sprint 1A-ζ Phase 0 Sandbox + Vault Prep Checklist（414 行；E3 + AI-E sequential 4-6 hr；V096 catch-up + role + Vault TOTP secret + sample fills seed；non-scope = production DB / Console / GUI patch；per spike scope spec §6.1 + §7.2 + §12 Q1d/Q2 operator decision） |
| `execution_plan/2026-05-21--sprint_1a_zeta_3_e1_dispatch_packet.md` | Sprint 1A-ζ Phase 2 — 3 E1 IMPL Dispatch Packet（Track A V112 LAL + Track B V106 health + Track C V107 replay；PA Phase 1 single-thread deliverable；待 Phase 0 sandbox §6 6 confirm PASS 後 PM stagger 5min dispatch 3 並行 sub-agent） |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_phase1_pa_refine.md` | PA Sprint 1A-ζ Phase 1 PA Refine Closure Report（single-thread 4-6 hr；5 critical patch P-5/P-6/P-7/P-8/P-9 close + 3 E1 dispatch packet 撰寫 + Phase 0 → Phase 1 → Phase 2 sign-off chain；verdict READY for Phase 2 dispatch） |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1a_zeta_track_b_m3_health_v106_impl.md` | E1 Sprint 1A-ζ Phase 2 Track B IMPL Round 1（M3 4-state ladder + V106 PG apply + amp cap 24h fire；3 task；health/mod.rs 516 LOC + tests/m3_amp_cap_24h_fire.rs 213 LOC；IMPL DONE → 待 E2 round 1 + E4 + QA） |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1a_zeta_track_b_m3_health_v106_impl_round2.md` | E1 Sprint 1A-ζ Phase 3a Track B Round 2 Fix（E2 round 1 catch 7 findings 全 closure：1 CRITICAL 6-domain naming + 1 HIGH amp cap fire 語意 drift + 3 MEDIUM + 2 LOW；READY for E2 round 2 re-review） |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1a_zeta_track_c_v107_m11_spike.md` | E1 Sprint 1A-ζ Phase 2 Track C IMPL（V107 sandbox PG apply + M11 Python skeleton spike_trigger + divergence_d1_fill_chain + AC-6 dedup contract empirical；per Q4a override +5-10 hr scope） |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3b_regression.md` | E4 Sprint 1A-ζ Phase 3b Regression Report（PASS；6 AC hard-gate PASS 含 AC-4 PG CHECK 反向 + AC-5 amp cap 24h fire + AC-6 dedup contract + AC-7 1e-4 fixture PoC；Mac Rust 3074-3769 pass / 0 fail；pytest 6037 pass / 28 pre-existing fail；兩遍 non-flaky；5 carry-over） |
| `CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3c_qa_empirical_verify.md` | QA Sprint 1A-ζ Phase 3c Empirical Verify Report（PASS WITH 3 CARRY-OVER；AC-2/3/4/5/6/7 全 PASS + AC-1 PARTIAL 沿用 E4 同手法 sandbox _sqlx_migrations 0 row + 1 NEW-QA-1 spec § AC-1.1 反向 INSERT 補 cohort_min_n / human_final_review NOT NULL） |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_pm_phase_3e_signoff.md` | PM Sprint 1A-ζ Phase 3e Sign-off + Final Verdict（SIGNED-OFF；PASS WITH 3 CARRY-OVER per spec §5.3；8 AC verdict 拍板 + 9 PM sign-off carry-over routing + Sprint 1A-ε P1 7 條 + Sprint 1B 6 條 + Sprint 4+ 3 條 deploy-time verify；Sprint 1B 派發 readiness gate OPEN） |

### 2026-05-22 Sprint 2 — M3 metric emitter Wave 1+2 IMPL

| 文件 | 內容 |
|------|------|
| `execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` | Sprint 2 M3 metric emitter design spec（6 Track × Wave 1+2 + D1 sysinfo + D2 並行 + D3 cascade reject log emit minimal + AC-1a/AC-1b 拆分 + §5.0 OBSERVE-4 invariant + §3.2 ApiLatencySample 8 field + §6.2 anomaly_id 命名表 api_latency 8 literal）|
| `execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` | Sprint 2 dispatch packet（6 Track × Wave 1+2 派發 + Phase chain estimate + 9 元素齊 + §1.6.1 AC-1a/1b 拆分契約 + §1.7 Track A scaffold contract 含 OBSERVE-4 guard + §5.x Track D PA-DRIFT-4 carry-over + §7.4 Track F position_count_active ladder）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_readiness_signoff.md` | PA Sprint 2 Phase 1 readiness sign-off（D1/D2/D3 整合 + Sub-agent ceiling 預警 + 6 Track 派發 readiness OPEN with carry-over conditions）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave1_m3_spec_amend.md` | PA Sprint 2 Wave 1 spec amend（4 finding：Track B HIGH-2 持續 2min semantic + MEDIUM-1 drift/signal threshold + Track C MEDIUM-1 pool_max_conn 5th column + MEDIUM-3 disconnected fail-closed OK band；M3 spec §2.3.1/§2.3.2 新節）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave1_packet_ac1_split_fix.md` | PA Sprint 2 Wave 1 packet AC-1 split fix（HIGH-3 AC-1 sign-off 不可達 Wave 1 phase + LOW-1 描述粗略；6 Track AC-1 拆 a/b：AC-1a in-memory mock fixture + AC-1b Sprint 4 first Live real PG empirical）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave2_track_def_spec_amend.md` | PA Sprint 2 Wave 2 spec amend（4 finding：Track D CRIT-1 ApiLatency 5→8 field + MED-1 OBSERVE-4 replay guard 升 Track A scaffold contract + HIGH-3 PA-DRIFT-4 bybit instrumentation prerequisite false + Track F MED-1 position_count_active ladder；M3 spec §2.3.3 + Sprint 2 spec §5.0 新節）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_engine_runtime.md` | E1 Sprint 2 Wave 1 Track A engine_runtime + scaffold owner + D3 cascade reject IMPL（sysinfo "0.32" + DomainEmitter trait + RollingWindowAggregator + HealthObservationWriter + HealthEventBus + observe_classified + 6 metric × 5 sample = 30 row tick + D3 evidence_json reject_reason 2 reason emit；scaffold ~2280 LOC）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_round2_fix.md` | E1 Sprint 2 Track A round 2 fix（E2 round 1 REJECT 6 finding closure：HIGH-1 D3 cascade reject_reason false positive + HIGH-2 recovery dwell anchor 升階方向 + MEDIUM-1 async lock 跨 await + MEDIUM-2 dwell_time_sec hardcoded 0 + LOW-2 cosmetic；is_anomaly_capped + infer_reject_reason pub helper DRY pattern）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_round2_combined_fix.md` | E1 Sprint 2 Wave 1 round 2 combined fix（Track A scaffold round 3 + Track B round 2 + Track C round 2；5 deterministic fix：Track A MEDIUM-2 mean.round() cast + Track C HIGH-1 classify_aggregated 加 database_pool 3 arm + HIGH-2 test assert + Track B HIGH-1 heartbeat CRITICAL revert + Track C MEDIUM-2 doc TODO）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_round3_pa_dependent_fix.md` | E1 Sprint 2 Wave 1 round 3 PA-dependent fix（Track B 2 doc fix + Track C 3 fix：Track B HIGH-2 doc 對齊 §2.3.1 + MEDIUM-1 doc 引 §2.3 line 102 amend；Track C MEDIUM-1 C Path A pool_max_conn 5th column + MEDIUM-3 disconnected fail-closed OK band + evidence_json 寫入）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_d_api_latency.md` | E1 Sprint 2 Wave 2 Track D api_latency IMPL（ApiLatencySample 8 field rest_p50/p95/p99 + ws_rtt_p50/p99 + ret_4xx/5xx + ws_dropout；4 含 CRITICAL + 4 不含；ApiLatencySourceProbe trait + Arc<dyn> 注入；scaffold reuse 8/8；7/7 integration test PASS）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_e_strategy_quality.md` | E1 Sprint 2 Wave 2 Track E strategy_quality IMPL（StrategyQualitySample 5 field + 4 metric × 4 band classify + signal_count_24h telemetry-only + 25 pair × 4 metric = 100 SM + 1 aggregate SM + aggregate rule degraded_count/total_count > 0.40 → DEGRADED + 獨立 StrategyQualityScheduler；strategy_quality.rs 1489 LOC）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_f_risk_envelope.md` | E1 Sprint 2 Wave 2 Track F risk_envelope IMPL（RiskEnvelopeSample 5 field cum_pnl + max_dd + position_count_active + correlation_avg + concentration_top1；ladder 1:1 對齊 M3 spec §2.3 line 106；對 user prompt 7 metric push back governance docs SSOT；emit DEGRADED 不觸 5-gate kill）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_round2_combined_fix.md` | E1 Sprint 2 Wave 2 round 2 combined fix（Track D 6 + E 3 + F 1 + Cross-Wave OBSERVE-4：Track D CRIT-1 doc 對齊 + HIGH-1 line 104 amend reference + HIGH-2 trait 8 method `_60s_window` 後綴 + Track E HIGH-1 aggregate pair-level OR-aggregate Path A + 3 boundary test + LOW-1 expand 100 SM + LOW-3 rename；OBSERVE-4 fix M3Error::ReplaySubprocessForbidden variant + 雙 scheduler guard + 12 caller site cascade + replay_forbidden 3 test）|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_2_phase_3b_regression.md` | E4 Sprint 2 Phase 3b regression（PASS；cargo workspace 3894/0/4 ignored × 2 runs non-flaky；6 Track integration 51/51 + spike 3/3 + health:: 87/0 + governance::lal:: 15/0；pytest 6042/28 兩遍 non-flaky；cross-lang Python 7/7 + Rust binding 5/5 FULL；cross-platform aarch64-apple-darwin clean；nm 0 hit；4 carry-over）|
| `CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_2_phase_3c_qa_empirical_verify.md` | QA Sprint 2 Phase 3c empirical verify（PASS WITH 1 EXPECTED CARRY-OVER；AC-1a in-memory 51/51 + AC-2 6 ladder + AC-3 amp cap 3/3 + AC-4 5 cross-domain + AC-5 nm 0 + AC-6 baseline 不退 + OBSERVE-4 3/3 + PA spec amend 9/9 對齊；AC-1b PARTIAL DEFER to Sprint 4 deploy + AC-7 OPEN-CARRY-OVER bench fixture 未 IMPL；5 carry-over）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_overall_acceptance.md` | TW Sprint 2 M3 metric emitter Overall Acceptance Report（PASS WITH 5 CARRY-OVER；Phase 0-3c chronology + 6 Track Acceptance + AC-1a/1b/2/3/4/5/6/7 + OBSERVE-4 verdict map + Lessons Learned 6 條 + Sprint 4+ 4 條 + Sprint 5+ 4 條 + Doc+lint 3 條 carry-over；待 PM Phase 3e 拍板）|

### 2026-05-21 Sprint 1A closure narrative + acceptance evidence + 三化審計

| 文件 | 内容 |
|------|------|
| `audits/2026-05-21--sprint_1a_acceptance_evidence.md` | FA Sprint 1A 6 欄 acceptance audit (grade A；揭露 RUNTIME-NOT-APPLIED 真相；48 條目 0✅ 真 IMPL / 47⚠️ DESIGN-DONE / 1❌) |
| `archive/2026-05-21--sprint_1a_alpha_repair_closure.md` | Sprint 1A α+修補+β+γ+δ canonical closure narrative §A-§K |
| `archive/2026-05-21--sprint_1a_delta_dup_artifacts/README.md` | Sprint 1A-δ multi-session dual write 棄置 file 歸檔說明 (5 file archived per R4 + PA dedup audit 2026-05-21；M5/V114/V115/M13/V116 棄置版本 + dedup decision narrative) |
| `archive/2026-05-21--todo_v60_archive.md` | TODO v60 archive：v57 12 prefix DONE + W-AUDIT-4b retained + H+I 批 closure + 9 批 narrative (v61 起以 v5.8 為主軸) |
| `archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md` | v80 cold audit 全閉環歸檔：17 P1 + 15/17 P2 + 7/7 P3 source-done 逐項 + commit map (b93d3210/11b9531f/7909ca3d/dc2a15aa/f2b020e5) + review chain catch；P2-06/07 design-deferred；runtime deploy-gate 殘留 |

### 2026-05-21 v5.7/v5.8 reference ADR list (baseline cross-ref per R4 NEW-M-5)

| 文件 | 内容 |
|------|------|
| `adr/0021-alpha-source-architecture-upgrade.md` | ADR-0021 Alpha Source Architecture Upgrade (v5.8 M6 / V110 cite 來源) |
| `adr/0024-cowork-subscription-operator-assistant.md` | ADR-0024 Cowork operator-assistant (v5.8 M4 Cowork hybrid path + AMD-2026-05-21-01 protected scope (j) 來源) |
| `adr/0030-copy-trading-evidence-gated.md` | ADR-0030 Copy Trading evidence-gated (v5.8 M11 counterfactual_quality_report runbook 對接；Y1 末 Sprint 10 Evidence Gate 數據準備) |
| `adr/0031-framework-expansion-earn-macro-onchain.md` | ADR-0031 Earn / Macro / On-chain framework expansion (Earn governance spec 對應 governance ADR) |
| `adr/0032-bybit-earn-asset-movement-guardian.md` | ADR-0032 Bybit Earn 5-Gate Adapter (Earn governance runbook 對應 governance ADR) |
| `adr/0033-adr-0006-bybit-binance-amendment.md` | ADR-0033 Bybit-Binance amendment (v5.8 M13 ADR-0040 amendment 基線；Binance market-data only Y3+ at earliest) |

### 2026-05-16 12-agent consolidated audit + Wave 1-4 (WP-01..13)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-16--12-agent-consolidated-fix-plan.md` | PA 12-agent consolidated audit fix plan：FA/AI-E/QC/E5/A3/E3/MIT/R4/BB/CC finding 驗證 + 修復優先排序 |
| `CCAgentWorkSpace/Operator/2026-05-16--12-agent-consolidated-fix-plan.md` | Operator brief：12-agent consolidated fix plan |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-16--full-scope-testing-audit.md` | E4 full-scope testing audit |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-16--12-agent-audit-pm-signoff.md` | PM 12-agent audit sign-off report |
| `CCAgentWorkSpace/Operator/2026-05-16--12-agent-audit-pm-signoff.md` | Operator brief：12-agent audit PM sign-off |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md` | PM cleanup：Stage 1 promotion is Demo-only; A4-C active marker reduced to diagnostic-only tombstone |
| `CCAgentWorkSpace/Operator/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md` | Operator brief：Stage 1 Demo + A4-C tombstone cleanup |
| `CCAgentWorkSpace/E1a/workspace/reports/2026-05-16--wp01_gui_safety_round1.md` | WP-01 GUI safety Round 1 sign-off（typed-phrase × 4 + LinUCB dead buttons + bilingual + native→modal）|
| `CCAgentWorkSpace/E1a/workspace/reports/2026-05-16--wp01_gui_real_fix.md` | WP-01 GUI Round 2 補修（A3-MAJOR-2 unify / 雙層 modal 拆 / 第 6 metric / 繁簡 / modal lock）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp02_donchian_deprecate.md` | WP-02 Donchian deprecate sign-off（hygiene-only + audit drift 第 3 次教訓）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp05_security_hardening.md` | WP-05 security Round 1 sign-off（bind 0.0.0.0 + global exception handler）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp05_security_real_fix.md` | WP-05 security Round 2 真修（17 routes 38 callsite + handler 順位 + error_sanitize helper）|
| `CCAgentWorkSpace/TW/workspace/reports/2026-05-16--wp09_doc_real_fix.md` | WP-09 doc Round 2 補修（README 126 entries / KNOWN_ISSUES reconcile / REF-21 SUPERSEDED / WP-01/02 sign-off）|
| `CCAgentWorkSpace/A3/workspace/reports/2026-05-16--wp01_round2_re_audit.md` | A3 WP-01 Round 2 對抗審核（8.5/10 GO-conditional）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp03_ou_sigma_fix.md` | WP-03 OU sigma residual (OLS n-2 dof) sign-off（grid_helpers.rs +170 LOC + 5 new test） |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp04_ai_observability.md` | WP-04 AI obs+budget sign-off（F-04 record_strategist_invocation + F-01 budget drift fix + F-09 TODO）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp10_bybit_integration.md` | WP-10 Bybit sign-off（BB-A-1 ReduceOnlyReject=110017 + BB-M-1 backtest URL env var）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--reject_cooldown_split_bbmf3.md` | BB-MF-3 reject_cooldown entry/close split sign-off（grid_trading 5 files + 8 new test）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp06_wp08_python_fixes.md` | Wave 3 WP-06 deepcopy 3→2 + WP-08 engine_mode + purge_days sign-off |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp13_reconciler_cmd_tx.md` | Wave 3 WP-13 demo reconciler DemoCmdSenderSlot sign-off |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-16--wave2_3_full_regression.md` | E4 Wave 2-3 full regression (7366 cases Mac-side PASS) |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-16--wave2_wp{03,04,06,08,10,13}_retroactive_review.md` | E2 retroactive review × 6 WP（補 chain breach） |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-16--bbmf3_retroactive_review.md` | E2 retroactive review BB-MF-3（APPROVE-CONDITIONAL） |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-16--wave2_wp10_bbmf3_round3_bb_review.md` | BB Wave 2 WP-10 + BB-MF-3 Round 3 review（APPROVE-COND）|
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-16--bb_dict_110017_patch.md` | BB 字典 §4.2 110017 ReduceOnlyReject row 補完 |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-16--mit_cron_reconcile.md` | PA reconcile MIT-P0-2「6/12 cron 未裝」= **FALSE FINDING**（廣口徑漂移）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-15--v094_schema_migration_spec_pa_verdict.md` | PA Wave 2a Track A2 V094 spec finalize verdict |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-15--wave_1_5b_spec_v1_3_amd_v0_4_consolidated.md` | PA Wave 1.5b spec v1.3 + AMD v0.4 consolidated |
| `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` | V094 hybrid schema migration spec（Wave 2a Track A2，commit 9b1117a0）|
| `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` | AMD-2026-05-15-02 v0.4（EDGE-P2-3 Phase 1b 4-agent re-review consolidated）|
| Wave 2 IMPL commit `ef6ea79f` | WP-03 OU sigma + WP-04 AI obs + WP-07 dead code + WP-10 Bybit retCode |
| Wave 2b BB-MF-3 IMPL commit `27f02a07` | reject_cooldown entry/close split (Wave 2b recovery) |
| Wave 3 IMPL commit `f31b6e8f` | WP-06 deepcopy 3→2 + WP-08 engine_mode + purge_days + WP-13 demo reconciler |
| Wave 4 WP-11 commit `564c9db6` | 15 failing Python tests fix (16→1 flaky) |
| Wave 4 closure commit `fca27914` | WP-11 DONE + WP-12 DEFERRED |

### 2026-05-11 Sprint N+1 dispatch + W-D + LG design

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md` | PA MAG-083 三角 audit |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md` | PA W2 A4-C IMPL v1.2 dispatch plan |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_v083_ipc_close_fix_design.md` | PA P1 V083 IPC close fix design |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md` | PA P1 RCA1 F1/F2 emergency fix plan |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_22h08_deploy_edge_regression_rca.md` | PA P0 22h08 deploy edge regression RCA |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md` | PA P0 option A position state SSOT refactor |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_strategist_params_persist_ma_crossover_rca.md` | PA P1 Strategist params persist MA crossover RCA |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p2_n2_backlog_tickets.md` | PA P2 N+2 backlog tickets |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--f3_f4_writer_defense_n1_dispatch_plan.md` | PA F3/F4 writer defense N+1 dispatch plan |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_replay_engine_counterfactual_fix_design.md` | PA P0 replay engine counterfactual fix design |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` | PA LG-2/3/4 design plan |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md` | PA LG-3 spec v1 |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md` | PA LG-3 spec v2 final |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md` | PA close-maker-first verdict |

#### 2026-05-11 owner reports — E1 (39)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_2_p2_1_bb_breakout_w7_propagation.md` | E1 P1-2 / P2-1 bb_breakout W7 propagation |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_2_btc_lead_lag_producer_v088_writer.md` | E1 W2 IMPL 2: BTC→Alt Lead-Lag producer V088 writer |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w1_impl_alpha_panel_aggregator_v085_writer.md` | E1 W1 IMPL alpha panel_aggregator V085 writer |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w1_impl_beta_oi_delta_aggregator_v087_writer.md` | E1 W1 IMPL beta oi_delta_aggregator V087 writer |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w1_impl_gamma_ws_subscription_main_loop.md` | E1 W1 IMPL gamma WS subscription main loop |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl.md` | E1 W-C fix Rust impl |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_3_strategy_paper_shadow_log.md` | E1 W2 IMPL 3: strategy paper shadow log |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl_round2.md` | E1 W-C fix Rust impl round 2 |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_5_ipc_slot_main_spawn_step_4_5_wire.md` | E1 W2 IMPL 5: IPC slot main spawn step 4/5 wire |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_1_stable_id_helper.md` | E1 P1-1 stable_id_helper |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_rca1_orphan_er_missed_fill.md` | E1 P1 RCA1 orphan ER missed fill |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_v083_ipc_close_impl_done.md` | E1 P1 V083 IPC close IMPL DONE |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_3_check_57.md` | E1 W2 IMPL 3 check 57 |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_4_paper_edge_report.md` | E1 W2 IMPL 4: paper edge report |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_1_orderbook_wiring.md` | E1 W2 IMPL 1: orderbook wiring |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_4_sql_fix.md` | E1 W2 IMPL 4 SQL fix |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_d_grid_trading.md` | E1 option-A-lite grid_trading |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_e_funding_arb.md` | E1 option-A-lite funding_arb |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_b_bb_reversion.md` | E1 option-A-lite bb_reversion |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_c_bb_breakout.md` | E1 option-A-lite bb_breakout |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_a_ma_crossover.md` | E1 option-A-lite ma_crossover |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p2_v083_cron_synthetic_id_recognition.md` | E1 P2 V083 cron synthetic ID recognition |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_2_replay_counterfactual_validation.md` | E1 option-2 replay counterfactual validation |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_2_replay_engine_validation_v2.md` | E1 option-2 replay engine validation v2 |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_b_manifest_config_echo.md` | E1 replay tier A: manifest config echo |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_a_runner_position_state.md` | E1 replay tier A: runner position state |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_c_per_symbol_price.md` | E1 replay tier A: per-symbol price |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_d_acceptance_pack.md` | E1 replay tier A: acceptance pack |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_27h_validation_run.md` | E1 replay tier A 27h validation run |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_stable_id_helper_impl.md` | E1 P1 stable ID helper impl |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_fill_lineage_drop_fix.md` | E1 P1 fill-lineage drop fix |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t4_h0_block_summary_route.md` | E1 LG-1 T4 H0 block summary route |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t3_h0_flip_runbook_ctor.md` | E1 LG-1 T3 H0 flip runbook ctor |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t1_h0_blocking_test.md` | E1 LG-1 T1 H0 blocking test |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t4_riskconfig_pricing.md` | E1 LG-2 T4 RiskConfig pricing binding |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t2_h0_block_acceptance.md` | E1 LG-1 T2 H0 block acceptance |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t1_contract_tests.md` | E1 LG-2 T1 contract tests |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t3_fee_source_enum.md` | E1 LG-2 T3 FeeSource enum + IPC route |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t2_startup_assertion.md` | E1 LG-2 T2 startup assertion |

#### 2026-05-11 owner reports — E2 (10)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w_c_fix_e2_review_round2.md` | E2 W-C fix review round 2 |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_1_stable_id_helper_e2_review.md` | E2 P1-1 stable_id_helper review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_v083_p2_freq_e2_review.md` | E2 P1 V083 P2 frequency review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_chain_e2_adversarial_review.md` | E2 W2 chain adversarial review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_impl_4_sql_fix_e2_review.md` | E2 W2 IMPL 4 SQL fix review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_impl_5_e2_review.md` | E2 W2 IMPL 5 review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--option_a_lite_post_merge_audit.md` | E2 option-A-lite post merge audit |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--replay_tier_a_post_impl_audit.md` | E2 replay tier A post-IMPL audit |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_fill_lineage_drop_e2_review.md` | E2 P1 fill-lineage drop review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--wave2_2_lg1_lg2_e2_review.md` | E2 Wave 2.2 LG-1/LG-2 review |

#### 2026-05-11 owner reports — E4 (10)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_c_fix_e4_regression.md` | E4 W-C fix regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--p1_v083_p2_freq_e4_regression.md` | E4 P1 V083 P2 frequency regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_chain_e4_regression.md` | E4 W2 chain regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_impl_4_sql_fix_e4_redryrun.md` | E4 W2 IMPL 4 SQL fix re-dry-run |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_impl_5_e4_regression.md` | E4 W2 IMPL 5 regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--option_a_lite_post_merge_regression.md` | E4 option-A-lite post merge regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--replay_tier_a_post_impl_regression.md` | E4 replay tier A post-IMPL regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_audit_3b_runtime_smoke.md` | E4 W-AUDIT-3b runtime smoke |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--p1_fill_lineage_drop_e4_regression.md` | E4 P1 fill-lineage drop regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--wave2_2_e4_regression.md` | E4 Wave 2.2 regression |

#### 2026-05-11 owner reports — QC (3)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-11--w_d_mag083_qc_audit.md` | QC W-D MAG-083 audit |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md` | QC P1 micro profit amplification 數學分析 |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-11--lg3_spec_qc_review.md` | QC LG-3 spec review |

#### 2026-05-11 owner reports — MIT (1) / A3 (1) / PM (1)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-11--lg3_spec_mit_review.md` | MIT LG-3 spec review |
| `CCAgentWorkSpace/A3/workspace/reports/2026-05-11--wave2_2_a3_ux.md` | A3 Wave 2.2 UX review |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-11--amd_w6_1_pm_consolidate_signoff.md` | PM AMD-W6-1 consolidate sign-off |

#### 2026-05-11 owner reports — Operator briefs (5)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/Operator/2026-05-11--p1_v083_ipc_close_fix_design.md` | Operator brief: P1 V083 IPC close fix design |
| `CCAgentWorkSpace/Operator/2026-05-11--p0_22h08_deploy_edge_regression_rca.md` | Operator brief: P0 22h08 deploy edge regression RCA |
| `CCAgentWorkSpace/Operator/2026-05-11--p1_strategist_params_persist_ma_crossover_rca.md` | Operator brief: P1 Strategist params persist MA crossover RCA |
| `CCAgentWorkSpace/Operator/2026-05-11--lg_3_spec_v1.md` | Operator brief: LG-3 spec v1 |
| `CCAgentWorkSpace/Operator/2026-05-11--lg_3_spec_v2_final.md` | Operator brief: LG-3 spec v2 final |

#### 2026-05-10 owner reports — E1 (18)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_audit_8a_phase_a_trait_alpha_surface.md` | E1 W-AUDIT-8a Phase A trait AlphaSurface |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_audit_4b_m3_part_2_rust_producer_emit_reject.md` | E1 W-AUDIT-4b M3 part 2 Rust producer emit reject |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_3_emergency_1tick_defense.md` | E1 W7-3 emergency 1-tick defense |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w2_w7_1_trait_skeleton_prewrite.md` | E1 W2/W7-1 trait skeleton prewrite |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_v086_sql_skeleton_prewrite.md` | E1 W6 V086 SQL skeleton prewrite |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_2_ma_crossover_bb_reversion_entry_path_query.md` | E1 W7-2 ma_crossover/bb_reversion entry path query |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_5_on_fill_bootstrap_import_positions.md` | E1 W7-5 on_fill bootstrap import positions |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w2_v088_btc_lead_lag_panel_sql_skeleton_prewrite.md` | E1 W2 V088 BTC lead-lag panel SQL skeleton prewrite |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w1_v087_sql_skeleton_prewrite.md` | E1 W1 V087 SQL skeleton prewrite |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_3c_v086_impl_dry_run_writer_code.md` | E1 W6-3c V086 IMPL dry-run writer code |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w5_e1_c_dynamic_unblock_check_1_impl.md` | E1 W5 dynamic-unblock-check-1 IMPL |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v085_087_088_dry_run_apply.md` | E1 V085/087/088 dry-run apply |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w5_e1_a_canary_stage_criteria_1_impl.md` | E1 W5 canary-stage-criteria-1 IMPL |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v089_dry_run_apply.md` | E1 V089 dry-run apply |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--check_65_chain_integrity_post_m3_impl.md` | E1 check 65 chain integrity post-M3 IMPL |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v091_decision_features_mutex_check_impl.md` | E1 V091 decision_features mutex check IMPL |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--p1_1_bb_reversion_w7_3_propagation.md` | E1 P1-1 bb_reversion W7-3 propagation |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_c_fix_python_impl.md` | E1 W-C fix Python impl |

#### 2026-05-10 owner reports — E2 (4)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-10--sprint_n0_w2_second_batch_review.md` | E2 Sprint N+0 W2 second batch review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-10--sprint_n0_w2_third_pass_review.md` | E2 Sprint N+0 W2 third pass review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-10--w7_3_review.md` | E2 W7-3 review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-10--w_c_fix_e2_review.md` | E2 W-C fix review |

#### 2026-05-10 owner reports — E4 (5) / E5 (1)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--sprint_n0_w2_regression_baseline.md` | E4 Sprint N+0 W2 regression baseline |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--sprint_n0_w2_regression_third_pass.md` | E4 Sprint N+0 W2 regression third pass |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w7_3_regression.md` | E4 W7-3 regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w_audit_3b_runtime_smoke_test_design.md` | E4 W-AUDIT-3b runtime smoke test design |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w4_router_lease_guard_drop_test_prewrite.md` | E4 W4 RouterLeaseGuard drop test prewrite |
| `CCAgentWorkSpace/E5/workspace/reports/2026-05-10--w_c_fix_e5_perf_review.md` | E5 W-C fix perf review |

#### 2026-05-10 owner reports — QC (5)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--tonusdt_structural_edge_replay.md` | QC TONUSDT structural edge replay |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_rfc_qc_questions_self_answer.md` | QC W6 RFC questions self-answer |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w2_a4c_qc_review_alpha_decay_dsr.md` | QC W2 A4-C alpha decay / DSR review |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_1_rfc_qc_signoff_verdict.md` | QC W6-1 RFC sign-off verdict |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--amd_w6_1_qc_verify.md` | QC AMD-W6-1 verify |

#### 2026-05-10 owner reports — MIT (9)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--sprint_n0_final_review.md` | MIT Sprint N+0 final review |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--v083_v084_linux_pg_dry_run_verify.md` | MIT V083/V084 Linux PG dry-run verify |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--chain_integrity_historical_replay.md` | MIT chain integrity historical replay |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--governance_reject_baseline_w6_rfc.md` | MIT governance reject baseline W6 RFC |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_rfc_mit_questions_self_answer.md` | MIT W6 RFC questions self-answer |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_3a_close_tag_distribution_audit.md` | MIT W6-3a close tag distribution audit |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w2_c3_sigma_verify_btcusdt_1m_forward_return.md` | MIT W2-C3 sigma verify BTCUSDT 1m forward return |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md` | MIT W6-1 RFC sign-off verdict |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--amd_w6_1_mit_verify.md` | MIT AMD-W6-1 verify |

#### 2026-05-10 owner reports — BB (2) / CC (1) / R4 (1)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-10--sprint_n0_final_bybit_compatibility_review.md` | BB Sprint N+0 final Bybit compatibility review |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-10--w1_w2_bybit_v5_rate_budget_review.md` | BB W1/W2 Bybit V5 rate budget review |
| `CCAgentWorkSpace/CC/workspace/reports/2026-05-10--n1_d0_signoff_compliance_pre_check.md` | CC N+1 D+0 sign-off compliance pre-check |
| `CCAgentWorkSpace/R4/workspace/reports/2026-05-10--n1_d0_docs_audit_pre_signoff.md` | R4 N+1 D+0 docs audit pre-sign-off |

#### 2026-05-10 owner reports — PM (5) / Operator briefs (6)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--n1_d1_second_day_dispatch_sop.md` | PM N+1 D+1 second-day dispatch SOP |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--live_today_pnl_gui_fix.md` | PM live today PnL GUI fix |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--n0_high5_signoff_draft.md` | PM N+0 HIGH-5 sign-off draft |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--live_demo_pnl_series_gui.md` | PM live demo PnL series GUI |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--live_demo_pnl_series_refresh_fix.md` | PM live demo PnL series refresh fix |
| `CCAgentWorkSpace/Operator/2026-05-10--pa_governance_4docs_invariant17_closure.md` | Operator brief: PA governance 4 docs invariant 17 closure |
| `CCAgentWorkSpace/Operator/2026-05-10--a4c_btc_alt_lead_lag_spec.md` | Operator brief: A4-C BTC→Alt Lead-Lag spec |
| `CCAgentWorkSpace/Operator/2026-05-10--live_today_pnl_gui_fix.md` | Operator brief: live today PnL GUI fix |
| `CCAgentWorkSpace/Operator/2026-05-10--live_demo_pnl_series_gui.md` | Operator brief: live demo PnL series GUI |
| `CCAgentWorkSpace/Operator/2026-05-10--w6_1_rfc_pa_signoff_verdict.md` | Operator brief: W6-1 RFC PA sign-off verdict |
| `CCAgentWorkSpace/Operator/2026-05-10--live_demo_pnl_series_refresh_fix.md` | Operator brief: live demo PnL series refresh fix |

### 2026-05-15 PM/PA/FA 5-day audit + current-state sync

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--pm_pa_fa_5day_audit_todo_sync.md` | PM/PA/FA 5 日工作质量、TODO/README/MEMORY stale 核查、排序重整与三端同步结果 |
| `CCAgentWorkSpace/Operator/2026-05-15--pm_pa_fa_5day_audit_todo_sync.md` | Operator brief：PM/PA/FA audit verdict、当前事实、重排优先级和 Linux sync blocker |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_oi_confirmed_5m_preflight.md` | `bb_breakout_oi_confirmed_5m` Stage 0R replay packet spec；spec-only，未执行 replay，`eligible_for_demo_canary=false` |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_oi_confirmed_5m_feasibility_probe.md` | `bb_breakout_oi_confirmed_5m` read-only feasibility probe；data surface healthy but runtime-style rows underpowered/negative，仍不可作 promotion evidence |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--post_rebuild_sync_7b33ab2e.md` | Post-rebuild sync：runtime code line `7b33ab2e` rebuilt；`[27]` immediate PASS under fresh-restart grace，post-grace closure tracked separately |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--alpha_path_phase_c_dispatch.md` | Alpha path dispatch：A4-C remains GATE-RED；W-AUDIT-8a Phase C split into C0 inventory / C1 revival；current TODO 8b/8c naming made canonical |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--p1_intent_freeze_27_post_grace_closure.md` | `[27] intents_counter_freeze` post-grace direct PASS closure；`[66]`/`[67]` remain PASS；Stage 1 demo still blocked by alpha gates |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8a_phase_c0_liquidation_inventory.md` | W-AUDIT-8a Phase C0 liquidation revival inventory：DB/table/retention/source status + production topic guard test + C1 BB probe contract |
| `execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md` | W-AUDIT-8a C1 standalone proof plan：official `allLiquidation.{symbol}` topic, isolated 24h BB probe contract, output files, and production boundary |
| `execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` | W-AUDIT-8b Funding Skew Directional spec v0.2：cross-sectional crowding signal using FundingSkew + OIDeltaPanel, with QC/MIT/BB Stage 0R design constraints |
| `execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` | EDGE-P2-3 Phase 1b Close-Maker-First spec：close path maker-first refactor, 3-phase rollout, V094 migration design |
| `execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md` | A4-C archive verdict：Stage 0R Step 5b failed the R² archive rule, so BTC→Alt Lead-Lag is diagnostic-only and no longer a promotion candidate |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_unblock_engineering_card.md` | A4-C PM/PA/FA engineering card：archive from promotion, allow only read-only `P1-A4C-RCA-1`, and block demo budget unless a future preregistered Stage 0R packet is green |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_stage0r_rca_start.md` | A4-C `P1-A4C-RCA-1` read-only RCA start：current 7d dry-run and finite threshold probe both remain below promotion/revive bands |
| `CCAgentWorkSpace/Operator/2026-05-15--a4c_unblock_engineering_card.md` | Operator brief for A4-C archive/RCA card |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--micro_profit_alpha_prework.md` | PM report for P0-MICRO-PROFIT prework：C1 probe packet, 8b spec, A4-C archive verdict, TODO/active-plan sync |
| `CCAgentWorkSpace/Operator/2026-05-15--micro_profit_alpha_prework.md` | Operator brief for P0-MICRO-PROFIT alpha prework |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--todo_v30_three_side_sync.md` | TODO v30 source-sync checkpoint：remove stale active docs sync wording and record source-only Mac/origin/Linux sync boundary |
| `CCAgentWorkSpace/Operator/2026-05-15--todo_v30_three_side_sync.md` | Operator brief for TODO v30 source-only three-side sync |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_rca_final_and_c1_proof_start.md` | A4-C RCA final + C1 proof start：QC/MIT close `P1-A4C-RCA-1` no-revive and start 24h isolated `allLiquidation.BTCUSDT` proof on `trade-core` |
| `CCAgentWorkSpace/Operator/2026-05-15--a4c_rca_final_and_c1_proof_start.md` | Operator brief for A4-C no-revive RCA closure and running C1 proof |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8b_review_stage0r_design.md` | W-AUDIT-8b Funding Skew review + Stage 0R design：QC/MIT/BB conditional approve design-only with locked K/DSR/PBO, raw panel joins, and funding attribution boundaries |
| `CCAgentWorkSpace/Operator/2026-05-15--w_audit_8b_review_stage0r_design.md` | Operator brief for W-AUDIT-8b review/design checkpoint |
| `CCAgentWorkSpace/Operator/2026-05-15--stage0r_preflight_verification.md` | Operator brief for Stage 0R preflight verification |
| `CCAgentWorkSpace/Operator/2026-05-15--passive_healthcheck_7108035d_plan_sync.md` | Operator brief for passive healthcheck 7108035d plan sync |
| `CCAgentWorkSpace/Operator/2026-05-15--feature_baseline_restore.md` | Operator brief for W-AUDIT-4b feature baseline restore |
| `CCAgentWorkSpace/Operator/2026-05-15--stage0r_preflight_step5b.md` | Operator brief for A4-C Stage 0R Step 5b runtime verification |
| `CCAgentWorkSpace/Operator/2026-05-15--p1_healthcheck_55_invariant.md` | Operator brief for `[55]` fully-filled plan invariant source-clear |
| `CCAgentWorkSpace/Operator/2026-05-15--p1_intent_freeze_27_qty_rounding_rca.md` | Operator brief for `[27]` intent freeze qty rounding RCA |
| `CCAgentWorkSpace/Operator/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md` | Operator brief for F-FA-3 W-C caveat 2 guard tests design |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md` | AMD-2026-05-15-02 4-agent adversarial review consolidated：17 must-fix / 14 should-fix / QC+FA+BB+MIT 全 APPROVED-CONDITIONAL |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_qc.md` | QC verdict for AMD-2026-05-15-02：4 MF / 5 SF / 3 NTH |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md` | FA verdict for AMD-2026-05-15-02：4 MF / 5 SF / 4 NTH |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_bb.md` | BB verdict for AMD-2026-05-15-02：5 MF / 3 SF / 4 NTH |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_mit.md` | MIT verdict for AMD-2026-05-15-02：4 MF / 4 SF / 1 NTH |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_preflight_verification.md` | Stage 0R preflight verification report |
| `archive/2026-05-15--todo_v24_stale_rows_archive.md` | TODO v24 中过时 active rows / stale claims 归档，包括 V079 pending、engine 5/8 binary、旧 05-09 demo state、旧 `[55]`/`[67]` 判断 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--p1_healthcheck_55_invariant.md` | `[55]` fully-filled plan invariant source-clear report |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--feature_baseline_restore.md` | W-AUDIT-4b feature baseline restore report，646 active rows / 19 symbols / 34 features |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_preflight_step5b.md` | A4-C Stage 0R Step 5b runtime verification，仍 GATE-RED |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--passive_healthcheck_7108035d_plan_sync.md` | Passive healthcheck 7108035d plan sync report |

### 2026-05-09 v3 verification + PA redesign + DUAL-TRACK index addendum

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` | PA architectural root cause redesign blueprint — R-1..R-5 upgrade roadmap; alpha-poverty / Strategist scope / Analyst dormant / forcing function gap / 5-Agent skeleton without soul 5 root causes |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` | DUAL-TRACK fix plan v2 — Track W (88 finding maintenance) + Track A (R-1..R-5 architectural) parallel |
| `execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` | W-AUDIT-8a SPEC PHASE — Alpha Surface Foundation interface contract + DAG (R-1 spec phase, no IMPL) |
| `adr/0021-alpha-source-architecture-upgrade.md` | ADR-0021 — Alpha Source Architecture Upgrade R-1..R-5; supersedes LG-X-02..05 system-wide promotion design |
| `adr/0022-strategist-cap-wide-parameter-adjustment-skill.md` | ADR-0022 — Strategist 30%→50% cap as wide_parameter_adjustment skill (freedom-not-gate; SM-05 invariants 完全保留 + 50% 偏離監測 ledger + monthly Guardian veto review) |
| `architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md` | ARCH-04 — Historical Graduated Canary architecture baseline; Stage 1 paper semantics superseded by AMD-2026-05-15-01 (Stage 0R replay preflight + Stage 1 demo micro-canary), while Live 5-gate / DOC-08 §12 / SM-04 ladder / §二 16 原則 hard boundaries remain unchanged |
| `governance_dev/amendments/2026-05-10--AMD-2026-05-10-03-invariant-5-wording-n0-scope.md` | AMD-2026-05-10-03 — invariant 5 wording 對齊 N+0 actual IMPL (option A per operator 2026-05-10 sign-off discussion；commit `0b9a03ef` 已 land) + invariant 5b N+1 預告 |
| `governance_dev/amendments/2026-05-10--AMD-2026-05-10-04-toml-drift-fix-sop.md` | AMD-2026-05-10-04 — TOML drift gap 治理 SOP (option B-later per operator 2026-05-10；Sprint N+1 W3 cohort 拍板 + atomic patch + W-AUDIT-9 T7 regression + W-AUDIT-3b runtime smoke pre-launch) |
| `governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md` | AMD-2026-05-15-01 — W-AUDIT-9 canary rebase: remove Stage 1 paper cohort, add Stage 0R Replay Preflight, redefine Stage 1 as Demo micro-canary, and require Stage 2 entry from Stage 1 demo evidence |
| `governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md` | AMD-2026-05-21-01 — v5.8 13-module thesis 核心治理 amendment: CLAUDE.md §二 priority order 第 5 條 "human final review" 拆 protected scope (6 條 a-f 永不可 auto：Stage LAL 3-4 / 5-gate / Copy Trading enable / Auto-Allocator activation / kill criteria / ADR-debt) vs opt-in scope (8 條 g-n operator 一次 opt-in 後可 auto：LAL 1+2 / M2 always-on / M3 Tier 1+2 / M6 ≤30% / M7 demote / M8 Y2 trigger / M10 tier eval)；5 條 mitigation + 6 條反向 attack counter-mitigation；不放鬆 §四 hard boundaries 任一條 |
| `execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md` | W1 Phase B Tier 2 panel collector spec v1.1 — Rust panel_aggregator/{funding_curve,oi_delta} 訂閱既有 WS tickers broadcast (BB WS-first push back 採納, rate 100 req/min → 0 req/s ongoing + 75 req cold-start once) + bb_breakout fail-closed 寫 oi_panel_unavailable + 5m/15m/1h schema |
| `execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` | W2 A4-C BTC→Alt Lead-Lag spec v1.4 — Cohort 8 symbol (BTCUSDT lead + 7 alt; exclude BUSDT/INXUSDT/frozen) + lead signal triple component (return + volume z + book imbalance) over N=120s + V088 panel.btc_lead_lag_panel + 2026-05-23 paper Archive/diagnostic fence (`OPENCLAW_ENABLE_PAPER=1` ignored; diagnostic env only) + dual-layer σ acceptance (raw market σ_60=4.54 vs net edge σ=50-80) + +15/+5-15/<+5 階梯 gate + PSR(0) skew/kurt formula 強制 |
| `execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md` | P1-CANARY-STAGE-CRITERIA-1 spec — W-AUDIT-9 Stage 1→2→3→4 promotion + demote criteria 寫死 (per QC HIGH push back 2 sample size vs wall-clock 矛盾)；AMD-2026-05-10-05 起草；[58] healthcheck enrich |
| `execution_plan/2026-05-10--p1_canary_cohort_freq_23_spec.md` | P1-CANARY-COHORT-FREQ-23 spec — invariant 23 cohort frequency cap (30d 內 cohort symbol 最多 2 次 Stage 1 entry, 第 3 次 PA+QC override sign-off) + V089 governance.cohort_freq_cap_attempts + AMD-2026-05-10-06 起草 + [63] healthcheck |
| `execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md` | P1-DYNAMIC-UNBLOCK-CHECK-1 spec — 30d cycle audit logic + auto unblock criteria + manual override SOP + reverse re-freeze (per QC v3 NEW-ISSUE-V3-4 17 frozen cells permanent dormant 環路) + V090 governance.unblock_candidates + [64] healthcheck + reuse blocked_symbols_7d_counterfactual.py 改 30d |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` | **Sprint N+1 Dispatch Draft v3.7** (PA, current authoritative) — 7 Wave (W1-W7) + W6 reframe (governance 沒 over-fit, real gap = metadata + imbalance + duplicate_intent bug) + W7 STRATEGY-POSITION-SYNC (W7-1+W7-3 PR ready) + W2 A4-C fast-track + 24 D+0 提前準備項；HEAD `9695b59a` |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-10--n0_signoff_n1_dispatch_fire_sop.md` | N+0 sign-off + N+1 dispatch fire SOP — pre-fire 檢查 + deploy 步驟 (一次 restart_all --rebuild --keep-auth W7-3+W7-1+W2 trait) + dispatch fire (W7-2/W7-4/W7-5 + W6 + W1 + W2 + W4 + W5 並行) + memory persist + 24h watch |
| `archive/2026-05-09--w_audit_verified_closed_archive_v2.md` | v2 verified-closed archive (R4 v2 errata 補登) |
| `archive/2026-05-09--w_audit_verified_closed_archive_v3.md` | v3 verified-closed archive — DUAL-TRACK structure + 5 commits real cover + cross-agent PA Redesign verdict |
| `archive/2026-05-21--srv_root_cleanup/2026-05-09--audit_fix_verification_v3_summary.md` | PM v3 sign-off summary (top-level operator-facing；2026-05-21 archived from srv root) |
| `CCAgentWorkSpace/{FA,AI-E,E5,E4,E3,CC,QC,MIT,BB,TW,R4,A3}/workspace/reports/2026-05-09--*_v3.md` | 12 v3 verification reports (per-agent re-audit after v2 land) |
| `archive/2026-05-21--srv_root_cleanup/2026-05-09--audit_fix_verification_v2_summary.md` | PM v2 sign-off summary (intermediate, superseded by v3；2026-05-21 archived from srv root) |

### 2026-05 W-AUDIT-1 index addendum（AgentTodo / audit / governance）

| 文件 | 内容 |
|------|------|
| `archive/2026-05-21--srv_root_cleanup/2026-05-08--full_audit_fix_plan.md` | 12-agent full audit PA 整合修復計劃：88 unique findings / W-AUDIT-1..7 / 5 pending operator decisions（2026-05-21 archived from srv root） |
| `governance_dev/2026-05-08--w_c_lease_router_authorized.md` | W-C Decision Lease router evidence-mode operator authorization record |
| `governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` | AMD-2026-05-02-01 + §5.4.1 W-C early evidence flag addendum |
| `governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md` | AMD-2026-05-03-01 Wave 7 P5 IMPL accepted / deploy blocked split |
| `governance_dev/amendments/2026-05-09--SM-05_executor_shadow_mode_polling_design.md` | AMD-2026-05-09-01 accepted SM-05 Executor shadow-mode polling policy; F-01 implementation pending |
| `governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md` | AMD-2026-05-09-02 operator decision audit closure for P0-DECISION-AUDIT-2/4/5 |
| `governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md` | AMD-2026-05-09-03 Strategist 30%->50% wide_parameter_adjustment skill（freedom-not-gate + RuntimeMaxEnvelope） |
| `governance_dev/amendments/2026-05-09--demo_promotion_evidence_push.md` | AMD-2026-05-09-04 Demo->LivePending promotion_evidence producer + V079 schema + QC push back 採納 |
| `governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` | AMD-2026-05-09-03 Graduated Canary default-OFF（ARCH-04 配套 default gate） |
| `governance_dev/amendments/2026-05-10--AMD-2026-05-10-05-canary-stage-criteria-spec.md` | AMD-2026-05-10-05 canary stage criteria spec (Stage 1-4 promotion/demote criteria + sample-size gate) |
| `governance_dev/amendments/2026-05-11--AMD-2026-05-11-W6-1-rfc-final-verdict-absorb.md` | AMD-2026-05-11-W6-1 RFC final verdict absorb (W6 governance metadata + duplicate_intent bug + imbalance weight) |
| `governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` | AMD-2026-05-15-02 EDGE-P2-3 Phase 1b Close-Maker-First refactor (fee optimization pathway + 3-phase灰度 + V094 schema) |
| `governance_dev/SPECIFICATION_REGISTER.md` | SM/EX/DOC/REF/ARCH/AUDIT/LG-X/OPS-X specification register, updated through W-AUDIT-1 + LG-X-05 catch-up |
| `governance_dev/2026-05-11--w_c_window_pass_signoff.md` | W-C MAG-082 Stage 2 WINDOW_PASS sign-off (2026-05-11) |
| `governance_dev/2026-05-11--w_d_mag083_reviewer_brief.md` | W-D MAG-083 reviewer brief |
| `governance_dev/2026-05-11--w_d_mag084_signoff.md` | W-D MAG-084 operator sign-off |
| `governance_dev/2026-05-11--w2_impl_signoff_pack.md` | W2 A4-C IMPL sign-off pack |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-09--w_audit_3_partial_f15_f17_sm05.md` | PM sign-off report for W-AUDIT-3 partial F-15/F-17/SM-05 checkpoint |
| `CCAgentWorkSpace/Operator/2026-05-09--w_audit_3_partial_f15_f17_sm05.md` | Operator-facing copy of W-AUDIT-3 partial checkpoint report |
| `adr/0001-rust-as-trading-authority.md` | ADR-0001: Rust 為唯一交易參數權威 |
| `adr/0002-three-mode-engine-independent-risk-configs.md` | ADR-0002: 三引擎模式獨立風控 config |
| `adr/0003-paper-pipeline-disabled-by-default.md` | ADR-0003: Paper pipeline 預設關閉 |
| `adr/0004-livedemo-no-degradation.md` | ADR-0004: LiveDemo 不因 endpoint 降級 |
| `adr/0005-engine-mode-tag-live-demo.md` | ADR-0005: engine_mode 標籤 live_demo 升級 |
| `adr/0006-bybit-only-exchange.md` | ADR-0006: Bybit 為唯一交易所 |
| `adr/0007-mac-dev-linux-runtime-split.md` | ADR-0007: Mac=開發 / Linux=Runtime |
| `adr/0008-decision-lease-state-machine.md` | ADR-0008: Decision Lease 狀態機 |
| `adr/0009-hot-config-arcswap-no-restart.md` | ADR-0009: ArcSwap 熱重載無需重啟 |
| `adr/0010-timescale-hypertable-with-guard-migrations.md` | ADR-0010: TimescaleDB hypertable + Guard migration |
| `adr/0011-v-migration-linux-pg-dry-run-mandatory.md` | ADR-0011: V### migration Linux PG dry-run 強制 |
| `adr/0012-chinese-only-comments-default.md` | ADR-0012: 注釋默認只寫中文 |
| `adr/0013-openclaw-gateway-not-trading-conductor.md` | ADR-0013: OpenClaw Gateway 非交易指揮 |
| `adr/0014-arcane-equilibrium-soft-rename.md` | ADR-0014: 玄衡 Arcane Equilibrium 軟更名 |
| `adr/0015-openclaw-control-plane-repositioning.md` | ADR-0015: OpenClaw is Control Plane/Gateway, not trading conductor |
| `adr/0016-decision-lease-router-evidence-mode.md` | ADR-0016: Decision Lease router flag may run as shadow evidence |
| `adr/0017-scanner-is-evidence-not-authority.md` | ADR-0017: scanner is always-on evidence infrastructure, not authority |
| `adr/0018-funding-arb-v2-deprecation-watch.md` | ADR-0018: funding_arb V2 **Retired closed** per AMD-2026-05-26-01（status 升格自「retire from active strategy set」；W-AUDIT-6 cleanup 終結） |
| `adr/0019-github-issues-active-tracker.md` | ADR-0019: GitHub Issues active external tracker; git remains SoT |
| `adr/0020-layer2-manual-supervisor-only.md` | ADR-0020: Layer2 is manual supervisor escalation, not autonomous loop |
| `adr/0030-copy-trading-evidence-gated.md` | ADR-0030: Copy Trading Y1 末 4-Gate Evidence Evaluation, Y2 Enablement Conditional (Proposed; v5.7 §11 提案順移自 ADR-0028) |
| `adr/0031-framework-expansion-earn-macro-onchain.md` | ADR-0031: Framework Expansion — Earn Governance + Macro Counterfactual + On-Chain Counterfactual (Proposed; v5.7 §11 提案順移自 ADR-0029) |
| `adr/0032-bybit-earn-asset-movement-guardian.md` | ADR-0032: Bybit Earn Asset Movement Guardian — 5-Gate Adapter + Decision Lease Retrofit + Audit Log (Proposed; v5.7 §12 提案順移自 ADR-0030) |
| `adr/0033-adr-0006-bybit-binance-amendment.md` | ADR-0033: ADR-0006 Amendment — Binance Market Data Approved Y1 + Trading Defer Y2 + DEX/Hyperliquid NOT Approved + D12 + ToS (Proposed; v5.7 §12 amendment standalone) |
| `adr/0034-decision-lease-layered-approval-lal.md` | ADR-0034: Decision Lease Layered Approval (LAL) — M1 Tier 0-4 分層治理 (Proposed; v5.8 §2 M1；ADR-0008 擴展不取代；Tier 0-4 重命名避免 AMD-2026-05-15-01 Stage 0R-4 字面碰撞) |
| `adr/0035-m5-online-learning-interface-reserved.md` | ADR-0035: M5 Online Learning Interface Reserved — Trait Stub + V114 Placeholder, IMPL Deferred Y3+ (Proposed; v5.8 §2 M5；Sprint 1A-δ deliverable；retirement criteria 4 條) |
| `adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md` | ADR-0036: M8 Anomaly Detection + M10 Tier D Regime — Model Blacklist (HMM / Markov-switching / GARCH 永久禁用) + ATR-vol × Funding-state 雙 axis 9 cell 矩陣替代 + RV Percentile + Block Bootstrap Threshold + Y3+ PELT Evaluation ADR-debt (Proposed; v5.8 §2 M8+M10 Tier D 合併治理 ADR per PA CR-5 / PM 仲裁 #5) |
| `adr/0037-m9-ab-framework-and-statistical-methodology.md` | ADR-0037: M9 A/B Testing Framework + Statistical Methodology — 4 Variant Cluster × i.i.d. 修正 × Variant Stage 路徑 + Fair Execution Clause (Proposed; v5.8 §2 M9；Sprint 1A-γ DESIGN 50-70 hr / Sprint 4 read-only logging / Sprint 7-8 manual A/B / Y2 auto-gate 分階段 IMPL) |
| `adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` | ADR-0038: M11 Continuous Counterfactual Replay — Self-Hosted PG market.liquidations 作 historical source (Proposed; v5.8 §2 M11；BB 5.21 audit push back 落地) |
| `adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md` | ADR-0039: M12 OrderRouter Trait — Maker-Fill-Rate Metric + Adaptive Routing Audit Schema (Proposed; v5.8 §2 M12；V115 reserve) |
| `adr/0040-multi-venue-gate-spec.md` | ADR-0040: Multi-Venue Gate Spec — M13 Binance Trade Enable Defer Y3+ At Earliest (Proposed; v5.8 §2 M13；ADR-0033 §Decision 2 時點 amendment standalone) |
| `adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md` | ADR-0041: ContextDistiller v4 — Layered Snapshot + Token Hard Cap + DOC-08 AI Cost Amendment (Proposed; v5.8 AI-E must-fix #1；ADR-0027 v4 級延伸) |
| `architecture/2026-05-06--openclaw_control_plane_repositioning.md` | ARCH-02: OpenClaw control-plane repositioning |
| `architecture/multi_agent_rework_2026-05-05/ENGINEERING_PLAN.md` | ARCH-03 parent: Agent Decision Spine engineering plan |
| `architecture/multi_agent_rework_2026-05-05/AgentTodo.md` | Historical AgentTodo milestone board for MAG-010..084 |
| `architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md` | MAG-015 Sprint A contract addendum |
| `architecture/multi_agent_rework_2026-05-05/2026-05-06--mag020_scanner_authority_modes.md` | MAG-020 historical scanner authority-mode contract, superseded by ADR-0017 boundary |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag030_agent_spine_rust_module_design.md` | MAG-030 Agent Spine Rust module design |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag034_idempotency_double_execution_audit.md` | MAG-034 idempotency / double execution audit |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag040_strategist_v2_matching_model.md` | MAG-040 Strategist V2 matching model |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag050_guardian_v2_risk_metrics_model.md` | MAG-050 Guardian V2 risk metrics model |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag060_execution_plan_interface.md` | MAG-060 ExecutionPlan interface and order styles |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag070_analyst_insight_l1_l2_l3_schema.md` | MAG-070 AnalystInsight L1/L2/L3 schema |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag080_cutover_policy.md` | MAG-080 shadow -> canary -> primary cutover policy |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag081_canary_flag_runtime_risk_review.md` | MAG-081 canary flag runtime risk review |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag082_24h_canary_validation_checklist.md` | MAG-082 24h canary validation checklist |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag083_final_release_audit_blocked.md` | MAG-083 final release audit blocked report |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag084_operator_signoff_blocked.md` | MAG-084 operator sign-off blocked report |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-08--full_chain_functional_audit.md` | 12-agent audit input: FA functional audit |
| `CCAgentWorkSpace/AI-E/workspace/reports/2026-05-08--ai_effectiveness_full_audit.md` | 12-agent audit input: AI effectiveness audit |
| `CCAgentWorkSpace/E5/workspace/reports/2026-05-08--full_chain_optimization_audit.md` | 12-agent audit input: optimization / structure audit |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-08--full_chain_test_audit.md` | 12-agent audit input: test audit |
| `CCAgentWorkSpace/E3/workspace/reports/2026-05-08--full_chain_security_audit.md` | 12-agent audit input: security audit |
| `CCAgentWorkSpace/CC/workspace/reports/2026-05-08--project_compliance_audit.md` | 12-agent audit input: compliance audit |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-08--strategy_risk_math_audit.md` | 12-agent audit input: quant / strategy audit |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-08--db_ml_foundation_audit.md` | 12-agent audit input: DB / ML foundation audit |
| `CCAgentWorkSpace/MIT/README.md` | MIT workspace orientation and current report pointer |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-08--bybit_api_compatibility_audit.md` | 12-agent audit input: Bybit compatibility audit |
| `CCAgentWorkSpace/BB/README.md` | BB workspace orientation and current report pointer |
| `CCAgentWorkSpace/TW/workspace/reports/2026-05-08--apr_may_doc_audit.md` | 12-agent audit input: TW documentation audit |
| `CCAgentWorkSpace/R4/workspace/reports/2026-05-08--index_completeness_audit.md` | 12-agent audit input: R4 index completeness audit |
| `CCAgentWorkSpace/A3/workspace/reports/2026-05-08--gui_ux_full_audit.md` | 12-agent audit input: GUI/UX audit |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md` | PA de-duped full audit fix plan |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-08--mattpocock_skills_setup.md` | PM report: mattpocock skills setup and GitHub Issues posture |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-09--w_audit_1_docs_governance_sync.md` | PM report: W-AUDIT-1 docs/governance sync closure |
| `CCAgentWorkSpace/Operator/2026-05-09--w_audit_1_docs_governance_sync.md` | Operator-facing W-AUDIT-1 completion note |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag080_cutover_policy.md` | PM report: MAG-080 cutover policy |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag081_canary_flag_runtime_risk_review.md` | PM report: MAG-081 flag risk review |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag082_24h_canary_validation_checklist.md` | PM report: MAG-082 validation checklist |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag083_final_release_audit_blocked.md` | PM report: MAG-083 blocked pre-audit |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag084_operator_signoff_blocked.md` | PM report: MAG-084 blocked sign-off |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_m8_stage2_fast_track_no_go.md` | PM report: M8 fast-track NO-GO |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--todo_v13_agent_openclaw_replan.md` | PM report: TODO v13 Agent/OpenClaw replan, superseded by TODO v14 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--p1_healthcheck_fail_queue_and_executor_fake_live_fix.md` | PM report: P1 healthcheck FAIL queue and executor fake-live source fix |
| `../helper_scripts/SCRIPT_INDEX.md` | helper_scripts 維護/啟動/CI/DB/audit/cron/operator/research 腳本索引 |

### docs/agents/ — GitHub Issues / Agent triage guidance

| 文件 | 内容 |
|------|------|
| `agents/context-loading.md` | Agent context source-of-truth map and loading route |
| `agents/role-profile-memory-standard.md` | Agent role profile / memory split and hygiene standard |
| `agents/todo-maintenance.md` | TODO.md active-queue maintenance standard |
| `agents/domain.md` | Agent domain ownership and routing rules for issue triage |
| `agents/issue-tracker.md` | GitHub Issues operating model after the 2026-05-08 tracker decision |
| `agents/triage-labels.md` | Triage labels and severity/status conventions for Agent work |

### _indexes/ — 文档 inventory / redirect map / GUI metadata（2026-05-06+）

| 文件 | 内容 |
|------|------|
| `document_inventory.json` | R4 文档信息架构盘点结果：当前 cluster counts、目标 taxonomy、GUI 热交互候选、分阶段执行计划 |
| `path_redirects.md` | 文档重命名/搬迁 redirect plan；当前仅规划，不代表文件已移动 |

### Phase Packet Archive Index — 2026-03 ~ 2026-04 早期 phase 工作日誌（2026-05-28 歸檔）

下表 6 個目錄為 OpenClaw 早期 phase（A-K 章節 + Phase 5 + Control API/GUI + learning）工作日誌。**2026-05-28 phase 2 cleanup 統一歸檔至 `archive/2026-05-28--worklog_<topic>_archived/`**，原 detail 索引保留於各 archive 子目錄的 `_README.md`（grep 可命中）。

| Phase 目錄 | 期間 | 歸檔位置 | 檔數 |
|---|---|---|---|
| `chapters_a-g/` | 2026-03-11 ~ 03-19 | [`archive/2026-05-28--worklog_chapters_a-g_archived/`](archive/2026-05-28--worklog_chapters_a-g_archived/_README.md) | 11 |
| `chapters_h-i/` | 2026-03-20 ~ 03-22 | [`archive/2026-05-28--worklog_chapters_h-i_archived/`](archive/2026-05-28--worklog_chapters_h-i_archived/_README.md) | 13 (README ghost +1) |
| `chapters_j-k/` | 2026-03-22 ~ 03-24 | [`archive/2026-05-28--worklog_chapters_j-k_archived/`](archive/2026-05-28--worklog_chapters_j-k_archived/_README.md) | 8 |
| `control_api_gui/` | 2026-03-25 ~ 04-02 | [`archive/2026-05-28--worklog_control_api_gui_archived/`](archive/2026-05-28--worklog_control_api_gui_archived/_README.md) | 50 |
| `phase5_arch_rc1/` | 2026-04-03 ~ 04-07 | [`archive/2026-05-28--worklog_phase5_arch_rc1_archived/`](archive/2026-05-28--worklog_phase5_arch_rc1_archived/_README.md) | 5 (README ghost +15) |
| `learning/` | 2026-03-26 | [`archive/2026-05-28--worklog_learning_archived/`](archive/2026-05-28--worklog_learning_archived/_README.md) | 1 |

> 雙向 link：本表為順向入口；每個 archive 子目錄 `_README.md` 含原 README 對應段（grep `<檔 stem>` 仍命中）+ 逆向 link 回 `_indexes/path_redirects.md` Executed phase 2 段。
> Pre-2026-04-08 phase work moved to archive/; new worklogs go to `worklogs/` root（見下方「頂層工作日誌」段）。

### worklogs/ — 頂層工作日志（2026-04-08+，daily_summary 為當日權威）

| 文件 | 内容 |
|------|------|
| `2026-04-08--daily_summary.md` | ★★★★ 2026-04-08 日匯總：ARCH-RC1 1C-3-D/1C-3-E F-mini/1C-3-F/1C-4 + GUI fake-success Wave 1-2 + P1 Per-Trade Risk wiring |
| `2026-04-09--daily_summary.md` | ★★★★ 2026-04-09 日匯總：StrategyAction Enum（策略出場死鎖修復）+ Rust 市場掃描器 Phase A-D + QC/FA 全修 · 830 tests |
| `2026-04-10--daily_summary.md` | ★★★★ 2026-04-10 日匯總：ML Pipeline Remediation + Signal Diamond Phase 1-4 + Fix Round + Live GUI P0-P6 + Phase 6 Reconciler 自動降級 + W19/W20 安全治理 · 850 tests |
| `2026-04-11--daily_summary.md` | ★★★★ 2026-04-11 日匯總：3E-ARCH 三引擎並行 + Multi-Symbol + Fix Rounds Phase A-G |
| `2026-04-12--daily_summary.md` | ★★★★ 2026-04-12 日匯總：全程序鏈審計 P0+P1+P2+P3 58 findings + A3 GUI 36 + BB Bybit API 10 + FIX-08 拆分 + Earned-Trust TTL Ladder + PNL-FIX-1/2 · 4250 tests |
| `2026-04-13--daily_summary.md` | ★★★ 2026-04-13 日匯總：R-06-v2 Agent Value Delivery（Executor shadow IPC / Analyst→DB→Strategist feedback / Guardian rejection / Conductor real health）· 1124 Rust + 2852 Python |
| `2026-04-14--engine_self_healing.md` | ENGINE-HEAL 4 Fix：panic hook + crash-only + WS stale self-cancel + watchdog 4 道保險（尚未合併至 daily_summary）|
| `2026-04-14--qol_1_and_qol_3_delivery.md` | QoL-1（paper_state restore_from_db）+ QoL-3（PyO3 雙 venv 部署）交付（尚未合併至 daily_summary）|
| `2026-04-27--live_auth_watcher_event_consumer_spawn_fix.md` | ★★ P0 Silent Regression：LiveAuthWatcher respawn 路徑遺漏 `spawn_live_pipeline` → event_consumer 8 天未 spawn（2252 tests）· commits 588d207 / 0fa41b1 / merge 1fac9b1 |

> 2026-04-14 worklog audit：所有舊碎片已合併至當日 `daily_summary.md` 並刪除；`2026-04-08--arch_rc1_1c_history_archive.md` 已移至 `docs/archive/`。

### handoffs/ — 阶段交接文档

| 路径 | 内容 |
|------|------|
| `2026-03-25_api_gui_handoff/` | Control API v1 + GUI v1 阶段交接（含 12 份文档 + source_docs） |

### decisions/ — 架构/设计决策记录 + 治理源文件

| 文件 | 内容 |
|------|------|
| `2026-04-01--symbol_category_mapping_design.md` | Symbol→Category 映射策略決策：方案 B 運行時映射（短期）+ 方案 A SymbolCategoryRegistry 批量填充（長期），雙層架構設計 |
| `2026-03-17--工程一审修改建议报告_终稿.md` | Revision 2 工程一审修改建议报告（md 终稿） |
| `2026-03-17--工程一审修改建议报告_终稿.txt` | Revision 2 工程一审修改建议报告（txt 终稿） |
| `2026-03-20--关于h和i部分的核心设计讨论.txt` | H-I 核心设计讨论（AI 成本均衡 / 本地计算 / 延迟框架 / 设备容错） |
| **治理源文件（.docx，Operator 原始治理规格）** | |
| `DOC-NAV_...治理文件导航_V3.docx` | 治理文件导航 V3（13 份文件总入口） |
| `DOC-01_...项目宪法与根原则_V2.docx` | 项目宪法：16 条根原则（§5.1–§5.16） |
| `DOC-02_...边界定义_V2.docx` | 系统边界定义（H0 <1ms SLA、执行权限、数据平面） |
| `DOC-03_...字段级与状态级规范_V1.1.docx` | 字段级与状态级规范 |
| `DOC-04_...Agent能力蓝图_V2.docx` | Agent 能力蓝图（A-J 十大能力目标） |
| `DOC-05_...真相源与所有权矩阵_V1.1.docx` | 真相源与所有权矩阵 |
| `DOC-06_...变更治理_V2.docx` | 变更治理流程 |
| `DOC-07_...审计事故与熔断政策_V1.1.docx` | 审计/事故/熔断政策 |
| `DOC-08_...实施桥梁_V1.docx` | 实施桥梁（AI 成本上限 $2/天、provider 配置） |
| `SM-01_...授权状态机规范_V1.docx` | SM-01 授权状态机规范 |
| `SM-02_...决策租约状态机规范_V1.docx` | SM-02 决策租约状态机规范 |
| `SM-03_...执行状态机规范_V1.1.docx` | SM-03 OMS 执行状态机规范 |
| `SM-04_...风控状态机规范_V1.docx` | SM-04 风控状态机规范 |
| `EX-01_...风控边界定义_V2.docx` | 风控边界定义 |
| `EX-02_...OMS与执行正式边界定义_V1.docx` | OMS 与执行正式边界定义 |
| `EX-03_...控制平面正式边界定义_V1.docx` | 控制平面正式边界定义 |
| `EX-04_...对账正式边界定义_V1.docx` | 对账正式边界定义 |
| `EX-05_...学习边界定义_V2.docx` | 学习边界定义 |
| `EX-06_...多Agent编排正式边界定义_V1.docx` | 多 Agent 编排正式边界定义 |
| `EX-07_...感知平面正式边界定义_V1.docx` | 感知/数据平面正式边界定义 |
| `HIST-01_...核心设计总纲_V1.docx` | 历史参考：核心设计总纲 |
| `HIST-02_...治理设计交付包_V1.docx` | 历史参考：治理设计交付包 |

### CCAgentWorkSpace（各 Agent workspace/reports）— ★★★ 2026-03-31 七Agent全系统审计

| Agent | 文件（CCAgentWorkSpace/<Agent>/workspace/reports/） | 内容 |
|-------|------|------|
| E3 | `2026-03-31--e3_security_audit.md` | E3 安全审计：3 CRITICAL / 5 HIGH / 6 MEDIUM / 5 LOW |
| CC | `2026-03-31--cc_compliance_check.md` | CC 合规检查：11/16 原则完全合规，B 级 |
| E4 | `2026-03-31--e4_testing_report.md` | E4 测试评估：71 文件/2480 用例 |
| E5 | `2026-03-31--e5_optimization_report.md` | E5 优化评估：49 项 |
| A3 | `2026-03-31--a3_gui_usability_report.md` | A3 GUI 可用性：6.2/10 |
| PM | `2026-03-31--pm_review.md` | ★ PM 整合审核：71 项去重，~110h 工时 |
| PA | `2026-03-31--pa_review.md` | ★ PA 技术复验：4 CRITICAL 确认属实 |

双语注释审计：`audits/2026-03-30--bilingual_comment_audit_report.md`

### CCAgentWorkSpace（各 Agent workspace/reports）— ★★★ 2026-04-01 十Agent全系统审计

| Agent | 文件（CCAgentWorkSpace/<Agent>/workspace/reports/） | 内容 |
|-------|------|------|
| AI-E | `2026-04-01--ai_effectiveness_audit.md` | AI-E AI 效果审计 |
| CC | `2026-04-01--compliance_check.md` | CC 合规检查：16 条根原则逐一验证 |
| E3 | `2026-04-01--security_audit.md` | E3 安全审计 |
| E4 | `2026-04-01--testing_audit.md` | E4 测试评估 |
| E5 | `2026-04-01--optimization_audit.md` | E5 优化评估 |
| FA | `2026-04-01--functional_gap_audit.md` | FA 功能缺口审计 |
| TW | `2026-04-01--documentation_quality_audit.md` | TW 文档品质审计 |
| R4 | `2026-04-01--document_index_audit.md` | R4 文档索引审计 |
| Operator | `2026-04-01--pa_review.md` | PA 技术复验 |
| Operator | `2026-04-01--pm_execution_plan.md` | PM 执行计划 |

### audits/2026-04-05--l3_comprehensive/ — L3 全系统综合审计（2026-04-05，12 角色专项报告）

注：这批审计文件是 2026-04-05 L3 审计轮次产出，因当时未遵守命名规范（无日期前缀），现统一归入此子目录。

| 文件 | 内容 |
|------|------|
| `audit_A3_gui_usability_report.md` | A3 GUI 可用性审计报告 |
| `audit_AIE_effectiveness_report.md` | AI-E AI 效果评估报告 |
| `audit_BB_bybit_api_report.md` | BB Bybit API 专项审计报告 |
| `audit_CC_compliance_report.md` | CC 合规审计报告 |
| `audit_E3_security_report.md` | E3 安全审计报告 |
| `audit_E4_test_coverage_report.md` | E4 测试覆盖报告 |
| `audit_E5_optimization_report.md` | E5 优化评估报告 |
| `audit_FA_functional_spec_report.md` | FA 功能规格审计报告 |
| `audit_MIT_database_ml_report.md` | MIT 数据库 + ML 专项报告 |
| `audit_QC_math_algorithm_report.md` | QC 数学算法审计报告 |
| `audit_R4_index_verification_report.md` | R4 文档索引完整性审计报告 |
| `audit_TW_document_inventory_report.md` | TW 文档盘点审计报告 |

### audits/（专项审计报告）

| 文件 | 内容 |
|------|------|
| `2026-03-30--bilingual_comment_audit_report.md` | 双语注释全量审计报告（评级 9.5/10，100% 覆盖） |
| `2026-04-04--bybit_api_infra_audit.md` | ★ Bybit API 基础设施专项审计：REST/WS 端点覆盖度、SDK 对接质量、IPC 接口审核 |
| `2026-04-06--consolidated_remediation_report.md` | ★ L3 全系统审计 63 问题整改追踪报告：11 工作包 · 4 波执行 · R0-R3 整改记录 |
| `2026-04-07--e3_r6_directive_applier_security_audit.md` | E3 R6 Directive Applier 安全审计（Phase 4 前置） |
| `2026-04-07--phase4_final_signoff_audit.md` | Phase 4 最终验收审计报告 |
| `2026-04-08--e2_review_1c3_bbc.md` | E2 代码审查：ARCH-RC1 1C-3 BBC（Build-Before-Commit 验收） |
| `2026-04-09--db_rw_ml_pipeline_full_audit.md` | DB 读写 + ML 管线全量审计（Signal Diamond Phase 1 前置）|
| `2026-04-11--3e_arch_e2_multi_role_review.md` | ★★ 3E-ARCH E2 多角色審查：9 角色並行 Phase A-F 全修驗證 |
| `2026-04-11--3e_arch_phase_g_reaudit.md` | ★★ 3E-ARCH Phase G 重審：9/9 PASS — 0 BLOCKER |
| `2026-04-12--full_program_chain_audit.md` | ★★★★ 全程序鏈審計總報告：12 角色合併 · 58 findings（8 P0 · 17 P1 · 28 P2 · 5 P3） |
| `2026-04-12--full_audit_fix_plan_pm_confirmed.md` | ★★★ PM 確認修復計劃：P0~P3 分級修復排期 + PM 簽核 |
| `2026-05-31--funding_short_v2_structural_infeasibility.md` | ★★ A1 funding_short_v2 修復核驗（f7271405 三程序 bug 屬實且修對）+ 結構性可行性審計：Bybit 正側 funding 硬上限 +10.9% APR < 策略 30% 入場門檻 → 結構性 NO-GO 永久（自抓 Bybit API + MIT PG 驗證） |

### KNOWN_ISSUES.md

| 文件 | 内容 |
|------|------|
| `KNOWN_ISSUES.md` | ★ 已知問題追蹤（OPEN 9 / RESOLVED 15，最後更新 2026-04-12） |

### architecture/ — 架構設計文件

| 文件 | 内容 |
|------|------|
| `DATA_STORAGE_ARCHITECTURE_V1.md` | ★ 數據存儲架構 V1：PG + TimescaleDB 方案 · 8 Schema · 存儲精簡 97%（5.6→0.17 GB/day）· 冷存儲 NAS 策略 |
| `architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md` | AgentTodo Sprint A MAG-015 合約附錄：local observations、OpenClaw view models、supervisor escalation、proposal/approval/channel schemas、endpoint allowlist、cloud budget、store ownership、state transitions |

### references/ — 长期参考文档

| 文件 | 内容 |
|------|------|
| **state_dictionary/** | |
| `2026-03-25--状态字典_数据字典_v1_最终版.md` | 状态字典 / 数据字典 V1 最终版（1149 行） |
| `2026-03-25--状态字典_v1_rc2_伴随补丁.md` | 状态字典 V1 RC2 伴随补丁 |
| **api_contract/** | |
| `2026-03-25--control_api_v1_最终定稿.md` | Control API V1 最终定稿（1008 行） |
| `2026-03-25--control_api_v1_rc2_最终候选版.md` | Control API V1 RC2 最终候选版 |
| `2026-03-25--control_api_v1_rc2_审核报告.md` | Control API V1 RC2 审核报告 |
| `2026-03-25--fastapi_openapi_v1_rc2_路由草案.md` | FastAPI / OpenAPI V1 RC2 路由草案 |
| `2026-03-25--后端实现清单_v1_rc2.md` | 后端实现清单 V1 RC2 |
| **api_stub/** | |
| `2026-03-25--control_api_v1_rc2_fastapi_stub.py` | FastAPI 骨架代码（553 行） |
| **根目录** | |
| `2026-03-25--capability_and_permission_switch_plan_v1.md` | 能力与权限开关规划 V1（md） |
| `2026-03-25--capability_and_permission_switch_plan_v1.pdf` | 能力与权限开关规划 V1（pdf） |
| `2026-03-25--gui_operator_console_learning_cockpit_v1_spec.md` | GUI Operator Console + Learning Cockpit V1 规格书 |
| `2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` | Layer 2 AI 推理引擎完整实现计划（4 层搜索降级 + 模型升级 + 自适应预算 + 9 路由 + GUI 集成） |
| `2026-03-27--local_trading_logic_audit_and_strategy_plan.md` | 本地交易逻辑审查报告：安全审查 + 本地覆盖缺口 + 盈利可能性评估 + ABCD 策略补齐计划 |
| `2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md` | ★ 全品类风控框架完整设计：三层优先级 P0/P1/P2 + Bybit V5 全 6 品类 + 对抗性止损 + AI 注意力税 + Agent 自主交易 |
| `2026-03-27--phase2_strict_audit_report.md` | ★ Phase 2 严格审核报告：8 CRITICAL + 15 HIGH + 25 MEDIUM + 19 LOW，全 CRITICAL/HIGH 已修复 |
| `2026-03-27--phase2_audit_fix_roadmap.md` | Phase 2 审核修复工程路线图：已完成项 + 待完善项 + 架构级待定 |
| `2026-03-27--system_reference_handbook.md` | ★ 系统参考手册（从 CLAUDE.md 移出的参考性内容：能力目标/API路由/安全加固/产品族/订单类型/风控/部署/历史编号） |
| `2026-03-27--phase2_round2_strategic_audit_report.md` | Phase 2 第二轮审核：实战适用性（策略盈利性/管线连通性/数据质量/风控集成/信号可靠性） |
| `2026-03-27--full_system_audit_A_to_K.md` | ★★ 全系统审核 A-K：569 文件 63,874 行，7 CRITICAL + 19 HIGH + 28 MEDIUM + 16 LOW |
| `2026-03-27--remote_access_guide.md` | 远程访问完整指南：Tailscale 安装配置 + Bybit Demo 访问地址 + secrets 权限加固 |
| `2026-03-22--local_private_layout.md` | 本地私有布局说明：Git 仓库 vs 本地私有目录结构（secrets/srv 分离） |
| `2026-03-30--local_ai_expansion_analysis.md` | 本地 AI 擴展用途分析（Ollama/Qwen 3.5 應用場景，DOC-08 依據） |
| `2026-04-03--openclaw_improvement_report_v3_final.md` | ★★★★ 外部全面改善建議報告 V3 Final：五輪三人審批 34 項修正 · Agent 自主化架構 + 雙層決策 + 四階段放權 + 10 新模組 + 5 策略 V2 + L0-L2 路徑 + Claude API 整合 |
| `2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` | V1.1+R1 · Agent 認知自適應規範：CognitiveModulator（L0 決策門檻調製）+ OpportunityTracker（遺憾追蹤）+ DreamEngine（閒置蒙特卡洛模擬）— 五角色審查通過，Phase 1 並行組 B |
| `2026-04-03--rust_migration_master_plan_v2.md` | V2 草稿（歸檔）· Rust 遷移總方案初版 |
| `2026-04-03--rust_migration_v2.5_consolidated.md` | V2.5 整合版（歸檔）· 六路缺口修復後 |
| `2026-04-03--rust_migration_v3_final.md` | ★★★★ V3-FINAL · Rust 遷移正式執行依據：五角色三輪審查 · 32,500 行 Rust · 14 週路線圖 · 分級浮點容差 · 四層測試 · 回滾計劃 · 21 項嚴格論證修正 |
| `2026-04-02--system_status_report.md` | 系統狀態報告（2026-04-02）：引擎健康度、測試基準線、已知問題彙整 |
| `2026-04-03--agent_param_tuning_design_draft_v0.2.md` | Agent 參數調整設計草稿 V0.2：策略參數 JSON 介面 · Agent 自主調參機制 · AGT-1 技術規格 |
| `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` | 數據存儲架構最優方案草稿 V0.1：PG + TimescaleDB · 分區策略 · 冷熱分層 |
| `2026-04-03--llm_abstraction_audit.md` | LLM 抽象層審計：LocalLLMClient ABC 介面覆蓋度 · Ollama 耦合殘留 · 跨平台兼容性評估 |
| `2026-04-03--ml_dl_learning_architecture_v0.4.md` | ★ ML/DL 學習架構 V0.4：Teacher-Student + LightGBM + Optuna + 3 DL 場景 · 三方審查完成 |
| `2026-04-10--signal_diamond_db_todo.md` | ★★ Signal Diamond DB TODO 歸檔：多引擎數據分離 5 Phase 規劃 · Phase 1-4 ✅ + 審計備註 · Phase 5 待實施（⚠ TradingMode→PipelineKind 歷史術語） |
| `2026-04-04--bybit_api_reference.md` | ★★ Bybit API 字典手冊：REST/WS 全端點速查 · V5 API 分類覆蓋 · 開發必讀 |
| `2026-04-04--comprehensive_audit_template_v1.md` | 全面審查模板 V1：L1/L2/L3 三級審計流程 · 5 路並行 9 角色 + DL/DB 專項 |
| `2026-04-04--execution_plan_v1.md` | ★ 融合方案執行計劃 V1：DB + ML/DL + 新聞 Agent 20 週路線圖 · Phase 0-6 詳細規格 |
| `2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md` | 統一 DB + ML + 新聞 Agent 工作計劃草稿 V0.1：融合方案 v0.5 設計文件 · 67 項修正後版本 |
| `2026-04-06--phase4_execution_plan_v2.md` | 融合方案執行計劃 V2：Phase 4 更新版排期 |
| `2026-04-07--arch_rc1_1c3_scope.md` | ARCH-RC1 1C-3 範圍定義 |
| `2026-04-07--arch_rc1_1c3a_gap_analysis.md` | ARCH-RC1 1C-3A 缺口分析 |
| `2026-04-07--arch_rc1_1c3c_recon.md` | ARCH-RC1 1C-3C 對賬設計 |
| `2026-04-11--three_engine_parallel_arch_plan.md` | ★★★ 三引擎並行架構遷移計劃 v4：26 設計決策 · PM+PA+FA 三角色（✅ 已完成） |
| `2026-04-11--3e_arch_session_execution_plan.md` | ★★ 3E-ARCH Session 執行計劃：8 工作日排期（✅ 已完成） |
| `2026-04-06--math_implementation_notes.md` | 數學實現方案彙編：LinUCB/風控公式/統計檢定/校準/shrinkage |
| `2026-04-20--dust_frozen_position_manual_clear_procedure.md` | ★ Dust-Frozen 持倉手動清理 SOP：DUST-EVICTION-GAP-1 P1-8 設計背景 · Bybit GUI 三路線 · Live 前 pre-flight checklist |
| `2026-04-20--cross_platform_redeploy_dependencies.md` | ★ 跨平台重部署依賴參考：Linux→macOS（Apple Silicon）冷裝清單 · brew/rustup/pip 步驟 · systemd↔launchd 差異 · HMAC 憑證重簽陷阱 |
| `2026-05-02--reality_calibrated_fast_replay_governance.md` | REF-19 · Reality-Calibrated Fast Replay 治理契約：Replay 調用 MLDE/DreamEngine 作實驗環境與資料來源，但不改寫其 Agent 自我學習本職；明確 source tagging、execution calibration、demo/live 邊界 |
| `2026-05-02--reality_calibrated_fast_replay_governance_zh.md` | REF-19 中文版 · 與英文契約同義，供 operator-first 閱讀與後續實作引用；明確 Replay 只是 MLDE/DreamEngine 的實驗環境之一，不改變其 Agent 自我學習本職 |
| `2026-05-02--paper_replay_learning_surface_design.md` | REF-20 · Paper Replay Lab + Learning surface 設計：Paper Tab 原地升級為 Replay Lab；Learning 保持知識 cockpit；5-Agent 抽出為 read-only Agents Monitor |
| `2026-05-02--paper_replay_learning_surface_design_zh.md` | REF-20 中文版 · 與英文設計同義，明確 Paper / Learning / 5-Agent / MLDE / DreamEngine 的產品邊界、API/storage 姿態、分階段交付與驗收檢查 |

### execution_plan/ — 执行计划

| 文件 | 内容 |
|------|------|
| `archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md` | REF-20 Paper Replay Lab 開發方案 v0.1：早期審查材料，指出 manifest、source tagging、calibration、auth、安全與 UX 等風險（2026-05-28 archived；由 v3 取代） |
| `archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/2026-05-02--ref20_paper_replay_lab_dev_plan_v1.md` | REF-20 Paper Replay Lab 開發方案 V1：第一版開發基線，確認 manifest signature、route auth、replay registry、MLDE source guard、execution calibration、多重檢驗與 5-Agent 抽出等問題大多屬真實風險（2026-05-28 archived；由 v3 取代） |
| `2026-05-02--ref20_v1_round2_audit.md` | REF-20 V1 第二輪 audit：對 V1 的安全、資料、量化、UX、API 審查意見；其中大多成立，但 P2 禁 IntentProcessor / Mac 禁 S2 public data 需在 V2 中反對或改寫 |
| `archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/2026-05-02--ref20_paper_replay_lab_dev_plan_v2.md` | REF-20 Paper Replay Lab 開發方案 V2：整合 Round2 audit；已被 Round3/V2.1 收斂為更嚴格實作基線（2026-05-28 archived；由 v3 取代） |
| `2026-05-02--ref20_v2_round3_audit.md` | REF-20 V2 第三輪 audit：7-agent 審查 V2，指出 schema 物理欄位、MLDE retrofit、DB role guard、V### governance、P2 isolation、UX subdoc、Mac non-actionable policy 等 P0 gates |
| `archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/2026-05-02--ref20_paper_replay_lab_dev_plan_v2_1_round3.md` | REF-20 Paper Replay Lab 開發方案 V2.1 Round3：當前實作前基線；接受 Round3 真實問題，明確 schema/DB/migration/runner/quant/UX gates，保留 P2 isolated no-write TickPipeline/IntentProcessor 方案（2026-05-28 archived；由 v3 取代） |
| `2026-05-02--ref20_ux_subdoc_v1.md` | REF-20 Paper Replay Lab UX Subdoc V1：P1 前必讀 UX contract；定義 Session/Replay/Compare/Handoff、mode badges、disabled states、no submit/cancel 與 handoff gating |
| **`2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`** | **★ SoT** REF-20 Paper Replay Lab 開發方案 V3：取代 V2.1 Round3 為當前 implementation baseline；§12 25 條 acceptance binding；§4.1 replay.experiments 22 col + replay.simulated_fills 17 col 規範表；§4.2 mlde_shadow_recommendations 三 column 雙路 CHECK |
| `2026-05-03--ref20_implementation_workplan_v1.md` | REF-20 Implementation Workplan V1：9-Wave / 76-task atomic breakdown；§6 hard prereq table 7 條；總工時 12-14 sprint（不含 P5 LG 等期）|
| `2026-05-03--ref20_wave2_dispatch_v1.md` | REF-20 Wave 2 dispatch v1：5 ambiguity decisions（unified terminology / 2only / reuse / Mac/Linux priority / bilingual flexibility）|
| `2026-05-03--ref20_wave1_to_6_master_closure.md` | REF-20 Wave 1-6 master closure summary（commits 9e0c826 / 1851714+b1f6b8a / 5a618ff / 4b48b6d / 457a458 / eb5f106）|
| `2026-05-03--ref20_wave7_defer_note.md` | REF-20 Wave 7 defer note：hard prereq LG-2/3/4 frontend stable NOT GREEN；事件觸發 dispatch 標準；後 commit `c887e4e` operator override IMPL（已正式 amendment AMD-2026-05-03-01 規範 IMPL/Deploy 2-stage gate）|
| `2026-05-03--ref20_wave9_pm_sign_off_template.md` | REF-20 Wave 9 PM sign-off 7-item checklist template；deploy 後 14d gradient observation 起算 |
| `2026-05-03--ref20_final_closure_and_deploy_guidance.md` | REF-20 Final IMPL closure + Operator Deploy Guidance；§4 14-step procedure (Phase A-G)；**注意**：line 99 「~3500+ PASS」是虛構數字（cold reality 3387 PASS，差 113-126；P2-FOLLOW-UP-5 訂正 ticket 待修）|
| `2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md` | REF-21 Full-Chain Replay Engine V1.3：active plan；修正 negative-edge fail-open，補 subprocess deploy path、V057/V058/V059/V060 DDL sketch + Linux PG dry-run、promotion FSM/signatures、Bybit SSOT URI、block bootstrap、survival/correlation/cost thresholds、baseline SLA |
| `2026-05-06--ref21_gui_ux_spec_v1_1.md` | REF-21 Replay GUI/UX Spec V1.1：active GUI companion；補二次確認、cooldown、12-tab 一致性、a11y/i18n、agent quota UI、sign-off SOP |
| `archive/2026-05-28--ref21_full_chain_replay_engine_superseded/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_2.md` | REF-21 Full-Chain Replay Engine V1.2：已被 V1.3 supersede，保留作第三輪 audit 追溯（2026-05-28 archived） |
| `archive/2026-05-28--ref21_gui_ux_spec_superseded/2026-05-06--ref21_gui_ux_spec_v1.md` | REF-21 Replay GUI/UX Spec V1：已被 V1.1 supersede，保留作 GUI 初版追溯（2026-05-28 archived） |
| `archive/2026-05-28--ref21_full_chain_replay_engine_superseded/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_1.md` | REF-21 Full-Chain Replay Engine V1.1：已被 V1.2 supersede，保留作第二輪 audit 追溯（2026-05-28 archived） |
| `archive/2026-05-28--ref21_full_chain_replay_engine_superseded/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1.md` | REF-21 Full-Chain Replay Engine V1：已被 V1.1 supersede，保留作方向性 baseline 與 audit 追溯（2026-05-28 archived） |
| `2026-05-XX--ref21_s1_recorder_spec_placeholder.md` | REF-21 S1 recorder placeholder：已被 REF-21 Full-Chain Replay V1 接管，保留作 REF-20 Wave 5 歷史 trace |
| `2026-05-03--ref20_sprint3_track_i_linux_deploy_runbook.md` | REF-20 Sprint 3 Track I Linux deploy runbook |
| `2026-05-03--ref20_sprint4_final_closure.md` | REF-20 Sprint 4 final closure |
| `2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` | REF-20 Gap Closure Plan V1：Sprint A-D 的 SoT execution plan |
| `2026-05-07--ref21_replay_remaining_wave_reset_v1.md` | REF-21 Replay Remaining Wave Reset V1：REF-21 V1.3 governance gates 保留前提下剩餘 wave 重排 |
| `2026-05-09--w_audit_8b_strategist_alpha_orchestrator_spec.md` | W-AUDIT-8b Strategist Alpha-Source Orchestrator spec（R-2 spec phase） |
| `2026-05-09--w_audit_8c_hypothesis_pipeline_spec.md` | W-AUDIT-8c Hypothesis Pipeline as First-Class Governance Object spec（R-3 spec phase） |
| `2026-05-09--w_audit_8d_per_alpha_source_promotion_gate_spec.md` | W-AUDIT-8d Per-Alpha-Source Live Promotion Gate spec（R-4 spec phase）|
| `2026-05-09--w_audit_8e_spec_as_code_spec.md` | W-AUDIT-8e Spec-as-Code + Module Lifecycle SM spec（R-5 spec phase）|

#### REF-20 governance amendments

| 文件 | 內容 |
|------|------|
| `governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` | AMD-2026-05-02-01 Decision Lease retrofit 路徑 A（Rust facade + router gate + Python IPC bridge + audit writer fix）|
| `governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md` | AMD-2026-05-03-01 Wave 7 P5 IMPL-accept-deploy-blocked（IMPL gate vs Deploy gate 2-stage 規範 + 4 AC + 失敗回退 + PM autonomous mode 嚴格門檻 4 條）|

#### REF-20 Sprint reports（cold audit + Sprint 1+2 retroactive）

| 文件 | 內容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md` | PA Sprint 1 4 並行 Track partition design + 5 push back |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md` | PA Sprint 2 Track E Decision Lease retrofit AMD-2026-05-02-01 partition + 5 AC SQL + 6 Phase 灰度 rollout |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_{a,b,c,d}_*.md` | E1 Sprint 1 4 Track IMPL reports（spawn argv / Rust manifest verify / Python 3 安全洞 / V049-V053 schema）|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_sprint1_4track_review.md` | E2 Sprint 1 round 1 4 Track review（Track C RETURN-TO-E1 1500 LOC enforce）|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_sprint1_round2_retrofit_review.md` | E2 Sprint 1 round 2 retrofit verify（Track A + C retrofit PASS + cross-track 7/7）|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_wave3_to_9_retroactive_master_review.md` | E2 Sprint 2 retroactive Wave 3-9 master review（10 LOW + 7 P2 ticket 提案 + Wave 7 PASS / Wave 3/4/5/6/8/9 CONDITIONAL）|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_final_closure_e4_cold_audit.md` | E4 cold audit baseline（pre-Sprint 1 真實 pytest/cargo 數字）|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_sprint1_e4_regression.md` | E4 Sprint 1 regression CONDITIONAL PASS（+13 PASS / +7 lib / 0 新 fail / 2 pre-existing carry-over）|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_wave3_to_9_retroactive_e4_cumulative.md` | E4 Sprint 2 retroactive Wave 3-9 cumulative（4 P0 forgery flag + 5 mock retroactive flag + 3 P2-FOLLOW-UP 提案）|

#### PM scanner / edge reports（2026-05-06）

| 文件 | 內容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-06--scanner_opportunity_integration_audit.md` | PM scanner opportunity integration audit：整合零散 scanner / edge / market judgment 模塊，定義 shadow-only 中性 opportunity 判斷邊界 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-06--scanner_opportunity_v1_shadow_implementation.md` | Scanner Opportunity v1 shadow implementation：Rust scanner opportunity math、intent details、Python reader、測試與對抗性審查結果 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-06--scanner_opportunity_healthcheck_51.md` | Scanner Opportunity `[51]` passive healthcheck：snapshot / intent / MLDE row proof coverage + opportunity_lcb_bps calibration，shadow-only |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-06--agenttodo_sprint_a_event_store_source_wiring.md` | AgentTodo Sprint A MAG-010..014 source wiring：default-off AgentEventStore、MessageBus sink、state/AI invocation hooks、`[52]` healthcheck；Linux row proof pending |

### governance_dev/ — 治理开发文档

> 注意：governance_dev/ 下早期文件使用大寫命名（如 `T2_EXECUTION_SUMMARY.md`），
> 晚於 2026-03-31 的新文件必須遵循 `YYYY-MM-DD--描述.md` 命名規範。

#### governance_dev/audits/ — ★ 审计报告

| 文件 | 内容 |
|------|------|
| `2026-03-30--round2_cold_functional_audit.md` | ★★★ Round 2 冷酷功能审核（任务 1/2/3：32% 完成度 + 架构融合 + Paper Trading 路线图） |
| `2026-03-30--governance_compliance_audit.md` | 治理合规审计（EX-05/06/07/DOC-01~08，合规度 ~65%） |
| `2026-03-30--pipeline_bridge_paper_engine_audit.md` | PipelineBridge + PaperTradingEngine 代码级审计（治理 gate 验证 + 止损验证 + 学习回调验证） |
| `2026-03-31--gap_analysis_287_specs.md` | ★ 287 条治理规格 Gap 分析报告（76% 已实施：67A + 18B + 8C + 2D） |
| `2026-03-31--spec_requirements_287.md` | 287 条规格完整列表（Markdown 版，与 Gap 分析配套） |
| `2026-03-31--spec_requirements_287.json` | 287 条规格完整列表（JSON 机器可读版） |
| `2026-03-31--gap_analysis_findings.json` | Gap 分析发现结果（JSON 结构化输出） |
| `2026-03-31--gap_analysis_file_reference.md` | Gap 分析文件引用索引 |
| `2026-03-31--development_roadmap_v2.md` | 4-Phase 开发路线图 V2（基于 Gap 分析制定） |
| `2026-03-31--phase0_round2.5_audit_report.md` | Phase 0 Round 2.5 审计报告（2 P0 + 1 P1 修复 + 287 spec Gap 分析） |

#### governance_dev/audits/2026-03-30--全面審核/ — ★★★ 全系统冷酷功能审核（9 Batch）

| 文件 | 内容 |
|------|------|
| `00_審查計劃總綱.md` | 审查计划总纲 + 进度追踪（9 Batch，A-I） |
| `01_A_即時問題診斷.md` | ★★★ P0 根因分析：MA_Cross metadata falsy + FundingRate 错误 symbol（10/10 策略全失效） |
| `02_B_交易核心路徑.md` | 交易核心路径验证（B1-B7：状态机/Fill/PnL/round_trip 均正确） |
| `03_C_風控框架.md` | 风控框架验证（P1：drawdown gate 无强制执行；其余 C2-C8 均正确） |
| `04_D_學習系統.md` | 学习系统验证（E1 路径代码就绪，因 0 fills 未实际运行） |
| `05_E_AI治理層.md` | AI 治理层验证（H0/Decision Lease 完整；AI 调用合法跳过） |
| `06_F_掃描器策略部署.md` | 扫描器与策略部署验证（5min 周期、40% 过滤、WS 动态订阅均正确） |
| `07_G_GUI_API端點.md` | GUI 与 API 端点验证（所有关键端点存在，数据源正确） |
| `08_H_測試健康度.md` | 测试健康度（2,166 通过；P0 bug 路径无测试覆盖） |
| `09_I_代碼品質.md` | 代码品质扫描（无 TODO/FIXME/silent except；硬编码值均有注释） |
| `99_審查總結與修復清單.md` | ★★★ 审查总结：3 个问题（P0×2 + P1×1）+ 修复方案 + 系统健康全景 |

#### governance_dev/2026-03-30 Round 2 修复计划

| 文件 | 内容 |
|------|------|
| `2026-03-30--round2_fix_plan_batches_7_12.md` | ★★ Batch 7-12 完整技术规格（Conductor + Guardian + Perception + Analyst + L2 + Paper→Live） |
| `2026-03-30--round2_fix_plan_EXECUTIVE_SUMMARY.md` | 修复计划管理摘要（缺口分析 + 策略 + 风险） |
| `2026-03-30--round2_fix_plan_QUICK_REFERENCE.md` | 修复计划开发速查（批次清单 + 依赖图 + 成本） |
| `2026-03-30--ROUND2_FIX_PLAN_INDEX.md` | 修复计划导航索引 |
| `2026-03-30--round2_pragmatic_fix_plan.md` | Round 2 务实修复计划（优先级排序 + 实施策略） |

#### governance_dev/ — 规格提取与287条治理规格（根目录文件）

| 文件 | 内容 |
|------|------|
| `README.md` | governance_dev 子目录自述文件 |
| `COMPREHENSIVE_SPEC_REQUIREMENTS.md` | 287 条治理规格完整列表（Markdown 版） |
| `COMPREHENSIVE_SPEC_REQUIREMENTS.json` | 287 条治理规格完整列表（JSON 机器可读版） |
| `SPECIFICATION_EXTRACTION_SUMMARY.md` | 规格提取摘要（13 份 .docx → 287 条结构化提取过程） |
| `SPECIFICATION_REGISTER.md` | 规格登记册（DOC/SM/EX 文件版本追踪） |
| `EXTRACTION_VALIDATION.txt` | 提取验证报告（规格数量/覆盖度/交叉引用校验） |
| `QUICK_START_REFERENCE.txt` | 治理开发快速入门参考 |

#### governance_dev/governance_extracts/ — 治理规格提取（5 份参考文档）

| 文件 | 内容 |
|------|------|
| `GOVERNANCE_DOCUMENTATION_INDEX.md` | 治理文档索引（13 份规格文件导航） |
| `GOVERNANCE_IMPLEMENTATION_CHECKLIST.md` | 治理实现清单（需求→代码映射 + 完成度追踪） |
| `GOVERNANCE_QUICK_REFERENCE.md` | 治理速查手册（16 根原则 + 状态机速览） |
| `OPENCLAW_GOVERNANCE_SUMMARY.md` | 治理综合摘要（13 份文件结构化总结） |
| `OPENCLAW_TECHNICAL_SPEC.md` | 技术规格总结（22 份治理规格集） |

#### governance_dev/changelogs/ — T2.01–T2.23 模组变更日志（23 份）

每份治理模组的实现变更日志，命名格式 `2026-03-29_T2.XX_模组名.md`。

#### governance_dev/phase2_execution/ — Phase 2 治理模組执行记录

| 文件 | 内容 |
|------|------|
| `T2_EXECUTION_SUMMARY.md` | ★ Phase 2 执行总览：21 模组矩阵 + 关键指标 |
| `T2_PM_QUALITY_AUDIT_REPORT.md` | Phase 2 PM 品质审核报告（T2.01–T2.23，整体 4/5，0 个 P0 blocker） |
| `T2_TW_COMMENT_AUDIT_REPORT.md` | Phase 2 TW 注释品质审核报告（评级 9.5/10，100% 双语覆盖） |
| `T2_TEST_RESULTS.md` | T2 测试套件执行报告（1485 测试） |
| `PM_FA_FULL_COMPLIANCE_AUDIT.md` | PM + FA 完整合规审计 |
| `PM_T0_ENGINEERING_AUDIT.md` | PM T0 工程审计 |
| `REVIEW_T2_CODE_QUALITY.md` | T2 代码质量审查 |
| `DOCUMENTATION_REVIEW_T2.07-LATEST.md` | T2.07+ 文档审查 |
| `FIXTURE_REFACTOR_SUMMARY.md` | 测试 Fixture 重构总结 |
| `TEST_FIXTURE_OVERVIEW.md` | 测试 Fixture 重构概览 |

#### governance_dev/phase3_integration/ — Phase 3 治理集成

| 文件 | 内容 |
|------|------|
| `PHASE3_WORK_PLAN.md` | Phase 3 工作计划（从 72% 到可安全交易） |
| `T3.01_FA_INTEGRATION_DESIGN.md` | FA 集成设计 |
| `T3_GOVERNANCE_INTEGRATION_GUIDE.md` | Phase 3 治理集成指南 |
| `PHASE3_CODE_REVIEW_REPORT.md` | Phase 3 代码审查报告 |
| `SECURITY_AUDIT_PHASE3.md` | Phase 3 安全审计报告 |
| `2026-03-30_TW_ENGINEERING_AUDIT_REPORT.md` | TW 工程审计报告 |
| `REVIEW_GOVERNANCE_GUI.md` | GUI 治理集成审查（PASS） |

#### governance_dev/phase4_acceptance/ — Phase 4 验收

| 文件 | 内容 |
|------|------|
| `T4.01_CC_COMPLIANCE_MATRIX.md` | CC 合规矩阵 |
| `T4.02_E4_TEST_COVERAGE_REPORT.md` | E4 测试覆盖报告 |
| `T4.03_A3_UX_REVIEW_REPORT.md` | A3 UX 审查报告 |
| `T4.04_R4_DOCUMENT_AUDIT_REPORT.md` | R4 文档审计报告 |
| `T4.05_PM_FINAL_ACCEPTANCE_REPORT.md` | PM 最终验收报告 |
| `T4.06_PM_GUI_GOVERNANCE_PLAN.md` | PM GUI 治理计划 |
| `TEST_REPORT_GOVERNANCE_E4.md` | E4 测试工程师验收报告 |

#### governance_dev/phase1–12 其他阶段 — 各阶段任务书 + PM 验收 + FA 缺口审计

每阶段通常包含：`PHASE*_TASK_BOOK`, `PHASE*_PM_ACCEPTANCE_REPORT`, `FA_GAP_AUDIT_REPORT`。
详见各子目录。

---

### CCAgentWorkSpace/ — Agent 獨立工作空間（2026-03-31 新增）

19 個 Agent 角色各自的獨立工作空間。每個 Agent 有 `profile.md`（角色定位）、`memory.md`（工作記憶）、`workspace/`（報告存檔）。

| 目錄 | Agent | 層次 |
|------|-------|------|
| `CCAgentWorkSpace/PM/` | Project Manager | 管理層 |
| `CCAgentWorkSpace/FA/` | Functional Auditor | 管理層 |
| `CCAgentWorkSpace/PA/` | Project Architect | 管理層 |
| `CCAgentWorkSpace/CC/` | Compliance Checker | 質量保證層 |
| `CCAgentWorkSpace/E2/` | Code Reviewer | 質量保證層 |
| `CCAgentWorkSpace/E3/` | Security Auditor | 質量保證層 |
| `CCAgentWorkSpace/E4/` | Test Engineer | 質量保證層 |
| `CCAgentWorkSpace/E5/` | Optimization Engineer | 質量保證層 |
| `CCAgentWorkSpace/E1/` | Backend Developer | 執行層 |
| `CCAgentWorkSpace/E1a/` | Frontend Developer | 執行層 |
| `CCAgentWorkSpace/A3/` | UX Auditor | 專項審查層 |
| `CCAgentWorkSpace/R4/` | Document Auditor | 專項審查層 |
| `CCAgentWorkSpace/TW/` | Technical Writer | 專項審查層 |
| `CCAgentWorkSpace/AI-E/` | AI Effectiveness Evaluator | 分析層 |
| `CCAgentWorkSpace/MIT/` | ML / DB Foundation Auditor | 專項審查層 |
| `CCAgentWorkSpace/BB/` | Bybit API Compatibility Auditor | 專項審查層 |
| `CCAgentWorkSpace/QA/` | Quality Assurance | 分析層 |
| `CCAgentWorkSpace/QC/` | Quantitative/Math Auditor | 專項審查層 |
| `CCAgentWorkSpace/Operator/` | Operator（人類 Operator 視角） | 管理層 |

---

### archive/ — TODO.md / CLAUDE.md §三 歷史敘述歸檔

| 文件 | 內容 |
|------|------|
| `2026-04-30--active_docs_cleanup_archive.md` | 2026-04-30 active docs cleanup 歸檔說明：CLAUDE/TODO/README 清理範圍、保留快照、Linear 高層同步摘要 |
| `2026-04-30--TODO-stale-active-mainline.md` | 2026-04-30 TODO 修正歸檔：從 active section 移出的過時 62-finding mainline / Post-Wave-H hotfixes 摘要 |
| `2026-04-30--CLAUDE-pre-cleanup-snapshot.md` | 2026-04-30 清理前 `CLAUDE.md` 完整快照 |
| `2026-04-30--TODO-pre-cleanup-snapshot.md` | 2026-04-30 清理前 `TODO.md` 完整快照 |
| `2026-04-30--README-pre-cleanup-snapshot.md` | 2026-04-30 清理前 `README.md` 完整快照 |
| `2026-04-29--62finding-batch-A-to-F.md` | ★★★★ 62-Finding Audit Remediation Batch A-F 全程歸檔（commits `bc3fa70` + `6539e4e` + `5db4e29`）：6 batch × 62 findings × Linear NCY-5~10 milestone 對應 + post-deploy healthcheck status（FAIL [12]+[22] / WARN [27]，live pipeline gate v1→v2）|
| `2026-04-29--strkusdt-p0-wave.md` | ★★★ STRKUSDT Dust Spiral P0 Wave 歸檔：F1 deploy `af48ee1` + F2-F7 6 PR merge（`1dff948` / `5ac7a80` / `310ae29` / `31c8206` / `1341c01` / `1edc6fe`）+ E4 combined 2252/0 + 8 healthcheck [22]-[29] + RCA 三層（entry_notional fail-open / Gate 2 cross-symbol / 41 phantom fills attribution）|
| `2026-04-01--completed_todo_archive_wave0_7_phase1_3.md` | Wave 0-7 / Phase 1-3 completed TODO archive |
| `2026-04-03--completed_todo_archive_batch9a_wave8_xp.md` | Batch 9a / Wave 8 XP completed TODO archive |
| `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` | Data storage architecture draft archive |
| `2026-04-03--rust_migration_master_plan_v2.md` | Rust migration master plan v2 archive |
| `2026-04-03--rust_migration_v2.5_consolidated.md` | Rust migration v2.5 consolidated archive |
| `2026-04-03--system_snapshot_external_analysis.md` | External system snapshot analysis archive |
| `2026-04-04--completed_todo_archive_phase0123_rust.md` | Phase 0-3 Rust completed TODO archive |
| `2026-04-06--completed_todo_archive_l3_phases.md` | L3 phases completed TODO archive |
| `2026-04-07--claude_md_section3_history_phase0_4.md` | CLAUDE.md §三 Phase 0-4 history archive |
| `2026-04-08--arch_rc1_1c_history_archive.md` | ARCH-RC1 1C history archive |
| `2026-04-08--main_docs_1c3_1c4_narrative.md` | Main docs 1C3/1C4 narrative archive |
| `2026-04-09--scanner_todo_phase_a_d_spec.md` | Scanner TODO Phase A-D spec archive |
| `2026-04-10--completed_todo_live_gui_dead_py.md` | Live GUI dead-Python completed TODO archive |
| `2026-04-11--completed_todo_3e_arch.md` | 3E architecture completed TODO archive |
| `2026-04-11--completed_todo_w19_w20_phase6.md` | W19/W20 Phase 6 completed TODO archive |
| `2026-04-12--changelog_archive_pre_0408.md` | Pre-2026-04-08 changelog archive |
| `2026-04-12--completed_todo_full_program_audit.md` | Full program audit completed TODO archive |
| `2026-04-13--changelog_archive_0408_0409.md` | 2026-04-08/09 changelog archive |
| `2026-04-14--completed_todo_w22_phantom_heal.md` | W22 phantom-heal completed TODO archive |
| `2026-04-15--claude_md_section3_snapshot.md` | CLAUDE.md §三 2026-04-15 snapshot |
| `2026-04-15--completed_todo_w22_engine_heal_edge_p3.md` | W22 engine-heal / Edge P3 completed TODO archive |
| `2026-04-15--phase5_promotion_edge_crisis_full.md` | Phase 5 promotion edge crisis archive |
| `2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md` | Strategy close-tag / Edge P3 dedup archive |
| `2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md` | P0 scanner phantom-live guard archive |
| `2026-04-20--claude_md_section3_snapshot.md` | CLAUDE.md §三 2026-04-20 snapshot |
| `2026-04-20--completed_todo_batch.md` | 2026-04-20 completed TODO batch archive |
| `2026-04-21--claude_md_section3_snapshot.md` | CLAUDE.md §三 2026-04-21 snapshot |
| `2026-04-21--completed_todo_batch.md` | 2026-04-21 completed TODO batch archive |
| `2026-04-22--step_0_derived_todo_batch.md` | Step 0 derived TODO batch archive |
| `2026-04-24--completed_todo_batch.md` | 2026-04-24 completed TODO batch archive |
| `2026-04-24--todo_snapshot_pre_refactor.md` | TODO pre-refactor snapshot archive |
| `2026-04-24--todo_v1_refactor_snapshot.md` | TODO v1 refactor snapshot archive |
| `2026-04-24--todo_v2_dual_axis_snapshot.md` | TODO v2 dual-axis snapshot archive |
| `2026-04-29--CLAUDE-pre-trim-snapshot.md` | CLAUDE.md pre-trim snapshot archive |
| `2026-04-29--TODO-pre-trim-snapshot.md` | TODO pre-trim snapshot archive |
| `2026-04-29--claude_md_section3_pre_04_27_detail.md` | CLAUDE.md §三 pre-2026-04-27 detail archive |
| `2026-04-29--wave-A-to-H-narrative.md` | Wave A-H narrative archive |
| `2026-05-01--completed_waves_1_2_3_and_backlog.md` | Completed Waves 1-3 and backlog archive |
| `2026-05-02--CLAUDE-pre-trim-snapshot.md` | CLAUDE.md 2026-05-02 pre-trim snapshot archive |
| `2026-05-02--TODO-pre-trim-snapshot.md` | TODO 2026-05-02 pre-trim snapshot archive |
| `2026-05-06--claude_md_stale_extract.md` | CLAUDE.md stale extract archive |
| `2026-05-06--readme_stale_extract.md` | README stale extract archive |
| `2026-05-06--todo_completed_extract.md` | TODO completed extract archive |
| `2026-05-07--todo_v12_agent_openclaw_replan_archive.md` | TODO v12 Agent/OpenClaw replan archive |
| `2026-05-09--claude_md_section5_pre_alpha_surface.md` | CLAUDE.md §五 pre-AlphaSurface architecture framing archive |
| `2026-05-09--qctodo_sprint_n0_n5_archive.md` | QCTODO Sprint N+0..N+5 planning archive |
| `2026-05-09--w_audit_verified_closed_archive.md` | W-AUDIT-1..7 verified-closed details archive |
| `2026-05-15--todo_v21_completion_cleanup_archive.md` | TODO v21 completion cleanup archive: completed sprint ledgers, DONE rows, and W-AUDIT priority delta |
| `2026-05-15--todo_v24_stale_rows_archive.md` | TODO v24 stale rows archive：過時 active rows / stale claims 歸檔（V079 pending / engine 5/8 binary / 舊 demo state / 舊 `[55]`/`[67]` 判斷）|
| `2026-05-16--todo_v36_completion_cleanup_archive.md` | TODO v36 completion cleanup archive：v35 / 2026-05-15..16 completed detail, closed wave rows, DONE P0/P1/P2 rows, and stale C1 running wording moved out of active TODO |
| `2026-05-16--close_maker_first_phase_1b_round1_archive.md` | Close-Maker-First Phase 1b Round 1 archive：design/governance/review history and active gates moved out of active TODO |
| `2026-05-16--stage1_demo_a4c_tombstone_cleanup.md` | Stage 1 Demo + A4-C tombstone cleanup archive：old W3 paper cohort / A4-C promotion markers removed from active docs while diagnostic tombstone remains |
| `2026-05-19--todo_v55_translation_archive.md` | TODO v55 translation archive：v55 中譯/重排過渡內容歸檔 |
| `2026-05-20--todo_v57_3_closure_cleanup_archive.md` | TODO v57.3 closure cleanup archive：v5.7 dispatch-safe patch 收尾 closed rows 清理歸檔 |
| `2026-05-21--todo_v57_5_route_change_purge.md` | TODO v57.5 route change purge archive：v5.7 dispatch-safe patch 收斂前過時 active route 清除 |
| `2026-05-21--todo_v58_layout_refactor_archive.md` | TODO v58 layout refactor archive：reverse-chronological dispatch view → grouped-by-module/wave view 重組過渡記錄 |
| `2026-05-21--todo_v60_archive.md` | TODO v60 archive：Sprint N+1 / Sprint A 收尾與已完成內容歸檔；v61 起以 v5.8 13-module thesis 為主軸（含 §A v5.7 12 prefix DONE / §B W-AUDIT-4b retained / §C H+I 批 P2/P3 closure / §D 過去 14d 9 批 closure narrative） |
| `2026-05-23--gui_bybit_first_pnl_refactor.md` | GUI Bybit first-PnL refactor archive：早期 GUI / Bybit PnL 顯示與重構歷史歸檔 |
| `2026-05-23--sprint_4plus_5plus_wave1_closure.md` | Sprint 4+ / 5+ Wave 1 closure archive：closure narrative 與過時 active TODO 內容歸檔 |
| `2026-05-31--todo_v92_archive.md` | TODO v92 archive：v75-91 歷史增量與 P0-EDGE cost-wall / alpha redirection / V### reconcile 決策歸檔 |
| `2026-05-31--todo_v93_pre_aeg_cleanup_archive.md` | TODO v93 pre-AEG cleanup archive：AEG cleanup 前 active TODO 快照與歷史敘事歸檔 |
| `2026-06-03--todo_v110_pre_cleanup_archive.md` | TODO v110 pre-cleanup archive：funding/OI backfill 落地後 active TODO 快照與 AEG/P0-EDGE 歷史敘事歸檔 |
| `2026-07-04--todo_v738_pre_slim_archive.md` | TODO v738 pre-slim archive：P1-7 瘦身前全文快照(v684-v738 演進殘骸/§1 DONE_WITH_CONCERNS 墓場/§2 60 行原文/§4 sha 清單) |
