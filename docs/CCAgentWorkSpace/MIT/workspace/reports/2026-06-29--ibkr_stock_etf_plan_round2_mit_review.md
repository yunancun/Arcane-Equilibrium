STATUS: DONE_WITH_CONCERNS
VERDICT: CONDITIONAL|FINDINGS=8(C:2/H:5/M:1/L:0)

# MIT 二轮审计 — IBKR Stock/ETF Paper + Shadow patched plan

审计对象：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`

结论：patched plan 已经把首轮 CC/FA/PA/E3/QC/MIT 的主要问题收敛成 Phase 0/1/3 blocker；这足够支撑 Phase 0 ADR/spec。它仍不是 one-time robust implementation 级别的数据设计。当前文本多处说“必须定义 DB evidence contract / evidence clock / formula appendix”，但没有给出 DDL、natural keys、constraints、migration guards、indexes、retention/compression、hash-chain event sourcing 或 machine-checkable DQ gate。因此 Phase 1 schema work 与 Phase 3 collector work 仍应阻断。

## 二轮裁决

- Phase 0：可继续。只允许 ADR/spec，不接 IBKR、不建 secret、不迁移 DB、不启动 runtime collector。
- Phase 1：不通过。schema 仍是 contract backlog，不是 DDL packet。
- Phase 3：不通过。evidence clock 与 collector 完整性仍不可机器判定。
- 不可逆数据债风险：高。若先落表/采集，会把错误 instrument identity、raw/adjusted 混用、缺失 cash/FX/cost lineage、paper/shadow 不可链接、scorecard 聚合当事实源等问题固化进历史数据。

## Findings

### C-01 — DDL-level schema contract 仍缺失，不能开始 Phase 1 migration

证据：

- patched plan 只列出 `broker.instruments`、`broker.instrument_listings`、`broker.market_sessions`、`broker.corporate_actions`、`broker.paper_orders`、`research.stock_shadow_*` 等表名，并补充“Schema 必须包含 instrument identity、universe version、corporate actions、market-data provenance、FX/cash ledger、cost model version、benchmark version、paper-vs-shadow reconciliation”这种要求，但没有列级 DDL、PK/FK/natural key、CHECK、索引、retention/compression 或 hypertable 决策：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:221`, `:236`, `:243`。
- Phase 1C 仍只写“DB migration source design + Linux dry-run packet”，验收为“migration design ready；若 apply，必须 Linux PG dry-run + double apply”，没有定义 migration packet 的最低 DDL 内容：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:512`, `:523`。
- ADR-0010 要求所有 V### migration 应用 Guard A/B/C 并二次 apply 幂等；ADR-0011 要求含 PG reflection/schema assumption 的 migration 在 E1 design 前做 Linux PG empirical dry-run：`docs/adr/0010-timescale-hypertable-with-guard-migrations.md:8`, `docs/adr/0011-v-migration-linux-pg-dry-run-mandatory.md:8`。
- PM 集成报告仍明确称“DB evidence contract is not yet a schema”：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:74`。

Required resolution：

- Phase 1 前提交独立 DDL packet：每张表的 columns、types、NOT NULL、CHECK、PK、FK、natural/unique keys、write owner、plain table vs hypertable、chunk interval、compression、retention、hot-path indexes、partial indexes、source-of-truth/derived 标记。
- migration spec 必须逐项标 Guard A/B/C、idempotency double-apply、Linux PG dry-run命令、rollback/repair policy、sqlx checksum policy。

### C-02 — Atomic evidence / immutable event sourcing 仍不足，scorecard 仍可能变成事实源

证据：

