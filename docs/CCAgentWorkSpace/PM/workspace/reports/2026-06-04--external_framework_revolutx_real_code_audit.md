# 2026-06-04 External Framework + Revolut X Real-Code Audit

Role: PM
Scope: Zhihu-linked external framework audit, related papers/projects, latest Revolut X API practices, and strict comparison against the real `srv/` codebase.
Status: audit only; no trading code/config changes.

## Source Reliability

- The two original Zhihu URLs were not directly readable from this environment: both direct access and `r.jina.ai` snapshots returned Zhihu login/security-verification pages. I therefore used the visible mirrored article text only as a lead, not as authority.
- Primary sources checked instead:
  - RD-Agent(Q): https://arxiv.org/abs/2505.15155 and https://github.com/microsoft/RD-Agent
  - AlphaAgent: https://arxiv.org/abs/2502.16789 and https://github.com/RndmVariableQ/AlphaAgent
  - QuantaAlpha: https://arxiv.org/abs/2602.07085 and https://github.com/QuantaAlpha/QuantaAlpha
  - Trading skill/process references: https://github.com/tradermonty/claude-trading-skills plus general skill-library repos.
  - Revolut X: https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api and https://github.com/revolut-engineering/revolut-x-api
- Full PDF extraction was blocked locally (`pdftotext`, `mutool`, `qpdf`, `gs`, `pdfinfo`, and Python PDF libs were unavailable). I used arXiv pages, available ar5iv HTML for AlphaAgent, and official repo/docs. Claims beyond those are treated as non-authoritative.
- Claude's previous memory file was useful as an index of leads, but every material conclusion below was checked against code or primary sources.

## Addendum: Pasted Zhihu Body + QuantaAlpha Repo

The user later provided the pasted body of one Zhihu article. That text materially improves source coverage, but it also confirms the article is an advertisement-style synthesis rather than a clean primary source. It mixes four distinct things:

1. Saulius Tautvaisas's QuantaAlpha-inspired Claude Code commodity-futures experiment.
2. The official QuantaAlpha arXiv paper and GitHub repo.
3. Generic Claude Code / skill-library promotion.
4. Finance-agent benchmark claims and unrelated trading-agent anecdotes.

Verified corrections:

- The Saulius commodity-futures experiment is real enough to cite as a blog/LinkedIn lead: his post describes 53 futures contracts, a Dec. 31 2022 train/test split, a 21-trading-day embargo, 20 factors over 5 rounds, and a `vol_regime_adaptive_momentum` factor with test Sharpe 1.72 / return 38.7% / max drawdown -15.8%.
- That experiment is not the official QuantaAlpha paper result. It says he modified the open-source QuantaAlpha framework to use Claude Code as the reasoning engine.
- The pasted article folds Saulius's later LightGBM recursive-improvement post into the first experiment. The DSR statement needs precision: the later post says permutation tests passed with p < 0.001, but DSR results were mixed; high validation-Sharpe models passed, moderate Sharpe models did not. It is not evidence that every model passed DSR.
- Official QuantaAlpha arXiv v3 (2026-05-18) reports IC 0.0472, ARR 4.68%, MDD 11.8% in the abstract. The GitHub README still advertises IC 0.1501, Rank IC 0.1465, ARR 27.75%, MDD 7.98%. This is version/surface drift and should be treated as a warning sign when quoting headline metrics.
- The pasted star counts for skill libraries are stale. As of this audit, GitHub reports much higher counts for `VoltAgent/awesome-agent-skills`, `K-Dense-AI/scientific-agent-skills`, and others. Star counts are not decision evidence anyway.

QuantaAlpha repo inspection:

- Repo: `QuantaAlpha/QuantaAlpha`, default branch `main`, latest inspected commit `be80873637d59f6956b64ba38484a78209354158` dated 2026-05-06.
- GitHub API reported no detected license, while README displays an MIT badge. The clone root did not contain a `LICENSE` file.
- The repo is more than a README: it has Qlib/HDF5 data setup, an experiment config, a factor mining pipeline, AST parsing, complexity checks, redundancy checks, mutation/crossover operators, and independent Qlib backtesting.
- Default `configs/experiment.yaml` has `quality_gate.consistency_enabled: false`, while `complexity_enabled` and `redundancy_enabled` are true. So the paper's semantic-consistency idea exists in code, but is not default-enforced by the main config inspected here.
- `configs/backtest.yaml` uses chronological train/valid/test splits, Qlib `CSRankNorm`, and transaction costs (`open_cost=0.0005`, `close_cost=0.0015`, `min_cost=5`). I did not find repo-level DSR/PBO/CPCV/permutation gates comparable to our statistical governance tooling.

