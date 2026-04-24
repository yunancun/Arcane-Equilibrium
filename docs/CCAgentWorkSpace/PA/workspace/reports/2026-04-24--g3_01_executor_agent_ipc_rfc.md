# G3-01 RFC — ExecutorAgent ConfigStore + IPC Contract for Shadow→Live Toggle

- **Author**: PA (Project Architect)
- **Date**: 2026-04-24
- **Status**: DRAFT (design artifact, not implementation)
- **Git HEAD**: `d624dea` (branch `main`)
- **Supersedes**: None
- **Implemented by**: G3-02 / G3-03 (later sessions)
- **Related audits**:
  - `docs/audits/2026-04-24--todo_refactor_audit.md` — flagged `_shadow_mode` hardcode
  - `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md` — G3 work group
- **Related memory**:
  - `memory/project_layer2_agent_design.md` — "real Layer 2 gap" framing
  - `memory/feedback_rust_authoritative_config.md` — Rust ConfigStore is authoritative
  - `memory/project_5agent_runtime_state.md` — runtime state of 5-agent layer
- **CLAUDE.md references**: §二 principle #3 (AI output ≠ immediate command), #6 (failure default = shrink), §七 Rust authority rule

---

## 1. Problem Statement

### 1.1 Concrete finding (from 2026-04-24 10-agent audit)

`ExecutorAgent._shadow_mode = True` is a Python class-level attribute hardcoded in the source file, with no constructor override or runtime read path. Concrete locations:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482`:

  ```python
  _shadow_mode: bool = True
  ```

  This literal sits in the `ExecutorAgent` class body. Every instance sees `self._shadow_mode = True` unless an explicit `instance._shadow_mode = False` mutation happens somewhere — and grep confirms **there is none in the repo**.

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:467`:

  ```python
  EXECUTOR_AGENT = ExecutorAgent(
      config=ExecutorConfig(),
      message_bus=MESSAGE_BUS,
      paper_engine=PAPER_ENGINE,
      governance_hub=_GOV_HUB_FOR_EXECUTOR,
      audit_callback=_EXECUTOR_AUDIT_CB,
  )
  ```

  `ExecutorConfig()` is called with zero overrides. The dataclass (`executor_agent.py:99-112`) holds `max_slippage_bps`, `max_fill_time_ms`, `max_reports`, `dedup_window_seconds` — **no `shadow_mode` field exists on the config at all**. The `shadow_mode` flag is a separate class attribute on the agent itself, structurally detached from the config.

- `executor_agent.py:512`: the runtime read:

  ```python
  if self._shadow_mode:
      # Shadow mode: log only, don't submit / 影子模式：僅記錄不提交
      ...
      return report
  ```

  Result: `_execute_via_ipc` always takes the shadow branch. SubmitOrder IPC to Rust `intent_processor` is **physically unreachable** in the running system.

### 1.2 Why this is a violation

**CLAUDE.md §二 principle #3** — "AI 輸出 ≠ 即時命令":

> AI → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行

The Decision Lease path is intentionally designed so that an AI agent's intent must be reversible and auditable. A hardcoded Python bool violates this because:

1. **Not reversible at runtime.** Flipping requires a code edit + `restart_all.sh --rebuild` (engine rebuild, minutes of downtime) instead of the project's standard `<60s` IPC hot-reload turnaround.
2. **Not auditable.** There is no `ipc_change_audit_log` entry for a Python literal change; a `git blame` on `executor_agent.py:482` is the only trace.
3. **Not gated by authorization.** The existing live-gate chain (`authorization.json` HMAC, Operator role, `OPENCLAW_ALLOW_MAINNET`, `live_reserved`) is bypassed entirely by a Python code edit.

Additionally, **CLAUDE.md §七** ("Rust 為唯一交易參數權威"): all trading/risk/learning parameters live in Rust `ConfigStore` + TOML + IPC hot-reload. A critical execution gate on the Python side outside that contract is a category error — it places trading-behavior authority in Python, not Rust.

### 1.3 Live deploy path blocker

Per CLAUDE.md §十 ("下一步工作指針"), the current Live_Ready state has 5 gates (4 Rust-verifiable + 1 Python). The Executor IPC shadow is not itself one of those 5 gates — it is *below* the gates, at the physical plumbing layer. Even if operator clears all 5 gates, **no SubmitOrder IPC will reach Rust** because `_shadow_mode=True` short-circuits the call on line 512. Concretely:

- StrategistAgent is `shadow=False` (live-wired at `strategy_wiring.py:243`). Intents flow into `message_bus`.
- GuardianAgent approves/rejects them via `message_bus`.
- ExecutorAgent receives approved intents, calls `_execute_via_ipc`, hits line 512, returns a shadow report, and **does not call `paper_trading_routes._ipc_command`**.
- Rust `intent_processor` never sees the `SubmitOrder` message.

Executor is the last 5-agent still in forced shadow; unblocking real demo-fill → live traffic requires a proper control-plane flip, not a Python literal edit.

### 1.4 Anti-pattern to avoid

The naive fix — add a `shadow_mode: bool = True` field to Python `ExecutorConfig` and flip it in `strategy_wiring.py:467` — would violate §七's Rust-authority rule and create a second source of truth. The next operator who tries to disable executor via `patch_risk_config` will be confused when nothing happens. RFC rejects this path (see §3).

---

## 2. Design Goals

### 2.1 Hard requirements

