# L2 Advisory Mesh — Phase 1 (D3 Provenance & Audit) Technical Design

Date: 2026-06-08
Author: PA (Project Architect)
Status: **E1-READY · LOCKED (design-only)** — no code, no migration apply, no DB write, no deploy in this pass. Operator final decisions 2026-06-08 (`consequential`=side-table Option (c); provenance ALTER=own V136) are LOCKED into this doc, overriding the earlier PA recommendations.
Owner chain (this phase): PM → **PA (this doc)** → E1/E1a → E2 → E3 → E4 → QA → PM.
SSOT design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--l2-advisory-mesh-design-draft.md` (v4-final, 4-review-passed).
Execution plan: `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md` §0/§1/§2 Phase 1.
Operator scope ruling (2026-06-08): P1 = ledger + sanitize + **upstream research-plane** provenance columns only. The R2-5 live-fills/outcomes + Decision-Lease audit-row hop is **EXPLICITLY DEFERRED** to a separate gated step (forward-compatible, not designed here).

This document does **not** re-litigate the v4-final design. It grounds every Phase-1 schema/table
assertion in `file:line`, locks the design items the execution plan flagged — now operator-RESOLVED
2026-06-08: `consequential` = **append-only side-table** (Option (c)), provenance ALTERs = **own
migration V136**, strategy-variant hop = **deferred-by-absence** — together with redactor
reuse-vs-build and exact upstream target tables, and hands E1 a table-by-table executable spec.

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
| **append-only enforcement pattern** | repo has **two** patterns; D3 uses the **DB-level REVOKE** pattern (stronger) on **all three** P1 tables, with **zero column-level UPDATE grant anywhere** (operator-LOCKED Option (c)). `consequential` is modeled as an append-only side-table (`agent.l2_consequential_marks`), not a mutable ledger column — so the ledger is freely compressible later (V114 twin trap N/A). | See §A.3 / §A.4 below. App business role = **`trading_ai`** (INSERT/SELECT only); admin/correction role = **`trading_admin`** (`V099:294-307`). Side-table precedent: `learning.lease_transitions` (`V054:225`). |
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
  consequential_at_creation BOOLEAN NOT NULL DEFAULT false  -- IMMUTABLE: set once at INSERT from registry default; NEVER UPDATEd. retention class (§Q6); later-discovered consequence is recorded in the append-only side-table agent.l2_consequential_marks — see A.4.
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
  `created_at`=`timestamp with time zone`, `consequential_at_creation`=`boolean`. (Drift here = a
  JSONB column silently created as text would break the writer.)
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
  - PK `(l2_reply_id, created_at)` already serves the primary `WHERE l2_reply_id = ?` lookup (§D.4
    step 2).
  - **Retention index DEFERRED with the retention logic (§Q6 is post-P1).** P1 locks table *shape*
    only — it ships **no `drop_chunks` policy and no retention partial index**. When retention lands
    (post-P1), the correct predicate for the (c) shape is *"keep if consequential-at-creation OR a
    mark exists"*, i.e. drop targets rows where `consequential_at_creation = false` **AND NOT EXISTS
    a row in `agent.l2_consequential_marks`** (the anti-join, §Q6 below). The matching support index
    is therefore `(created_at DESC) WHERE consequential_at_creation = false` — but it is built **with**
    the retention migration, not in V134, so the index does not falsely imply a retention policy
    exists. (The old single-column `WHERE consequential = false` partial index is removed: under (c)
    a false-at-creation row may still be retention-worthy via a later mark, so that predicate alone
    is wrong.)

### A.4 Append-only enforcement + the `consequential` resolution [LOCKED — operator 2026-06-08: Option (c) side-table]

**The repo has a mature, vetted append-only pattern — D3 uses it, not application-discipline-only.**

There are two patterns in the repo:
1. **Application-discipline append-only** (V064 `decision_state_changes`, V133 `agent.lessons`,
   V035 `governance_audit_log`): no DB REVOKE; relies on "single INSERT write entry + read-only
   read." Used for low-blast audit logs.
2. **DB-level REVOKE append-only** (the strong pattern): `REVOKE UPDATE, DELETE FROM PUBLIC` +
   `REVOKE FROM trading_ai`. Used where immutability is load-bearing:
   - V099 `system.autonomy_level_switch_audit` (`:298-307`, verified verbatim) — the **closest
     semantic precedent**: "trading_ai 業務 role 完全不可 UPDATE/DELETE；只有 trading_admin 透過顯式
     ADR-0006 數據訂正路徑可動" (`:294-296`).
   - V058 (`:136-137`), V059 (`:112`), V060 (`:95`) — pure `REVOKE UPDATE, DELETE FROM PUBLIC`.

**D3 ledger uses pattern 2** (DB-level), because a leak-bearing, hard-to-purge audit store that
*also* permits silent post-hoc UPDATE would defeat root principle 8 (reconstructable).

#### A.4.1 LEDGER `agent.l2_calls` — PURE append-only, ZERO column-level UPDATE grant

The ledger gets **no UPDATE grant of any kind** (not even a narrow column-scoped one). The D3 writer
holds **INSERT + SELECT only**. There is **no mutable `consequential` path on the ledger** — that
property is recorded immutably-at-creation in the ledger column `consequential_at_creation` (set once
at INSERT, never UPDATEd) and, for the *later-discovered* case, in a separate append-only side-table
(A.4.2). Concrete E1 SQL, mirroring V099 `:298-307` (the DO-block guard handles dev-sandbox where
`trading_ai` is absent):

```sql
REVOKE UPDATE, DELETE ON agent.l2_calls FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON agent.l2_calls FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT ON agent.l2_calls TO trading_ai';
        RAISE NOTICE 'V134: agent.l2_calls — trading_ai = INSERT/SELECT only; UPDATE/DELETE revoked';
    ELSE
        RAISE NOTICE 'V134: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;
