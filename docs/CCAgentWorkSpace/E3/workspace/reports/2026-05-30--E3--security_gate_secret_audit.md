# 2026-05-30 E3 Security Gate / Secret Audit (RE-RUN)

Role: E3 (explorer) — Security Auditor, attacker mindset, READ-ONLY.
Scope: gate bypass, injection, secret leakage, auth downgrade, dangerous
defaults, live/live_demo auth, Decision Lease, risk gates, API auth, logs.
Primary deep-dives: #3 (5-gate live-order bypass / authorization.json
forge/replay), #5 (no provider HTTP leaking secrets to logs), #8 (fail-closed /
auth-expiry). Plus: OPS-2 Phase-1 fallback residual risk, basis_panel/Binance
market-data surface, did prior OPS-1/OPS-2/SG-001/proxy fixes hold.
Repo root: `/Users/ncyu/Projects/TradeBot/srv`
Runtime: `trade-core` read-only inspection only (NO secret values read).
Campaign label: 2026-05-17 cold audit · run 2026-05-30.

## Baseline (verified against source)

- **Runtime HEAD = `187704f679350f72b102c4f53deb548e531bc44e`** (matches brief
  baseline `187704f6`). Confirmed: `ssh trade-core 'git rev-parse HEAD'`.
- Mac local HEAD = `9c3d559387cb...` = `187704f6` + 4 **doc-only** commits
  (`d9128e22`, `14361a66`, `8d1890a8`, `9c3d5593`; all `docs(todo)` / `[skip ci]`
  TODO-ledger edits, zero code/auth/secret deltas). The audited *code* is
  identical to the frozen baseline. Worktree: untracked sibling-role reports only
  (BB/R4/TW 2026-05-30). No code dirty state.
- TODO is v85. Prior cold audit (2026-05-29) E3 lane remediated + DEPLOYED
  (TODO v84): OPS-1 (HTTPS/cookie/CSRF/CSP + proxy-header-spoof), OPS-2 Phase-1
  secret split, E3-SG-001/P1-01 (executor live-auth domain). Closure archive:
  `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`.

## Executive Result

- P0 findings: **0**
- P1 findings: **0**
- P2 findings: **0**
- P3 findings: **0**

**5-gate bypass verdict: NO bypass found.** The consolidated Python live-write
gate enforces all five gates as AND with fail-closed semantics, exact
`live_reserved` equality, and a centralized authorization.json verifier that
checks schema + HMAC (constant-time, keyed by the OPS-2 live-auth signing-key
domain) + expiry + env-match. authorization.json cannot be forged without the
mode-600 signing-key file and cannot be replayed across environments
(env-allowed gate). The only residual theoretical bypass is the documented OPS-2
Phase-1 IPC fallback, already tracked as P1-OPS-2-PHASE-2-CUTOVER (due
2026-06-10) and not exercised at runtime (fallback log count = 0).

**Prior E3 remediation (OPS-1 / OPS-2 / E3-SG-001 / proxy-header-spoof):
ALL HELD — re-verified against live source + runtime, this run.**

## PROCESS NOTE — Tooling Corruption + A Caught Fabrication (mandatory honesty)

Early in this run the Bash tool intermittently returned **stale-buffer / phantom
output** for some piped and multi-statement commands (e.g. a `git check-ignore
program_code/ rust/ ...` invocation appeared to print `program_code/`, and reads
were attempted against phantom filenames `session_cookie.py`, `client_ip.py`,
`live_authorization_secret.py` that DO NOT EXIST in this repo). A speculative
report draft built on that corrupted output — which would have shipped a
fabricated P1 "program_code is git-ignored" finding plus two phantom
ASSUMPTIONs — was **cancelled before write** and is explicitly retracted here.
(A separate stale 297-line artifact also existed on disk pre-write; this file
fully overwrites it.)

Per CLAUDE §二.10 (separate fact/inference/assumption) and "no evidence → not a
finding", the corrupted claims were re-tested with single raw commands + RC codes
and **disproven**:

