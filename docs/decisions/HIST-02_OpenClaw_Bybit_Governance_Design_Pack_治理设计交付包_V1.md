**OpenClaw / Bybit
Trading Agent Governance Design Pack
V1**

*Integrated governance architecture, boundary definitions, canonical semantics,
change-control rules, and incident-governance framework*

Version V1  •  2026-03-29

| **Package type** | Governance design pack |
|---|---|
| **Primary purpose** | Formal handoff, design review, implementation alignment, and governance reference |
| **Project scope** | OpenClaw governance-first trading agent using Bybit as main trading venue |
| **Status** | Top-level design package / V1 integrated bundle |

**Version:** V1

**Date:** 2026-03-29

**Purpose:** Consolidated governance design package for the OpenClaw / Bybit trading agent.


## 1. Package purpose

This package consolidates the current top-level governance architecture for the OpenClaw / Bybit trading agent into a single portable handoff document.

It is intended for:

new conversation handoff

design review

governance review

implementation alignment

future API / state-machine / runbook expansion

This package does **not** replace the individual source documents conceptually. Instead, it acts as the integrated master pack that captures the current agreed structure in one place.


## 2. Governing design thesis

The OpenClaw / Bybit trading agent is **not** defined as a fast auto-ordering bot and **not** as an unconstrained AI trader.

It is defined as:

*A long-horizon, progressively authorized, governance-first trading autonomous system operating inside strict risk boundaries, explicit authorization matrices, canonical state semantics, unified write paths, full auditability, and permanent human final oversight.*

Its core objective is not to win every market race. Its objective is to:

identify which situations are worth acting on

reject situations that should not be traded

measure success in **Net PnL**, not Gross PnL

survive abnormal markets and abnormal system states

degrade safely

request human review when needed

earn autonomy gradually through verified performance


## 3. Document architecture map

### Layer A — Constitution Layer

Defines the highest, non-negotiable principles.

Project Constitution / Root Principles

### Layer B — Boundary & Architecture Layer

Defines the structural bones of the system.

H0-H1~H5-I Formal Boundary Definition

Agent Capability Blueprint

Risk Governor Formal Boundary Definition

OMS / Execution Formal Boundary Definition

Control Plane / Operator Console Formal Boundary Definition

### Layer C — Canonical Engineering Truth Layer

Defines engineering truth, canonical objects, and ownership.

Field-Level & State-Level Specification

Truth Source & Ownership Matrix

### Layer D — Governance Operations Layer

Defines how the system changes and how it behaves under incidents.

Promotion / Change Control / Authorization Policy

Audit / Incident / Circuit Breaker Policy

### Layer E — Index Layer

Defines how the full package is read and maintained.

Documentation Architecture / Master Index


## 4. Precedence order

When two documents conflict, the order of authority is:

Project Constitution / Root Principles

Formal Boundary Definitions

Field-Level & State-Level Specification

Truth Source & Ownership Matrix

Promotion / Change Control / Authorization Policy

Audit / Incident / Circuit Breaker Policy

Agent Capability Blueprint

Implementation docs, API docs, GUI docs, test docs


## 5. Recommended reading orders

### For new handoff

Project Constitution / Root Principles

Documentation Architecture / Master Index

H0-H1~H5-I Formal Boundary Definition

Agent Capability Blueprint

Field-Level & State-Level Specification

Truth Source & Ownership Matrix

Promotion / Change Control / Authorization Policy

Audit / Incident / Circuit Breaker Policy

Risk Governor Formal Boundary Definition

OMS / Execution Formal Boundary Definition

Control Plane / Operator Console Formal Boundary Definition

### For implementers

Constitution

H0-H1~H5-I boundaries

Risk Governor boundary

OMS / Execution boundary

Control Plane boundary

Field / state specification

Ownership matrix

Change control / authorization

Incident / circuit breaker

Capability blueprint

### For governance / audit reviewers

Constitution

Ownership matrix

Change control / authorization

Incident / circuit breaker

Formal boundaries

Field / state specification

Capability blueprint


# PART I — PROJECT CONSTITUTION / ROOT PRINCIPLES

## 6. Project nature

This project is not a “model that can place orders.”

This project is not a “speed-first quant bot.”

This project is:

*A long-cycle evolving trading agent running inside strict risk boundaries, explicit authorization matrices, full audit trails, and human final governance.*

The agent may:

perceive markets

identify states

form trade hypotheses

generate controlled trade intent

act only through a unified risk and execution chain

learn through review and attribution

The agent may **not**:

cross survival boundaries

bypass risk governance

treat AI output as direct live trading command

self-widen permissions

self-modify live risk floors

self-rewrite code into production

## 7. Highest priority order

All design and implementation must obey this order:

Account survival

Risk governance

System health and state consistency

Auditability and explainability

Human final governance and takeover rights

True Net PnL

Autonomous capability growth

Strategy coverage and trading frequency

Gross PnL expansion

## 8. Root worldview

The system must assume that the market contains:

faster algorithmic players

stronger institutional players

