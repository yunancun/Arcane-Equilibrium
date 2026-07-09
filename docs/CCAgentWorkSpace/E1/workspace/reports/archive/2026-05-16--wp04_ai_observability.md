# E1 Report: WP-04 AI Observability + Budget Fixes

Date: 2026-05-16
Task: AI-E audit findings F-04 / F-01 / F-09
Status: IMPL DONE, awaiting E2 review

## 1. Task Summary

Three AI observability/budget findings from the 12-agent AI-E audit:

- **F-04**: `_handle_strategist()` in `ai_service_dispatch.py` did not record AI
  invocations after calling Ollama. Other agent handlers (analyst, guardian,
  strategist_edge_eval) call `_record_ai_invocation()` via BaseAgent, making
  strategist IPC handler costs invisible in the budget dashboard.

- **F-01**: `daily_usd_max = 100.0` in both `budget_config.toml` files was 50x
  the DOC-08 S12 documented $2/day budget for L0+L1 tier. Placeholder value
  never tightened.

- **F-09**: `"model_tier": "l1_9b"` hardcoded in Rust `evaluate.rs` should be
  configurable via TOML. Minimal fix: TODO comment (full extraction requires
  Rust struct changes + rebuild, deferred to avoid scope creep).

## 2. Changes

| File | Change |
|---|---|
| `ai_service_dispatch.py` | Added `import hashlib`; new `_record_strategist_invocation()` static method; 3 call sites (success / ollama_error / exception) + `t0 = time.monotonic()` timer |
| `budget_config.toml` (root) | `daily_usd_max` 100.0 -> 2.0; `monthly_usd_max` 150.0 -> 60.0; added DOC-08 S12 comment |
| `settings/risk_control_rules/budget_config.toml` | Same budget changes as root |
| `rust/.../evaluate.rs` | Added `// TODO(WP-04)` comment on hardcoded `"l1_9b"` |

## 3. Key Diff

### F-04: ai_service_dispatch.py

New static method `_record_strategist_invocation()` calls
`agent_event_store.get_agent_event_store().record_ai_invocation()` directly
(AIService is NOT a BaseAgent subclass, so cannot use `self._record_ai_invocation()`).
Fail-soft: exception in recording does not affect IPC response.

Three call sites:
1. After successful `ollama.generate()` response (success=True)
2. After `response.success == False` (success=False)
3. In the `except Exception` handler (success=False)

### F-01: budget_config.toml (both)

```toml
# DOC-08 S12 L0+L1
daily_usd_max = 2.0
monthly_usd_max = 60.0   # 30d x $2
```

### F-09: evaluate.rs

```rust
// TODO(WP-04): l1_9b -> [strategist] TOML config
"model_tier": "l1_9b",
```

## 4. Governance Alignment

- Comments in Chinese only (2026-05-05 governance)
- Both budget_config.toml files are git-tracked (verified via `git ls-files`)
- `ai_service_dispatch.py` line count: 768 -> 836 (above 800 warning, below 2000 hard cap)
- No business logic changes; recording is fail-soft observability
- Rust change is comment-only, no rebuild required

## 5. Uncertainties

- `exhaustion_cooldown_minutes = 60` in both budget files left unchanged (not
  mentioned in finding; proportional adjustment not requested).
- Ollama calls are local (cost_usd=0.0), so the budget impact is on invocation
  tracking/visibility rather than USD spend. The value was still wrong as a
  config safety net.
- F-09 full TOML extraction deferred per task instructions (no new config infra
  from scratch). The `[strategist]` section already exists in risk_config_*.toml
  with `max_param_delta_pct` but adding `model_tier` requires Rust struct +
  serde changes.

## 6. Next Steps (for E2/operator)

- E2: review the 3 call sites in `_handle_strategist` for correct placement
- E2: verify `agent_event_store.get_agent_event_store()` is safe to call from
  async context (it is -- the singleton uses `threading.Lock`, and the call is
  synchronous within the already-synchronous `_record_strategist_invocation`)
- E4: regression test for strategist IPC dispatch
- Operator: after deploy, verify `agent.ai_invocations` table shows
  `purpose='strategist_evaluate_ipc'` rows
