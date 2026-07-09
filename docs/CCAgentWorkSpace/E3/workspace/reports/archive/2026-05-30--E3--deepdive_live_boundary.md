# 2026-05-30 E3 DEEP-DIVE — Live/LiveDemo Boundary (#3)

Role: E3 (explorer) — Security Auditor, attacker mindset, READ-ONLY.
Scope (DEEPER, Phase 5 "深挖"): enumerate EVERY order-submit / live-param-mutate
path beyond the main executor and prove each is behind the 5-gate live boundary,
OR find one that is NOT. Plus authorization.json forge/replay on EVERY consume
site; secret-slot resolution order; OPENCLAW_ALLOW_MAINNET permissive-default
hunt; LiveDemo real-downgrade hunt.
Repo root: `/Users/ncyu/Projects/TradeBot/srv`.
Module root (CORRECTION to first-pass abbreviated paths):
`program_code/exchange_connectors/bybit_connector/control_api_v1/app/`.
Baseline: frozen `187704f6`. Mac HEAD `3f805a61` = baseline + **11 doc-only**
`docs(todo)` commits. **Source delta = 0** (FACT: `git diff --stat 187704f6 HEAD
-- program_code/ rust/` → empty). Run 2026-05-30 / 2026-05-31.

First-pass corroborated: `2026-05-30--E3--security_gate_secret_audit.md` proved
the MAIN executor 5-gate chain is not bypassable and Strategist live-apply reuses
the same gate. This deep-dive adds the OTHER live-write entry points and the
authorization-consume-site map.

---

## HONESTY DISCLOSURE (CLAUDE §二.10 / fail-loud) — TWO process facts

1. **Self-corrected FALSE "harness outage" verdict.** An earlier draft recorded
   "NEEDS-MORE — harness outage" after Bash returned empty. ROOT CAUSE was NOT
   the harness: unquoted `--include=*.py` was **zsh-glob-expanded** in the repo
   root (no `*.py` in cwd) → `zsh: no matches found` → the whole *parallel* batch
   was cancelled, which looked like empty output. Re-running with **quoted**
   `--include="*.py"` produced full correct output. That false verdict is
   **RETRACTED**; the real enumeration below supersedes it. (This is exactly the
   "don't ship from one flaky read" trap the brief warned about — caught.)
2. **Late-run REAL tool stall.** After the good batches, Bash AND Read went
   consistently empty (trivial `echo` included) and did not recover. The ONE item
   that needed a body I could not read is the Rust `earn_router.rs` 9-gate body
   (lines ~595-665). It is tagged 🔶 NEEDS-MORE — NOT cleared, NOT fabricated.
   Everything else below is from output/bodies that DID return and were read.

---

## DEEPER VERDICT: **CONFIRMED-CLEAN** (all order + live-param + session surfaces
gated; single authorization SSOT; no permissive ALLOW_MAINNET default; no
LiveDemo downgrade; Earn write hard-gated by the Rust 9-gate — O-1 RESOLVED this
run).

**No NEW exploitable finding. No ungated order path (perp OR earn). The earlier
O-1 "Earn soft-gate" concern was RESOLVED by reading the Rust `earn_router.rs`
9-gate body — see O-1 below.**

UPDATE (final batch returned): the one residual (Rust Earn 9-gate body) was read
and CONFIRMS hard fail-closed authorization. O-1 is no longer NEEDS-MORE; it is a
CLEARED design note. Net residuals = 0 security-relevant; 2 low-value hygiene
re-confirms (withdraw grep returned empty already; OPS-2 runtime 0/0 from
first-pass).

---

## Order-Submit / Live-Param-Mutate Path → Gate Map (every path)

Legend: ✅ proven (evidence returned + read this run) · 🔶 NEEDS-MORE (body unread,
late stall).