- plan 正确说 daily scorecard 只能是 derived artifact、atomic facts 才是 source of truth：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:241`。
- 但 plan 只写“append-only audit”和“日报可追溯至 append-only evidence”，没有 `audit.asset_lane_events` 的 event type、sequence、previous_hash、payload_hash、actor、source artifact、environment、asset_lane、broker、schema version：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:69`, `:651`。
- 首轮 MIT 已指出 daily aggregate 不能作为 reconstructability source，scorecard row 必须带 code commit、data snapshot ids、universe/cost/benchmark/fill-model versions 与 artifact hash，atomic facts 必须 immutable 或 append-only：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:199`, `:208`。

Required resolution：

- 把 `research.stock_etf_scorecard` 明确为 derived table/materialized artifact；禁止其成为唯一证据源。
- 定义 immutable facts：signals、quotes/bars、market-data snapshots、order intents、order state changes、fills、commissions、cash ledger、FX conversions、corporate actions、benchmark marks。
- 定义 hash-chain 或 immutable artifact reference：`previous_hash`、`payload_hash`、`input_artifact_hashes[]`、`producer_commit`、`schema_version`、`generated_at`。

### H-01 — Instrument identity / PIT universe 仍不完整，ticker 级设计会造成不可逆 join debt

证据：

- plan 只列出 `EquityInstrumentId`、ListingVenue、Currency、PrimaryExchange、TradabilityStatus 等类型名：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:99`。
- plan Phase 1 blocker 要求 DB evidence contract 包含 instrument identity / PIT universe，但没有列 natural keys：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:689`。
- 首轮 MIT 的最小 schema contract 要求 `broker.instruments` 包含 internal id、IBKR conid、secType、symbol、localSymbol、tradingClass、currency、FIGI/ISIN/CUSIP/SEDOL、issuer、valid_from/to；`broker.universe_versions` / `universe_members` 要有 rule hash、data cutoff、membership validity、PIT lifecycle proof：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:286`, `:288`。

Required resolution：

- instrument natural key 至少包含 `broker=ibkr`、`environment`、`conid`、`secType`、`currency`、`primaryExchange`/MIC、`valid_from/to`；ticker/symbol 只能作 display/alias。
- universe 必须是 PIT construction rule + member snapshot，不是“冻结今天幸存者”。每个 member 需 inclusion/exclusion reason、data cutoff、tradability source、lifecycle validity。

### H-02 — Market-data provenance 与 corporate-action adjustment 仍不能重放

证据：

- Phase 3 blocker 要求 market-data vendor/tier、PIT universe、corporate-action adjustment set 机器可检查，但没有 vendor matrix、tier enum、raw vs adjusted storage、adjustment-set DDL：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:555`。
- evidence clock blocker 要求 corporate-action / FX / fee source as-of records，但没有 source schema：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:700`。
- 首轮 MIT 最小 contract 要求 `market.stock_bars` / `market.stock_quotes` 记录 vendor、data tier、subscription id、exchange timestamp、receive timestamp、adjusted/raw flag、corporate-action adjustment set id、raw payload hash；`broker.corporate_actions` 要 action type、ex/record/pay/effective dates、ratio/cash/currency、source version：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:290`, `:291`。

Required resolution：

- 定义 vendor/tier matrix：bars、quotes、trades、corporate actions、benchmark returns、FX、fee/tax 各自来源、延迟/实时/历史修正语义。
- 每条 bar/quote 需 `exchange_ts`、`received_ts`、`request_ts/run_id`、`data_vendor`、`data_tier`、`raw_payload_hash`、`adjustment_policy`。
- corporate-action adjustment set 必须 versioned/replayable，scorecard 不得静默混用 raw 与 adjusted returns。

### H-03 — Cash/FX/cost/tax/benchmark 版本化仍不是 executable contract

证据：

- plan scorecard 列出 commission、spread/slippage、FX drag、FTT/tax placeholder、benchmark excess，但不是公式或版本表：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:430`, `:434`, `:435`, `:441`。
- Phase 3 blocker 要求 FX/cost model、benchmark 机器可检查；Phase 3 前 blocker 要求 frozen benchmark/cost hashes 与 corporate-action/FX/fee/tax source as-of records：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:555`, `:699`, `:700`。
- 首轮 QC 指出 benchmark 未定义会让 beta 伪装 alpha，成本墙必须预注册 base/conservative/punitive cost 与 cost-edge ratio：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_qc_review.md:64`, `:78`。
- 首轮 MIT 要求 `cost_model_versions` / components、`broker.fx_rates` / `broker.cash_ledger`、`benchmark_versions`：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:292`, `:293`, `:297`。

Required resolution：

- 定义 `cost_model_versions` 与 components：commission、regulatory/exchange/clearing/pass-through、CAT、FTT/stamp duty、withholding、FX spread/commission、slippage、fill penalty、source_url、retrieved_at、effective_from/to、code_hash。
- 定义 cash ledger：currency、account fingerprint、event type、trade date、settlement date、value date、source event id。
- 定义 benchmark versions：TR vs price return、currency、calendar、constituents/rebalance source、strategy-to-benchmark mapping、matched-control rules。
- “FTT/tax placeholder”必须改成 unknown => fail-closed/conservative，不得默认为 zero。

### H-04 — Paper-vs-shadow reconciliation 仍缺稳定链接与隔离动作

证据：

- plan 要求 paper fill 与 shadow fill 分表/分标记，并冻结 divergence thresholds，但没有 linking table 或 divergence taxonomy：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:238`, `:387`, `:572`。
- `ibkr_paper_order_lifecycle_v1` 只列状态、broker id、execution id、commission report id、idempotency key，没有 scorecard/reconciliation source ids：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:162`。
- 首轮 MIT 要求 stable `signal_id`、`order_intent_id`、`broker_order_id`、`execution_id`、`commission_report_id`、`scorecard_row_id`，并用 reconciliation table 分类 price/quantity/timing/venue/commission/FX/tax/corporate-action divergence：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:185`, `:194`。