```

**Why this is the LOCKED design and why it beats the rejected narrow-column-UPDATE option (the
long-term key):** because the ledger carries **zero column-level `GRANT UPDATE (...)`**, the V114
compressed-twin trap **cannot occur on `agent.l2_calls`**. The trap is exclusively a property of
column-level UPDATE grants: TimescaleDB propagates a `GRANT UPDATE (col)` to the
`_compressed_hypertable_NN` twin, whose columns are compressed-segment format, so the grant aborts
with `ERROR: column "<col>" of relation "_compressed_hypertable_NN" does not exist`
(SQLSTATE 42703 undefined_column) — verified verbatim in `V114:208-216` + the nested-exception
idempotency kludge `V114:249-257`. With **no** column-level grant on the ledger, **TimescaleDB
compression is freely enableable on `agent.l2_calls` in any future phase** with no reorder, no
nested-exception kludge, no twin-abort risk. This is the long-term-extensibility reason the operator
chose (c): the ledger stays a clean, compressible, purely-append-only forensic store.

(For P1 itself the design still does **not** enable compression — §A.4.4 / §H — but the point is
that (c) leaves that door open trivially, whereas the rejected narrow-column-UPDATE option would
have permanently coupled the ledger to the V114 ordering+nested-exception discipline.)

#### A.4.2 NEW append-only side-table `agent.l2_consequential_marks` (built in V134)

`consequential` is an **"discovered-after-the-fact" attribute** — a reply's artifact may only reach
a retention-worthy lane *later*. Modeling that as an **append-only event** (not a ledger column
UPDATE) is both correct and idiomatic in this repo: it lets the same `l2_reply_id` be marked
**multiple times, for multiple reasons, by multiple lanes/actors**, each carrying its own
when/why/which-lane/by-whom — strictly richer than a single boolean flip, and it keeps the ledger
pure.

**Repo precedent for an append-only event/transition side-table (cited):**
`learning.lease_transitions` (`V054__lease_transitions_audit_writer.sql:225`, schema `learning`, PK
`(transition_id, created_at)` `:240`) is exactly this shape — every lease state change is an
**appended row**, never a row mutation; the "current state of a lease" is the latest appended
transition, not an UPDATE. The marks table applies the identical event-sourced pattern to the
"became consequential" event. (Same family as the gate-seam log §D, which is also a `learning`/`agent`
append-only event table.)

(E1 note: the `agent` schema already exists — `V001:35` / `V064:18` / `V133:38` all
`CREATE SCHEMA IF NOT EXISTS agent;` — so V134 mirrors that idempotent `CREATE SCHEMA IF NOT EXISTS
agent;` at its top before either `agent.*` CREATE, exactly as V133 does, and does not assume it.)

```sql
-- built INSIDE V134 (same retention/lifecycle unit as the ledger it annotates)
CREATE TABLE IF NOT EXISTS agent.l2_consequential_marks (
  mark_id      BIGSERIAL,
  l2_reply_id  TEXT        NOT NULL,            -- joins agent.l2_calls.l2_reply_id (logical FK, not DB FK)
  marked_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reason       TEXT        NOT NULL,            -- why it became consequential (free text / code)
  lane         TEXT,                            -- which retention-worthy lane it entered (NULL = unspecified)
  marked_by    TEXT,                            -- which applier/role/actor recorded the mark
  details      JSONB       NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (mark_id, marked_at)              -- composite (this table is a hypertable on marked_at)
)
```

- **Hypertable** on `marked_at`, 7-day chunks (V035 `:141-154` interval form — `marked_at` is
  timestamptz). Composite PK `(mark_id, marked_at)` for the same hypertable-unique-constraint reason
  as the ledger (A.1) — mirrors `lease_transitions` `(transition_id, created_at)` `:240`.
- **Guard A** on CREATE TABLE (V133 `:41-78` shape; required-column reflection).
- **Index** `idx_l2_marks_reply` ON `(l2_reply_id, marked_at DESC)` — the retention anti-join + "show
  me why this reply is consequential" forensic query. Guard C verifies it.
- **Pure append-only — REVOKE UPDATE/DELETE, NO column-level UPDATE grant** (same block shape as the
  ledger A.4.1, table name swapped). The marks table is itself append-only, so it *also* carries no
  column-level UPDATE grant → it too is freely compressible later. A correction to a wrong mark is a
  **new compensating mark row** (e.g. `reason='retracted:<mark_id>'`), never an UPDATE — the
  event-sourced discipline of `lease_transitions`.

```sql
REVOKE UPDATE, DELETE ON agent.l2_consequential_marks FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON agent.l2_consequential_marks FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT ON agent.l2_consequential_marks TO trading_ai';
        EXECUTE 'GRANT USAGE ON SEQUENCE agent.l2_consequential_marks_mark_id_seq TO trading_ai';
        RAISE NOTICE 'V134: agent.l2_consequential_marks — trading_ai = INSERT/SELECT only; UPDATE/DELETE revoked';
    ELSE
        RAISE NOTICE 'V134: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;
