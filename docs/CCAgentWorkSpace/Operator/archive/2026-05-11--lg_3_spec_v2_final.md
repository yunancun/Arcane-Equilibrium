# LG-3 Supervised-Live State Machine Spec v2 Final

Date: 2026-05-11
Owner: PA
Wave: Sprint N+1 Wave 2.2 (Spec Phase v2 — incorporate Wave 2.1.5 三方 review caveats)
Status: PA spec v2 final — ready for PM Wave 2.4 IMPL dispatch
Predecessor: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md` (1221 行)
Reviewer inputs (Wave 2.1.5):
- QC: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--lg3_spec_qc_review.md` — APPROVE WITH 6 STATISTICAL CAVEATS + 4 SHOULD = 10 條
- MIT: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-11--lg3_spec_mit_review.md` — APPROVE WITH 6 MUST + 3 SHOULD = 9 條
- BB: `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-11--lg3_spec_bb_review.md` — APPROVE WITH 6 + 1 BYBIT CAVEATS = 7 條

**Total caveats incorporated**: 26 (10 QC + 9 MIT + 7 BB)。0 REQUEST CHANGES。0 design redesign。

---

## v2 變更摘要（與 v1 對比）

- 新章節 6 個：§2.2A audit→state inverse map（17 action × 7 state, MIT MUST-6）、§3.6 Renew clarification（BB caveat 3）、§3.7 Approval Gate 7 KYC cross-ref（BB caveat 5）、§4.4A Non-training surface invariant（MIT MUST-5）、§6.6 Kill rate-limit pattern（BB caveat 2+4）、§7.6 WS reconnect 不觸 SM（BB caveat 1）、§7.4A EarnedTrust × Bybit KYC table（BB caveat 5）、§15.4 Mainnet pre-flight checklist（BB caveat 6）、§16 Caveat Resolution Table。
- 新章節 9 個 sub-section / 內聯 amendment：§3.5 immutability declaration（QC CAVEAT 7）、§4.1 Guard A part 2（MIT MUST-1）、§4.1 ADD CONSTRAINT block（MIT MUST-2）、§4.1 repair_migration_checksum SOP（MIT MUST-4）、§4.1 SHOULD column（MIT SHOULD-2/3）、§5.1 P1 per-intent vs aggregate（QC CAVEAT 6）、§5.1 u32 saturating（QC CAVEAT 5）、§5.3 補 TC-13~TC-19（QC CAVEAT 1/2/3/4/5/6）、§10 [59] baseline KS test（MIT SHOULD-1）、§10 [60] 30d 1% violation budget gate（QC CAVEAT 9）、§11.9 Kill rate-limit competition（BB caveat 補風險）、§13.4 Linux PG dry-run dispatch SOP（MIT MUST-3）、§13.4 Wave 2.4 pre-flight changelog check（BB caveat 7）、§6.5A GUI Approval response panel（QC CAVEAT 10）。
- v1 → v2 行數估：1221 行 → ~1700 行（< 2000 hard cap，符合 §九 規範）。

---

## 0. Scope & Non-Scope (unchanged from v1)

### Scope (本 spec 涵蓋)

1. 7-state SupervisedLiveStateMachine 集中表達（Rust SoT + Python mirror）
2. State transition table + invariants + fail-closed semantic
3. External observer reconcile loop（5 SoT 對賬 30s）
4. Approval RPC schema + 端點 + Pydantic models
5. Audit mirror schema（V094_supervised_live_audit）+ dual-write outbox
6. session_override `compute_effective_limits` `min`-only enforcement
7. GUI kill button + 5s countdown confirm modal
8. SM-04 / Decision Lease / W-AUDIT-9 graduated canary / EarnedTrust T0-T3 / AlphaSurface 五處整合接口
9. LG3-T1..T7 IMPL-ready task breakdown
10. QC + BB + MIT review checklist
11. Healthcheck `[59]` `[60]` `[61]` 新增

### Non-Scope (本 spec 不涵蓋)

- ❌ R-2 Strategist scope reframe（→ W-AUDIT-8e DEFER N+4+）
- ❌ R-3 Hypothesis Pipeline（→ W-AUDIT-8f DEFER N+5+）
- ❌ R-4 Per-alpha-source Live Promotion Gate（→ W-AUDIT-8g DEFER N+7+，本 spec 為 `alpha_source_id` 留 NULLable 接口而已）
- ❌ True live mainnet 訂單路徑 IMPL（仍為 supervised live，LiveDemo + 「mainnet pending operator final sign-off」 兩態，**不啟動真實 mainnet 流量**）
- ❌ Per-tier (T0-T3) authorization TTL refactor（既有 EarnedTrust 不動）
- ❌ Decision Lease 5-state lifecycle SoT 改動（learning.lease_transitions V054 既有，spec 只「接入」）
- ❌ Feature code IMPL（PA spec 只用接口 sketch，IMPL 留 Wave 2.4）

---

## 1. State Diagram (7-state) — unchanged from v1

```
              ┌─────────────────────────────────────────┐
              │            DRAFT                         │
              │  Python-only state; operator preparing  │
              │  request payload; no Rust SM row yet.   │
              └────────────────┬────────────────────────┘
                                │ POST /api/v1/live/supervised/request
                                │   (validates schema; rejects mal-formed)
                                ▼
              ┌─────────────────────────────────────────┐
              │            REGISTERED                    │
              │  Request row in DB; awaiting operator   │
              │  review action. NO live actions yet.    │
              └────────────────┬────────────────────────┘
                                │ POST /api/v1/live/supervised/approve
                                │   (operator role + live_reserved checked)
                                │   (5-gate live boundary checked)
                                ▼
              ┌─────────────────────────────────────────┐
              │      ACTIVE_PRE_AUTH                     │
              │  Operator approved; Python written      │
              │  authorization.json; Rust LiveAuthWatch │
              │  not yet observed file.                 │
              └────────────────┬────────────────────────┘
                                │ LiveAuthWatcher detects file +
                                │ verify HMAC + env_allowed match
                                ▼
              ┌─────────────────────────────────────────┐
              │       ACTIVE_AUTHED                      │
              │  Rust authorized + Live pipeline spawn  │
              │  but no Decision Lease bound yet.       │
              │  shadow_mode if W-AUDIT-9 Stage<3.      │
              └────────────────┬────────────────────────┘
                                │ Strategy emits intent +
                                │ GovernanceHub.acquire_lease() granted
                                │ (W-AUDIT-9 Stage≥3 only)
                                ▼
              ┌─────────────────────────────────────────┐
              │      ACTIVE_TRADING                      │
              │  ≥1 lease bound; live orders may dispatch│
              │  Effective limits = min(P1, override,    │
              │                          strategy_cfg).  │
              └────────┬───────────────────────┬────────┘
                       │                       │
        Drawdown auto │                       │ Lease released or
        revoke (Rust │                       │ session_max_duration hit
        side)         ▼                       ▼
              ┌──────────────┐         ┌────────────────────────────┐
              │ DRAWDOWN_    │         │       CLOSED                │
              │  PAUSE       │         │  Normal session end, kill   │
              │ (transitional│         │  switch, or drawdown halt.  │
              │  → CLOSED)   ├────────►│  TERMINAL state — no further│
              └──────────────┘         │  transition.                │
                                       └────────────────────────────┘

非法 transition (e.g. DRAFT→ACTIVE_TRADING 跳級) → fail-closed REJECT。
從任一非 TERMINAL state 觸發 kill switch → 強制 CLOSED + reason="kill_switch_*"。
```

### 1.1 State Invariants (每 state 入境條件) — unchanged from v1

| State | Invariants (進入時必滿足) |
|---|---|
| DRAFT | Python 側 in-memory request 物件 valid；無 DB row |
| REGISTERED | DB row 存在；`request.scope` 已 ASCII canonical sort；`request.expires_at` > NOW；無 authorization.json 寫入 |
| ACTIVE_PRE_AUTH | Approval row inserted；operator_id verified；authorization.json HMAC-signed + 寫盤；無 Rust SM row yet |
| ACTIVE_AUTHED | Rust LiveAuthWatcher `Verified` state；engine env_allowed match；engine fresh spawn 或繼續 run；無 active lease |
| ACTIVE_TRADING | ≥1 active lease，lease_id 在 `learning.lease_transitions` 有 `acquired` row 未 `released` |
| DRAWDOWN_PAUSE | drawdown_revoke `should_revoke()` Some；authorization.json 已被 Rust `revoke_live_authorization()` 刪除；轉移到 CLOSED 中 |
| CLOSED | TERMINAL；authorization.json absent OR expired；所有 active lease 已 release；session_override 已清；audit row `action="session_closed"` 寫入 |

### 1.2 Legal Transition Table (v2 amendment — kill_api Side Effects 改)

| Src State | Event | Dst State | Preconditions | Side Effects |
|---|---|---|---|---|
| (none) | `request_submitted` | DRAFT | Python-only; schema valid | 0 DB; 0 audit |
| DRAFT | `request_registered` | REGISTERED | scope canonicalized; expires_at > NOW + 5min | INSERT `supervised_live_audit` action=`request_registered` |
| REGISTERED | `approval_granted` | ACTIVE_PRE_AUTH | operator role auth; `live_reserved` mode; 5-gate boundary; W-AUDIT-9 Stage 知會（不阻 Stage<3） | INSERT audit action=`approval_granted`; call `_write_signed_live_authorization()` |
| REGISTERED | `approval_rejected` | CLOSED | 任一驗證 fail | INSERT audit action=`approval_rejected` + `reason_codes` |
| REGISTERED | `request_expired` | CLOSED | `expires_at < NOW` | INSERT audit action=`expired_pre_auth` |
| ACTIVE_PRE_AUTH | `auth_file_observed` | ACTIVE_AUTHED | LiveAuthWatcher Verified state 觀察到 file + HMAC + env_allowed match | INSERT audit action=`auth_file_observed` |
| ACTIVE_PRE_AUTH | `auth_file_invalid` | CLOSED | LiveAuthWatcher reports any AuthError variant | INSERT audit action=`auth_file_invalid` + reason_codes |
| ACTIVE_AUTHED | `lease_acquired` | ACTIVE_TRADING | GovernanceHub.acquire_lease Ok；W-AUDIT-9 Stage ≥3 (per AMD §5.4.1) | INSERT audit action=`lease_acquired` + `decision_lease_id` |
| ACTIVE_AUTHED | `auth_recheck_fail` | CLOSED | main.rs 5-min re-verify fail | INSERT audit action=`auth_recheck_fail` + reason_codes |
| ACTIVE_TRADING | `lease_released` | ACTIVE_AUTHED | last lease released（still authorized） | INSERT audit action=`lease_released` |
| ACTIVE_TRADING | `drawdown_breach` | DRAWDOWN_PAUSE | drawdown_revoke.should_revoke Some | INSERT audit action=`drawdown_breach`; call `revoke_live_authorization` |
| (any non-TERMINAL) | `kill_api` | CLOSED | operator-initiated POST /api/v1/live/supervised/kill | **v2 amendment: 順序 = cancel-all THEN close-position THEN revoke**；per §6.3 + §6.6 sequence；INSERT audit action=`kill_api` + 1 audit row per affected sub-state |
| (any non-TERMINAL) | `kill_ipc` | CLOSED | IPC `trigger_kill_switch` (Rust-local cancel) | 同 kill_api 順序；INSERT audit action=`kill_ipc` + 1 audit row per affected sub-state |
| (any non-TERMINAL) | `session_max_duration` | CLOSED | `scope.max_duration_minutes` 倒計時到期 | INSERT audit action=`session_max_duration` |
| (any non-TERMINAL) | `reconcile_force_close` | CLOSED | external observer 對賬發現 5 SoT disagree | INSERT audit action=`reconcile_force_close` + reason_codes=`['split_brain_detected']` |
| DRAWDOWN_PAUSE | `transitional_close` | CLOSED | revoke 完成 + leases revoked | INSERT audit action=`drawdown_close_complete` |

### 1.3 Illegal Transition Handling — unchanged from v1

```rust
fn try_transition(&mut self, event: SmEvent) -> Result<SmState, IllegalTransitionError> {
    let key = (self.state, event.kind());
    let next = LEGAL_TRANSITIONS.get(&key)
        .ok_or_else(|| IllegalTransitionError {
            src: self.state,
            event: event.kind(),
            session_id: self.session_id.clone(),
        })?;

    // Write audit row BEFORE state mutation (outbox-style; see §4.3)
    self.audit_writer.queue(AuditRow {
        action: "illegal_transition_attempted",
        reason_codes: vec![format!("from_{}_event_{}", self.state, event.kind())],
        ..AuditRow::default()
    });

    // fail-closed: stay in current state; do NOT advance
    Err(IllegalTransitionError { ... })
}
```

非法 transition 嘗試 → 留在當前 state + audit row + log ERROR；不 crash engine。

---

## 2. External Observer Reconcile Loop

### 2.1 5 SoT 清單 (unchanged from v1)

| # | SoT | 物件 | 讀取方式 |
|---|---|---|---|
| 1 | Rust SM | `Arc<RwLock<SupervisedLiveSm>>` in-process | 直讀 |
| 2 | Python SM mirror | `supervised_live_state.py` in-memory + JSON disk persistence | 直讀 |
| 3 | `authorization.json` | `$OPENCLAW_SECRETS_DIR/live/authorization.json` | LiveAuthWatcher 既有路徑 |
| 4 | `learning.lease_transitions` (V054) | PG query 30d window；`WHERE session_id = $1 AND released_at IS NULL` | sqlx |
| 5 | `learning.supervised_live_audit` (V094 new) | PG query；`SELECT MAX(action) FROM ... WHERE session_id = $1` | sqlx |

### 2.2 對賬規則 (v2 amendment: 新增 inverse map cross-ref)

每 30s reconcile loop 計算 4 個 projected state，比對 4 種來源是否 agree：

```
projected_from_rust_sm     = Rust SM 當前 state
projected_from_python_sm   = Python SM mirror 當前 state
projected_from_auth_file   = if exists+valid+not_expired → ACTIVE_AUTHED-or-later
                              else → CLOSED-or-pre-auth