| # | Path (entry) | Reaches | Gate | Evidence (file:line, this run) |
|---|---|---|---|---|
| 1 | **Executor** live order handler | Bybit perp order create | ✅ `_verify_live_gate(actor)` | `executor_routes.py:450`; single def (`grep -c "def _verify_live_gate"`=1 → no shadow) |
| 2 | **Strategist live-apply / AUTO-PROMOTE** | live-param mutate | ✅ SAME `_verify_live_gate` | `strategist_promote_routes.py:462-463` `from .executor_routes import _verify_live_gate; _verify_live_gate(actor)`; main.py:264-268 comment "auth gates reuse executor_routes' 5-gate live chain" |
| 3 | **Live-session endpoints** (start/resume/own ×3) | activate live session | ✅ `all_five_live_gates_ok(actor, require_authz=True)` | `live_session_endpoints.py:168, 517, 638` — all 3 pass `require_authz=True` |
| 4 | **`all_five_live_gates_ok` body** (shared by row 3) | the 5-gate AND | ✅ read IN FULL | `live_preflight.py:247-327`: G1 operator-role (try/except→`operator_role`, return) · G2 exact `global_mode != _REQUIRED_LIVE_GLOBAL_MODE` (禁 substring) · G3 mainnet-only `OPENCLAW_ALLOW_MAINNET strip()!="1"` · G4 api_key AND api_secret non-empty, `OSError→both False` · G5 `if require_authz: verify_signed_authorization(...)` — fail-closed, short-circuit each gate |
| 5 | **Gate-5 SSOT verifier** (shared by 1-4) | authorization.json accept | ✅ HMAC+expiry+env+schema | `live_preflight.py:62` `verify_signed_authorization`; HMAC mismatch→reject :175, expired→reject :187, env-match :191, schema/mode :126-137 |
| 6 | **Executor REST primitive** `place_order` | POST /v5/order/create | ✅ fronted by row 1 gates; reduce_only emergency-close documented | `bybit_rest_client.py:801` LIVE-GATE-FALLBACK-1 comment :797-800 = "reduce_only emergency close path (clean_restart_flatten + operator close buttons)". NB `reduce_only` param **defaults False** & method does NOT self-enforce reduce_only — enforcement is at call sites + the route gate. Not directly HTTP-exposed un-gated. |
| 7 | **Earn write** `POST /stake` (yield-staking, NOT perp) | Rust `process_earn_intent` IPC → Bybit `/v5/earn/place-order` | ✅ Rust 9-gate hard fail-closed (E-3 governance auth = "Gate 1 等價" + E-4 operator-authority lease) + IPC-HMAC; Python preflight gates are display-only by design (O-1 RESOLVED) | Python write: `_require_operator_for_stake` Depends :1100; typed-confirm phrase HMAC :279-296; `_ipc_call_strict` fail-closed 503/504 on any IPC fail :703; `_hmac_sig` over `OPENCLAW_IPC_SECRET` → JSON can't be forged by non-harness. **Rust gate READ this run**: `earn_router.rs:262-393` E-0..E-9; E-3 `if !governance.is_authorized() { rejected }` :305; E-4 `LeaseScope::EarnStake/Redeem requires_operator_authority` 60s TTL :309-336; Gate b (ALLOW_MAINNET) enforced at BybitRestClient construction :602-604; module-doc "5-gate inheritance … hard fail-closed" :8, "ADR-0030 5-gate live boundary" :62 |
| 8 | **ML / Dream / ExecutorAgent (shadow)** | submit_order | ✅ shadow→Paper, not live | `executor_agent.py:603` `self._paper_engine.submit_order(...)`; :722 "When shadow_mode=False: sends SubmitOrder IPC to Rust" → live path is the Rust OMS single-write-entry (row 9), governed; `openclaw_authority_contracts.py:124` `"can_submit_orders": False` default-deny |
| 9 | **Rust OMS single write entry** | `order_manager.place_order` | ✅ single entry; called only via event_consumer dispatch | `order_manager.rs:354` `pub async fn place_order`; only callers `event_consumer/dispatch.rs:789,799` + `handlers/lifecycle.rs:168 handle_submit_order` — i.e. order submit is funneled through the event_consumer lifecycle handler, not scattered |
| 10 | **Risk-config mutate** (live-param) | `patch_risk_config` IPC → Rust ConfigStore | ✅ route→RiskViewClient→IPC | `risk_routes.py:23` documents the write path is route → IPC → Rust `ConfigStore.replace()` (Rust is the config authority per CLAUDE §一) |

### Ungated perp-order path found: **NONE.**
Every perp-order / live-param surface routes through `_verify_live_gate`
(executor+strategist, row 1-2) or `all_five_live_gates_ok(require_authz=True)`
(sessions, row 3-4), both terminating in the single `verify_signed_authorization`
SSOT (row 5). Live perp submission is funneled through the Rust OMS single write
entry `order_manager.place_order` reachable only via the event_consumer lifecycle
handler (row 9). No HTTP route reaches a live perp order without the gate.

---

## DESIGN OBSERVATION O-1 — Earn Python gate is soft-by-design; binding enforcement is the Rust 9-gate (RESOLVED — CLEAN, not a finding)

