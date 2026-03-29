# Governance Module Migration Plan

This document outlines the planned migration of governance modules from their current location in the control API to a dedicated governance subsystem.

## Overview

**Current Location:** `program_code/exchange_connectors/bybit_connector/control_api_v1/app/`

**Target Location:** `program_code/governance/`

The migration will consolidate governance modules into a cohesive, independently versioned subsystem organized by functional domain.

## Governance Module Categories

Governance modules are organized into five functional domains:

### 1. Base (Core Interfaces & Utilities)
Fundamental abstractions, type definitions, and event models used across all governance domains.

### 2. Authorization
Permission and authorization-related governance logic, including approval gates and recovery controls.

### 3. Risk Governor
Risk management state machines and portfolio-level risk controls.

### 4. Decision Lease
Decision lifecycle management, TTL enforcement, and execution control.

### 5. Reconciliation
Audit trails, trade attribution, and consistency verification.

---

## Migration Mapping Table

| # | Module Name | Current Path | Target Path | Category | Description |
|---|---|---|---|---|---|
| 1 | incident_event_model | `app/incident_event_model.py` | `governance/base/incident_event_model.py` | Base | Event and incident data models |
| 2 | change_audit_log | `app/change_audit_log.py` | `governance/base/change_audit_log.py` | Base | Change tracking and audit log models |
| 3 | authorization_state_machine | `app/authorization_state_machine.py` | `governance/authorization/authorization_state_machine.py` | Authorization | Authorization and permission state machine |
| 4 | recovery_approval_gate | `app/recovery_approval_gate.py` | `governance/authorization/recovery_approval_gate.py` | Authorization | Recovery and approval gate logic |
| 5 | risk_governor_state_machine | `app/risk_governor_state_machine.py` | `governance/risk_governor/risk_governor_state_machine.py` | Risk Governor | Risk governance state transitions |
| 6 | risk_manager | `app/risk_manager.py` | `governance/risk_governor/risk_manager.py` | Risk Governor | Core risk management logic |
| 7 | portfolio_risk_control | `app/portfolio_risk_control.py` | `governance/risk_governor/portfolio_risk_control.py` | Risk Governor | Portfolio-level risk controls |
| 8 | protective_order_manager | `app/protective_order_manager.py` | `governance/risk_governor/protective_order_manager.py` | Risk Governor | Protective order management and enforcement |
| 9 | decision_lease_state_machine | `app/decision_lease_state_machine.py` | `governance/decision_lease/decision_lease_state_machine.py` | Decision Lease | Decision lease state management |
| 10 | ttl_enforcer | `app/ttl_enforcer.py` | `governance/decision_lease/ttl_enforcer.py` | Decision Lease | Time-to-live enforcement for decisions |
| 11 | lease_ttl_config | `app/lease_ttl_config.py` | `governance/decision_lease/lease_ttl_config.py` | Decision Lease | TTL configuration and policies |
| 12 | shadow_decision_builder | `app/shadow_decision_builder.py` | `governance/decision_lease/shadow_decision_builder.py` | Decision Lease | Shadow decision building for execution control |
| 13 | reconciliation_engine | `app/reconciliation_engine.py` | `governance/reconciliation/reconciliation_engine.py` | Reconciliation | Core reconciliation and consistency logic |
| 14 | audit_persistence | `app/audit_persistence.py` | `governance/reconciliation/audit_persistence.py` | Reconciliation | Audit log persistence and verification |
| 15 | trade_attribution | `app/trade_attribution.py` | `governance/reconciliation/trade_attribution.py` | Reconciliation | Trade attribution and accounting |
| 16 | data_source_enforcer | `app/data_source_enforcer.py` | `governance/base/data_source_enforcer.py` | Base | Data source enforcement and validation |
| 17 | learning_tier_gate | `app/learning_tier_gate.py` | `governance/authorization/learning_tier_gate.py` | Authorization | Learning tier gating logic |
| 18 | paper_live_gate | `app/paper_live_gate.py` | `governance/authorization/paper_live_gate.py` | Authorization | Paper-to-live trading gate |
| 19 | oms_state_machine | `app/oms_state_machine.py` | `governance/base/oms_state_machine.py` | Base | Order management state machine |
| 20 | market_regime | `app/market_regime.py` | `governance/base/market_regime.py` | Base | Market regime detection and classification |
| 21 | scanner_rate_limiter | `app/scanner_rate_limiter.py` | `governance/base/scanner_rate_limiter.py` | Base | Rate limiting and throttling |

---

