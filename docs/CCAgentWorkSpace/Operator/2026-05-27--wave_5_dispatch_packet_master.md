# Wave 5 Dispatch Packet Master — Layered Autonomy v2 Cascade IMPL

**Date**: 2026-05-27 · **Owner**: PA · **Status**: DRAFTED — ready for主會話派發
**Trigger**: Operator 2026-05-27 APPROVE AMD-2026-05-21-01 v2 → Wave 5 cascade IMPL 81-126 hr / 3 並行

**4 SSOT files**:
- AMD: `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`（684 行）
- PA spec v2: `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`（1031 行）
- V099 spec: `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`（568 行）
- CC re-audit: `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md`（A 級）

---

## §0 三 Packet Executive Summary

| Packet | 範圍 | Owner | Est hr | Wall | Parallelism | Blocker |
|---|---|---|---|---|---|---|
| **A — V099 schema land** | Schema + ENUM + 2 table + Guard A/B/C + Linux PG dry-run 13 條 | E1 + MIT (dry-run) | **8-12 hr** | ~1 day | INDEP | sqlx hash drift SOP 必走（per memory P0 2026-05-02）|
| **B — GUI Autonomy Posture sub-section** | tab-governance.html 加 sub-section + CONFIRM SWITCH typed-confirm + 14 path × 2 level panel + 8 anti-pattern | E1a + A3 + E3 (auth) | **21-28 hr** | ~2-3 day | INDEP for IMPL；READ-only depends on A | A done before B can render 14 path × 2 level matrix from DB |
| **C — Rust SM-04 patch** | `RiskEvent::NotificationFailsafeTimeout` 新 variant + Defensive `active_de_risking` hook 擴充 + 35+ transition rule verify + E4 regression | PA + E1 + E4 | **52-86 hr per AMD §9.8（含 Wave 5 內全 cascade subset）；本 packet 純 SM-04 patch ~6-10 hr** | ~1 day | INDEP | NONE — risk_gov.rs `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_core/src/sm/risk_gov.rs` 940 行 verified |

**3 並行 ceiling**：A + B + C 文件互不重疊（PG schema layer / GUI HTML+JS layer / Rust SM module）= **完全並行** per PM §5 Wave-X2 規範。

**Wall-clock**：max(A, B, C) ≈ **2-3 working day**（B dominates）.

**即派可行性**：
- ✅ Packet A — IMMEDIATELY DISPATCHABLE（V099 spec 字面 IMPL-ready；568 行字面對齊）
- ✅ Packet C — IMMEDIATELY DISPATCHABLE（risk_gov.rs 已 verified；既有 Defensive 變體 line 180-187 不重造；新 variant insertion point line ~53-78 RiskEvent enum 確認）
- ⚠️ Packet B — DISPATCHABLE 但需 **Wait Packet A complete** 才能 e2e regression（GUI 14 path × 2 level panel + cooldown countdown + emergency override rate 計算需 DB schema 已 land；E1a IMPL 可先進但 e2e GREEN 需 V099 land）