Value extracted for TradeBot:

- Saulius's strongest transferable lesson is not the 1.72 Sharpe. It is the disciplined separation between evolution feedback and hidden OOS test metrics, plus the later admission that DSR is harsh and validation RankIC alone did not predict OOS RankIC.
- QuantaAlpha's strongest transferable repo pattern is a small operator/AST layer with explicit complexity and redundancy checks. This is useful for proposal quality control, not as proof of live edge.
- For TradeBot, the first adaptation should be a narrow `SignalSpec` / `FactorSpec` manifest and static checker:
  - permitted fields/operators,
  - PIT alignment contract,
  - holding horizon,
  - cost/fill assumptions,
  - complexity and duplicate-expression checks,
  - expected market/beta exposure,
  - mandatory residual edge evidence.
- Do not build broad QuantaAlpha-style evolution before `R_beta` exists. Otherwise the system will efficiently evolve BTC/regime beta, cost artifacts, or data leaks.

## Second-Pass Real-Code Corrections

This pass intentionally revisited the harshest claims against TradeBot and corrected the ones that were too broad.

### Correction 1: TradeBot is not purely OHLCV/textbook at the feature layer

Claude's memory says ingestion is strong but active strategy breadth is mostly textbook TA. That is directionally right for strategy logic, but too weak on the ML feature surface:

- `rust/openclaw_engine/src/edge_predictor/features.rs:74-92` defines a 17-feature canonical vector including `funding_rate`, `basis_bps`, `orderbook_imbalance_top5`, `spread_bps`, `confluence_score`, position context, time-of-day, and funding-window flags.
- `program_code/ml_training/parquet_etl.py:40-58` mirrors the same 17-feature order for training, with schema hashes to catch train/serve drift.
- `rust/openclaw_engine/src/edge_predictor/feature_builder.rs:55-99` actually builds funding, basis, orderbook imbalance, and spread from runtime context.
- But `rust/openclaw_engine/src/linucb/runtime.rs:34-43` and `program_code/ml_training/linucb_trainer.py:47-56` still use an 8-feature LinUCB context: ATR, RSI, Bollinger bandwidth, Hurst, ADX, volume ratio, and time-of-day.

Verdict: the repo is better than "only OHLCV", but the richer feature vector is not the same as a proven residual alpha discovery loop. The missing gate remains: these features can still encode market beta, volatility beta, liquidity regime, or cost/fill artifacts unless residualized and tested out-of-sample.

### Correction 2: liquidation data is partially wired, but liquidation alpha is not active

The earlier "liquidation dormant" wording needs precision:

- `rust/openclaw_engine/src/scanner/runner.rs:57-64` includes `allLiquidation.{symbol}` in dynamic WebSocket topics.
- `rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs` has a real `LiquidationPulseAggregator`.
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:261-270` can inject a `LiquidationPulsePanel` into `AlphaSurface`.

But the active alpha path is still not closed:

- `rust/openclaw_engine/src/panel_aggregator/mod.rs:549-559` says the liquidation slot factory is provider-only and main-process wiring is left to a later wave.
- Repo search found no caller of `set_liquidation_pulse_panel_slot(...)` outside its definition.
- `settings/strategy_params_demo.toml:233-243` keeps `liquidation_cascade_fade.active = false`.

Verdict: do not say "liquidation data is absent"; say "liquidation data plumbing exists, but the consumer/strategy path is not an active alpha surface by default."

### Correction 3: DSR/PBO evidence is more wired than "pure advisory", but still late-stage

The previous critique that `dsr_gate.py` / `pbo_gate.py` are advisory remains true for those standalone modules, but the repo has a more serious promotion-evidence path:

- `program_code/ml_training/promotion_evidence.py:126-173` builds strategy promotion evidence from real James-Stein raw return series.
- `program_code/ml_training/promotion_evidence.py:176-206` fail-closes if selection-bias evaluation throws.
- `program_code/ml_training/promotion_evidence.py:407-535` pushes selection-bias and tail-risk reports into the promotion gate and optional DB ledger/report tables.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:525` runs the promotion evidence push after the James-Stein cycle; `:602-650` restricts it to the demo promotion lane.

Limits still matter:

- This operates after realized/demo edge estimation, not as a proposal-time alpha/factor gate.
- The scheduler add-on catches top-level errors fail-open, so it should not be treated as a universal hard block.
- It still lacks estimated residual BTC/market beta as a first-class evidence field.

Verdict: revise "statistical tooling is not wired" to "statistical tooling is partially wired for promotion, but not yet unified across proposal, research, replay, and live-candidate gates."

### Correction 4: evidence-source filtering is good, but schema fallback is a promotion risk

`program_code/ml_training/mlde_demo_applier_evidence_filter.py:67-90` excludes `synthetic_replay` by default, which is the right conservative default. However, `:189-214` returns an empty filter if `evidence_source_tier` is missing, and `:235-275` weakens replay manifest checks when physical columns/tables are missing.

That is reasonable for forward compatibility, but candidate promotion should not silently become less strict. If the schema cannot prove evidence source and replay lineage, the output should be marked `research_only` or `pending_schema`, not treated as normal promotion evidence.

## Claude Memory Reassessment

I agree with these Claude conclusions:

- P0 should be a repo-owned BTC/market residual alpha module plus proposal/live-candidate `R_beta` gate.
- The multiday trend volatility-regime leak is real and should be fixed by porting the funding-tilt expanding/prior-window pattern.
- External projects are strongest upstream; our downstream execution/governance is stronger than theirs, but our alpha discovery loop is weaker.
- Revolut X's portable lesson is mostly idempotent client order IDs, not Ed25519 or venue mechanics.
- A broad QuantaAlpha-style DSL/evolution stack should not precede residual-alpha validation.

I would modify these Claude conclusions:

- "Real run is all textbook TA" is too strong. Strategy activation is narrow, but the Edge-P3 feature vector already includes funding, basis, orderbook imbalance, spread, and position context.
- "DSR/PBO are advisory-only" is too strong. Promotion evidence is wired into the demo edge-estimator cycle. The right critique is that it is late-stage and not universal.
- "Liquidation is double dormant" is too strong if read as data absence. The topic/parser/aggregator/surface plumbing exists; the missing part is active main wiring plus enabled strategy consumer.
- QuantaAlpha is more practically useful than just an idea: its AST parsing, complexity, redundancy, mutation/crossover, and trajectory memory are concrete implementation patterns. Its headline metrics and default gates are not authority.

I would add these missing priorities:

- Add a test-blind research protocol: agents may use train/validation feedback for iteration, but a reserved hidden OOS window should be opened only once per candidate family.
- Add a mandatory `SignalSpec` / `FactorSpec` manifest before more alpha work: hypothesis, allowed fields, point-in-time contract, horizon, expected turnover, cost/fill assumptions, raw edge, residual edge, DSR/PBO/CPCV, sample power, evidence tier, and failure taxonomy.
- Add failure taxonomy to postmortems: `no_edge`, `beta_edge`, `cost_defeat`, `fill_failure`, `regime_only`, `data_leak`, `sample_insufficient`, `implementation_bug`.
- Treat missing evidence lineage columns as a downgrade, not as silent compatibility.

## External Framework Takeaways

### RD-Agent(Q)

Useful ideas:

- Treat research as an iterative hypothesis -> implementation -> backtest -> feedback loop, not one-shot prompting.
- Use an adaptive scheduler/bandit to decide whether to spend budget on factor exploration, model innovation, or data improvement.
- Keep factor and model search coupled; factor mining without downstream model/portfolio validation is incomplete.

Limits for us:

- The paper is Qlib/equity-index oriented, with benchmark claims on CSI/DJIA/SP500-style datasets. It does not prove live crypto edge under Bybit fees, maker/taker fill constraints, liquidation/funding microstructure, or our governance envelope.
- It is stronger upstream automation, not a replacement for our downstream live-safety gates.

Adoptable for TradeBot:

- A small "research packet" schema for candidate ideas: hypothesis, fields, time alignment, implementation, expected holding period, beta exposure hypothesis, forbidden future data, cost model, and validation plan.
- A scheduler that prioritizes candidates by unresolved evidence gaps, not only expected return.

### AlphaAgent

Useful ideas:

- AST-based originality checking against existing factor libraries.
- Hypothesis-factor alignment scoring: factor code must actually use fields implied by the stated market mechanism.
- Complexity penalties: symbolic length, parameter count, and feature count should be explicit.

Limits for us:

- Originality is not alpha. A novel factor can still just be BTC beta, volatility beta, or a cost illusion.
- The core missing check for our use case is residualized crypto beta performance; AlphaAgent's novelty mechanism does not solve that by itself.

