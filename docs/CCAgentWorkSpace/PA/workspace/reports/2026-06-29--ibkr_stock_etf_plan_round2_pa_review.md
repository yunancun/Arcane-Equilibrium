STATUS: DONE_WITH_CONCERNS
VERDICT: CONDITIONAL|FINDINGS=8(C:1/H:4/M:3/L:0)

# IBKR Stock/ETF Paper+Shadow 二轮 PA 架构与时序审计

日期：2026-06-29
角色：PA(default)
范围：二轮对抗性审计，报告-only。未改 runtime/code/TODO，未触碰 Linux `trade-core`、PG、服务、secrets、IBKR/Bybit 网络。

## 总结

补丁后的计划比第一轮明显收敛：`Broker` 与 `BrokerEnvironment` 已拆开，功能性 live flag 已删除，Phase 1 被拆成更小 slice，且第 11 节把 Phase 1+、IBKR API、secret slot、paper order、GUI runtime activation、evidence clock 全部标为 BLOCKED。

但它仍不能批准 Phase 1 conditional。核心问题不是模块名不对，而是 Phase 0/Phase 1 边界仍不够硬：计划一边说 Phase 1D 才定义 lane-scoped IPC/order-lifecycle Interface，另一边又说 Phase 1 前必须完成该 Interface、DB evidence contract、flag/secret matrix、Python no-write guard、GUI contract。若 PM 现在把 Phase 1A-D 派给 E1，E1 仍会被迫发明契约，产生浅抽象和 ad hoc connector。

PM gate 建议：只批准 Phase 0，并把 Phase 0 扩成 ADR + interface/spec packet。Phase 1 只能在这些 packet 被接受后作为实现任务启动。

## Findings

### C1 - Phase 0/Phase 1 边界仍自相矛盾，E1 会被迫发明 Interface

