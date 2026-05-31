# AI-E VERIFY — Daily-cap fail-open / unmetered paid L2 (Claude) call

Date: 2026-05-30 (PG runtime read 2026-05-31) · Role: AI-E (default), rule-10 verification · READ-ONLY (no edit except this report)
Source deep-dive: `docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-30--AI-E--deepdive_ai_truthfulness.md`
Repo root: `/Users/ncyu/Projects/TradeBot/srv` · HEAD `3f805a61`

> METHOD CORRECTION (this is why the deep-dive fabricated 4 items): it cited `openclaw_engine/src/ai/{budget,claude_teacher,usage_store}.rs` — **those paths do not exist.** Real code: `rust/openclaw_engine/src/claude_teacher/` (mod 301L, client 287L, consumer_loop 665L) + `rust/openclaw_engine/src/ai_budget/` (tracker 913L, usage_io 118L). Tables also exist (deep-dive wrongly said absent). Every claim below = a file I read at the cited line, or a live PG result behind a passing `SELECT 1` control (the `-t -A` SSH path silently returned empty rows — caught via control + switched to default-format queries; the exact tool flakiness warned about).

## VERDICT: **P2 (bounded — not reachable as deployed). Confidence: HIGH.** One real pre-enablement design gap (see Item 1b).

The paid Claude L2 path is the `ClaudeTeacher` "teacher consumer loop". As shipped it is **default-OFF** AND **fail-closed on a missing API key**, so no unmetered paid call can fire. The deep-dive's two candidates are both effectively REJECTED for the production path, but I am NOT rating REJECT overall because the budget gate on the teacher path is **post-call accounting, not a pre-call cumulative-cap DENY** — a genuine gap that must be closed before paid-AI is switched on.

## Item 1 — PRE-CALL cumulative-cap gate on the paid path

(a) The mechanism EXISTS: `ai_budget/tracker.rs:120` `DegradeLevel::from_usage(used, limit)` returns `Killswitch` at ratio ≥ 1.0 (and `from_usage` is fail-closed: limit ≤ 0 ⇒ Killswitch, `:123`). `degrade_level()` (`:422`) feeds it MTD spend; `BudgetTracker::new` seeds MTD from PG via `load_mtd_usage` (`:215`).

(b) **GAP (the kernel of truth in the P1-candidate):** the `ClaudeTeacher` paid call path does **NOT consult `degrade_level()`/`from_usage` before calling**. `mod.rs:142` `fetch_parse_persist` order is: (1) `client.call_with_messages` — the paid HTTP call FIRST (`:144-148`); (2) THEN `budget.record_usage` (`:159`) which only *charges/records* and fails closed on DB-write/unknown-model error — it does NOT check whether the cumulative cap is already exceeded. So the daily/MTD cap is enforced as a **ledger + per-call fail-closed on write**, not as a pre-call "you're over $X, deny" gate. `DegradeLevel` is consumed only by IPC status (`status_json:469`), not by the teacher loop. → For the teacher, a paid call is made first and accounted after; the cap cannot pre-empt call #N once usage is already at the ceiling. **This is the real finding.** Confidence HIGH (read the full method).

## Item 2 — no-BudgetTracker branch fail-OPEN? (deep-dive FACT/P2) → REJECTED for production

`ClaudeTeacher.budget: Option<...>`; the `None` arm at `mod.rs:188-190` does `warn!("…proceeding without cost accounting")` and proceeds — permissive **as written**. BUT production wiring never hits it: `tasks.rs:259-263` returns early if the BudgetTracker slot is empty, and `tasks.rs:273-278` constructs the teacher with `Some(Arc::clone(&budget))`. The only `None` constructions are unit tests. So the fail-open arm is **unreachable in the shipped binary** → bounded, not a live exposure.

## Item 3 — is $2/day enforced at runtime? + Linux PG evidence

Two enablement locks make paid calls impossible right now:
1. **Default-OFF:** `tasks.rs:290` `AtomicBool::new(false)`; `consumer_loop.rs:235` skips the whole cycle when disabled. Comment + log: "DEFAULT-OFF until E3 R6 PASS; operator flips via IPC" (`tasks.rs:311`). No `enabled:true` override anywhere.
2. **Fail-closed key:** the real `AnthropicClient` (`client.rs:124-128,137`) returns `MissingApiKey` and makes NO HTTP call unless `ANTHROPIC_API_KEY` is non-empty.

Cap config: the cap is the **$100/$150 monthly** ladder (SoftWarn $80 / HardLimit $95 / Killswitch $100 on `local_total`; per-agent teacher $60) — `tracker.rs:83-90, 104-111`. The DOC-08 "$2/day" daily figure is **not** what this code enforces; there is no per-day Rust gate (the only daily-USD symbol, Python `total_spent_today_usd`, lives in `bybit_thought_gate/bybit_query_budget_gate.py`, a separate query gate — confirms the deep-dive's "no populator for the daily cap" note).

Live PG (`docker exec trading_postgres psql -U trading_admin -d trading_ai`, `SELECT 1`=1 control PASSED):
- `agent.ai_invocations` total=**2**, today=**0**; `learning.ai_usage_log` (the cap's actual source table) total=**0**; `public.ai_cost_events`(view) total=**2**.
- `agent.ai_invocations`: nonzero-cost rows = **0**, `max(cost_usd)` = **0**. (Schema is `model`, not `model_id`; cost col = `cost_usd numeric(10,6)`.)
- ⇒ **Today cost $0, MTD cost $0 in `ai_usage_log` (0 rows). Cap-ever-blocked: NO** — no paid Claude row has ever been written; the teacher loop has never run a billable cycle.

## Rule-10 basis
FACT: gate-as-post-call-ledger (`mod.rs:142-190` read in full); default-off (`tasks.rs:290`); key-fail-closed (`client.rs:124-137`); no-tracker arm unreachable in prod (`tasks.rs:259-278`); PG = 0 paid rows / $0 (live, control-verified). INFERENCE (flagged): if paid L2 were enabled, the absence of a pre-call `from_usage` DENY on the teacher path means the cap can only stop call N+1 via record_usage write-failure, not refuse call N when already over — i.e. it can overshoot by up to the in-flight call. Not a current exposure (cost is $0, loop off, no key).

## Recommended fix direction (owner: MIT lead; support E1 Rust) — pre-condition to ANY paid-AI enablement
1. **Add a pre-call gate** in `ClaudeTeacher::fetch_parse_persist`: call `budget.degrade_level()` (or a scoped check) BEFORE `client.call_with_messages`; on `Killswitch` (and `HardLimit` for non-P0) return `Err(Budget(...))` without calling the LLM. This converts post-hoc accounting into a true cumulative-cap DENY.
2. **Fail-closed no-tracker arm:** make `mod.rs:188` `None` ⇒ `Err`, not proceed (defense-in-depth even though prod passes `Some`).
3. **Daily cap:** if DOC-08 "$2/day" is intended, add a per-day scope/threshold to `DegradeLevel`/config (today only monthly exists) and seed today's spend from PG, so a mid-day restart can't zero a daily counter.
4. Keep default-OFF + key-fail-closed; on enablement, add an audit line when a call is refused for cap/key.