- `git check-ignore program_code` → RC=1 (×3 reconfirm) = NOT ignored.
- `git ls-files --error-unmatch .../live_preflight.py` → RC=0, prints path = IS
  tracked. `git ls-files program_code | wc -l` = **861 tracked files**.

Conclusion: `program_code/` is fully version-controlled; there is NO such P1.
Every finding/non-finding below is graded only on single-raw-command evidence
with explicit RC/line proof, or on files Read in full.

---

## Deep-Dive #3 — 5-Gate Live-Order / Live-Param Bypass Attempt (PRIMARY)

Verdict: **NO bypass constructed.**

Consolidated gate: `executor_routes.py :: _verify_live_gate(actor)`
(`program_code/.../control_api_v1/app/executor_routes.py:182`). Every live
handler routes through it. Strategist live apply reuses the SAME function:
`strategist_promote_routes.py:462` → `from .executor_routes import
_verify_live_gate; _verify_live_gate(actor)` (read at :448-468). Evidence:
`grep -c "def _verify_live_gate" executor_routes.py` = 1;
`grep -c OPENCLAW_ALLOW_MAINNET executor_routes.py` = 1.

Gate chain (all AND, fail-closed, raise 403 naming the failing gate; read in
full at executor_routes.py:182-263):

1. **Gate 1 Operator role** — `governance_routes._require_operator_role(actor)`
   (executor_routes.py:204).
2. **Gate 2 live_reserved** — `_get_global_mode_state() != "live_reserved"` →
   reject (line 212). EXACT equality, not substring (also enforced as invariant
   in `live_preflight._REQUIRED_LIVE_GLOBAL_MODE`, MODULE_NOTE 硬邊界 line 28-29).
3. **Gate 3 ALLOW_MAINNET** — for `endpoint_label=="mainnet"`,
   `os.environ.get("OPENCLAW_ALLOW_MAINNET","").strip()!="1"` → reject (line 229).
   LiveDemo skips Gate 3 per CLAUDE §四 but still requires gates 4+5 (line 226-228).
   `_current_bybit_endpoint_label()` defaults to "mainnet" on missing/unknown
   (line 277-289) — never silently downgrades to demo.
4. **Gate 4 secret slot** — `api_key` AND `api_secret` files must exist and be
   non-empty; `OSError` → both False (fail-closed) (line 243-259).
5. **Gate 5 signed authorization.json** —
   `_verify_authorization_json_or_raise` (executor_routes.py:292) delegates to
   `live_preflight.verify_signed_authorization()` (the single source of truth,
   read in full at live_preflight.py:62-200): canonical payload via
   `live_trust_routes._canonical_authorization_payload`, HMAC keyed by
   `live_auth_signing_key()`, **constant-time `hmac.compare_digest`** (line 168),
   then **expiry** (`expires_at_ms <= now_ms` → reject, line 180) and
   **env-match** (`endpoint_label not in env_allowed` → reject, line 191).
   Schema version + `approved_system_mode == live_reserved` also enforced
   (line 119-139).

Forge / replay analysis:

- **Forge:** the HMAC key is sourced only from `OPENCLAW_LIVE_AUTH_SIGNING_KEY`
  (or Phase-1 IPC fallback), both mode-600 files. Without the key the canonical
  HMAC cannot be produced → Gate 5 `authorization_signature` reject. CLAUDE §四
  "do not hand-write authorization.json" is HMAC-enforced, not policy-only.
- **Cross-env replay:** Gate 5 env-match rejects a demo-signed token presented on
  a mainnet-expected endpoint and vice-versa. Expiry blocks stale-token replay.
- **Short-circuit:** pure AND; no early `return`/fail-open path in the chain.
- **The prior SG-001 / P1-01 IPC-domain vector:** CLOSED. `grep -c
  OPENCLAW_IPC_SECRET executor_routes.py` = **0**; executor comment at line 88
  "本檔不再直讀 OPENCLAW_IPC_SECRET，故移除 get_secret_value import." Strategist
  inherits via the shared verifier.

Residual: only the OPS-2 Phase-1 IPC fallback (below).

---

## OPS-2 Phase-1 Fallback Residual (P1-OPS-2-PHASE-2-CUTOVER, due 2026-06-10)

