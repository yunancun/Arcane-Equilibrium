# FA 功能覆蓋審計 — IBKR Stock/ETF Paper + Shadow 計劃

日期：2026-06-29
角色：FA(default)
任務：功能覆蓋與產品需求審計，不改 runtime / code
審計對象：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`

## Verdict

**DONE_WITH_CONCERNS / Conditional**

計劃方向正確：它明確把 `stock_etf_cash` 定位為 paper/shadow research lane，保留 Bybit 主線，並多次禁止 IBKR live、margin、short、options、CFD、資金劃轉與非 Bybit live。

但它目前**只足夠支撐 Phase 0 ADR/spec 評審**，不夠支撐 Phase 1+ implementation，也不夠支撐 6-8 週 validation clock 開始。主要原因是 IBKR API/session 假設、paper order lifecycle state machine、evidence clock 合格條件、flag/secret/operator decision matrix 仍缺少可測試的功能契約。

Finding counts: **CRITICAL 3 / HIGH 7 / MEDIUM 3 / LOW 1**.

## Sources Reviewed

- `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `TODO.md`, `docs/agents/context-loading.md`
- `.codex/agents/PM.md`, `.codex/agents/FA.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.claude/agents/FA.md`, `docs/CCAgentWorkSpace/FA/profile.md`, `docs/CCAgentWorkSpace/FA/memory.md`, `.claude/skills/spec-compliance/SKILL.md`
- `CONTEXT.md` relevant glossary sections: Decision Lease, Authorization, Control Plane, SoT/Forbidden Writer, Agent Decision Spine, risk/evidence/product-family taxonomy
- ADRs: `0001-rust-as-trading-authority`, `0006-bybit-only-exchange`, `0008-decision-lease-state-machine`, `0033-adr-0006-bybit-binance-amendment`, `0040-multi-venue-gate-spec`
- IBKR official docs checked for API assumptions:
  - TWS API docs: https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
  - Client Portal Web API docs: https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/
  - Web API trading / staging: https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/ and https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-staging/
  - TWS order lifecycle docs: https://interactivebrokers.github.io/tws-api/order_submission.html and https://interactivebrokers.github.io/tws-api/open_orders.html
  - Market data docs: https://interactivebrokers.github.io/tws-api/market_data_type.html and https://www.interactivebrokers.com/campus/ibkr-api-page/market-data-subscriptions/
  - Paper account docs: https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/

## Coverage Matrix

| Surface | Current coverage | FA verdict |
|---|---|---|
| GUI lane selector | Direction present: login selector, lane badge, all tabs carry `asset_lane`. | Partial. Needs query/auth/cache isolation and disabled-lane negative tests. |
| Stock/ETF-specific views | Required views and major fields listed. | Partial. Needs operator workflow states, stale/no-data states, and view-level acceptance. |
| IBKR paper/demo API assumptions | Only says read-only, paper connector, healthcheck, order/fill import. | Insufficient. API/runtime/session model is not defined. |
| Order lifecycle | Mentions normalized intent/state and cancel/replace reservation. | Insufficient. No canonical state machine or broker-id reconciliation contract. |
| Evidence collection | 6-8 week window and 5-day preconditions exist. | Partial. Clock eligibility/reset/completeness rules are missing. |
| Scorecard | Metric list exists. | Partial. Formula, benchmark, confidence, FX/corporate-action and regime rules missing. |
| Settings / feature flags | Initial flags and config files listed. | Partial. Needs precedence, authority boundaries, kill-switch and test matrix. |
| Secrets | External IBKR slot paths listed. | Partial. Needs credential/session-token/redaction/rotation/fingerprint requirements. |
| Operator decisions | Five pre-work decisions listed. | Partial. Several blocking product/operator choices missing. |
| CFD / margin / live exclusion | Strong prose boundary. | Directionally good, but not yet machine-checkable. |

## Findings

### F-01 — CRITICAL — Phase 0 unlock can be misread as informal approval instead of a formal ADR/AMD gate

Evidence:
- Plan lines 22-24 correctly say a new ADR/AMD must amend the current `Bybit-only execution` boundary before formal work.
- Plan lines 395-409 define Phase 0, but acceptance line 407 says "ADR accepted 或 operator 明確批准".
- ADR-0006 remains accepted and says execution/connectors/policy work is Bybit-only; ADR-0040 only provides a future venue-aware gate pattern, not IBKR approval.

Why this blocks:
- "Operator explicitly approved" is not precise enough for a product-boundary change that introduces a non-Bybit broker surface. Without a formal accepted ADR/AMD artifact, Phase 1+ code can violate the current repo boundary while still claiming it followed the plan.

Required requirement:
- Before any Phase 1 implementation, require a merged/accepted ADR or AMD that explicitly names `stock_etf_cash`, IBKR read-only, IBKR paper, forbidden IBKR live, forbidden transfer, forbidden margin/short/CFD/options, and the permitted API surfaces.
- Remove or narrow the informal "operator explicitly approved" path to "operator approval recorded in the ADR/AMD acceptance trail".

### F-02 — CRITICAL — IBKR API/runtime/session assumptions are undefined

Evidence:
- Plan lines 429-446 cover "IBKR read-only + paper connector" only at feature-list level.
- Plan lines 155-159 say `ibkr_paper_routes.py` may expose read-only healthcheck/account/fill status but do not identify the IBKR API family or runtime dependency.
- Official IBKR docs expose materially different integration surfaces: TWS API / IB Gateway local socket, Client Portal/Web API gateway, paper credentials, brokerage sessions, and market data subscription/delayed-data behavior.

Why this blocks:
- Engineering cannot implement or validate "IBKR paper/demo" without knowing whether the connector targets TWS API, IB Gateway, Client Portal Web API, or another IBKR interface.
- Validation differs by API: local Java gateway availability, single brokerage-session rules, paper username/password, account selection, market data subscription vs delayed data, websocket vs callback semantics, and authentication renewal all affect healthcheck, evidence collection, and order lifecycle.

Required requirement:
- Phase 0 ADR/spec must choose the first IBKR API baseline and define: runtime process owner, host placement, authentication/session lifecycle, paper credential source, account selection, market-data subscription/delayed-data policy, rate limits, reconnect/backoff, maintenance windows, and explicit "demo" terminology.
- If both TWS API and Client Portal/Web API remain candidates, Phase 1 must be split into a no-order spike with acceptance criteria before any connector implementation.

### F-03 — CRITICAL — Paper order lifecycle has no canonical state machine or reconciliation contract

Evidence:
- Plan lines 126-130 mention `broker_order_lifecycle`, normalized intent/state, cancel/replace reservation, and paper fill import.
- Plan lines 435-446 require paper orders/fills with broker ids and live fail-closed.
- CONTEXT requires Decision Lease, Guardian, Rust IntentProcessor, audit lineage, and Reconciliation to govern order effects.

Why this blocks:
- "Paper order lifecycle rehearsal" cannot be validated without exact broker-to-internal state mapping.
- IBKR exposes order callbacks/status, open orders, executions, broker order ids, and account-specific behavior. Missing mapping creates ambiguous handling for partial fills, duplicate callbacks, cancelled-after-fill, rejected/inactive states, replace flows, manual TWS changes, restart recovery, and stale/unknown broker state.

Required requirement:
- Define an `ibkr_paper_order_lifecycle_v1` state machine before Phase 2: internal states, allowed transitions, terminal states, retry/cancel/replace semantics, idempotency keys, order ids (`client_id`, local id, broker id / perm id where applicable), fill/execution id handling, restart recovery, stale state policy, and `STATE_UNKNOWN -> MANUAL_REVIEW_REQUIRED`.
- Require fixture tests and one paper-account rehearsal manifest that proves reconstructability without creating live authority.

### F-04 — HIGH — GUI lane selector lacks enforceable query/permission isolation

Evidence:
- Plan lines 52-59 define the three lanes.
- Plan lines 258-259 require a lane badge and `asset_lane` on all tab queries.
- Plan lines 300-311 list existing-tab splits.

Gap:
- No requirement covers default-lane persistence, URL/deep-link behavior, server-side `asset_lane` enforcement, route-level validation, cache partitioning, stale active-lane state, CSRF/auth preservation, or disabled-lane behavior for `cfd_margin` and stock live surfaces.

Required requirement:
- Add GUI acceptance tests proving every data endpoint either requires or derives `asset_lane`, rejects invalid/missing lane where unsafe, never falls back from stock to crypto data, never uses GUI lane selection as trading authority, and preserves existing crypto tab behavior.

