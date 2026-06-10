# L2 Advisory Mesh — Phase 1 (D3 Provenance & Audit) Technical Design

Date: 2026-06-08
Author: PA (Project Architect)
Status: **E1-READY (design-only)** — no code, no migration apply, no DB write, no deploy in this pass.
Owner chain (this phase): PM → **PA (this doc)** → E1/E1a → E2 → E3 → E4 → QA → PM.
SSOT design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--l2-advisory-mesh-design-draft.md` (v4-final, 4-review-passed).
Execution plan: `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md` §0/§1/§2 Phase 1.
Operator scope ruling (2026-06-08): P1 = ledger + sanitize + **upstream research-plane** provenance columns only. The R2-5 live-fills/outcomes + Decision-Lease audit-row hop is **EXPLICITLY DEFERRED** to a separate gated step (forward-compatible, not designed here).

This document does **not** re-litigate the v4-final design. It grounds every Phase-1 schema/table
assertion in `file:line`, resolves the open design items the execution plan flagged
(`consequential` append-only matrix, redactor reuse-vs-build, exact upstream target tables), and
hands E1 a table-by-table executable spec.

---

## 0. Read-before-build clearance (every assertion grounded)

I read the source before designing. These are the §0 execution-plan `needs-verification` items,
now **CLEARED with file:line** (or escalated to a Linux read-only check where Mac SQL cannot prove
runtime state).

| Item | Finding | Ground |
|---|---|---|
| **V134 free** | V133 is highest physical migration; no V134 exists. **Ledger = V134.** | `ls sql/migrations/` → highest is `V133__agent_lessons.sql`. **V128 is a soft reservation** (reserved-if-needed for a deferred breadth table, PM-decided) — `V127__aeg_regime_labels.sql:125` ("V128 reserved-if-needed 給 deferred breadth 表") + MIT report `2026-06-03--aeg_s2_evidence_automation_design.md:178,192`. So the next clean free number **after V134** is **V135** (skip the V128 soft-reservation to avoid collision). |
| **`agent.ai_invocations` shape → reuse vs add** | ai_invocations stores **`prompt_hash` (hash) + `response_summary` (summary)**, NOT full prompt/response. Confirms D.1 must be a **NEW table** (full-text shape ai_invocations was not built for) that **reuses the ledger's helper discipline**. | Actual INSERT column list: `program_code/ai_agents/bybit_thought_gate/bybit_ai_invocation_ledger.py:222-227` → `(ts, invocation_id, provider, model, tier, purpose, prompt_hash, input_tokens, output_tokens, cost_usd, latency_ms, success, response_summary, context_id, details, engine_mode)`. Reusable helpers: `_sha256_text()` (`:49-52`), `deterministic_event_ts()` (`:55-81`), `write_invocation_ledger()` (`:139`). |
| **`Layer2CostTracker` is cost-only** | Confirmed cost/metadata only — not a partial prompt/response audit. The central D3 gap stands. | `layer2_cost_tracker.py` is the persistence module; `layer2_engine.py` passes `system_prompt` to the model at `:275/:295/:329/:561/:752` but has **no INSERT/persist of full prompt/response** anywhere — the only persist is `persist_lessons` (`:723`, lesson insight only). |
| **D3 central gap (full prompt/response never persisted)** | **VERIFIED ABSENT.** `layer2_engine` feeds `system_prompt` to the model but never writes the full prompt/response to any durable store. | Grep of `layer2_engine.py` for `INSERT INTO` / `persist` / `_write_` over the prompt path → 0 hits except `persist_lessons` (lesson text, not the prompt). |
| **Secret redactor reuse** | **PARTIAL reuse + new redactor needed.** `error_sanitize.py` exists and solves the `str(e)`/error-leak half (reason_code → safe message), reusable for D.1.1's "no raw exception text" rule. But it does **NOT** scrub secret patterns (API keys / bearer / DSN / `authorization.json` material) from large free-text — that does not exist and must be built. | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/error_sanitize.py` (whole file, 83 lines): `_REASON_CODE_MESSAGES` dict + `sanitize_exc_for_detail()` (`:39`) + `sanitize_exc_str()` (`:65`). No secret-pattern regex anywhere in repo (grep `redact|scrub|sanitiz|\[REDACTED` → only `error_sanitize.py` + route-level error handling, none do secret-pattern masking of stored text). |
| **append-only enforcement pattern** | repo has **two** patterns; D3 uses the **DB-level REVOKE** pattern (stronger), with the **V114 controlled narrow-column UPDATE exception** for the `consequential` matrix. | See §A.3 / §A.4 below. App business role = **`trading_ai`**; correction/admin role = **`trading_admin`** (`V099__autonomy_level_config.sql:295-307`). |
| **upstream target tables (exact names)** | `learning.hypotheses` (NOT `research.hypotheses`); `replay.experiments` (plain table); demo fills = `trading.fills` (engine_mode='demo', columnstore hypertable); `learning.mlde_shadow_recommendations` exists (P3, not P1). **No physical strategy-variant table exists.** | See §C below per target. |

**Single most important correction to the v4 design text:** the design §D.2 names
`research.hypotheses` / `hid`. The **actual** table is **`learning.hypotheses`** with PK
**`hypothesis_id BIGSERIAL`** (`V100__m4_hypothesis_base_table.sql:273-274`). E1 must use the real
names. (The v4 design was a heads/grep read; this is the in-full correction it asked for.)

---

## A. V134 `agent.l2_calls` migration design

### A.1 Final column list (per design §D.1, lines 644-669)