Required resolution：

- 定义 `paper_shadow_reconciliations`：source ids、divergence kind、threshold version、quarantine action、resolved_by、resolved_at、payload_hash。
- 不允许 paper 与 shadow pooled profitability proof；divergence 越界的 day/strategy/symbol 必须自动 quarantine，不计入 feasibility。

### H-05 — Evidence-clock completeness / DQ gates 仍不可机器判定

证据：

- plan 已列 clock 起算条件：IBKR connector 5 个交易日绿灯、shadow collector 5 个交易日无缺口、scorecard 每日产出、manifest hash、benchmark/cost/universe/hypothesis/corporate-action/FX/fee source freeze、divergence threshold freeze：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:375`。
- 但 plan 没有 day-count algorithm、holiday/early-close/timezone、coverage threshold、symbol-level completeness、latency SLO、pause/reset/quarantine、manifest schema。
- 首轮 FA 同样指出“5 trading days no gap”和“scorecard daily output”不是 machine-checkable，缺 trading calendar/timezone、daily cutoff、completeness threshold、allowable outage、reset/pause、collector version freeze 等：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_fa_review.md:119`, `:126`。

Required resolution：

- `stock_etf_evidence_clock_v1` 必须是 manifest schema，不是 prose：calendar id、trading day、session coverage、expected symbols、bar/quote/fill completeness、max latency、DQ failures、gap taxonomy、quarantine ids、start/pause/reset state、all input hashes。
- 一天是否计入 6-8 周必须由 deterministic checker 输出 PASS/FAIL/QUARANTINED，不能人工解释。

### H-06 — Retention/compression/index 与 after-schedule reproducibility 没有闭环

证据：