```

#### A.4.3 at-creation sub-variant chosen: (i) immutable ledger boolean + marks table

Two sub-variants were on the table for the *known-at-creation-consequential* case:
- **(i)** ledger keeps an **immutable** `consequential_at_creation BOOLEAN DEFAULT false` (INSERT-set
  once from the registry default, **never UPDATEd → needs no grant**), and the marks table covers
  later-discovered consequence.
- **(ii)** marks-only — at-creation-known rows insert a mark `reason='at_creation'` in the same txn
  as the ledger INSERT; the ledger carries no consequential column at all.

**PA selects (i).** Justification (cleanliness, the operator's stated optimization axis):
1. **It keeps the common-case predicate a cheap single-column ledger scan, no join.** The
   known-at-creation case is expected to be the bulk; with (i), "is this reply
   consequential-at-creation?" is `consequential_at_creation = true` on the ledger row already in
   hand (the row you just fetched by `l2_reply_id`), with **no second-table lookup**. (ii) would
   force every at-creation-known reply through a second INSERT into the marks table in the same txn
   and every such predicate through a join/EXISTS — more write amplification and more read cost for
   the majority case.
2. **`consequential_at_creation` is INSERT-only → it does NOT reintroduce the V114 trap.** It is set
   once by the writer at INSERT and never UPDATEd, so the ledger still carries **zero column-level
   UPDATE grant** — the compressibility property of A.4.1 is fully preserved. (i) gets the cheap
   at-creation flag *without* any of the mutable-column baggage that drove the operator away from the
   narrow-column-UPDATE option.
3. **Marks table still owns the genuinely-dynamic signal** (later lane entry, multi-reason,
   multi-actor) — (i) does not weaken the event-sourced richness; it only fast-paths the static
   at-creation bit.

**The "is this reply consequential?" predicate (LOCKED) is therefore the OR / EXISTS:**

```sql
-- a reply is consequential iff it was flagged at creation OR has at least one later mark
SELECT c.l2_reply_id
FROM agent.l2_calls c
WHERE c.consequential_at_creation = true
   OR EXISTS (SELECT 1 FROM agent.l2_consequential_marks m WHERE m.l2_reply_id = c.l2_reply_id);
```

#### A.4.4 retention (post-P1, §Q6) — P1 locks shape only

P1 ships **table shape only**: **no `drop_chunks` policy, no retention partial index, and NO
compression** on either `agent.l2_calls` or `agent.l2_consequential_marks`. When retention lands
(post-P1, §Q6 below), the drop logic is the **anti-join against the marks table** plus the at-creation
flag: a non-consequential chunk is one whose rows all have `consequential_at_creation = false`
**AND NOT EXISTS** a mark in `agent.l2_consequential_marks`. The matching support index
(`(created_at DESC) WHERE consequential_at_creation = false` on the ledger, plus the
`idx_l2_marks_reply` already built) is created **with the retention migration**, not in V134, so V134
does not falsely imply a retention policy exists. **P1 contains no drop logic and enables no
compression** (the latter is now a *free future option*, per A.4.1, precisely because there is no
column-level UPDATE grant anywhere).

#### A.4.5 write-side contract (LOCKED)

- **`L2CallLedgerWriter` is INSERT-only on the ledger** (`agent.l2_calls`) — never UPDATE/DELETE.
  `consequential_at_creation` is one of the INSERT values (set from the registry
  `consequential_default`, design §B `:443`), written **once** at row creation.
- **"became consequential later" = a separate append-only INSERT into `agent.l2_consequential_marks`**
  (NOT a ledger UPDATE). At-creation-known consequence is captured by the ledger boolean (sub-variant
  i); a later lane-entry path appends a mark row. Both writes are INSERTs; **nothing ever UPDATEs the
  ledger.** The at-creation-known case does **not** require a same-txn mark (that was variant ii,
  rejected) — the immutable boolean suffices, and a mark is added only if/when a *later* event occurs.
- This keeps the writer single-entry append-only (root principle 1/8) while honoring §Q6's
  "consequence discovered after the fact" requirement, and — the operator's long-term key — leaves
  both tables purely append-only and therefore **freely compressible** with zero V114 twin risk.

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

### B.5 [E1 fix-round addendum — redactor v2 → v3, operator-A pivot + honest residual] (2026-06-08)

**v2 history (kept honest, not whitewashed).** E3's first adversarial review RETURNed the v1 redactor
(1 HIGH: bare/encoding-evasion key shapes stored verbatim). The E1 v2 response added a **blanket bare
high-entropy arm** (any `[A-Za-z0-9+/=_-]{24,}` with entropy ≥ 3.5 + ≥2 char-classes → redact),
intending to catch bare base64 / 64-hex HMAC. **This arm exceeded the PA-LOCKED §B.2 spec**, which only
authorized high-entropy redaction **keyed by an adjacent keyword** (`api_key`/`secret`/`key=`), plus the
named structural arms — never standalone bare high-entropy. re-E2 empirically measured the blanket arm
**falsely redacting ~29% of legitimate forensic content** (git-SHA, sha256 digests, config-flag names,
model-ids — all legitimately high-entropy), which **destroys ledger reconstructability — the very purpose
of D3** (principle 8). The v2 pin was an E1 over-reach; this addendum does not paper over it.

**Operator decision (2026-06-08) = A.** Revert to **keyword-gated + structural arms**, accept the
**naked-context-free residual**. Rationale: information-theoretically, a *bare* secret token is
**indistinguishable** from a legitimate high-entropy identifier (sha256/git-SHA/base64 config) without
mass false-positive redaction; the best fix for the truly-naked residual is **source-side at P3** (the
producer not writing raw key material into prompts/summaries), not redactor-side mass over-redaction
that blinds the forensic store. `redactor_version` bumped `l2_redactor.v2 → l2_redactor.v3`.

**v3 coverage (what is still redacted):**

- **keyworded arm** (the §B.2-authorized high-entropy path): value adjacent to
  `api_key`/`apiKey`/`secret`/`password`/`token`/`X-BAPI-SIGN`/`PGPASSWORD`/… → value redacted,
  min-length lowered so a `<16`-char `api_key=` value no longer leaks (§B.2.d).
- **structural arms (keyword-free, distinguishable, low false-positive — these match the PA §B.2
  structural-arm spirit, retained):** DSN scheme (`postgres|mysql|redis|amqp|mongodb…://user:pw@`,
  credential redacted, scheme/host kept), JWT (`eyJ….….…`), private IP (10/8, 172.16/12, 192.168/16,
  192.0.2/24, 127/8, 169.254/16, IPv6 fc00::/7 + fe80::/10), internal host (`trade-core`, `*.local`).
