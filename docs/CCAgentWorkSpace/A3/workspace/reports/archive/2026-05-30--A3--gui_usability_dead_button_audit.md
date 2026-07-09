# A3 GUI Usability / Dead-Button / Fake-Success Audit — 2026-05-30 (cold audit RE-RUN)

> PERSISTENCE NOTE (PM): A3(default) ran with a read-only toolset and returned the full report inline; PM(default) persisted it verbatim. Authorship = A3(default); persistence = PM(default).

**Prior audit date label:** 2026-05-17 (executed 2026-05-29) · **Actual audit time:** 2026-05-30 · **Baseline freeze:** 187704f6 · **Scope:** Canonical FastAPI OpenClaw Control Console static frontend — all tabs.

## Pre-Check Result
Report did not exist before this run. Proceeding.

## Prior Remediation Status (Wave3 7909ca3d holds check) — ALL 8 prior findings REMEDIATED + DEPLOYED
- **A3-GUI-001 (P1, Global Mode success on Rust sync fail):** FIXED. `control_ops.py:533-598` explicit IPC `set_system_mode`, live-capable mode requires `get_state` readback, mismatch → `result_status="partial_failure"`, exception → `partial_failure`+`rust_synced=False`. INV-A2 referenced line 534. `except: pass` gone.
- **A3-GUI-002 (P1, Live Start active after swallowed IPC fail):** FIXED. `live_session_endpoints.py:168` `all_five_live_gates_ok(actor, require_authz=True)` first gate; IPC `resume_paper` fail (line 196) → `_set_execution_authority(None)` + HTTP 502. `tab-live.js:1038` `classifyLiveMutation(d)`.
- **A3-GUI-003 (P1, Emergency Stop/Close-All success on partial fail):** FIXED. `tab-live.js:1096` + `:1127` use `classifyLiveMutation`; residual → persistent `ocResidualRiskBanner`; typed-confirm `'EMERGENCY STOP'`/`'CLOSE ALL'`.
- **A3-GUI-004 (P1, Safe Recheck/Demo Validate stamps readiness):** FIXED. `control_ops.py:184-186` sets `demo_last_action_result="manual_mark"`, evidence `manual_mark`, reason `evidence_manual_mark_not_verified`.
- **A3-GUI-005 (P2, Paper/Demo Stop success on residual errors):** FIXED. `paper_trading_routes.py:430-447` sets `action_result="partial_failure"` when errors non-empty; `tab-paper.html:384` `classifyLiveMutation`.
- **A3-GUI-006 (P2, Scheduled Restart live button for 410-disabled endpoint):** FIXED. `tab-settings.html:157-174` disabled-state card (`disabled aria-disabled="true"`) + ref `restart_all.sh`.
- **A3-GUI-007 (P2, Governance Quick Status calls undefined `loadGovernance()`):** FIXED. `tab-governance.html:247` now `onclick="loadAll()"` (defined `governance-tab.js:1780`). (Stale comment at `tab-governance.html:1060-1061` still references `loadGovernance()` — cosmetic, see below.)
- **A3-GUI-008 (P2, Autonomy Posture jargon):** FIXED. `autonomy-posture.js:11-49` label maps; raw enums in tooltip; `autonomyPlainWithRaw()`.

## New Surfaces Audited (2026-05-29/30 delta)

### Tab: Earn 理財 (`tab-earn.html` + `earn-tab.js`) — NEW write surface
- **Rust Authority [FACT]:** `earn_routes.py:1178` `_ipc_call_strict(_IPC_METHOD_PROCESS_EARN_INTENT, ...)` — strict Rust IPC (Rust `earn_router.rs` 9-gate). Python 5-gate preflight before IPC. Goes through Rust authority (CLAUDE §七). ✓
- **Anti-fake-success [FACT]:** success only when `ipc_result["submitted"]==True`; rejection → `rejected_reason`+`submitted=False`+60s cooldown; frontend `earn-tab.js:552-569` branches on `data.submitted`.
- **Typed-confirm [FACT]:** `earn-tab.js:37-41` `'CONFIRM EARN STAKE $<amount> USDT'` (Math.floor), backend re-validates `earn_routes.py:1142`.
- **5-gate disable-before-submit [FACT]:** `earn-tab.js:361-362` blocks submit if `stage_0r_status !== 'PASS'`.

**Finding A3-GUI-009 — Earn Tab Wave D Pending State not clearly distinguished from full success (NEW, P2)**
- Label: INFERENCE (backend confirmed; frontend not fully verified read-only) · Severity: P2
- Path: `earn-tab.js:552-562` + `earn_routes.py:1197`
- Evidence: backend returns `wave_d_pending=True` when `intent_id=None && movement_id=None && submitted=True`; frontend toasts `'✓ Earn stake 已提交（intent_id=?；movement_id=?）'` — `'?'` shown (honest) but does not branch on `wave_d_pending`.
- Impact: during Wave D transition operator may read `'✓ 已提交'` as completed when IntentProcessor hasn't processed the movement. Not fake-success (Bybit IPC called), but intermediate state not communicated.
- Why real: `wave_d_pending` field explicitly designed (line 1197) to signal incomplete wiring; toast conflates with success.
- Fix direction: branch on `data.wave_d_pending===true` → distinct orange warn toast. Fix owner: E1(worker). Verifier: E2(explorer)+A3.

### Canary Cohort Status (`canary-tab.js` in `tab-governance.html`)
- Typed-confirm `'PROMOTE'` [FACT] `canary-tab.js:334`; success only when `res.data.stage_log_id` is a number [FACT] `:400`; Stage 4 guard, promote button only `currentStage 0..2` [FACT] `:167`. No fake-success.

## Stale Comment Advisory (cosmetic, not a finding)
`tab-governance.html:1060-1061` comment still references `loadGovernance()`; actual loader is `loadAll()`. Misleading to maintainers (was the prior dead-button root cause). E1 one-liner during next governance-tab touch.

## Node --check Note
Per GUI sign-off SOP, `node --check` on `earn-tab.js`, `canary-tab.js`, `autonomy-posture.js`, `governance-tab.js`, `tab-live.js` must be confirmed by E1/E2 before any next Wave deploy touching these files. Static grep showed no obvious brace imbalance, but static count ≠ node --check.

## Write Surface Rust-Authority Confirmation
| Write Surface | Rust Authority | Evidence |
|---|---|---|
| Global mode switch | YES (IPC + readback) | `control_ops.py:554,561` |
| Live session start | YES (5-gate + IPC resume, fail-closed) | `live_session_endpoints.py:168,194` |
| Live emergency stop | YES (IPC + residual banner) | `tab-live.js:1093` |
| Live close-all | YES (IPC + residual banner) | `tab-live.js:1123` |
| Paper stop | YES (IPC + partial_failure contract) | `paper_trading_routes.py:410-447` |
| Earn stake | YES (strict Rust IPC, 9-gate Rust side) | `earn_routes.py:1178` |
| Canary manual promote | YES (lease, stage_log_id evidence) | `canary-tab.js:400` |
| Demo validate | Python-only by design (manual_mark, not claimed as Rust gate) | `control_ops.py:184` |

## Summary
- Counts: **P0=0 · P1=0 (all prior P1 FIXED) · P2=1 OPEN (A3-GUI-009) · cosmetic 1**. Score 8.5/10.
- Prior remediation HELD: YES (Wave3 7909ca3d). New Earn tab = genuine Rust-authority write path.
- Blockers: A3-GUI-009 → E1 frontend fix (no architecture decision). Stale comment → E1 cleanup. node --check → E1/E2 before next deploy.