projected_from_lease_table = if ∃ open lease for session_id → ACTIVE_TRADING
                              else if last audit action ∈ {auth_file_observed, lease_released} → ACTIVE_AUTHED
                              else → use audit cursor
projected_from_audit_table = audit row last `action` 對應 state (per §2.2A inverse map)
```

**SoT 真值權威 = `learning.supervised_live_audit` (#5)**。其餘 4 個為 derived view。

### 2.2A audit `action` → projected state 反向映射表（MIT MUST-6 ★★★）

> **MIT pushback 接納**：5 SoT 對賬必有明文 inverse map，否則 IMPL 階段 Rust reconciler + Python mirror 兩端對 「last audit action → 預期 state」解讀可能不一致 = split-brain epidemic 風險。

| audit `action` | projected_state | 備註 |
|---|---|---|
| `request_registered` | REGISTERED | 初始化態，無 session_id 也允許 |
| `approval_granted` | ACTIVE_PRE_AUTH | authorization.json 已 write |
| `approval_rejected` | CLOSED | 直接 fail-closed |
| `expired_pre_auth` | CLOSED | TTL 過期 |
| `auth_file_observed` | ACTIVE_AUTHED | LiveAuthWatcher Verified |
| `auth_file_invalid` | CLOSED | HMAC fail / env_allowed mismatch |
| `lease_acquired` | ACTIVE_TRADING | 首筆 lease bound |
| `lease_released` | ACTIVE_AUTHED | 仍 authorized，但無 lease |
| `auth_recheck_fail` | CLOSED | 5min re-verify fail |
| `drawdown_breach` | DRAWDOWN_PAUSE | revoke 進行中 |
| `drawdown_close_complete` | CLOSED | DRAWDOWN_PAUSE 結束 |
| `kill_api` | CLOSED | operator API kill |
| `kill_ipc` | CLOSED | IPC kill 觸發 |
| `session_max_duration` | CLOSED | TTL 自然到期 |
| `reconcile_force_close` | CLOSED | 對賬強推 |
| `illegal_transition_attempted` | **(stay at src state, NOT projected_state)** | 不變 state；audit 僅 forensic |
| `session_closed` | CLOSED | normal close（synonym） |

**Rust 端 implementation hint**（reconciler.rs）：

```rust
fn audit_action_to_projected_state(action: &str) -> Option<SmState> {
    match action {
        "request_registered" => Some(SmState::Registered),
        "approval_granted" => Some(SmState::ActivePreAuth),
        "approval_rejected" | "expired_pre_auth" | "auth_file_invalid"
            | "auth_recheck_fail" | "drawdown_close_complete"
            | "kill_api" | "kill_ipc" | "session_max_duration"
            | "reconcile_force_close" | "session_closed" => Some(SmState::Closed),
        "auth_file_observed" | "lease_released" => Some(SmState::ActiveAuthed),
        "lease_acquired" => Some(SmState::ActiveTrading),
        "drawdown_breach" => Some(SmState::DrawdownPause),
        "illegal_transition_attempted" => None,  // 不更新 state
        _ => None,  // unknown action 走 fail-closed 路徑（reconcile WARN）
    }
}
```

Python mirror `supervised_live_state.py` 必 1:1 對應同一 dict（IMPL phase E2 check 等價性）。

### 2.3 Disagree 處理 — unchanged from v1

任 4 個 derived view 與 #5 audit 表 disagree → **強制 reconcile_force_close transition**：

1. INSERT audit row `action="reconcile_force_close"`、`reason_codes=['rust_sm_drift'|'python_sm_drift'|'auth_file_drift'|'lease_drift']`
2. Rust SM 強推到 CLOSED state
3. Python SM mirror 強推到 CLOSED
4. 若 authorization.json 仍存在 → 呼叫 `revoke_live_authorization()`
5. 所有 active lease release（per session_id）
6. session_override 清空
7. log ERROR + healthcheck `[61]` flag 警告

### 2.4 Reconcile Loop Placement — unchanged from v1

- **位置**：Rust async task in `rust/openclaw_engine/src/supervised_live_sm/reconciler.rs`
- **interval**：30s（不 hot path）
- **lifecycle**：engine boot 後 spawn；engine shutdown 透過 `CancellationToken` 取消
- **leader election**：本地 process-wide singleton
- **read-only on 4 derived sources**：reconciler 不直接寫 SM；它只觀察 disagree 並透過 `try_transition(SmEvent::ReconcileForceClose)` 走正常 SM path

### 2.5 No-False-Positive 條件 — unchanged from v1

連 2 cycle disagree 才升 force_close。1-cycle disagree → log WARN + 標 `reconcile_pending` flag；第 2 次 disagree 仍存在 → 升 ERROR + force_close。

---

## 3. Approval RPC Schema + 端點

### 3.1 Request Schema (LG-4 RFC 13 欄基礎 + 補欄位) — unchanged from v1

POST `/api/v1/live/supervised/approve`

```json
{
  "request_id": "req:<uuid_v4>",
  "engine_mode": "live",
  "scope": {
    "symbols": ["BTCUSDT"],
    "strategies": ["ma_crossover"],
    "max_duration_minutes": 60
  },
  "risk_limits": {
    "max_position_notional_usd": 50.0,
    "max_daily_loss_usd": 25.0,
    "max_orders": 10,
    "max_leverage": 1.0
  },
  "operator_id": "ncyu",
  "operator_reason": "supervised smoke test alpha_btc_lead_lag",
  "expires_at": "2026-05-11T20:00:00Z",
  "envelope": {
    "ts_ms": 1715000000000,
    "nonce": "<random_hex_16>",
    "signature": "<hmac_sha256_hex>"
  },
  "metadata": {
    "alpha_source_id": null,
    "cohort_ref": "w_audit_9_stage3_cohort_id"
  }
}
```

| 欄位 | 必填 | 驗證 |
|---|---|---|
| `request_id` | ✅ | `^req:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$` UUID v4 |
| `engine_mode` | ✅ | enum `"live"` only (LiveDemo 走 live code path 但本 RPC 視為 live) |
| `scope.symbols` | ✅ | non-empty list；每 symbol 在 `risk_config_live.toml` whitelist；ASCII sort |
| `scope.strategies` | ✅ | non-empty list；每 strategy 在 active strategies whitelist；ASCII sort |
| `scope.max_duration_minutes` | ✅ | int 1 ≤ N ≤ 480 (8 小時 cap) |
| `risk_limits.max_position_notional_usd` | ✅ | f64 0.0 < x ≤ P1 ceiling |
| `risk_limits.max_daily_loss_usd` | ✅ | f64 0.0 < x ≤ P1 ceiling |
| `risk_limits.max_orders` | ✅ | int 1 ≤ N ≤ P1 ceiling |
| `risk_limits.max_leverage` | ✅ | f64 1.0 ≤ x ≤ P1 ceiling |
| `operator_id` | ✅ | 對齊 `auth.verify_operator_identity()` |
| `operator_reason` | ✅ | TEXT 10 ≤ len ≤ 500 |
| `expires_at` | ✅ | RFC3339 UTC；NOW+5min ≤ expires_at ≤ NOW+8h |
| `envelope.*` | ✅ | per `auth.RequestEnvelope` HMAC-SHA256 |
| `metadata.alpha_source_id` | ❌ | NULL or `"alpha:<lowercase_snake>"` — R-4 forward-compat |
| `metadata.cohort_ref` | ❌ | 對齊 `governance.canary_cohort_log.cohort_id` (W-AUDIT-9 Stage ≥3) |

### 3.2 Response Schema — unchanged from v1

```json
{
  "session_id": "sess:<uuid_v4>",
  "state": "ACTIVE_PRE_AUTH",
  "approved_at_ts_ms": 1715000001000,
  "expires_at_ts_ms": 1715003601000,
  "authorization_path": "/path/to/authorization.json",
  "audit_row_id": 12345,
  "reason_codes": []
}
```

或 fail：

```json
{
  "session_id": null,
  "state": "REGISTERED",
  "rejected_at_ts_ms": 1715000001000,
  "reason_codes": ["scope_widens_live_authorization", "max_leverage_exceeds_p1_ceiling"],
  "audit_row_id": 12346
}
```

### 3.3 Validation Pipeline (v2 amendment: 加 Gate 7 Bybit KYC tier — BB caveat 5)

```python
@router.post("/api/v1/live/supervised/approve", response_model=ApprovalResponse)
async def approve(
    request: ApprovalRequest,
    actor: AuthenticatedActor = Depends(get_authenticated_actor),
) -> ApprovalResponse:
    # Gate 1: operator role + envelope signature
    auth.require_operator_role(actor)
    auth.verify_envelope_signature(request.envelope)
    auth.verify_operator_identity(request.envelope, actor)

    # Gate 2: live_reserved global mode
    if base.STORE.system_mode != "live_reserved":
        raise HTTPException(403, detail={"reason_codes": ["not_live_reserved_mode"]})

    # Gate 3: scope/limits validation
    reasons = validate_scope_and_limits(request)
    if reasons:
        await sm.transition(SmEvent.ApprovalRejected, reasons=reasons)
        raise HTTPException(400, detail={"reason_codes": reasons})

    # Gate 4: 5-gate live boundary check (existing CLAUDE.md §四)
    boundary = await check_live_boundary_5_gate(request.engine_mode)
    if not boundary.ok:
        await sm.transition(SmEvent.ApprovalRejected, reasons=boundary.failures)
        raise HTTPException(403, detail={"reason_codes": boundary.failures})

    # Gate 5: W-AUDIT-9 cohort awareness (informational; doesn't block Stage<3)
    cohort_warn = check_canary_cohort_consistency(request.metadata.cohort_ref)

    # Gate 6: EarnedTrust tier authority + scope tier-cap enforcement
    trust_state = earned_trust_engine.get_state_snapshot()
    tier_caps = TIER_CAPS.get(trust_state.current_tier)
    if not tier_caps.allows(request.scope):
        await sm.transition(SmEvent.ApprovalRejected,
                            reasons=["scope_exceeds_earned_trust_tier_cap"])
        raise HTTPException(403, detail={
            "reason_codes": ["scope_exceeds_earned_trust_tier_cap"]
        })

    # === v2 NEW Gate 7: Bybit KYC tier cross-ref (BB caveat 5) ===
    # per §3.7 + §7.4A: ensure Bybit account KYC tier ≥ required for EarnedTrust tier
    kyc_tier = await query_bybit_kyc_tier_cached()  # 5min cache; GET /v5/user/query-api permissions
    required_kyc = REQUIRED_KYC_FOR_TRUST_TIER[trust_state.current_tier]
    if kyc_tier < required_kyc:
        await sm.transition(SmEvent.ApprovalRejected,
                            reasons=["bybit_kyc_tier_below_trust_tier_requirement"])
        raise HTTPException(403, detail={
            "reason_codes": ["bybit_kyc_tier_below_trust_tier_requirement"]
        })

    # Gate 8: Transition REGISTERED → ACTIVE_PRE_AUTH (atomic + write authorization.json)
    session = await sm.transition(
        SmEvent.ApprovalGranted,
        request=request,
        actor=actor,
        cohort_warn=cohort_warn,
    )

    return ApprovalResponse(
        session_id=session.session_id,
        state=session.state,
        approved_at_ts_ms=session.approved_at_ts_ms,
        expires_at_ts_ms=session.expires_at_ts_ms,
        authorization_path=str(session.authorization_path),
        audit_row_id=session.audit_row_id,
        reason_codes=[],
    )