Template to mirror: **V133** (`agent` schema, additive-only, `BEGIN/COMMIT`, Guard A/B/C, explicit
"single write entry + read-only read" discipline). The column set is the design's §D.1 verbatim;
the only PA-added grounding is the **type-sensitivity / Guard-B targets** and the
**`prompt_sha256`/`response_sha256` CHECK** mirroring V064's `payload_hash` regex.

```
agent.l2_calls (
  l2_reply_id        TEXT PRIMARY KEY,        -- "l2r:<uuid12>" universal lineage handle
  session_id         TEXT,                    -- Layer2Session.session_id (groups multi-call sessions)
  capability_id      TEXT NOT NULL,
  trigger            TEXT NOT NULL,           -- "event|schedule|manual|threshold" + spec
  created_at         TIMESTAMPTZ NOT NULL,    -- hypertable partition key
  model              TEXT NOT NULL,
  model_version      TEXT,
  contract_ver       TEXT NOT NULL,           -- PromptContract version (§E.1, design :820)
  schema_ver         TEXT NOT NULL,           -- output-schema version (§E.1)
  system_prompt      TEXT NOT NULL,           -- FULL deterministic prompt as sent (sanitized, §B)
  input_context      JSONB NOT NULL,          -- FULL structured input + offered tool defs (sanitized)
  raw_response       TEXT NOT NULL,           -- FULL raw model output, pre-parse (sanitized)
  parsed_output      JSONB,                   -- schema-validated output (NULL if guard rejected)
  guard_verdict      TEXT,                    -- out-of-bound guard result: pass|clamp|reject
  fact_inf_assm      JSONB,                   -- {facts:[],inferences:[],assumptions:[]}
  input_tokens       INTEGER,
  output_tokens      INTEGER,
  cost_usd           NUMERIC,
  latency_ms         INTEGER,
  prompt_sha256      TEXT,                    -- sha256 over the SANITIZED stored system_prompt
  response_sha256    TEXT,                    -- sha256 over the SANITIZED stored raw_response
  redactor_version   TEXT,                    -- [PA-ADD] which sanitize-redactor version ran (§B)
  error_code         TEXT,                    -- [PA-ADD] classified error code if the call failed (§B; never str(e))
  consequential      BOOLEAN NOT NULL DEFAULT false  -- retention class (§Q6); see A.4 for the matrix resolution
)
```

**[PA-ADD rationale]** Two columns are added beyond the §D.1 list, both required by the §B sanitize
gate (E3-HIGH) and not optional:
- `redactor_version` — D.1.1 mandates "redactor version is logged" (design `:697`,`:700`). Without
  a column, that log has nowhere to live in the row. This makes a row's redaction provenance
  reconstructable.
- `error_code` — D.1.1 mandates failed calls store "a classified error code + a sanitized reason,
  not the raw exception" (design `:688-691`). `error_code` holds the classification; the
  human-readable sanitized reason can ride in `raw_response` (already sanitized) or
  `input_context`. This is the structural enforcement that `str(e)` never lands verbatim.

PK is `l2_reply_id` (single column). **Hypertable caveat:** TimescaleDB requires the partition
column (`created_at`) to be part of any unique constraint. Because `agent.l2_calls` is a hypertable
on `created_at`, the PK must be **composite `(l2_reply_id, created_at)`** — this is exactly the
pattern V035 (`PRIMARY KEY (id, ts)`, `:135`) and V114 (`PRIMARY KEY (id, ts_ms)`, `:178`) and V064
state-changes (`PRIMARY KEY (transition_id, ts)`, `:163`) all use. **E1 MUST use
`PRIMARY KEY (l2_reply_id, created_at)`**, with a plain unique index documentation note that
`l2_reply_id` is globally unique by construction (uuid12). The design's "`l2_reply_id text PRIMARY KEY`"
is shorthand; the hypertable forces the composite. (This is a real E1 trap — flagged.)

### A.2 Guards (mirror V133 / V035 / V064)

- **Guard A** (on CREATE TABLE, mandatory per CLAUDE.md "Data, Migrations, And Validation"):
  `DO $$ ... IF EXISTS(table) THEN reflect required columns; missing → RAISE EXCEPTION $$` —
  exactly V133 `:41-78` shape. Required-column array = the 24 columns above. Catches "table exists
  but schema drift" on re-apply.
- **Guard B** (type-sensitive columns): reflect `data_type` of the type-load-bearing columns and
  RAISE on drift — V133 `:108-130` shape. Targets: `system_prompt`/`raw_response`=`text`,
  `input_context`/`parsed_output`/`fact_inf_assm`=`jsonb`, `cost_usd`=`numeric`,
  `created_at`=`timestamp with time zone`, `consequential`=`boolean`. (Drift here = a JSONB column
  silently created as text would break the writer.)
- **Guard C** (indexes exist): the lineage + forensic hot-path indexes (below) — V133 `:133-156` shape.
- Optional content-integrity CHECK on the hashes, mirroring V064's `payload_hash`
  (`:62-64`,`:135-137` → `CHECK (payload_hash ~ '^sha256:[0-9a-f]{64}$')`). **Recommendation:**
  use a *nullable-tolerant* CHECK `CHECK (prompt_sha256 IS NULL OR prompt_sha256 ~ '^[0-9a-f]{64}$')`
  (bare hex, matching V132's content-hash CHECK style `:110-113`, since these are bare sha256 hex
  not the `sha256:`-prefixed style of V064). Pick **one** convention and document it; do not mix.

### A.3 Hypertable + indexes