## Migration Strategy

### Phase 1: Namespace Reservation (CURRENT - In Progress)
- Create directory structure under `program_code/governance/`
- Create placeholder `__init__.py` files in each subdomain
- Create this migration plan document
- **Status:** Reserved, no code movement yet

### Phase 2: Adapter Layer Creation
Once migration is approved, we will:
1. Create import adapters in the original locations that re-export from new locations
2. Add deprecation warnings to adapter imports
3. Update all internal imports to point to new locations
4. Maintain backward compatibility for external consumers

Example adapter structure in `app/reconciliation_engine.py`:
```python
# DEPRECATED: Import from new location
# Scheduled for removal in Q3 2026
import warnings
from program_code.governance.reconciliation.reconciliation_engine import *

warnings.warn(
    "Importing from app.reconciliation_engine is deprecated. "
    "Use program_code.governance.reconciliation.reconciliation_engine instead.",
    DeprecationWarning,
    stacklevel=2
)
```

### Phase 3: Import Updates
1. Update all internal imports within the control API
2. Update all references in other packages
3. Verify all tests pass
4. Update CI/CD configuration if needed

### Phase 4: Deprecation Period (6-8 weeks)
- Maintain adapter layer for backward compatibility
- Document migration in release notes
- Provide clear upgrade path to consumers
- Monitor for external usage

### Phase 5: Cleanup
- Remove adapter layer imports
- Remove deprecated re-exports
- Archive old location as documentation reference

---

## Directory Structure After Migration

```
program_code/
├── governance/
│   ├── __init__.py
│   ├── MIGRATION_PLAN.md
│   │
│   ├── base/
│   │   ├── __init__.py
│   │   ├── incident_event_model.py
│   │   ├── change_audit_log.py
│   │   ├── data_source_enforcer.py
│   │   ├── oms_state_machine.py
│   │   ├── market_regime.py
│   │   └── scanner_rate_limiter.py
│   │
│   ├── authorization/
│   │   ├── __init__.py
│   │   ├── authorization_state_machine.py
│   │   ├── recovery_approval_gate.py
│   │   ├── learning_tier_gate.py
│   │   └── paper_live_gate.py
│   │
│   ├── risk_governor/
│   │   ├── __init__.py
│   │   ├── risk_governor_state_machine.py
│   │   ├── risk_manager.py
│   │   ├── portfolio_risk_control.py
│   │   └── protective_order_manager.py
│   │
│   ├── decision_lease/
│   │   ├── __init__.py
│   │   ├── decision_lease_state_machine.py
│   │   ├── ttl_enforcer.py
│   │   ├── lease_ttl_config.py
│   │   └── shadow_decision_builder.py
│   │
│   └── reconciliation/
│       ├── __init__.py
│       ├── reconciliation_engine.py
│       ├── audit_persistence.py
│       └── trade_attribution.py
```

---

## Implementation Checklist

### Pre-Migration
- [ ] Review all module dependencies and import chains
- [ ] Identify all external consumers (other packages, scripts)
- [ ] Create comprehensive test coverage for all governance modules
- [ ] Document any circular dependencies or special cases

### Migration Execution
- [ ] Copy all governance modules to new locations
- [ ] Create import adapters in original locations
- [ ] Update all internal imports (Phase 3)
- [ ] Run full test suite
- [ ] Update CI/CD configuration
- [ ] Create release notes

### Post-Migration
- [ ] Monitor adapter usage
- [ ] Collect feedback from consumers
- [ ] Track deprecation timeline
- [ ] Remove adapters at end of deprecation period

---

## Rollback Plan

If migration encounters critical issues:

1. **Pause at Phase 1:** If issues are found before Phase 2 starts, simply don't proceed
2. **Rollback during Phase 2-3:** Restore adapters to full re-exports, revert import changes
3. **Full Rollback:** Delete governance directory, revert all branch changes

---

## Timeline

- **Week 1:** Namespace reservation (Phase 1) - ✓ COMPLETED
- **Week 2-3:** Adapter creation and testing (Phase 2)
- **Week 4:** Import updates and CI validation (Phase 3)
- **Week 5-8:** Deprecation period (Phase 4)
- **Week 9:** Cleanup (Phase 5)

---

## Notes

- This migration maintains full backward compatibility during the deprecation period
- The 21 governance modules represent the core control and decision-making logic of the system
- Migration enables independent versioning and testing of governance logic
- New modules can be added to the governance subsystem without cluttering the control API
- Consider creating governance-specific documentation and API specifications post-migration