Evidence:
- 计划把 Phase 1 拆成 `1A` type reservation、`1B` flag/readiness、`1C` DB migration source design、`1D` lane-scoped IPC/order-lifecycle Interface（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:504`）。
- 但第 11 节又要求 Phase 1 前必须完成 Rust lane-scoped IPC/order Interface、`ibkr_paper_order_lifecycle_v1`、DB evidence contract、feature flag/secret invariant matrix、Python no-write guard、GUI display/filter-only contract（同文件 `:680`）。
- PM 集成报告也明确 Phase 1+ implementation blocked，只允许 Phase 0 ADR/spec packet（`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:120`）。

Required resolution:
- 将当前 Phase 1A-D 中的“Interface/spec/design”部分前移为 Phase 0 deliverables：`Phase0A governance ADR/AMD`、`Phase0B type/IPC/lifecycle specs`、`Phase0C DB/security/GUI/evidence specs`。
- Phase 1 只能是“实现已接受 spec 的代码 slice”，不得包含未决架构决策。
- E1 dispatch 前必须有可测试的输入输出契约、denial reasons、fixtures、negative tests 清单。

### H1 - `AssetLane + Broker + BrokerEnvironment` 必要但不充分，缺 broker capability registry / operation authority matrix

Evidence:
- 当前计划只列出 `AssetLane::{CryptoPerp, StockEtfCash, CfdMargin}`、`Broker::{Bybit, Ibkr}`、`BrokerEnvironment::{ReadOnly, Paper, LiveReserved}`（计划 `:94`）。
- 计划列出 flags 和 secret/API/session 补充项，但没有定义“某 broker/env 支持哪些 operation、需要哪些 auth/lease/attestation、禁止哪些 operation”的注册表（计划 `:261`）。
- E3 第一轮已要求按 method/action/environment 列 IBKR allowlist，并默认拒绝 transfer/withdraw/live/margin/options/CFD 等动作（`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md:43`）。

Required resolution:
- Phase 0 必须产出 `broker_capability_registry_v1` 或等价 spec，至少包含：operation taxonomy、allowed lanes、required signed envelope、Decision Lease/Guardian requirements、paper attestation requirement、rate-limit/transport policy、audit event type、typed-denial reason。
- 所有 flags 只能改变 visibility/readiness，不得直接授予 capability。
- `LiveReserved`、CFD、margin、short、options、transfer 必须在 registry 中是 typed-deny，不是未实现分支。

### H2 - 市场数据、账户/组合、现金/FX 模型仍不是实现级接口

Evidence:
- 计划列出 `broker.instruments`、`broker.market_sessions`、`broker.fx_rates`、`broker.paper_orders`、`research.stock_etf_scorecard` 等表名，但承认 table list 还只是目标拆分（计划 `:221`）。
- MIT 明确判定 DB plan 是 table names, not schema，缺 PK/FK/CHECK/index/hypertable/lineage（`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:33`）。
- MIT 还指出 market-data vendor/tier/provenance、FX/cash ledger、settlement/withholding、benchmark provenance 均未形成机器可检查模型（MIT 报告 `:80`, `:129`, `:171`）。

Required resolution:
- Phase 0 必须补 `stock_market_data_provenance_v1`、`broker_account_portfolio_cash_ledger_v1`、`cost_model_version_v1`、`benchmark_versions_v1`。
- DB contract 必须到 DDL/ERD 级别：keys、constraints、lineage、plain table vs hypertable、retention/compression、idempotent migration guard、Linux PG dry-run packet。
- 没有这些 contract 前，不得派 Phase 1C migration implementation。

### H3 - Paper order lifecycle 仍缺事件日志、kill switch、runbook 和异常恢复闭环

Evidence:
- 计划要求 `ibkr_paper_order_lifecycle_v1` 包含 states、ids、restart recovery、`STATE_UNKNOWN -> MANUAL_REVIEW_REQUIRED`、typed denial reasons（计划 `:162`），这是正确方向。
- 但该段没有定义 lifecycle event log、hash chain、manual broker-side mutation handling、kill switch、operator runbook、disable/cleanup path。
- E3 指出 runtime/deploy surface 仍需 topology、local binding、process ownership、service policy、kill switch，且不得在未审查时安装 IBKR process 到 `trade-core`（E3 报告 `:47`, `:76`, `:88`）。

Required resolution:
- 增加 `broker_lifecycle_event_log_v1`：每个 submit/ack/partial_fill/fill/cancel/replace/reject/inactive/manual_unknown/recovery 事件都有 monotonic sequence、previous hash 或 immutable artifact ref、broker ids、actor/source、environment、asset_lane。
- 增加 `stock_etf_kill_switch_and_runbook_v1`：如何禁用 lane、冻结 paper rehearsal、停止 connector、处理 unknown state、清理 stale orders、导出审计包、恢复只读。
- kill switch 必须在 Rust authority 与 control-plane status 中可见，并且高于普通 feature flag。

### H4 - 现有 Paper IPC/OrderRouter 不能复用，计划还未给新 IPC command schema

Evidence:
- 当前 Rust `Venue`/`AssetClass` 是 ADR-0040 的 M13 interface reservation，明确“不含 venue dispatch / trade routing / method body”（`rust/openclaw_types/src/asset_venue.rs:4`）。
- 当前 `OrderRouter` 也是 fail-loud trait stub，默认 method body 不实现，且 helper `OrderRequest` 仍是 venue/asset-class 形状（`rust/openclaw_engine/src/order_router.rs:1`, `:44`）。
- 现有 `submit_paper_order` IPC 只接 `symbol/side/qty/order_type/limit_price/confidence/strategy`，再转 `PipelineCommand::SubmitOrder`，没有 asset lane、broker、environment、instrument identity、currency、listing venue、cost model、paper/shadow provenance（`rust/openclaw_engine/src/ipc_server/handlers/strategy.rs:157`; Python caller `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py:435`）。
- 计划只说新增 `lane_scoped_ipc` 且禁止复用既有 `submit_paper_order`，但未列 command/request/response schema（计划 `:143`）。

Required resolution:
- Phase 0 必须提交 `lane_scoped_ipc_v1`：command names、request schema、response schema、required auth envelope fields、audit ids、idempotency keys、typed denial enum、versioning/compat rules。
- 在该 spec 被接受前，任何“只加 IBKR adapter”或“先复用 submit_paper_order”都应 BLOCK。
- 现有 crypto/paper IPC 行为必须保持 backward compatible，并有 contract tests 证明默认 lane 为 `crypto_perp` 时不变。

### M1 - 多个模块仍有过度泛化或浅模块风险

Evidence:
- 计划列 `openclaw_core::calendar`、`openclaw_core::stock_etf_risk`、`equity_instrument`、`asset_lane_routes`、`evidence_routes` 等模块（计划 `:99`, `:173`）。
- 第一轮 PA 已指出 `openclaw_core::calendar` 容易过度泛化、`equity_instrument` 容易前置过多产品 taxonomy、`stock_etf_risk` 需要 pure/runtime split（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_pa_review.md:185`）。

Required resolution:
- 每个模块必须有“首个 caller + 输入输出 + 不做什么 + denial behavior”。没有两个以上真实 caller 时，不建 broad reusable module。
- 初始只实现 narrow interfaces：session calendar for evidence/risk gates、instrument identity needed for US large/ETF v1、cash-only risk predicates、derived evidence views。
- `evidence_routes` 不得成为跨 lane 业务层；route handlers 只能 parse -> call service -> format，业务逻辑下沉。

### M2 - GUI 时序仍有冲突：login selector 与 badge/readiness-first 同时存在

