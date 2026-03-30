# Gap Analysis — File Reference & Navigation Guide

**Purpose:** Quick lookup of implementation files for each spec requirement

---

## CORE GOVERNANCE COMPONENTS

### SM-01: Authorization State Machine
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/authorization_state_machine.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - States definition: 52-70
  - Transition rules: 119-154
  - State machine implementation: 392-724
- **Tests:** `test_governance_hub.py`, `test_change_audit_log.py`

### SM-02: Decision Lease State Machine
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/decision_lease_state_machine.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - States definition: 53-64
  - Lease object with immutable parameters: 227-380
  - State machine implementation: 392-740
- **Config:** `/app/lease_ttl_config.py`
- **Tests:** `test_governance_hub.py`, `test_integration_phase7.py`

### SM-04: Risk Governor State Machine
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_governor_state_machine.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - Risk level definition: 63-77
  - Risk events: 83-110
  - Transition rules: 125-147
  - State machine implementation: 420-858
- **Integration:** `/app/governance_hub.py:366`
- **Tests:** `test_governance_hub.py`

### SM-03: OMS State Machine (EX-02)
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/oms_state_machine.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - 11-state lifecycle: 44-61
  - Transition rules: 110-180
- **Related:** `/app/paper_trading_engine.py` (7-state base)
- **Tests:** `test_governance_hub.py`

---

## PROTECTION MECHANISMS

### EX-01: Protection & Anti-Hunt

#### Protective Orders
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/protective_order_manager.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - Order types (6): 60-94
  - Order configuration: 100-147
  - Protective order implementation: 150+
- **Features:** Dual defense, ATR scaling, anti-hunt stealth
- **Tests:** `test_protective_order_manager.py`

#### Portfolio Risk Control
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/portfolio_risk_control.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - Correlation config: 48-72
  - Price return tracker: 79-140
  - Portfolio risk control: 150+
- **Thresholds:** 0.7 correlation, 40% sector limit, 30% reserve buffer
- **Tests:** `test_portfolio_risk_control.py`

#### Risk Manager
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_manager.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - Position limits config: 290-330
  - cost_edge_ratio computation: 953-974
  - Risk pressure calculation: 900+
- **Tests:** `test_risk_manager.py` (legacy)

### EX-04: Reconciliation Engine
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/reconciliation_engine.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - Discrepancy types: 46-69
  - Severity levels: 71-77
  - Configuration: 92-100
  - Engine implementation: 300+
- **Features:** 5-retry conflict resolution, discrepancy classification
- **Tests:** (Not explicitly found; assumed covered in governance_hub tests)

---

## AUDIT & EXPLAINABILITY

### Trade Attribution (DOC-01 §5.8)
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/trade_attribution.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - Attribution factors (6): 60-68
  - Attribution score: 82-115
  - Trade attribution result: 118-150
  - attribute_trade() method: 150+
  - aggregate_attribution(): 200+
- **Factors:** ALPHA, TIMING, SIZING, EXECUTION, COST, LUCK
- **Tests:** `test_trade_attribution.py`, `test_trade_attribution_integration.py`

### Audit Persistence
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/audit_persistence.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Integration:** All state machines emit audit callbacks
- **Tests:** `test_audit_persistence.py`

### Change Audit Log
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Features:** Immutable append-only state change tracking
- **Tests:** `test_change_audit_log.py`

### Incident Event Model
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/incident_event_model.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - FormalEvent definition: 90+
  - Event attributes with truth source integrity: 150+
- **Tests:** `test_incident_event_model.py`

---

## DATA QUALITY & SOURCES

### Perception Data Plane (EX-07)
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/perception_data_plane.py`
- **Status:** CATEGORY B (Partial)
- **Key Lines:**
  - Cognitive level definition: 29-38
  - Data source types: 49-59
  - Source cognitive defaults: 62-71
  - Perception data object: 128-150
  - register_data() method: 333+
- **Features:** Fact/inference marking, freshness tracking, quality assessment
- **Tests:** `test_perception_data_plane.py`

### Data Source Enforcer
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/data_source_enforcer.py`
- **Status:** CATEGORY B (Partial)
- **Features:** Source validation, access control per agent
- **Gap:** Integration with risk decisions not fully verified

---

## AGENT FRAMEWORK

### Multi-Agent Framework
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Key Lines:**
  - Agent roles (5): 29-36
  - Message types (8): 39-52
  - Structured message objects: 97-150
  - Conflict resolution: Guardian > Strategist
- **Tests:** `test_governance_hub.py`

### Scout Agent
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_routes.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Tests:** `test_scout_integration.py`

### Strategist Agent
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`
- **Status:** CATEGORY A (Fully Implemented)

### Guardian Agent
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Tests:** `test_batch8_guardian_integration.py`

### Analyst Agent
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_agent.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Integration:** L1 post-trade review, trade attribution

### Executor Agent
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Feature:** Single write port (exclusive order execution)

### Governance Hub (Orchestration)
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Integration:** SM-01, SM-02, SM-04, EX-04, all agents
- **Key Lines:**
  - SM-01 integration: 87-93
  - SM-04 integration: 93-96
  - SM-02 integration: 98-99
  - EX-04 integration: 102-103
  - SM wiring: 344-379

---

## LEARNING SYSTEM

### Learning Tier Gate (EX-05)
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_tier_gate.py`
- **Status:** CATEGORY C (Partial: L1 works, L2 partial, L3-L5 stubbed)
- **Key Lines:**
  - Learning tiers definition: 60-107
  - Tier eligibility criteria: 134-157
  - Tier capabilities: 165-240
  - Learning tier gate implementation: 300+