```

**v2 修訂 note**：原 v1 共 6 Gate，v2 加 Gate 7（Bybit KYC tier）→ 8 Gate sequence。Gate 6 從「W-AUDIT-9 cohort awareness」rename 為「EarnedTrust tier authority」（per BB caveat 5 整合 + §7.4A）；舊 Gate 6 cohort awareness 移到 Gate 5（informational, non-blocking）。Gate 8 = transition action（不算 validation）。

### 3.4 Mock + Real Path — unchanged from v1

- **Mock path**：unit test 用 `MockSm` 驗 8 個 gate 與 reason_codes 對應；無 PG / 無 file write
- **Real path**：production 用 `SupervisedLiveSmAdapter`（singleton 接 Rust IPC + Python SM mirror）
- **dependency injection**：route handler 接 `sm: SupervisedLiveSm = Depends(get_sm_singleton)`

### 3.5 反例 — scope 不能 widen + session_override immutability（QC CAVEAT 7 + 3 ★★）

> **v2 amendment (QC CAVEAT 7 / Option 1 採納)**：session_override **immutable for session lifetime**。GUI 修改 = kill + new approve。
>
> 理由：
> 1. 杜絕 mid-session attack surface（operator 在 reconcile cycle 邊界改 override 可能誤觸 reconcile_force_close）
> 2. 簡化 audit table 不需新增 `session_override_updated` enum
> 3. 簡化 reconciler inverse map（§2.2A 維持 17 action 不擴）
> 4. 對齊 EarnedTrust authorization TTL 設計（一次性鎖定）

如 authorization.json 已存在且 valid（如先前 session 啟動），同一 operator 不可透過 approve 增加 symbols / strategies / risk_limits / max_duration / max_leverage 任一 dimension；必須先 `kill` 既有 session → 再 approve 新 session。

驗證：`scope_widens_live_authorization` reason code（per Gate 3）— 對比 existing active session 的 scope，若新 request 任一 dimension 增量 → reject。

#### 3.5.1 Sequential kill+approve scope widening 處理（QC CAVEAT 3 ★★）

如 operator A 在 T=0 kill 既有 session，T+5s 重新 approve 一個更大 scope 的 session：

- spec 接受（CLOSED 後新 approve 不算 widening 舊 session）
- 但 audit forensic：v2 在 `learning.supervised_live_audit` 加 `payload` field `previous_session_id` (TEXT)、`previous_session_scope_diff` (JSONB)，紀錄連續 kill+approve 場景下前後 scope diff
- healthcheck `[60]` 加 sub-check：30d window 內若同一 operator 連續 kill+approve 序列中 scope diff 增量 > 50%（任一 dimension）→ WARN
- 不阻新 approve（operator 應有完整自主），但 audit trail 完整

### 3.6 Renew Flow Clarification（BB caveat 3 ★ new）

> LG-3 SM 不直接 IMPL renew。renew 走既有 `live_trust_routes.renew()` 端點（`_write_signed_live_authorization()` 同 path）。

SM 收到 LiveAuthWatcher 觀察的 `auth_file_observed` event 後 transition ACTIVE_PRE_AUTH → ACTIVE_AUTHED 正常（同 fresh approve 後路徑）。

LG3-T1 / T3 / T5 IMPL **不重複** renew logic。

若 operator 需 extend session：當前 active session 內**無法 renew TTL**（per §3.5 immutability）；需 kill → new approve（per spec §3.5 anti-pattern guard）。

E2 review 必查：LG3-T3 `approve` route + LG3-T5 `kill` route 不引入新 renew code path；新 renew code 應 push back 重用 既有 `live_trust_routes.renew()`。

### 3.7 Gate 7 — Bybit KYC tier cross-ref（BB caveat 5 ★★ new）

per §3.3 Gate 7 IMPL + §7.4A KYC × EarnedTrust 對照表，approve 流程必 cross-check operator 帳戶 Bybit KYC tier vs request 之 EarnedTrust tier。

**為什麼必要**：若 approval pass 但 Bybit 端 retCode=10005（PermissionDenied）→ live order create 後失敗 + 該 transition 仍 audit 寫入 + lease 浪費 + operator 困惑為何「pass approval 但無單成交」。

**caching**：`query_bybit_kyc_tier_cached()` 5min cache（GET /v5/user/query-api permissions），避免 approve 每次都打 Bybit。失效時間：cache miss / TTL expire / 手動清 cache。Cache miss + Bybit unreachable → fail-closed reject approve（reason: `bybit_kyc_check_unreachable`）。

**REQUIRED_KYC_FOR_TRUST_TIER 對應表**：見 §7.4A（cross-ref）。

---

## 4. Audit Mirror Schema (V094)

### 4.1 V094__supervised_live_audit.sql 草案 (v2 amendment — MIT MUST-1/2/3/4/5 + SHOULD-2/3 整合)

migration 號預留：V093 由 W-AUDIT-9 T4 既有；V094 為 LG-3 audit。

```sql
-- V094__supervised_live_audit.sql
-- Purpose: append-only audit mirror for SupervisedLiveStateMachine 7-state SM transitions.
-- Spec source: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md §4
--
-- ★ sqlx checksum SOP (per MIT MUST-4 / project_2026_05_02_p0_sqlx_hash_drift.md):
--   V094 file edit 後若 DB 已手動 `psql -f` apply 過：
--     bin/repair_migration_checksum --target V094  (preferred)
--   OR
--     unset OPENCLAW_AUTO_MIGRATE=1 重 apply 走 bootstrap_db.sh
--   對齊 V083 + V084 + V028-V034 既有教訓。
--
-- ★ Linux PG dry-run mandatory (per MIT MUST-3 / feedback_v_migration_pg_dry_run.md):
--   Mac mock pytest 不夠；必 Linux PG empirical query 驗 Guard A/B/C + idempotency。
--
-- ★ Non-training surface invariant (per MIT MUST-5):
--   supervised_live_audit 是 operator-bound control plane audit；
--   E3 安全審計 grep rule reject `SELECT ... FROM learning.supervised_live_audit`
--   出現在 program_code/**/ml/**, program_code/**/training/**,
--   program_code/**/learning/** 路徑 (除 healthcheck + reconciler 路徑外)。
--   對齊既有 CLAUDE.md §九 `replay.simulated_fills synthetic_replay` 防護 SOP。

CREATE SCHEMA IF NOT EXISTS learning;

-- Guard A part 1: validate base schema/columns prerequisites (V054 lease_transitions + V035 governance_audit_log).

DO $$
DECLARE
    v_v054_exists BOOLEAN;
    v_v035_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'lease_transitions'
    ) INTO v_v054_exists;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'governance_audit_log'
    ) INTO v_v035_exists;
    IF NOT v_v054_exists OR NOT v_v035_exists THEN
        RAISE EXCEPTION 'V094 Guard A part 1: V054 or V035 prerequisite missing';
    END IF;
END $$;

-- v2 amendment: Guard A part 2 — supervised_live_audit own 21-column allowlist check (per MIT MUST-1)
-- Mirror V054 §155-188 14-column required check pattern.

DO $$
DECLARE
    v_table_exists BOOLEAN;
    v_missing TEXT[] := ARRAY[]::TEXT[];
    v_required TEXT[] := ARRAY[
        'event_id', 'ts_ms', 'operator_id', 'session_id', 'request_id',
        'decision_lease_id', 'engine_mode', 'symbols', 'strategies', 'risk_limits',
        'action', 'src_state', 'dst_state', 'result', 'reason_codes',
        'alpha_source_id', 'cohort_ref', 'strategy_alpha_score', 'regime_tag',
        'payload', 'created_at'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'supervised_live_audit'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'learning'
                  AND table_name = 'supervised_live_audit'
                  AND column_name = v_col
            ) THEN
                v_missing := array_append(v_missing, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION 'V094 Guard A part 2: supervised_live_audit missing columns: %',
                array_to_string(v_missing, ', ');
        END IF;
    END IF;
END $$;

-- Main table

CREATE TABLE IF NOT EXISTS learning.supervised_live_audit (
    event_id              TEXT        NOT NULL,                       -- "evt:" + 16-hex random
    ts_ms                 BIGINT      NOT NULL,                       -- emit ms epoch
    operator_id           TEXT        NOT NULL,                       -- per RequestEnvelope.operator_id
    session_id            TEXT,                                       -- "sess:" + UUID v4; NULL only for REGISTERED/REJECTED
    request_id            TEXT        NOT NULL,                       -- "req:" + UUID v4 (per approval request)
    decision_lease_id     TEXT,                                       -- NULL until ACTIVE_TRADING; references lease_transitions.lease_id
    engine_mode           TEXT        NOT NULL,                       -- live / live_demo (CHECK constraint added below)
    symbols               TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    strategies            TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    risk_limits           JSONB       NOT NULL DEFAULT '{}'::JSONB,   -- {max_position_notional_usd, max_daily_loss_usd, max_orders, max_leverage}
    action                TEXT        NOT NULL,                       -- 17 enum values (CHECK added below)
    src_state             TEXT,                                       -- NULL for first row of session
    dst_state             TEXT        NOT NULL,
    result                TEXT        NOT NULL,                       -- ok / rejected / forced (CHECK added below)
    reason_codes          TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    alpha_source_id       TEXT,                                       -- R-4 forward-compat (W-AUDIT-8g); NULL until N+7+
    cohort_ref            TEXT,                                       -- W-AUDIT-9 cohort cross-ref; NULL until Stage>=3
    strategy_alpha_score  FLOAT8,                                     -- v2 NEW (MIT SHOULD-2): R-4 alpha routing forward-compat
    regime_tag            TEXT,                                       -- v2 NEW (MIT SHOULD-3): R-2 Strategist regime-aware forward-compat
    payload               JSONB       NOT NULL DEFAULT '{}'::JSONB,   -- arbitrary extra fields (incl. previous_session_id / submitted_override / effective_after_min per QC CAVEAT 3+10)
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, created_at)
);

-- v2 amendment: ADD CONSTRAINT block per MIT MUST-2 (mirror V054 line 245-317 pattern)
-- Idempotent: re-runs no RAISE.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_supervised_live_audit_action'
    ) THEN
        ALTER TABLE learning.supervised_live_audit
        ADD CONSTRAINT chk_supervised_live_audit_action CHECK (
            action IN (
                'request_registered',
                'approval_granted',
                'approval_rejected',
                'expired_pre_auth',
                'auth_file_observed',
                'auth_file_invalid',
                'lease_acquired',
                'lease_released',
                'auth_recheck_fail',
                'drawdown_breach',
                'drawdown_close_complete',
                'kill_api',
                'kill_ipc',
                'session_max_duration',
                'reconcile_force_close',
                'illegal_transition_attempted',
                'session_closed'
            )
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_supervised_live_audit_result'
    ) THEN
        ALTER TABLE learning.supervised_live_audit
        ADD CONSTRAINT chk_supervised_live_audit_result CHECK (
            result IN ('ok', 'rejected', 'forced')
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_supervised_live_audit_engine_mode'
    ) THEN
        ALTER TABLE learning.supervised_live_audit
        ADD CONSTRAINT chk_supervised_live_audit_engine_mode CHECK (
            engine_mode IN ('live', 'live_demo')
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_supervised_live_audit_ts_ms_positive'
    ) THEN
        ALTER TABLE learning.supervised_live_audit
        ADD CONSTRAINT chk_supervised_live_audit_ts_ms_positive CHECK (
            ts_ms > 0
        );
    END IF;
END $$;

-- TimescaleDB hypertable on created_at (7-day chunk; lower row volume than V054 lease_transitions justifies)

SELECT create_hypertable('learning.supervised_live_audit', 'created_at',
                         chunk_time_interval => INTERVAL '7 days',
                         if_not_exists => TRUE);

-- Guard C: indexes (idempotent)

CREATE INDEX IF NOT EXISTS idx_supervised_live_audit_session_id
    ON learning.supervised_live_audit (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supervised_live_audit_request_id
    ON learning.supervised_live_audit (request_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supervised_live_audit_action
    ON learning.supervised_live_audit (action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supervised_live_audit_operator
    ON learning.supervised_live_audit (operator_id, created_at DESC);
```

### 4.2 11 欄 RFC + 6+2 補欄位 (v2 amendment: +2 SHOULD column — MIT SHOULD-2/3)

LG-4 RFC 11 欄 + 本 spec 加 6 個（IMPL 必要 + R-4 forward-compat）+ v2 加 2 個（MIT SHOULD-2/3）：

| RFC 11 欄 | 本 spec 對應 |
|---|---|
| `event_id` | `event_id TEXT NOT NULL` |
| `ts` | `ts_ms BIGINT NOT NULL` (改 ms epoch 對齊 lease_transitions) |
| `operator_id` | `operator_id TEXT NOT NULL` |
| `request_id` | `request_id TEXT NOT NULL` |
| `decision_lease_id` | `decision_lease_id TEXT NULL` |
| `engine_mode` | `engine_mode TEXT NOT NULL CHECK (live/live_demo)` |
| `symbols` | `symbols TEXT[]` |
| `strategies` | `strategies TEXT[]` |
| `risk_limits` | `risk_limits JSONB` |
| `action` | `action TEXT NOT NULL CHECK (17 enum values)` |
| `result` | `result TEXT NOT NULL CHECK (ok/rejected/forced)` |
| `reason` | `reason_codes TEXT[]` (改 array 對齊 governance_audit_log V035 pattern) |

| 補欄位 | 理由 |
|---|---|
| `session_id` | 跨 row JOIN unique key |
| `src_state` | SM transition src state（debug + audit 完整性） |
| `dst_state` | SM transition dst state |
| `alpha_source_id` | R-4 forward-compat（NULLable，N+7+ W-AUDIT-8g backfill） |
| `cohort_ref` | W-AUDIT-9 cohort cross-ref（NULLable，Stage<3 為 NULL） |
| `payload` | JSONB 額外彈性欄（v2: 加 previous_session_id / submitted_override / effective_after_min subfield） |
| **`strategy_alpha_score`** (v2) | **MIT SHOULD-2**: Alpha-bearing strategy 評分 R-4 routing 決策依據；NULLable FLOAT8 |
| **`regime_tag`** (v2) | **MIT SHOULD-3**: R-2 Strategist reframe regime-aware live 配套；NULLable TEXT |

**Payload JSONB 結構穩定文檔（MIT A.1 §4.1 warning 緩解）**：

```json
{
  "previous_session_id": "sess:xxx",                              // QC CAVEAT 3: 連續 kill+approve 場景
  "previous_session_scope_diff": {"symbols_added": [...], ...},   // QC CAVEAT 3
  "submitted_override": {"max_position_notional_usd": 80.0},      // QC CAVEAT 10: GUI 顯示
  "effective_after_min": {"max_position_notional_usd": 50.0},     // QC CAVEAT 10
  "submitted_vs_effective_reason": "P1 caps",                     // QC CAVEAT 10
  "cohort_warn": "stage_below_3_informational"                    // §3.3 Gate 5
}
```

**SHOULD-stable**: 上述 6 個 subfield 為 v2 ship 期內 stable contract；任新 subfield 必同步更新本 doc。

### 4.3 Dual-Write Outbox 設計 — unchanged from v1

SM transition 與 audit 寫入必須**原子**（要嘛兩者都成功，要嘛兩者都不發生）。

**Outbox pattern**（mirror lease_transition_writer.rs §200-250）：

```
Rust SM transition flow:
  1. Lock self.state mutex
  2. Validate (src, event) in LEGAL_TRANSITIONS
  3. Compute next state + audit row
  4. Push audit row to mpsc::Sender<SupervisedLiveAuditMsg> (bounded 1024)
     - try_send; if full → log ERROR + drop transition (fail-closed; SM stays in src state)
  5. If audit send OK → mutate self.state to next
  6. Release lock
  7. Notify reconciler + Python SM mirror via IPC broadcast
```

Audit writer task (engine-side)：
- 同 lease_transition_writer.rs 既有 pattern
- Bridge thread: std::sync::mpsc → tokio::sync::mpsc
- Async writer task: batch 100 row 或 1s flush
- Fail-soft: PG unavailable → 保留 pending + log WARN（不阻 SM transition，但 PG 長期 down 應觸發 healthcheck `[61]` ERROR）

### 4.4 Audit Row 防丟保護 — unchanged from v1

- **Buffer 滿時**：mpsc::Sender::try_send Err → **fail-closed**（SM transition 不 advance；返回 IllegalTransitionError）+ 升 healthcheck `[61]` ERROR
- **PG 寫入失敗 retry**：writer task 重試 3 次；3 次都 fail → log ERROR + pending vec 保留（max 10k row）+ engine shutdown signal
- **engine 重啟**：pending vec 不持久化（accepted trade-off）

### 4.4A PG retry 用盡時 in-memory state recovery（QC CAVEAT 4 ★★ v2 new）

> **QC pushback 接納**：spec §4.4 寫了 engine shutdown，但未明示 in-memory state 處理。

**recovery 規則**：

1. PG retry 3 次都失敗 → audit writer task 升 ERROR、engine 開始 graceful shutdown（cancel_token fire）
2. engine shutdown 過程中，pending vec 內 audit row **永久遺失**（accepted trade-off，per CLAUDE.md §九 既有 `_REGISTER_IDEM_CACHE` 重啟丟 cache 同精神）
3. engine 重啟後，reconciler 第一個 cycle 觀察到 4 SoT 與 audit table（last row before fail）disagree → 連 2 cycle 確認 → `reconcile_force_close` 自動清空 session
4. operator GUI 顯示 「session ended unexpectedly」reason=`engine_crashed_pending_audit_lost`，operator 必須手動 acknowledge before 重 approve

**TC-16 cover scenario**: engine PG retry exhaustion + restart → reconcile_force_close → session_overrides[sid] removed → operator GUI 顯示 lost reason。

**Non-recovery action**：禁 IMPL 將 pending vec 寫盤再 replay（會破 audit append-only semantic + 引入 disk write hot path）。

### 4.4B Non-training surface invariant（MIT MUST-5 ★★★ v2 new）

> **MIT pushback 接納**：spec 已 §9.3 MIT review 預設 + §15.1 原則 7 描述 ML 不讀 supervised_live_audit；v2 加 schema-level safety 明文。

**Invariant 文字（嵌入 V094 SQL header 注釋 + 本 spec §4.1）**：

> `learning.supervised_live_audit` 是 operator-bound control plane audit；不是 ML training surface。
>
> **E3 安全審計 grep rule**：reject `SELECT ... FROM learning.supervised_live_audit` 出現在以下路徑 (除 healthcheck + reconciler + audit writer 路徑外)：
> - `program_code/**/ml/**`
> - `program_code/**/training/**`
> - `program_code/**/learning/**`
> - `program_code/**/scorer/**`
> - `program_code/**/linucb/**`
> - `program_code/**/mlde/**`
> - `program_code/**/dream/**`
> - `program_code/**/optuna/**`
> - `program_code/**/thompson/**`
>
> **允許 grep 路徑**：
> - `helper_scripts/db/passive_wait_healthcheck/**`
> - `program_code/healthcheck/**`
> - `rust/openclaw_engine/src/supervised_live_sm/reconciler.rs`
> - `rust/openclaw_engine/src/database/supervised_live_audit_writer.rs`

對齊既有 CLAUDE.md §九 `replay.simulated_fills synthetic_replay` non-training tier 防護 SOP。

E3 IMPL after Wave 2.4 Phase 3：補 `helper_scripts/audit/e3_grep_non_training_surface.sh` script per CLAUDE.md §九 W-AUDIT-3..7 pattern。

---

## 5. session_override `compute_effective_limits`

### 5.1 函數 Signature + 嚴格 min-only（v2 amendment: u32 saturating + P1 cap semantic 明示）

位置：`rust/openclaw_engine/src/intent_processor/mod.rs`（既有 `IntentProcessor::process_intent` 之內 / `apply_risk_envelope` 之前）。

```rust
/// Compute effective risk limit for an intent under supervised live session.
///
/// LG-3 spec §5: session_override 是 lease-bound dynamic risk_limits
/// 寫盤外 in-memory override，作用範圍是「該 session 期間下的所有 intent」。
/// Effective limit 必 `min` 而非 `max` — session_override 只能 tighten，不能 loosen。
///
/// === v2 amendment notes ===
/// - P1 cap semantic: per-intent cap, NOT aggregate (QC CAVEAT 6)
///   * 對應 RiskConfig `[limits].max_position_notional_usd` 是 per-intent
///   * 對 aggregate constraint（如 `correlated_exposure_max_pct`），see RiskConfig
///     `apply_risk_envelope` 既有 aggregate gate，不在 compute_effective_limits 範圍
/// - u32 max_orders use saturating math (QC CAVEAT 5):
///   * min3_u32 自然 saturating（u32 不可負）
///   * SessionOverrideLimits parsing 已 reject 0（per §5.4）
///   * P1 / strategy_config / session_override 不可超 u32::MAX → no overflow path
///   * v2 explicit assertion in fn body
/// - session_override immutable for session lifetime (QC CAVEAT 7 Option 1 採納，per §3.5)
///
/// Returns: 4 fields {max_position_notional_usd, max_daily_loss_usd, max_orders, max_leverage}
pub fn compute_effective_limits(
    p1_ceiling: &RiskLimits,           // RiskConfig.limits.* hot-reload SoT (per-intent cap)
    session_override: Option<&SessionOverrideLimits>,   // None = no override (degrades to P1)
    strategy_config: &StrategyOverride,  // RiskConfig.per_strategy[strat]
) -> EffectiveLimits {
    // v2 explicit u32 saturating assertion
    debug_assert!(p1_ceiling.max_orders < u32::MAX, "P1 max_orders must be < u32::MAX");
    debug_assert!(
        session_override.map(|so| so.max_orders < u32::MAX).unwrap_or(true),
        "session_override max_orders must be < u32::MAX"
    );

    EffectiveLimits {
        max_position_notional_usd: min3_f64(
            p1_ceiling.max_position_notional_usd,
            session_override.map(|so| so.max_position_notional_usd).unwrap_or(f64::INFINITY),
            strategy_config.max_position_notional_usd_override.unwrap_or(f64::INFINITY),
        ),
        max_daily_loss_usd: min3_f64(
            p1_ceiling.max_daily_loss_usd,
            session_override.map(|so| so.max_daily_loss_usd).unwrap_or(f64::INFINITY),
            strategy_config.max_daily_loss_usd_override.unwrap_or(f64::INFINITY),
        ),
        max_orders: min3_u32(
            p1_ceiling.max_orders,
            session_override.map(|so| so.max_orders).unwrap_or(u32::MAX),
            strategy_config.max_orders_override.unwrap_or(u32::MAX),
        ),
        max_leverage: min3_f64(
            p1_ceiling.max_leverage,
            session_override.map(|so| so.max_leverage).unwrap_or(f64::INFINITY),
            strategy_config.max_leverage_override.unwrap_or(f64::INFINITY),
        ),
    }
}

#[inline]
fn min3_f64(a: f64, b: f64, c: f64) -> f64 {
    a.min(b).min(c)
}

#[inline]
fn min3_u32(a: u32, b: u32, c: u32) -> u32 {
    a.min(b).min(c)
}
```

### 5.2 嚴格 `min`-only Formula — unchanged from v1

**核心不變式**：

```
effective = min(P1, session_override, strategy_config)
```

絕對禁止：

- ❌ `effective = max(...)` — session_override 不能放寬 P1
- ❌ `effective = if override > P1 then override else P1` — 變相 loosen
- ❌ `effective = avg(...)` — 任何平均化破不變式

**反例 grep 規則**（E2 review 必查 + sub-agent IMPL DONE 後 A3 review 必查）：

```bash
grep -nE '\bmax\(\s*p1|\bmax\(\s*session_override|max\(\s*self\.session_override' \
    /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/*.rs
# Expected: 0 matches.
```

### 5.3 不變式 Test Cases (v2 amendment: 加 TC-13~TC-19 — QC CAVEAT 1/2/3/4/5/6 + TC-19 split-brain)

| Test | Input | Expected Output |
|---|---|---|
| **TC-1 No override** | `session_override=None`, `p1=50`, `strategy=∞` | `effective=50` |
| **TC-2 Override < P1** | `session_override=30`, `p1=50`, `strategy=∞` | `effective=30` (tighten OK) |
| **TC-3 Override > P1 (attack)** | `session_override=80`, `p1=50`, `strategy=∞` | `effective=50` (must NOT widen) |
| **TC-4 Strategy < both** | `session_override=30`, `p1=50`, `strategy=20` | `effective=20` (strictest wins) |
| **TC-5 All equal** | `session_override=50`, `p1=50`, `strategy=50` | `effective=50` |
| **TC-6 Zero session_override** | `session_override=0`, `p1=50`, `strategy=∞` | `effective=0` (intent rejected) |
| **TC-7 NaN session_override** | `session_override=NaN` | reject at SessionOverrideLimits parsing |
| **TC-8 Negative session_override** | `session_override=-10` | reject at SessionOverrideLimits parsing |
| **TC-9 Float precision boundary** | `session_override=49.9999999`, `p1=50` | `effective=49.9999999` |
| **TC-10 Override only some fields** | `session_override.max_position=30, max_orders=None`, `p1.max_position=50, max_orders=100` | `effective.max_position=30, max_orders=100` |
| **TC-11 P1 hot-reload tighten** | initial `p1=50` → reload `p1=40`; session_override=45 | `effective=40` |
| **TC-12 P1 hot-reload widen** | initial `p1=50` → reload `p1=60`; session_override=45 | `effective=45` |
| **TC-13 Zero override at parse layer** (QC CAVEAT 1) | request `risk_limits.max_position_notional_usd=0` | reject at SessionOverrideLimits::from_request; `reason_codes=['invalid_session_override_max_position_zero']` |
| **TC-14 Lease re-acquire 不重設 override** (QC CAVEAT 2) | session in ACTIVE_TRADING, lease released → re-acquired | session_override unchanged (per §3.5 immutability); effective 仍套既有 override |
| **TC-15 Sequential kill+approve scope-widen audit** (QC CAVEAT 3) | session A kill, T+5s approve session B with 50% wider scope | accept; audit B row `payload.previous_session_id=A, previous_session_scope_diff={...}`; `[60]` 30d window 內若 >50% increase WARN |
| **TC-16 Outbox PG retry exhaustion + in-memory recovery** (QC CAVEAT 4) | engine PG retry 3 fail → cancel_token fire → restart → reconciler 連 2 cycle detect disagree → `reconcile_force_close` | session_overrides[sid] removed; GUI 顯示 reason=`engine_crashed_pending_audit_lost` |
| **TC-17 u32 saturating at boundary** (QC CAVEAT 5) | `session_override.max_orders=u32::MAX, p1.max_orders=10` | `effective.max_orders=10` (saturating, no overflow panic) |
| **TC-18 P1 per-intent vs aggregate semantic** (QC CAVEAT 6) | 3 strategy 各跑 effective=50 per-intent，aggregate exposure = 150 | accept individual intent (P1 per-intent); aggregate gate 由 既有 `correlated_exposure_max_pct` 在 `apply_risk_envelope` 後續 enforce |
| **TC-19 Split-brain reconcile clears override** | cycle 2 disagree → `reconcile_force_close` fire | session_overrides[sid] removed atomically; subsequent intent reject reason=`session_closed_by_reconcile` |

### 5.4 SessionOverrideLimits Parsing 防衛 — unchanged from v1

```rust
#[derive(Debug, Clone, Deserialize)]
pub struct SessionOverrideLimits {
    pub max_position_notional_usd: f64,
    pub max_daily_loss_usd: f64,
    pub max_orders: u32,
    pub max_leverage: f64,
}

impl SessionOverrideLimits {
    pub fn from_request(req: &ApprovalRequest) -> Result<Self, ParseError> {
        let limits = SessionOverrideLimits {
            max_position_notional_usd: req.risk_limits.max_position_notional_usd,
            max_daily_loss_usd: req.risk_limits.max_daily_loss_usd,
            max_orders: req.risk_limits.max_orders,
            max_leverage: req.risk_limits.max_leverage,
        };
        // Fail-closed: NaN / negative / extreme / zero reject (TC-7/8/13)
        if !limits.max_position_notional_usd.is_finite() || limits.max_position_notional_usd <= 0.0 {
            return Err(ParseError::InvalidLimit("max_position_notional_usd"));
        }
        if !limits.max_daily_loss_usd.is_finite() || limits.max_daily_loss_usd <= 0.0 {
            return Err(ParseError::InvalidLimit("max_daily_loss_usd"));
        }
        if limits.max_orders == 0 {
            return Err(ParseError::InvalidLimit("max_orders"));
        }
        if !limits.max_leverage.is_finite() || limits.max_leverage < 1.0 {
            return Err(ParseError::InvalidLimit("max_leverage"));
        }
        Ok(limits)
    }
}
```

### 5.5 Hot-Reload 行為 — unchanged from v1

- `compute_effective_limits` 每筆 intent 都 call（hot path 但 trivial cost ~10ns）
- `p1_ceiling` 來自 `Arc<ArcSwap<RiskConfig>>::load().limits` — hot reload 立即生效
- `session_override` 來自 `Arc<RwLock<HashMap<SessionId, SessionOverrideLimits>>>` — 由 SM ACTIVE_PRE_AUTH transition 寫入；CLOSED 寫 remove；**session lifetime 內不可中途修改**（per §3.5 immutability）
- `strategy_config` 來自 `Arc<ArcSwap<RiskConfig>>::load().per_strategy[strat]` — hot reload 生效

**不變式恆成立**（min 是 monotonic in tightening direction）。

---

## 6. GUI Kill Button

### 6.1 UI Element 位置 — unchanged from v1

在 13-tab Control Console 的 `live` tab 內，新增 sub-section "Supervised Live Sessions"。

| Element | 行為 |
|---|---|
| **Active sessions table** | 列當前 ACTIVE_PRE_AUTH / ACTIVE_AUTHED / ACTIVE_TRADING session（每 row：session_id, operator_id, strategies, symbols, started_at, remaining_min, state） |
| **Kill button per row** | 紅色按鈕；點擊 → 5s countdown modal |
| **Audit log feed** | 即時 SSE feed `/api/v1/live/supervised/audit/stream`；最新 50 條 audit row |
| **Approval form** | 新建 approval request；操 `/api/v1/live/supervised/approve` |

### 6.2 5s Countdown Modal (per W-AUDIT-7 F-system-mode-confirm precedent) — unchanged from v1

```
┌─────────────────────────────────────────────────────────┐
│        Kill Supervised Live Session — confirm           │
├─────────────────────────────────────────────────────────┤
│  Session: sess:abc12345-...                              │
│  Operator: ncyu                                          │
│  Strategies: [ma_crossover]                              │
│  Symbols: [BTCUSDT]                                      │
│  Active leases: 3                                        │
│  Active orders: 2 (will cancel)                          │
│  Open positions: 1 (will close at market)                │
│                                                          │
│  This action is IRREVERSIBLE.                            │
│  Confirm in:                                             │
│  ┌──────┐                                                │
│  │  5   │  countdown 5→0                                 │
│  └──────┘                                                │
│                                                          │
│  [CANCEL]                       [CONFIRM KILL] ←disabled │
│                                          (enabled @ 0s)  │
└─────────────────────────────────────────────────────────┘
```

行為：
1. Modal 打開 countdown=5；按鈕 disabled
2. 每秒 -1；按鈕仍 disabled
3. countdown=0 → 按鈕 enabled → 點擊送 `POST /api/v1/live/supervised/kill?session_id=...`
4. 任何時候 CANCEL → modal 關閉，無 IPC 動作
5. CONFIRM KILL 後：
   - SSE feed 即時收到 audit row `action="kill_api"`
   - 該 row 從 active sessions 表移除（state CLOSED）

### 6.3 Confirmation Flow (v2 amendment: 順序明文 cancel-then-revoke — BB caveat 4 ★★)

> **BB pushback 接納**：spec v1 §6.3 沒 explicit 講 Bybit 端 cancel-all + close-position 何時 fire。v2 明文順序：**Cancel-all → close-position → revoke → cancel_token**，DCP 為 backup。

```
operator click kill →
  modal countdown 5s →
    confirm →
      POST /api/v1/live/supervised/kill →
        Python route: auth + envelope + session_id valid →
          Python SM: ACTIVE_TRADING/ACTIVE_AUTHED → CLOSED (kill_api event) →
            IPC: trigger_kill_switch(session_id) →
              Rust SM: confirm CLOSED →
                [per §6.6 序列化 batch_wait per-symbol]
                  for each symbol in session.symbols (ASCII sort):
                    POST /v5/order/cancel-all (per symbol)        ← STEP 1
                    if open_position: POST /v5/order/create reduce_only ← STEP 2
                    wait 0.3s (Order group 20 r/s safety margin)
                ↓
                revoke_live_authorization() (per drawdown_revoke same path) ← STEP 3
                ↓
                engine cancel_token fire (graceful shutdown if needed) ← STEP 4
                ↓
                audit row written + SSE broadcast + GUI session table updated
```

**禁止**：先 revoke → engine cancel_token → cancel-all 沒 fire → DCP fallback 救場。
**DCP 是 backup 而非 primary**。Operator 視 DCP fire 為「kill 沒做完整」，應觸發 RCA。

### 6.4 Audit Log — unchanged from v1

每 kill 對應 1 個 audit row（`action="kill_api"`）+ per-lease 觸發 1 row in `learning.lease_transitions` (released event) + per-cancelled-order 1 row in 既有 `trading.orders` audit。

### 6.5 A3 Review Prerequisites — unchanged from v1

GUI kill button ship 前必派 A3：
- 5s countdown 計時器 in JS（防 client-side bypass）+ 防 keyboard enter 提前觸發
- modal 不可被 keyboard `Tab+Enter` skip
- CANCEL = X 按鈕 = ESC 三條取消路徑都 work
- Confirm 點擊後立即 disabled 防 double-click

per `feedback_gui_node_check_sop.md`，前端 JS 動 IMPL DONE 強制 `node --check` + A3 + E2 三方核驗。

### 6.5A Approval Response Panel — submitted vs effective（QC CAVEAT 10 ★★ v2 new）

> **QC pushback 接納**：operator 填 80（override > P1=50）→ spec min-only 算 effective=50；但 GUI 未明示「effective 顯示」可能誤以為 80 生效。

**UI Requirement**：

Approval form submit response 後 GUI panel 必明確區分 submitted vs effective：

```
┌─────────────────────────────────────────────────────────┐
│        Approval Success — Session sess:xxx               │
├─────────────────────────────────────────────────────────┤
│  State: ACTIVE_PRE_AUTH                                  │
│                                                          │
│  Risk Limits Effective (after P1 / strategy cap):       │
│  ┌──────────────────┬──────────┬──────────┬──────────┐  │
│  │ Field            │ Submitted│ Effective│ Reason   │  │
│  ├──────────────────┼──────────┼──────────┼──────────┤  │
│  │ max_position     │  $80     │  $50     │ P1 caps  │  │
│  │ max_daily_loss   │  $25     │  $25     │ same     │  │
│  │ max_orders       │  10      │  10      │ same     │  │
│  │ max_leverage     │  3.0     │  2.0     │ P1 caps  │  │
│  └──────────────────┴──────────┴──────────┴──────────┘  │
│                                                          │
│  [VIEW AUDIT LOG]      [OPEN ACTIVE SESSIONS TABLE]     │
└─────────────────────────────────────────────────────────┘
```

**Audit payload binding**：每 approval audit row 之 `payload.submitted_override` + `payload.effective_after_min` + `payload.submitted_vs_effective_reason` 填寫對應 dict，per §4.1 SHOULD-stable subfield。

**LG3-T7 AC-T7-7（new）**：Approval response panel test：submitted_override=80, p1=50 → GUI 顯示 effective=50 + reason="P1 caps"。

### 6.6 Kill Rate-Limit Pattern — batch_wait per-symbol（BB caveat 2 ★★★ v2 new）

> **BB pushback 接納**：25 symbol full universe kill 觸發時 cancel-all + close-position 可能瞬發 ~125+ Order group calls，超 20 r/s × 5s safety cap → IP rate-limit 403 + 10min cooldown。

**`/kill` IMPL 必走 `OrderManager::place_order()` 既有 rate_limit_remaining 預檢路徑**。

**序列化規則**（per BB caveat 2 + 字典 §1.1）：

```python
# Rust pseudocode (real IMPL in rust/openclaw_engine/src/ipc_server/handlers/supervised_kill.rs)
async fn execute_kill_sequence(session: &Session) -> Result<KillReport> {
    let mut report = KillReport::new();
    // STEP 1+2: per-symbol cancel-all + close-position with 0.3s batch_wait
    for symbol in session.symbols.iter().sorted_by(|a, b| a.cmp(b)) {  // ASCII sort 為 deterministic
        // 1.1 cancel pending orders for this symbol
        let cancel_result = order_manager.cancel_all_for_symbol(symbol).await?;
        report.cancellations.push((symbol.clone(), cancel_result));

        // 1.2 if open position exists, fire reduce_only flip-side market order
        if let Some(pos) = position_manager.get_open_position(symbol).await {
            let close_result = order_manager.close_position_market(symbol, &pos).await?;
            report.closures.push((symbol.clone(), close_result));
        }

        // 1.3 0.3s batch_wait per Bybit Order group 20 r/s × 0.3s safety margin
        tokio::time::sleep(Duration::from_millis(300)).await;
    }
    // STEP 3: revoke local authorization
    revoke_live_authorization()?;
    report.revoked_at = Instant::now();
    // STEP 4: engine cancel_token fire (graceful shutdown if needed)
    cancel_token.cancel();
    Ok(report)
}
```

**SLA**: 25 symbols × 0.3s = 7.5s + cancel/close time ~3s = 完整 kill 總時間 ≤ 10s。GUI countdown 顯示「Kill in progress (estimated 10s remaining)」per progress feed。

**Rate budget**:
- per kill cycle: 25 cancel-all + 25 close-position = 50 calls / 7.5s ≈ 6.7 r/s
- Order group 20 r/s cap → 33% utilization，留 67% headroom for concurrent strategy intent during kill
- 0.3s safety margin per symbol absorbs Bybit clock-side jitter

**禁止 anti-pattern**：
- ❌ 並發發出 25 cancel + 25 close = 瞬發 50 calls 超 Order group 20 r/s × 5s cap (~100)
- ❌ 依賴 DCP 救場（per §6.3 + caveat 4）

**LG3-T5 AC-T5-7（new）**: kill sequence rate budget test：mock 25 symbol × 0.3s batch_wait → verify 5s window 內 ≤ 20 calls。

---

## 7. Integration Points

### 7.1 SM-04 Ladder 接入 — unchanged from v1

SM-04 (drawdown ladder) 既有 `drawdown_revoke.should_revoke()` 路徑：

- SM-04 透過 `drawdown_revoke::should_revoke()` 觸發 → drawdown_breach event in SupervisedLiveSm
- audit row 寫入 + revoke_live_authorization() + SM transition 到 DRAWDOWN_PAUSE → CLOSED
- 不改 SM-04 本身邏輯；只在 SM-04 fire 時 supervised_live_sm 同步 transition

接入點：`rust/openclaw_engine/src/main.rs` periodic loop 既有 `should_revoke()` call site 之後加 `supervised_live_sm.transition(SmEvent::DrawdownBreach{...})`。

### 7.2 Decision Lease 接入 (lease_bound_live_action) — unchanged from v1

ACTIVE_AUTHED → ACTIVE_TRADING transition 條件 = `lease_acquired` event。

Lease 接入流程：
1. Strategy emit intent → IntentProcessor → GovernanceHub.acquire_lease()
2. Lease grant 成功 → emit `LeaseTransitionMsg` (既有 V054 path)
3. 新增：lease_transition_writer 觀察到「engine_mode in {live, live_demo}」且 session_id 對齊 → fire `SmEvent::LeaseAcquired` 到 SupervisedLiveSm
4. SM transition ACTIVE_AUTHED → ACTIVE_TRADING + audit row

**雙寫對齊**：每 `lease_acquired` 同時寫 `learning.lease_transitions` (V054) + `learning.supervised_live_audit` (V094 new)；reconciler §2 對賬。

### 7.3 W-AUDIT-9 Graduated Canary 接入 — unchanged from v1

W-AUDIT-9 5-stage cohort（per AMD-2026-05-09-03）與 LG-3 SM **互補不衝突**：

- W-AUDIT-9 SM = per-cohort canary stage（決定 `shadow_mode_provider` 對該 cohort 回什麼值）
- LG-3 SM = per-session supervised live state（決定真 live 訂單能不能下）

**Gate**：LG-3 SM `lease_bound_live_action` state（ACTIVE_TRADING）開放條件 = W-AUDIT-9 Stage ≥3（per AMD §5.4.1）。

接入點：approval gate 5（§3.3）check `cohort_ref` 對應 cohort 在 `governance.canary_cohort_log` 是否為 Stage ≥3；非則 reject (reason: `cohort_not_stage_3_or_above`).

### 7.4 EarnedTrust T0-T3 接入 — unchanged from v1

- T0-T3 ladder 既有 EarnedTrustEngine 不動
- approval gate 6 check `earned_trust.current_tier ≥ T0` + `last_auth_expires_ts_ms > NOW`
- T0 cap 1 strategy；T1 cap 2；T2 cap 3；T3 cap 5
- T0 max session duration 30 min；T1 60 min；T2 120 min；T3 480 min

接入點：`live_session_routes.approve()` 之 Gate 6 scope validation 內 lookup `earned_trust_engine.get_state_snapshot().current_tier` + cross-ref tier 上限表。

### 7.4A EarnedTrust × Bybit KYC tier cross-ref（BB caveat 5 ★★ v2 new）

per BB caveat 5：approval Gate 7 必 cross-check operator Bybit KYC tier vs request `EarnedTrust.current_tier`。

| EarnedTrust tier | Bybit KYC required (minimum) | Bybit risk_limit_tier 影響 |
|---|---|---|
| T0 | Tier 0+ (any) | risk_limit base |
| T1 | Tier 1+ (基本 KYC) | risk_limit base |
| T2 | Tier 2+ (進階 KYC) | risk_limit base |
| T3 | Tier 2+ | risk_limit base (notional may upgrade) |

**Implementation hint**：

```python
REQUIRED_KYC_FOR_TRUST_TIER = {
    TrustTier.T0: BybitKycTier.TIER_0,
    TrustTier.T1: BybitKycTier.TIER_1,
    TrustTier.T2: BybitKycTier.TIER_2,
    TrustTier.T3: BybitKycTier.TIER_2,
}
```

**為什麼必要**：若 approval pass 但 Bybit 端 retCode=10005 (PermissionDenied) → live order create 後失敗 + 該 transition audit 寫入 + lease 浪費 + operator 困惑為何「pass approval 但無單成交」。Gate 7 在 approval 時 cross-ref，避免 lease + audit 浪費。

**caching**：`query_bybit_kyc_tier_cached()` 5min cache（per §3.7）。Cache miss + Bybit unreachable → fail-closed reject approve（reason: `bybit_kyc_check_unreachable`）。

**LG3-T3 AC-T3-6（new）**: Gate 7 reject test：mock Bybit KYC tier 0，request EarnedTrust T2 → reject reason=`bybit_kyc_tier_below_trust_tier_requirement`。

### 7.5 AlphaSurface (W-AUDIT-8a) 預留接口 — unchanged from v1

R-4（per-alpha-source live promotion gate）在 W-AUDIT-8g DEFER N+7+ 才 IMPL；本 spec 為其留：

- `approval_request.metadata.alpha_source_id` NULLable
- `audit.alpha_source_id` NULLable column
- `audit.strategy_alpha_score` NULLable FLOAT8（v2 MIT SHOULD-2 補欄位，R-4 routing 評分依據）
- 未來 N+7+ W-AUDIT-8g 在 LG-3 SM 之上加 `LiveBudget(alpha_source_id, slice)` 維度

**Backward-compat 保證**：N+1 ship 時所有 `alpha_source_id=NULL`、`strategy_alpha_score=NULL`、`regime_tag=NULL`；W-AUDIT-8g land 時 add UPDATE backfill 不破 V094。

### 7.6 WS Reconnect 不觸 SM transition（BB caveat 1 ★ v2 new）

> **BB pushback 接納**：spec 未顯式回應 WS reconnect 對 SM state 影響，避免後續 IMPL 誤判 WS disconnect 為 `auth_file_invalid` event。

**規則**：

- WS reconnect 是 `ws_client/run_loop.rs` + `bybit_private_ws.rs` 內部 retry path（指數退避 3-60s）；LG-3 SM state **不受 WS reconnect 直接影響**
- `auth_file_observed` → `ACTIVE_AUTHED` 階段 Private WS 已 auth + subscribed；SM state 是 control plane meta，**不觸 WS re-subscribe**
- WS reconnect 失敗 + authorization.json 仍 valid → SM state 維持
- 若 WS reconnect 失敗 + authorization.json **expired** → 5min re-verify fire `auth_recheck_fail` → `CLOSED`（既有 path）
- WS connection 斷開單獨不觸 `auth_file_invalid` event

**implementation hint**：reconciler `should_force_close()` 不參考 WS connection state。

**LG3-T6 AC-T6-6（new）**: WS reconnect under load test：模擬 WS 斷開 → 重連 30s 內 → SM state 維持不變（無 transition）。

---

## 8. LG3-T1..T7 IMPL Tasks (v2 amendment: 補 AC + LOC 微調)

### LG3-T1 Rust SM Core

| Item | Value |
|---|---|
| **Surface** | Rust |
| **Files** | NEW `rust/openclaw_engine/src/supervised_live_sm/mod.rs` (~200 LOC)<br>NEW `rust/openclaw_engine/src/supervised_live_sm/state.rs` (~300 LOC SmState + SmEvent + IllegalTransitionError enums + `audit_action_to_projected_state` fn per §2.2A)<br>NEW `rust/openclaw_engine/src/supervised_live_sm/transition.rs` (~500 LOC try_transition + LEGAL_TRANSITIONS table + invariant check)<br>NEW `rust/openclaw_engine/src/supervised_live_sm/reconciler.rs` (~300 LOC 30s reconcile loop + inverse map use)<br>NEW `rust/openclaw_engine/src/supervised_live_sm/tests.rs` (~400 LOC) |
| **Total LOC** | ~1700 LOC |
| **Acceptance Criteria** | AC-T1-1: `LEGAL_TRANSITIONS` table 覆蓋 §1.2 全部 16 條合法 transition<br>AC-T1-2: 16 個 transition 各有 unit test 證明 (src, event) → dst 正確<br>AC-T1-3: 非法 transition 至少 6 個 test case 各觸 `IllegalTransitionError`<br>AC-T1-4: reconciler 30s loop test 在 mock 5 SoT 下 disagree 觸 force_close<br>AC-T1-5: reconciler false-positive 防衛 test：transient 1-cycle disagree 不觸 force_close<br>AC-T1-6: p99 transition latency <100us<br>**AC-T1-7 (v2)**: `audit_action_to_projected_state` fn 17 action mapping 全 cover unit test（per §2.2A; MIT MUST-6） |
| **Parallel constraint** | 新 module，不衝突任何現有 file |

### LG3-T2 Python SM Mirror

| Item | Value |
|---|---|
| **Surface** | Python |
| **Files** | NEW `program_code/exchange_connectors/bybit_connector/control_api_v1/app/supervised_live_state.py` (~500 LOC) |
| **Total LOC** | ~500 LOC |
| **Acceptance Criteria** | AC-T2-1: 16 transition 各有 pytest unit test 證明對應 Rust SM 行為<br>AC-T2-2: JSON persist round-trip<br>AC-T2-3: 接收 Rust SM IPC broadcast 後 in-memory state 與 Rust 一致<br>AC-T2-4: disagree 觸發 reconcile 路徑可被 mock injected<br>AC-T2-5: fail-soft：JSON file corrupted → log + fallback to ALL DRAFT state<br>**AC-T2-6 (v2)**: Python `audit_action_to_projected_state` dict 1:1 對應 Rust §2.2A 表（IMPL 後 E2 check 等價性） |
| **Parallel constraint** | 新 file |

### LG3-T3 Approval RPC Route

| Item | Value |
|---|---|
| **Surface** | Python |
| **Files** | EXTEND `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py` (+250 LOC: ApprovalRequest/ApprovalResponse Pydantic models + `/approve` `/kill` `/request` `/status` 4 端點 + Gate 7 KYC check)<br>NEW `program_code/exchange_connectors/bybit_connector/control_api_v1/app/supervised_live_models.py` (~150 LOC pydantic + validation helpers) |
| **Total LOC** | +400 LOC |
| **Acceptance Criteria** | AC-T3-1: §3.3 8 個 Gate 各有 fail test case<br>AC-T3-2: scope_widens_live_authorization reject 正常 work<br>AC-T3-3: 5-gate live boundary check 接 既有 `check_live_boundary_5_gate()`<br>AC-T3-4: HMAC envelope verify 走既有 `auth.verify_envelope_signature()`<br>AC-T3-5: 12 個 §5.3 TC 中 hot-reload 相關 4 個 covered by integration test<br>**AC-T3-6 (v2)**: Gate 7 reject test：mock Bybit KYC tier 0，request EarnedTrust T2 → reject reason=`bybit_kyc_tier_below_trust_tier_requirement`（BB caveat 5）<br>**AC-T3-7 (v2)**: `query_bybit_kyc_tier_cached` 5min cache test：cache hit / miss / expire / Bybit unreachable fail-closed paths<br>**AC-T3-8 (v2)**: §3.5 immutability: lease re-acquire 不重設 override（QC CAVEAT 7 / TC-14） |
| **Parallel constraint** | 依 LG3-T2 SM state import |

### LG3-T4 Audit Mirror Writer

| Item | Value |
|---|---|
| **Surface** | Mix (SQL + Rust + Python healthcheck) |
| **Files** | NEW `sql/migrations/V094__supervised_live_audit.sql` (~280 LOC per §4.1 v2)<br>NEW `rust/openclaw_engine/src/database/supervised_live_audit_writer.rs` (~400 LOC mirror lease_transition_writer.rs pattern)<br>NEW `helper_scripts/db/passive_wait_healthcheck/checks_supervised_live_audit.py` (~250 LOC `[59]` invariant + `[60]` approval_rpc_health 含 30d budget gate + `[61]` audit_mirror_freshness)<br>NEW `helper_scripts/audit/e3_grep_non_training_surface.sh` (~50 LOC per MIT MUST-5) |
| **Total LOC** | ~980 LOC |
| **Acceptance Criteria** | AC-T4-1: V094 idempotent rerun（per CLAUDE.md §九 strict Guard A/B/C）<br>**AC-T4-1a (v2)**: Linux `psql -f V094 × 2 round` second run no-op (MIT idempotency 補測)<br>AC-T4-2: Linux PG dry-run 必驗（per `feedback_v_migration_pg_dry_run.md`）<br>AC-T4-3: writer 接 SupervisedLiveAuditMsg mpsc channel；batch 100 row 或 1s flush<br>AC-T4-4: PG down → fail-soft retry 3 次後升 healthcheck `[61]` ERROR<br>AC-T4-5: `[60]` check 24h `MAX(created_at)` 與 `[55]` lease_transitions cross-correlate<br>AC-T4-6: alpha_source_id NULLable column 在 schema；CHECK constraint 不阻 NULL<br>**AC-T4-7 (v2)**: Guard A part 2 reject test：rm column `event_id` → migration 跑 → RAISE EXCEPTION（MIT MUST-1）<br>**AC-T4-8 (v2)**: CHECK constraint test：INSERT action='invalid_action' → reject; INSERT result='ko' → reject; INSERT ts_ms=0 → reject（MIT MUST-2）<br>**AC-T4-9 (v2)**: E3 grep test：`grep -E 'SELECT.*supervised_live_audit' program_code/{ml,training,learning,scorer,linucb,mlde,dream,optuna,thompson}` returns 0 matches（MIT MUST-5）<br>**AC-T4-10 (v2)**: SHOULD column NULLable test：INSERT without `strategy_alpha_score` 或 `regime_tag` → pass（MIT SHOULD-2/3） |
| **Parallel constraint** | 新 file + 獨立 PG migration |

### LG3-T5 Kill Switch + session_override + lease binding

| Item | Value |
|---|---|
| **Surface** | Mix (Python route + Rust IPC handler + IntentProcessor) |
| **Files** | EXTEND `live_session_routes.py` (+100 LOC `/kill` route)<br>NEW `rust/openclaw_engine/src/ipc_server/handlers/supervised_kill.rs` (~200 LOC kill_switch IPC cmd handler + 序列化 batch_wait pattern per §6.6)<br>EXTEND `rust/openclaw_engine/src/intent_processor/mod.rs` (+120 LOC compute_effective_limits + SessionOverrideLimits struct + Arc<RwLock<HashMap>> session_overrides slot) |
| **Total LOC** | +420 LOC |
| **Acceptance Criteria** | AC-T5-1: §5.3 19 TC 全 pass（含 TC-13~TC-19 attack vector + 邊界 case）<br>AC-T5-2: kill API 與 kill IPC 兩條路徑 idempotent<br>AC-T5-3: kill 同步 revoke ALL active leases for session_id<br>AC-T5-4: kill 同步 cancel ALL pending orders for session.symbols<br>AC-T5-5: grep `max\(.*p1` returns 0 matches in intent_processor/<br>AC-T5-6: integration test: P1 hot reload tighten + session_override 持平 → effective 立即 tighten<br>**AC-T5-7 (v2)**: kill sequence rate budget test：mock 25 symbol × 0.3s batch_wait → verify 5s window 內 ≤ 20 calls（BB caveat 2）<br>**AC-T5-8 (v2)**: kill sequence order test：cancel-all THEN close-position THEN revoke THEN cancel_token；revoke 提前 fire → test fail（BB caveat 4）<br>**AC-T5-9 (v2)**: u32 saturating test (TC-17)：session_override.max_orders=u32::MAX 不 panic |
| **Parallel constraint** | 依 LG3-T1 SM state import + LG3-T2 mirror |

### LG3-T6 E2E Acceptance Tests

| Item | Value |
|---|---|
| **Surface** | Mix |
| **Files** | NEW `rust/openclaw_engine/tests/supervised_live_e2e.rs` (~600 LOC LG-4 RFC 10 條件 + 反 §3.5 attack vector + load test)<br>NEW `program_code/tests/test_supervised_live_e2e.py` (~500 LOC API-side E2E) |
| **Total LOC** | ~1100 LOC |
| **Acceptance Criteria** | AC-T6-1: LG-4 RFC §Acceptance Tests 10 條件全 cover<br>AC-T6-2: split-brain test：mock 5 SoT 中強推 2 個 disagree → 連 2 cycle reconcile → force_close + audit row<br>AC-T6-3: kill switch dual-path idempotent test<br>AC-T6-4: scope widen attack test reject<br>AC-T6-5: 7-state 完整 walk-through happy path test<br>**AC-T6-6 (v2)**: WS reconnect under load test：WS 斷開 → 重連 30s 內 → SM state 維持不變（BB caveat 1）<br>**AC-T6-7 (v2)**: load test 1000 concurrent intents × 100 sessions × 24h continuous run; assert ∀ intent computed_effective ≤ P1_at_call_time（QC CAVEAT 8）<br>**AC-T6-8 (v2)**: 30d post-ship metric gate validate（QC CAVEAT 9 同 [60] healthcheck cross-link）<br>**AC-T6-9 (v2)**: Approval response panel test：submitted_override=80, p1=50 → audit payload `submitted_override=80, effective_after_min=50, reason="P1 caps"`（QC CAVEAT 10）<br>**AC-T6-10 (v2)**: TC-15 Sequential kill+approve scope-widen audit forensic test |
| **Parallel constraint** | 依 LG3-T1+T2+T3+T4+T5 全 land 後 |

### LG3-T7 GUI Surface

| Item | Value |
|---|---|
| **Surface** | Frontend |
| **Files** | EXTEND `static/live-tab.js` (+450 LOC supervised live sub-section + active sessions table + kill modal + approval response panel)<br>EXTEND `static/live-tab.css` (+120 LOC kill modal styles + approval response table)<br>EXTEND `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py` (+50 LOC `/audit/stream` SSE endpoint) |
| **Total LOC** | +620 LOC |
| **Acceptance Criteria** | AC-T7-1: 5s countdown modal: kill button disabled until countdown 0<br>AC-T7-2: ESC + X + CANCEL 三條取消路徑 work<br>AC-T7-3: CONFIRM KILL 後立即 disabled 防 double-click<br>AC-T7-4: SSE feed 即時收到 audit row 並 update active sessions table<br>AC-T7-5: `node --check live-tab.js` PASS<br>AC-T7-6: A3 review APPROVE<br>**AC-T7-7 (v2)**: Approval response panel test：submitted_override=80, p1=50 → GUI 顯示 effective=50 + reason="P1 caps"（QC CAVEAT 10 / §6.5A）<br>**AC-T7-8 (v2)**: Approval response panel 4 fields 全顯示（max_position, max_daily_loss, max_orders, max_leverage） |
| **Parallel constraint** | 不依 T1-T6（GUI 用 mock SM state 開發） |

### Task Summary (v2 amendment: LOC 微調)

| Task | Surface | LOC | Parallel Group | Sprint Phase |
|---|---|---|---|---|
| LG3-T1 | Rust | ~1700 | Group A (independent) | Wave 2.4 Phase 1 |
| LG3-T2 | Python | ~500 | Group A (independent) | Wave 2.4 Phase 1 |
| LG3-T4 | SQL+Rust+Python | ~980 | Group A (independent) | Wave 2.4 Phase 1 |
| LG3-T7 | Frontend | ~620 | Group A (independent w/ mock) | Wave 2.4 Phase 1 |
| LG3-T3 | Python | ~400 | Group B (依 T1+T2) | Wave 2.4 Phase 2 |
| LG3-T5 | Python+Rust | ~420 | Group B (依 T1+T2) | Wave 2.4 Phase 2 |
| LG3-T6 | Mix | ~1100 | Group C (依 T1..T5) | Wave 2.4 Phase 3 |

**Total LOC**: ~5720 LOC (Rust ~3500 / Python ~1400 / SQL ~200 / Frontend ~620)

**Parallel capacity**: Phase 1 = 4 並行 (T1/T2/T4/T7); Phase 2 = 2 序列 (T3 → T5 或 T3//T5 看 T2 import); Phase 3 = 1 (T6 必後).

---

## 9. QC + BB + MIT Review Checklist (v1 預期；Wave 2.1.5 已三方 APPROVE)

### 9.1 QC Review Result — APPROVE WITH 6 STATISTICAL CAVEATS + 4 SHOULD

CAVEAT 1-10 全 incorporate（per §16 resolution table）。0 redesign。

### 9.2 BB Review Result — APPROVE WITH 6 + 1 BYBIT CAVEATS

caveat 1-7 全 incorporate（per §16 resolution table）。0 ship-stop blocker。Bybit V5 changelog 0 breaking change since baseline 2026-05-09。

### 9.3 MIT Review Result — APPROVE WITH 6 MUST + 3 SHOULD

MUST-1~6 全 incorporate；SHOULD-1~3 全 incorporate（per §16 resolution table）。0 schema bug / 0 ML leakage / 0 V### naming conflict。

---

## 10. Required Healthchecks ([59] [60] [61]) (v2 amendment)

### `[59]` supervised_live_sm_invariant (v2: 加 baseline + KS test — MIT SHOULD-1)

```python
def check_supervised_live_sm_invariant() -> str:
    """
    Verify 5 SoT consistency for last 5min window + transition frequency drift.
    Returns: PASS / WARN / FAIL.
    """
    # Sub-check 1 (既有): 5 SoT disagree detection
    # 1. Query last 5min audit rows
    # 2. Query lease_transitions for same session_ids
    # 3. Check authorization.json exists if any ACTIVE_AUTHED+ session
    # 4. Check Python SM disk state JSON exists + parseable
    # 5. If any pairwise disagree → return WARN (1 cycle); FAIL if last 2 cycles both WARN

    # === v2 Sub-check 2 (MIT SHOULD-1 — transition frequency baseline) ===
    # 6. last_24h_transition_count vs trailing_7d_average per (action, engine_mode)
    # 7. KS test p-value < 0.01 持續 1h → WARN (transition rate drift)
    # 8. Baseline reference window: trailing 7d avg
    # 9. For (action='kill_api', 'drawdown_breach', 'session_max_duration'):
    #    - sudden spike (z-score > 3) → WARN
    #    - sustained anomaly (z-score > 2 持續 1h) → WARN
    ...
```

| Threshold | 行為 |
|---|---|
| 0 disagree + 0 drift | PASS |
| 1-cycle disagree OR transition frequency KS p<0.01 | WARN |
| 2+ cycles disagree | FAIL |

### `[60]` approval_rpc_health (v2: 30d 1% violation budget gate — QC CAVEAT 9)

```python
def check_approval_rpc_health() -> str:
    """
    Verify approval RPC endpoint reachable + last 24h success rate sane.
    + 30d window violation budget gate.
    Returns: PASS / WARN / FAIL.
    """
    # Sub-check 1 (既有 + 24h): approval rate sanity
    # 1. Query last 24h supervised_live_audit row count by action
    # 2. If 0 approval_granted + 0 approval_rejected in 24h → INFO
    # 3. If approval_rejected/approval_granted > 50% → WARN
    # 4. Query /api/v1/live/supervised/status local healthz → if fail → FAIL

    # === v2 Sub-check 2 (QC CAVEAT 9 — 30d budget gate) ===
    # 5. 30d window N sessions:
    #    - min_only_invariant_violation_count == 0 → hard FAIL if > 0
    #    - illegal_transition_count == 0 → hard FAIL if > 0
    #    - reconcile_force_close_count / total_sessions < 1% → WARN > 5%
    # 6. Sequential kill+approve scope-widen > 50% in 30d (QC CAVEAT 3) → WARN

    # === v2 Sub-check 3 (BB caveat 5 — KYC tier reject rate) ===
    # 7. reason_codes='bybit_kyc_tier_below_trust_tier_requirement' rate > 10% in 24h → INFO
    #    (signals operator KYC misconfig)
    ...
```

### `[61]` audit_mirror_freshness — unchanged from v1

```python
def check_audit_mirror_freshness() -> str:
    """
    Verify supervised_live_audit writer 健康 + reconcile_force_close 異常頻率.
    Returns: PASS / WARN / FAIL.
    """
    # 1. MAX(created_at) for non-empty period < 5min → PASS
    # 2. Last 24h reconcile_force_close count > 3 → WARN
    # 3. Last 24h reconcile_force_close > 10 → FAIL (split-brain epidemic)
    # 4. PG retry exhaustion log line in last 1h → FAIL
    ...
```

### Cross-check with 既有 healthchecks — unchanged from v1

| 既有 | 互補關係 |
|---|---|
| `[33]` maker_fill_rate | 不重疊 |
| `[40]` realized_edge | 不重疊 |
| `[45]` pricing_binding | 不重疊 |
| `[55]` agent_decision_spine_lineage | 部分重疊 |
| `[56]` live_pipeline_active | 互補 |
| `[58]` canary_stage_invariant | 互補 |

---

## 11. Risk + Mitigation 重排 (v2 amendment: +11.9 kill rate-limit — BB caveat 補)

### 11.1 (極高) SM 5-SoT split-brain

- Mitigation 1：external observer reconcile loop §2，連 2 cycle disagree 強制 force_close
- Mitigation 2：audit table 為 SoT 真值權威；其餘 4 個 derived view
- Mitigation 3：reconciler 30s 而非 5s + 1-cycle delay 防 transient
- Mitigation 4：healthcheck `[59]` `[61]` 雙線監控
- **Mitigation 5 (v2)**: §2.2A inverse map 17 action × 7 state 完整表（MIT MUST-6）+ Rust/Python 1:1 等價（IMPL phase E2 check）

### 11.2 (極高) session_override 變相突破 P1

- Mitigation 1：`compute_effective_limits` 嚴格 `min`-only formula §5.1
- Mitigation 2：19 TC 不變式 test E2 + QC + MIT 三角必審（v2: 從 12 升到 19 TC）
- Mitigation 3：grep `\bmax\(.*p1\|.*session_override.*p1\)` E2 review 必查（0 match）
- Mitigation 4：SessionOverrideLimits parsing fail-closed for NaN/負/零（§5.4）
- **Mitigation 5 (v2)**: session_override immutable for session lifetime（§3.5 + QC CAVEAT 7）
- **Mitigation 6 (v2)**: u32 saturating math 明示（§5.1 + TC-17）

### 11.3 (高) GUI kill button 誤操作

- Mitigation 1：5s countdown modal §6.2，CONFIRM 按鈕初始 disabled
- Mitigation 2：A3 review prerequisites §6.5
- Mitigation 3：node --check + E2 + A3 三方核驗
- **Mitigation 4 (v2)**: Approval response panel submitted vs effective 明示（§6.5A + QC CAVEAT 10）

### 11.4 (中) outbox mpsc buffer 滿 SM 不 advance

- Mitigation 1：buffer cap 1024
- Mitigation 2：SM transition 非 hot path，fail-closed OK
- Mitigation 3：healthcheck `[61]` 監控 PG retry exhaustion
- **Mitigation 4 (v2)**: §4.4A PG retry 用盡後 in-memory state recovery + reconciler 自動 force_close（QC CAVEAT 4 + TC-16）

### 11.5 (中) approval RPC 6-gate 序列繞過 attack (v2 升 8-gate)

- Mitigation 1：所有 8 個 Gate 都必過才 transition；無短路
- Mitigation 2：scope_widens_live_authorization reject (§3.5)
- Mitigation 3：integration test 覆蓋每 Gate fail case
- **Mitigation 4 (v2)**: Gate 7 Bybit KYC tier cross-ref（BB caveat 5）
- **Mitigation 5 (v2)**: §3.5 immutability + sequential kill+approve audit forensic（QC CAVEAT 3 + TC-15）

### 11.6 (中) Rust+Python SM IPC broadcast race

- Mitigation 1：audit 是 SoT；reconciler 觀察 audit 為真值
- Mitigation 2：Python SM mirror 接 IPC broadcast 但不獨自決定 state
- **Mitigation 3 (v2)**: §2.2A inverse map Rust/Python 1:1 等價 IMPL（MIT MUST-6）

### 11.7 (低) R-4 backward-compat 破壞

- Mitigation：alpha_source_id / strategy_alpha_score / regime_tag NULLable column
- **Mitigation 2 (v2)**: MIT SHOULD-2/3 預留 2 forward-compat column

### 11.8 (低) Spec phase 工期超 1.5d

- 已避免（spec v1 ship 1d；spec v2 final ship 0.5d）

### 11.9 (中) Kill 序列化 vs Bybit rate-limit 競爭（BB caveat 補 v2 new）

- **Mitigation 1**：cancel-all + close-position 序列化 per symbol（§6.6）
- **Mitigation 2**：每 step 0.3s safety margin 在 Order 20 r/s 之內
- **Mitigation 3**：DCP 為 fallback 不為 primary kill mechanism
- **Mitigation 4**：cancel-all THEN close-position THEN revoke 順序明文（§6.3 + BB caveat 4）

---

## 12. Cross-Wave 衝突檢查 — unchanged from v1

### 12.1 與 LG-1 (H0 Blocking)

- 0 file 重疊
- LG-1 [59] healthcheck name 衝突 → 本 spec 改用 `[59] supervised_live_sm_invariant` + LG-1 移到 `[N+1] h0_block_acceptance`

### 12.2 與 LG-2 (Provider Pricing Binding)

- 0 file 重疊
- LG-2 `[pricing]` section 加 risk.rs；LG-3 不動 risk.rs schema

### 12.3 與 W-AUDIT-9 Graduated Canary

- 0 file 重疊
- gate 互補

### 12.4 與 W-AUDIT-8a AlphaSurface

- 0 file 重疊
- R-4 forward-compat schema 為 N+7+ 預留

### 12.5 與 Sprint N+1 W2 (A4-C BTC→Alt Lead-Lag) IMPL

- 0 file 重疊

### 12.6 與 F3/F4 writer defense

- 0 file 重疊

### 12.7 與 Wave 1.6 P1-FILL-LINEAGE-DROP

- 0 file 重疊

---

## 13. 完成序列 + Sign-off Gate (v2 amendment: §13.4 加 Linux PG dry-run dispatch SOP + pre-flight changelog)

### 13.1 PA spec v1 ship — DONE 2026-05-11

- ✅ 存路徑：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md`

### 13.2 Wave 2.1.5 QC + BB + MIT parallel review — DONE 2026-05-11

- ✅ QC APPROVE WITH 6 STATISTICAL CAVEATS + 4 SHOULD
- ✅ BB APPROVE WITH 6 + 1 BYBIT CAVEATS
- ✅ MIT APPROVE WITH 6 MUST + 3 SHOULD
- ✅ 3 reviewer 同時 APPROVE，0 REQUEST CHANGES

### 13.3 PA spec v2 final — DONE 2026-05-11 (本 doc)

- ✅ 收 QC/BB/MIT 反饋 incorporate 26 caveats
- ✅ 0.5d window 內 ship
- ✅ spec ship 路徑：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`
- ⏳ memory.md 追加（本 session 結束時做）
- ⏳ PM 派 Wave 2.4 IMPL phase

### 13.4 Wave 2.4 IMPL phase (v2 amendment: Linux PG dry-run dispatch SOP — MIT MUST-3 + BB caveat 7)

per §8 task breakdown：
- Phase 1：4 並行（T1/T2/T4/T7）3-4d
- Phase 2：T3+T5 序列 2d
- Phase 3：T6 E2E test 2d
- 全 IMPL ~7-8d

E2 + E4 + A3 + QC + MIT review parallel 1.5d。

#### 13.4.1 Linux PG dry-run dispatch SOP（MIT MUST-3 ★★★ v2 new）

per `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift.md` 教訓：

**LG3-T4 V094 sub-task dispatch order**：

1. **E1 IMPL on Mac** (per CLAUDE.md §九 Sprint A R3 既有 SOP):
   - 寫 V094__supervised_live_audit.sql per §4.1 v2 包含 Guard A part 1+2 + ADD CONSTRAINT block
   - 寫 Rust supervised_live_audit_writer.rs + IPC handler
   - 寫 healthcheck `[59]/[60]/[61]` per §10
   - Mac mock pytest 跑全 unit test
   - git push to branch

2. **Linux dry-run round 1** (per V055 + V083+V084 既有 SOP):
   - ssh trade-core `git pull --ff-only`
   - 不啟用 `OPENCLAW_AUTO_MIGRATE`，手動 `psql -f V094.sql`
   - 跑 `\dt learning.supervised_live_audit` 驗 schema
   - 跑 4 INSERT test data 驗 CHECK constraint reject invalid values
   - 跑 `SELECT * FROM pg_constraint WHERE conname LIKE 'chk_supervised_live_audit_%'` 驗 4 constraint 存在
   - 跑 `\d learning.supervised_live_audit` 驗 21 column

3. **Linux dry-run round 2** (idempotency verify per MIT AC-T4-1a):
   - 再跑一次 `psql -f V094.sql` (no DROP)
   - 期望：second run **no RAISE** (Guard A part 2 + ADD CONSTRAINT IF NOT EXISTS 都 idempotent)
   - 任一 RAISE → reject migration，回 E1 fix

4. **sqlx checksum verify** (per MIT MUST-4 + project_2026_05_02_p0_sqlx_hash_drift.md):
   - 跑 `cargo run --bin sqlx -- migrate info` 驗 V094 checksum
   - 跑 `cargo test` 驗 supervised_live_audit_writer 接通 PG
   - 任一 checksum drift → `bin/repair_migration_checksum --target V094`

5. **進 E2 / E4 / A3** (per CLAUDE.md §八 強制工作鏈):
   - E2 code review
   - E4 regression（含 healthcheck dry-run）
   - A3 GUI / kill modal review

6. **進 sign-off**

**禁止**：Mac mock pytest PASS 不等於 Linux PG runtime semantic PASS（per `feedback_v_migration_pg_dry_run.md`；V055 5-round loop 教訓）。

#### 13.4.2 Wave 2.4 IMPL Pre-flight Bybit V5 Changelog Check（BB caveat 7 ★ v2 new）

每個 LG3-T# IMPL 啟動前（Phase 1 / Phase 2 / Phase 3 各前），E1 或 BB 自跑 changelog drift check：

```bash
# Pseudo-code; real use WebSearch tool
WebSearch site:bybit-exchange.github.io changelog v5 <baseline_date>..<today>
```

baseline_date = 字典手冊 v1.2 ship 日（2026-04-26 G9-01 audit + 2026-05-08 BB v3 baseline）。

發現 breaking change 立即 push back 暫停 IMPL，BB ad-hoc audit。

當前（2026-05-11 BB review time）verify：**0 breaking change** since baseline。

### 13.5 Wave 2.5 Sign-off — unchanged from v1

- LG-3 三方 sign-off + QA + PM 收口；audit row first batch land；GUI tab live

---

## 14. PA 不做事項聲明 — unchanged from v1

- ❌ 本文件不寫 feature code
- ❌ 不啟動 E1（PM 派發 Wave 2.4）
- ❌ 不發 commit
- ❌ 不改 TODO.md / CLAUDE.md
- ❌ 不擴大 scope（R-2/R-3/R-4 留 N+4/N+5/N+7+）

---

## 15. 16 原則 + DOC-08 §12 + 硬邊界 5 項 Compliance Check (v2 amendment: §15.4 Mainnet pre-flight checklist 加 — BB caveat 6)

### 15.1 16 原則 — unchanged from v1

| # | 原則 | 本 spec compliance |
|---|---|---|
| 1 | 單一寫入口 | ✅ SM transition writer 經 audit_writer outbox §4.3 |
| 2 | 讀寫分離 | ✅ GUI / SSE feed read-only；approval/kill 是 operator-side write 限定 |
| 3 | AI ≠ command | ✅ approval 是 operator 路徑；agent 仍走 lease |
| 4 | 策略不繞風控 | ✅ session_override 只能 tighten（min-only）+ session_override immutable |
| 5 | 生存 > 利潤 | ✅ drawdown_revoke 整合；kill 5s confirm + cancel-then-revoke 順序 |
| 6 | 失敗默認收縮 | ✅ 任何 disagree → force_close；任何 transition 失敗 fail-closed |
| 7 | 學習 ≠ 改寫 Live | ✅ Non-training surface invariant（§4.4B + MIT MUST-5） |
| 8 | 交易可解釋 | ✅ audit join (request_id ↔ approval ↔ lease ↔ fills) + payload submitted vs effective |
| 9 | 災難保護 | ✅ kill switch dual-path + 既有 SM-04 ladder |
| 11 | Agent 最大自主 | ✅ supervised live 是 operator-bound scope |
| 13 | 成本感知 | ✅ N/A（control plane） |
| 14 | 零外部成本可運行 | ✅ SM 不依 cloud LLM；audit outbox PG 為本機 |

無原則破壞。

### 15.2 DOC-08 §12 安全不變量 9 條 — unchanged from v1

| # | 安全不變量 | 本 spec compliance |
|---|---|---|
| 1 | Pre-trade audit/replay 必開 | ✅ |
| 2 | Lease 必在執行前 acquired | ✅ |
| 3 | 執行回報必落 fills 表 | ✅ |
| 4 | 風控降級 → engine 自動止血 | ✅ |
| 5 | Authorization 過期/失效 → engine cancel_token | ✅ |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | ✅ |
| 7 | Bybit retCode != 0 → fail-closed | ✅ |
| 8 | Reconciler 對賬差異 → 自動降級 paper | ✅ |
| 9 | Operator 角色與 live_reserved 缺一即拒 | ✅ |

### 15.3 硬邊界 5 項 — unchanged from v1

| # | 硬邊界 | 本 spec 觸碰？ |
|---|---|---|
| 1 | Python `live_reserved` global mode | ❌ |
| 2 | Python Operator 角色 auth | ❌ |
| 3 | OPENCLAW_ALLOW_MAINNET=1 | ❌ |
| 4 | secret slot api_key/api_secret | ❌ |
| 5 | authorization.json HMAC + env_allowed | ❌ |

**0 硬邊界觸碰**。

### 15.4 Mainnet 解鎖前 BB Mandatory Checklist（BB caveat 6 ★★★ v2 new）

LG-3 ship 後 LiveDemo + mainnet code path 90%+ share。Mainnet 真實流量啟動前 BB review mandatory 8 項：

| # | 項目 | 當前狀態 | 責任方 |
|---|---|---|---|
| 1 | M5-1 governance entry: `docs/governance_dev/<date>--bybit_compliance_signoff.md` 建檔（KYC tier + 地理 + API permission + IP whitelist + ToS 6 項 operator 自證） | 0 進展（>12 day stale） | Operator |
| 2 | M5-2 IP whitelist preflight: `helper_scripts/preflight/check_bybit_ip_whitelist.py` IMPL + restart_all 啟動跑 | 0 進展（>12 day stale） | E1 / Operator |
| 3 | mainnet API key 配置驗證：withdraw=false 強制 + trade=true + read=true + IP whitelist set（24h cool-down 後生效） | TBD | Operator |
| 4 | P0-OPS-4 首日 mainnet runbook | outstanding | PM / TW |
| 5 | mainnet authorization.json env_allowed=['mainnet'] vs LiveDemo `['live_demo']` explicit 分隔 | ✅ 既有 code handle | E1 |
| 6 | 首日 limit 在 spec §7.4 T0 30min cap + 1 strategy + 1 symbol cohort 內 | LG-3 IMPL 後 enforced | E1 + Operator |
| 7 | mainnet 切 LiveDemo 不可 hot-swap，必 engine restart + authorization re-issue | LG-3 IMPL 後 enforced | E1 / Operator |
| 8 | broker partnership eligibility 例行驗（每月，per BB skill §6.2）— mainnet ramp-up 30d 內第一次跑 | 當前 30d $45K << $10M（自然不合格） | BB monthly |

**BB 在 mainnet 解鎖前最終發 final audit report 確認 8/8 closed**。

---

## 16. Caveat Resolution Table（v2 new — 26 caveat full audit trail ★★★）

> 給 reviewer 快速查驗每條 caveat 是否 incorporate + 對應 spec v2 章節 + 處理方式。

| # | Source | Severity | Caveat | spec v2 resolution | Status |
|---|---|---|---|---|---|
| **1** | QC CAVEAT 1 | MUST | TC-13 zero session_override parse layer reject | §5.3 TC-13 + §5.4 parsing | ✅ incorporated |
| **2** | QC CAVEAT 2 | MUST | TC-14 lease re-acquire 不重設 override | §5.3 TC-14 + §3.5 immutability | ✅ incorporated |
| **3** | QC CAVEAT 3 | SHOULD | Sequential kill+approve scope widening audit forensic | §3.5.1 + §4.1 payload subfield + §5.3 TC-15 + §10 [60] sub-check | ✅ incorporated |
| **4** | QC CAVEAT 4 | MUST | TC-16 + TC-19 PG retry exhaustion in-memory recovery | §4.4A new + §5.3 TC-16/TC-19 | ✅ incorporated |
| **5** | QC CAVEAT 5 | SHOULD | u32 saturating math 明示 + TC-17 | §5.1 fn body + §5.3 TC-17 | ✅ incorporated |
| **6** | QC CAVEAT 6 | MUST | P1 per-intent vs aggregate cap 明示 + TC-18 | §5.1 doc comment + §5.3 TC-18 | ✅ incorporated |
| **7** | QC CAVEAT 7 | MUST | session_override 中途變更語意（Option 1 immutable） | §3.5 immutability + §5.5 hot-reload note + §5.3 TC-14 | ✅ incorporated (Option 1 採納) |
| **8** | QC CAVEAT 8 | SHOULD | LG3-T6 E2E 加 load test 1000 × 100 × 24h | §8 AC-T6-7 | ✅ incorporated |
| **9** | QC CAVEAT 9 | SHOULD | [60] healthcheck 30d 1% violation budget gate | §10 [60] sub-check 2 | ✅ incorporated |
| **10** | QC CAVEAT 10 | MUST | GUI Approval response panel effective vs submitted + audit payload | §6.5A + §4.1 payload subfield + §8 AC-T7-7+T7-8 + §8 AC-T6-9 | ✅ incorporated |
| **11** | MIT MUST-1 | MUST | Guard A part 2 21-column allowlist | §4.1 Guard A part 2 block | ✅ incorporated |
| **12** | MIT MUST-2 | MUST | ADD CONSTRAINT IF NOT EXISTS block | §4.1 ADD CONSTRAINT block | ✅ incorporated |
| **13** | MIT MUST-3 | MUST | Linux PG dry-run dispatch SOP | §13.4.1 new | ✅ incorporated |
| **14** | MIT MUST-4 | MUST | `bin/repair_migration_checksum` SOP 注釋 | §4.1 SQL header comment + §13.4.1 step 4 | ✅ incorporated |
| **15** | MIT MUST-5 | MUST | Non-training surface invariant + E3 grep rule | §4.4B new + §4.1 SQL header + §8 AC-T4-9 | ✅ incorporated |
| **16** | MIT MUST-6 | MUST | §2.2 inverse map (17 action × 7 state) | §2.2A new full table + Rust hint + Python mirror AC-T1-7/T2-6 | ✅ incorporated |
| **17** | MIT SHOULD-1 | SHOULD | drift baseline `[59]` KS test | §10 [59] sub-check 2 | ✅ incorporated |
| **18** | MIT SHOULD-2 | SHOULD | `strategy_alpha_score` NULLable column | §4.1 schema + §4.2 補欄位表 + §7.5 backward-compat | ✅ incorporated |
| **19** | MIT SHOULD-3 | SHOULD | `regime_tag` NULLable column | §4.1 schema + §4.2 補欄位表 + §7.5 backward-compat | ✅ incorporated |
| **20** | BB caveat 1 | MEDIUM | §7.6 WS reconnect 不觸 SM transition | §7.6 new + §8 AC-T6-6 | ✅ incorporated |
| **21** | BB caveat 2 | HIGH | §6.6 `/kill` per-symbol 序列化 batch_wait pattern | §6.6 new + §8 AC-T5-7 | ✅ incorporated |
| **22** | BB caveat 3 | LOW | §3.6 Renew 走既有 live_trust_routes.renew() | §3.6 new | ✅ incorporated |
| **23** | BB caveat 4 | HIGH | Cancel-all THEN close-position THEN revoke 順序；DCP backup | §6.3 改 + §1.2 kill_api Side Effects 加註 + §8 AC-T5-8 | ✅ incorporated |
| **24** | BB caveat 5 | MEDIUM | Bybit KYC tier × EarnedTrust tier cross-ref | §3.3 Gate 7 + §3.7 + §7.4A new + §8 AC-T3-6+T3-7 + §10 [60] sub-check 3 | ✅ incorporated |
| **25** | BB caveat 6 | HIGH | §15.4 Mainnet 解鎖前 BB mandatory 8 項 checklist | §15.4 new | ✅ incorporated |
| **26** | BB caveat 7 | LOW (meta) | §13.4 Wave 2.4 IMPL pre-flight changelog 自查 | §13.4.2 new | ✅ incorporated |

**26/26 caveat fully incorporated**。0 deferred / 0 不接納 / 0 redesign。

---

## 17. 改動風險評級 (v2 amendment: 仍 極高，但 mitigation 更完整)

| 部分 | 評級 | 理由 |
|---|---|---|
| SM 7-state IMPL | **高** | 改核心狀態機；但新 module，不改既有 hot path；v2 加 §2.2A inverse map IMPL 一致性 |
| audit V094 schema | **中** | 新 PG migration；v2 加 Guard A part 2 + ADD CONSTRAINT + Linux PG dry-run dispatch SOP |
| session_override min-only | **極高** | 觸 P1 風控邊界；spec 嚴格 `min` 約束 + 19 TC（v2 從 12 升）+ immutable lifetime + grep guard |
| GUI kill button | **高** | operator 誤操作高損失；5s countdown + A3 + 序列化 batch_wait + cancel-then-revoke + Approval response panel |
| reconciler 30s loop | **中** | 新 task；非 hot path；連 2 cycle 防 false-positive；inverse map 1:1 等價 |
| audit outbox | **中** | mirror lease_transition_writer 既有 pattern；v2 加 PG retry exhaustion in-memory recovery |
| Bybit KYC tier cross-ref Gate 7 | **中** | 新 approval gate；5min cache + fail-closed unreachable；mock test 必有 |
| Mainnet pre-flight checklist | **高** (mainnet path) | 8 項 mandatory；M5-1 + M5-2 已 12+ day 0 進展，須先收 |

整體：**極高**（session_override + SM core）。Spec v2 完整 incorporate 26 caveat 後 IMPL phase 仍須 E2 + E4 + A3 + QC + MIT 三角必審。

---

PA SPEC v2 FINAL DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`

Next:
- ⏳ PA memory.md 追加（spec v2 final 完成 + 26 caveat resolution 索引）
- ⏳ PM 派 Wave 2.4 IMPL（per §8 task breakdown, 7-8d）
- 後續 sign-off：Wave 2.5（LG-3 三方 sign-off + QA + PM 收口）