Evidence:
- 计划 5.1 说登录成功后第一屏进入 asset lane selector（计划 `:305`）。
- 计划 7 Phase 4 又说第一个 GUI slice 应是 lane badge/readiness page，不是立即把 login-success selector 作为主流程（计划 `:574`）。
- 现有 console tab registry 是静态 tab，当前 `paper` 标记为 `Legacy Paper`（`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/console.html:351`），README 也说 paper 是 archive/diagnostic，不是 promotion lane（`README.md:24`）。

Required resolution:
- 移除或降级 login-success selector 作为第一 slice；Phase 4A 只做默认 `crypto_perp` badge/readiness + stock read-only status page。
- 完整 selector 必须等 lane-scoped backend contract、auth/flag matrix、route/cache partition tests 都通过后再做。
- GUI contract 必须证明 client lane state 不授权、不改变 broker environment、不选择 risk config、不改变 order route。

### M3 - rollback/disable/cleanup 与 crypto backward compatibility 仍不足

Evidence:
- 计划说 crypto governance 不因本计划变更（计划 `:59`），GUI 验收说 crypto tabs 不回归（计划 `:590`）。
- 计划也说若无 after-cost edge，关闭或降级 stock/ETF lane（计划 `:653`）。
- 但没有列出 lane disable runbook、secret cleanup、connector teardown、DB artifact retention/archival、migration rollback policy、GUI cache cleanup、existing Bybit route/IPC regression suite。
- 当前项目硬边界仍是 Bybit only execution、Rust authority、Python control-plane（`CLAUDE.md:27`），README 也声明 Bybit 是唯一下单/执行 adapter（`README.md:6`）。

Required resolution:
- Phase 0 增加 `stock_etf_disable_cleanup_runbook_v1`：如何回到 no-stock state，如何证明 live slot absent/empty，如何保留/归档 evidence，如何关闭 GUI surface，如何处理 DB migration rollback/forward-only retention。
- Phase 1 acceptance 增加 crypto regression gate：existing Bybit default lane、Decision Lease display、risk config、Demo/LiveDemo/Live routes、`submit_paper_order` IPC、paper archive tab 均保持现状。
- 任何 DB migration 必须说明 forward-only cleanup/archival，而不是依赖 destructive rollback。

## 直接回答审计问题

1. `AssetLane + Broker + BrokerEnvironment` 是否足够？

不够。它们是必要 taxonomy，但缺少 capability registry、operation authority matrix、market-data source model、account/portfolio/cash ledger model、lifecycle event log、kill switch、runbook。没有这些，E1 会把 policy 分散写进 routes、flags、connector 和 SQL。

2. Phase plan 是否避免技术债？

已改善，但仍需要再拆。当前 Phase 1A-D 混有“定义 Interface”和“实现 Interface”。应把所有 Interface-only specs 放入 Phase 0 packet，Phase 1 才开始代码实现。否则 Phase 1 会变成半设计半实现，债务很快固化。

3. 哪些模块可能过度泛化或浅？

高风险：`asset_lane_router`、`broker_order_lifecycle`、`openclaw_core::calendar`、`equity_instrument`、`stock_etf_risk`、`stock_shadow_engine`、`evidence_routes`、Python `ibkr_connector/paper_client.py`。这些名字合理，但必须先有 caller obligations、denial enum、lineage fields、fixtures 和 negative tests。

4. E1 前必须存在的 exact docs/specs

- ADR/AMD: `stock_etf_cash` read-only/paper/shadow scope, forbidden live/margin/short/options/CFD/transfer.
- `asset_lane_taxonomy_v1`.
- `broker_capability_registry_v1` / operation authority matrix.
- `non_bybit_api_allowlist_v1`.
- `ibkr_api_session_topology_v1`.
- `feature_flag_secret_auth_matrix_v1`.
- `lane_scoped_ipc_v1`.
- `ibkr_paper_order_lifecycle_v1`.
- `broker_lifecycle_event_log_v1`.
- `stock_etf_db_evidence_ddl_v1`.
- `market_data_provenance_v1`.
- `broker_account_portfolio_cash_ledger_v1`.
- `cost_model_version_v1`.
- `benchmark_versions_v1`.
- `stock_shadow_fill_model_v1`.
- `gui_lane_contract_v1` with crypto regression tests.
- `stock_etf_evidence_clock_v1`.
- `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`.

5. rollback/disable/cleanup 与 crypto backward compatibility 是否足够？

不足。计划已有 default-off、live-denied、crypto-unchanged 的方向，但缺少可执行 runbook、cleanup proof、migration retention policy、GUI cache/route cleanup、Bybit regression contract。这个缺口必须在 Phase 0 或 Phase 1 gate 前补齐。

## Gate Decision

PM-facing gate decision: APPROVE_PHASE0_ONLY