better-capitalized and better-connected actors

heterogeneous market participants with different advantages

Therefore, the system must **not** assume broad speed advantage, infrastructure advantage, or informational advantage.

It should avoid pure speed competition and instead build edge from:

selection quality

state recognition

cost awareness

discipline

controlled degradation

survival

## 9. Definition of autonomy

Autonomy is not unlimited freedom.

Autonomy means:

*Inside explicitly authorized, verified, auditable, and revocable boundaries, the agent may decide whether to trade, what to trade, when to trade, how much risk to take, and when to exit.*

Autonomy must be:

granted by matrix, not globally

earned by verified performance

revocable upon failure or instability

permanently subordinate to hard risk boundaries and human final governance

## 10. Non-negotiable principles

Single legal write-entry principle

Read/write separation

AI output must not become direct live command

Strategy layer must never bypass risk layer

Survival judgment must precede profitability judgment

Failure defaults to contraction

Learning must not directly rewrite live

Every trade must remain explainable and traceable

## 11. Net PnL principle

All business evaluation must be based on **Net PnL**, not Gross PnL.

The system must recognize:

fees

slippage

funding / borrowing costs

AI decision cost

infrastructure and operational drag

But it must also distinguish:

direct trading cost

decision cost

operating allocation cost

## 12. System health priority principle

The system may only continue trading when it can reliably:

perceive

judge

execute

reconcile

audit

Health must outrank market opinion.

## 13. Human Operator status

The human Operator is not the person manually placing every trade.

But the Operator must remain the **final governance authority** with the right to:

review

veto

grant authorization

withdraw authorization

degrade

freeze

roll back

take over

classify incidents

approve recovery


# PART II — FORMAL BOUNDARY ARCHITECTURE

## 14. H0 / H1-H5 / I chain

### H0

**Local Deterministic Judgment & Gate Core**

Purpose:

first hard gate

local, deterministic, low-latency filtering

reject what should not even enter AI deliberation

H0 may:

check system / health / authorization / basic market structure

reject, defer, downgrade, or pass to H

H0 may not:

generate direct live orders

generate final Lease

rewrite live risk limits

rewrite authorization

### H1-H5

**AI Governance, Deliberation & Lease Drafting Layer**

Purpose:

interpret market context

challenge hypotheses

assess maintenance / attention / cost burden

review risk / authorization alignment

synthesize Lease drafts

H1-H5 may:

recommend reject

recommend defer

recommend passive-only

produce Lease draft

request manual review

H1-H5 may not:

write to exchange

become final risk approval

widen permissions

rewrite live truth objects

### I

**Decision Lease Control Plane**

Purpose:

register Lease

manage Lease lifecycle

handle active / revoked / frozen / expired states

bridge formally controlled Lease into downstream governance chain

I may not:

become strategy engine

directly write exchange

replace final risk approval

## 15. Risk Governor

Risk Governor is the final risk adjudication layer.

It can:

approve within envelope

reject

downsize

degrade

enforce reduce-only

freeze scope

trigger circuit breaker

gate recovery

It cannot:

generate market thesis

draft Lease

directly place orders

widen authorization on its own

Key principle:

*Risk Governor may always make the system more conservative than strategy, but never more permissive than the approved risk envelope.*

## 16. OMS / Execution

OMS / Execution is the unified execution coordination layer.

It can:

convert formally approved intent into execution behavior

manage execution state

handle submit / cancel / modify / partial-fill / retry / reconcile

maintain execution idempotency

emit execution audit events

It cannot:

decide that a trade is worth taking

widen risk boundaries

act without formal upstream objects

declare final order/fill/position truth

Key principle:

*Execution may become more conservative than upstream intent, but never more aggressive than approved risk boundaries.*

## 17. Control Plane / Operator Console

Control Plane / Operator Console is the human governance plane.

It can:

observe all formal state objects

trigger governance requests

approve changes

switch modes

freeze

stop

authorize

revoke

approve recovery

It cannot:

directly place exchange orders

rewrite canonical truth objects

replace Lease lifecycle truth

replace risk adjudication truth

bypass audit

Key principle:

*The Control Plane is a formal governance entry point, not a hidden backdoor.*


# PART III — CANONICAL ENGINEERING TRUTH

## 18. Core canonical objects

The governance pack standardizes at least the following canonical objects:

system_state

health_state

market_state

account_state

risk_state

authorization_state

candidate_context

h0_decision

deliberation_state

decision_lease

execution_state

position_state

order_state

fill_state

audit_event

learning_record

## 19. Field-level principles

one field = one formal meaning

raw / derived / display values must be separated

core enums should not be nullable

UTC is the machine truth timezone

costs, percentages, times, prices, and quantities require explicit units and precision

GUI labels must not be mistaken for machine truth

## 20. Ownership matrix principles

Every major object must have:

one source of truth

one primary writer

explicit readers

optional advisory writers

controlled human override path

explicit forbidden writers

High-level mapping:

system_state → Control Plane / Governance Core

health_state → Health / Monitoring Pipeline

market_state → Market State Engine

account_state → Account Sync + Reconciliation

risk_state → Risk Governor

authorization_state → Authorization Governance + Approval Path

h0_decision → H0 Core

deliberation_state → H1-H5 Pipeline

decision_lease → I Lease Control Plane

execution_state → Execution Coordinator / OMS

order_state / fill_state / position_state → Sync + Reconciliation

audit_event → Audit Pipeline

learning_record → Learning Plane


# PART IV — CAPABILITY BLUEPRINT

## 21. Formal capability definition

The agent should not be optimized to be “fastest everywhere.”

It should be optimized to become:

more selective

more state-aware

more cost-aware

more disciplined

more auditable

more survivable under uncertainty

## 22. Core capability layers

### Core capabilities

market perception

state understanding

trade thesis generation

probabilistic reasoning

multi-timeframe reasoning

selectivity

controlled execution decision

### Supporting capabilities

Net PnL awareness

self-observability

portfolio awareness

execution intelligence

auditability

context memory

### Governance capabilities

authorization self-discipline

fail-closed contraction

manual review request

learning and attribution

change suggestion without direct live rewrite

## 23. Strong-opponent environment reprioritization

Because stronger players exist, the system should **not** prioritize:

lowest-latency competition

pure microstructure sniping

shortest half-life alpha races

It **should** prioritize:

state identification

trade rejection ability

cost and maintenance awareness

degradation under uncertainty

controlled autonomy

explainable decision chains


# PART V — CHANGE, AUTHORIZATION, INCIDENT, AND RECOVERY GOVERNANCE

## 24. Change-control philosophy

Learning does not equal live effect.

Changes must be classified into levels:

L1 parameter-level

L2 strategy weight / selection-level

L3 guard / constraint-level

L4 authorization-level

L5 core behavior logic-level

L6 semantic / truth-source / governance-structure-level

Only the smallest, pre-approved, bounded changes may auto-activate, and only when:

they stay inside approved envelopes

they do not alter risk floors

they do not alter authorization

they do not alter truth-source or canonical semantics

they have passed replay + shadow

## 25. Authorization promotion

Authorization must be granted per unit, not globally.

At minimum, authorization binds to:

venue

symbol scope

strategy family

position size envelope

risk envelope

order-type scope

runtime stage

Authorization expansion requires:

stable verified behavior

no uncontrolled events

no audit-chain gaps

no unresolved state consistency issues

proven degradation under stress

acceptable Net PnL behavior

## 26. De-authorization

Authorization must be reduced or revoked when:

audit gaps appear

state consistency problems appear

risk limits are penetrated or nearly penetrated

abnormal behavior is not properly degraded

manual interventions are rising

repeated failure patterns appear

new authorization range behaves materially worse than expected

## 27. Incident taxonomy

Formal event severity levels:

notice

anomaly

near_miss

incident

critical_incident

## 28. Risk response modes

Formal response modes:

NORMAL

CAUTIOUS

REDUCED

DEFENSIVE

CIRCUIT_BREAKER

MANUAL_REVIEW

## 29. Incident response stages

detect

contain

stabilize

investigate

remediate

recover

## 30. Recovery principle

Recovery is never assumed.

Recovery must be:

formally approved

gradual

bounded

auditable

preceded by containment and sufficient root-cause understanding


# PART VI — MASTER INDEX SUMMARY

## 31. What each document controls

### Project Constitution / Root Principles

Controls highest principles and hard non-negotiables.

### H0-H1~H5-I Formal Boundary Definition

Controls system backbone roles and responsibility boundaries.

### Field-Level & State-Level Specification

Controls canonical state semantics and field definitions.

### Agent Capability Blueprint

Controls what the system should be able to do within governance constraints.

### Truth Source & Ownership Matrix

Controls who owns truth and who is allowed to write what.

### Promotion / Change Control / Authorization Policy

Controls how changes and autonomy expansions enter live.

### Audit / Incident / Circuit Breaker Policy

Controls how the system behaves when things go wrong.

### Risk Governor Formal Boundary Definition

Controls the final risk adjudication layer.

### OMS / Execution Formal Boundary Definition

Controls the unified execution coordination layer.

### Control Plane / Operator Console Formal Boundary Definition

Controls the human governance plane.

### Documentation Architecture / Master Index

Controls how the whole pack is read, maintained, and extended.


## 32. Recommended next expansion documents

The next natural formal documents to add are:

Risk Governor state-machine specification

OMS / Execution state-machine specification

Control Plane governance action schema

API canonical schema / contract package

Release / approval checklist pack

Incident review template pack

Recovery runbook

Symbol / strategy authorization matrix pack


## 33. Final governing sentence

*The OpenClaw / Bybit trading agent is governed as a constrained autonomous trading system whose primary obligation is not to trade often, not to trade fast, and not to appear intelligent, but to remain within explicit risk, authorization, audit, and control boundaries while only taking trades that survive disciplined state, cost, governance, and execution scrutiny.*