1. **Rust is the single source of truth.** `shadow_mode` lives in Rust `RiskConfig.executor.shadow_mode` (a new sub-struct inside the existing per-engine risk config), persisted in `settings/risk_control_rules/risk_config_{demo,live,paper}.toml` as a new `[executor]` section.
2. **Hot-reloadable via IPC.** A single IPC method `patch_executor_config` flips shadow↔live with the same `<60s` turnaround guaranteed by `patch_risk_config` (mirror contract shape exactly).
3. **No Python restart.** Python `ExecutorAgent` reads from a lightweight cache layer refreshed at tick cadence (or every N seconds) — no per-tick IPC round-trip, no restart-to-apply.
4. **No Rust rebuild.** TOML edit or IPC patch alone activates the change. Rust binary only rebuilds when the control-plane code itself changes.
5. **Auth-gated write path.** The IPC method mirrors `patch_risk_config`'s auth check — Operator role + live_reserved + (for shadow→live flip specifically) a green `authorization.json` matching the engine's live gate.
6. **Principle #6 fail-closed.** If the cache fetch errors, stale reads default to `shadow_mode=true` (safe: no live order placed). Never fail-open to live.

### 2.2 Explicit non-goals (defer to later RFCs)

- **Per-symbol overrides.** v1 global only. Symbol-scoped shadow mode would require extending the map model and is deferred (listed as open question in §10).
- **Gradual position ramp** (e.g. `max_position_pct` 0%→100% over N days). This RFC lets a separate `max_position_pct` field live in the new `ExecutorConfig` block but does not specify a ramp schedule. Operator manually staircases via repeated IPC patches.
- **Layer 2 reasoning integration.** `memory/project_layer2_agent_design.md` lays out a larger L0/L1/L2 picture. This RFC unblocks the physical IPC layer; Layer 2 reasoning rides on top unchanged.
- **Executor-scoped circuit breaker** (automatic shadow-flip on N consecutive slippage violations). Nice-to-have; `ExecutorAgent` can set internal flags but does not mutate `ConfigStore`. Defer.

---

## 3. Source-of-Truth Map

### 3.1 Field routing table

| Field | Canonical location | Format | Hot-reload | Python read path | Rust read path |
|---|---|---|---|---|---|
| `shadow_mode` | Rust `RiskConfig.executor.shadow_mode` | `bool` | Yes (IPC + TOML) | `executor_config_cache.get().shadow_mode` | `risk_config.executor.shadow_mode` |
| `max_position_pct` | Rust `RiskConfig.executor.max_position_pct` | `f64` (0.0–1.0) | Yes | cache | direct |
| `per_symbol_position_cap` | Rust `RiskConfig.executor.per_symbol_position_cap` | `HashMap<String, f64>` | Yes | cache | direct |
| `max_slippage_bps` | **Open Q — §10.3**. Provisional: stays in Python `ExecutorConfig` (local validation concern) | `f64` | No (Python-side static) | `self._config.max_slippage_bps` | N/A |
| `max_fill_time_ms` | Python `ExecutorConfig` (local) | `f64` | No | `self._config.max_fill_time_ms` | N/A |
| `dedup_window_seconds` | Python `ExecutorConfig` (local) | `f64` | No | `self._config.dedup_window_seconds` | N/A |
| `max_reports` | Python `ExecutorConfig` (local, memory sizing) | `int` | No | `self._config.max_reports` | N/A |

**Principle**: trading-behavior fields (shadow gate, position sizing) → Rust. Local-process housekeeping (in-memory report buffer size, dedup window timing) → Python stays.

### 3.2 Write path (single direction)

```
operator → POST /api/v1/executor/shadow_toggle (FastAPI)
       ↓  (validate payload + Operator role check)
       ↓
  IPC patch_executor_config {shadow_mode: false, source: "operator"}
       ↓
  Rust ipc_server/handlers_config.rs → handle_patch_config(...)
       ↓  (RiskConfig.validate, ArcSwap swap, persist TOML, audit log)
       ↓
  ConfigStore<RiskConfig> version bump, broadcast on watch channel
       ↓
  Python ExecutorConfigCache polls at next tick → sees new version
```

### 3.3 Read path (every tick)

Python executes per-tick:

```
ExecutorAgent.on_message(intent) → Guardian-approved → _execute_via_ipc(...)
       ↓
  shadow = executor_config_cache.get().shadow_mode   # ← O(1) cached read
       ↓
  if shadow: log + return shadow report
  else: send SubmitOrder IPC to Rust
```

No IPC call inside the hot path. The cache layer (§5.2) refreshes out of band.

---

## 4. IPC Contract (RFC Core)

### 4.1 Method: `patch_executor_config`

**Shape**: mirrors `patch_risk_config` exactly. From `rust/openclaw_engine/src/ipc_server/mod.rs:944-960`, the existing pattern is:

```rust
"patch_risk_config" => {
    let engine = req.params.get("engine").and_then(|v| v.as_str()).unwrap_or("paper");
    let store = risk_stores.as_ref().map(|s| Arc::clone(s.select(engine)));
    handle_patch_config(id, &store, &req.params, RiskConfig::validate,
                        &format!("risk/{engine}"), audit_pool)
}
```

The new handler **reuses the same `handle_patch_config` generic** (no new infrastructure), routed through the same per-engine store selector. Copy-adapt is trivial.

### 4.2 Request schema (JSON-RPC 2.0)

```json
{
  "jsonrpc": "2.0",
  "method": "patch_executor_config",
  "params": {
    "engine": "demo",                // "paper" | "demo" | "live" (default "paper")
    "source": "operator",            // provenance: "operator" | "agent" | "scheduler"
    "patch": {
      "shadow_mode": false,          // optional
      "max_position_pct": 0.05,      // optional, 0.0-1.0
      "per_symbol_position_cap": {   // optional, partial merge
        "BTCUSDT": 0.10,
        "ETHUSDT": 0.05
      }
    }
  },
  "id": 9101
}
```

Partial patch semantics: any field absent from `patch` is left unchanged. `per_symbol_position_cap` merges key-by-key (set a value to `null` to remove a symbol).

### 4.3 Response schema

Success:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "applied": {"shadow_mode": false, "max_position_pct": 0.05},
    "rejected": {},
    "version": 47,                    // post-patch ConfigStore version
    "ts_ms": 1729800000000,
    "source": "ipc",
    "engine": "demo"
  },
  "id": 9101
}
```

Validation failure (mirrors `test_rc1_patch_risk_config_validation_failure_rolls_back` at `rust/openclaw_engine/src/ipc_server/tests/config.rs:87`):

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32602,
    "message": "validation failed",
    "data": {
      "field": "max_position_pct",
      "reason": "out of range [0.0, 1.0]",
      "got": 1.5
    }
  },
  "id": 9101
}
```

Auth failure:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32001,
    "message": "authorization required",
    "data": {
      "gate_failed": "live_reserved",
      "hint": "only Operator role with live_reserved mode can flip shadow_mode=false"
    }
  },
  "id": 9101
}
```

### 4.4 Auth gate matrix

| Transition | `engine="paper"` | `engine="demo"` | `engine="live"` (LiveDemo or Mainnet) |
|---|---|---|---|
| `shadow_mode: true → true` (no-op) | Operator | Operator | Operator |
| `shadow_mode: true → false` (enable real send) | Operator | Operator + live_reserved | **Operator + live_reserved + authorization.json green + `OPENCLAW_ALLOW_MAINNET=1` (Mainnet only)** |
| `shadow_mode: false → true` (back to safe) | Operator | Operator | Operator (no live-gate required for retreat) |
| `max_position_pct` decrease | Operator | Operator | Operator |
| `max_position_pct` increase | Operator | Operator | Operator + live_reserved |

**Key asymmetry**: flipping back to shadow (safe direction) requires only Operator role; flipping to live requires full gate. This matches CLAUDE.md §四 live-gate chain and principle #6 (fail-closed, retreat is always cheap).

Implementation note: Rust handler reads `source` field + checks against current engine mode + calls existing `verify_operator_role` / `verify_live_gate` helpers used by `patch_risk_config`. No new auth logic to build.

### 4.5 Companion method: `get_executor_config`

```json
{"jsonrpc":"2.0","method":"get_executor_config","params":{"engine":"demo"},"id":9102}
```

Returns the current `ExecutorConfig` state + version. Used by:

1. `ExecutorConfigCache` background refresh (§5.2).
2. `/api/v1/executor/config` GET route (§5.4) for GUI display.
3. Audit/debug tools.

Shape:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "engine": "demo",
    "config": {
      "shadow_mode": true,
      "max_position_pct": 0.02,
      "per_symbol_position_cap": {}
    },
    "version": 46,
    "ts_ms": 1729800000000
  },
  "id": 9102
}
```

### 4.6 Rollback contract

- Single IPC `patch_executor_config {shadow_mode: true}` → full retreat.
- Target turnaround: **< 60 seconds** end-to-end (operator GUI click → Python cache refresh). Measured: IPC round-trip ~5-20ms, cache refresh window 100ms (§5.2), worst-case next-tick read ~1s → 2s p99 including network.
- Persistent: Rust handler writes the TOML file in the same operation (reusing the `handle_patch_config` persist logic), so engine restart respects the latest value.

### 4.7 Rate limit / debounce

Match `patch_risk_config`: no explicit rate limit in Rust; FastAPI-side `slowapi` limiter on `/api/v1/executor/shadow_toggle` keeps external call rate sane. Audit log entry per call regardless (§4.2 already ties into `audit_pool`).

### 4.8 Audit trail

Existing `handle_patch_config` writes to `ipc_change_audit_log`. The new method reuses it unchanged. Operator can grep the audit log for every `shadow_mode` flip with full before/after/timestamp/source.

---

## 5. Python-Side Changes (File-by-File, No Code)

### 5.1 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py`

- **Line 99–112** (`ExecutorConfig` dataclass): keep as-is. Do **not** add `shadow_mode` field here (see §3.1 — `shadow_mode` moves to Rust ConfigStore, not to a Python config). The Python `ExecutorConfig` continues to own local-process housekeeping fields only.
- **Line 482** (class attribute `_shadow_mode: bool = True`): **remove**. The class-level literal goes away entirely.
- **Line 512** (`if self._shadow_mode:` check): replace with a cache lookup. The control plane reads from a module-level cache helper (defined in §5.2), not from an instance attribute. Failure path: cache unavailable → default `True` (shadow) per principle #6.
- Add a short docstring block referencing this RFC + CLAUDE.md §二 principle #3 + the audit finding.
- **No behavior change from Phase B alone.** When the cache sees `shadow_mode=true` (the initial TOML default), flow is identical to today.

### 5.2 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_config_cache.py` (NEW, ~80-120 lines)

Sibling module to existing IPC call helpers. Responsibilities:

- **Singleton cache** holding last-known `ExecutorConfig` snapshot (`shadow_mode`, `max_position_pct`, `per_symbol_position_cap`, `version`, `fetched_at_ms`).
- **Refresh policy**: background `asyncio.Task` (or a thread-based poller for worker-process safety under uvicorn's `--workers 4`) calls `get_executor_config` every `POLL_INTERVAL_MS` (default 100ms, configurable via env). Swaps the snapshot atomically.
- **Read API**: `get_snapshot() -> ExecutorConfigSnapshot` — O(1) dict/object access, never blocks.
- **Fail-closed default**: on first run before initial fetch succeeds, or after >3 consecutive fetch failures, `get_snapshot().shadow_mode` returns `True` (safe). Log warning at most every 60s to avoid log spam.
- **Engine-aware**: the cache picks engine from `OPENCLAW_ENGINE_MODE` env (default `"demo"`) and requests the matching engine in `get_executor_config`. Mirror the convention used by `patch_risk_config` clients.
- **Leader election consideration**: uvicorn 4-worker deployment → 4 pollers. Fine for reads (read amplification is tiny, IPC overhead negligible); no leader election needed. Contrast with `edge_estimator_scheduler.py`'s flock pattern (§CLAUDE.md §九 singleton table) which must be single-writer.
- **Register as singleton** in CLAUDE.md §九 singleton table: `_EXECUTOR_CONFIG_CACHE` in `executor_config_cache.py`, internal lazy init via `get_executor_config_cache()`.

Testing hooks: `_reset_for_tests()`, `_inject_snapshot_for_tests(snapshot)`.

### 5.3 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py`

- **Line 467** (`EXECUTOR_AGENT = ExecutorAgent(config=ExecutorConfig(), ...)`): keep the construction, but insert cache initialization **before** agent construction (approx. line 460 area, after `_EXECUTOR_AUDIT_CB` is built):
  - Call `executor_config_cache.get_executor_config_cache()` once to warm-start the cache (triggers initial fetch + starts the poller task).
  - Pass the cache handle into `ExecutorAgent` constructor if we need per-instance override support later — open question, §10. Default for v1: cache is a module-level singleton and `ExecutorAgent` reads it by import (matches the current pattern used elsewhere like `paper_trading_routes._ipc_command`).
- Add a line in the post-construction log to show initial cached `shadow_mode` value + version + engine.

### 5.4 Route layer — new or appended file

Two candidate landing spots (pick during implementation):

- **Option A (preferred)**: new `program_code/exchange_connectors/bybit_connector/control_api_v1/app/legacy_routes/executor_routes.py`, registered from `main_legacy.py` alongside the other `register_*_legacy_routes(app)` calls. Clean separation, matches the Wave A-D split pattern (CLAUDE.md §三).
- **Option B**: append to existing `control_legacy_routes.py` (the 493-line control/IPC sibling). Cheaper but muddies ownership.

Routes:

1. `GET /api/v1/executor/config?engine={paper,demo,live}` — proxy to IPC `get_executor_config`. No auth beyond standard session. Returns sanitized config JSON for GUI display.
2. `POST /api/v1/executor/shadow_toggle` — body `{"engine": "demo", "shadow_mode": false}`. Operator-only auth. Calls IPC `patch_executor_config` with `source="operator"`. Responds with `applied`/`rejected` envelope matching other write routes.
3. `POST /api/v1/executor/config/patch` — general-purpose patch endpoint; body is the full `patch` object per §4.2. Same auth as #2 but with stricter gate on `shadow_mode=false` and `max_position_pct` increase (§4.4 matrix).

Envelope + rate limiter: use `base.envelope_response` + `base.limiter` from `main_legacy` per CLAUDE.md §九 singleton table.

### 5.5 Tests

- Unit test for `executor_config_cache`: mock IPC client, inject responses, assert fail-closed default, assert refresh cadence, assert atomic swap.
- Route test for `/api/v1/executor/shadow_toggle`: mock IPC, assert Operator-role required, assert payload validation, assert audit log entry emitted via existing test patterns used by `patch_risk_config` routes.

---

## 6. Rust-Side Changes (File-by-File, No Code)

### 6.1 `rust/openclaw_engine/src/config/risk_config.rs`

- Add a new struct `ExecutorConfig` (not to be confused with Python's `ExecutorConfig` dataclass — namespaces differ, not a collision concern because Rust field is `RiskConfig.executor`):
  - `shadow_mode: bool` (default `true`)
  - `max_position_pct: f64` (default `0.02`, i.e. 2%; range 0.0–1.0)
  - `per_symbol_position_cap: HashMap<String, f64>` (default empty map)
- Embed as a field on `RiskConfig`:
  - `pub executor: ExecutorConfig`
- Implement `Default` for `ExecutorConfig` with the conservative defaults above.
- Implement `validate()` hook: range-check `max_position_pct` in `[0.0, 1.0]`; per-symbol cap values in `[0.0, 1.0]`; reject non-ASCII or empty symbol keys.
- Implement `Serialize`/`Deserialize` via `serde` (mirrors existing sub-structs like `ExitConfig`).
- Extend `RiskConfig::validate` to recursively call `self.executor.validate()`.

### 6.2 `rust/openclaw_engine/src/config/risk_config_tests.rs` (append)

- TOML deserialization test: `[executor] shadow_mode = true` round-trips.
- Validation test: `max_position_pct = 1.5` → `validate` errors.
- Default test: missing `[executor]` section → all defaults materialize.
- Partial patch test: patch merges correctly without clobbering sibling fields.

### 6.3 `rust/openclaw_engine/src/ipc_server/mod.rs`

- Add two method arms in `dispatch_request` alongside the existing `"patch_risk_config"` / `"get_risk_config"` pattern (from lines 932–960):
  - `"get_executor_config"` — extract engine param, select store, call a new light handler that returns just the `executor` sub-view of `RiskConfig` + version. Why a dedicated handler: future `patch_executor_config` might diverge from `patch_risk_config` in validation hooks; keeping separate avoids entanglement.
  - `"patch_executor_config"` — call `handle_patch_config` **scoped to the executor sub-config** using a closure-based path into `RiskConfig.executor`. Alternative: reuse `handle_patch_config` directly with a pre-processed patch JSON that wraps `{executor: {...}}` around the incoming patch object — simpler, no new generic. Pick during implementation; both work.

### 6.4 `rust/openclaw_engine/src/ipc_server/handlers_config.rs`

- Add `get_executor_config_handler` (wraps `handle_get_config` with a field projection).
- Wire the auth matrix from §4.4 in a small `check_executor_patch_auth(params, current_config) -> Result<(), AuthError>` function called before `handle_patch_config`. Specifically:
  - If `patch.shadow_mode == Some(false)` and engine is live → require `authorization.json` green + `live_reserved`.
  - If `patch.max_position_pct.is_some() && new > current` and engine is live → require `live_reserved`.
  - Otherwise → Operator role sufficient.

### 6.5 `rust/openclaw_engine/src/ipc_server/tests/config.rs`

Add integration tests mirroring existing `test_rc1_patch_risk_config_*` patterns:

- `test_g3_01_patch_executor_config_bumps_version_and_updates` — happy path.
- `test_g3_01_patch_executor_config_shadow_true_to_false_live_denied_without_auth` — auth gate.
- `test_g3_01_patch_executor_config_shadow_false_to_true_always_allowed` — retreat is cheap.
- `test_g3_01_patch_executor_config_engine_routing` — paper/demo/live stores route independently (mirrors `test_p2_patch_risk_config_engine_routing`).
- `test_g3_01_get_executor_config_returns_current_state`.
- `test_g3_01_patch_executor_config_validation_rejects_out_of_range_position_pct`.

### 6.6 `rust/openclaw_engine/src/intent_processor/mod.rs`

- `SubmitOrder` IPC receiver: at entry, read `risk_config.executor.shadow_mode` via `ConfigStore::load()`.
- If `true`: log at `info` level `"intent_processor: SubmitOrder received but executor.shadow_mode=true, swallowing / 執行器影子模式, 不轉發"` + **do not** call downstream REST/paper_state. Return a success response to the caller (Python side treats this as "intent captured but not executed" — mirrors current shadow semantics).
- If `false`: continue to the existing live path (forward to Bybit REST or paper_state per `engine_mode`).

This is the physical enforcement gate. Even if Python cache is stale and sends a `SubmitOrder`, Rust has the last word. Defense in depth.

**Note**: keep the Python-side shadow check from §5.1. Redundant with Rust? Yes — intentionally. Principle #6: two independent gates, either failing closed → safe. Removing Python-side check would make shadow status opaque at the intent-emission boundary (loses audit clarity in `ExecutionReport`).

### 6.7 TOML files

**Three files** in `settings/risk_control_rules/`:

- `risk_config_paper.toml`:

  ```toml
  [executor]
  shadow_mode = true
  max_position_pct = 0.02
  # per_symbol_position_cap = { }
  ```

- `risk_config_demo.toml`: same defaults (`shadow_mode = true`).
- `risk_config_live.toml`: **initially** `shadow_mode = true`. Flipped to `false` by operator via IPC after Phase C verification (§7.3). **Not** flipped statically in TOML at first deploy — we want the IPC path exercised end-to-end before committing to a persisted live state.

Comments in each TOML file should reference:
- This RFC (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g3_01_executor_agent_ipc_rfc.md`).
- CLAUDE.md §二 principle #3.
- The flip playbook in §7.

### 6.8 `rust/openclaw_engine/src/config/io.rs`

- If the file-based TOML loader uses a strict schema (deserialize error on unknown keys), extend the schema mapping so `[executor]` is recognized in all three risk config files.
- Round-trip persist: when `handle_patch_config` writes back, `[executor]` section emits with current values.

---

## 7. Migration Plan (3 Phases, Each Independently Verifiable)

### 7.1 Phase A — Rust foundation (no runtime behavior change)

**Scope**:
- §6.1 `ExecutorConfig` struct + `validate`.
- §6.2 unit tests.
- §6.3 IPC method arms.
- §6.4 auth-check helper.
- §6.5 integration tests.
- §6.6 `intent_processor` reads `executor.shadow_mode` (but Python still hardcodes `True`, so this path is not yet exercised from Python).
- §6.7 TOML entries (all three files, `shadow_mode = true`).
- §6.8 io.rs schema.

**Verification**:
- `cargo test --release -p openclaw_engine --lib` — engine lib test count goes from 1992 baseline → 1992 + N new (expect ~8-12 from config + IPC tests, §8).
- `cargo test --release -p openclaw_engine --test migrations_test` — green (no schema impact expected; this is the existing test harness).
- Manual: `ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild"` → engine starts with new config, healthcheck green.
- Manual: `echo '{"jsonrpc":"2.0","method":"get_executor_config","params":{"engine":"demo"},"id":1}' | socat - UNIX-CONNECT:$OPENCLAW_DATA_DIR/engine.sock` → returns current state (`shadow_mode=true`, etc.).
- Manual: patch via IPC, verify audit log row, verify TOML file persisted.

**Git**: one commit, label `feat(g3-01/phase-a): Rust ExecutorConfig + IPC handlers`. No Python change → engine behavior identical to pre-RFC.

### 7.2 Phase B — Python read path (still default shadow)

**Scope**:
- §5.2 `executor_config_cache.py` new file.
- §5.1 `executor_agent.py:482` removed, line 512 refactored to cache read.
- §5.3 `strategy_wiring.py:467` area updated to warm-start the cache.
- §5.4 three FastAPI routes.
- §5.5 tests.
- CLAUDE.md §九 singleton table updated with `_EXECUTOR_CONFIG_CACHE`.

**Verification**:
- Unit + route tests green.
- Manual: start uvicorn, watch logs — cache initial fetch logs `shadow_mode=true version=X`.
- Manual: `GET /api/v1/executor/config?engine=demo` → returns `{shadow_mode: true, ...}`.
- Manual: inject a decision via Strategist, watch Executor log — should still log `"Executor IPC shadow: intent=..."` (no behavior change from Phase A, just a different read path).
- Regression: all existing integration tests pass (no change in external behavior).

**Git**: one commit, label `feat(g3-01/phase-b): Python ExecutorConfigCache + FastAPI routes`. TOML still `shadow_mode=true` for all engines → live order placement still impossible.

### 7.3 Phase C — Flip demo to live (operator-driven)

**Scope**: no code change. Operator action.

1. Pre-flight:
   - Ensure demo engine_mode healthy, engine + uvicorn green per `passive_wait_healthcheck`.
   - Run `ssh trade-core "cat $OPENCLAW_DATA_DIR/engine_mode.txt"` — confirm `demo`.
   - Verify `GET /api/v1/executor/config?engine=demo` returns `shadow_mode=true`.
2. Flip:
   - `POST /api/v1/executor/shadow_toggle` body `{"engine": "demo", "shadow_mode": false}` with Operator session.
   - Observe HTTP 200 + `applied: {shadow_mode: false}`.
   - Observe IPC audit log row appended.
3. Post-flip verification (within 2s cache refresh):
   - Inject a test Strategist intent for a tiny BTCUSDT position.
   - Watch logs in order:
     - Strategist: emits intent.
     - Guardian: approves.
     - Executor: **now logs real IPC submit**, not shadow.
     - Rust intent_processor: receives `SubmitOrder`, forwards to paper_state (demo mode).
     - Bybit demo: receives order, fills.
     - Executor `ExecutionReport`: `success=true, metadata.execution_path="ipc_real"` (not `ipc_shadow`).
   - Verify `trading.fills` table gets the row (via `helper_scripts/db/audit_migrations.py`-style query).
4. Rollback check:
   - Flip back: `POST /api/v1/executor/shadow_toggle` body `{"engine": "demo", "shadow_mode": true}`.
   - Verify next intent returns to shadow path. Confirms 60s turnaround viable.
5. Update CLAUDE.md §十一 one-liner to reflect "ExecutorAgent demo live-wired".

Phase C **does not flip live**. `risk_config_live.toml` stays `shadow_mode=true`. Live flip is a separate decision gated on the full 5-gate chain + operator approval + demo stability ≥21d (per CLAUDE.md §十).

**Git**: no code commit. Single TOML commit optional if operator decides to persist the demo flip (otherwise engine restart re-applies TOML default = safe retreat).

---

## 8. Testing Plan

### 8.1 Unit tests (Rust)

- `rust/openclaw_engine/src/config/risk_config_tests.rs`:
  - `ExecutorConfig::default()` produces safe values.
  - `ExecutorConfig::validate` rejects out-of-range `max_position_pct`.
  - `ExecutorConfig::validate` rejects invalid symbol keys.
  - TOML round-trip (serialize → deserialize → equal).

- `rust/openclaw_engine/src/ipc_server/tests/config.rs` (new tests alongside existing):
  - See §6.5 list (6 tests).

### 8.2 Unit tests (Python)

- `tests/test_executor_config_cache.py`:
  - Initial fetch success caches snapshot.
  - Initial fetch failure → `get_snapshot().shadow_mode == True`.
  - Repeated fetch failures → still safe default + warn-log throttling.
  - Successful refresh atomically swaps (old readers see old value until swap).

- `tests/test_executor_routes.py`:
  - `GET /api/v1/executor/config` returns envelope.
  - `POST /api/v1/executor/shadow_toggle` requires Operator role.
  - `POST /api/v1/executor/shadow_toggle` live engine rejects without authorization.
  - Payload validation (negative `max_position_pct` → 400).

### 8.3 Integration tests

- Python: construct `ExecutorAgent`, seed cache with `shadow_mode=false`, inject a fake Guardian-approved intent, assert that `_execute_via_ipc` calls `paper_trading_routes._ipc_command` (mocked).
- Python: seed cache with `shadow_mode=true`, same intent, assert `_ipc_command` **not** called.
- Rust: spin up ipc_server test harness, issue `patch_executor_config`, issue `get_executor_config`, assert state progression + audit log row.

### 8.4 E2E (manual, Phase C only)

Per §7.3, steps 3–4 constitute the E2E test. Not automated until we have a reliable demo-order-then-rollback harness (future work).

### 8.5 Regression

- Engine lib baseline: 1992 tests (per CLAUDE.md §十一 summary — rolling target). Post-RFC: 1992 + (config tests + IPC tests from §6.5) = expect ~2002-2006. **Zero failed** after all three phases.
- Python test suite: full `pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/` passes.
- `helper_scripts/db/passive_wait_healthcheck.py` green across all 17 checks post-Phase A and post-Phase B.
- No change to `_sqlx_migrations` schema (this RFC is pure config + IPC, no DB migration).

### 8.6 Performance

- IPC `get_executor_config` latency: measure at test harness; expected <1ms (reads ArcSwap snapshot).
- Cache refresh CPU cost: 100ms poller × 4 uvicorn workers × ~1ms per call = 40ms/sec aggregate. Negligible.
- Hot-path overhead in `_execute_via_ipc`: one dict access replaces an attribute read. Sub-microsecond difference.

---

## 9. Risks and Mitigations

### 9.1 Stale cache during flip

- **Scenario**: Operator flips `shadow_mode=false` at time T. Python cache last refreshed at T-90ms. Intent arrives at T+10ms, reads stale `shadow_mode=true`, returns shadow report.
- **Impact**: one tick of intents (worst case ~100ms) sees stale `true`. This is a `true→false` flip direction mis-read, which means a real intent is **swallowed as shadow** rather than forwarded live. **Direction is safe**: principle #6 failure default. The intent was not ready to be live at T because cache not refreshed; one tick later it is.
- **Conversely**, `false→true` flip (retreat): stale `false` for one tick means one real order goes out after operator pressed retreat. **This is the dangerous direction**.
- **Mitigation**:
  - Cache poll cadence 100ms (fast).
  - `ExecutorAgent.on_message` is not a microsecond-critical path; operators pressing retreat expect retreat to propagate in ≤1 second. 100ms cache is conservative.
  - For higher safety on retreat, the FastAPI route `POST /api/v1/executor/shadow_toggle {shadow_mode: true}` can **additionally** invalidate a per-worker in-memory flag immediately (without waiting for cache poll). Out of scope for v1, noted for v2.
  - Rust side (§6.6): `intent_processor` checks `shadow_mode` directly on receiving `SubmitOrder`, so even if Python sends a real submit after retreat, Rust swallows. Defense in depth.

### 9.2 Auth bypass

- **Scenario**: An attacker/buggy agent constructs a `patch_executor_config` RPC directly over the socket, bypassing FastAPI routes.
- **Mitigation**:
  - IPC socket is Unix domain socket in `$OPENCLAW_DATA_DIR`, permission-restricted to engine user. External access requires local-host compromise.
  - `handle_patch_config` audit log captures every call with `source` provenance. Any `source="agent"` on a `shadow_mode=false` patch should alert in the healthcheck (future work; file a follow-up TODO in Phase C commit message).
  - §6.4 auth-check enforces the matrix from §4.4. `source` alone is not enough; Rust cross-checks against `live_reserved` state + authorization.json.

### 9.3 IPC fetch blocks on engine restart

- **Scenario**: Engine restarting (e.g. `--rebuild`), socket unavailable for ~30-60s. Python cache tries to fetch, times out.
- **Mitigation**:
  - Cache poller uses short timeout (~500ms per attempt).
  - On consecutive failures, `get_snapshot().shadow_mode == True` (principle #6).
  - No live orders go out during engine restart window.
  - When engine returns, next poller cycle fetches successfully, snapshot updates.

### 9.4 Config drift between demo and live stores

- **Scenario**: Operator updates demo `max_position_pct` to 0.10, forgets to update live. Live flip later goes out with stale 0.02.
- **Mitigation**:
  - Both stores are independent by design (per-engine config). This is a feature, not a bug.
  - Healthcheck [new] proposal: `check_executor_config_drift` — compare `max_position_pct` across engines, warn if > 3× divergence. File follow-up TODO.

### 9.5 TOML partial-write race

- **Scenario**: Two concurrent `patch_executor_config` calls, each wanting to update different fields. Persistence layer writes TOML; second write overwrites first's half-applied state.
- **Mitigation**: `handle_patch_config` already serializes writes via the `ConfigStore` mutex (existing infrastructure). Patches are transactional per store. Tested by existing `test_rc1_patch_risk_config_bumps_version_and_updates`.

### 9.6 Python worker divergence (uvicorn --workers 4)

- **Scenario**: 4 FastAPI workers, each with its own `executor_config_cache` singleton. Worker A refreshes at T, worker B refreshes at T+50ms. For 50ms, they see different snapshots.
- **Impact**: minimal — `ExecutorAgent` runs once per worker (module-level singleton per process), so inconsistent snapshot across workers means one worker's agent sees stale value. Same `≤100ms` tolerance applies.
- **Mitigation**: None needed for v1. If operator requires strict cross-worker consistency, future option is to centralize the cache into a shared memory segment or switch to a broker-subscribe model (Rust pushes updates via Unix-socket subscribe channel).

### 9.7 Depending on "removal of hardcode" to change behavior — does nothing change at Phase B?

- **Scenario**: Operator deploys Phase B, intents still log shadow, nothing changes — how do we know Phase B actually works?
- **Verification**:
  - Route probe: `GET /api/v1/executor/config` must return `shadow_mode=true version=N`. If version increments, cache is live.
  - Log probe: executor log line should say "reading from cache snapshot v=N" vs old "using class attr _shadow_mode".
  - Synthetic flip in a test env: Phase B rolled out, then in a staging setup flip cache internal state (via `_inject_snapshot_for_tests`) to `false`, verify real IPC submit attempted.
  - Commit includes a log-scraping regression test — run pytest that asserts the new log signature appears.

### 9.8 Rust intent_processor performance regression

- **Scenario**: §6.6 adds a `ConfigStore::load()` call per `SubmitOrder`. Path is currently hot under paper-mode stress tests.
- **Mitigation**: `ConfigStore::load()` is an ArcSwap read — nanosecond cost. Measured in existing benches as <100ns. No regression.

---

## 10. Open Questions

### 10.1 Per-symbol override granularity

Do we need `shadow_mode` at symbol level (e.g., "flip BTC to live but keep ETH in shadow")? Use case: symbol-by-symbol rollout where a single symbol has passed Phase 5 edge re-evaluation but others haven't.

- **Impacts**: adds `shadow_mode_per_symbol: HashMap<String, bool>` with global fallback. Python cache becomes dict-lookup. Complexity +10%.
- **v1 decision**: no. Global only. Revisit when first symbol passes edge gate.

### 10.2 Gradual position ramp

Do we want a first-class "ramp schedule" (e.g., `max_position_pct` follows a scheduled curve over N days) or leave it as repeated manual IPC patches?

- **Arguments for scheduler**: operator-hands-off, avoids "forgot to bump" failure mode.
- **Arguments against**: scheduling logic is strategic, not infrastructural. Belongs in a separate orchestration layer, not in ExecutorConfig.
- **v1 decision**: manual. Operator bumps via IPC. Scheduler is a separate later RFC if needed.

### 10.3 Where does `max_slippage_bps` live?

Current: Python `ExecutorConfig` dataclass (local validation). Candidate: move to Rust `RiskConfig.executor.max_slippage_bps` for hot-reload.

- **Arguments for moving**: consistent "all executor parameters in one place" design. Matches the RFC's stated goal.
- **Arguments for keeping**: `max_slippage_bps` is a local Python-side report flag — it does not gate order submission, only flags reports as "slippage violation" for downstream audit. Pure Python logging concern.
- **v1 decision**: keep in Python. Document in §3.1 as Python-local. Revisit if slippage gating becomes a gate (future: circuit breaker on repeated slippage violations → would need Rust-side enforcement).

### 10.4 Should `patch_executor_config` support `per_symbol_position_cap` delete semantic?

JSON has no "delete this key" built-in. Options:
- Null-value sentinel: `{"BTCUSDT": null}` → delete.
- Explicit array: `{"delete_symbols": ["BTCUSDT"]}` alongside `patch`.
- Full replace: patch always replaces the entire map (loses partial merge benefit).

- **v1 decision**: null-value sentinel. Matches typical JSON patch conventions. Document in §4.2.

### 10.5 GUI surface for executor config

Separate 11-tab page, or inline panel in the existing Live GUI?

- **v1 decision**: out of scope. API routes are sufficient for operator CLI access. GUI integration deferred to a later UI task.

### 10.6 Interaction with `live_reserved` auto-trip

If `live_reserved` mode auto-trips off (session timeout, emergency revoke), does `shadow_mode` auto-revert to `true`?

- **v1 decision**: no automatic coupling. Manual control. But: healthcheck should verify `shadow_mode=true` whenever `live_reserved=false` (cross-gate sanity). File follow-up.

### 10.7 Phase 6 Reconciler interaction

`Phase 6 Reconciler` (CLAUDE.md §五) reconciles orders post-submission. If a Phase C flip happens mid-reconciliation window, does the reconciler see a sudden jump in live orders? Does it need a "shadow→live transition marker" timestamp?

- **v1 decision**: operator-driven flip is intentional + audit-logged. Reconciler already handles sudden state changes (e.g., manual orders). Noted but not a blocker.

---

## 11. References

### 11.1 Audits

- `docs/audits/2026-04-24--todo_refactor_audit.md` — line flagging `_shadow_mode` hardcode.
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md` — G3 work group.

### 11.2 Code paths consulted

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:99-112` — `ExecutorConfig` dataclass shape.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:476-527` — `_execute_via_ipc` shadow branch.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:459-484` — current agent construction.
- `rust/openclaw_engine/src/ipc_server/mod.rs:925-976` — `patch_risk_config` / `get_risk_config` routing (shape template).
- `rust/openclaw_engine/src/ipc_server/tests/config.rs:54-300` — `test_rc1_patch_risk_config_*` test patterns (template for §6.5).
- `rust/openclaw_engine/src/config/risk_config.rs` — `RiskConfig` struct and sub-struct patterns (`ExitConfig` precedent).
- `settings/risk_control_rules/risk_config_paper.toml:160-163` — existing `[exit] shadow_enabled` pattern (EDGE-P2-3 precedent).

### 11.3 Doctrinal references (CLAUDE.md + memory)

- CLAUDE.md §二 principle #3 — AI output ≠ immediate command.
- CLAUDE.md §二 principle #6 — failure default = shrink (retreat).
- CLAUDE.md §四 — 5 live gates.
- CLAUDE.md §七 — Rust authority + cross-platform + audit rules.
- CLAUDE.md §九 — singleton table (new `_EXECUTOR_CONFIG_CACHE` entry needed).
- CLAUDE.md §十 — Wave 1-4 path, Layer 2 gap framing.
- `memory/feedback_rust_authoritative_config.md` — Rust is authoritative.
- `memory/project_layer2_agent_design.md` — the real Layer 2 gap; this RFC unblocks the lowest physical layer.
- `memory/project_5agent_runtime_state.md` — 4552 LOC 5-agent runtime, Executor-is-last-shadow observation.
- `memory/feedback_no_dead_params.md` — "agent-adjustable params must be real" — this RFC is exactly that rule applied to `shadow_mode`.

### 11.4 Precedent patterns (for implementation guidance)

- **`ExitConfig.shadow_enabled`** (EDGE-P2-3) — same shape: TOML + IPC hot-reload + env default + Rust-side check. Copy the pattern.
- **`patch_risk_config` IPC contract** — exact mirror for `patch_executor_config`. Auth check, persistence, audit, validate.
- **`edge_estimator_scheduler.py` flock pattern** — *not* used here. Cache is read-mostly; multiple uvicorn workers each have their own poller, no leader election needed.

---

## 12. Implementation Order for G3-02 (Next Session)

Recommended sequencing for whoever picks up Phase A implementation:

1. Read this RFC top-to-bottom.
2. Read `ExitConfig` (EDGE-P2-3) in `rust/openclaw_engine/src/config/risk_config.rs` as the structural template.
3. Read `test_rc1_patch_risk_config_*` tests in `rust/openclaw_engine/src/ipc_server/tests/config.rs` as the integration-test template.
4. Implement §6.1 + §6.2 (config struct + unit tests). Commit.
5. Implement §6.3 + §6.4 + §6.5 (IPC handlers + auth + integration tests). Commit.
6. Implement §6.6 (intent_processor check). Commit.
7. Implement §6.7 + §6.8 (TOML + io.rs). Commit.
8. Run engine_lib tests → expect 1992 + N passes. 0 fails.
9. `--rebuild` on Linux, verify IPC round-trip manually.
10. Open G3-03 PR for Phase B.

End-state after Phase A deploy: runtime behavior identical to pre-RFC. Rust is ready for Phase B.

---

**End of RFC.** This document is a design artifact; no code was written or executed.