**衝突警示**：
- 🚨 **不可與 Sprint 1A-ε V099-V116 並行**（TODO §15 #7：「Wave-X2 V099 與 V112 LAL 同主路徑」）— Sprint 1A-ε P1+P2 已 DONE 2026-05-22 但若仍有未 IMPL P3+ 補丁觸 V099-V116 必先序列
- 🚨 **不可與 LG-3 V104 IMPL 並行碰 sql/migrations/** — V104 spec scaffold ship 2026-05-26；earliest dispatch ~2026-05-30；衝突點不在 V099/V104 號碼（不撞）而在 `_sqlx_migrations` 雙 apply timing；ssh trade-core engine restart auto-migrate 必序列觸發
- 🟡 **不可與 Sprint 2 Stream B V108/V109/V111 並行**（TODO §15 #7）— Sprint 2 W12-15 dispatch；現階段未啟動，不衝

---

## §1 Packet A — V099 Schema Land Full Prompt Template

```
TASK: V099 migration schema land — Autonomy Level Toggle system-wide policy state

ROLE: E1 IMPL + MIT Linux PG empirical dry-run + E4 regression
EST: 8-12 hr active work + 14d soak window 不適用（schema additive，apply 即 land）
PARALLEL: 完全獨立於 Packet B + C；可 immediately dispatch

CONTEXT (self-contained — sub-agent 不需再讀 AMD/PA spec)：
- V099 spec SSOT: srv/docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md（568 行）
- AMD §3.5 + PA spec §3 land 為依據；本 packet 純執行字面 SQL IMPL + Linux PG dry-run

DELIVERABLES:
1. 新建 file `sql/migrations/V099__autonomy_level_config.sql`，字面 IMPL V099 spec §2.1 + §2.2 + §2.3：
   - Phase 1: `CREATE SCHEMA IF NOT EXISTS system;` + COMMENT
   - Phase 1.5: PG ENUM `system.autonomy_level_enum AS ENUM ('CONSERVATIVE', 'STANDARD')` 用 DO block `IF NOT EXISTS pg_type`（per spec §2.1 line 87-96）
   - Phase 2: Table 1 `system.autonomy_level_config`（single-row, id=1, current_level ENUM, last_switched_at, switched_by, switch_reason, created_at, updated_at, updated_at trigger, cold seed ON CONFLICT DO NOTHING）
   - Phase 3: Table 2 `system.autonomy_level_switch_audit`（17 column 含雙時間戳 + actor + actor_role + level_before/after + 2fa fields + result enum + emergency_override fields + 3 notification status + notification_escalation_result）
   - Phase 4: REVOKE UPDATE/DELETE on PUBLIC + DO block REVOKE on trading_ai（per spec §2.3 line 319-326）
   - Phase 5: 3 index（idx_autonomy_audit_switched_at_utc DESC / idx_autonomy_audit_switched_at_local_override partial WHERE emergency_override=true / idx_autonomy_audit_actor_role compound）
   - All Guard A/B/C 套用 spec §2.1 + §2.2 + §2.3 line 107-130 / 157-170 / 209-240 / 343-356 字面

2. **NO local psql -f**（per spec §1.2 + memory `project_2026_05_02_p0_sqlx_hash_drift`）— V099 file write + git commit + push only；本地不 force apply。

3. Linux PG empirical dry-run 13 條（per spec §3.1 D1-D13）：
   - ssh trade-core → docker exec trading_postgres → psql -U trading_admin -d trading_ai
   - D1 (sqlx version baseline) → D2 (first apply + reflection) → D3 (二次 apply idempotency) → D4 (cold seed verify) → D5 (ENUM reject INVALID) → D6 (REVOKE + EXPLAIN ANALYZE Index Scan) → D7 (twofa FAIL audit row 必可寫) → D8 (switch_reason < 30 chars 必拒) → D9 (AV-9 atomic rollback) → D10 (AV-10 race PG advisory lock；2-session parallel test deferred to E4 regression) → D11 (B1 escalation `notification_escalation_result`) → D12 (B4 PG NOTIFY channel name verify) → D13 (雙時間戳一致性 < 1s)
   - **D5 + D6 + D11 + D12 + D13 為 highest risk** per spec §3.2；report 必引用 spec 字面理由

4. sqlx hash drift workflow:
   - V099 file commit + push
   - ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only"
   - 觸發 engine restart with OPENCLAW_AUTO_MIGRATE=1
   - sqlx 第一次 apply 寫 `_sqlx_migrations.checksum`
   - 若需修改 V099 file → 必走 `bin/repair_migration_checksum`（不可直接重 apply）

5. E4 regression covers AC-1 + AC-5 + AC-7 + AC-8（per PA spec §12 8 AC）：
   - AC-1: Fresh PG apply → `SELECT current_level FROM system.autonomy_level_config WHERE id=1` = 'CONSERVATIVE'
   - AC-5: Mock DB row corrupted / read fail → engine startup fail-closed → Level 1
   - AC-7: Mock 4 path lease emit at Level 2 → 4 independent lease row（no umbrella）
   - AC-8: Lease emit at Level 1 with autonomy_level snapshot → Level 切到 2 → lease lifecycle 走完 Level 1 行為

ACCEPTANCE CRITERIA:
- [AC-A1] V099 file ship + Linux PG D1-D13 全 PASS
- [AC-A2] sqlx hash drift 0 incident（peer review confirm 無本地 psql -f）
- [AC-A3] Engine restart 後 `system.autonomy_level_config` row id=1 current_level='CONSERVATIVE'
- [AC-A4] healthcheck `check_autonomy_level_switch_recent_24h()` 新增（per spec §5.2 + PA spec §13），可選 Sprint 1A-ε 補；本 packet 不阻
- [AC-A5] PA spec §12 AC-1/5/7/8 4 條 E4 regression PASS

HARD BOUNDARY CHECK:
- 不碰 `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET=1` / `live_reserved` / `authorization.json` 5 gate
- 不碰 5-gate live boundary / venue change 永鎖兩條（per AMD v2 §3.2/§3.3）
- 不碰 §Decision 2 5 條 fail-safe hard requirement runtime override（per AMD §Decision 2.5 compile-time only）

SIGN-OFF CHAIN: E1 IMPL → MIT Linux PG D1-D13 dry-run → E2 code review (Guard A/B/C 完整 + grep `runtime_failsafe_override`/`disable_failsafe` 零出現) → E4 regression 4 AC → CC 16-root walkthrough → PM final
ROLLBACK: NONE（additive schema；rollback 走 ADR-0006 forward-patch per spec §4）
GIT WORKFLOW: meta-doc 不動；只動 sql/migrations/V099__autonomy_level_config.sql；commit subject "feat(autonomy): V099 schema land Autonomy Level Toggle config + audit"；body 引 spec § + AMD §3.5；不加 [skip ci]（要跑 CI lint）；push origin + ssh trade-core git pull --ff-only

DELIVERABLE：
- File: `srv/sql/migrations/V099__autonomy_level_config.sql`
- Report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-XX-XX--v099_schema_land.md`（含 D1-D13 dry-run output snippet + EXPLAIN ANALYZE proof）
```

---

## §2 Packet B — GUI Autonomy Posture Sub-section Full Prompt Template

```
TASK: GUI Governance tab 加 Autonomy Posture sub-section — Level toggle UI + 14 path × 2 level panel + CONFIRM SWITCH typed-confirm

ROLE: E1a (Vanilla JS IMPL) + A3 (UI design sign-off) + E3 (Operator role auth path security review) + E2 (code review)
EST: 21-28 hr active work + node --check sign-off + e2e regression
PARALLEL: IMPL 階段獨立於 Packet A + C；e2e regression GREEN 需 Packet A V099 land 後 ~24h delay；建議 IMPL D+0 起即派但 sign-off gate D+2 after Packet A complete

CONTEXT (self-contained)：
- PA spec §5 GUI Integration full text: srv/docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md §5（line 524-706）
- Target file: srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-governance.html + governance-tab.js
- AMD v2 §Decision 3.1 三路通知 + §Decision 3.3 emergency halt + 24h undo

DELIVERABLES:
1. tab-governance.html 加新 sub-section `<section id="autonomy-posture">`（與既有 LAL toggle sub-section 同 tab 不同 sub-section）：
   - Header line: `Current Level: <X> (<Conservative|Standard>) - Last switched: <UTC> (local <TZ±>) by <actor> - Reason: <reason>` per PA spec §5.6
   - 14 path × 2 level 對照表（per PA spec §2.1 表）：可展開/折疊（A3 U2: Level 1→2 升級時預設展開；Level 2→1 降級時預設折疊）
   - Level 2 eligibility progress panel（C-1 ~ C-3 三條 readiness criteria + tooltip per PA spec §5.4）
   - Switch button（Level 2 disabled until evidence baseline 達標；button greyed-out + lock icon + tooltip 顯示具體 unmet 條件 + 達標進度 per FA U-FA-1）

2. governance-tab.js 加 7-step switch UI flow（per PA spec §5.2 line 533-628）：
   - [Step 1] Switch button click → modal 顯示當前 Level + 提議目標 Level + 14 path matrix 預設展開/折疊
   - [Step 2] Warning modal 雙向 differential 中文 copy（per spec §5.2 [2]，升級 / 降級兩段 wording）
   - [Step 3] Reason 輸入：Dropdown（4 預設選項）+ free text ≥30 字元必填
   - [Step 4] 2FA confirm: TOTP 6-digit code only（per A3 anti-pattern AP-5: 禁 'Remember device 30d' / 禁 hardware_key 單獨）
   - [Step 5] System verify 5 個 check（Operator role / 2FA / PG advisory lock / 24h cooldown / freeze state / emergency override rate / no-op assertion）
   - [Step 6] System execute: POST /api/v1/governance/autonomy-level/switch with HMAC chain；後端走 PG transaction wrap（per AV-9 atomic + spec §5.2 [6] BEGIN/UPDATE/INSERT/NOTIFY/COMMIT 偽碼）
   - [Step 7] Console banner 24h persistence + BroadcastChannel cross-tab + 3-stage fold pattern（initial 展開 / 1h 折 / 24h hide）

3. Typed-confirm phrase = `CONFIRM SWITCH`（per A3 U1，case-sensitive，兩方向統一）：
   - Phase 必 client + server 雙端 case-sensitive 驗
   - Mismatch → audit `result='typed_confirm_mismatch'`（informational，不算 attack；per spec §5.2 [2]）

4. Confirm button 5s delay-enabled（per A3 anti-pattern AP-1）：button initially disabled / 5s countdown enable

5. 8 anti-pattern AP-1..AP-8 寫入 spec（per PA spec §5.5 全表 line 678-689）：
   - AP-1: 5s delay-enabled / AP-2: 簡潔 phrase / AP-3: 雙向 differential warning / AP-4: dropdown + ≥30 free text / AP-5: TOTP only / AP-6: 24h banner persistence + BroadcastChannel + 3-stage fold / AP-7: 14 path matrix 升級展開 / AP-8: 雙時間戳 UTC + local

6. FastAPI route 後端：
   - `POST /api/v1/governance/autonomy-level/switch` with operator role auth + 2FA verify + HMAC sign + PG transaction wrap
   - `GET /api/v1/governance/autonomy-level/state` read-only current_level + last_switched_at + 三路通知 status
   - `GET /api/v1/governance/autonomy-level/eligibility` read C-1/C-2/C-3 達標進度（per PA spec §5.4 query）

7. 三路通知 emit hooks: Slack ≤10s + email ≤60s + Console banner ≤5s（per AMD §Decision 3.1）；任一失敗不阻其他兩路；audit notification_*_status 三 column

ACCEPTANCE CRITERIA:
- [AC-B1] tab-governance.html 加 Autonomy Posture sub-section ship；node --check PASS（per `feedback_gui_node_check_sop`）
- [AC-B2] 7-step UI flow 完整 + 14 path × 2 level panel 展開/折疊 work
- [AC-B3] Typed-confirm `CONFIRM SWITCH` case-sensitive 雙端驗
- [AC-B4] Confirm button 5s delay-enabled
- [AC-B5] Level 2 toggle disabled until C-1+C-2+C-3 三條 PASS（tooltip 顯示具體 unmet 進度）
- [AC-B6] 2FA backend timeout/unreachable → fail-closed `twofa_verify_result='FAIL', twofa_method='backend_unreachable'`（per AV-11）
- [AC-B7] PA spec §12 AC-2 + AC-3 + AC-4 + AC-6 4 條 E4 regression PASS：
  - AC-2: 第一次切換 audit trail 完整（actor + level_before/after + 2FA + reason + 雙時間戳 + 三路通知 status）
  - AC-3: 24h cooldown 強制（連續切換立即拒 + audit cooldown_blocked）
  - AC-4: Emergency override 30% trigger（mock 30d rolling rate → freeze 24h + monthly PM review）
  - AC-6: Freeze state active 期間 Level toggle 拒切換

HARD BOUNDARY CHECK:
- 5-gate Operator role HMAC 簽署兩 level 都 manual（per AMD §3.2/§3.3）— GUI 不可有 toggle 跳過 Operator role
- venue change 永鎖兩 level 都 manual — GUI 不可有 toggle 直接觸 venue change
- Vanilla JS only（per CLAUDE.md §七）— 不引入 React/Vue/Angular
- No fake-success（per feedback_no_dead_params）— GUI handler 必走 PG 真 write

SIGN-OFF CHAIN: E1a IMPL → A3 UX review (8 anti-pattern AP-1..AP-8 全防 + 14 path matrix 展開/折疊 correct + Chinese copy differential clarity) → E3 security review (Operator role auth path + HMAC chain + 2FA TOTP-only fail-closed) → E2 code review (node --check + governance-tab.js lexical scope grep per `feedback_gui_node_check_sop` W-AUDIT-7c 教訓) → A3+E2 adversarial review per `feedback_impl_done_adversarial_review` (高風險 GUI IMPL 必派) → E4 regression 4 AC → PM final
ROLLBACK: GUI 撤掉 sub-section + 後端 route 撤；對 V099 schema 無影響
GIT WORKFLOW: commit subject "feat(gui): autonomy-posture sub-section + 14-path level matrix + typed-confirm"；body 引 PA spec §5 + AMD §Decision 3.1/3.3；不加 [skip ci]（要跑 CI lint + node --check）

DELIVERABLE：
- Files: 
  - `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-governance.html`（加 sub-section）
  - `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/governance-tab.js`（加 7-step flow）
  - `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/api/governance_routes.py`（加 3 endpoint）
- Report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-XX-XX--gui_autonomy_posture_sub_section.md`（含 node --check output + screenshot）
```

---

## §3 Packet C — Rust SM-04 Patch Full Prompt Template

```
TASK: Rust SM-04 `RiskEvent::NotificationFailsafeTimeout` 新 variant + `Defensive` `active_de_risking` hook 擴充

ROLE: PA (design verify) + E1 (Rust IMPL) + E4 (regression test 35+ transition pair)
EST: 6-10 hr active work per AMD §9.8（不是 52-86 hr — 後者是 Wave 5 整體 cascade subset；本 packet 純 SM-04 patch）
PARALLEL: 完全獨立於 Packet A + B；可 immediately dispatch

CONTEXT (self-contained)：
- Target file: srv/rust/openclaw_core/src/sm/risk_gov.rs（940 行 verified）
- 既有 Defensive variant: line 180-187（active_de_risking=true / reduce_only=true / new_entries_allowed=false / emergency_stops=false）
- 既有 RiskEvent enum: line 53-78（23 variant；新增第 24）
- 35+ transition pair: line ~285-366
- AMD §9.8 PA spec §4.4 line 446-509 escalation ladder 設計 + §9.8 line 553-570 patch item table

DELIVERABLES:
1. `RiskEvent::NotificationFailsafeTimeout` 新 variant 加 enum（line ~53-78 RiskEvent enum + line ~83-110 impl RiskEvent as_str）：
   - Variant doc: "Three-channel notification (Slack/email/Console banner) all failed + 1h timeout → trigger SM-04 Defensive transition (per AMD-2026-05-21-01 v2 §Decision 3.1 + PA spec §4.4 Stage 3b)"
   - as_str: "notification_failsafe_timeout"

2. Defensive `active_de_risking` hook 擴充（既有 line 180-187 RiskLevel::Defensive 不動）：
   - 新增 active 鎖利擴充 function: `pub fn active_lock_profit_per_position(positions: &[Position], atr_buffer: f64) -> Vec<StopAdjustment>`
   - 對每個 active position：縮 SL 至 entry + ATR-based protective buffer（per PA spec §4.4 Stage 3b line 485-487）
   - 同步 sync 至 exchange-side conditional protection（per CLAUDE.md §二 原則 9 雙重防線）
   - 觸發後 emit lease "active_lock_profit_triggered_by_notification_failsafe"（per spec §4.4 line 488）

3. Transition rule 新增 35+ pair audit（per AMD §9.8 mitigation 理由 2「不破壞既有 35+ pair」）：
   - 新 RiskEvent::NotificationFailsafeTimeout 觸發 path: `(Normal|Cautious|Reduced, Defensive)` via NotificationFailsafeTimeout event
   - 補入 transition_rule pattern match: 
     ```rust
     (Normal | Cautious | Reduced, Defensive) if event == RiskEvent::NotificationFailsafeTimeout => Some(TransitionRule { ... reason: "notification_3way_fail_1h_timeout_auto_escalate" })
     ```
   - 既有 Defensive → CircuitBreaker / Defensive → ManualReview / Defensive → Reduced / Defensive → Cautious 4 條 transition 不動（不影響 escalation 既有路徑）
   - Recovery path: 必 operator manual unfreeze + 7d cooling（per PA spec §4.4 Stage 4 + Q4 拍板 30d→7d）— transition `Defensive → Normal` 加入 NotificationFailsafeTimeout 特例 require operator manual + 7d cooling check

4. Audit emit: `notification_escalation_result='auto_escalated_to_sm04_defensive'` 寫入 `system.autonomy_level_switch_audit`（per V099 spec §2.3 + PA spec §4.4 Stage 3b）；event 觸發時刻必 INSERT audit row 含 escalation 完整 chain

5. E4 regression 6 test case（per AMD §9.8 + PA spec §12 AC + §4.4 ladder Stage 1-4）：
   - T1: 三路通知全 FAIL → trigger NotificationFailsafeTimeout RiskEvent
   - T2: NotificationFailsafeTimeout + 1h timeout → SM-04 escalate Normal → Defensive transition success
   - T3: Defensive transition 後 active_lock_profit_per_position 縮 SL + sync exchange conditional
   - T4: Operator response within 1h → audit `notification_escalation_result='operator_responded'` + 不自動進 SM-04
   - T5: 7d cooling window 期間 Defensive → Normal transition 必拒
   - T6: 35+ existing transition pair regression（cargo test -p openclaw_engine sm/risk_gov + ensure new variant 不破壞既有 transition）

ACCEPTANCE CRITERIA:
- [AC-C1] RiskEvent::NotificationFailsafeTimeout variant 加 + as_str("notification_failsafe_timeout")
- [AC-C2] Defensive active_de_risking hook 擴充 active_lock_profit_per_position function 加 + ATR buffer 紀律
- [AC-C3] 35+ existing transition pair regression 全 GREEN（cargo test）— 既有 Defensive ↔ CircuitBreaker/ManualReview/Reduced/Cautious 4 條不變
- [AC-C4] 新增 Normal|Cautious|Reduced → Defensive via NotificationFailsafeTimeout pair 加 + reason text 對齊 spec
- [AC-C5] Audit notification_escalation_result 雙路徑驗（operator_responded / auto_escalated_to_sm04_defensive）
- [AC-C6] 7d cooling enforce on Defensive → Normal post-NotificationFailsafeTimeout（per spec Q4）

HARD BOUNDARY CHECK:
- Defensive `emergency_stops=false` 不改（保住 unrealized PnL，per spec line 482 「保住盈利」語義）
- CircuitBreaker `emergency_stops=true` 不誤用（per AMD §9.8 mitigation 理由 3）
- 不新增第 7 級 `ULTRA_DEFENSIVE`（per PA 拍板 §4.4 4 條理由 + Q3 RESOLVED Path A）
- §Decision 2.5 fail-safe compile-time hard-coded — active_lock_profit logic 必 compile-time 不接受 runtime TOML override

SIGN-OFF CHAIN: PA spec review confirm + E1 Rust IMPL → E2 code review (cargo clippy + 35+ transition pair grep + 反模式 grep `runtime_failsafe_override`/`disable_failsafe`零出現) → E4 regression 6 test case PASS → CC walkthrough 16-root principle (#3 AI → Lease → 復核 / #4 strategy 不繞 Guardian / #9 雙重防線 / #11 Agent autonomy 在 P0/P1 邊界內) → A3+E2 adversarial review (高風險 IMPL per `feedback_impl_done_adversarial_review`) → PM final
ROLLBACK: 撤 RiskEvent::NotificationFailsafeTimeout variant + active_lock_profit hook → 5+ transition pair revert；對 V099 schema 無影響
GIT WORKFLOW: commit subject "feat(sm-04): NotificationFailsafeTimeout RiskEvent + Defensive active_lock_profit hook"；body 引 AMD §9.8 + PA spec §4.4；不加 [skip ci]（要跑 cargo test + clippy）

DELIVERABLE：
- Files: 
  - `srv/rust/openclaw_core/src/sm/risk_gov.rs`（line 53-78 + line ~285-366 transition pair 補入 + 新 active_lock_profit_per_position function）
  - `srv/rust/openclaw_core/src/sm/risk_gov_tests.rs` or 既有 tests/ integration crate（加 T1-T6）
- Report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-XX-XX--sm04_notification_failsafe_timeout.md`（含 cargo test output + 35+ pair regression matrix）
```

---

## §4 三 Packet Dependency Graph

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  Packet A (V099 schema)          Packet B (GUI sub-section)              │
│       │                                │                                  │
│       │ schema land                   │ IMPL 階段 INDEP                  │
│       │                                │                                  │
│       │                                ▼                                  │
│       │                            E1a IMPL → A3+E3+E2 review            │
│       │                                │                                  │
│       └────► E4 regression GREEN ◄────┤                                  │
│              （AC-A1..A5 + AC-B1..B7）                                   │
│                                                                          │
│  Packet C (Rust SM-04)                                                   │
│       │                                                                  │
│       │ INDEP from A + B（Rust SM module 完全獨立）                     │
│       │                                                                  │
│       ▼                                                                  │
│   PA verify → E1 IMPL → E2 review → E4 6 test case → CC walkthrough     │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘

並行 wave 設計：
  D+0 (kick-off): A + B + C 三 packet 並行 dispatch
  D+0 ~ D+1 (8-12 hr): Packet A V099 ship + Linux PG dry-run
  D+0 ~ D+3 (21-28 hr): Packet B GUI IMPL + UX review
  D+0 ~ D+1 (6-10 hr): Packet C Rust SM-04 patch + E4 regression
  D+1 ~ D+2: 等 Packet A 完成 → Packet B 才能跑 e2e regression GREEN
  D+2 ~ D+3: PM final sign-off Wave 5 cascade IMPL DONE

Cross-packet 觸點：
  - A → B: V099 schema land 才能讓 B 後端 FastAPI route 真 INSERT/UPDATE
  - A → C: V099 audit table 才能讓 C 寫 notification_escalation_result audit row
  - B + C 之間: 三路通知 fail trigger 在 GUI 後端 emit / SM-04 接 RiskEvent；contract 對齊在 spec 字面，IMPL 各自獨立
```

---

## §5 Sprint 1A-ε 衝突分析

| Sprint 1A-ε 範圍 | V099 衝突 | Wave 5 並行 ceiling |
|---|---|---|
| **R4 cross-ADR 5C+4H** | NO 直接衝突 | 可並行（R4 不動 sql/migrations/）|
| **TW CHANGELOG/CONTEXT** | NO 衝突 | 可並行 |
| **MIT V099-V116** | 🚨 **V099 號碼直撞** | 必序列 — Sprint 1A-ε V099 占用 = Wave 5 V099；2026-05-22 spec 明示「V099 free」+ 2026-05-27 empirical verify V99 仍 free；但若 Sprint 1A-ε 內某 V099-V116 子任務 IMPL 階段提到 V099/V100/V101/V102/V103/V112，則 sqlx_migrations apply order 衝突 |
| **E5 Mac CI** | NO 衝突 | 可並行 |
| **A3 Wizard** | 🟡 GUI tab-governance.html 雙寫風險 | A3 Wizard 若改 tab-governance.html 同 file → 必序列；若改其他 tab 文件可並行 |

**Sprint 1A-ε P1+P2 already DONE 2026-05-22**（TODO line 62）；P3+ 補丁未明示 active 狀態 → 假設 P3 等可序列 dispatch。

**仲裁規則**（per TODO §15 #7）：「Wave-X2 V099 與 V112 LAL 同主路徑；不可同 Sprint 1A-ε 並行」— 字面要求 Sprint 1A-ε **全範圍** dispatch 完成或 pause 才能 trigger Wave 5。

**PA verdict**: 派發前必 ssh trade-core `grep -n "Sprint 1A-ε" srv/TODO.md` confirm Sprint 1A-ε 狀態；若 P1+P2 DONE + 無 P3+ active → Wave 5 派發無衝突；若 Sprint 1A-ε P3+ active 觸 sql/migrations/ → 必序列等 Sprint 1A-ε 完成。

**LG-3 V104 衝突**（TODO §1 line 46 + §15 #1）：
- V099 vs V104 號碼**不撞**（V99 vs V104）
- 但 ssh trade-core engine restart auto-migrate 是序列觸發 — Wave 5 V099 apply 後 LG-3 V104 apply 必後序
- LG-3 earliest dispatch ~2026-05-30 post 2 external gate（v56 P0 Layer B + 24h）
- 若 Wave 5 D+0 = 2026-05-27 → Wave 5 V099 apply 完成 by D+2 = 2026-05-29 → V104 D+5 dispatch 不衝

---

## §6 Sign-off Chain Detail

### Packet A (V099)
```
E1 IMPL DONE
  → MIT Linux PG empirical dry-run D1-D13 13 條（per V099 spec §3.1）
      AC: D2 reflection 字面對齊 + D5 ENUM reject INVALID + D6 EXPLAIN ANALYZE Index Scan + D11/D12/D13 highest risk verify
  → E2 code review
      AC: Guard A/B/C 完整 + idempotency 雙跑 + grep `runtime_failsafe_override`/`disable_failsafe` 零出現
  → E4 regression AC-1+5+7+8（per PA spec §12）
      AC: Fresh PG apply default CONSERVATIVE + cold start fail-closed Level 1 + 4 path individual lease + in-flight lease 不受切換影響
  → CC 16-root walkthrough
      AC: 原則 #6 fail-closed / 原則 #9 audit traceability / 原則 #11 portfolio autonomy 對 V099 對齊；9 安全不變量逐條
  → PM final sign-off
```

### Packet B (GUI)
```
E1a IMPL DONE
  → A3 UX review
      AC: 8 anti-pattern AP-1..AP-8 全防 + 14 path matrix 升級/降級展開/折疊 correct + Chinese copy differential clarity
  → E3 security review
      AC: Operator role auth path + HMAC chain + 2FA TOTP-only + AV-11 fail-closed on backend timeout
  → E2 code review
      AC: node --check PASS（per `feedback_gui_node_check_sop`）+ governance-tab.js lexical scope grep（per W-AUDIT-7c 教訓）
  → A3+E2 adversarial review（per `feedback_impl_done_adversarial_review` 高風險 GUI 強制）
      AC: 第三方獨立 catch SyntaxError + scope bug
  → E4 regression AC-2+3+4+6（per PA spec §12）
      AC: Audit trail 完整 + 24h cooldown 強制 + emergency override 30% trigger + freeze 期間禁切換
  → PM final sign-off
```

### Packet C (Rust SM-04)
```
PA spec design verify confirm（本 packet master = PA confirm）
  → E1 Rust IMPL DONE
  → E2 code review
      AC: cargo clippy 零 warning + 35+ transition pair grep no-regress + `runtime_failsafe_override`/`disable_failsafe` grep 零出現
  → E4 regression 6 test case T1-T6
      AC: 三路 fail → NotificationFailsafeTimeout / 1h timeout → Defensive transition / active_lock_profit 縮 SL + exchange sync / operator response 路徑 / 7d cooling enforce / 35+ existing pair regress GREEN
  → CC 16-root walkthrough
      AC: 原則 #3 AI→Lease→復核 / 原則 #4 strategy 不繞 Guardian / 原則 #9 雙重防線 / 原則 #11 P0/P1 邊界內 autonomy
  → A3+E2 adversarial review（per `feedback_impl_done_adversarial_review` 高風險 Rust IPC schema 強制）
      AC: 第三方獨立 catch transition matrix corner case
  → PM final sign-off
```

### Wave 5 final closure
```
Packet A + B + C 各自 PM sign-off DONE
  → R4 cross-ADR audit（per AMD §9.4 + spec §9.6）— 5 module ADR cross-ref verify（ADR-0034/0040/0041/0042/0043/0044/0045）
  → TW docs/README.md + amendments index update（per AMD §9.6）
  → PM Wave 5 closure log + memory append
```

---

## §7 Risk + Mitigation

| Risk | Likelihood | Mitigation |
|---|---|---|
| **R1**: sqlx hash drift incident on V099 apply | M | Pre-deploy SOP per spec §1.2 + memory P0；E1 dispatch packet 明示禁本地 psql -f |
| **R2**: GUI sub-section 改 tab-governance.html 觸 W-AUDIT-7c lexical scope shadow bug | M | E2 強制 node --check + governance-tab.js lexical scope grep + A3+E2 adversarial review per `feedback_impl_done_adversarial_review` |
| **R3**: Rust 35+ transition pair regression 漏 case | L | E4 6 test case 矩陣 covers Normal/Cautious/Reduced → Defensive 新路徑 + 既有 Defensive ↔ 4 條 unchanged verify |
| **R4**: Sprint 1A-ε P3+ active 同時派 → sql/migrations/ collide | L-M | 派發前 ssh trade-core grep Sprint 1A-ε 狀態 + 確認 P3+ 無 active |
| **R5**: LG-3 V104 dispatch timing 與 Wave 5 V099 apply order conflict | L | Wave 5 D+0=2026-05-27 → V099 apply by D+2；LG-3 V104 earliest 2026-05-30；無衝突 |
| **R6**: Three-channel notification 三路 fail trigger 同時觸發其他 RiskEvent → escalate 路徑碰撞 | L | PA spec §4.4 single-fire principle + audit single row notification_escalation_result；E4 T2 必驗 |
| **R7**: GUI Confirm button 5s countdown 與 typed-confirm 字面互動 corner case | L | A3 UX review 強制 + E4 e2e regression |

---

## §8 PA 推薦派發順序

**Recommended order**（per PA 拍板）:
1. **D+0 09:00** — operator final sign-off Wave 5 IMPL roadmap
2. **D+0 09:30** — 主會話 ssh trade-core fetch + grep Sprint 1A-ε P3+ 狀態 confirm 無衝突
3. **D+0 10:00** — 三 packet 同時派發（A / B / C）
4. **D+1 evening** — Packet A V099 schema land complete + Linux PG D1-D13 全 PASS
5. **D+1 evening** — Packet C Rust SM-04 patch complete + E4 6 test case PASS
6. **D+2 morning** — Packet B GUI IMPL DONE + node --check PASS
7. **D+2 afternoon** — Packet B e2e regression GREEN (相依 Packet A schema 已 land)
8. **D+3 morning** — R4 cross-ADR audit + TW docs index
9. **D+3 afternoon** — PM Wave 5 closure + memory log

**衝突警示再確認**：派發前主會話必 ssh trade-core `grep -nE 'Sprint 1A-ε' srv/TODO.md` confirm Sprint 1A-ε P3+ 未 active。

---

*OpenClaw / 玄衡 Arcane Equilibrium PA Workspace — Wave 5 Dispatch Packet Master · 2026-05-27 · PA*

*Self-contained 三 packet template + dependency graph + Sprint 1A-ε conflict analysis + sign-off chain detail*
