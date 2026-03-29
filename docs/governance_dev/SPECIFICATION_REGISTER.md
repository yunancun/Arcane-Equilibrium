# Governance Specification Register / 治理規範註冊表

**Project:** OpenClaw / Bybit
**Last Updated:** 2026-03-30
**Maintained By:** R4 (Document Auditor)

---

## Active Specifications / 活躍規範

### State Machine Specifications (SM)

| Code | Name | Module | Status | Description |
|------|------|--------|--------|-------------|
| SM-01 | Authorization State Machine | authorization_state_machine.py | ✅ Active | 8 states, 16 transitions, fail-closed auth |
| SM-02 | Decision Lease State Machine | decision_lease_state_machine.py | ✅ Active | 9 states, TTL-based lease lifecycle |
| SM-03 | (Reserved) | — | ⏳ Reserved | Reserved for future state machine |
| SM-04 | Risk Governor State Machine | risk_governor_state_machine.py | ✅ Active | 6-level risk escalation/de-escalation |

### Exchange Specifications (EX)

| Code | Name | Module(s) | Status | Description |
|------|------|-----------|--------|-------------|
| EX-01 | Protection & Anti-Hunt | protective_order_manager.py, portfolio_risk_control.py | ✅ Active | Hard stops, ATR dynamic distance, correlation gates |
| EX-02 | OMS & Order Lifecycle | oms_state_machine.py | ✅ Active | 11-state order management with reconciliation gate |
| EX-03 | (Reserved) | — | ⏳ Reserved | Reserved for future exchange spec |
| EX-04 | Reconciliation Engine | reconciliation_engine.py | ✅ Active | Paper vs. live/demo position consistency checks |
| EX-05 | Learning Tiers & Autonomy | learning_tier_gate.py | ✅ Active | L1-L5 analyst evolution with tier gates |
| EX-06 | Agent Conflict Arbitration | multi_agent_framework.py, market_regime.py | ✅ Active | Scout/Conductor pattern, fact/inference/hypothesis |
| EX-07 | Agent Data Access Control | governance_hub.py | ✅ Active | Cross-SM authorization and data flow control |

### Organization Document Specifications (DOC)

| Code | Name | Module(s) | Status | Description |
|------|------|-----------|--------|-------------|
| DOC-01 | Core Risk Doctrine | protective_order_manager.py | ✅ Active | Hard stop-loss §5.9, position sizing, risk limits |
| DOC-02 | Scanning & Monitoring | scanner_rate_limiter.py | ✅ Active | 5-minute scan interval, rate limiting |
| DOC-03 | Market Regime Detection | market_regime.py | ✅ Active | Regime classification, confidence scoring |
| DOC-04 | Agent Learning Evolution | learning_tier_gate.py | ✅ Active | Tier advancement criteria, performance metrics |
| DOC-06 | Change Audit Log | change_audit_log.py | ✅ Active | Append-only JSONL, rotation, thread-safe |
| DOC-07 | Audit Persistence | audit_persistence.py | ✅ Active | JSONL audit trail, file rotation |
| DOC-08 | Incident Response | incident_event_model.py | ✅ Active | Incident classification, SM trigger integration |

---

## Specification Numbering Rules / 編號規則

- **SM-XX**: State Machine specifications (core governance automata)
- **EX-XX**: Exchange specifications (trading operations and integration)
- **DOC-XX**: Organization document specifications (policies and procedures)
- **§** notation: Section references within a spec (e.g., "DOC-01 §5.9")

---

## Cross-Reference Summary / 交叉引用摘要

| Metric | Count |
|--------|-------|
| Active specifications | 16 |
| Reserved specifications | 2 (SM-03, EX-03) |
| Total code references | 335+ |
| Implementing modules | 22 |
| Test coverage | 1,566 tests |

---

## How to Add New Specifications / 如何新增規範

1. Assign next available code in appropriate category (SM/EX/DOC)
2. Create implementation module following naming convention (lowercase_snake_case)
3. Add spec code references in code comments (e.g., `# Per SM-XX §Y`)
4. Create test file with matching name (test_module_name.py)
5. Add changelog entry in `docs/governance_dev/phase{N}_*/changelogs/`
6. Update this register

---

*OpenClaw / Bybit Governance Specification Register*
