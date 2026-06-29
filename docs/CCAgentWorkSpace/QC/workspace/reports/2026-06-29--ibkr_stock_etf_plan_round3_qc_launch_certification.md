STATUS: DONE
CERTIFICATION: CERTIFIABLE_IF_GATES_PASS, SCOPE=paper_shadow_only, FINDINGS=0(C:0/H:0/M:0/L:0)

# QC Round 3 Launch-Certification Closure Audit - IBKR Stock/ETF Paper + Shadow

Date: 2026-06-29
Role: QC(default)
Scope owner: profitability/evidence wording launch certification
Task shape: third-round release-certification closure audit, report-only
Boundary observed: no code/runtime/TODO/IBKR/Bybit/Linux/PG/services/secrets/network actions.

## Direct Decision

Yes, conditionally.

If every hardened evidence-clock, pre-registration, sample-size, benchmark,
cost-wall, paper-vs-shadow divergence, ADR-0047 regime/breadth/freshness, and
release-packet gate passes exactly as written, QC can certify paper/shadow
evidence launch completeness for `stock_etf_cash`.

This is not a present-tense launch approval and not a profitability
certification. It means the hardened plan has converted the known QC
profitability/evidence omissions into machine-checkable gates; under the
operator's narrowed interpretation of launch as paper/shadow evidence
collection plus preliminary feasibility screening, QC sees no remaining
minimum missing QC gate.

Final PM-facing decision:

`PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS`

## Certified Scope

QC certification covers only:

- Asset lane: `stock_etf_cash`.
- Evidence mode: IBKR read-only / broker-paper rehearsal / synthetic shadow.
- Purpose: evidence collection, engineering shakedown, and preliminary
  after-cost feasibility screening.
- Evidence outputs: pre-registered hypothesis packets, daily scorecards,
  conservative cost/fill reconstructions, benchmark-relative after-cost
  results, paper-vs-shadow divergence checks, ADR-0047 regime/breadth/freshness
  labels, independent-sample accounting, and weekly PM/QC/MIT review.
- Verdict language: `engineering_ready`, `research_promising`,
  `profitability_feasible`, `insufficient_evidence`,
  `execution_model_invalid`, or `kill`, where `profitability_feasible` is only
  a paper/shadow feasibility label and never live authority.

The evidence window remains a screening lane. Low-frequency or underpowered
positive results must stay `research_promising` or `insufficient_evidence`.
Single-regime positives must be labeled `regime-bet / learning-only` where
applicable.

## Explicit Exclusions

This QC certification excludes:

- IBKR live and IBKR tiny-live.
- Any non-Bybit live trading authority.
- Margin, short, options, CFD, leveraged/inverse expansion, transfer,
  withdrawal, or account-management write paths.
- Profitability guarantee, durable-alpha proof, production/live readiness, or
  automatic promotion from paper/shadow to tiny-live/live.
- Legacy Paper promotion-lane revival.
- Any claim that IBKR paper fills are live execution proof.
- Any relaxation of Rust authority, Decision Lease, Guardian/risk, auditability,
  reconstructability, or existing live gates.

## Required QC Gates

The conditional certification depends on all of these passing with immutable
artifacts and hashes:

1. `stock_etf_evidence_clock_v1`: deterministic PASS / FAIL / QUARANTINED day
   checker, with frozen universe, benchmark, cost model, strategy hypothesis,
   corporate-action, FX, fee/tax, fill-model, and divergence-threshold hashes.
2. Pre-registration: each hypothesis has alpha source, holding horizon,
   turnover target, benchmark, parameter grid, K count, primary metric,
   rejection rule, and verdict mapping before the clock starts.
3. Sample-size/power: `n_independent_min`, cluster/block unit, sector/event/week
   grouping, minimum calendar span, effect size or MDE, purge/embargo if
   applicable, and DSR/PSR or equivalent deflation universe are fixed before
   scoring.
4. Benchmark: matched benchmark and controls are frozen with total-return vs
   price-return, currency, calendar, rebalance/source vendor, beta/tracking
   error, and benchmark-excess formula defined.
5. Cost wall: base/conservative/punitive cost components are frozen, including
   commission, spread, slippage/adverse selection, FX, regulatory/exchange fees,
   tax/FTT or fail-closed conservative placeholders. Unknown cost cannot default
   to zero.
