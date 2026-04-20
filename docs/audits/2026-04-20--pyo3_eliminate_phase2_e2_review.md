# PYO3-ELIMINATE-1 Phase 1 + Phase 2 · E2 Adversarial Review

**Date**: 2026-04-20
**Reviewer**: E2 sub-agent (adversarial)
**Scope**: Phase 1 (PyO3 dead-code deletion + lib.rs registration trim) + Phase 2 (httpx `BybitClient` + 3 call-site migration)
**Critical path covered**: LIVE-GATE-FALLBACK-1 reduce_only emergency close (root principle #6)

---

## Verdict

**APPROVE_WITH_NITS**

Phase 1 deletion is clean (0 production refs, 0 inbound module deps, Cargo.toml unaffected).
Phase 2 httpx client preserves LIVE-GATE-FALLBACK-1 semantics byte-for-byte on the critical
path: `reduce_only` body field key matches (`reduceOnly: true`), `round_qty` returns `None`
on cache miss preserving the `float(None) → TypeError → except → raw qty` fallback chain,
`place_order` returns a dict with `order_id` + `order_link_id` (plus camelCase aliases,
spec-sanctioned superset), and the 3 LIVE-GUARD-1 gates (#1 env opt-in, #2 mainnet env var
fallback closed, #3 empty-credentials ctor raise) are all implemented in `__init__` before
`self._client` is constructed.

Two HIGH findings do not block commit but should be tracked: (1) per-request
`BybitClient` construction in `live_session_routes._get_rust_client_safe()` creates a new
`httpx.Client` per call → connection-pool + file-descriptor pressure under load; (2) error
type change from `RuntimeError` to `BybitBusinessError` / `BybitTransportError` subclasses
of `BybitError(Exception)` is caught by existing `except Exception`, but the **message
format** for `retCode != 0` now leads with `"Bybit API error: retCode=..."` while the
exception class also carries `.ret_code` / `.ret_msg` attributes — this is a net
improvement but needs one grep-check for any log-match / string-dependent consumer
downstream (none found in the 3 migrated call sites, but GUI alerting / Sentry rules may
depend on the old message shape).

Three MEDIUM and four LOW/NIT findings follow. **None are blockers.**

---

## F1 · CRITICAL (none)

No critical findings. LIVE-GATE-FALLBACK-1 semantics preserved:
- `reduce_only=True` → body `"reduceOnly": true` (line 763-764) ✓ Bybit V5 accepts this.
- `order_type="Market"` → body `"orderType": "Market"` (line 747) ✓ no implicit IOC injected.
- Return dict has `{order_id, order_link_id}` + camelCase aliases (line 903-914) — spec §0.3
  required snake_case minimum; camelCase is an additive superset that `_order_response_dual_shape`
  documents explicitly and the parity test locks down (test `test_place_order_dual_shape_response`).
- `instrument_count()` is a method returning `int` — matches old PyO3 shape and the
  `hasattr(rc, "instrument_count") and rc.instrument_count() == 0` guard at
  `live_session_routes.py:1246`.
- `round_qty` returns `Optional[float]` with `None` semantics on cache miss, preserving the
  `float(None)` → `TypeError` → `except Exception → fallback raw qty` chain at lines
  1257-1260.

---

## F2 · HIGH

### F2.1 · Per-request `BybitClient` construction on Live path leaks HTTP connection pools
- **File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py:196-227`
- **Problem**: `_get_rust_client_safe()` constructs a **new** `BybitClient(environment=...)`
  every time the Live slot is configured (the `/live/balance` / `/live/positions` /
  `/live/orders` / `/live/fills` paths hit this). The new httpx `BybitClient.__init__`
  builds an `httpx.Client(...)` with its own connection pool (`bybit_rest_client.py:293-297`).
  `__del__` calls `close()` best-effort, but Python GC is non-deterministic under asyncio
  event loop pressure; concurrent `/live/*` polls from GUI (every ~3-5s) can stack up
  dozens of unclosed `httpx.Client` instances before GC runs.
- **Impact**: Under sustained Live GUI polling (e.g. during a 30-minute operator session
  watching a drawdown), file-descriptor exhaustion risk + TCP connection churn to
  `api-demo.bybit.com` / `api.bybit.com`. Not observable in test (MockTransport), only
  under real load. Old PyO3 was not singleton either but the Rust `reqwest` pool had
  different lifecycle semantics and fewer per-instance allocations.
- **Suggested fix**: Either (a) add `functools.lru_cache(maxsize=4)` keyed on `(env, key)`
  at `live_session_routes.py:207` to reuse instances, or (b) add a module-level
  `_LIVE_BYBIT_CLIENT_CACHE: dict[str, BybitClient]` with a slot-file-mtime invalidation
  check. Spec §4.5 flagged this as a post-migration follow-up; that's acceptable, but
  please file it as a TODO P1 before the 2-3 day observation window closes. If operators
  report Live GUI latency or `httpx.ConnectError`s this is the likely root cause.

### F2.2 · Exception type change from `RuntimeError` to `BybitError` subclasses
- **File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:62-85`
- **Problem**: Old PyO3 bridge raised plain `RuntimeError("Bybit API error: retCode=...")`
  (Rust `mod.rs:29-38`). New raises `BybitBusinessError(RuntimeError)` wait — actually
  new raises `BybitBusinessError(BybitError(Exception))`, **not** a `RuntimeError`
  subclass. The 3 migrated call sites all `except Exception as exc` so catch semantics
  are preserved, but any downstream consumer that specifically `except RuntimeError as exc`
  would **silently miss** the new exception class.
- **Impact**: Grep verified no `except RuntimeError` or `isinstance(..., RuntimeError)`
  checks in the 3 call sites or their direct callees. However, FastAPI middleware,
  Sentry filters, logger filters may upcast to `RuntimeError`. Post-deployment log-diff
  will show error messages change from `RuntimeError: Bybit API error...` to
  `BybitBusinessError: Bybit API error...` — cosmetic but operator-visible.
- **Suggested fix**: Option A — change `BybitError` base from `Exception` to `RuntimeError`
  for perfect backward compat (`class BybitError(RuntimeError)` at line 62). Low risk,
  widens catch radius matching PyO3 behavior. Option B — leave as-is and accept the
  cosmetic log change; E4 regression should grep server logs for `RuntimeError: Bybit`
  → should drop to zero after rebuild.

---

## F3 · MEDIUM

### F3.1 · `get_positions` signature narrowed from 3 params to 1
- **File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:608`
- **Problem**: Old PyO3 `get_positions(category="linear", symbol=None, settle_coin="USDT")`
  accepted 3 keyword args and filtered by `symbol` when provided. New signature is
  `get_positions(self, category: str = "linear")` — only 1 param. Always adds
  `settleCoin=USDT` for linear, never accepts a `symbol` filter.
- **Impact**: Grep verified all 6 production call sites (strategy_ai_routes.py:379/491/620,
  live_session_routes.py:972/1135/1305) pass only `"linear"` positionally. Zero caller
  uses `symbol=` or `settle_coin=` kwarg. **No actual regression**, but the signature
  drift violates the spec §0.3 row 7 contract which required the 3-param form for future
  flexibility / signature parity.
- **Suggested fix**: Widen to match spec:
  ```python
  def get_positions(
      self,
      category: str = "linear",
      symbol: Optional[str] = None,
      settle_coin: Optional[str] = "USDT",
  ) -> list[dict[str, Any]]:
      params: dict[str, Any] = {"category": category}
      if symbol:
          params["symbol"] = symbol
      elif category == "linear" and settle_coin:
          params["settleCoin"] = settle_coin
      # ... rest unchanged
  ```
  This is 5 min of work; do it to avoid the signature regression surprising a future
  caller.

### F3.2 · `get_executions` silently drops `symbol` kwarg vs old bridge
- **File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:683-699`
- **Problem**: Old PyO3 `get_executions(category="linear", symbol=None, limit=None, settle_coin="USDT")`
  had 4 params; new has only `(category: str = "linear", limit: int = 50)` — 2 params. No
  `symbol` or `settle_coin` kwarg acceptance.
- **Impact**: Grep verified production calls only use `get_executions("linear", limit=50)`;
  no regression. But same signature-drift concern as F3.1. Also: default `limit` changed
  from `None → server default (~50)` to explicit `50`. Bybit V5 default for
  `/v5/execution/list` is already 50 so behaviorally equivalent. Flagging for completeness.
- **Suggested fix**: Add `symbol: Optional[str] = None` param and `if symbol: params["symbol"] = symbol`
  branch. Low priority — cosmetic signature parity only.

### F3.3 · Parity test Mode A skip path silently green-signals migration
- **File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_bybit_rest_client_parity.py:85-91`
- **Problem**: `_MODE_A_ENABLED` evaluates `False` when either the PyO3 cdylib is missing
  OR `OPENCLAW_PYO3_PARITY_MODE=skip`. When that happens, all Mode A tests skip with an
  innocuous pytest marker, but Mode B alone doesn't provide side-by-side parity proof —
  it only validates the new client against a synthetic fixture. The stated validation
  (40+15+2647 green) per task description includes 8 Mode A **skips**, meaning no real
  side-by-side parity was ever executed in this session.
- **Impact**: If the Mode B fixtures drifted from actual Bybit V5 response shape (e.g. a
  missing camelCase key that the old PyO3 client also defaulted to `""`), both Mode B
  and production might tolerate it but operator-visible fields could silently go empty.
  Spec §7 step 3 required "PM apply Mode A parity with BOTH clients" but the actual
  validation skipped this.
- **Suggested fix**: Before deployment, run Mode A against a real Bybit demo endpoint
  at least once locally (set `OPENCLAW_PARITY_DEMO_API_KEY` / `OPENCLAW_PARITY_DEMO_API_SECRET`
  env vars from demo slot files, `pytest test_bybit_rest_client_parity.py::TestModeAParity -v`).
  This is operator-run-once validation, not a code change.

---

## F4 · LOW / NIT

### F4.1 · `place_order` `**kwargs` silently drops unknown keys
- **File**: `bybit_rest_client.py:710-790`
- **Problem**: Any misspelled kwarg (e.g. `reduceOnly=True` instead of `reduce_only=True`)
  is silently accepted by `**kwargs` but **ignored** (not in the explicit list of recognized
  keys inside the body). Old PyO3 had an explicit positional signature — `reduceOnly=True`
  would have raised TypeError immediately.
- **Impact**: Future caller typo → silent degradation to non-reduce_only (could open
  instead of close a position). Not a regression from the migration (old bridge would
  have raised, not silently accepted — so new is **worse**) but no current caller has
  this typo risk.
- **Suggested fix**: Replace `**kwargs` with explicit kwargs matching old PyO3 signature
  (`price`, `time_in_force`, `order_link_id`, `trigger_price`, `trigger_direction`,
  `take_profit`, `stop_loss`, `close_on_trigger`). Post-Phase 2 cleanup.

### F4.2 · `clean_restart_flatten.py` error message still has hardcoded `/home/ncyu/`
- **File**: `helper_scripts/clean_restart_flatten.py:40`
- **Problem**: `print("      cd /home/ncyu/BybitOpenClaw/srv  # or $OPENCLAW_BASE_DIR", ...)`
  hardcodes user home dir. Spec §七 requires no hardcoded `/home/ncyu/` paths.
- **Impact**: Text-only hint in an error path; `# or $OPENCLAW_BASE_DIR` comment makes
  the portability intent clear. Still flagged by §七 E2-must-check grep.
- **Suggested fix**:
  ```python
  print("      cd ${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}", file=sys.stderr)
  ```
  or drop the `cd` hint and just say "from the repo root".

### F4.3 · `updated_at_ms` fills local clock, not server time
- **File**: `bybit_rest_client.py:508, 536`
- **Problem**: `updated_at_ms` is set to `int(time.time() * 1000)`. Old PyO3 did the same
  thing (Rust `SystemTime::now()`). The GUI reads this for freshness display. Under
  heavy clock skew (NTP not synced), this can diverge from Bybit server time by seconds.
- **Impact**: Cosmetic — freshness indicator may appear slightly stale/fresh vs reality.
  Not a regression.
- **Suggested fix**: Consider using Bybit response `time` field from `/v5/account/wallet-balance`
  envelope (top-level `time` key per V5 spec) for future improvement. Not urgent.

### F4.4 · NIT — `refresh_balance` hard-codes `accountType=UNIFIED`
- **File**: `bybit_rest_client.py:495`
- **Problem**: Only queries UNIFIED account. CLASSIC / CONTRACT accounts not supported.
  Old PyO3 `AccountManager` had the same limitation (hardcoded UNIFIED). Not a regression.
- **Impact**: Zero — OpenClaw project only uses UNIFIED; docs/ confirms this.
- **Suggested fix**: Document in MODULE_NOTE "UNIFIED-only by design".

---

## Verified items (tracked assertions)

1. **Phase 1 deletion cleanliness**: Read `rust/openclaw_pyo3/src/lib.rs` lines 1-25,
   confirmed only `mod bybit_bridge` declared and only `bybit_bridge::BybitClient`
   registered. Grep `pub mod context_distiller|pub mod hedging_engine|use.*context_distiller|use.*hedging_engine` in
   `rust/` → **0 matches**. Grep `ContextDistiller|HedgingEngine` across repo → only
   doc archives match, zero production code. Cargo.toml read — minimal, unaffected by
   file deletions. Phase 1 is **cleanly revertible**.

2. **No stray `from openclaw_core` production imports**: Grep all `.py` files for
   `from openclaw_core|import openclaw_core` → only match is
   `tests/test_bybit_rest_client_parity.py:76` (test-side optional import with skip
   guard). Spec §9 acceptance criteria satisfied.

3. **LIVE-GUARD-1 Gate #1 (OPENCLAW_ALLOW_MAINNET=1)** enforced: Read
   `bybit_rest_client.py:251-259`, raises `BybitBusinessError` with `retCode=-1` and
   `guard="OPENCLAW_ALLOW_MAINNET"` tag when `os.environ.get("OPENCLAW_ALLOW_MAINNET", "") != "1"`
   on Mainnet. Test `test_mainnet_requires_openclaw_allow_mainnet_env` at line 192-197
   asserts this raises.

4. **LIVE-GUARD-1 Gate #2 (Mainnet env var fallback closed)**: Read `_resolve_credentials`
   at `bybit_rest_client.py:163-200`. `is_mainnet = (env == "mainnet")` gates both
   `BYBIT_API_KEY` and `BYBIT_API_SECRET` env var reads — only demo/testnet/live_demo
   read env vars. Test `test_mainnet_env_var_fallback_disabled` at line 181-189 asserts
   `BybitBusinessError` raised on mainnet + env-only creds.

5. **LIVE-GUARD-1 Gate #3 (empty creds → ctor raise)**: Read
   `bybit_rest_client.py:265-273`, `if is_mainnet and (not key or not secret)` →
   `raise BybitBusinessError` with `guard="mainnet_credentials"`. Matches Rust
   `bybit_rest_client.rs:386-497` semantic.

6. **Credential resolution priority**: Verified explicit-param > env > slot for
   non-mainnet, explicit-param > slot only for mainnet. Test
   `test_resolve_credentials_mainnet_prefers_param` at line 200-206 and
   `test_has_credentials_env_var_for_demo` at 154-163 + `test_has_credentials_slot_file_fallback`
   at 166-178 cover all paths.

7. **HMAC signing parity**: Read `_sign` at line 359-372. Payload format is
   `f"{timestamp}{self._api_key}{self._recv_window}{params}"` — byte-identical to
   Rust `common/bybit_signer.rs:50` `format!("{}{}{}{}", ts, api_key, recv_window, params)`.
   Test `test_sign_known_vector_matches_rust_formula` at line 213-230 asserts this.
   `recv_window` default `"5000"` matches Rust.

8. **GET query string signing (sorted)**: `_get` at line 400-417 sorts `(k, v)` tuples
   by key before joining `k=v&k=v`. Matches Rust contract.

9. **POST body signing (canonical JSON)**: `_post` at line 430-443 uses
   `json.dumps(body, separators=(",", ":"), ensure_ascii=False)` for both the sent
   body and the signing input — consistent (both sides sign the same bytes). Rust
   side uses `serde_json::to_string` which also produces compact separators by default.

10. **Auth headers**: Read `_auth_headers` at line 374-383 — sends
    `X-BAPI-API-KEY`, `X-BAPI-SIGN`, `X-BAPI-TIMESTAMP`, `X-BAPI-RECV-WINDOW`,
    `Content-Type: application/json`. Matches Bybit V5 spec and Rust bridge.

11. **`place_order` `reduceOnly` body field**: Read line 763-764 —
    `if reduce_only: body["reduceOnly"] = True`. Byte-identical to Bybit V5 required
    field name. LIVE-GATE-FALLBACK-1 critical.

12. **`place_order` return shape**: Read `_order_response_dual_shape` at line 903-914.
    Returns dict with `order_id`, `order_link_id`, `orderId`, `orderLinkId` all as
    strings (coerced via `str(...)`). Plus pass-through of any other keys in
    `result` dict. Supports both spec §0.3 minimum shape and `clean_restart_flatten.py:136`
    `r.get('order_id') or r.get('orderId')` fallback chain.

13. **`round_qty` None semantics**: Read line 586-601. `if not spec: return None` on
    cache miss. Matches Rust `InstrumentInfoCache::round_qty` `Option<f64>` → Python
    `None`. Preserves `live_session_routes.py:1258` `float(None)` TypeError fallback
    behavior.

14. **`instrument_count()`**: Read line 343-347. Returns `int` (not a property). Matches
    `live_session_routes.py:1246` `hasattr(rc, "instrument_count") and rc.instrument_count() == 0`
    check.

15. **`get_active_orders` positional-arg compat**: Read line 630-650. Accepts
    `(category, symbol, settle_coin)` as positional and kwargs. `clean_restart_flatten.py:81`
    `client.get_active_orders("linear", None, "USDT")` positional form works.

16. **All 3 call-site imports migrated**: Read `strategy_ai_routes.py:49`
    (`from .bybit_rest_client import BybitClient`), `live_session_routes.py:220`
    (same), `clean_restart_flatten.py:36` (absolute import). Zero leftover
    `from openclaw_core import BybitClient` in production.

17. **Singleton naming change registered**: `strategy_ai_routes.py:34-35`
    `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE` — CLAUDE.md §九 table does not
    currently list `_RUST_BYBIT_CLIENT` / `_BYBIT_CLIENT` entries. **Register
    `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE`** under CLAUDE.md §九 in same
    commit as the migration, otherwise §九 drift accrues.

---

## Required operator-side validation

1. **Run Mode A parity against real Bybit demo endpoint at least once** (not in
   CI — locally):
   ```bash
   export OPENCLAW_PARITY_DEMO_API_KEY="$(cat $OPENCLAW_SECRETS_DIR/demo/api_key)"
   export OPENCLAW_PARITY_DEMO_API_SECRET="$(cat $OPENCLAW_SECRETS_DIR/demo/api_secret)"
   unset OPENCLAW_PYO3_PARITY_MODE
   cd program_code/exchange_connectors/bybit_connector/control_api_v1
   pytest tests/test_bybit_rest_client_parity.py::TestModeAParity -v
   ```
   This is the spec §7 step 3 gate that's currently unproven.

2. **Post-deployment grep server logs** for `RuntimeError: Bybit` vs `BybitBusinessError`
   / `BybitTransportError` — confirms F2.2 cosmetic impact is understood. Any Sentry /
   log-filter rule keyed on the old message should be updated.

3. **Watch file descriptor count on FastAPI worker** during a 30-min Live GUI session:
   ```bash
   ls -la /proc/$(pgrep -f 'uvicorn.*openclaw')/fd | wc -l
   ```
   Baseline expectation: <256 FDs. If rising >1000 in 30 min, F2.1 is confirmed and
   F3.1-style caching needed urgently.

---

## Recommended next steps

1. **Commit Phase 1 + Phase 2 as-is** (APPROVE_WITH_NITS — no blocker).
2. **Same commit**: add `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE` to CLAUDE.md §九
   singleton table (F4 bookkeeping).
3. **Follow-up PR (P1)**: address F3.1 `get_positions` signature parity + F3.2
   `get_executions` signature parity (~15 min combined, low risk).
4. **Follow-up PR (P2)**: address F2.1 `live_session_routes._get_rust_client_safe()`
   caching (`functools.lru_cache` or module-level cache) — defers connection-pool
   leak risk.
5. **Follow-up PR (P3)**: address F4.1 `place_order` kwargs → explicit params
   (typo-safety).
6. **Operator gate** before Phase 3 (PyO3 crate deletion): complete the Mode A real-endpoint
   parity run from §"Required operator-side validation" step 1. Without it, deleting
   the `openclaw_pyo3` crate in Phase 3 is premature — the Mode B snapshot tests alone
   cannot prove side-by-side equivalence.

---

## Notes on scope boundaries

- Not reviewed: `test_bybit_rest_client.py` 40 unit tests — task description stated these
  are green, treated as given.
- Not reviewed: Rust `bybit_bridge/orders.rs` / `positions.rs` / `market_data.rs` internals
  beyond what was needed to verify old `OrderResponse` serde shape and `SymbolSpec::round_qty`
  semantics.
- Not reviewed: integration tests in `tests/test_live_gate_fallback.py` — assumed green
  per operator report but E4 should run them once more post-migration.

— END OF REPORT —