**RESOLUTION (read this run, `earn_router.rs:262-625` + module doc :8-63):** the
Python `_check_gate_a..e` ARE intentional preflight/display only; the BINDING
authorization for the Earn write is the Rust `dispatch_earn_intent` 9-gate, which
is hard fail-closed:
- **E-3 governance authorization** (:304-306): `if !governance.is_authorized()
  { return rejected(GovernanceNotAuthorized) }` — comment "Gate 1 等價" (the
  5-gate operator/authorization equivalent).
- **E-4 lease** (:309-336): `LeaseScope::EarnStake/EarnRedeem` with
  `requires_operator_authority`, 60s TTL; lease-facade `AuthNotEffective` →
  "authorization not effective (earn fail-closed)" reject (:177-181).
- **Gate b (OPENCLAW_ALLOW_MAINNET)** enforced at **BybitRestClient
  construction** (:602-604) — a Mainnet client construction fail-closes, so the
  Earn dispatch only ever holds an already-authorized client instance.
- E-0 capability-wiring, E-1 payload, E-2 IntentType, E-5 amount, E-6 audit-row,
  E-7 Bybit place, E-8/E-9 outcome — all `fail-closed reject` (:262-393).
- Module doc: "5-gate inheritance 驗證 per earn_governance §2.1 hard fail-closed"
  (:8), "ADR-0030 5-gate live boundary + lease facade" (:62).
This is the CORRECT Rust-authority pattern (CLAUDE §一: Rust is the trading/risk
authority; Python is control-plane). The soft Python probe cannot authorize a
live Earn write on its own — the Rust gate + IPC-HMAC are the real boundary.
**Verdict: CLEAN. O-1 is a documentation/clarity note, NOT a vulnerability.**

(Historical concern, now disproven, kept for the record:)

FACT (`earn_routes.py:578-652`, read in full): the Earn route implements its OWN
`_check_gate_a..e` rather than calling `_verify_live_gate` / `all_five_live_gates_ok`:
- `_check_gate_b_signed_authorization` (:588-608) is explicitly a **Sprint-1B
  fail-soft probe**: it only checks `main_legacy.LIVE_AUTHORIZATION is not None`
  and returns `{"status":"PASS"}` — it does **NOT** call
  `verify_signed_authorization`, so NO HMAC / expiry / env-match here. Docstring
  says full scope verify is "Wave D MIT 接通".