- **JSONB key-name arm**: a dict key in {authorization, api[_-]?key, secret, password, token,
  x-bapi-sign, dsn, connection_string, private_key, …} → value redacted regardless of structure
  (catches header-echo dicts whose value carries no keyword/structure).
- **encoding-evasion**: NFKC normalize + strip zero-width/control + URL-decode-once are still applied —
  but **for detection only** (see store-original below).

**v3 removed (operator A):** the blanket bare high-entropy arm (`_redact_high_entropy` /
`_HIGH_ENTROPY_CANDIDATE_RE`) is **deleted**. Non-keyword, non-structural bare high-entropy strings are
**no longer redacted** — back to PA-LOCKED §B.2 behavior plus the in-spec tradeoff the earlier E2 had
signed.

**v3 store-original-by-span invariant (§B.5 fix Finding 2):** the redactor now **stores the original
text with only the actual secret span replaced by `[REDACTED:*]`** — not the normalized text.
Normalization (NFKC / url-decode / strip) is used **only to detect** evasions; a `normalized→original`
offset map maps each detected span back to the original, and redaction is applied on the **original**.
Consequence: a zero-secret input (CJK full-width punctuation `，：（）`, legitimate `%2F`/`%20`,
zero-width chars) is stored **byte-identical** — previously v2 stored the normalized rewrite, which is
no longer the "as-sent" text and would corrupt forensic reconstruction. `prompt_sha256`/`response_sha256`
are computed over this original-redacted text (the writer still hashes `redactor.text`; the
`RedactResult.text` contract is unchanged, only its content is now original-redacted). For an evasion
that cannot map cleanly, the fail-safe redacts the minimal mapped region — **never leaks the secret,
never corrupts unrelated text**.

**Honest residual (information-theoretic limit, operator-A accepted):** a **naked-context-free**
high-entropy string — a bare alnum token / bare 64-hex / bare base64 blob with **no adjacent keyword and
no JWT/DSN/IP structure** — is not redacted, because it cannot be pattern-distinguished from a legitimate
high-entropy identifier without the ~29% false-positive blast measured above. **Every *named* critical
asset is still caught** (Bybit API key / secret / bearer / HMAC sign / authorization.json material /
secret-slot / DSN / private topology), because in real flows those assets virtually always carry their
customary keyword or structural shape. The truly-naked residual's best fix is **P3 source-side**. These
residual vectors are marked `xfail(strict)` in the test suite so they cannot silently regress to
"claimed-covered" (a strict-XPASS would force re-review). ReDoS: all v3 regex are linear (no nested
quantifier / overlapping alternation).

**Finding 3 (D.1.1 closure, re-E3 LOW-1):** `Layer2CostTracker.record_session` now passes the session's
LLM free-text fields (`final_summary`, `recommendation.reasoning`, `insights[].title/detail`) through
the redactor **before** the durable write to `layer2_cost_state.json`, satisfying §D.1.1 "applies
everywhere full text is persisted". Structural/numeric fields (cost/tokens/symbol/action) are left
untouched.

### B.5.1 [E1 fix-round addendum — redactor v3 → v4: CRITICAL gate fix + keyword completeness + DoS cap] (2026-06-08)

This round closes the re-E2 **CRITICAL secret-leak** plus two re-E3 LOWs. `redactor_version` bumped
`l2_redactor.v3 → l2_redactor.v4`.

**CRITICAL — fast-path gate secret-leak (re-E2, Finding 1).** The v3 fast-path gate was
`not _NEEDS_OFFSET_MAP_RE.search(text) AND is_normalized("NFKC")`. `_NEEDS_OFFSET_MAP_RE` was a
**hand-listed codepoint range** and was **not a superset of** the actual strip predicate
`_is_control_or_format` (the slow-path strips every `Cc`/`Cf` char + the explicit zero-width set, keeping
only `\t\n\r`). Empirically the regex **missed 136 strip-set characters** that are simultaneously
(a) stripped by detection and (b) NFKC-stable — e.g. U+00AD, U+061C, U+06DD, U+070F, U+180E,
U+2066–2069 isolates, the U+E0000 tag block (U+E0001/U+E0020–E007F). A secret whose keyword was split by
any such char (`api⁦_key=<secret>`) took the **fast-path**, where detection runs on the **raw** (un-stripped)
text → the keyword stays broken → no match → the secret is stored **verbatim** into the append-only ledger.
**Fix (E2 direction A, gate-set == strip-set by construction):** the gate is now `_needs_offset_map(text)`,
which routes to slow-path iff the text contains **any** `_is_control_or_format(c)` char, **or** `'%'`,
**or** is non-NFKC-normalized. Because the gate **reuses the strip predicate itself**, the gate-set and
strip-set are structurally identical and the drift is impossible to reintroduce. A brute-force test asserts
that **all** strip-set chars over the entire Unicode space route to slow-path (RED on any future drift),
and a parametrized regression asserts keyword-split secrets (U+180E/U+061C/U+2066–2069/a U+E00xx tag char)
are fully redacted with no verbatim residual. The earlier suite only exercised U+200B, missing the other 134.

