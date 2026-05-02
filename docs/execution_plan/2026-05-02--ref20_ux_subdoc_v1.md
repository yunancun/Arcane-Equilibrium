# REF-20 Paper Replay Lab UX Subdoc V1

**日期：** 2026-05-02
**狀態：** Dedicated UX contract for REF-20 P1 entry
**Owner：** PM / A3
**上游文件：** `2026-05-02--ref20_paper_replay_lab_dev_plan_v2_1_round3.md`

---

## 1. UX Decision

Paper Tab is upgraded in place into Paper Replay Lab.

The first screen is the working tool, not a landing page. The user should be able to inspect the current paper session, configure a replay, compare baseline vs candidate, and understand why a result is or is not actionable.

This subdoc is mandatory before P1. A PR section is not an acceptable substitute because P1 UI work changes operator trust boundaries.

---

## 2. Information Architecture

Paper Replay Lab has four top-level sub-tabs:

| Sub-tab | Purpose | Actionability |
|---|---|---|
| Session | current paper session status and historical paper state | read-only after P1 |
| Replay | create and monitor non-actionable replay runs | P2+ only |
| Compare | compare baseline vs candidate reports | non-actionable until P3/P4 gates |
| Handoff | bounded demo candidate review | disabled until P6 |

Learning remains the durable learning cockpit. It may show replay evidence inbox and MLDE/Dream producer health, but it does not run replay.

Agents Monitor is a later extraction target. Until P5, any existing 5-Agent panel must remain read-only and must not be expanded inside Paper Replay Lab.

---

## 3. Session Sub-Tab

Session displays:

- current paper session mode
- strategy/risk config hash when available
- open simulated paper positions if the legacy paper engine still exposes them
- recent paper orders/fills as read-only rows
- paper engine health
- link or indicator to Replay baseline snapshot source

Session must not expose manual submit/cancel controls after P1.

If the operator later requires manual paper order entry for debugging, it must be a separate legacy-only dev surface. It cannot share the Replay Lab workflow and cannot look like a supported replay action.

---

## 4. Replay Sub-Tab

Replay run form minimum fields:

| Field | Control |
|---|---|
| symbol set | multi-select or preset menu |
| timeframe | segmented control |
| data tier | segmented control with tier badge |
| runtime environment | readonly badge |
| baseline config | readonly snapshot picker |
| candidate config | explicit patch/config snapshot picker |
| market data window | date/time range |
| fee model | maker/taker selector or readonly model badge |
| execution model | readonly `none` in P2 |
| output policy | readonly, handoff disabled before P6 |

Replay status panel:

- run id / experiment id
- manifest hash
- git sha
- engine binary sha or Mac NULL notice
- started / elapsed / status
- current phase
- failure reason if failed
- artifact links rendered as safe text, never arbitrary HTML

P2 Replay must visually communicate `execution_confidence=none`. A user should not be able to mistake P2 for a realistic backtest.

---

## 5. Compare Sub-Tab

Compare displays baseline vs candidate with at least these metrics:

1. net bps after fees
2. gross bps
3. fee bps
4. q10 / q50 / q90 outcome bands
5. 95% CI when available
6. max drawdown
7. trade count
8. reject rate
9. source mix
10. data tier
11. execution confidence
12. calibration freshness

Viewport requirement:

- Desktop: metrics table plus compact chart can fit without horizontal scrolling at normal operator console width.
- Mobile/narrow window: metrics collapse into grouped sections; no text may overlap badges, buttons, or tables.
- Compare never hides data tier or execution confidence below the fold when a verdict is shown.

Verdict labels:

- `reject`
- `defer_data`
- `defer_calibration`
- `research_only`
- `demo_candidate` only after P6 gates

There is no `live_approved` replay verdict.

---

## 6. Handoff Sub-Tab

Handoff is disabled until P6.

When enabled, it requires:

- typed confirmation
- idempotency key
- manifest hash
- baseline delta
- data tier
- execution confidence
- trace id
- replay experiment id
- PM/operator identity

Disabled Handoff state must state the blocking gate: P2 no execution confidence, P3 calibration incomplete, P4 advisory not verified, or P6 handoff disabled.

No hidden button, fake active CTA, or optimistic success copy is allowed.

---

## 7. Mode Badges

Every visible replay result must show four badges:

| Badge | Values |
|---|---|
| run mode | paper_session / replay_smoke / calibrated_replay / advisory / handoff |
| data tier | S0 / S1 / S2 / S3 / S4 |
| execution confidence | none / limited / calibrated |
| runtime environment | linux_trade_core / mac_dev_smoke_test_only |

Rules:

1. `execution_confidence=none` must be visually non-actionable.
2. `mac_dev_smoke_test_only` must show dry-run status and cannot show handoff controls.
3. S2/S3 results cannot be framed as production evidence.
4. A verdict must never appear without all four badges in the same viewport context.

---

## 8. Disabled State Contract

Disabled controls must explain the exact missing gate.

Allowed examples:

- `P2 backend pending`
- `Requires Linux replay rerun`
- `Execution calibration unavailable`
- `Insufficient sample: n < 30`
- `Handoff disabled until P6`
- `Manifest signature missing`

Forbidden:

- fake active submit buttons
- hidden no-op clicks
- generic `Coming soon` without phase/gate
- success styling on non-actionable results
- replay controls that resemble live trading controls

---

## 9. Terminology

| English | 中文 UI 建議 | Meaning |
|---|---|---|
| Replay | 快速回放 | accelerated historical run |
| Backtest | 回測 | only for calibrated P3+ reports |
| Smoke Replay | 煙霧回放 | P2 non-actionable test |
| Execution Confidence | 執行可信度 | none / limited / calibrated |
| Data Tier | 資料層級 | S0-S4 evidence source |
| Baseline | 基準配置 | current/demo snapshot under comparison |
| Candidate | 候選配置 | config/strategy patch under test |
| Handoff | 候選交接 | bounded demo candidate path |
| Advisory | 建議證據 | MLDE/Dream recommendation, not mutation |

UI copy should avoid implying that P2 is a real backtest. Use `Smoke Replay` / `快速回放` for P2 and reserve `Backtest` / `回測` for calibrated P3+ reports.

---

## 10. Accessibility and Layout

1. Buttons use icons where the action is conventional and text where the risk is high.
2. Destructive or handoff actions require text labels and typed confirmation.
3. Tables must keep IDs copyable.
4. Manifest hash and experiment id may truncate visually but must expose full value on click/copy.
5. Badges must not rely only on color.
6. Long strategy names, symbols, hashes, and failure reasons must wrap or truncate without layout shift.
7. No card should contain another card.
8. Replay charts are diagnostic; they cannot obscure verdict badges.

---

## 11. P1 Acceptance

P1 may start only when:

1. Paper Replay Lab IA is accepted.
2. Session / Replay / Compare / Handoff shell behavior is specified.
3. manual submit/cancel controls are removed from Paper Replay Lab surface or isolated in a separately approved legacy-only dev surface.
4. disabled states use phase/gate language.
5. all replay result mock states include four mode badges.
6. `execution_confidence=none` state is visually non-actionable.
7. Handoff is disabled and cannot be clicked before P6.

P1 completion requires a UI regression check proving `paper_replay_lab_no_order_submit`.
