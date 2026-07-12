# Reconcile Path B — Real Two-Sided paper↔demo Reconciliation (DESIGN)

> PA-design-writer, 2026-07-12. Read-only investigation + design. **No implementation, no
> runtime, no broker contact in this task.** Operator decided **Path B (BUILD)**, not remove.
> Home decision: **this dedicated doc**, not `design/08 §5`. §5 (`08_smoke_tests.md`) is the
> smoke-ratchet record of the M1 drift and only owns the allowlist line (§8 below); the build
> design is a governance-backend architecture change larger than the smoke-test doc scope.
> §5's M1 disposition should back-link here.

Evidence class: `implementation_contract` (source-verified, file:line pinned). Runtime
semantics (does the paper engine submit to the same api-demo account?) are
`EXTERNAL_VERIFICATION_PENDING` — see **UNKNOWN-1**, the dominant risk.

All paths below are under
`srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/` unless noted.

---

## 0 · TL;DR

- **Chosen architecture: server-side assembly (Option A).** The `/reconcile` route builds
  BOTH `paper_state` and `demo_state` from server-authoritative sources; the GUI only sends
  `{reason}`. This structurally deletes L1 (dead client route), L2 (client shape), L3 (client
  self-compare), and removes a client-forgeable governance input that feeds risk escalation.
- **Two reusable providers** (`build_paper_reconcile_snapshot()`, `build_demo_reconcile_snapshot()`)
  in a new small module. Same two callables a future `ScheduledReconciler` wants
  (`paper_state_fn`, `remote_state_fn`) — Second-Adapter satisfied.
- **L4 fix = one `map_report_to_escalation(report_dict)` in `reconciliation_engine.py`**, used by
  BOTH callers. It inspects `discrepancies[].severity` (not just `overall_result`) so it can tell
  FATAL (freeze) from CRITICAL (risk-escalate) — which `overall_result` alone cannot, because
  `_determine_overall_result` collapses both to `MISMATCH_MAJOR`.
- **Fail-closed:** demo unreachable / creds absent / httpx raise ⇒ route returns `STALE_DATA`
  **before** `engine.reconcile` is ever called ⇒ escalation path not entered ⇒ **freeze
  impossible on demo-unreachable**. Never substitute an empty `{}` demo snapshot.
- **CC decision (UNKNOWN-1):** paper-engine positions may not be the same account as api-demo. If
  they are not, a real compare produces FATAL `POSITION_MISSING` on every position ⇒ freeze.
  Recommend landing the button as **advisory-first**: mapping correct, but the FATAL→auth-freeze
  cascade gated OFF for the manual path until account-identity is confirmed and a steady-state
  MATCH is observed.

---

## 1 · Paper-side snapshot source (the gap BB did not cover) — FINDINGS

There is **no `paper_engine.export_state()`** in Python. The `ScheduledReconciler` docstring
(`reconciliation_engine.py:883-885`) references one, but it is never wired; the paper engine is
the **Rust** engine, read over IPC.

Authoritative accessor: `get_rust_reader()` → `RustSnapshotReader` (`ipc_state_reader.py:346`,
module singleton `_READER` at `:342`). Per-engine snapshot files
`pipeline_snapshot_{paper|demo|live}.json`. Paper-tab routes read `engine="paper"` explicitly
(3E-ARCH; otherwise the compat file is whichever engine is `is_primary`,
`paper_trading_routes.py:685-688`).

Exact functions and shapes:

| Contract key | Paper source (function) | Returned shape | Gap → transform needed |
|---|---|---|---|
| `positions` (DICT) | `get_paper_state(engine="paper")["positions"]` (`ipc_state_reader.py:202-222`) | **LIST** of `{symbol, is_long:bool, size\|qty, entry_price\|avg_entry_price, unrealized_pnl, entry_fee}` (`paper_trading_routes.py:709`, `:832-839`, `:289`, `:468`) | **SHAPE GAP.** List→Dict keyed by symbol; `side="Buy" if is_long else "Sell"`; `size=float(p.get("size") or p.get("qty") or 0)`; `avg_entry_price=p.get("entry_price", p.get("avg_entry_price",0))`; `category` inferred (`inverse` if symbol endswith `USD` & not `USDT`, else `linear`, mirror `demo_snapshot_payloads.py:240-242`); drop `size==0`. |
| `balances` (DICT) | `get_paper_state(engine="paper")["balance"]` (`paper_trading_routes.py:711`) | **scalar** float (USDT-denominated single balance) | **SHAPE GAP.** Wrap `{"USDT": float(balance)}`. |
| `fills` (LIST) | `get_recent_fills(mode="paper")` (`ipc_state_reader.py:313-323`) | LIST of `{symbol, is_long\|side, qty, price, fee, realized_pnl}` (`paper_trading_routes.py:990-993`) | side backfill `"Buy" if is_long else "Sell"` when absent (as `:992-993`). Pass through; engine keys on `execTime`/`execId` tolerantly (`reconciliation_engine.py:598-660`). |
| `orders` (LIST) | `get_recent_intents(mode="paper")` (`ipc_state_reader.py:301-311`) OR `[]` | LIST of order **intents** (not live open orders) | **SEMANTIC GAP (UNKNOWN-2).** Intents are not exchange open orders and lack matching `orderId`. Recommend `orders=[]` on the paper side for v1 (order reconcile off) to avoid false `ORDER_MISSING` (WARNING-only, not freeze, but noisy). Revisit if the paper engine exposes true open orders. |
| `snapshot_ts_ms` (int) | `int(time.time()*1000)` at read time | — | No in-payload snapshot timestamp field exists; freshness is enforced upstream by `is_engine_available` (file-mtime < staleness threshold, `ipc_state_reader.py:148-157`). Stamping `now` is acceptable and keeps the engine `max_data_age_ms` freshness check (`:745-775`) from firing a false stale on a known-fresh read. |

Availability gate: `is_engine_available("paper")` (`ipc_state_reader.py:148`). If false ⇒ paper
snapshot is `None` ⇒ **fail-closed** (route returns `STALE_DATA`, no compare). There is **no**
existing paper assembler that emits the engine contract (BB found the demo one; the paper one
does not exist and must be written).

---

## 2 · Architecture decision — server-side assembly (Option A, RECOMMENDED)

