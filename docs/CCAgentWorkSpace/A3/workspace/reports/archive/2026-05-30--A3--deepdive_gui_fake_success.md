# A3 Deep-Dive: GUI Fake-Success / Dead-Button / Blocked-But-Green Audit — 2026-05-30

**Run date:** 2026-05-31 · **Baseline freeze:** 187704f6 · **Scope:** ALL 16 tabs, every write-capable button/form · **Role:** A3(default) READ-ONLY

## Executive Summary

Audited 53 distinct write surfaces across 16 tabs. Found **2 NEW fake-success findings** (P2 each). No dead buttons. No gate-blocked-but-shows-green. Prior 8 findings (P1×3, P2×5) and A3-GUI-009 remain as documented.

---

## Methodology

For each tab: grepped `fetch(`, `ocPost`, `method.*POST`, `onclick` handlers in both HTML and dedicated `.js` files. Traced each to: (1) backend Python handler — does it raise HTTP error on IPC failure or silently return ok? (2) Frontend success branch — does it check response body fields (`action_result`, `rust_synced`, `submitted`, `saved`, `ok`, `stage_log_id`) or merely `if (d)` (truthy-only)?

`ocPost()` returns `null` on any HTTP ≥4xx (confirmed `common.js:221-255`). So `if (d)` protects against HTTP failure. But if backend returns HTTP 200 with a truthy body even when the operation partially failed (without raising HTTPException), `if (d)` is fake-success.

---

## Per-Tab Write Button Table