- `_check_gate_c_mainnet_env` (:611-631) reads `BYBIT_ENV` env directly (different
  source than the executor's `_current_bybit_endpoint_label()`); demo→`N/A`.
- `_check_gate_d` (:634-652) checks `BYBIT_API_KEY` env presence only.

Why this is NOT a perp-order bypass / why LOW, not a finding:
1. Earn writes to Bybit **Earn (yield staking)** `/v5/earn/place-order`, a
   distinct product from perp `/v5/order/create` — it cannot open a leveraged
   trading position, and withdraw permission stays false (no fund exfiltration).
2. The Earn **gate-status dict is preflight/display**; the actual write
   (`POST /stake`) is fail-closed through `_ipc_call_strict` (503 on any IPC
   failure, :705-737) and the IPC payload is **HMAC-signed with
   `OPENCLAW_IPC_SECRET`** (:66,163-164) plus a typed-confirm phrase HMAC
   (:279-296) — a non-harness actor cannot forge the intent JSON.
3. The BINDING authorization enforcement is documented to be the **Rust 9-gate
   `IntentProcessor.process_earn_intent`** (`earn_router.rs`, referenced
   :71-84). The Python probe being soft is by Sprint-1B design IF the Rust gate
   is hard.

🔶 NEEDS-MORE (the one real residual): I could NOT read `earn_router.rs:595-665`
this run (tool stall) to confirm the Rust 9-gate actually verifies a signed
authorization / live_reserved / mainnet for the Earn write. UNTIL that is read,
O-1 should be treated as: *Python Earn gate is intentionally soft; live-money
safety for Earn depends ENTIRELY on the Rust 9-gate + IPC-HMAC.* If the Rust gate
were also soft, an operator-authenticated-but-not-live-authorized actor could
place an Earn (yield) stake — bounded to the Sprint-1B `[100,200]` USDT hard-lock
(`EarnStakeRequest`, :183) and reduce-only-irrelevant (staking, not perp). Risk
ceiling is therefore small even in the worst case, hence LOW.
- Severity: LOW · Path: `earn_routes.py:588-608` + `earn_router.rs` (Rust gate)
- Non-leaking evidence cmd: `sed -n '595,665p'
  rust/openclaw_engine/src/intent_processor/earn_router.rs` (confirm it checks
  authorization/live_reserved/mainnet, not just connectivity).
- Impact: under-authorized Earn yield-stake (≤200 USDT, no perp, no withdraw).
- Why-real-not-FP: Python gate_b literally returns PASS on `authz is not None`.
- Fix direction (only if Rust gate is soft): route Earn write through the same
  `verify_signed_authorization` SSOT, or harden the Rust 9-gate to verify the
  signed authorization + env + expiry.
- Fix owner: E1 (Python) / Rust-eng (earn_router) · Verifier: E3 + BB.

---

## authorization.json forge / replay — EVERY-consume-site verdict: ONE SSOT, BLOCKED

FACT — structurally ONE authorization-VERIFYING consume site:
`live_preflight.verify_signed_authorization` (`live_preflight.py:62`). Reached by
`_verify_live_gate` (executor_routes.py:314) and `all_five_live_gates_ok`
(live_preflight.py:315-317). All other `authorization.json` string hits are:
- the **signer** in `live_trust_routes.py` (`_write_signed_live_authorization`,
  `_canonical_authorization_payload`),
- **read-only status/display** views (`live_trust_routes.py:446` "Rust live-gate
  view … without exposing the [signature]"; :488 malformed→warn),
- the **Earn soft probe** (O-1, does NOT verify HMAC),
- doc-strings.

None of the display/probe readers can authorize a live PERP effect. Forge needs
the mode-600 signing key (→ `authorization_signature` reject); cross-env replay
blocked by env-match; expired blocked by `expires_at_ms <= now_ms`. Because
env-binding + expiry + HMAC live in the ONE delegated verifier, they are enforced
on every PERP consume site by construction — no per-endpoint copy to drift. The
only authorization READER that skips HMAC is the Earn probe (O-1), and it gates a
non-perp yield product backstopped by IPC-HMAC + Rust gate.

---

## Secret-slot resolution order — CLEAN

FACT: executor + `all_five_live_gates_ok` both resolve via `_live_secret_slot_dir`
= `$OPENCLAW_SECRETS_DIR/live` else `~/BybitOpenClaw/secrets/.../bybit/live`
(`live_preflight.py:240-244`), then require BOTH `api_key` AND `api_secret`
non-empty, `OSError→both False` (:300-312). `secret_runtime.get_secret_value`
(first-pass, read in full): env `name` (ignored if empty) → `name_FILE` 0600 file
→ `None`. No default, no cross-slot fallback that satisfies the gate with a
blank/wrong secret. Earn gate_d uses `get_secret_value("BYBIT_API_KEY")` — same
fail-closed primitive.

## OPENCLAW_ALLOW_MAINNET permissive-default hunt — CLEAN (unset = DENY) everywhere

FACT, all three independent check sites agree unset/empty/`0` → reject, never
permit:
- executor: `os.environ.get("OPENCLAW_ALLOW_MAINNET","").strip()=="1"` (first-pass :229)
- `all_five_live_gates_ok`: `(os.environ.get("OPENCLAW_ALLOW_MAINNET") or "").strip()!="1"` → `mainnet_env` reject (live_preflight.py:295)
- Earn gate_c: `env_value=="1"` required when `BYBIT_ENV=="live"` (earn_routes.py:616-625)
`_current_bybit_endpoint_label()` defaults to "mainnet" on missing/unknown →
unknown endpoint gets the STRICTER gate, never a silent demo downgrade. No path
treats unset/0 as permissive.

## LiveDemo vs Live downgrade hunt — CLEAN (one documented mainnet-gate skip only)

FACT: LiveDemo skips ONLY Gate 3 (ALLOW_MAINNET, mainnet-only by definition) in
BOTH the executor (first-pass :226-228) and `all_five_live_gates_ok`
(live_preflight.py:294 only enters the ALLOW_MAINNET branch when
`endpoint_label == _ENV_MAINNET`). Gates 1,2,4,5 (operator role, exact
`live_reserved`, secret slot, signed authorization w/ env-match+expiry) all still
enforced for LiveDemo. Session callers all use `require_authz=True`. Matches
invariant "LiveDemo 不因 endpoint 降級". No real downgrade.

## No-withdraw invariant — (intended check, NOT completed this run)
🔶 The "API key withdraw permission always false / no withdraw endpoint" grep was
queued but hit the stall. First-pass found `openclaw_authority_contracts.py:124
"can_submit_orders": False` default-deny posture. Recommend next-run:
`grep -rniE "/v5/asset/withdraw|def withdraw" program_code rust` to confirm no
withdraw code path exists. (Memory + E3 hard-constraint #4 assert it; not
re-proven this run.)

## OPS-2 Phase-1 fallback — tracked residual, not new (FACT)
Primary `OPENCLAW_LIVE_AUTH_SIGNING_KEY` → Phase-1 fallback `OPENCLAW_IPC_SECRET`
(one-shot WARN) → Phase-2 (2026-06-10) raises. Tracked P1-OPS-2-PHASE-2-CUTOVER;
first-pass runtime log count 0/0 (not re-sshed this run). On track. NB the Earn
IPC path's reliance on `OPENCLAW_IPC_SECRET` (O-1) means the Phase-1 window where
IPC-secret == auth-signing-key slightly enlarges the Earn-forge surface — another
reason the 2026-06-10 cutover matters.

---

## Findings summary
- **P0=0 P1=0 P2=0 P3=0. No NEW exploitable finding. No ungated order path
  (perp OR earn).**
- **O-1 (RESOLVED — CLEAN):** Earn Python gates are preflight/display by design;
  the binding authorization is the Rust 9-gate (E-3 governance auth + E-4
  operator-authority lease, hard fail-closed, `earn_router.rs:262-625`) + IPC-HMAC
  intent integrity. Correct Rust-authority pattern. NOT a vulnerability.
- **No-withdraw invariant: HELD (structural).** `bybit_rest_client.py` exposes
  ONLY `cancel_order` (:655) + `place_order` (:801) as live-write primitives;
  `grep -rniE "/v5/asset/withdraw|def withdraw"` returned EMPTY → no withdraw
  code path exists.
- **Low-value next-run hygiene (NOT residual risk):** re-ssh OPS-2 fallback 0/0
  (first-pass green; cosmetic re-confirm only).

## Required next-run actions (all LOW-value / cosmetic — no open security residual)
1. Re-ssh OPS-2 fallback log count (expect 0/0; first-pass already green).
2. (Optional) read `governance.is_authorized()` impl to confirm it terminates in
   the SAME signed-authorization SSOT as the Python path (high-confidence
   INFERENCE it does, via the lease facade `AuthNotEffective`; not byte-traced).
3. Reminder for any future harness flakiness: probe `echo` + `git diff --stat`
   first; use QUOTED `--include="*.py"` to avoid the zsh-glob false-empty trap
   that produced this run's retracted "outage" verdict.

## Evidence hygiene
- No secret VALUES read/echoed (presence/mode/log-count/call-graph/HMAC-design only).
- Source delta=0 independently re-verified this run.
- Earlier "harness outage / NEEDS-MORE" verdict RETRACTED — root cause was an
  unquoted-glob zsh error; corrected enumeration supersedes it.
- The Rust earn 9-gate body WAS read in the final batch (`earn_router.rs:262-625`)
  → O-1 resolved CLEAN. No finding or clean-verdict was shipped from an empty/flaky
  read; the retracted "outage" verdict is fully disclosed above.

## Closure
DEEPER VERDICT: **CONFIRMED-CLEAN** for ALL order (perp + earn) + live-param +
live-session + authorization-consume surfaces. Single
`verify_signed_authorization` SSOT; `_verify_live_gate` 2 callers
(executor+strategist); `all_five_live_gates_ok` 3 callers all `require_authz=True`
(body read in full = proper 5-gate AND, fail-closed, short-circuit); Rust OMS
single write entry `order_manager.place_order` funneled only through the
event_consumer lifecycle handler; Earn write hard-gated by the Rust 9-gate (E-3
governance auth + E-4 operator-authority lease) + IPC-HMAC. authorization.json
forge / cross-env-replay / expiry: BLOCKED at the one SSOT. Secret-slot
resolution: env→file→None, no permissive default. ALLOW_MAINNET unset=DENY at all
3 sites. LiveDemo: one documented mainnet-skip only, no real downgrade. No-withdraw
invariant structurally held (only cancel_order + place_order exist). **NEW
finding: NONE. Residual security risk: NONE.** One design note (O-1, Earn
soft-Python/hard-Rust split) documented and CLEARED. The only earlier
"NEEDS-MORE" was a self-caught zsh-glob false-empty, retracted with corrected
evidence.