**LOW-1 — keyword-set completeness (re-E3, closes a v2→v3 regression).** The keyworded arm
(`_KW_DISPATCH`) and the JSONB key-name arm (`_SENSITIVE_KEY_RE`) gained: `auth_signing_key`, `hmac_key`,
`hmac`, `signing_key`, `signing_secret`, `auth_key`, naked `secret`, `private_key`. This makes §B.5's
"every named critical asset still caught" literally true and aligns with the secret-leak-detection skill's
Pattern-A. Alternation order is longest/most-specific-first within each group (e.g. `hmac_key` before
`hmac`, `auth_signing_key` before `signing_key`) and naked `secret` is the catch-all tail of `g_api`, so a
shorter prefix never shadows a longer keyword and back-tracking stays minimal (ReDoS-safe). Each keyword has
both a free-text `kw=value` test and a JSONB-key test.

**LOW-2 — `raw_response`/`input_context` size cap (re-E3, DoS guard).** `redact()` now truncates input
over a high-water **256KB** constant (`_MAX_REDACT_INPUT_CHARS`) **before** detection, appending a logged
`…[TRUNCATED:n chars]` marker, with idempotent re-truncation suppression (output already carrying the marker
is not re-truncated, preserving the no-op-on-already-redacted invariant). Placing the cap at the redactor
entrypoint bounds **every** persistence caller (ledger `system_prompt`/`raw_response`/`final_summary`,
cost-tracker free-text, JSONB string leaves) in one place. **Rationale:** the store-original per-char Python
loop is **super-linear** on degenerate all-evasion input (~n^1.7; 9.4s at 800K pre-cap); the cap clamps the
worst case to ~23ms regardless of input size (800K and 2M both clamp to 256K), and bounds durable storage.
256KB is far above any realistic L2 response (realistic responses are << 256KB), so the cap only bounds
pathological/abusive input and never affects the full-forensic goal — consistent with the existing cap
discipline (`final_summary[:2000]`, `str(e)[:500]`). A secret inside the retained region is still redacted.

**Honest scope note.** The operator-A **naked-context-free residual** is unchanged: the 4 xfail(strict)
residual tests still hold (no XPASS), confirming the gate fix and keyword additions did **not** start
catching truly-bare high-entropy tokens (which would re-introduce the ~29% false-positive blast). ReDoS:
all v4 regex remain linear; the cap additionally hard-bounds the per-char loop. Mac-tested (mocked PG);
Linux PG dry-run + re-E3 adversarial stress owed to E4.

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
| **demo fills / `decision_outcomes`** | demo fills = **`trading.fills`** (engine_mode='demo'; `V003` base + `V015:15` engine_mode); `decision_outcomes` = `V005__indexes_views.sql` / extended `V101`/`V074` | `source_l2_reply_id TEXT NULL` on each | **`trading.fills` is a TimescaleDB columnstore hypertable** (`V101:49-53`). **CRITICAL:** ADD COLUMN must be **nullable, no DEFAULT, no SET NOT NULL** (columnstore `feature_not_supported` per V077 lesson; V101 `:170-181` is the exact vetted range). `trading.decision_outcomes` is documented as a **plain table** (`V075:8` "2 plain tables: learning.decision_features, trading.decision_outcomes") → a plain `ADD COLUMN` would suffice; but confirm on live `timescaledb_information.hypertables` before finalizing (migration-text could be stale) — **and note `decision_outcomes` provenance belongs to the deferred R2-5 live hop, not P1's V136** (see R2-5 note below). `trading.fills` (demo) IS in P1's V136. | `ALTER TABLE trading.fills ADD COLUMN IF NOT EXISTS source_l2_reply_id TEXT NULL;` (columnstore-safe form). Guard A/B mirror V101 `:90-167`. |
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
- Append-only via the same `REVOKE UPDATE, DELETE FROM PUBLIC` + `REVOKE FROM trading_ai` +
  `GRANT SELECT,INSERT` block as §A.4.1 (under the LOCKED Option (c), **all three P1 tables**
  — ledger, marks, gate-seam — are pure append-only with **zero column-level UPDATE grant**, so
  all three are uniformly compressible later; there is no narrow-column UPDATE exception anywhere).
- `verdict` CHECK enum matches the guard-verdict vocabulary already in the ledger's `guard_verdict`
  (design `:659`, `:818`).

### D.2 Gate-seam migration number — V135 (unchanged)

**Gate-seam stays in its own migration `V135__l2_gate_seam_log.sql`** (next free after V134,
**skipping the V128 soft-reservation**).