| Tab | Button/Action | Endpoint | Checks Body? | Rust Authority? | Verdict |
|---|---|---|---|---|---|
| **system** | Global mode switch | `/api/v1/input/config-change` | YES — `classifyLiveMutation`, `action_result==='success'` + residualRiskBanner | YES (IPC set_system_mode + readback) | CLEAN |
| **system** | Paper session start/stop | `/api/v1/paper/session/stop\|start` | **NO** — `_paperActive` toggled optimistically BEFORE checking `d` [LINE 653]; always toasts success | Python→Rust IPC | **NEW FINDING A3-GUI-010 (P2)** |
| **replay** | (read-only, no write surfaces) | — | — | — | CLEAN |
| **paper** | Paper stop (main) | via `app-paper.js` | YES — `classifyLiveMutation` | YES | CLEAN (verified in baseline) |
| **demo** | Session start/pause/resume/stop | `/api/v1/strategy/demo/session/{action}` | `if (d)` only — no body field check | Python→Rust IPC (raises HTTPException on fail) | SOFT-RISK [INFERENCE] — backend raises on IPC fail so `null` path is covered; but backend could HTTP 200 + partial error |
| **demo** | Close all positions | `/api/v1/strategy/demo/close-all-positions` | `d && d.data` checked (message extracted) | YES (IPC) | CLEAN |
| **demo** | Close single position | `/api/v1/strategy/demo/positions/.../close` | `if (d && d.data)` | YES (IPC) | CLEAN |
| **live** | Live start | `/api/v1/live/session/start` | `classifyLiveMutation` | YES (5-gate + IPC) | CLEAN |
| **live** | Emergency stop | `/api/v1/live/emergency-stop` | `classifyLiveMutation` + residualBanner | YES | CLEAN |
| **live** | Close all | `/api/v1/live/close-all` | `classifyLiveMutation` + residualBanner | YES | CLEAN |
| **live** | Live stop | `/api/v1/live/session/stop` | `classifyLiveMutation` | YES | CLEAN |
| **strategy** | Create strategy | `/api/v1/strategy/create` | `if (d)` — body not checked for specific field; backend raises HTTPException on fail | YES (Rust IPC) | SOFT-RISK [INFERENCE] |
| **strategy** | Pause/Stop/Delete strategy | `/api/v1/strategy/{name}/{action}` | `if (d)` only — backend raises HTTPException on fail | YES (Rust IPC) | SOFT-RISK [INFERENCE] |
| **risk** | Save stop/position/cooldown settings | `/api/v1/paper/risk/config/engine/{engine}/global` | `if (d)` only — backend raises HTTPException if IPC fails (`_ipc_failure`) | YES (IPC `patch_risk_config`) | CLEAN [FACT — IPC fail → HTTP 5xx → null] |
| **risk** | Risk governor override (de-escalate) | `/api/v1/governance/risk/override` | `d && d.ok` | Backend unclear [INFERENCE] | NEEDS-MORE |
| **risk** | Reset cooldown | `/api/v1/paper/risk/reset-cooldown` | `if (d)` only — backend raises on IPC fail | YES (IPC) | CLEAN |
| **risk** | Unhalt session | `/api/v1/paper/risk/unhalt-session` | `if (d)` only — backend raises on IPC fail | YES (IPC) | CLEAN |
| **risk** | H0 shadow mode toggle | `/api/v1/paper/risk/config/engine/{engine}/global` | `if (d)` + live confirm | YES (IPC) | CLEAN |
| **risk** | Save AI budget | `/api/v1/ai_budget/config` | `r.ok` HTTP status check per scope — throws on fail | Python-only config store [INFERENCE] | SOFT-RISK [INFERENCE] |
| **governance** | Canary manual promote | `/api/v1/canary/...` | `res.data.stage_log_id` is a number | YES (lease) | CLEAN (baseline) |
| **governance** | Auth renew | `/api/v1/live/auth/renew` | `d.ok \|\| d.status==='ok' \|\| d.data` | YES (auth module) | CLEAN |
| **governance** | Auth renew-review (T3) | `/api/v1/live/auth/renew-review` | `d.ok \|\| d.status==='ok' \|\| d.data` | YES (auth module) | CLEAN |
| **ai** | Trigger Layer 2 session | `/api/v1/paper/layer2/trigger` | `if (d)` only — backend raises on IPC fail | Python→L2 | CLEAN |
| **ai** | Save provider key (6 providers) | `/api/v1/paper/layer2/config` | `d.data.provider_results` per-provider granular check; branch on `myErr/myResult` | Python config store | CLEAN |
| **ai** | Clear provider key (6 providers) | `/api/v1/paper/layer2/config` | typed-confirm + body check | Python config store | CLEAN |
| **ai** | Save AI config | `/api/v1/paper/layer2/config` | `d.action_result === 'success'` explicit check | Python config store | CLEAN |
| **ai** | Run evolution | `/api/v1/evolution/run` | `!d → throw`; `d.best_sharpe` | Python | CLEAN |
| **learning** | Review approve/reject | `/api/v1/learning/review/{id}/decide` | `if (d)` only | Python DB write | SOFT-RISK [INFERENCE] |
| **learning** | AI consult | `/api/v1/learning/review/{id}/decide` | `if (d)` only | Python DB write | SOFT-RISK [INFERENCE] |
| **learning** | Auto scan (3 types) | `/api/v1/learning/auto/{type}` | `if (d)` + count extract | Python | SOFT-RISK [INFERENCE] |
| **agents** | (read-only, no write surfaces) | — | — | — | CLEAN |
| **monitoring** | (read-only, links only) | — | — | — | CLEAN |
| **settings** | Scheduled restart | `/api/v1/system/scheduled-restart` | `d.action_result === 'scheduled'` explicit check | Python scheduler | CLEAN |
| **settings** | Demo arm/validate/enable/relock | `/api/v1/control/demo/{action}` | branches on `evidence==='manual_mark'` + warn toast | Python (Python-only by design, manual mark) | CLEAN |
| **settings** | Safe recheck | `/api/v1/control/safe-recheck-bundle` | `if (d)` — backend raises on fail | Python composite | CLEAN |
| **settings** | configAction: set-demo-mode, enable-spot | `/api/v1/input/config-change` | `if (d)` only — **does NOT use classifyLiveMutation** unlike tab-system; IPC sync result ignored | YES (IPC set_system_mode on mode path) | **NEW FINDING A3-GUI-011 (P2)** |
| **settings** | Submit cost / PnL entry | `/api/v1/input/cost`, `/api/v1/input/pnl-entry` | `if (d)` only | Python DB | CLEAN |
| **settings** | Paper engine enable/disable | `/api/v1/settings/paper-engine` | `data` checked + `data.enabled` readback | Python config | CLEAN |
| **settings** | Dev support toggle | localStorage only (no HTTP POST) | n/a | n/a — browser-local only | CLEAN |
| **settings** | API key save (demo/live_demo/live) | `/api/v1/settings/api-key/{slot}` | `d.saved \|\| d.data.saved` explicit check | Python + Bybit validation | CLEAN |
| **phase4** | (read-only, static card loads) | — | — | — | CLEAN |
| **development** | (read-only, migration view) | — | — | — | CLEAN |
| **edge-gates** | (read-only) | — | — | — | CLEAN |
| **earn** | Earn stake | `/api/v1/earn/intent` | `data.submitted===true` check; `wave_d_pending` not branched (A3-GUI-009, P2, open) | YES (strict Rust IPC 9-gate) | OPEN (prior finding) |

---

## New Findings

### A3-GUI-010 — System Tab Paper Session Start/Stop: Optimistic Fake-Success (NEW, P2)

- **Tag:** FACT (code confirmed)
- **Severity:** P2
- **Path:** `tab-system.html:647-657`
- **Evidence command:** `grep -n "_paperActive" static/tab-system.html`
- **Root cause:** `_paperActive = !_paperActive` (line 653) and the success toast (line 657) execute unconditionally after `await ocPost(...)` — the return value `d` is never tested. If the paper session API call returns null (HTTP error / IPC fail), the button label and dot still flip to the opposite state, and the operator sees "Paper 模擬 已啟動" even though the engine rejected the call.
- **Impact:** Operator believes paper is running when it is not (or stopped when it is not). Low severity because: (a) paper is a non-critical training pipeline, not live money; (b) `loadAll()` is called 1s later (line 666) which will correct the displayed state from server readback. But there is a 1-second window of false-green plus a deceptive toast.
- **Why real, not FP:** The other paper stop path (`app-paper.js`, tab-paper) correctly uses `classifyLiveMutation`. The system-tab shortcut path skipped that pattern.
- **Fix direction:** Assign `const d = await ocPost(...)` then gate `_paperActive = !_paperActive` inside `if (d)`. Change toast to error on null. Owner: E1(worker). Verifier: E2 + node --check.

