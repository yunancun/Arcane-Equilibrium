# ADR 0027: AI Plan Mode — Time-Based Budgeting (Not Dollar Cycling)

Date: 2026-05-20
Status: Accepted-pending-commit

## Context

3rd reviewer audit 2026-05-20 proposed AI Plan Mode with three intensity
modes (Build / Observe / Low Activity) and dollar-based caps ($220-300 /
$100-150 / $40-120). The intent — prevent indefinite open-ended dev burn
on an unproven project — is correct. The dollar-cycling mechanism is
flawed because:

1. Claude Max ($200/mo) and ChatGPT Plus ($200/mo) are **monthly
   subscriptions without prorated cancel**. They cannot be cycled monthly
   without losing service.
2. Operator uses both subscriptions for **multiple parallel activities**
   (this project + other personal/professional work). Attributing
   $400/mo to this project is accounting fiction.
3. The "Low Activity Mode $40-120" implicitly requires canceling both
   subscriptions, which is unrealistic given cross-project utility.
4. **Real variable cost** is API spending ($10-30/mo when active) +
   hosting ($20-30/mo) + operator hours opportunity cost.

The right control variable is operator hours allocated to this project,
not subscription dollar spending.

## Decision

Plan Mode is a **time-budget discipline**, not a dollar-cycling
discipline. Subscriptions are treated as sunk cost; variable spending
(API + hosting) is bounded per mode; **operator weekly hours** is the
primary control.

### Mode Definitions

| Mode | Operator hr/wk | API spend cap/mo | Hosting | Trigger |
|---|---|---|---|---|
| **Build** | 20-30 hr | $30 | $30 | Active dev sprint (default for N+1-N+3 evidence sprint) |
| **Observe** | 5-10 hr | $10 | $30 | W8 PASS technical but waiting for live gates / demand maturity |
| **Low Activity** | 1-3 hr | $5 | $30 | Indefinite background; only weekly check-ins |
| **Deep Dev Exception** | up to 50 hr/wk | $50 | $30 | P0 incident / live gate clear / monetization sprint; operator manual approve |

### Transition Rules

```
Default for evidence sprint (N+1 to N+3):
  Mode = Build

W8 Joint Verdict (per v4.3 §5.1):
  PASS technical + PASS demand     → continue Build (W9-W12)
  PASS technical + FAIL demand     → switch to Observe Mode
  FAIL technical + PASS demand     → switch to Build Mode (pivot sprint)
  FAIL technical + FAIL demand
    + IP signal                    → switch to Build (IP closing sprint)
    + no IP signal                 → switch to Low Activity

W12 Hard Verdict:
  All-3-fail → KILL all streams; switch to Low Activity → sunset
  Partial pass → conditional Observe (per v4.3 §5.3)

Hard cap:
  Build Mode max 2 consecutive months without Deep Dev Exception
  → W8-end auto-cooldown to Observe unless operator explicit approve

W24 (6 months post-W12):
  Low Activity ≥ 4 consecutive months → operator forced revival/kill decision
```

### Subscription Accounting

Claude Max + ChatGPT Plus monthly subscriptions ($200 + $200 = $400/mo)
are **NOT attributed to this project budget**. They are operator general
dev tooling expense, shared across all activities. Cancellation requires
operator life-level decision, not project-mode decision.

This-project variable cost = API spending + hosting + operator hours
opportunity cost.

### API Spend Ledger

Existing `agent.ai_invocations` ledger logs all LLM calls. v4.3 enforces:

```sql
-- monthly API spend check
SELECT
    date_trunc('month', invocation_ts) AS month,
    SUM(cost_usd) AS total_cost_usd
FROM agent.ai_invocations
WHERE track IN ('direct_exploit', 'asds_factory', 'baseline')
  AND invocation_type NOT IN ('cowork_operator_assist', 'cowork_scheduled_task')
GROUP BY 1
ORDER BY 1 DESC;
```

(Cowork subscription invocations excluded per ADR-0024-lite — they're
zero-marginal-cost.)

If month-to-date spend > Mode cap → alert operator, switch to L1 Ollama
fallback for remaining invocations that month.

### Time Budget Ledger

Operator self-reports weekly hours in `TODO.md` weekly review section.
Honor system; no automated enforcement. If hours exceed mode cap
consistently, operator should formally switch mode or invoke Deep Dev
Exception.

### Deep Dev Exception

Reserved for:
- P0 incident response (e.g. v56 type)
- Live gate clearance (P0-LG-1/2/3 / P0-OPS-1..4 final landing)
- Monetization sprint (per W8 PIVOT branch)
- IP sale closing sprint (per W12 IP-only branch)

Operator explicit `[DEEP_DEV_EXCEPTION:reason]` tag in commit messages
during exception period. Auto-expire after 4 weeks unless renewed.

## Consequences

- Plan Mode controllable variable = operator hours, not subscriptions
- Subscription $400/mo accepted as sunk cost; not eligible for "savings"
  in mode transitions
- API spending cap actually enforceable via ledger query
- 2-month Build cap forces W8 verdict + Observe transition (prevents
  indefinite architecture-补丁 trap reviewer warned about)
- 4-month Low Activity cap forces W24 revival/kill decision
- Operator can flex up via Deep Dev Exception when justified

## Reviewer Audit Trail

3rd reviewer audit 2026-05-20 proposed dollar-cycling Plan Mode. Claude
push-back: subscription = sunk cost, dollar cycling not feasible. v4.3
adopts the **intent** (variable intensity by project state) but
**rejects the mechanism** (monthly dollar cycling) in favor of
operator-hours discipline. Operator approved this push-back.

## References

- v4.3 spec: `srv/2026-05-20--commercial-evidence-sprint-v4.3.md` §4, §11
- AMD-2026-05-20-04 (this ADR ratified inside)
- ADR-0024-lite Cowork subscription operator-assistant
- ADR-0020 Layer 2 manual+supervisor-only