### F-05 — HIGH — Stock/ETF views list fields but not operator-grade states or workflows

Evidence:
- Plan lines 261-297 list stock overview/universe/paper/shadow/risk/evidence fields.

Gap:
- Missing view states: market closed, delayed data, no market data subscription, connector down, paper account unavailable, stale scorecard, no positions, reconciliation unknown, paper-vs-shadow divergence, corporate action pending, instrument blocked, and live-disabled reason.
- Missing operator workflows: what the operator can inspect, approve, freeze, export, or escalate from each view.

Required requirement:
- Each stock tab needs an acceptance table: inputs, empty/loading/stale/error states, allowed operator actions, blocked actions, audit events emitted, and evidence links shown.

### F-06 — HIGH — Evidence collection clock is underdefined

Evidence:
- Plan lines 315-322 define preconditions for the 6-8 week window.
- Plan line 525 says evidence starts only after Phase 3/4 stable.

Gap:
- "5 trading days no gap" and "scorecard daily output" are not machine-checkable yet. Missing: trading calendar/timezone, early-close/holiday handling, daily cutoff, completeness threshold, allowable outage, reset/pause rules, collector version freeze, universe-change reset, cost-model-change reset, source-data freshness ladder, and manifest signature.

Required requirement:
- Define `stock_etf_evidence_clock_v1` with start/pause/reset rules, trading-day calendar, data-completeness threshold, gap taxonomy, daily manifest schema, and the exact condition under which a day counts toward the 6-8 week window.

### F-07 — HIGH — Scorecard metrics lack formulas and proof-quality thresholds

Evidence:
- Plan lines 359-385 list daily metrics and promotion-like requirements.

Gap:
- The plan does not define formulas for net expectancy, benchmark excess return, conservative fill penalty sensitivity, paper-vs-shadow divergence, FX drag, tax/FTT placeholders, turnover, drawdown, or exposure time.
- It does not define benchmark choice per instrument/strategy, base currency, corporate-action adjusted prices, dividends, survivorship handling, confidence intervals, walk-forward/bootstrap parameters, or whether 100+ samples apply per strategy, per universe, per lane, or in aggregate.

Required requirement:
- Add a scorecard schema/formula appendix with versioned formulas, benchmark assignment, confidence statistics, regime labels, corporate-action/dividend treatment, FX conversion source, and minimum sample interpretation.

### F-08 — HIGH — Feature flag semantics need a precedence and invariant matrix

Evidence:
- Plan lines 217-226 list flags, including `OPENCLAW_IBKR_PAPER_ENABLED`, `OPENCLAW_IBKR_LIVE_ENABLED`, and `OPENCLAW_STOCK_ETF_SHADOW_ONLY`.
- CONTEXT lines 153-158 define feature flags as non-authorization.

Gap:
- Missing precedence rules: e.g. what happens if `OPENCLAW_IBKR_PAPER_ENABLED=1` and `OPENCLAW_STOCK_ETF_SHADOW_ONLY=1`; whether read-only can run when lane UI is disabled; how live flag fails closed in compile/runtime/tests; how flags propagate through service restart scripts; what kill-switch overrides all lane flags.

Required requirement:
- Add a flag matrix with every meaningful combination, expected allowed actions, expected UI state, expected route/API response, expected Rust authority result, and negative tests. Explicitly state that no flag grants authorization or order authority.

### F-09 — HIGH — Secret handling is only path-level, not functionally complete

Evidence:
- Plan lines 228-246 define external IBKR secret slot paths and future authorization fields.
- Plan lines 438-446 mention redaction and "secrets not in argv/log".

Gap:
- Missing credential type and lifecycle: paper username/password or token, gateway session cookies, OAuth/session renewals if applicable, market-data entitlements, file mode, owner, rotation, revocation, fingerprinting, redaction allowlist, and live-slot nonexistence assertion.

Required requirement:
- Add an E3-ready secret contract: credential classes, storage permissions, no-argv/no-log rules, session-token location, fingerprint schema, rotation/revocation workflow, healthcheck redaction fixtures, and a test proving `$OPENCLAW_SECRETS_DIR/external/ibkr/live/` is absent or empty before stock lane can run.

### F-10 — HIGH — CFD/margin/live exclusions are strong prose but not yet machine-checkable

Evidence:
- Plan lines 20, 44-48, 57-58, 108-110, 287-290, 331-339, and 531-535 repeatedly exclude live, margin, short, options, CFD, and transfer.

Gap:
- The plan lacks concrete negative requirements for broker account type, account permissions, instrument classification, order side, short-sale fields, margin loan/leverage, fractional constraints, leveraged/inverse ETF handling, options chains, CFD symbols, FX conversion trades, and transfer endpoints.

Required requirement:
- Add fail-closed invariants and tests: only `InstrumentKind::{Stock, Etf}` in `stock_etf_cash`; account must be verified cash-only or treated as paper-cash-only envelope; no short-open; no margin attributes; no options/CFD/order-transfer endpoints; disabled `cfd_margin` lane must have no API write path and no secret slot.

### F-11 — MEDIUM — Operator decision list is incomplete

Evidence:
- Plan lines 549-557 list five operator decisions.

Gap:
- Missing decisions that change functional scope: chosen IBKR API surface, paper account jurisdiction/account id, market data subscriptions vs delayed mode, universe owner, benchmark owner, base currency, acceptable data cost, initial risk/loss caps, shadow-only lift criteria, whether any paper orders are allowed in Phase 2, weekly review format, and whether eToro/Saxo challengers require separate ADRs.

Required requirement:
- Expand Phase 0 operator decision checklist so PM can collect all decisions before PA/E1 implementation planning.

### F-12 — MEDIUM — Existing Bybit behavior isolation needs explicit regression acceptance

Evidence:
- Plan line 56 says crypto governance remains unchanged.
- Plan lines 300-311 split existing tabs by data source.

Gap:
- No acceptance criteria prove the existing Bybit Demo/LiveDemo/Live surfaces continue to route through the same Rust authority, risk config, Decision Lease display, and scorecard semantics after `asset_lane` is introduced.
- Instrument identity reuse is risky because CONTEXT currently defines `Symbol` as a Bybit instrument; stock symbols need a separate identity contract to avoid mixed joins and display collisions.

Required requirement:
- Add "crypto regression unchanged" acceptance: existing tab smoke tests, route contract tests, no changed Bybit default lane, and explicit stock `EquityInstrumentId` usage wherever `Symbol` would be ambiguous.

### F-13 — MEDIUM — Shadow fill model is not deterministic enough to validate

Evidence:
- Plan lines 131-134 define `stock_shadow_engine`.
- Plan lines 282-286 and 454-459 require synthetic fills and conservative fill model.

Gap:
- Missing deterministic fill rules: quote/bar source, latency assumption, spread crossing, auction handling, partial fill model, stale quote rejection, volume participation cap, corporate-action adjustment, and how paper-vs-shadow divergence is computed.

Required requirement:
- Add `stock_shadow_fill_model_v1` with formulas and fixture cases before Phase 3.

### F-14 — LOW — Engineering estimate likely undercounts spec/security/API spike time

Evidence:
- Plan lines 506-523 estimate 4-5 weeks median engineering pre-work.

Concern:
- The estimate may be reasonable after API choice and ADR acceptance, but the current plan bundles API selection, gateway/runtime operation, security, evidence schema, GUI split, and order lifecycle into the same pre-work window without an explicit discovery spike.

Required requirement:
- Treat API/runtime selection as a separate Phase 0/1 spike and re-estimate after F-02/F-03 are resolved.

## Blocking Requirements Before Phase 1+

1. Accepted ADR/AMD for `stock_etf_cash` paper/shadow scope with no IBKR live permission.
2. Chosen IBKR API baseline and runtime/session/market-data assumptions.
3. Canonical paper order lifecycle and reconciliation state machine.
4. Feature flag and secret invariant matrix, including live-slot absence and flag precedence.
5. GUI lane/query isolation acceptance tests.
6. Evidence clock schema and daily manifest contract.
7. Scorecard formula and benchmark/currency/corporate-action treatment.
8. Machine-checkable no-CFD/no-margin/no-live/no-short/no-transfer invariants.
9. Expanded operator decision checklist.

## Final Functional Assessment

Proceed with **Phase 0 only**. Do not start Phase 1 implementation, IBKR API calls, secret creation, connector scaffolding, DB migrations, GUI lane rollout, or paper order rehearsal until the blocking requirements above are added to the ADR/spec and accepted.

The plan is directionally sound and conservative, but implementation-readiness is **not yet achieved**.