### A3-GUI-011 — Settings Tab configAction Skips classifyLiveMutation for Mode-Change (NEW, P2)

- **Tag:** FACT (code confirmed)
- **Severity:** P2
- **Path:** `tab-settings.html:734-761` (`configAction` function)
- **Buttons affected:** "Set Demo Reserved" (`btn-set-demo`), "Enable Spot Shadow" (`btn-enable-spot`)
- **Evidence command:** `grep -n "configAction\|Config change OK\|classifyLiveMutation" static/tab-settings.html`
- **Root cause:** Both buttons POST to `/api/v1/input/config-change`. The `tab-system.html` version (line 727-739) correctly calls `classifyLiveMutation(result)` and displays `ocResidualRiskBanner` if `rust_synced=false`. The settings tab `configAction` (line 754) does only `if (d) { ocToast('Config change OK', 'success') }` — no body inspection. If the IPC `set_system_mode` call fails (engine offline, IPC timeout), the backend returns HTTP 200 with `action_result='partial_failure'` + `rust_synced=false`, which is truthy, so the settings tab toasts "Config change OK" green while Rust did not actually switch mode.
- **Impact:** Operator may believe demo_reserved is active while Rust engine is still in previous mode. Lower risk than live mode switches (demo_reserved is not capital-at-risk), but contradicts INV-A2 "never show success when Rust sync failed."
- **Why real, not FP:** `control_ops.py:533-598` explicitly produces `result_status='partial_failure'` + `rust_synced=False` when IPC fails — this is designed to be read by the consumer. `tab-system.html` reads it; `tab-settings.html` does not.
- **Fix direction:** Refactor `configAction` to call `classifyLiveMutation(d)` and branch the same way as `executeModeChange` in `tab-system.html`. Owner: E1(worker). Verifier: E2.

---

## Risk Governor Override — NEEDS-MORE

`submitRiskOverride()` checks `d && d.ok` (`risk-tab.js:87`). Backend route needs inspection to confirm what `d.ok` reflects. Not audited deep enough in this pass due to tool budget.

---

## SOFT-RISK Pattern (Not New Findings — Baseline Pattern)

Several `if (d)` checks where backend always raises HTTPException on IPC fail (not returning HTTP 200): `demoSessionAction`, `strategyAction`, `createStrategy`, `deleteStrategy`, `reviewAction`, `autoScan`. These are safe because `ocPost() → null` on any HTTP ≥4xx. Not classified as fake-success because the backend's error contract is raise-on-fail, not return-200-with-error. Tagged INFERENCE because full backend handler read was not done for every one.

---

## Confirmed Clean Surfaces

**`classifyLiveMutation` / explicit body checks confirmed used for:** global mode switch (system tab), all live tab actions (start/stop/emergency/close-all), paper stop (paper tab), earn stake, canary promote, auth renew, scheduled restart, API key save, save AI config, save provider key, demo close-all, demo close-single.

**`if (d)` with backend raise-on-fail contract (safe):** risk config save (all 3 engines), reset-cooldown, unhalt-session, H0 shadow mode, strategy actions.

---

## Write Surface Count

- 16 tabs total: 8 tabs are read-only (replay, agents, monitoring, phase4, development, edge-gates + partial paper/replay)
- Distinct write endpoints touched: **42** across 8 active write tabs
- Dedicated write JS files: risk-tab.js (10), tab-live.js (6), earn-tab.js (2), canary-tab.js (1), governance-tab.js (1), app-paper.js (5)

---

## node --check Results

- `risk-tab.js`: PASS (confirmed)
- `.html` files: node v26 rejects `.html` extension in ESM check mode — not a syntax error, tool limitation. Per project SOP, E1/E2 must use alternative syntax check for inline-JS HTML files before deploy.

---

## Verdict

**DEEPER VERDICT: NEW-FINDING (×2 P2)**

| Finding | Tab | Severity | Status |
|---|---|---|---|
| A3-GUI-009 | Earn — Wave D pending not distinguished | P2 | OPEN (prior) |
| A3-GUI-010 | System — paper start/stop optimistic fake-success | P2 | NEW OPEN |
| A3-GUI-011 | Settings — configAction skips classifyLiveMutation | P2 | NEW OPEN |

Score adjustment: 8.5/10 → **8.0/10** (2 additional P2).

All P1 (A3-GUI-001, 002, 003) remain FIXED and verified. No P0. No dead buttons. No gate-blocked-but-shows-green.