Adoptable for TradeBot:

- Add a proposal-time "semantic/code mismatch" check before spending compute on backtests.
- Add a simple AST/operator-tree duplicate detector only after the residual alpha gate exists.

### QuantaAlpha

Useful ideas:

- DSL/operator grammar gives controllable factor generation and easier static checks than arbitrary generated Python.
- Trajectory-level mutation/crossover is more useful than mutating final code only; it lets the system reuse good hypotheses, data choices, and validation failures.
- Factor memory bank can prevent rediscovering the same idea.

Limits for us:

- The arXiv v3 abstract reports IC 0.0472, ARR 4.68%, MDD 11.8%; some repo/HuggingFace/marketing surfaces show much higher numbers such as IC 0.1501 and ARR 27.75%. Treat headline metrics as version-sensitive and promotional until reproduced.
- Building a full DSL now is premature if our current candidate funnel cannot first distinguish residual alpha from BTC beta.

Adoptable for TradeBot:

- Start with a narrow DSL-like candidate manifest and static validator; postpone general evolution until P0/P1 residual evidence is in place.

### Trading Skill Libraries

Most useful pattern is not "more skills"; it is codifying review habits:

- Signal postmortem: regime-tagged, post-fee, attribution-backed, and linked to next parameter/weight decisions.
- Edge strategy review: force explicit answers on cost defeat, crowding, liquidity, sample power, market beta, and operational failure modes.
- Strategy pivot designer: when a signal dies, identify whether the failure is cost, beta, regime, data, or implementation before changing parameters.

## Revolut X Findings

Official docs confirm Revolut X REST auth uses:

- `X-Revx-API-Key`
- `X-Revx-Timestamp`
- `X-Revx-Signature`
- Ed25519 signing over timestamp + HTTP method + request path + query + minified body, with no separators.

The open-source SDK/client currently auto-mints `client_order_id` with a UUID when placing an order. Its repo latest public surface showed release `1.0.43` on 2026-06-01 and the SDK repo was updated on 2026-06-03.

What is useful for us:

- Auto-generate client order IDs when missing.
- Enforce local credential file permission hygiene and narrow read access for any future exchange connector tooling.
- Keep MCP/agent trading tools read-only unless explicitly routed through the execution authority.

What is not portable:

- Revolut's Ed25519 headers do not map to Bybit's HMAC scheme.
- Revolut symbol format and order endpoint semantics are not relevant to the current Bybit connector.

Concrete TradeBot gap:

- Rust `CreateOrderRequest.order_link_id` is optional and only emitted if provided: `rust/openclaw_engine/src/order_manager.rs:123-144` and `:354-389`.
- Python `BybitRestClient.place_order` also only sends `orderLinkId` if caller passes it: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:814-892`.
- Therefore the portable Revolut X improvement is a small idempotency/traceability patch: auto-mint `orderLinkId` when missing, with strategy/symbol/time prefix plus collision-resistant suffix, respecting Bybit length constraints.

## Real Code Verdict

### 1. Missing P0: reusable beta/BTC residual alpha gate

I found no repo-owned reusable residualizer or proposal-time `R_beta` gate. Search hits for `market_beta`, `crypto_beta`, `beta_neutral`, `residualize`, and related terms are VaR stress exposure, tests, docs, or pair-specific research scripts. They are not a generic BTC/market residual alpha validator.

Consequence:

- A candidate can look good because it is long/short crypto beta or regime beta.
- Existing PSR/DSR/PBO can still validate a beta exposure if the market window favored it.

Required P0:

- Implement a point-in-time residualizer over BTC/market returns and, where relevant, sector/cluster returns.
- Gate candidates on raw edge and residual edge separately.
- Fail if raw edge is positive but residual edge is not.
- Add block bootstrap/permutation checks over residual returns.

### 2. DSR/PBO/CPCV exist, but they are fragmented and not uniformly blocking

Evidence:

- `program_code/learning_engine/dsr_gate.py:1-49` explicitly says pure math/advisory output and excludes call-site wiring/audit/PBO/cost in that scope.
- LG-5 R4 in `governance_hub_live_candidate_review.py:995-1015` skips DSR-style deflation when `K < R4_TRIGGER_PENDING_COUNT`.
- That skip is informational, not blocking: `governance_hub_live_candidate_review.py:1376-1404`, and approve can still include only `r4_skipped_insufficient_pool` at `:1453-1467`.
- CPCV exists in the ML validation area, and the selection-bias manifest validator has stricter requirements, but those are not the same as universal proposal-time strategy gates.

Consequence:

- The repo has serious statistical tooling, but the protection is unevenly wired across candidate creation, research scripts, replay, ML promotion, and live candidate review.

Required P1:

- Define one candidate evidence manifest consumed by all proposal/promotion paths.
- Make DSR/PBO/CPCV/purge/embargo evidence either mandatory or explicitly mark the output "research only".

### 3. Known regime lookahead remains in multiday trend diagnostic

Evidence:

- `helper_scripts/research/multiday_trend_diagnostic/data_loader.py:296-303` computes high-vol tercile from all finite vols, which includes future vol distribution.
- The fixed pattern exists elsewhere: `helper_scripts/research/funding_tilt_diagnostic/data_loader.py:379-382` documents the leak, and `:407-420` uses expanding/prior-365 vols.

Consequence:

- Any multiday trend conclusion using that regime split remains suspect until migrated.

Required P0/P1:

- Port the funding-tilt expanding/prior-365 logic into the multiday trend diagnostic.
- Add a small regression test that fails on full-sample quantile usage.

### 4. Strategy breadth is real in code, but active/wired breadth is narrower

Evidence:

- Registry constructs eight strategies in `rust/openclaw_engine/src/strategies/registry.rs:57-321`, including `funding_short_v2` and `liquidation_cascade_fade`.
- Demo TOML keeps `funding_short_v2` inactive: `settings/strategy_params_demo.toml:213-224`.
- Demo TOML keeps `liquidation_cascade_fade` inactive: `settings/strategy_params_demo.toml:233-243`.
- Risk config also disables both per-strategy blocks: `settings/risk_control_rules/risk_config_demo.toml:100-121`.

Consequence:

- The real live/demo behavior is still dominated by the older strategy set unless operator/governance explicitly activates newer candidates.
- Do not infer deployable breadth from registry existence.

### 5. Cost-defeat and postmortem loops are partial

Evidence:

- `settings/risk_control_rules/risk_config_demo.toml:446-452` keeps `cost_edge.enabled=false`.
- Existing strategist-weight logic adjusts by confidence/static regime patterns more than realized, regime-tagged, post-fee failure attribution.

Consequence:

- We have cost-aware gates and learning rows, but not a fully closed loop where realized cost defeat automatically changes strategy weights, candidate budgets, or proposal priors.

Required P2:

- Attach every postmortem to regime, strategy, data source, cost bucket, and residual beta result.
- Feed those postmortems into proposal scheduling and strategy weights only after attribution-chain checks pass.

## Priority Decision

P0:

1. Build `beta_residualizer` and proposal-time/live-candidate `R_beta` gate.
2. Migrate the multiday trend regime vol-tercile leak fix.
3. Add a residual-edge report to every new alpha candidate summary.
4. Reserve a hidden OOS protocol for candidate families so iterative agents cannot repeatedly tune on the final test window.

P1:

1. Create a unified candidate evidence manifest with PIT alignment, purge/embargo, DSR/PBO/CPCV, residual beta, cost, and sample-power fields.
2. Run beta-neutral cross-sectional exploration using existing AEG/FND data before starting a broad DSL/evolution system.
3. Add proposal-time semantic/code alignment and complexity checks inspired by AlphaAgent.
4. Change promotion/recommendation consumers so missing evidence-lineage schema downgrades outputs to `research_only` / `pending_schema`.

P2:

1. Auto-mint Bybit `orderLinkId` in Rust and Python when caller omits it.
2. Turn signal postmortems into realized post-fee/regime-tagged feedback for weights and candidate scheduling.
3. Add a cost-defeat classifier that separates "edge absent" from "edge present but eaten by fee/slippage/fill failure".
4. Add QuantaAlpha-style AST duplicate/complexity checks after the `SignalSpec` manifest exists.

P3:

1. Only after residual alpha evidence exists, consider QuantaAlpha-style DSL/evolution and trajectory memory.

## Bottom Line

The external projects are strongest as upstream research-process examples. They are not proof that agentic factor mining survives our actual Bybit crypto execution environment. The most valuable thing to copy is disciplined candidate structure, semantic/static checks, trajectory memory, and postmortem loops.

The biggest real TradeBot gap is simpler and more important: we need a reusable BTC/market residual alpha gate before investing in broader factor evolution. Without it, better automation mostly makes us mine beta faster.