6. Cost veto: conservative or punitive costs cannot flip net expectancy or
   benchmark excess negative. The cost-edge ratio veto must be pre-registered.
7. Paper-vs-shadow divergence: fill-rate, timing, price/slippage, partial/unfill,
   commission, FX/tax, and lifecycle divergence thresholds produce quarantine or
   `execution_model_invalid` / `insufficient_evidence`, not pooled favorable
   PnL.
8. ADR-0047 labels: regime, breadth, freshness, survivorship, execution realism,
   and statistical gates are non-null or explicitly blocking/downgrading.
9. Concentration veto: no result may be driven by a single symbol, sector, event,
   week, or regime without downgrade.
10. Scorecard reproducibility: scorecard is derived-only and regenerates from
    atomic facts, input hashes, cost/benchmark/fill-model versions, and DQ
    manifests.
11. `tiny_live_adr_eligibility_v1`: separate from scorecard; positive
    paper/shadow evidence can only open a future ADR discussion if all
    pre-registered evidence gates pass.
12. `stock_etf_release_packet_v1`: contains role reports, E2/E4/QA logs, command
    outputs, hashes, redaction fixtures, DQ manifests, GUI evidence screenshots
    if applicable, scorecard regeneration outputs, and disable/cleanup paths.

## Missing Gates

Under the stated hypothetical that every hardened gate passes exactly as
written, QC identifies no additional minimum missing QC gate.

Current-state caveat: the repo is not launch-certified today. The actual
artifacts, accepted Phase 0 packet, Phase 1-5 gate evidence, and final release
packet must exist and pass first. If any gate is absent, stale, prose-only, or
not reproducible from artifacts, QC certification collapses to
`NOT_CERTIFIABLE` until that gate is repaired.

## QC Launch Wording

QC-approved wording:

> The `stock_etf_cash` lane is paper/shadow evidence-launch certifiable if, and
> only if, every hardened evidence-clock, pre-registration, independent-sample,
> benchmark, cost-wall, paper-vs-shadow divergence, ADR-0047 regime/breadth/
> freshness, scorecard-regeneration, and release-packet gate passes with
> immutable artifacts. This permits IBKR read-only / broker-paper rehearsal /
> synthetic-shadow evidence collection and preliminary after-cost feasibility
> screening only. It does not assert profitability, durable alpha, tiny-live or
> live readiness, or permission for margin, short, options, CFD, transfer, or
> any non-Bybit live execution.

Forbidden wording:

- "Profitability is certified."
- "Durable alpha is proven."
- "The stock/ETF lane is live-ready."
- "Positive paper/shadow results can go tiny-live."
- "6-8 weeks proves the strategy works."
- "IBKR paper fills are live execution proof."
- "Scheduled work can fully go online" unless "fully" is explicitly restricted
  to the `stock_etf_cash` paper/shadow evidence lane after all gates pass.

## PM Wording

PM may use this exact wording:

> QC certifies the `stock_etf_cash` paper/shadow evidence launch as complete if,
> and only if, the accepted Phase 0 packet and every hardened Phase 1-5 evidence
> gate pass exactly as written. The certified scope is IBKR read-only /
> broker-paper rehearsal / synthetic-shadow evidence collection, conservative
> after-cost reconstruction, benchmark comparison, paper-vs-shadow divergence
> control, ADR-0047 labeling, and preliminary feasibility screening. This does
> not certify profitability, durable alpha, IBKR live or tiny-live, margin,
> short, options, CFD, transfer, or any automatic promotion beyond paper/shadow.

## Basis Reviewed

- `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `TODO.md`.
- `docs/agents/context-loading.md`.
- `docs/agents/profit-first-autonomy-loop.md`.
- `.codex/AGENT_DISPATCH_PROTOCOL.md`.
- `.codex/SUBAGENT_EXECUTION_RULES.md`.
- `.codex/agents/QC.md`, `.claude/agents/QC.md`, QC profile, QC memory.
- `docs/adr/0047-alpha-edge-regime-evidence-governance.md`.
- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`.
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_pm_integration.md`.
- Round-2 CC/FA/PA/E3/E5/QC/MIT/QA reports.
- Round-3 PA/CC/E3/FA/MIT/QA launch-certification reports.

## Final PM-Facing Decision

PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS
