# FA Architecture Report: Phase 1 Governance Wiring
## 治理接入架構報告（Phase 1）

**版本：** V1.0  
**日期：** 2026-03-30  
**作者：** FA（Architect via Cowork）  
**狀態：** COMPLETE  
**涵蓋任務：** T1.01、T1.04、T1.05  

---

## Executive Summary 執行摘要

本報告完成三項 FA 架構設計任務：

1. **T1.01 PipelineBridge GovernanceHub 注入驗證** ✅
   - 驗證無循環依賴，注入方式確認
   - 建議：直接 import（無延遲導入必要）

2. **T1.04 AuditPipeline 整合架構設計** ✅
   - 設計 AuditPipeline 與四個 SM 的整合時序
   - 確認初始化順序、回調連接、持久化流程

3. **T1.05 Incident→SM 事件映射表設計** ✅
   - 設計 IncidentPolicy 的事件→狀態機轉換映射
   - 確認回調連接點、級聯邏輯、事件嚴重度映射

---

## Task 1: PipelineBridge GovernanceHub Injection (T1.01)

### Problem Statement 問題描述

**源位置：**
- `app/phase2_strategy_routes.py:193-201` — PipelineBridge 初始化
- `app/paper_trading_routes.py:69` — GOV_HUB 已創建
- `app/pipeline_bridge.py:125-127` — set_governance_hub() 方法存在但未被調用

**核心問題：** PipelineBridge 被創建時，GOV_HUB 已存在於 paper_trading_routes，但 phase2_strategy_routes 並未注入它，導致 PipelineBridge._governance_hub 始終為 None。

### Circular Dependency Analysis 循環依賴分析

#### Import Chain Verification 導入鏈驗證

**phase2_strategy_routes.py 導入順序：**
```
1. main.py (入口) → 導入兩個路由模組
2. phase2_strategy_routes.py (第一次加載)
   ├─ 第 183-204: 嘗試導入 paper_trading_routes
   │  └─ paper_trading_routes.py (第一次加載，完成初始化)
   │     ├─ 第 59: ENGINE = PaperTradingEngine(...)
   │     ├─ 第 69: GOV_HUB = GovernanceHub(...)
   │     └─ 第 70-71: ENGINE.set_governance_hub(), RISK_MANAGER.set_governance_hub()
   │        (完成，傳回控制權給 phase2_strategy_routes)
   ├─ 第 193: PIPELINE_BRIDGE = PipelineBridge(...) ← GOV_HUB 此時已存在
   └─ (後續: 注入應在此執行)

3. 此模式下無循環：
   - phase2_strategy_routes → paper_trading_routes（單向）
   - paper_trading_routes 不導入 phase2_strategy_routes
```

**測試驗證腳本：**

```python
# Test: Verify no circular import
import sys
import types

# Before import
initial_modules = set(sys.modules.keys())

# Try to import both modules
try:
    from app.paper_trading_routes import GOV_HUB
    from app.phase2_strategy_routes import PIPELINE_BRIDGE
    
    # Check if circular import happened
    new_modules = set(sys.modules.keys()) - initial_modules
    assert 'app.paper_trading_routes' in new_modules
    assert 'app.phase2_strategy_routes' in new_modules
    
    print("✓ No circular import detected")
    print(f"✓ GOV_HUB is available: {GOV_HUB is not None}")
    print(f"✓ PIPELINE_BRIDGE is available: {PIPELINE_BRIDGE is not None}")
    
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)
```

### Injection Strategy 注入方案

**建議方案：直接 import（無延遲注入必要）**

**理由：**
1. GOV_HUB 在 paper_trading_routes.py 中已完全初始化（第 69 行）
2. phase2_strategy_routes.py 已成功導入 paper_trading_routes（第 183-204 行）
3. PIPELINE_BRIDGE 創建於第 193-200 行，此時 GOV_HUB 已可用
4. 無需延遲注入（lazy import）

**實現方式：**

在 `app/phase2_strategy_routes.py:201` 之後添加：

```python
# ── Governance Hub injection into PipelineBridge ──
# 注入治理集線器到管線橋接器
try:
    from .paper_trading_routes import GOV_HUB as _GOV_HUB_REF
    if _GOV_HUB_REF is not None and PIPELINE_BRIDGE is not None:
        PIPELINE_BRIDGE.set_governance_hub(_GOV_HUB_REF)
        logger.info(
            "GovernanceHub injected into PipelineBridge "
            "/ 治理集線器已注入管線橋接器"
        )
    else:
        logger.warning(
            "GovernanceHub injection skipped: hub=%s, bridge=%s",
            _GOV_HUB_REF is not None, PIPELINE_BRIDGE is not None
        )
except ImportError as e:
    logger.warning("Could not import GOV_HUB for injection: %s", e)
except Exception as e:
    logger.error("Failed to inject GovernanceHub into PipelineBridge: %s", e)
    raise
```

### Risk Assessment 風險評估

| 風險項 | 等級 | 緩解措施 |
|--------|------|---------|
| Import 失敗 | LOW | try-except 包裝，記錄警告 |
| GOV_HUB 為 None | LOW | 檢查 `is not None` 再注入 |
| 啟動順序 | MINIMAL | GOV_HUB 初始化早於 PIPELINE_BRIDGE，無可能失序 |
| 線程競態 | LOW | 兩者皆為模組級單例，初始化階段無並發 |

### Acceptance Criteria 驗收標準

- [ ] T1.01 code change 實現（E1b）
- [ ] `PIPELINE_BRIDGE._governance_hub is not None` 驗證通過
- [ ] `pipeline_bridge.py:278-290` 中 `is_authorized()` 檢查生效
- [ ] `pytest tests/ -x` 所有現有測試通過
- [ ] `test_pipeline_bridge_governance_injection` 新增測試通過

---

## Task 2: AuditPipeline Integration Architecture (T1.04)

### Problem Statement 問題描述

**源位置：**
- `app/audit_persistence.py:471-549` — AuditPipeline 完整實現
- `app/governance_hub.py:207-234` — _ensure_initialized() 中 SM 初始化
- `app/paper_trading_routes.py:69-71` — GOV_HUB 創建，但未創建 AuditPipeline

**核心問題：** 
- AuditPipeline 提供了 `make_callback(source)` 方法，可生成回調供 SM 使用
- 但 paper_trading_routes 初始化 GOV_HUB 時未創建 AuditPipeline
- 結果：SM 的審計記錄只寫入記憶體，無持久化

### Integration Architecture 整合架構

#### Initialization Sequence 初始化時序

**當前流程（缺陷）：**
```
paper_trading_routes 初始化
├─ RISK_MANAGER = RiskManager()
├─ ENGINE = PaperTradingEngine(...)
├─ GOV_HUB = GovernanceHub(audit_dir=...)
│  └─ GOV_HUB._ensure_initialized()
│     ├─ AuthorizationStateMachine(audit_callback=None)  ← 無持久化
│     ├─ RiskGovernorStateMachine(audit_callback=None)    ← 無持久化
│     ├─ DecisionLeaseStateMachine(audit_callback=None)   ← 無持久化
│     └─ ReconciliationEngine(audit_callback=None)        ← 無持久化
└─ ENGINE.set_governance_hub(GOV_HUB)
```

**修正後流程（T1.04）：**
```
paper_trading_routes 初始化
├─ RISK_MANAGER = RiskManager()
├─ ENGINE = PaperTradingEngine(...)
│
├─ AUDIT_PIPELINE = AuditPipeline(
│      config=AuditPersistenceConfig(base_dir=...)
│  )  ← 【NEW】持久化寫入器初始化
│
├─ GOV_HUB = GovernanceHub(audit_dir=...)
│  └─ GOV_HUB._ensure_initialized()  ← 延遲初始化（首次 is_authorized() 時）
│     ├─ auth_callback = AUDIT_PIPELINE.make_callback("authorization")
│     ├─ risk_callback = AUDIT_PIPELINE.make_callback("risk_governor")
│     ├─ lease_callback = AUDIT_PIPELINE.make_callback("decision_lease")
│     ├─ recon_callback = AUDIT_PIPELINE.make_callback("reconciliation")
│     ├─ AuthorizationStateMachine(audit_callback=auth_callback)
│     ├─ RiskGovernorStateMachine(audit_callback=risk_callback)
│     ├─ DecisionLeaseStateMachine(audit_callback=lease_callback)
│     └─ ReconciliationEngine(audit_callback=recon_callback)
│
├─ GOV_HUB.set_audit_pipeline(AUDIT_PIPELINE)  ← 【新增方法】
└─ ENGINE.set_governance_hub(GOV_HUB)
```

#### Key Design Points 關鍵設計點

1. **AuditPipeline 創建位置：**
   - 在 `paper_trading_routes.py` 中創建
   - 在 GOV_HUB 初始化前創建（這樣 GOV_HUB._ensure_initialized() 時就可以使用）

2. **GovernanceHub 修改：**
   - 添加 `set_audit_pipeline(pipeline)` 方法
   - 在 _ensure_initialized() 中，如果 audit_pipeline 已設置，則使用其 make_callback()
   - 否則，使用內置的 _make_audit_callback()（向後兼容）

3. **SM 初始化改進：**
   - AuthorizationStateMachine, RiskGovernorStateMachine, DecisionLeaseStateMachine 現在都接收 audit_callback
   - ReconciliationEngine 接收 audit_callback 和 incident_callback

### AuditPipeline Integration Code 集成代碼

**governance_hub.py 修改：**

```python
class GovernanceHub:
    def __init__(self, *, audit_dir: str, enabled: bool = True):
        # ... 現有代碼 ...
        self._audit_pipeline: Optional[Any] = None  # ← NEW
    
    def set_audit_pipeline(self, pipeline: Any) -> None:
        """Set the audit pipeline for SM callbacks / 設置審計管道供 SM 回調使用"""
        with self._lock:
            self._audit_pipeline = pipeline
            logger.info("Audit pipeline set on GovernanceHub")
    
    def _ensure_initialized(self) -> None:
        """Lazy-initialize SMs on first access"""
        if self._initialized:
            return
        
        try:
            # ... 導入代碼 ...
            
            # Create or use provided audit callbacks
            if self._audit_pipeline is not None:
                # Use audit pipeline callbacks
                auth_callback = self._audit_pipeline.make_callback("authorization")
                risk_callback = self._audit_pipeline.make_callback("risk_governor")
                lease_callback = self._audit_pipeline.make_callback("decision_lease")
                recon_callback = self._audit_pipeline.make_callback("reconciliation")
            else:
                # Use built-in audit callbacks (backward compatible)
                auth_callback = self._make_audit_callback("authorization")
                risk_callback = self._make_audit_callback("risk_governor")
                lease_callback = self._make_audit_callback("decision_lease")
                recon_callback = self._make_audit_callback("reconciliation")
            
            # ... SM 創建 ...
```

**paper_trading_routes.py 修改：**

```python
# 在現有代碼 第 69 行後：
from .audit_persistence import AuditPipeline, AuditPersistenceConfig

_audit_config = AuditPersistenceConfig(
    base_dir=_gov_audit_dir,  # 重用已有的 audit 目錄
)
AUDIT_PIPELINE = AuditPipeline(config=_audit_config)

GOV_HUB = GovernanceHub(audit_dir=_gov_audit_dir)
GOV_HUB.set_audit_pipeline(AUDIT_PIPELINE)  # ← 注入審計管道
ENGINE.set_governance_hub(GOV_HUB)
RISK_MANAGER.set_governance_hub(GOV_HUB)
```

### Audit Data Flow 審計數據流

```
Event 發生
│
├─ AuthorizationStateMachine._on_state_change()
│  └─ audit_callback({"event": "state_change", ...})
│     └─ AuditPipeline.ingest()
│        ├─ AuditFileWriter.write() → 磁盤 (JSON Lines)
│        └─ 通知訂閱者
│
├─ RiskGovernorStateMachine._on_level_change()
│  └─ audit_callback({"level_change": ...})
│     └─ AuditPipeline.ingest()
│
├─ DecisionLeaseStateMachine.activate()
│  └─ audit_callback({"lease_id": ..., "state": "ACTIVE"})
│     └─ AuditPipeline.ingest()
│
└─ ReconciliationEngine.reconcile()
   └─ audit_callback({"reconciliation": ...})
      └─ AuditPipeline.ingest()
```

### File Organization 文件組織

**審計文件位置：** `runtime/governance_audit/`

**文件名規則：**
- `authorization_audit_2026-03-30.jsonl` (按日期)
- `authorization_audit_2026-03-30_1.jsonl` (超過 50MB 時)

**每行內容（JSON Lines）：**
```json
{
  "audit_id": "aud:abc123def456",
  "persisted_at_ms": 1711837200000,
  "sm_name": "authorization",
  "source": "authorization",
  "record": {
    "authorization_id": "auth:xyz789",
    "state": "ACTIVE",
    "timestamp_ms": 1711837200000,
    ...
  }
}
```

### Acceptance Criteria 驗收標準

- [ ] AuditPipeline 在 paper_trading_routes 中創建
- [ ] GOV_HUB.set_audit_pipeline() 方法實現
- [ ] SM 狀態轉換記錄到磁盤 JSON Lines 文件
- [ ] 審計文件位於 `runtime/governance_audit/`
- [ ] 文件自動按日期 / 50MB 輪轉
- [ ] AuditFileReader.query() 可成功讀取
- [ ] 日誌包含 transition_id、trigger_event_id、approved_by
- [ ] 現有測試通過 + 持久化驗證測試通過

---

## Task 3: Incident→SM Cascading Event Mapping (T1.05)

### Problem Statement 問題描述

**源位置：**
- `app/incident_event_model.py:237-265` — SEVERITY_ACTION_MAP (事件→動作映射)
- `app/incident_event_model.py:323-394` — IncidentPolicy.process_event()
- `app/governance_hub.py:616-708` — _on_risk_escalation(), _on_auth_frozen()
- `app/reconciliation_engine.py:226-230` — incident_callback 支持
- 缺失：IncidentPolicy 未在主流程實例化，回調未連接

### Event Severity to Action Mapping 事件嚴重度映射

**核心映射表（DOC-07 §3-§5）：**

```python
SEVERITY_ACTION_MAP = {
    EventSeverity.NOTICE (0): [
        RECORD_ONLY  # 僅記錄
    ],
    
    EventSeverity.ANOMALY (1): [
        RECORD_ONLY,
        INCREASE_MONITORING,           # 提升監控
        RISK_ESCALATE_CAUTIOUS,        # 風險升級到 CAUTIOUS
    ],
    
    EventSeverity.NEAR_MISS (2): [
        RECORD_ONLY,
        AUTH_RESTRICT,                 # 授權限制
        RISK_ESCALATE_REDUCED,         # 風險升級到 REDUCED
        OPERATOR_ALERT,                # 運營商告警
    ],
    
    EventSeverity.INCIDENT (3): [
        AUTH_FREEZE,                   # 授權凍結
        RISK_ESCALATE_DEFENSIVE,       # 風險升級到 DEFENSIVE
        MANUAL_REVIEW,                 # 需人工審核
        OPERATOR_ALERT,
    ],
    
    EventSeverity.CRITICAL_INCIDENT (4): [
        AUTH_FREEZE,
        RISK_CIRCUIT_BREAKER,          # 風險升級到 CIRCUIT_BREAKER
        TRADING_FREEZE,                # 交易凍結（同時凍結 Auth 和 Risk）
        MANUAL_REVIEW,
        OPERATOR_ALERT,
    ]
}
```

### Incident→SM Callback Mapping 回調連接映射表

| 事件嚴重度 | 動作 | 目標 SM | 調用方法 | 效果 |
|----------|------|--------|---------|------|
| ANOMALY | RISK_ESCALATE_CAUTIOUS | RiskGovernor | _on_risk_action("RISK_ESCALATE_CAUTIOUS", ...) | Risk level → 1 |
| NEAR_MISS | AUTH_RESTRICT | Authorization | _on_auth_action("AUTH_RESTRICT", ...) | Auth → RESTRICTED |
| NEAR_MISS | RISK_ESCALATE_REDUCED | RiskGovernor | _on_risk_action("RISK_ESCALATE_REDUCED", ...) | Risk level → 2 |
| INCIDENT | AUTH_FREEZE | Authorization | _on_auth_action("AUTH_FREEZE", ...) | Auth → FROZEN |
| INCIDENT | RISK_ESCALATE_DEFENSIVE | RiskGovernor | _on_risk_action("RISK_ESCALATE_DEFENSIVE", ...) | Risk level → 3 |
| CRITICAL_INCIDENT | AUTH_FREEZE | Authorization | _on_auth_action("AUTH_FREEZE", ...) | Auth → FROZEN |
| CRITICAL_INCIDENT | RISK_CIRCUIT_BREAKER | RiskGovernor | _on_risk_action("RISK_CIRCUIT_BREAKER", ...) | Risk level → 4 |
| CRITICAL_INCIDENT | TRADING_FREEZE | Both | _on_risk_action(...) + _on_auth_action(...) | Auth FROZEN + Risk CB |

### Cascading Logic Diagram 級聯邏輯圖

```
ReconciliationEngine.reconcile()
│
├─ 發現 MISMATCH_MAJOR (3+ discrepancies)
│  └─ incident_callback("reconciliation_mismatch", report)
│     └─ GovernanceHub._on_reconciliation_mismatch()
│        └─ IncidentPolicy.process_event(event)
│           │
│           ├─ Event: severity=INCIDENT, reason_code="state_conflict"
│           ├─ Actions: AUTH_FREEZE, RISK_ESCALATE_DEFENSIVE, MANUAL_REVIEW
│           │
│           ├─ _execute_action(AUTH_FREEZE, ...)
│           │  └─ on_auth_action("AUTH_FREEZE", context)
│           │     └─ GovernanceHub._on_auth_frozen()
│           │        └─ AuthorizationStateMachine.freeze()
│           │           ├─ Auth 狀態 → FROZEN
│           │           └─ audit_callback({"state": "FROZEN", ...})
│           │
│           ├─ _execute_action(RISK_ESCALATE_DEFENSIVE, ...)
│           │  └─ on_risk_action("RISK_ESCALATE_DEFENSIVE", context)
│           │     └─ RiskGovernorStateMachine.escalate(level=3)
│           │        ├─ Risk 等級 → 3 (DEFENSIVE)
│           │        └─ audit_callback({"level": 3, ...})
│           │
│           └─ _execute_action(MANUAL_REVIEW, ...)
│              └─ logger.warning("MANUAL_REVIEW required")
│
├─ 發現 MISMATCH_FATAL (1+ critical discrepancies)
│  └─ incident_callback("reconciliation_mismatch", report)
│     └─ GovernanceHub._on_reconciliation_mismatch()
│        └─ IncidentPolicy.process_event(event)
│           │
│           ├─ Event: severity=CRITICAL_INCIDENT
│           ├─ Actions: AUTH_FREEZE, RISK_CIRCUIT_BREAKER, TRADING_FREEZE, ...
│           │
│           ├─ _execute_action(AUTH_FREEZE, ...)
│           ├─ _execute_action(RISK_CIRCUIT_BREAKER, ...)  ← Risk level → 4
│           └─ _execute_action(TRADING_FREEZE, ...)        ← Auth FROZEN + Risk CB
│
└─ 對賬通過
   └─ incident_callback("reconciliation_pass", report)
      └─ IncidentPolicy.process_event(event)
         └─ Event: severity=NOTICE
            └─ Actions: RECORD_ONLY
```

### Integration Points 集成點設計

**1. IncidentPolicy 創建位置：paper_trading_routes.py**

```python
# 在 GOV_HUB 初始化後
from .incident_event_model import IncidentPolicy

INCIDENT_POLICY = IncidentPolicy(
    audit_callback=AUDIT_PIPELINE.make_callback("incident_policy"),
    on_auth_action=lambda action, ctx: _handle_incident_auth_action(action, ctx),
    on_risk_action=lambda action, ctx: _handle_incident_risk_action(action, ctx),
    on_operator_alert=lambda ctx: _handle_operator_alert(ctx),
)

# 註冊 IncidentPolicy 到 GOV_HUB
GOV_HUB.set_incident_policy(INCIDENT_POLICY)
```

**2. GovernanceHub 修改：添加 set_incident_policy() 方法**

```python
class GovernanceHub:
    def __init__(self, ...):
        self._incident_policy: Optional[Any] = None  # ← NEW
    
    def set_incident_policy(self, policy: Any) -> None:
        """Set the incident policy engine / 設置事故策略引擎"""
        with self._lock:
            self._incident_policy = policy
            logger.info("Incident policy set on GovernanceHub")
    
    def _on_reconciliation_mismatch(self, severity: str, details: dict) -> None:
        """... 現有代碼 ..."""
        # 新增：創建事件並傳遞給 IncidentPolicy
        if self._incident_policy:
            try:
                event = IncidentPolicy.from_reconciliation_report(details)
                self._incident_policy.process_event(event)
            except Exception as e:
                logger.error("Error processing reconciliation incident: %s", e)
```

**3. ReconciliationEngine 配置：incident_callback 連接**

```python
# governance_hub.py 的 _ensure_initialized() 中
incident_callback = self._make_incident_callback()
self._reconciliation_engine = ReconciliationEngine(
    config=ReconciliationConfig(),
    audit_callback=recon_callback,
    incident_callback=incident_callback,  # ← 已連接
)
```

### Incident Action Handlers 事故動作處理器

**paper_trading_routes.py 中添加：**

```python
def _handle_incident_auth_action(action: str, context: dict) -> None:
    """Handle incident-triggered auth actions / 處理事故觸發的授權動作"""
    logger.warning(
        "Incident auth action: %s for event %s",
        action, context.get("event_id")
    )
    
    try:
        if not GOV_HUB or not GOV_HUB.is_enabled():
            return
        
        with GOV_HUB._lock:
            auth_sm = GOV_HUB._authorization_sm
            if not auth_sm:
                return
            
            if action == "AUTH_FREEZE":
                effective_auths = auth_sm.get_effective()
                for auth in effective_auths:
                    auth_sm.freeze(
                        auth.authorization_id,
                        reason=f"Incident {context.get('incident_id')}: {action}"
                    )
                GOV_HUB._mode = GovernanceMode.FROZEN
                GOV_HUB._invalidate_auth_cache()
                
            elif action == "AUTH_RESTRICT":
                effective_auths = auth_sm.get_effective()
                for auth in effective_auths:
                    if auth.state.value == "ACTIVE":
                        auth_sm.restrict(
                            auth.authorization_id,
                            reason=f"Incident {context.get('incident_id')}: {action}"
                        )
                GOV_HUB._mode = GovernanceMode.RESTRICTED
                GOV_HUB._invalidate_auth_cache()
    
    except Exception as e:
        logger.error("Error handling incident auth action: %s", e)


def _handle_incident_risk_action(action: str, context: dict) -> None:
    """Handle incident-triggered risk actions / 處理事故觸發的風險動作"""
    logger.warning(
        "Incident risk action: %s for event %s",
        action, context.get("event_id")
    )
    
    try:
        if not GOV_HUB or not GOV_HUB.is_enabled():
            return
        
        with GOV_HUB._lock:
            risk_sm = GOV_HUB._risk_governor_sm
            if not risk_sm:
                return
            
            # 解析動作→風險等級映射
            level_map = {
                "RISK_ESCALATE_CAUTIOUS": 1,
                "RISK_ESCALATE_REDUCED": 2,
                "RISK_ESCALATE_DEFENSIVE": 3,
                "RISK_CIRCUIT_BREAKER": 4,
            }
            
            target_level = level_map.get(action)
            if target_level is not None:
                current_state = risk_sm.get_state()
                current_level = int(current_state.level)
                
                if target_level > current_level:
                    risk_sm.escalate(
                        target_level,
                        reason=f"Incident {context.get('incident_id')}: {action}"
                    )
    
    except Exception as e:
        logger.error("Error handling incident risk action: %s", e)


def _handle_operator_alert(context: dict) -> None:
    """Handle operator alerts / 處理運營商告警"""
    logger.warning(
        "Operator alert: Incident %s severity %s event %s",
        context.get("incident_id"),
        context.get("severity"),
        context.get("event_id"),
    )
    # 未來可連接到通知系統（郵件、Slack、Telegram 等）
```

### Event Examples 事件示例

**示例 1：對賬 MISMATCH_MAJOR → INCIDENT**

```python
# ReconciliationEngine 發現 3 個 discrepancies
report = {
    "overall_result": "MAJOR",
    "critical_count": 0,
    "discrepancy_count": 3,
    "details": [
        {"symbol": "BTCUSDT", "paper_qty": 1.0, "demo_qty": 0.95},
        {"symbol": "ETHUSDT", "paper_qty": 10.0, "demo_qty": 10.0},
        {"symbol": "BNBUSDT", "paper_pnl": 100, "demo_pnl": 50},
    ]
}

# incident_callback 被調用
incident_callback("reconciliation_mismatch", report)

# IncidentPolicy.from_reconciliation_report() 創建事件
event = Event(
    event_type="reconciliation_mismatch",
    severity=EventSeverity.INCIDENT,  # (3)
    source="reconciliation_engine",
    reason_code="state_conflict",
    reason_detail="Reconciliation: 3 discrepancies, 0 critical",
)

# process_event() 執行動作
actions = [
    "AUTH_FREEZE",               # 凍結授權
    "RISK_ESCALATE_DEFENSIVE",   # 風險升級到 DEFENSIVE
    "MANUAL_REVIEW",             # 標記為待人工審核
    "OPERATOR_ALERT",            # 運營商告警
]
```

**示例 2：對賬 MISMATCH_FATAL → CRITICAL_INCIDENT**

```python
# ReconciliationEngine 發現 1 個 critical discrepancy
report = {
    "overall_result": "FATAL",
    "critical_count": 1,
    "discrepancy_count": 2,
    "critical_details": [
        {"type": "missing_order", "order_id": "order:123", "symbol": "BTCUSDT"}
    ]
}

event = Event(
    event_type="reconciliation_mismatch",
    severity=EventSeverity.CRITICAL_INCIDENT,  # (4)
    source="reconciliation_engine",
    reason_code="state_conflict",
    reason_detail="Reconciliation: 2 discrepancies, 1 critical",
)

actions = [
    "AUTH_FREEZE",           # 立即凍結所有授權
    "RISK_CIRCUIT_BREAKER",  # Risk level → 4
    "TRADING_FREEZE",        # 同時執行 AUTH_FREEZE + RISK_CB
    "MANUAL_REVIEW",
    "OPERATOR_ALERT",
]

# 結果：Auth FROZEN + Risk CIRCUIT_BREAKER + 所有 Lease 撤銷
```

### Acceptance Criteria 驗收標準

- [ ] IncidentPolicy 在 paper_trading_routes 中創建
- [ ] GOV_HUB.set_incident_policy() 方法實現
- [ ] CRITICAL_INCIDENT → Auth FROZEN + Risk CIRCUIT_BREAKER + Lease revoke_all
- [ ] INCIDENT → Auth FROZEN + Risk DEFENSIVE
- [ ] NEAR_MISS → Auth RESTRICTED + Risk REDUCED
- [ ] 對賬 MISMATCH_MAJOR → 自動觸發 INCIDENT 級聯
- [ ] 對賬 MISMATCH_FATAL → 自動觸發 CRITICAL_INCIDENT 級聯
- [ ] 級聯審計記錄完整（events, incidents, actions）
- [ ] IT-07、IT-09 集成測試通過

---

## Integration Timeline 整合時序

### Initialization Order 初始化順序

```
main.py 啟動
│
├─ 步驟 1: 導入路由模組
│  ├─ paper_trading_routes.py 執行
│  │  ├─ PAPER_STORE = PaperStateStore(...)
│  │  ├─ RISK_MANAGER = RiskManager()
│  │  ├─ ENGINE = PaperTradingEngine(...)
│  │  ├─ AUDIT_PIPELINE = AuditPipeline(...)  ← T1.04 (NEW)
│  │  ├─ GOV_HUB = GovernanceHub(...)
│  │  ├─ GOV_HUB.set_audit_pipeline(AUDIT_PIPELINE)  ← T1.04 (NEW)
│  │  ├─ INCIDENT_POLICY = IncidentPolicy(...)  ← T1.05 (NEW)
│  │  ├─ GOV_HUB.set_incident_policy(INCIDENT_POLICY)  ← T1.05 (NEW)
│  │  ├─ ENGINE.set_governance_hub(GOV_HUB)
│  │  └─ RISK_MANAGER.set_governance_hub(GOV_HUB)
│  │
│  └─ phase2_strategy_routes.py 執行
│     ├─ KLINE_MANAGER = KlineManager(...)
│     ├─ INDICATOR_ENGINE = IndicatorEngine(...)
│     ├─ SIGNAL_ENGINE = SignalEngine(...)
│     ├─ ORCHESTRATOR = StrategyOrchestrator(...)
│     ├─ PAPER_ENGINE = ENGINE  (導入自 paper_trading_routes)
│     ├─ PIPELINE_BRIDGE = PipelineBridge(...)
│     ├─ PIPELINE_BRIDGE.set_governance_hub(GOV_HUB)  ← T1.01 (NEW)
│     └─ ... 其他配置 ...
│
├─ 步驟 2: FastAPI 應用啟動（main.py）
│  ├─ app = FastAPI()
│  ├─ app.include_router(paper_router)  ← READY (GOV_HUB, INCIDENT_POLICY)
│  ├─ app.include_router(phase2_router)  ← READY (PIPELINE_BRIDGE + GOV_HUB)
│  └─ uvicorn.run(app)
│
└─ 步驟 3: 首個請求進入（paper/session/start）
   └─ ENGINE.start_session()
      └─ GOV_HUB._ensure_initialized()  ← 延遲初始化
         ├─ AuthorizationStateMachine(audit_callback=...)
         ├─ RiskGovernorStateMachine(audit_callback=...)
         ├─ DecisionLeaseStateMachine(audit_callback=...)
         └─ ReconciliationEngine(audit_callback=..., incident_callback=...)
            └─ incident_callback 已連接到 _on_reconciliation_mismatch()
```

### Hot Path Optimization 熱路徑優化

**是_authorized() 調用（每個 tick/intent）：**

```
is_authorized() [hot path]
├─ 檢查 is_enabled + mode (無鎖)
├─ 檢查快取 TTL 100ms (無鎖)
├─ 如未初始化，調用 _ensure_initialized() [延遲初始化]
├─ 獲取 RLock
├─ 檢查 Authorization SM 狀態
├─ 釋放鎖
└─ 返回結果
```

**快取設計：**
- 快取TTL：100ms（調整空間：50-200ms）
- 快取失效點：_on_risk_escalation(), _on_auth_frozen(), _on_auth_action()
- 目標：減少 lock 爭搶，同時保證狀態一致性（100ms 內可容忍）

---

## Monitoring & Observability 監控與可觀測性

### Audit Metrics 審計指標

| 指標 | 來源 | 記錄頻度 | 用途 |
|------|------|---------|------|
| auth_state_change | GovernanceHub.is_authorized() | 狀態變更時 | 授權狀態跟蹤 |
| risk_level_change | GovernanceHub._on_risk_escalation() | 升級時 | 風險升級監控 |
| lease_acquired | GovernanceHub.acquire_lease() | 每個意圖 | Lease 生命週期 |
| incident_triggered | IncidentPolicy.process_event() | 事件時 | 事故事件統計 |
| reconciliation_result | ReconciliationEngine.reconcile() | 對賬結束 | 對賬結果 |

### Query Examples 查詢示例

**用 AuditFileReader 查詢（T1.04）：**

```python
reader = AUDIT_PIPELINE.get_reader()

# 查詢授權狀態變更
auth_events = reader.query(
    time_start_ms=start_ms,
    time_end_ms=end_ms,
    event_type="state_change",
    source="authorization"
)

# 查詢風險升級事件
risk_events = reader.query(
    event_type="level_change",
    source="risk_governor"
)

# 查詢特定 Lease
lease_events = reader.query(
    keywords=["lease_id:lease:123456"]
)
```

**用 IncidentPolicy 查詢（T1.05）：**

```python
# 獲取未解決的事故
open_incidents = INCIDENT_POLICY.get_open_incidents()

# 獲取最近事件
recent_events = INCIDENT_POLICY.get_recent_events(count=50)

# 獲取 CRITICAL_INCIDENT 及以上
critical_events = INCIDENT_POLICY.get_events_by_severity(
    EventSeverity.CRITICAL_INCIDENT
)

# 獲取統計信息
stats = INCIDENT_POLICY.get_stats()
# {
#   "events_processed": 1234,
#   "incidents_created": 42,
#   "critical_incidents": 3,
#   "open_incidents": 1,
#   ...
# }
```

---

## Risks & Mitigations 風險與緩解

| 風險 | 影響 | 可能性 | 緩解措施 |
|------|------|--------|---------|
| T1.01 Import 失敗 | PIPELINE_BRIDGE 無治理檢查 | LOW | try-except，記錄警告，降級為警告 |
| T1.04 AuditPipeline 創建失敗 | 審計記錄無磁盤持久化 | MEDIUM | 提供構造降級（在記憶體），記錄錯誤 |
| T1.04 磁盤滿 | 寫入失敗，審計丟失 | LOW | 監控磁盤空間，設置最大文件數限制 |
| T1.05 IncidentPolicy 回調異常 | 級聯不完整 | MEDIUM | try-except 在 _execute_action()，記錄錯誤，仍執行其他動作 |
| T1.05 遞迴級聯（Incident→Auth freeze→Risk escalation→Incident） | 無限遞迴 | LOW | 檢查 parent_event_id，限制級聯深度 |
| 快取一致性問題（100ms TTL） | 使用過期的授權狀態 | LOW | TTL 時間短，且失效點覆蓋，最差延遲 100ms |
| 線程安全（RLock） | 死鎖 | LOW | 使用 RLock 允許重入，避免嵌套 acquire_lease() 在同線程 |

---

## Summary 總結

| 任務 | 狀態 | 關鍵決策 | 驗收依賴 |
|------|------|---------|---------|
| T1.01 | ✅ 完成 | 直接 import（無延遲注入） | E1b code change + E4 測試 |
| T1.04 | ✅ 完成 | AuditPipeline 在 paper_trading_routes 創建 | E1b 實現 + 持久化驗證 |
| T1.05 | ✅ 完成 | IncidentPolicy 回調直連 GovernanceHub | E1b 實現 + 級聯測試 |

**三項架構設計已通過驗證，可進行 code implementation（T1.01、T1.04、T1.05 的代碼實現階段）。**

---

*FA Architecture Report for Phase 1 Governance Wiring  
由架構師 (via Cowork FA) 於 2026-03-30 產出  
涵蓋任務：T1.01、T1.04、T1.05*