- Hypertable on `created_at` (TimescaleDB), 7-day chunks — V035 `:141-154` / V064 `:178-184` shape:
  `DO $$ IF EXISTS(pg_extension timescaledb) THEN PERFORM create_hypertable('agent.l2_calls','created_at', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE) $$`. The `INTERVAL '7 days'`
  (timestamptz) form is correct here (V035/V064 use it); the BIGINT-ms form is only for BIGINT
  partition columns (V114/V026) — `agent.l2_calls.created_at` is timestamptz, so use the interval form.
- Forensic hot-path indexes (the §D.4 fault-localization protocol queries):
  - `idx_l2_calls_session` ON `(session_id, created_at DESC)` — group a session.
  - `idx_l2_calls_capability` ON `(capability_id, created_at DESC)` — per-capability audit.
  - `idx_l2_calls_consequential_created` ON `(created_at DESC) WHERE consequential = false` — lets
    `drop_chunks` / retention target the non-consequential rows (§Q6, design `:668`).
  - PK `(l2_reply_id, created_at)` already serves the primary `WHERE l2_reply_id = ?` lookup (§D.4
    step 2).

### A.4 Append-only enforcement + the `consequential` matrix resolution [DESIGN GAP RESOLVED]

**The repo has a mature, vetted append-only pattern — D3 uses it, not application-discipline-only.**

There are two patterns in the repo:
1. **Application-discipline append-only** (V064 `decision_state_changes`, V133 `agent.lessons`,
   V035 `governance_audit_log`): no DB REVOKE; relies on "single INSERT write entry + read-only
   read." Used for low-blast audit logs.
2. **DB-level REVOKE append-only** (the strong pattern): `REVOKE UPDATE, DELETE FROM PUBLIC` +
   `REVOKE FROM trading_ai`. Used where immutability is load-bearing:
   - V099 `system.autonomy_level_switch_audit` (`:298-307`) — the **closest semantic precedent**:
     "trading_ai 業務 role 完全不可 UPDATE/DELETE；只有 trading_admin 透過顯式 ADR-0006 數據訂正路徑可動"
     (`:295-296`).
   - V058 (`:136-137`), V059 (`:112`), V060 (`:95`) — pure `REVOKE UPDATE, DELETE FROM PUBLIC`.

**D3 ledger uses pattern 2** (DB-level), because a leak-bearing, hard-to-purge audit store that
*also* permits silent post-hoc UPDATE would defeat root principle 8 (reconstructable). Concrete
E1 SQL, mirroring V099 `:298-307` (the DO-block guard handles dev-sandbox where `trading_ai` is absent):

```sql
REVOKE UPDATE, DELETE ON agent.l2_calls FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON agent.l2_calls FROM trading_ai';
        RAISE NOTICE 'V134: REVOKE UPDATE/DELETE on agent.l2_calls FROM trading_ai applied';
    ELSE
        RAISE NOTICE 'V134: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;
```

**Resolving the `consequential` append-only contradiction (execution plan §0, design §L `:1603-1605`,
operator Q6).** The schema notes `consequential` is "set AT CREATION" (design `:664`), but §Q6 wants
a row to flip to consequential only **later** when its artifact actually reaches a lane — which an
append-only (no-UPDATE-grant) table forbids. Three options were on the table; I evaluated each
against how the repo handles the identical shape:

- **Option (a) creation-only, accept no late promote.** Stamp `consequential` at creation from
  `l2_capability_registry.consequential_default` (design §B `:443`); never flip. Simple, but loses
  the "row became consequential after the fact" signal → over-retains (drops a row that later
  mattered) or under-retains.
- **Option (b) controlled narrow single-column UPDATE exception.** Keep the row append-only for
  *everything except* `consequential`, and grant a **column-scoped UPDATE on `consequential` only,
  to `trading_admin` only** — exactly the V114 pattern (`GRANT UPDATE (acked_at_utc, acked_by) ON
  observability.notification_failsafe_events TO trading_admin` + `REVOKE UPDATE,DELETE FROM PUBLIC`,
  `V114:204-265`, header `:42` "UPDATE 限 trading_admin role + 限 acked_* 2 column"). The
  `consequential` promote is a controlled lane-entry event, not free mutation.
- **Option (c) side index table.** A separate `agent.l2_consequential_marks (l2_reply_id, marked_at,
  reason)` append-only table; retention joins it. No UPDATE on the ledger at all.

**PA RECOMMENDATION: Option (b) — controlled narrow-column UPDATE on `consequential`, granted to
`trading_admin` only, with the V114 idempotency safeguards.** Rationale:
1. It is **the exact pattern the repo already vetted and dry-ran** (V114 is literally the
   `feedback_v_migration_pg_dry_run.md` V114 lesson: column-level GRANT UPDATE on an append-only
   hypertable). Reusing a vetted pattern beats inventing (c).
2. It preserves append-only semantics for **all forensic content** (`system_prompt`,
   `raw_response`, `input_context`, hashes, tags) — those remain immutable; only the retention-class
   bit is promotable, and only by the admin/correction role, never by `trading_ai` or the D3 writer.
3. **CRITICAL E1 carry-over from the V114 lesson (memory `feedback_v_migration_pg_dry_run.md`):**
   `agent.l2_calls` is a TimescaleDB hypertable; if compression is ever enabled, a **column-level
   `GRANT UPDATE (consequential)` propagates to the `_compressed_hypertable_NN` twin and aborts**
   (V114 `:208-216`). So the column-level GRANT must be wrapped in
   `BEGIN ... EXCEPTION WHEN undefined_column THEN RAISE NOTICE ... END` (V114 `:249-257`) for
   re-apply idempotency, **and** placed **before** any compression enable. **Recommendation for P1:
   do NOT enable compression on `agent.l2_calls` in V134** (retention is via `drop_chunks` of
   non-consequential chunks, design `:668`, which needs no compression) — this sidesteps the twin
   trap entirely for P1. If a later phase adds compression, it inherits the V114 ordering + nested-
   exception discipline.