- **L1 Status:** Implemented (post-trade review in analyst_agent.py)
- **L2 Status:** Framework defined; auto-discovery not wired
- **L3-L5 Status:** Tier definitions only; pipeline empty
- **Tests:** `test_learning_tier_gate.py`, `test_learning_promotion_integration.py`

### Paper Trading Engine
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_engine.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Features:** 7-state OMS, metrics tracking, strategy validation

### Paper Trading Metrics
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_metrics.py`
- **Status:** CATEGORY A (Fully Implemented)

### Paper-Live Gate
- **File:** `/sessions/determined-epic-cori/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_live_gate.py`
- **Status:** CATEGORY A (Fully Implemented)
- **Features:** 11-point eligibility criteria for live trading promotion
- **Tests:** (Assumed covered in governance tests)

---

## CRITICAL GAPS

### H0 Gate (DOC-02) — MISSING
- **Status:** CATEGORY D (Missing entirely)
- **Required File:** `/app/h0_gate.py` (DOES NOT EXIST)
- **Why Critical:** Every trade decision requires this <1ms deterministic check
- **Missing Checks:**
  - Market data freshness (<1000ms)
  - Health check (CPU, memory, latency, losses)
  - Risk envelope validation
  - Cooldown enforcement
- **Remediation:** Create h0_gate.py with inline deterministic checks

### Learning L3-L5 Evolution — STUBBED
- **Status:** CATEGORY C (Stubs only)
- **Required Files:**
  - `backtesting_engine.py` (MISSING)
  - `hypothesis_generator.py` (MISSING)
  - `strategy_evolution_engine.py` (MISSING)
  - `meta_learning_engine.py` (MISSING)
- **Why Stubbed:** Requires robust backtesting/training infrastructure
- **Remediation:** Phase 2 feature; defer for Phase 1

---

## NAVIGATION BY SPEC SECTION

### DOC-01: Core Risk Doctrine (18 Requirements)
- **DOC01-R01:** Single Write Port → `/app/executor_agent.py`
- **DOC01-R03:** AI Output Forms Leases → `/app/decision_lease_state_machine.py`
- **DOC01-R07:** 6-Element Trade Reconstruction → `/app/trade_attribution.py` (6 factors)
- **DOC01-R08:** Hard Stop-Loss Protection → `/app/protective_order_manager.py`
- **DOC01-R18:** 6-Level Degradation Modes → `/app/risk_governor_state_machine.py`

### DOC-02: Scanning & Monitoring (8 Requirements)
- **H0 Gate (DOC02-R02-R07):** MISSING (no h0_gate.py)
- **Freshness Check:** Would be in h0_gate.py
- **Health Check:** `/app/governance_routes.py:governance_health_check()` (HTTP, not <1ms)

### SM-01: Authorization (16 Requirements)
- **File:** `/app/authorization_state_machine.py` (724 lines)
- **Status:** CATEGORY A

### SM-02: Decision Lease (22 Requirements)
- **File:** `/app/decision_lease_state_machine.py` (740 lines)
- **Status:** CATEGORY A

### SM-04: Risk Governor (20 Requirements)
- **File:** `/app/risk_governor_state_machine.py` (858 lines)
- **Status:** CATEGORY A

### EX-01: Protection & Anti-Hunt (12 Requirements)
- **Protective Orders:** `/app/protective_order_manager.py`
- **Portfolio Risk:** `/app/portfolio_risk_control.py`
- **Risk Manager:** `/app/risk_manager.py`
- **Status:** CATEGORY A

### EX-02: OMS Order Lifecycle (2 Requirements)
- **File:** `/app/oms_state_machine.py`
- **Status:** CATEGORY A

### EX-04: Reconciliation (3 Requirements)
- **File:** `/app/reconciliation_engine.py`
- **Status:** CATEGORY A

### EX-05: Learning L1-L5 (see EX-05 §3 / DOC-04 §6)
- **File:** `/app/learning_tier_gate.py`
- **Status:** CATEGORY C (L1 works, L2-L5 stubbed)

### EX-06: Multi-Agent (see §2-§10)
- **File:** `/app/multi_agent_framework.py`
- **Status:** CATEGORY A

### EX-07: Data Quality (see §1-§8)
- **File:** `/app/perception_data_plane.py`
- **Status:** CATEGORY B (framework; enforcement partial)

---

## QUICK TEST REFERENCE

| Component | Test File(s) |
|-----------|--------------|
| SM-01 | test_governance_hub.py |
| SM-02 | test_governance_hub.py |
| SM-04 | test_governance_hub.py |
| EX-01 Protective Orders | test_protective_order_manager.py |
| EX-01 Portfolio Risk | test_portfolio_risk_control.py |
| EX-02 OMS | test_governance_hub.py |
| EX-04 Reconciliation | test_governance_hub.py (implied) |
| Trade Attribution | test_trade_attribution.py, test_trade_attribution_integration.py |
| Audit | test_audit_persistence.py, test_change_audit_log.py |
| Agents | test_scout_integration.py, test_batch8_guardian_integration.py |
| Learning L1-L2 | test_learning_tier_gate.py, test_learning_promotion_integration.py |
| Data Quality | test_perception_data_plane.py |
| Incident | test_incident_event_model.py |

---

## TOTAL TEST COUNT
- **78 test files** across codebase
- **2,227 tests passing** (Phase 0 baseline)
- **Missing:** H0 Gate tests, Learning L3-L5 tests, Backtesting tests

---

**Last Updated:** 2026-03-31
**Report Location:** `/sessions/determined-epic-cori/srv/GAP_ANALYSIS_REPORT.md`
**Detailed Findings:** `/sessions/determined-epic-cori/srv/GAP_ANALYSIS_DETAILED_FINDINGS.json`