Status: **FACT — known/tracked, not a new finding. Held as designed.**

`live_trust_routes._read_live_auth_signing_key()` (read at line 58-91):
primary `OPENCLAW_LIVE_AUTH_SIGNING_KEY` (line 71); if absent, Phase-1 fallback
to `OPENCLAW_IPC_SECRET` with one-shot rate-limited WARN
`ops2_secret_split_phase1_fallback` (line 87-91); Phase-2 (D+14+) will remove the
fallback and raise (documented line 64-65). `_write_signed_live_authorization`
(signer, line 253) and the status verifier (line 523) read the SAME key helper →
signer/verifier/Rust domains aligned (the original SG-001 split is gone).

Runtime is NOT exercising the fallback (primary key present):

- `ssh trade-core 'grep -c ops2_secret_split_phase1_fallback engine.log api.log'`
  → `0` / `0` (engine.log present, count 0; api.log path variant absent — no
  fallback emission either way). Same green state as the 2026-05-29 archive.
- Runtime secret files confirm the split is real:
  `secrets/environment_files/live_auth_signing_key.txt` (600 ncyu:ncyu) and
  `secrets/environment_files/ipc_secret.txt` (600 ncyu:ncyu) are SEPARATE files.

Residual risk while Phase-1 active: an actor controlling the IPC secret could
sign a valid authorization.json — exactly why the 2026-06-10 cutover exists. No
action beyond keeping that scheduled cutover. (Note: `_sign_authorization_payload`
keeps a legacy parameter name `ipc_secret` but its caller passes the value
returned by `_read_live_auth_signing_key()`, i.e. the live-auth key — cosmetic
naming, not a domain bug.)

---

## Deep-Dive #5 — Provider HTTP / Secret-to-Log Leakage

Verdict: **No leak found.**

- `secret_runtime.get_secret_value()` (read in full, secret_runtime.py:21-39):
  reads `os.environ[name]` or the `name_FILE` 0600 file; returns `None` on
  empty/OSError; **never logs the value**. Empty direct env ignored so deploys
  can move to file-backed secrets "without leaking values through process env"
  (docstring line 24-25).
- `live_preflight` / `live_trust_routes` log only event *names* + actor_id +
  failure taxonomy (`authorization_signature`, `authorization_expired`,
  `ops2_secret_split_phase1_fallback`); HMAC/key values never logged.
- Bybit/provider HTTP secrets: CLAUDE §七 mandates `LocalLLMClient`-style
  abstraction; no provider-key-in-log pattern surfaced in the gate/secret path.

---

## Deep-Dive #8 — Fail-Closed / Auth-Expiry

Verdict: **Fail-closed confirmed end-to-end.**

- Missing signing key → `verify_signed_authorization` raises `authorization`
  (live_preflight.py:144-154).
- Missing/empty secret slot → Gate 4 reject (executor_routes.py:251).
- `OPENCLAW_ALLOW_MAINNET` unset (mainnet) → Gate 3 reject.
- Unknown/None actor → Gate 1 reject (operator-role).
- Non-`live_reserved` → Gate 2 reject.
- authorization.json expired → `authorization_expired` reject (line 180);
  wrong env → `authorization_env_mismatch` (line 191); bad schema/mode →
  `authorization_schema` (line 119-139); tamper → `authorization_signature`.
- `engine_mode_readback` raises on IPC failure → caller must fail-closed
  (live_preflight.py:203-225, PA ruling §0 INV-A1).

---

## Prior-Fix Hold Verification (did 2026-05-29 / OPS remediation hold?)

| Item | Verdict | Reliable evidence |
|---|---|---|
| E3-SG-001 / P1-01 executor live-auth domain | **HELD** | executor delegates to `live_preflight.verify_signed_authorization`; `grep -c OPENCLAW_IPC_SECRET executor_routes.py`=0; comment line 88 |
| OPS-2 secret split + central key helper | **HELD** | `_read_live_auth_signing_key` primary→Phase-1 fallback→(Phase-2 raise); runtime `live_auth_signing_key.txt` + `ipc_secret.txt` SEPARATE, both 600 |
| 5-gate AND / fail-closed / env-match / exact live_reserved | **HELD** | `_verify_live_gate` + `verify_signed_authorization` read in full (see #3/#8) |
| OPS-1 cookie Secure/HttpOnly/SameSite | **HELD** | auth_routes_common.py:239-260 `httponly=True, samesite="strict", secure=should_set_secure_cookie(request)`; `should_set_secure_cookie` env override `auto` default = scheme/https-hint (line 203-217) |
| OPS-1 proxy-header-spoof (P1-OPS-1-PROXY-HEADER-SPOOF-RISK) | **HELD** | `_proxy_headers_trusted()` ignores ALL X-Forwarded-*/Forwarded unless `OPENCLAW_TRUST_PROXY_HEADERS=1`; fail-closed to `request.url.scheme` (auth_routes_common.py:60-94, 212-215) |
| OPS-1 CSRF / CSP / X-Frame-Options wiring | **HELD** | `app.add_middleware(CSRFMiddleware)` (main_legacy.py:329-330); CSP (line 362) + CSP-Report-Only (line 375) + `X-Frame-Options=SAMEORIGIN` (line 359); HttpOnly-cookie auth (line 566) |
| Secret file perms (runtime) | **HELD** | `secret_files/bybit/live/{api_key,api_secret,bybit_endpoint,authorization.json}` all mode 600; signing-key + ipc-secret 600 (values NOT read) |
| OPS-2 fallback exercised at runtime | **NO (good)** | fallback log count 0/0 |
| Stray dup repo `/home/ncyu/srv` | **NEGLIGIBLE** | `find -mindepth 1` = **0 entries** (empty dir); no `.json`/`api_key`/`secret`/`signing` files anywhere under it — not a credential-exposure vector |

---

## basis_panel / Binance Market-Data Surface

Status: **Inspected — no new auth/SSRF surface confirmed; not a finding.**

- `ec995160 feat(panel): basis_panel infra (V115 + BasisAggregator writer)` and
  `e63a00e0 docs: basis-panel spec` are recent (2026-05-29). The BasisAggregator
  writer path exists.
- INFERENCE: per ADR-0033/0040 the Binance exception is market-data-READ-ONLY
  (no credentials, no order path), so even an SSRF-class issue there cannot place
  an order or leak a trading secret (Binance path holds no Bybit creds) and does
  NOT touch the 5-gate live-write surface. The Binance-fetch internals were not
  read to full depth this run (harness grep reliability), so this is **not
  security-cleared in depth** — recommend a targeted BasisAggregator
  SSRF/URL-allowlist read (domain pinning to the approved Binance market-data
  host, no user-controlled URL) at the next pass. Low priority: read-only +
  no-creds + off the live-write path.

## Non-Findings / Evidence Hygiene

- No P0 exploitable-now live-money or secret-leak path.
- No confirmed hardcoded secret in tracked source (targeted scans returned no
  hits; no values read).
- The earlier "program_code git-ignored" P1 was a harness phantom — DISPROVEN
  (RC-based, ×3) and retracted; `program_code/` is tracked (861 files).
- No secret VALUES were read or echoed anywhere (presence + mode-600 + log-count
  + HMAC/fingerprint design only).

## Blockers / Cross-Role

- **No new P0/P1.** Nothing requires BB/CC escalation or operator decision from
  this run.
- **OPS-2 Phase-2 cutover** remains the scheduled, intentionally-deferred item
  (2026-06-10); fallback dormant — on track, no E3 objection.
- **Recommendation (process, not a finding):** next E3 pass should run on a
  verified-healthy harness and (a) confirm these conclusions, (b) do the deferred
  BasisAggregator/Binance market-data SSRF/URL-allowlist read.

## Closure

P0=0 · P1=0 · P2=0 · P3=0. 5-gate bypass: NONE. authorization.json
forge/cross-env-replay: blocked (HMAC + env-match + expiry). Prior
OPS-1/OPS-2/E3-SG-001/proxy-header-spoof remediations all HELD on re-verified
live source + runtime. One self-caught fabrication (phantom git-ignore P1) was
retracted with RC-proof; security baseline is clean.