**Observable outcome / invariants.** Pressing "Reconcile" runs a real compare of the local paper
engine mirror against the api-demo exchange state and shows the discrepancy report; a healthy
state does not escalate; a demo outage never freezes; the client cannot forge the governance
inputs that feed risk escalation (Root Principle 2 read/write separation, CLAUDE §七 "GUI write
surfaces write through authority, not client fake paths").

### Option A — server assembles (RECOMMENDED)

Route builds both snapshots from authoritative server sources; GUI sends only `{reason}`.

- **Deletion test:** delete the client-side `paperState` assembly (`governance.js:89-110`) — nothing
  coherent is lost; it is currently dead (404→`{}`) and its output is ignored the moment the
  server assembles. L1/L2/L3 disappear by construction.
- **Second-Adapter test:** the two providers are exactly `paper_state_fn` / `remote_state_fn` that
  `ScheduledReconciler.__init__` (`reconciliation_engine.py:893-903`) already expects. A future
  scheduled reconciler attaches through the same Interface with zero policy copy.
- **Authority/trust test:** governance reconcile inputs become server-authoritative. Client can no
  longer POST a crafted `paper_state`/`demo_state` into a risk-escalation-feeding path. Strict
  improvement.
- **Locality:** contract knowledge (engine `{orders,positions:dict,fills,ts,balances:dict}`) lives
  once, in Python, next to the engine that consumes it — not duplicated in JS.

### Option B — GUI assembles (REJECTED)

GUI repoints to a real paper route, calls a new demo endpoint, reshapes client-side, posts the
full payload. Rejected: keeps trusting a client-constructed governance payload; duplicates the
engine contract in JS; cannot be reused by `ScheduledReconciler`; re-exposes L2/L3 to client bugs;
violates CLAUDE §七. The only thing it saves is one server module — not worth the trust regression.

### Function signatures & placement (route stays parse→call→format; logic below)

New module `governance_reconcile_snapshots.py` (~90 lines, well under limits; keeps the three
>800-line files from growing):

```python
class DemoSnapshotUnavailable(Exception):
    """demo 端不可信(憑證缺/槽位缺/httpx raise/retCode≠0)。呼叫端必須 fail-closed。"""

def build_paper_reconcile_snapshot() -> dict | None:
    # 讀 Rust paper 引擎 IPC → 引擎對賬契約。引擎不可用回 None(fail-closed,不偽造空快照)。
    ...

def build_demo_reconcile_snapshot() -> dict:
    # 讀 httpx BybitClient(env=demo, api-demo, 只讀)→ 引擎對賬契約。
    # 任一原語 raise / retCode≠0 / 憑證缺 → raise DemoSnapshotUnavailable。絕不回 {}。
    ...
```

Demo provider uses the read-only singleton `_get_rust_client()` (`strategy_ai_routes.py:142-161`,
default `BybitClient(environment="demo")` → `https://api-demo.bybit.com`,
`bybit_rest_client.py:110-115,294-298`). BB-confirmed pure-GET primitives, `_full_scan`
(cursor, fail-closed, 50-page cap) variants for baseline:
`get_positions_full_scan("linear")` (`:718`), `get_active_orders_full_scan("linear",settle_coin="USDT")`
(`:779`), `get_executions("linear",limit)` (`:961`), `refresh_balance()["coins"]` (`:573`).
Mapping per BB verdict (positions→dict, drop `size==0`; balances→`{coin:wallet_balance}`;
`snapshot_ts_ms=int(time*1000)`). ~4 GETs/press, 50 req/s ceiling → no throttle risk.

---

## 3 · GUI change to `govPostReconcile` (Vanilla JS)

Replace `governance.js:84-113` in full; delete the entire dead `paperState` fetch/assembly block:

```javascript
async function govPostReconcile(reason) {
  // POST /api/v1/governance/reconcile —— 伺服器端組裝 paper/demo 快照,GUI 僅觸發。
  // 不再由前端拉 /paper/status 或建構 governance payload(移除 L1 dead-route / L2 shape /
  // L3 self-compare 全部失效面)。回應含 verdict/severity/is_consistent/discrepancies。
  return ocPost('/api/v1/governance/reconcile', { reason: reason || 'manual_trigger' });
}
```

Badge rendering (caller of `govPostReconcile`) consumes the new response fields (§5). GUI must
`node --check` before sign-off (CLAUDE Data/Migrations rules).

---

## 4 · L4 result→severity mapping fix (single source of truth)

### Verified enum facts
- `ReconciliationResult` = `MATCH, MISMATCH_MINOR, MISMATCH_MAJOR, MISSING_LOCAL, MISSING_REMOTE,
  STALE_DATA, ERROR` (`reconciliation_engine.py:47-56`).
- `Severity` = `INFO, WARNING, CRITICAL, FATAL` (`:72-77`).
- `_determine_overall_result` (`:781-798`): FATAL→`MISMATCH_MAJOR`, CRITICAL→`MISMATCH_MAJOR`,
  WARNING→`MISMATCH_MINOR`, else→`MISMATCH_MINOR`. **`overall_result` never yields CRITICAL /
  FATAL / STALE_DATA / MISSING_*.** ERROR only via internal exception (`:328`).
- `to_dict()` carries `overall_result` (str), `is_consistent`, `discrepancies[]` (each with
  `severity` str), `critical_count` (= count of CRITICAL+FATAL, `:176-180`). **No `fatal_count`,
  no `result`, no `severity` key.**
- FATAL severity is assigned by **position** discrepancies: `POSITION_MISSING` (`:502-503`,
  `:529-530`), `POSITION_SIZE` big (`:550-551`), `POSITION_SIDE` (`:568-569`) — all recommend
  `FREEZE_TRADING`. This is why an empty demo snapshot ⇒ fabricated FATAL ⇒ freeze.

### The three confirmed defects (all currently disarm escalation)
- **(a) manual path** `governance_hub.py:1472-1475`: passes literal `"CRITICAL"` to
  `_on_reconciliation_mismatch`, whose only branches are `MISMATCH_MINOR` / `MISMATCH_MAJOR` /
  `FATAL` (`governance_hub_cascades.py:478-519`). `"CRITICAL"` matches nothing.
- **(b) auto path — severity** `governance_hub_event_handlers.py:117,123`: reads
  `overall_result.upper()` then checks `in ["CRITICAL","FATAL"]`; real values are
  `MISMATCH_MAJOR`/`MISMATCH_MINOR` → never in set.
- **(b′) auto path — action name** `governance_hub_event_handlers.py:120`: filters
  `action in ["reconciliation_mismatch","reconciliation_failure"]`, but the engine emits
  `IncidentAction` values `"FREEZE_TRADING"/"MANUAL_REVIEW"/"ALERT"` (`reconciliation_engine.py:80-86`,
  `:824-834`). The filter never matches — the callback body is dead even before the severity check.

### Single mapping (new, in `reconciliation_engine.py`, the enum SoT)

```python
def map_report_to_escalation(report_dict: dict) -> str | None:
    """對賬報告 → _on_reconciliation_mismatch 可辨識的升級 token(唯一映射,手動+自動共用)。
      "FATAL"          → 熔斷 + 凍結授權(僅當存在 FATAL 差異)
      "MISMATCH_MAJOR" → 升級風控 REDUCED/DEFENSIVE(存在 CRITICAL 差異,或 overall=MISMATCH_MAJOR)
      "MISMATCH_MINOR" → 僅記錄(WARNING 級)
      None             → MATCH,不升級
    關鍵:必須看 discrepancies[].severity,因 overall_result 把 FATAL 與 CRITICAL 都塌成
    MISMATCH_MAJOR,單看 overall 無法分辨「凍結」與「降風控」。STALE_DATA/ERROR 由呼叫端
    fail-closed 短路,不進本函數。"""
    overall = str(report_dict.get("overall_result", "MATCH")).upper()
    if overall == "MATCH":
        return None
    disc_sev = {str(d.get("severity", "")).upper() for d in report_dict.get("discrepancies", [])}
    if "FATAL" in disc_sev:
        return "FATAL"
    if overall == "MISMATCH_MAJOR" or "CRITICAL" in disc_sev:
        return "MISMATCH_MAJOR"
    return "MISMATCH_MINOR"
```

### Wiring — ONE escalation entry point
- **Canonical path = engine incident_callback** (already wired at `governance_hub.py:433,442`).
  Rewrite the callback body (`governance_hub_event_handlers.py:115-135`): drop the broken action
  filter and the `["CRITICAL","FATAL"]` check; call `esc = map_report_to_escalation(report)` and,
  if not None, `self._on_reconciliation_mismatch(esc, report)`. **Dedup by `report_id`** (the
  callback fires once per action FREEZE/MANUAL_REVIEW/ALERT) so a report escalates at most once.
- **Manual path:** **remove** the redundant direct escalation `governance_hub.py:1472-1475`. The
  engine's `_execute_actions` already fires the (now-correct) incident_callback during
  `engine.reconcile()`. This unifies manual-now and scheduled-future through one code path.
- Also fix the self-compare (§6) and the response shape (§5, item R3) in `hub.reconcile`.

### RE-ARM WARNING — flag every fail-open/closed for CC
This change **re-arms** a real risk-escalate→auth-freeze cascade (`_on_reconciliation_mismatch`
FATAL branch: `RiskLevel.CIRCUIT_BREAKER` + collect auth ids + `self._mode = GovernanceMode.FROZEN`,
`governance_hub_cascades.py:499-519`). Fail-open/closed decisions for CC:
- **[CC-1] Arm freeze on the manual button? RECOMMEND NO until UNKNOWN-1 resolved.** If
  paper≠api-demo account, a correct compare yields FATAL `POSITION_MISSING` on every position →
  freeze live auth on a meaningless mismatch (foot-gun / weaponizable: a demo drift freezes live).
  Recommended default for v1: construct the manual-path engine with
  `ReconciliationConfig(auto_freeze_on_critical=False)` and **cap the emitted token at
  `MISMATCH_MAJOR`** (advisory risk-escalate, no auth freeze, emit a governance event noting the
  cap) until (i) operator confirms the paper engine submits to the same api-demo account and
  (ii) a shadow/scheduled run shows steady-state MATCH. A future scheduled reconciler on a
  confirmed account arms freeze. CC owns the gating mechanism.
- **[CC-2] Does CRITICAL freeze or only escalate?** Engine `_determine_actions` treats
  `critical_count>0 ∧ auto_freeze_on_critical` as FREEZE (`:813-814`), but the handler only
  freezes on the `FATAL` token. The mapping above sends CRITICAL→`MISMATCH_MAJOR` (escalate, no
  freeze) — the conservative reading. Confirm this is the intended semantics.

---

## 5 · Fail-closed contract (end-to-end)

Route logic (`trigger_manual_reconciliation`, `governance_routes.py:1096-1148`), server-side:

```
1. paper = build_paper_reconcile_snapshot()
   if paper is None:                      # 引擎不可用
       return verdict=STALE_DATA, reason="paper_engine_unavailable"   # 不 compare / 不 escalate
2. try:
       demo = build_demo_reconcile_snapshot()
   except DemoSnapshotUnavailable as e:   # 憑證缺 / 槽位缺 / httpx raise / retCode≠0
       return verdict=STALE_DATA, reason="demo_unreachable"           # 不 compare / 不 escalate / 不 freeze
   #   ★ 絕不以空 {} 代替 demo — 空 demo 會偽造 FATAL POSITION_MISSING → 誤凍結。
3. report = hub.reconcile(paper_state=paper, demo_state=demo)         # 真雙向
4. format → GUI
```

| Failure | Result | Escalate? | Freeze? |
|---|---|---|---|
| paper engine unavailable | route `verdict=STALE_DATA` (no engine call) | no | no |
| demo fetch raises / retCode≠0 | `DemoSnapshotUnavailable` → route `verdict=STALE_DATA` | no | no |
| demo creds absent / slot missing | provider raises `DemoSnapshotUnavailable` → `STALE_DATA` | no | no |
| engine internal exception | `overall_result=ERROR`, `_execute_actions` **not reached** (inside try, `:321-324`) → no callback | no | no |
| freshness stale (in-engine) | WARNING disc → `MISMATCH_MINOR` | log only | no |

**Confirmed: demo-unreachable can never freeze** — the route returns `STALE_DATA` before
`engine.reconcile` is called, so the escalation path is not entered.

**STALE_DATA/ERROR surfacing (engine → hub → route → GUI):**
- engine: `overall_result` = `ERROR` on internal exception; freshness → `MISMATCH_MINOR`.
- hub: returns `report_dict`, or `{ok:false, reason}` on disabled/error (`:1452-1489`).
- route: adds an explicit top-level `verdict` — `STALE_DATA` when a snapshot could not be built
  (route short-circuit), else the engine `overall_result`. **Response-shape fix R3:** the route
  currently reads `report.get("result")` / `report.get("severity")` (`governance_routes.py:1136-1138`)
  which **do not exist** in `report_dict` (keys are `overall_result` / `is_consistent` /
  `discrepancies` / `critical_count`). Return `verdict=overall_result`,
  `severity=map_report_to_escalation(report_dict)`, `is_consistent`, `discrepancies`.
- GUI badge states: `MATCH`(green) · `MISMATCH_MINOR`(amber) · `MISMATCH_MAJOR`(orange) ·
  `FATAL`(red + frozen) · `STALE_DATA`(grey "資料不足未對賬") · `ERROR`(grey/red).

---

## 6 · Remove the `demo_state or paper_state` self-compare

`governance_hub.py:1466`: `remote_state=demo_state or paper_state` → change to
`remote_state=demo_state`. Under server-side assembly the route always supplies a real `demo`
snapshot or short-circuits to `STALE_DATA` before calling `hub.reconcile`, so `demo_state` is
never falsy on the real path. Defensive behavior when `demo_state` is legitimately `None`
(e.g. a stray caller): `hub.reconcile` returns `{ok:false, reason:"demo_state_required"}` — do
**not** self-compare, do **not** fabricate an empty demo. This removes the trivial-MATCH
degeneracy (L3).

**Request-model hardening:** remove `paper_state` / `demo_state` from `ManualReconciliationRequest`
(`governance_routes.py:305-309`; `paper_state` is currently `Field(...)` required). Keep only
`reason`. The GUI button is the only live caller (`:1122`), so this is safe and closes a
client-forgeable governance-input surface (trust-boundary improvement).

---

## 7 · Touch-list (file:function:line anchor) + test surface

| # | File | Function / anchor | Change |
|---|---|---|---|
| 1 | `governance_reconcile_snapshots.py` **(NEW)** | `build_paper_reconcile_snapshot`, `build_demo_reconcile_snapshot`, `DemoSnapshotUnavailable` | New providers (§2). Chinese comments. |
| 2 | `reconciliation_engine.py` | new module fn near `_determine_overall_result` (`:781`) | Add `map_report_to_escalation` (§4). SoT. |
| 3 | `governance_hub_event_handlers.py` | `_make_incident_callback` `:115-135` | Drop broken action filter + `["CRITICAL","FATAL"]`; call mapping; dedup by `report_id`. |
| 4 | `governance_hub.py` | `reconcile` `:1462-1479` | `remote_state=demo_state` (`:1466`); **remove** direct escalation `:1472-1475`; keep return `report_dict`. |
| 5 | `governance_routes.py` | `ManualReconciliationRequest` `:305-309`; `trigger_manual_reconciliation` `:1096-1148` | Model→`{reason}` only; route builds paper+demo server-side with fail-closed short-circuits; fix response `verdict/severity` (R3). Optional `ReconciliationConfig(auto_freeze_on_critical=False)` per **CC-1**. |
| 6 | `static/governance.js` | `govPostReconcile` `:84-113` + badge caller | Trigger-only body (§3); consume `verdict/severity/discrepancies`. `node --check`. |
| 7 | `tests/structure/test_gui_smoke_fetch_route_alignment_static.py` | `KNOWN_MISMATCH_ALLOWLIST` `:575-580` | Remove M1 line (§8). |

Files >800 lines touched (review attention, all < 2000 cap): `governance_routes.py` (1366),
`governance_hub.py` (1499 — nearest cap; keep the edit minimal/subtractive), `reconciliation_engine.py`
(948). New logic goes in the NEW module to avoid growing them.

**Test surface (E4 hard edge):**
- **Shape correctness (Mac-runnable unit):** `build_paper_reconcile_snapshot` on a fixture Rust
  paper_state (list positions + scalar balance) emits `positions:dict`, `balances:dict`,
  `orders:list`, `fills:list`, `snapshot_ts_ms:int`; `size==0` dropped; `side`/`category` correct.
- **Fail-closed / no-false-freeze (critical):** demo provider raises `DemoSnapshotUnavailable` on
  httpx raise / retCode≠0 / missing creds; route returns `STALE_DATA` and **never** calls
  `engine.reconcile`; assert `_on_reconciliation_mismatch` **not** invoked (no freeze) when demo
  unreachable. Assert an empty `{}` demo is never passed to the engine.
- **Escalation mapping correctness:** table test of `map_report_to_escalation` over every enum
  combo — MATCH→None; WARNING-only→MISMATCH_MINOR; CRITICAL disc→MISMATCH_MAJOR; FATAL disc→FATAL;
  ERROR handled by short-circuit. Assert manual and auto callers produce identical tokens for the
  same report. Assert `report_id` dedup (single escalation across 3 actions).
- **Healthy-state → no escalate:** MATCH report ⇒ `_on_reconciliation_mismatch` not called, mode
  stays non-FROZEN.
- **Ratchet green:** `test_gui_smoke_fetch_route_alignment_static.py` passes with the M1 line
  removed (GUI no longer calls `/paper/status`).
- **NEEDS-LINUX-RUNTIME (not Mac-attestable):** real api-demo round-trip, real Rust IPC snapshot,
  real freeze cascade, real GUI badge render. Must be labeled runtime-pending, not source-closed.
- GUI: `node --check governance.js`.

---

## 8 · M1 KNOWN_MISMATCH_ALLOWLIST removal + ratchet re-tighten

Remove `("GET", "/api/v1/paper/status")` at
`tests/structure/test_gui_smoke_fetch_route_alignment_static.py:580` (plus its comment `:576-579`).
Under server-side assembly the GUI no longer calls `/paper/status`, so the drift is gone at the
source. `ACCEPTED = AUTHORITATIVE_ROUTES | DYNAMIC_DEBT_ALLOWLIST | KNOWN_MISMATCH_ALLOWLIST`
(`:587`) shrinks by one entry; the ratchet re-tightens automatically — any future GUI call to a
non-existent route fails the main alignment test (`:635-647`) instead of being silently
allowlisted. Back-link `design/08 §5`'s M1 disposition (`08_smoke_tests.md:97`) to this doc and
mark M1 resolved-on-merge.

---

## 9 · UNKNOWNS / risks needing operator or CC decision

- **UNKNOWN-1 (DOMINANT, operator+CC).** Is the Rust **paper** engine's position/balance state
  the same account as **api-demo**? `bybit_demo_sync.py:271-275` (old T7.04 design) says paper
  non-spot positions ARE submitted to Demo — but 3E-ARCH split into separate paper/demo/live
  engines and there is now a distinct Rust **"demo"** engine (`is_engine_available("demo")`,
  `bybit_sync_balance`, `paper_trading_routes.py:764-773`). If "paper" is a pure local sim that
  does **not** submit to api-demo, then a real compare produces FATAL `POSITION_MISSING` on every
  position → freeze. **Two options for the operator:** (A) confirm paper submits to api-demo, then
  paper↔api-demo is the right pair; or (B) the meaningful pair is **demo-engine-local
  (`get_paper_state(engine="demo")`) vs api-demo-exchange**, in which case side A should read
  `engine="demo"`, not `engine="paper"`. The provider signature should make the engine explicit so
  this can flip without a rewrite. This is `EXTERNAL_VERIFICATION_PENDING` and cannot be settled
  from source; recommend advisory-first arming (CC-1) until a shadow run shows steady-state MATCH.
- **UNKNOWN-2 (E1/E4).** Paper `orders` source. `recent_intents` are intents, not exchange open
  orders, and lack matching `orderId` → false `ORDER_MISSING` (WARNING, not freeze, but noisy).
  Recommend `orders=[]` on the paper side for v1; revisit if the paper engine exposes true open
  orders. Confirm the demo side likewise starts with orders reconcile scoped or off to avoid
  one-sided `ORDER_MISSING`.
- **CC-1 / CC-2:** freeze arming and CRITICAL-vs-FATAL semantics (§4). CC-owned.
- **Env/slot (BB, confirmed):** `demo`→`https://api-demo.bybit.com` with `demo` slot;
  `live_demo`→api-demo with `live` slot (slot-file only, env fallback disabled). Requires a
  read-scope key. NEVER mainnet (`OPENCLAW_ALLOW_MAINNET` gate intact,
  `bybit_rest_client.py:331-341`). The default singleton is `environment="demo"` (`:298`).
- **Guardian / Decision-Lease / Cost-Gate untouched.** Reconcile is governance/read; Python
  control-plane is the correct home (not Rust). No mainnet, read-only demo.

---

## 10 · Independent verification path

Writer = admitted source writer (Python control-plane + Vanilla JS). Independent E2 then E4 hard
edges. QC/CC review the escalation re-arm (CC-1/CC-2) and the trust-boundary change (§6).
Runtime attestation (api-demo round-trip, IPC read, freeze cascade, GUI badge) is Linux-only and
must be captured out-of-band before any "works" closure — Mac static tests prove
`implementation_contract`/source only.

---

# v2 — Reach a clean, armable steady-state MATCH (demo engine ↔ api-demo)

> PA-design-writer, 2026-07-12. Read-only investigation + design. **No implementation, no runtime,
> no broker contact in this task.** Builds on the LIVE, advisory-first implementation
> (commit `c2cb45fc5`): `build_local_reconcile_snapshot(engine="demo")` (IPC) +
> `build_demo_reconcile_snapshot()` (api-demo read-only REST) → `ReconciliationEngine`, escalation
> capped at `MISMATCH_MAJOR` by `RECONCILE_ADVISORY_FIRST_MAX_ESCALATION`
> (`governance_hub_event_handlers.py:75`). **v2 PRESERVES advisory-first: it only makes MATCH
> *achievable*; it does NOT arm.** Arming stays gated by C-ARM-1/2/3.

Rust paths under `srv/rust/openclaw_engine/src/`; Python paths under
`srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/`.

## v2.0 · Problem statement (given; not re-derived)

api-demo is **100% engine-originated** (all writes carry engine `oc_…_dm_…` orderLinkIds or engine
conditional stops). "Engine is sole actor" holds — but it is **necessary, not sufficient**, for
MATCH. The current 59 discrepancies decompose into three structural scope gaps, only one of which is
a real engine bug:

| # | Class | Count | Root class | v2 owner |
|---|---|---|---|---|
| 1 | Orders "missing locally" | 5 CRITICAL | build_local hardcodes `orders:[]` (`governance_reconcile_snapshots.py:119`); engine exposes **no** local open-order surface in IPC (v2.B) | Python (scope) |
| 2 | Dust "position missing locally" (ATOM/AVAX 0.1) | 2 FATAL | **REAL engine bug**: intraday close under-sweeps → sub-min-notional exchange residue; local `evict_if_dust` **drops** it instead of freezing (v2.A) | Rust (fix) |
| 3 | Fills local 4 vs remote 50 | count CRITICAL | window/retention artifact: remote mixes 31 `execType=Funding` + days of history across ~19 symbols; local `recent_fills` is a small ring (v2.C) | Python (matching) |

## v2.A · Engine intraday dust-eviction fix (Rust — trading logic, Rust-first per CLAUDE §一/§七)

### v2.A.1 · Confirmed mechanism (source-pinned)

Two dust dispositions exist and **diverge**, and the intraday path takes the wrong one:

- **Startup = FREEZE.** `PaperState::triage_bybit_sync` (`paper_state/dust_gate.rs:66-128`) retains a
  sub-min-notional exchange holding in `paper_state` under `owner_strategy =
  DUST_FROZEN_STRATEGY` (`"orphan_frozen"`, `position_reconciler/orphan_handler.rs:101`), dispatching
  no close. Local book therefore **mirrors** the exchange dust. Runs **only at startup**.
- **Intraday = EVICT.** A real strategy's close fill lands in
  `apply_fill_with_close_semantics` (`paper_state/fill_engine.rs:315`). The opposite-direction branch
  correctly computes `remaining = pos.qty - close_qty` (`:350`) and, for a partial close, sets the
  local position to the true residual (`:352-354`, e.g. `0.1`). It then immediately calls
  `evict_if_dust(symbol, fill_price, "apply_fill_opposite_residue")` (`:395`).
  `evict_if_dust` (`fill_engine.rs:653`) sees `notional = qty*price < dust_floor_usd` and
  **`positions_remove`s** the `0.1` (`:679`) as a "phantom dust position". `reduce_position` has the
  same post-mutation evict (`fill_engine.rs:525`).

Net: after a maker/partial close under-sweeps (`execute_position_close` dispatches the maker close
with the **explicit** `qty`, not Bybit's `qty=0` full-close form, because
`dispatch_qty = if full_close && !is_close_maker_limit { close_dispatch_qty_for_full_close(...) } else
{ qty }`, `commands.rs:1025-1029`), the exchange keeps `0.1` while local drops to flat. The WS
`PositionUpdate` path cannot repair this: PHANTOM-FILL-FIX-1 made intraday WS **advisory-only**
(`event_consumer/loop_exchange.rs:565-655`; sole mutator is `apply_fill`), and its
`converge_exchange_zero_close` (`commands.rs:1557`) only fires when the exchange reports
`size==0` — a `0.1` residue never triggers it. Reconcile then sees remote `0.1`, local absent →
`_reconcile_positions` "remote has, local doesn't" → **FATAL `POSITION_MISSING` / `FREEZE_TRADING`**
(`reconciliation_engine.py:528-537`).

**Why the existing per-tick retriage does not catch it.** `retriage_synthetic_owner`
(`paper_state/owner_attribution.rs:97`) runs the startup decision tree every tick via
`retriage_synthetic_owner_for_symbol` (`tick_pipeline/pipeline_helpers.rs:738`, called from
`on_tick/step_0_fast_track.rs:104`), and it *does* handle the `DUST_FROZEN` label. **But it early-
returns `NoOp` for any position NOT already wearing a `SYNTHETIC_OWNER_LABELS` label**
(`owner_attribution.rs:112`). A real-strategy close residue is still owned by `ma_crossover` /
`flash_dip_buy` / etc., so retriage never sees it — and `evict_if_dust` drops it before the next tick
anyway. **The gap is precisely the real-strategy→dust transition; it is the one path that freezes at
startup but evicts intraday.**

### v2.A.2 · The fix — freeze-aware `evict_if_dust` (minimal, sole-mutator preserved)

Make `evict_if_dust` **discriminate phantom (evict) from exchange-representable residue (freeze)** at
the eviction point, mirroring startup. The residue then flows into the **existing**
`retriage_synthetic_owner` lifecycle — no new mutator, no new lifecycle machinery.

- **Discriminator = exchange representability, not USD notional.** A `0.1` ATOM residue is a valid
  exchange lot (`round_qty(0.1) > 0`, exchange holds it) → **FREEZE**. A `7e-13` STRKUSDT residue
  (the canonical `dust_floor_usd` phantom, `fill_engine.rs:388-395`) rounds to zero
  (`round_qty(7e-13) == 0`, exchange cannot hold it) → **EVICT** (unchanged). Using `qty_step`
  representability is what keeps the phantom-eviction spiral protection intact while freezing genuine
  exchange residue. **Do NOT freeze on `notional < min_notional` alone** — that would trap `7e-13`
  phantoms as permanent frozen positions and manufacture a *new* "local-has / remote-doesn't"
  discrepancy.
- **PaperState needs one new input: per-symbol `qty_step`.** `PaperState` today has **no**
  `instrument_cache` (that lives on `TickPipeline`); it only mirrors the flat
  `dust_floor_usd` scalar (`paper_state/mod.rs:185`, set via `set_dust_floor_usd`,
  `accessor.rs:387`, from `sync_risk_config_if_changed`, `pipeline_config.rs:169`). Mirror the
  **same pattern**: add `dust_freeze_qty_step: HashMap<String,f64>` to `PaperState`, populated by a
  new `set_dust_freeze_qty_steps()` setter called from the instrument-cache sync point
  (`pipeline_helpers.rs:626` / the `on_tick` config-sync arm). This is a bounded per-symbol scalar
  map, refreshed on instrument sync — the accepted precedent set by `dust_floor_usd`.
- **`evict_if_dust` new disposition** (`fill_engine.rs:653`), inside `apply_fill` (sole mutator):
  1. `notional >= dust_floor_usd` → `None` (unchanged).
  2. else look up `qty_step`; if present **and** `floor(qty/qty_step)*qty_step > 0` (representable)
     **and** owner is a **real** strategy (not already synthetic) → relabel `owner_strategy =
     DUST_FROZEN_STRATEGY`, **retain** the position, bump a distinct `dust_frozen_intraday_total`
     counter (do **not** bump `dust_evictions_total`), return `None`.
  3. else (sub-lot phantom, or symbol absent from the map) → `positions_remove` (current behaviour).
- **Lifecycle after freeze is already built.** Once relabelled `orphan_frozen`, the next tick's
  `retriage_synthetic_owner_for_symbol` (`pipeline_helpers.rs:738`) owns it with the **real**
  `min_notional` from `instrument_cache`: below min → `FrozenAsDust` (stays, matches exchange); if
  price recovers ≥ min_notional and in-universe → `Promoted` back to a strategy; ≥ min_notional and
  out-of-universe → `NeedsEviction` → dispatches a real close. When the exchange residue *does*
  finally clear (a resting close fills, or operator clears it), the WS close fill flows through
  `apply_fill (is_close)` → `remaining≈0` → `positions_remove` (`fill_engine.rs:355`), so local
  tracks the exchange back to flat. The frozen residue is **not** permanently stuck; it is only "not
  re-closed by the engine" (a re-close would fail min_notional regardless).

**Invariants preserved:** `apply_fill` remains the sole `positions` mutator (relabel + retain happen
inside it); `evict_all_dust` reapers already skip `DUST_FROZEN` (`fill_engine.rs:723-726`) and
`evict_if_dust` already skips it (`:667-669`), so a frozen residue is stable against every evict path;
bit-exact PnL/balance arithmetic in the close branch is untouched (the change is post-settlement
disposition only).

### v2.A.3 · Does A subsume reconcile-side dust handling? — YES

`export_state` (`paper_state/snapshots.rs:51`) serialises **every** `positions` entry with its `qty`,
including `orphan_frozen` ones. `build_local_reconcile_snapshot` drops only `size==0`
(`governance_reconcile_snapshots.py:92`), so a frozen `0.1` residue appears locally with `size=0.1`
and its original `side`. `_reconcile_positions` then takes the **both-exist** branch: `0.1` vs `0.1`
is within `qty_tolerance_pct=0.001` → no discrepancy. **The two FATALs disappear at the source; no
reconcile-side dust special-case is needed** (and none should be added — a Python-side "ignore small
positions" filter would blind the reconcile to genuine small-position drift). This is the correct
locality: dust economics belong to the engine that creates and holds the position, not to the
read-only control-plane comparator.

## v2.B · Reconcile order scope (Python control-plane) — DECISION: documented scope-exclusion

### v2.B.1 · Does a matchable local open-order set exist? — NO (in exchange mode)

Investigated the IPC surface. `PipelineSnapshot` (`pipeline_types.rs:96`) exposes only
`recent_intents` (`:128-129`, `TimestampedIntent` — order **intents**, no exchange `orderId`) and
`paper_state`/`recent_fills`. There is **no** field for local open/resting/conditional orders keyed
by `orderId`/`orderLinkId`. Exchange-mode order tracking lives in **loop-transient**
`LoopState.pending_orders` + `order_id_to_link` (`event_consumer/loop_handlers.rs:35-38`), which are
**not** serialised into the snapshot. And by design, in exchange mode the engine keeps **no**
authoritative local resting book: "*Exchange mode never reads this map; real resting orders sit on
Bybit's book and surface via WS order/fill events*" (`paper_state/mod.rs:129-137`). So the exchange
**is** the order authority; any "local order book" would be a lagging echo of the same exchange.

### v2.B.2 · Decision: (b) documented scope-exclusion — recommended over (a)

**Recommend (b).** Keep local `orders` out of reconcile scope and make the comparator **not flag**
remote orders, with the exclusion documented and a `grep`-able flag.

- **(a) build a real local-order surface — REJECTED for v2.** It requires a **new Rust snapshot
  field** serialising `LoopState.pending_orders` (+ conditional stops) with `orderLinkId`/`orderId`,
  a cross-runtime schema change, and it would compare the exchange against a definitionally-downstream
  echo of itself → guaranteed race-flagging (order acked on Bybit, WS event not yet consumed →
  spurious CRITICAL). High cost, negative trust value, and it does not serve v2's goal.
- **Deletion test:** deleting order reconcile loses **nothing** governance-critical. Resting orders
  carry **no position/PnL risk until they fill**; at fill time the fill reconcile (v2.C) + position
  reconcile (v2.A) catch the effect. Positions and balances are the risk-bearing reconcile targets.
- **Authority/trust test:** the exchange is the sole order authority in exchange mode; reconciling it
  against a lagging local mirror weakens, not strengthens, the trust boundary.

**Implementation (Python only):** add `reconcile_orders: bool = False` to `ReconciliationConfig`
(`reconciliation_engine.py:93`). In `reconcile()` (`:278-287`), guard the `_reconcile_orders` call on
that flag; when off, set `orders_checked` to a scope-marker (e.g. `-1` / `0`) and record the exclusion
reason in the report so the operator sees "orders: out-of-scope (exchange-authoritative)" rather than
a silent skip. `build_local_reconcile_snapshot` keeps `orders: []` (document the reason at
`governance_reconcile_snapshots.py:119`, replacing the stale UNKNOWN-2 note with the v2.B decision).
`build_demo_reconcile_snapshot` **may keep pulling** remote orders (`:175`) purely to **display** them
in the response as advisory context (non-discrepancy), or drop the call to save one GET — either is
acceptable; if kept, they must not enter `_reconcile_orders`.

### v2.B.3 · Conditional / untriggered stops must never spuriously flag

The investigation saw **3 engine conditional stops with empty `orderLinkId`, Market/Untriggered**.
Two hazards, both handled by (b):

- Under **current** `_reconcile_orders`, remote-only orders are keyed on `orderId` (`:403`) — Bybit
  conditional stops **do** carry an `orderId`, so today they would flag as CRITICAL remote-only
  (`:421-430`). Scoping order reconcile OFF removes this entirely.
- **If (a) is ever built:** orders with empty `orderLinkId` must be filtered out **before** any
  `orderLinkId`-keyed match — otherwise all empty-linkId conditionals collapse to key `""` and
  cross-flag. Conditional stops are exchange-side **stop protection** (Root Principle 9), not resting
  entries, and should be excluded from any entry-order reconcile by construction. Record this as the
  binding constraint on a future (a).

## v2.C · Fill-window matching (Python control-plane)

### v2.C.1 · Why the ring-buffer asymmetry flags

`_reconcile_fills` (`reconciliation_engine.py:598`) opens with a raw **count** check
`len(paper_fills) != len(remote_fills)` (`:607`): local 4 vs remote 50 → diff 46 → CRITICAL
`FILL_COUNT`. Two independent distortions on the remote side: **(i)** `get_executions("linear",
limit=50)` (`governance_reconcile_snapshots.py:178`) returns raw Bybit executions **including 31
`execType=Funding`** rows (not trades); **(ii)** the 50 span **days across ~19 symbols**, while local
`recent_fills` is a small ring. Critically, local `TimestampedFill` (`pipeline_types.rs:72-91`) carries
`timestamp_ms/symbol/is_long/qty/price/fee` but **no `execId`/`orderId`/`orderLinkId`** — so
`_group_fills_by_order` (`:664`) buckets every local fill under `"unknown"`. **Per-order fill matching
is structurally impossible for the local side; only symbol+time-window matching is available.**

### v2.C.2 · Matching semantics (defined)

Split by locality: remote **data hygiene** in the provider; **windowed comparison policy** in the
engine.

1. **Funding filter — in `build_demo_reconcile_snapshot`** (remote provider, `:178`). Keep only real
   trades: `execType in {"Trade","AdlTrade","BustTrade"}`; drop `Funding`/`Settle`/etc. This is a pure
   function of remote data and belongs with the remote snapshot (BB confirms the execType set). Drops
   the 31 Funding rows.
2. **Window bound — in `_reconcile_fills`** (comparison policy, `:598`). Derive the local window
   `[t_min, t_max]` from local `timestamp_ms`. Filter remote (trade) fills to `execTime ∈ [t_min −
   ε, t_max + ε]`. Compare **within the window only** (count + per-symbol aggregate qty within
   `qty_tolerance_pct`). Do **not** compare per-order (no shared key). If local fills is **empty**,
   **skip** the fill count check (no window can be established → not a discrepancy; positions/balances
   still governs). ε is a small clock-skew tolerance (seconds).
3. **Result:** remote history older than the local ring's oldest retained fill is correctly excluded;
   Funding is excluded; the count/aggregate compare over the aligned window matches at steady state.

Placement rationale (CLAUDE §七 route parse→call→format; §一 control-plane owns reconcile): Funding is
remote-shape hygiene (provider); windowing needs both sides (engine). Neither belongs in the route.

## v2.D · Interaction & MATCH-reachability

**Verdict: after A + B + C, a clean steady-state MATCH is REACHABLE on the linear-USDT scope**, given
the one-time operator prerequisite below. Class-by-class:

- **Positions (2 FATAL):** A retains new intraday dust as `orphan_frozen` → local mirrors exchange →
  both-exist within tolerance → resolved.
- **Orders (5 CRITICAL):** B scopes order reconcile out (exchange-authoritative) → resolved.
- **Fills (count CRITICAL):** C filters Funding + windows the compare → resolved.
- **Balances:** watch item, not in the cited 59. `build_local` wraps a scalar USDT balance; `build_demo`
  sums `coins` with `wallet_balance>0`. Sub-min-notional dust coins can perturb the coin set; confirm
  the residual sits within `balance_tolerance_abs=1.0` USDT at steady state (runtime check).

**Advisory-first is untouched.** The escalation cap `RECONCILE_ADVISORY_FIRST_MAX_ESCALATION =
"MISMATCH_MAJOR"` (`governance_hub_event_handlers.py:75`) and `apply_reconcile_advisory_cap` (`:78`)
stay in place; arming is still gated by **C-ARM-1/2/3** (`:69-73`). v2 makes MATCH *observable*, which
is the evidence C-ARM-1 requires — it does **not** itself arm.

### One-time operator prerequisite (before arming, per `dust_gate.rs:39`)

1. **Clear pre-existing residual dust** on the Bybit **Demo** GUI (the ATOM/AVAX 0.1 etc. that predate
   the A fix). A can only freeze **new** dust going forward; dust the engine *already dropped locally*
   has no local counterpart to match. **Equivalent alternative:** restart the engine **after** the A
   fix deploys — startup `triage_bybit_sync` re-imports exchange dust and freezes it as `orphan_frozen`,
   restoring the local counterpart without touching the exchange. Either path closes the pre-existing
   FATALs; the GUI clear also cleans the book.
2. **Cancel stale resting orders** on the Bybit Demo GUI that the engine no longer tracks (optional for
   v2 MATCH since orders are scoped out; required hygiene if a future (a) arms order reconcile).
3. **Confirm scope = linear-USDT** (C-ARM-2): no inverse/spot holdings that `build_demo` does not
   capture (`get_positions_full_scan(settle_coin="USDT")` returns empty for coin-margined inverse,
   `governance_reconcile_snapshots.py:153-155`). If such holdings exist, either extend coverage or keep
   the documented linear-USDT scope label.
4. Then observe a **steady-state MATCH** across a live shadow window (C-ARM-1) before any arming diff
   (C-ARM-3, operator + CC).

## v2.E · Touch-list, Rust/Python split, tests, reviewers

### Touch-list (file : function : anchor)

| # | Runtime | File | Function / anchor | Change |
|---|---|---|---|---|
| A1 | Rust | `paper_state/mod.rs:185` | `PaperState` fields | Add `dust_freeze_qty_step: HashMap<String,f64>` (mirror `dust_floor_usd`). 中文註解. |
| A2 | Rust | `paper_state/accessor.rs:387` | near `set_dust_floor_usd` | Add `set_dust_freeze_qty_steps(map)` setter. |
| A3 | Rust | `tick_pipeline/pipeline_helpers.rs:626` (or `pipeline_config.rs:169` sync arm) | instrument-cache sync | Push per-symbol `qty_step` into PaperState on instrument sync. |
| A4 | Rust | `paper_state/fill_engine.rs:653` | `evict_if_dust` | Freeze-aware disposition: representable residue → relabel `DUST_FROZEN_STRATEGY` + retain + `dust_frozen_intraday_total`; else evict. Sole change point; callers `:395`/`:525` unchanged. |
| A5 | Rust | `paper_state/mod.rs` | new counter | `dust_frozen_intraday_total` (observability, process-local, NOT DB — per PA §1.2.5, same as `dust_evictions_total`). |
| B1 | Python | `reconciliation_engine.py:93` | `ReconciliationConfig` | Add `reconcile_orders: bool = False`. |
| B2 | Python | `reconciliation_engine.py:278-287` | `reconcile()` | Guard `_reconcile_orders` on the flag; record scope-exclusion reason in report. |
| B3 | Python | `governance_reconcile_snapshots.py:119,68` | `build_local_reconcile_snapshot` | Replace stale UNKNOWN-2 note with v2.B decision (orders out-of-scope, exchange-authoritative). |
| C1 | Python | `governance_reconcile_snapshots.py:178` | `build_demo_reconcile_snapshot` | Filter `execType ∈ {Trade,AdlTrade,BustTrade}` on remote fills. |
| C2 | Python | `reconciliation_engine.py:598-621` | `_reconcile_fills` | Window-bound both sides on local `timestamp_ms`; skip count check when local empty; per-symbol aggregate compare (no per-order key). |

**No change** to: the advisory-first cap, `map_report_to_escalation`, the route fail-closed
short-circuits (`governance_routes.py:1137-1177`), or `converge_exchange_zero_close`.

### Rust vs Python split (E1 dispatch)

- **Rust wave (A1–A5):** one engine change in `paper_state` + one sync-site push. Independent E2 then
  E4. Must `cargo build`/`cargo test` on Linux; the freeze/evict decision + retriage hand-off is
  hot-path — E2 must grep that `evict_if_dust`'s new branch is O(1) and not called per-tick beyond the
  existing `apply_fill`/`reduce_position` sites.
- **Python wave (B1–B3, C1–C2):** control-plane comparator + provider. Independent E2 then E4,
  Mac-runnable unit tests. Disjoint file scope from the Rust wave → the two waves are parallelisable;
  the only ordering coupling is the MATCH-reachability *observation* (needs both landed + the operator
  prerequisite), not the code.

### Test surface (E4 hard edges)

- **Rust (Mac `cargo test`):** (i) close fill leaving a representable sub-floor residue → position
  **retained** as `orphan_frozen`, `dust_frozen_intraday_total==1`, `dust_evictions_total==0`;
  (ii) `7e-13` phantom (rounds to 0) → **evicted**, frozen counter unchanged (phantom-spiral protection
  intact); (iii) symbol absent from `qty_step` map → evict (fail to current behaviour); (iv) a frozen
  residue then fully cleared by a WS close fill → `positions_remove` (tracks back to flat);
  (v) `export_state` includes the frozen residue with `qty>0`.
- **Python (Mac unit):** (i) `reconcile_orders=False` → zero `ORDER_MISSING` discrepancies even with
  remote orders present; (ii) Funding filter drops `execType=Funding` from remote fills; (iii)
  windowed fill compare: remote history older than local `t_min` excluded → no `FILL_COUNT`; empty
  local → fill check skipped; (iv) end-to-end fixture (local frozen 0.1 + remote 0.1, orders scoped,
  windowed fills) → report `overall_result=MATCH`, `is_consistent=True`, `critical_count=0`.
- **NEEDS-LINUX-RUNTIME (not Mac-attestable):** real api-demo round-trip post-fix; real engine restart
  re-freezing existing dust; a live shadow window showing steady-state MATCH (the C-ARM-1 evidence);
  balance residual within tolerance. Label runtime-pending, not source-closed.

### Reviewers needed

- **BB (Bybit venue):** REQUIRED. Confirm (a) the `execType` trade-set `{Trade,AdlTrade,BustTrade}` vs
  Funding/Settle for fill hygiene (v2.C); (b) `qty_step`/`min_notional`/`round_qty` semantics used as
  the freeze-vs-evict discriminator (v2.A); (c) conditional/Untriggered stop shape + empty-`orderLinkId`
  behaviour (v2.B.3).
- **QC (microstructure/economics):** REQUIRED for dust economics — the frozen-residue lifecycle
  (`retriage_synthetic_owner` may `Promote` a recovered residue back to a strategy, or `NeedsEviction`
  at min_notional). Confirm this is acceptable and note the funding-settlement interaction.
- **CC (authority/security):** REQUIRED to confirm advisory-first is preserved and the C-ARM-1/2/3 gate
  is untouched — v2 must not become a covert arming path (the freeze cap is the only load-bearing
  no-freeze guard).
- **E2 → E4:** independent hard edges on both the Rust and Python waves (writer ≠ verifier).

## v2.F · UNKNOWNS needing runtime (cannot be closed from source)

- **U-A1 (runtime).** The exact under-sweep mechanism (`~0.1`) is taken as given from the attribution
  investigation; source confirms the maker-close explicit-`qty` path (`commands.rs:1025-1029`) and the
  `evict_if_dust` drop, but the *empirical* residual size distribution needs a Linux run to confirm the
  freeze threshold behaves for the real ATOM/AVAX lots (BB to confirm those symbols' `qty_step`).
- **U-A2 (runtime).** After the fix, whether a maker-close's **resting** remainder (the unfilled close
  order that produced the residue) is itself still on the book — if so it self-clears via WS on the
  next fill; confirm no double-freeze/second residue in a live shadow.
- **U-C1 (runtime).** The precise local ring depth vs the remote window at steady state (does the ring
  ever evict a within-window fill, which would legitimately flag). Needs runtime; ε and the ring size
  are the tunables.
- **U-D1 (runtime).** Balance residual within `balance_tolerance_abs=1.0` USDT once dust is frozen.
- **U-scope (operator + CC).** C-ARM-2 linear-USDT vs full-account coverage (inverse/spot) is an
  operator/CC decision, not a source fact; keep the documented scope label until settled.