- plan 没有提到 market stock bars/quotes/fills 的 hypertable、chunk interval、compression、retention、raw artifact retention 或 hot-path query indexes；只在一处说若涉及 migration 需 Linux dry-run/double-apply：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:247`。
- 本 repo 的 DB schema skill/ADR 要求 per-tick/per-bar/per-fill/per-event audit log 使用 hypertable/time partition，compression/retention 与 hot-path indexes 需设计在 schema 阶段；ADR-0010 要求 Guard C 对 hot-path index 做 `pg_get_indexdef()` drift check：`docs/adr/0010-timescale-hypertable-with-guard-migrations.md:8`。

Required resolution：

- Phase 1 DDL packet 必须说明哪些表是 hypertable：bars/quotes/order state/fills/audit events/scorecard history；哪些是 regular metadata：instrument registry、cost/benchmark versions。
- 明确 retention：raw broker responses、raw market data、adjusted data、scorecard artifacts、audit hash chain 分别保留多久；若会删除 raw data，必须有 reproducible archived artifact/hash。
- 建立 hot-path indexes：as-of instrument identity、latest quote/bar by instrument/session/vendor tier、scorecard by strategy/universe/date、paper/shadow links、DQ manifests by evidence_clock_id。

### M-01 — 统计验证字段已补入，但还不是可执行 pre-registration

证据：

- patched plan 已加入 independent observation count、benchmark alpha/beta/tracking error/IR、cost-edge ratio、PSR/DSR 或 deflated metric、pre-registered sample threshold，并明确“原始 100+ trade rows 不等于 100+ independent observations”：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:444`, `:447`, `:458`。
- 但它仍没有 primary endpoint、effect size、n_independent 计算器、cluster unit、purge/embargo、HAC/block bootstrap、multiple-testing K、verdict automation。
- ADR-0047 要求每个候选报告至少包含 regime、breadth、freshness、survivorship、execution realism、statistical gates：`docs/adr/0047-alpha-edge-regime-evidence-governance.md:42`。
- 首轮 QC 明确要求 sample-size/statistical-power gates 基于 independent observations，而非 raw trade count，并要求 PSR/DSR/deflation、block bootstrap CI、multiple-testing correction：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_qc_review.md:37`, `:170`。

Required resolution：

- Phase 3 前提交 pre-registration appendix：strategy family、hypothesis id、K count、horizon、holding period、benchmark、primary metric、minimum independent samples、cluster definitions、purge/embargo、CI/PSR/DSR thresholds、concentration veto、automatic verdict labels。
- 6-8 周默认只能是 engineering shakedown + preliminary feasibility screen；若样本不足，唯一合法输出是 `insufficient_evidence` 或 `research_promising`，不能给 durable-alpha proof。

## Review Questions Answered

1. patched plan 是否仍缺 DDL-level contracts / natural keys / constraints / migration guards / indexes / retention / immutable event sourcing？

是。它已经把这些作为 blocker 写入计划，但没有提供 DDL packet。Phase 1 前必须补 C-01、C-02、H-06。

2. instrument identity、market data provenance、corporate actions、cash/FX ledger、cost/tax model、benchmark versions、paper-vs-shadow reconciliation 是否足够完整？

不够。当前只达到“必须包含”的 checklist 级别；还没有 natural keys、source/version/as-of 字段、validity windows、raw/adjusted policy、现金流水、benchmark 构造、reconciliation taxonomy。见 H-01 至 H-04。

3. evidence-clock completeness 和 data-quality gates 是否 machine-checkable？

未达标。plan 已列 frozen hashes 和 5-day preconditions，但没有 deterministic manifest schema、day-count algorithm、coverage threshold、pause/reset/quarantine action。见 H-05。

4. Phase 1 schema work 前必须增加什么？

- 接受的 ADR/AMD，仅批准 `stock_etf_cash` read-only/paper/shadow research。
- 完整 DDL/ERD packet：PK/FK/natural keys、CHECK、indexes、hypertable/chunk/compression/retention、Guard A/B/C、Linux PG dry-run/double-apply。
- instrument/PIT universe/corporate-action/market-data/cash-FX/cost/benchmark/audit/reconciliation schema。
- scorecard derived-only 与 atomic immutable facts 的 source-of-truth 规则。

5. Phase 3 collector work 前必须增加什么？

- vendor/tier/provenance matrix；calendar/session/holiday/early-close completeness checker。
- frozen universe/cost/benchmark/hypothesis/corporate-action adjustment hashes。
- `stock_etf_evidence_clock_v1` manifest schema + PASS/FAIL checker。
- paper-vs-shadow divergence thresholds + quarantine actions。
- pre-registration appendix：sample size、independent observation、statistical gates、ADR-0047 evidence labels。

6. 哪些遗漏会造成不可逆数据债？

- 用 ticker/symbol 作为事实 join key，而不是 IBKR conid/secType/primaryExchange/currency/validity-window identity。
- 没有 `exchange_ts` / `received_ts` / `request_ts` / vendor tier，导致 PIT provenance 无法补救。
- raw 与 adjusted market data 未分层，corporate-action adjustment set 缺失。
- paper/shadow/order/fill/commission/FX/cash/corporate-action 无 stable link id。
- scorecard aggregate 先落地为事实源，后续无法重建 atomic path。
- cost/tax/FX/benchmark 版本和 source-as-of 缺失，after-cost alpha 不可复现。
- audit log 无 hash chain / immutable artifact reference，schedule 结束后证据完整性不可证明。

PM-facing gate decision: APPROVE_PHASE0_ONLY