So the write-side contract is: **D3 writer has INSERT only** (never UPDATE/DELETE). The
`consequential` promote is a **separate `trading_admin`-scoped controlled UPDATE** invoked by the
lane-applier when (and only when) an artifact derived from this reply first enters a retention-
worthy lane. This keeps the writer single-entry append-only (root principle 1/8) while honoring §Q6.

**Concrete V114-style grant block for E1:**
```sql
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_admin') THEN
        EXECUTE 'GRANT SELECT, INSERT ON agent.l2_calls TO trading_admin';
        BEGIN
            EXECUTE 'GRANT UPDATE (consequential) ON agent.l2_calls TO trading_admin';
        EXCEPTION WHEN undefined_column THEN
            RAISE NOTICE 'V134: column-level GRANT UPDATE(consequential) skipped — compressed twin exists on re-apply (idempotent)';
        END;
        RAISE NOTICE 'V134: granted SELECT/INSERT (full) + UPDATE (consequential only) to trading_admin';
    END IF;
END $$;
-- D3 writer role (trading_ai) gets INSERT + SELECT only; no UPDATE/DELETE (the REVOKE block above).
```

---

## B. Sanitize-before-persist redactor specification (§D.1.1, E3-HIGH gate)

### B.1 Reuse-or-build decision

**DECISION: hybrid — reuse `error_sanitize.py` for the error-text half; BUILD a new deterministic
secret-pattern redactor for the large-text half.** Grounded:
- `error_sanitize.py` (whole file) already implements the "no raw exception text" contract: it maps
  an exception to a stable `reason_code` → safe user-facing message and **only** appends truncated
  `str(e)[:200]` when `OPENCLAW_DEBUG=1` (`:56-61`,`:74-75`). **Reuse its `reason_code` vocabulary**
  for D.1.1's `error_code` column and "classified error code + sanitized reason" rule (design
  `:688-691`). The D3 writer, on a failed call, calls a thin wrapper that yields `(error_code,
  sanitized_reason)` from this module's table — never `str(e)` into the ledger.