Rationale:
- **Different schema** (`learning` vs `agent`), different table, different lifecycle. Bundling
  unrelated DDL into one migration muddies the dry-run blast radius and the idempotency reasoning
  (each V### should be one coherent green checkpoint — CLAUDE.md "Git And Sync").
- The execution plan §0 (`:31`) already anticipates a "V13x" companion table. Using **V135 for
  gate-seam** keeps the C1 promote-candidate table (a P2 concern, design §O.4 `:1579`) for a later
  number.
- **E1 dry-run note:** V134 and V135 are independent (no inter-migration FK — `l2_reply_id` is a
  logical join, not a DB FK, mirroring V064 `decision_edges` "logical FK only" `:106-107` and V035's
  nullable candidate_id). So they can be dry-run + double-applied independently.

### E. Migration numbering (final) [LOCKED — operator 2026-06-08: provenance ALTER → its own V136]

P1 is **three** migrations:

| Migration | Contents | Free? |
|---|---|---|
| **V134** | `agent.l2_calls` (ledger, §A.1) **+** `agent.l2_consequential_marks` (side-table, §A.4.2) | YES — V133 highest; no V134 exists. |
| **V135** | `learning.l2_gate_seam_log` (gate-seam, §D) | YES — next clean free after V134, skips V128 soft-reservation. |
| **V136** | upstream provenance additive `ALTER`s (§C: `source_l2_reply_id` on `learning.hypotheses` / `replay.experiments` / `trading.fills`) | YES — next clean free after V135. V136 > V133 head, ≠ V128 soft-reservation, no collision with the V129-V133 already-present range. |

**Why V136 is its own migration (operator-LOCKED, overrides the earlier "fold into V134" rec):**
the ledger + marks are **fully designable today** (every shape is grounded), so V134 should be a
**clean, early-finalizable** migration. The §C provenance ALTERs have **Linux-verify dependencies
that V134 must not inherit** — specifically (a) whether `trading.fills`'s columnstore form needs the
nullable/no-DEFAULT/no-SET-NOT-NULL discipline confirmed on the live DB (V077/V101 trap), and (b)
whether the `decision_outcomes` / demo-manifest targets are tables-vs-jsonb on the live schema.
Splitting V136 out means V134 can be dry-run + signed off **without waiting** on those Linux
confirmations, and the provenance ALTERs land in V136 once §H.7 confirms them — with a **cleaner,
isolated rollback / dry-run blast radius** (a columnstore `feature_not_supported` regression, if any,
is contained to V136 and cannot taint the ledger migration). The gate-seam table stays separate as
V135. The C1 promote-candidate table remains **out of P1 scope** — it is P2, do not create it here.

**Migration-freedom check (all three):** `ls sql/migrations/` head = `V133__agent_lessons.sql`;
present high range = V125, V126, V127, V129, V130, V131, V132, V133 (**V128 absent = the
soft-reservation**, `V127:125` "V128 reserved-if-needed 給 deferred breadth 表"). Therefore **V134,
V135, V136 are all unused and contiguous-after-V133**, and none collides with the V128
soft-reservation. E1 must re-confirm on the Linux `_sqlx_migrations` head before applying (parallel
sessions could claim numbers — execution-plan §0 needs-verify guard).

---

## F. D3 writer singleton

**Name:** `L2CallLedgerWriter` (process-global, single sanctioned write entry for `agent.l2_calls`
+ `agent.l2_consequential_marks` + `learning.l2_gate_seam_log` + the §C provenance writes — **all
INSERT-only**).

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
| lock_primitive | DB-level append-only (REVOKE UPDATE/DELETE, zero column-level UPDATE grant on all 3 tables) is the real guard; in-process pool handle per asyncpg/psycopg norm |
| visibility | module-internal; sole public entries `record_l2_call()` / `record_consequential_mark()` / `record_gate_seam()` (all INSERT-only) |
| caller_chain | Orchestrator (P2) + lane appliers (P2+); P1 ships the writer + tests, callers wire in P2 |
| health_monitoring | recommend yes (a silent D3-write failure = a lineage gap = root-principle-8 violation) |
| registered_date | (E1 merge date) |
| governance_authority | this design + design v4-final §D; execution plan Phase 1 |
| migration_plan | none (new) |

**Hard boundary the singleton honors:** it has **INSERT-only** authority on **all three** P1 tables
(ledger, marks, gate-seam) — it **never UPDATEs**. The "became consequential later" signal is an
INSERT into `agent.l2_consequential_marks` (§A.4.2/§A.4.5), not a ledger UPDATE; the at-creation flag
`consequential_at_creation` is set once in the ledger INSERT and never mutated. It imports **no**
order surface, **no** `IntentProcessor`, **no** lease-acquire-for-trading — it is pure audit
(design §A.1 `:372-375`). CC will grep this in P2 (the Orchestrator no-auto-path audit), but the
writer module itself must already be clean in P1.

---

## G. E1 acceptance mapping (what each role verifies)

Maps each deliverable to execution-plan §2 Phase-1 acceptance bullets (`:99-122`) + the gating
ledger E2(sanitize) / E2(append-only) rows (`:77`, `:117-118`).

| Deliverable | E1 builds | E2 reviews | E3 verifies | E4 / dry-run |
|---|---|---|---|---|
| **A. V134 ledger + marks** | `agent.l2_calls` CREATE (Guard A/B/C + hypertable + indexes + **pure** REVOKE append-only, **zero column-level UPDATE grant**) **AND** `agent.l2_consequential_marks` CREATE (Guard A/C + hypertable + `idx_l2_marks_reply` + pure REVOKE append-only) — both in V134 | **both** tables append-only with `trading_ai` = INSERT/SELECT only, **no UPDATE/DELETE, no column-level UPDATE grant anywhere**; ledger 24-col schema incl. immutable `consequential_at_creation`; composite PK `(l2_reply_id, created_at)` (ledger) + `(mark_id, marked_at)` (marks); sha256 over sanitized text; consequential predicate = ledger-flag-OR-marks-EXISTS (§A.4.3) | — | **Linux PG double-apply idempotency** for both tables (see §H) |
| **B. Sanitize redactor** | `l2_secret_redactor` (new) + reuse `error_sanitize` for error path; integrate on D3 write path before INSERT | redactor idempotent + versioned; integrated pre-INSERT; sha256 over sanitized | **[E3-HIGH, must PASS]** synthetic secret → `[REDACTED:*]`, never the secret, on the write path, no window; `str(e)` never verbatim (`error_code` + sanitized reason) | redactor unit tests on Linux venv |
| **C. Provenance columns (V136)** | additive `source_l2_reply_id` on `learning.hypotheses` / `replay.experiments` / `trading.fills` (columnstore-safe) in **V136** + map `agent.lessons.context_id` + manifest jsonb key; **strategy-variant DEFERRED (no table)** | each ADD COLUMN nullable/no-backfill/no-NOT-NULL; columnstore-safe on `trading.fills`; root id never re-derived; V136 isolated from V134 | — | **V136 double-apply** each ALTER; columnstore `feature_not_supported` regression on `trading.fills` |
| **D. Gate-seam V135** | `learning.l2_gate_seam_log` CREATE + Guard A/C + hypertable + index + pure append-only REVOKE | schema + verdict CHECK enum + append-only (zero column-level UPDATE grant) | — | **V135 double-apply idempotency** |
| **F. D3 writer singleton** | `L2CallLedgerWriter` INSERT-only (all 3 tables) + singleton registry row | registered in singleton SSOT; route-thin; INSERT-only (no UPDATE/DELETE anywhere); no order/lease imports | (P2 CC grep, but module clean in P1) | Mac+Linux test pass |

**Maps to the two gating-ledger rows:**
- **E2 (sanitize)** row (plan §1 `:77`): deliverable **B** — "redact secrets/`str(e)`/raw errors on
  the write path, all 4 large-text columns, before append." Owned by **E3** sign-off (plan §2 `:117`).
- **E2 (append-only)** row (plan §1, design §L `:1660`): deliverable **A** (ledger **+** marks) +
  **D** (gate-seam) — "no UPDATE/DELETE grant for the app role" — and, under the LOCKED Option (c),
  the **stronger** invariant: **no column-level UPDATE grant on any P1 table** (so all three are
  compressible later with no V114 twin risk). Owned by **E2** sign-off (plan §2 `:117`).

### H. Linux PG dry-run checklist (mandatory before P1 implementation sign-off)

Per `feedback_v_migration_pg_dry_run.md` (Mac mock cannot catch PG runtime semantics; idempotency
double-apply is load-bearing). Connection (from E1 memory `:13893`): docker container
`trading_postgres`, user `trading_admin`, db `trading_ai`. Checklist covers **all three** P1
migrations (V134 = ledger **+** marks; V135 = gate-seam; V136 = provenance ALTERs). **E1/E4 run on
`ssh trade-core`:**

**V134 — ledger `agent.l2_calls` + side-table `agent.l2_consequential_marks`:**
1. **V134 first-apply** → all Guard A/B/C `RAISE NOTICE ... PASS` for **both** tables; both tables +
   both hypertables + all indexes (incl. `idx_l2_marks_reply`) present; both `REVOKE` blocks ran
   (or NOTICE'd dev-sandbox).
2. **V134 second-apply (idempotency)** → no `RAISE EXCEPTION`; Guard A reflects existing columns on
   both tables (no drift). **There is no column-level `GRANT UPDATE (...)` anywhere in V134**, so the
   V114 compressed-twin abort path **cannot trigger** — this is the structural win of Option (c).
   E1 must confirm V134 contains **no** `GRANT UPDATE (...)` statement on either table (grep the
   migration: zero hits).
3. **append-only grant verification — LEDGER**: as `trading_ai`, `UPDATE agent.l2_calls SET ...`
   → **permission denied**; `DELETE` → **permission denied**; `INSERT` → allowed. **No role
   (including `trading_admin`) has a column-level UPDATE grant** on the ledger — `consequential_at_creation`
   is set only at INSERT, never UPDATEd, so there is deliberately **no** `UPDATE agent.l2_calls SET
   consequential... = ...` path to test (its absence is the design; do **not** add one).
4. **append-only grant verification — MARKS**: as `trading_ai`, `INSERT INTO
   agent.l2_consequential_marks (...)` → **allowed**; `UPDATE agent.l2_consequential_marks SET ...`
   → **permission denied**; `DELETE` → **permission denied**. A correction = a new compensating
   INSERT row (§A.4.2), never an UPDATE.
5. **compression-readiness sanity (informational, not a P1 step)**: because neither V134 table
   carries a column-level UPDATE grant, a future `ALTER TABLE ... SET (timescaledb.compress)` would
   **not** hit the V114 twin-abort. **P1 itself enables NO compression** (§A.4.1/§A.4.4) — this step
   only documents that the door is left open cleanly.

**V135 — gate-seam `learning.l2_gate_seam_log`:**
6. **V135 first + second apply** → same idempotency; pure append-only REVOKE, **zero column-level
   UPDATE grant**; `trading_ai` = INSERT/SELECT only (UPDATE/DELETE denied). `verdict` CHECK enum
   present.

**V136 — upstream provenance additive ALTERs (§C):**
7. **V136 ALTERs double-apply**: `ADD COLUMN IF NOT EXISTS source_l2_reply_id TEXT NULL` on
   `learning.hypotheses`, `replay.experiments`, `trading.fills` → first apply adds the column,
   second apply no-ops cleanly. **`trading.fills` is a columnstore hypertable** (`V101:49-53`) →
   the ADD COLUMN **must be `nullable`, NO `DEFAULT`, NO `SET NOT NULL`**; confirm it does **not**
   raise `feature_not_supported` (the V077/V101 `:170-181` trap). A `SET NOT NULL` or `DEFAULT` on
   a columnstore would — E1 must use neither. V136's rollback/blast radius is isolated from V134/V135
   (operator-LOCKED split rationale, §E).

**All migrations:**
8. **Guard A/B re-apply no false-RAISE**: re-running V134/V135/V136 against the already-migrated DB
   must produce only NOTICEs, never an EXCEPTION (the V133/V101 idempotency contract).
9. **Linux read-only confirmations** (the items Mac SQL cannot prove — §F escalations; these gate
   **V136 finalization**, which is exactly why V136 is split from V134): (a) does a physical
   strategy-variant table exist? (grep said no; confirm on the live DB schema — if confirmed absent,
   that provenance hop stays deferred-by-absence and adds nothing to V136); (b) the Stage-1 demo
   manifest jsonb key path for `source_l2_reply_id` (jsonb key, no DDL); (c) **`trading.decision_outcomes`
   columnstore/hypertable status** — `V075:8` documents it as a **plain table** ("2 plain tables:
   learning.decision_features, **trading.decision_outcomes**"), which would mean a plain
   `ADD COLUMN` (no columnstore-safe form needed); but because that is a migration-text assertion and
   a later migration could have converted it, **E1 confirms on the live `timescaledb_information.hypertables`
   before choosing the ALTER form** for any `decision_outcomes` provenance column. (Note: `decision_outcomes`
   provenance is **part of the deferred R2-5 live hop** per §C, so it is **not** in P1's V136 unless
   operator scope reopens it — this confirmation is forward-prep, not a P1 blocker.)

---

## I. Side-effect / hard-boundary checklist (PA discipline)

1. **Other modules importing the changed surface?** P1 adds new tables (`agent.l2_calls`,
   `agent.l2_consequential_marks`, `learning.l2_gate_seam_log`) + a new writer + additive provenance
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
- All three P1 tables pure append-only (REVOKE UPDATE/DELETE, **zero column-level UPDATE grant**);
  sanitize on write path; secrets never verbatim; writer INSERT-only everywhere. ✔
- New singleton registered before merge. ✔
- Rust-first N/A (P1 is audit/provenance on the Python control plane + PG, per design §A.1; the
  trading-truth layer stays Rust and is untouched). ✔

---

## J. Verdict

**E1-READY (LOCKED).** This is a design-only pass — no code, no migration apply, no DB write, no
deploy was performed. The three previously-open items are now **operator-RESOLVED** (2026-06-08);
the design below is the locked spec, not a recommendation.

**Previously-open decisions — all RESOLVED (operator 2026-06-08):**
1. **`consequential` → RESOLVED: Option (c) side-table** (`agent.l2_consequential_marks`, append-only,
   built in V134), ledger stays **pure** append-only with an **immutable** `consequential_at_creation`
   boolean (sub-variant i) and **zero column-level UPDATE grant**. Long-term rationale (operator):
   ledger remains freely **TimescaleDB-compressible** later because no column-level UPDATE grant
   exists → the V114 compressed-twin column-grant abort (§A.4 was the trap that drove the rejected
   narrow-column option) **cannot occur**. Consequence is modeled as append-only events (when/why/
   which-lane/by-whom, multi-mark), consistent with `learning.lease_transitions` (`V054:225`). §A.4
   is the locked design; the rejected narrow-column-UPDATE option and its DO-block are removed.
2. **strategy-variant provenance hop → RESOLVED: deferred-by-absence (operator accepted).** No
   physical variant table exists (grep-confirmed; Linux read-only re-confirm §H.9a). The chain is
   forward-compatible; this hop lands when a variant table first exists.
3. **Migration packaging → RESOLVED: provenance ALTERs are their own `V136`** (NOT folded into V134).
   P1 = **V134** (`agent.l2_calls` + `agent.l2_consequential_marks`) · **V135**
   (`learning.l2_gate_seam_log`) · **V136** (§C upstream provenance ALTERs). Rationale (operator):
   ledger is fully designable now → V134 finalizes early/clean; provenance has Linux-verify
   dependencies (`trading.fills` columnstore form, `decision_outcomes`/manifest table-vs-jsonb) →
   isolating V136 keeps V134's rollback/dry-run blast radius clean and lets V134 sign off without
   waiting. V134/V135/V136 confirmed free, no collision with the V128 soft-reservation (§E).

**Three E2-must-scrutinize points (PA flags for the reviewer):**
1. **Composite PK `(l2_reply_id, created_at)`** (ledger) **and `(mark_id, marked_at)`** (marks) — the
   hypertable forces the composite; the design's "text PRIMARY KEY" shorthand is a trap. Verify E1
   used the composite on **both** tables (V035/V064/V114/lease_transitions precedent).
2. **`prompt_sha256`/`response_sha256` computed over SANITIZED text** — if E1 hashes the raw text
   before redaction, the hash won't match the stored row (design `:698-699`). This is a subtle
   ordering bug; E2 must confirm hash-after-sanitize.
3. **Zero column-level UPDATE grant on every P1 table** — under the LOCKED Option (c) this is the
   load-bearing invariant (it is what keeps all three tables compressible and the writer purely
   INSERT-only). E2 must grep V134/V135/V136 for any `GRANT UPDATE (...)` → **must be zero hits**;
   and confirm `trading_ai` gets INSERT/SELECT only on all three. (Plus the V136 columnstore-safe
   `ADD COLUMN` on `trading.fills`: nullable, no DEFAULT, no SET NOT NULL — V077/V101 trap — confirmed
   on the live Linux DB, not just the Mac mock.)

Report path: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-d3-phase1-tech-design.md`