- **No secret-pattern redactor exists** (grep confirmed: nothing in repo scrubs API-key/bearer/DSN
  shapes out of stored free text). D.1.1's core requirement — scrub secrets out of the **full**
  `system_prompt`/`input_context`/`raw_response`/`final_summary` before they hit a durable append-
  only store — must be **built new** (design §I `:1414` already lists it as NEW: "reuse a repo
  redactor if one exists" → none exists → build).

### B.2 New redactor spec (`l2_secret_redactor`, versioned)

Deterministic, idempotent, versioned. Located as a small pure module in `control_api_v1/app/`
(co-located with `error_sanitize.py`). Signature shape:
`redact(text: str) -> RedactResult{ text: str, kinds_hit: list[str], redactor_version: str }`.

**Pattern set (deterministic regex, `[REDACTED:<kind>]` replacement token):**

| kind | what it matches | why |
|---|---|---|
| `api_key` | Bybit/exchange API key shapes + generic high-entropy `[A-Za-z0-9]{20,}` keyed by adjacent `api_key`/`apiKey`/`secret`/`key=` | Bybit key material is the highest-value secret on this box. |
| `bearer` | `Bearer <token>`, `Authorization: <...>`, HMAC signature headers (`X-BAPI-SIGN`, `sign=`) | auth headers drift into logs/error strings. |
| `auth_json` | contents shaped like `authorization.json` fields (`signature`, `approved_by` token blobs, signed-payload base64) | CLAUDE.md §四: signed live auth material must never leak. |
| `secret_slot` | secret-slot identifiers / slot material references | secret-slot is a live-auth gate (CLAUDE.md §四). |
| `db_dsn` | `postgres://user:pass@host/db`, `password=...`, `PGPASSWORD`, connection-URL passwords | a captured DSN in a `str(e)` is the classic leak (D.1.1 `:683`). |
| `private_url` | internal hostnames (`trade-core`, private IPs `10.`/`192.168.`/`127.0.0.1`, `.local`) | private topology. |

- **Replacement token:** `[REDACTED:<kind>]` (stable, design `:695`). Forensically useful (you know
  a secret of kind X was there) without the secret.
- **Idempotent:** running `redact()` on already-redacted text is a no-op (the `[REDACTED:*]` token
  matches nothing in the pattern set). Required by D.1.1 `:696`.
- **Versioned:** `redactor_version` (e.g. `l2_redactor.v1`) is returned and written to the
  `agent.l2_calls.redactor_version` column. Any pattern-set change bumps the version. Required by
  D.1.1 `:697`.
- **JSONB handling:** `input_context` is JSONB — redact **recursively over all string leaf values**
  (keys are schema-controlled, not secret-bearing; values are where context blocks could carry a
  drifted secret). The redacted JSONB is what gets stored.

### B.3 Write-path integration point (the load-bearing "on write path, no window" requirement)

The sanitize pass runs **inside the D3 writer, immediately before the `INSERT`, and the
`prompt_sha256`/`response_sha256` are computed over the already-sanitized text** (design `:698-699`).
Concretely, the D3 writer's single `record_l2_call(...)` entry does, in order:

```
1. raw fields in (system_prompt, input_context, raw_response, [optional final_summary])
2. system_prompt   = l2_secret_redactor.redact(system_prompt)        # scrub
   raw_response     = l2_secret_redactor.redact(raw_response)
   input_context    = redact_jsonb(input_context)
   (if final_summary persisted elsewhere: redact it too — D.1.1 "applies everywhere")
3. if the call FAILED: error_code, sanitized_reason = classify(exc) via error_sanitize reason_code
                       (raw_response/str(e) NEVER stored verbatim)
4. prompt_sha256   = _sha256_text(system_prompt)    # over SANITIZED text (reuse ledger helper :49)
   response_sha256 = _sha256_text(raw_response)
5. INSERT INTO agent.l2_calls (... sanitized fields ..., redactor_version, error_code ...)
```

There is **no path** where an unsanitized large-text value is written and cleaned later. Step 2
precedes step 5 in the same function; the redactor is not an async post-hoc job. This is exactly the
E3 stress-test target (design `:703-705`, plan §2 `:107-110`, CC stress-test 19 `:1660-1662`).

**Hard rule (mirror design `:702`):** **no code path may write an unsanitized large-text field to
any durable store** — the D3 writer is the single sanctioned write entry; any other module wanting
to persist L2 prompt/response/summary must route through it (root principle 1: single controlled
write entry).

### B.4 E3-verifiability

E3 verifies by **injecting a synthetic secret** (a fake Bybit-shaped key, a fake `Bearer` token, a
fake DSN with password, a `str(e)` carrying a connection URL) into `system_prompt`/`raw_response`/the
exception path → assert the stored row contains `[REDACTED:api_key]` / `[REDACTED:bearer]` /
`[REDACTED:db_dsn]` and **never** the secret, and that `redactor_version` is populated, and that the
sha256 matches the sanitized stored text (not the original). Plus a negative test: a benign prompt
with no secret stores verbatim (no false-positive redaction of normal content). This is the E3-HIGH
gate (execution plan §1 `:77`, sign-off point `:117-118`).

---

## C. Upstream provenance columns (per target, grounded)

Operator scope (2026-06-08): P1 adds `source_l2_reply_id` (and the applicable immediate-parent id)
**only** to upstream research-plane targets. **Every one is an additive nullable column, no backfill,
no NOT NULL** — provenance is null for pre-existing/human/deterministic-origin rows, which is correct
(design §D.2 `:771-772`: a gate receiving an artifact lacking `source` treats it as non-L2). The root
`source_l2_reply_id` is **copied forward unchanged at every hop, never re-derived** (design `:751-754`).

| Target (real name) | Defining migration | Add | Schema-conflict check | E1 ADD-COLUMN shape |
|---|---|---|---|---|
| **`learning.hypotheses`** (NOT `research.hypotheses`) | `V100__m4_hypothesis_base_table.sql:273` (PK `hypothesis_id BIGSERIAL`, `:274`) | `source_l2_reply_id TEXT NULL` | Plain table, 13 columns, BIGSERIAL PK — **no hash-chain, not a hypertable** → additive col trivial. | `ALTER TABLE learning.hypotheses ADD COLUMN IF NOT EXISTS source_l2_reply_id TEXT NULL;` |
| **strategy variant / config draft** | **NO PHYSICAL TABLE EXISTS** | — | grep `CREATE TABLE.*(variant\|strategy_config\|config_draft\|asds)` → **0 hits**. Track-B "asds_factory" variants are today an **enum value on `trading.fills.track`** (`V101:79-82`), not a row in a variant table. There is nothing to add a column to. | **DEFER** — list as Linux read-only confirm item (§F); if confirmed no table, this hop is **N/A for P1** and lands when a variant table first exists. Chain stays forward-compatible (root id propagates whenever the table appears). |
| **`replay.experiments`** | `V041__replay_oos_embargo_enforcement.sql:81` (PK `experiment_id TEXT`) | `source_l2_reply_id TEXT NULL` (+ optional `origin_hypothesis_id BIGINT NULL` as the immediate parent) | Plain table, 4 columns, TEXT PK — **not a hypertable, not hash-chained** (the v4 text's "V131/V132 hash-chained" claim does **not** apply to `replay.experiments` itself; V131/V132 are the residual/hidden-OOS registries). Additive col trivial. | `ALTER TABLE replay.experiments ADD COLUMN IF NOT EXISTS source_l2_reply_id TEXT NULL;` |
| **demo Stage1 manifest** | manifest is `replay.experiments.manifest_jsonb` / Stage-1 manifest jsonb (per V132 header `:6-9` it lives in the manifest jsonb) | propagate `source_l2_reply_id` **inside the manifest jsonb** (no DDL) | The manifest is jsonb, not a column set — provenance rides as a manifest key, no migration needed for this hop. | No ALTER; producer writes `source_l2_reply_id` into the manifest jsonb. **Confirm jsonb key on Linux (§F).** |
| **demo fills / `decision_outcomes`** | demo fills = **`trading.fills`** (engine_mode='demo'; `V003` base + `V015:15` engine_mode); `decision_outcomes` = `V005__indexes_views.sql` / extended `V101`/`V074` | `source_l2_reply_id TEXT NULL` on each | **`trading.fills` is a TimescaleDB columnstore hypertable** (`V101:49-53`). **CRITICAL:** ADD COLUMN must be **nullable, no DEFAULT, no SET NOT NULL** (columnstore `feature_not_supported` per V077 lesson; V101 `:170-181` is the exact vetted range). `decision_outcomes` — confirm hypertable/columnstore status on Linux. | `ALTER TABLE trading.fills ADD COLUMN IF NOT EXISTS source_l2_reply_id TEXT NULL;` (columnstore-safe form). Guard A/B mirror V101 `:90-167`. |
| **`agent.lessons`** | `V133__agent_lessons.sql:80` (has `context_id TEXT`, `:87`) | **map existing `context_id`** to the L2 reply id (no new column needed) | V133 already carries `context_id` (`:87`); design §D.2 `:765` says "map it." A lesson distilled from an L2 insight sets `context_id = l2_reply_id`. **No DDL.** | No ALTER; `persist_lessons` writes `context_id = <l2_reply_id>` for L2-originated lessons. |

**R2-5 live hop — EXPLICITLY DEFERRED, shape-noted only (not designed here).** Per operator
2026-06-08: the post-cross live-fills / live-`decision_outcomes` / Decision-Lease audit-row
`source_l2_reply_id` propagation is a **separate gated step**, because it needs (a) a Rust engine
change to the live record path to copy the lease root id forward, and (b) an additive column on
possibly-hash-chained live-critical tables, and (c) it only matters once a P3+ capability exists and
a human crosses to live via the 5-gate flow (zero data flows before that). **Forward-compat shape
only:** when that step lands, the lease carries the candidate's `source_l2_reply_id`; the engine
copies that root id (never re-derives) onto the live fill / outcome / lease-audit rows as an
**additive, audit-only** column — same propagate-unchanged discipline as every P1 hop. **No live
authority, no new live path.** The P1 chain is designed so this slots in with identical root-id
semantics (the root never gets rewritten — design `:751-753`). E1 must **not** touch any live table
in P1.

---

## D. Gate-seam log `learning.l2_gate_seam_log`

### D.1 Schema (per design §D.3 `:776-781`)

Append-only. Records, per artifact, which deterministic gate let it through and what it became.

```
learning.l2_gate_seam_log (
  seam_id        BIGSERIAL,
  ts             TIMESTAMPTZ NOT NULL DEFAULT NOW(),   -- hypertable partition key
  l2_reply_id    TEXT NOT NULL,                        -- the artifact's root provenance (joins agent.l2_calls)
  gate_id        TEXT NOT NULL,                        -- which deterministic gate (dsr/pbo/leak/beta_neutral/...)
  verdict        TEXT NOT NULL CHECK (verdict IN ('pass','clamp','reject')),
  applier        TEXT,                                 -- which lane-bound applier (or NULL = proposal only)
  applied_as     TEXT,                                 -- what concretely changed, or "proposal only"
  details        JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (seam_id, ts)
)
```

- **Guard A** on CREATE TABLE (V133/V035 shape).
- Hypertable on `ts`, 7-day chunks (V035 `:141-154` shape).
- Index `idx_l2_gate_seam_reply` ON `(l2_reply_id, ts DESC)` — the §D.4-step-3 forensic query
  (`WHERE l2_reply_id = ?` → which gate passed it). Guard C verifies it.
- Append-only via the same `REVOKE UPDATE, DELETE FROM PUBLIC` + `REVOKE FROM trading_ai` block as
  §A.4 (this table has **no** late-promote need, so **no** narrow-column UPDATE exception — pure
  append-only, simpler than the ledger).
- `verdict` CHECK enum matches the guard-verdict vocabulary already in the ledger's `guard_verdict`
  (design `:659`, `:818`).

### D.2 Same-migration vs separate-V13x — RECOMMENDATION

**RECOMMENDATION: separate migration `V135__l2_gate_seam_log.sql`** (next free number after V134,
**skipping the V128 soft-reservation**).

Rationale:
- **Different schema** (`learning` vs `agent`), different table, different append-only profile (no
  consequential matrix). Bundling unrelated DDL into one migration muddies the dry-run blast radius
  and the idempotency reasoning (each V### should be one coherent green checkpoint — CLAUDE.md "Git
  And Sync").
- The execution plan §0 (`:31`) already anticipates a "V13x" companion table (it names the C1
  promote-candidate table as "V13x = next free after V134"). Using **V135 for gate-seam** and
  leaving the C1 promote-candidate table (a P2 concern, design §O.4 `:1579`) for a later number keeps
  P1's two tables cleanly numbered: **V134 = `agent.l2_calls`**, **V135 = `learning.l2_gate_seam_log`**.
- **E1 dry-run note:** V134 and V135 are independent (no inter-migration FK — `l2_reply_id` is a
  logical join, not a DB FK, mirroring V064 `decision_edges` "logical FK only" `:106-107` and V035's
  nullable candidate_id). So they can be dry-run + double-applied independently.

### E. Migration numbering (final)

| Migration | Table | Free? |
|---|---|---|
| **V134** | `agent.l2_calls` (ledger) | YES — V133 highest; no V134 exists. |
| **V135** | `learning.l2_gate_seam_log` (gate-seam) | YES — next clean free after V134, skips V128 soft-reservation. |

(Provenance columns in §C are **ALTER TABLE inside V134** if E1 prefers one migration for all of P1's
schema, **or** a third migration — PA recommendation: **fold the §C additive ALTERs into V134** as
additional DDL steps after the ledger CREATE, because they are P1-coherent and each is an
idempotent `ADD COLUMN IF NOT EXISTS`. The gate-seam table stays separate as V135. The C1 promote-
candidate table is **out of P1 scope** — it is P2, do not create it here.)

---

## F. D3 writer singleton

**Name:** `L2CallLedgerWriter` (process-global, single sanctioned write entry for `agent.l2_calls`
+ `learning.l2_gate_seam_log` + the §C provenance writes).

**Registration (mandatory before merge, CLAUDE.md §七/§九):** add a row to
`docs/architecture/singleton-registry.md` §2 using its 12-column format (`:39-44` defines the
columns: name / type_signature / location / owner_lifecycle / cross_task_pattern / lock_primitive /
visibility / caller_chain / health_monitoring / registered_date / governance_authority /
migration_plan). Proposed row:

| field | value |
|---|---|
| name | `L2CallLedgerWriter` (or module-level singleton binding) |
| type_signature | Python module-level singleton holding a PG connection-pool handle (mirror `bybit_ai_invocation_ledger` write-entry pattern) |
| location | `control_api_v1/app/<new file>:LINE` (E1 fills) — co-locate near `layer2_engine.py` |
| owner_lifecycle | constructed at control_api boot; lives for process; no live-trading lifecycle |
| cross_task_pattern | append-only INSERT on the advisory loop (Orchestrator → D3 write); read path is forensic SELECT |
| lock_primitive | DB-level append-only (REVOKE) is the real guard; in-process pool handle per asyncpg/psycopg norm |
| visibility | module-internal; sole public entry `record_l2_call()` / `record_gate_seam()` |
| caller_chain | Orchestrator (P2) + lane appliers (P2+); P1 ships the writer + tests, callers wire in P2 |
| health_monitoring | recommend yes (a silent D3-write failure = a lineage gap = root-principle-8 violation) |
| registered_date | (E1 merge date) |
| governance_authority | this design + design v4-final §D; execution plan Phase 1 |
| migration_plan | none (new) |

**Hard boundary the singleton honors:** it has **INSERT-only** authority (the `consequential`
promote is a *separate* `trading_admin`-scoped path, §A.4 — the writer never UPDATEs). It imports
**no** order surface, **no** `IntentProcessor`, **no** lease-acquire-for-trading — it is pure audit
(design §A.1 `:372-375`). CC will grep this in P2 (the Orchestrator no-auto-path audit), but the
writer module itself must already be clean in P1.

---

## G. E1 acceptance mapping (what each role verifies)

Maps each deliverable to execution-plan §2 Phase-1 acceptance bullets (`:99-122`) + the gating
ledger E2(sanitize) / E2(append-only) rows (`:77`, `:117-118`).

| Deliverable | E1 builds | E2 reviews | E3 verifies | E4 / dry-run |
|---|---|---|---|---|
| **A. V134 ledger** | `agent.l2_calls` CREATE + Guard A/B/C + hypertable + indexes + REVOKE append-only + V114-style `consequential` grant | append-only grant correct (no UPDATE/DELETE to `trading_ai`; narrow `consequential` UPDATE to `trading_admin` only); full 24-col schema; composite PK `(l2_reply_id, created_at)`; sha256 over sanitized text | — | **Linux PG double-apply idempotency** (see §H checklist) |
| **B. Sanitize redactor** | `l2_secret_redactor` (new) + reuse `error_sanitize` for error path; integrate on D3 write path before INSERT | redactor idempotent + versioned; integrated pre-INSERT; sha256 over sanitized | **[E3-HIGH, must PASS]** synthetic secret → `[REDACTED:*]`, never the secret, on the write path, no window; `str(e)` never verbatim (`error_code` + sanitized reason) | redactor unit tests on Linux venv |
| **C. Provenance columns** | additive `source_l2_reply_id` on `learning.hypotheses` / `replay.experiments` / `trading.fills` (columnstore-safe) + map `agent.lessons.context_id` + manifest jsonb key; **strategy-variant DEFERRED (no table)** | each ADD COLUMN nullable/no-backfill/no-NOT-NULL; columnstore-safe on `trading.fills`; root id never re-derived | — | **double-apply** each ALTER; columnstore `feature_not_supported` regression on `trading.fills` |
| **D. Gate-seam V135** | `learning.l2_gate_seam_log` CREATE + Guard A/C + hypertable + index + pure append-only REVOKE | schema + verdict CHECK enum + append-only | — | **double-apply idempotency** |
| **F. D3 writer singleton** | `L2CallLedgerWriter` INSERT-only + singleton registry row | registered in singleton SSOT; route-thin; INSERT-only (no UPDATE/DELETE); no order/lease imports | (P2 CC grep, but module clean in P1) | Mac+Linux test pass |

**Maps to the two gating-ledger rows:**
- **E2 (sanitize)** row (plan §1 `:77`): deliverable **B** — "redact secrets/`str(e)`/raw errors on
  the write path, all 4 large-text columns, before append." Owned by **E3** sign-off (plan §2 `:117`).
- **E2 (append-only)** row (plan §1, design §L `:1660`): deliverable **A** + **D** — "no UPDATE/DELETE
  grant for the app role." Owned by **E2** sign-off (plan §2 `:117`).

### H. Linux PG dry-run checklist (mandatory before P1 implementation sign-off)

Per `feedback_v_migration_pg_dry_run.md` (Mac mock cannot catch PG runtime semantics; idempotency
double-apply is load-bearing). Connection (from E1 memory `:13893`): docker container
`trading_postgres`, user `trading_admin`, db `trading_ai`. **E1/E4 run on `ssh trade-core`:**

1. **V134 first-apply** on a Linux PG → all Guard A/B/C `RAISE NOTICE ... PASS`; table + hypertable +
   indexes present; `REVOKE` block ran (or NOTICE'd dev-sandbox).
2. **V134 second-apply (idempotency)** → no `RAISE EXCEPTION`; Guard A reflects existing columns
   (no drift); the **column-level `GRANT UPDATE (consequential)`** must **not** abort on re-apply
   (if compression somehow enabled, the nested `EXCEPTION WHEN undefined_column` swallows it — V114
   lesson). **Recommended: P1 leaves compression OFF on `agent.l2_calls`, removing this risk.**
3. **append-only grant verification**: as `trading_ai`, attempt `UPDATE agent.l2_calls SET ...` →
   **permission denied**; `DELETE` → **permission denied**; `INSERT` → allowed. As `trading_admin`,
   `UPDATE agent.l2_calls SET consequential = true` → allowed; `UPDATE ... SET system_prompt = ...`
   → **permission denied** (column-scoped grant proves immutable forensic content).
4. **V135 first + second apply** → same idempotency; pure append-only REVOKE (no narrow exception).
5. **§C ALTERs double-apply**: `ADD COLUMN IF NOT EXISTS source_l2_reply_id` on `learning.hypotheses`,
   `replay.experiments`, `trading.fills` → second apply no-ops cleanly. **`trading.fills` is
   columnstore** → confirm the nullable/no-DEFAULT form does **not** raise
   `feature_not_supported` (the V077/V101 trap); a `SET NOT NULL` or `DEFAULT` would — E1 must use
   neither.
6. **Guard A/B re-apply no false-RAISE**: re-running V134/V135 against the already-migrated DB must
   produce only NOTICEs, never an EXCEPTION (the V133/V101 idempotency contract).
7. **Linux read-only confirmations** (the items Mac SQL cannot prove — §F escalations): (a) does a
   physical strategy-variant table exist? (grep said no; confirm on the live DB schema); (b) the
   Stage-1 demo manifest jsonb key path for `source_l2_reply_id`; (c) `decision_outcomes`
   hypertable/columnstore status (decides whether its ADD COLUMN needs the columnstore-safe form
   like `trading.fills`).

---

## I. Side-effect / hard-boundary checklist (PA discipline)

1. **Other modules importing the changed surface?** P1 adds new tables + a new writer + additive
   columns. The only *existing* code touched is `persist_lessons` setting `context_id = l2_reply_id`
   for L2-originated lessons (`V133` already has the column) and the `error_sanitize` reuse — both
   additive. No existing import breaks.
2. **Mocked functions?** The D3 writer is new; its tests verify intent (redaction on write path,
   append-only enforcement, root-id-never-re-derived), not just behavior (CLAUDE.md Operating Style 9).
3. **asyncio/threading boundary?** The writer does PG INSERT on the advisory loop; reuse the existing
   `bybit_ai_invocation_ledger` connection pattern (`:191-202`) — no new asyncio/thread mixing.
4. **API response schema change?** None. P1 is DB + writer; no route schema change (write endpoints
   are P2's Orchestrator concern, already operator-scope per plan §1 `:76`).
5. **Rust ↔ Python IPC schema?** **None in P1.** The R2-5 live hop (which *would* touch the Rust engine
   live-record path) is **deferred**. P1 is Python-control-plane + DB only.

**Hard boundaries (CLAUDE.md §四) — all honored:**
- No `live_execution_allowed` / `max_retries` / `system_mode` touch. ✔
- No new live path; R2-5 live hop deferred; P1 touches **zero** live tables. ✔
- L2 produces proposals never effects; D3 is audit/provenance only — no live authority. ✔
- Append-only ledger; sanitize on write path; secrets never verbatim. ✔
- New singleton registered before merge. ✔
- Rust-first N/A (P1 is audit/provenance on the Python control plane + PG, per design §A.1; the
  trading-truth layer stays Rust and is untouched). ✔

---

## J. Verdict

**E1-READY.** This is a design-only pass — no code, no migration apply, no DB write, no deploy was
performed. The design is complete enough for operator sign-off and for E1 to execute table-by-table.

**Three things that NEED an explicit decision before/at E1 (not blockers, but call them out):**
1. **`consequential` matrix → PA recommends Option (b)** (V114-style narrow `trading_admin`-only
   `UPDATE (consequential)` column grant, compression OFF in P1). If the operator/PM prefers the
   stricter Option (c) side-table or the simpler Option (a) creation-only, that is a one-line scope
   change — but (b) is the vetted-pattern recommendation and is what this design specs.
2. **strategy-variant provenance hop is N/A for P1** because no physical variant table exists
   (grep-confirmed; Linux read-only re-confirm in §H.7a). The chain is forward-compatible; this hop
   lands when a variant table first exists. PM should accept this hop as deferred-by-absence.
3. **Migration packaging**: PA recommends V134 = ledger **+** the §C additive ALTERs (P1-coherent,
   all idempotent), V135 = gate-seam. If PM prefers strict one-table-per-migration, split the §C
   ALTERs into a third number — functionally equivalent, more files.

**Three E2-must-scrutinize points (PA flags for the reviewer):**
1. **Composite PK `(l2_reply_id, created_at)`** — the hypertable forces it; the design's "text PRIMARY
   KEY" shorthand is a trap. Verify E1 used the composite (V035/V064/V114 precedent).
2. **`prompt_sha256`/`response_sha256` computed over SANITIZED text** — if E1 hashes the raw text
   before redaction, the hash won't match the stored row (design `:698-699`). This is a subtle
   ordering bug; E2 must confirm hash-after-sanitize.
3. **`trading.fills` columnstore ADD COLUMN** — must be nullable, no DEFAULT, no SET NOT NULL
   (V077/V101 `feature_not_supported` trap). E2 + E4 must confirm the columnstore-safe form on the
   live Linux DB, not just the Mac mock.

Report path: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-d3-phase1-tech-design.md`
