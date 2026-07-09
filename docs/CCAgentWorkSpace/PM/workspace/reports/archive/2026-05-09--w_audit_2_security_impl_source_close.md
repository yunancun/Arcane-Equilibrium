# W-AUDIT-2 Security IMPL Source Close

Date: 2026-05-09

## Scope

- Closed `W-AUDIT-2` / `P1-AUDIT-SEC-2` as a source/test checkpoint.
- No rebuild, restart, runtime env flip, live auth mutation, scanner authority,
  Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or
  true-live API action was performed.

## Closed Items

- F-24: Phase4 weekly review approve/reject now require an authenticated actor
  with operator role and `learning:manage`; audit `approved_by` uses
  `base.audit_actor_id(actor)` rather than trusting request payload identity.
- F-25: Scout market-signal and event-alert writes now require operator role and
  `learning:write`.
- F-mid-A: Layer2 manual trigger now requires operator role and
  `ai_budget:write`.
- F-mid-A: `AIServiceListener` chmods its Unix socket to `0600` after bind and
  fails closed if chmod fails.
- F-23: `restart_all.sh`, `clean_restart.sh`, and `fresh_start.sh` default API
  bind host to `${OPENCLAW_BIND_HOST:-127.0.0.1}`; deploy docs now prefer
  loopback + Tailscale Serve / reverse proxy, with explicit Tailscale-IP bind as
  the direct-listen option.
- F-03: Rust boot now starts `spawn_lease_transition_pipeline` and injects the
  shared lease transition sender into Paper/Demo/Live
  `GovernanceCore::set_lease_transition_tx`.

## Verification

- `python3 -m py_compile` on modified Python app and test files: PASS
- `python3 -m pytest .../test_batch_e_runtime_ownership.py -q`: 14 passed
- `python3 -m pytest .../test_phase4_routes.py -q`: 29 passed
- `python3 -m pytest .../test_scout_integration.py .../test_scout_audit_wiring.py -q`: 46 passed
- `python3 -m pytest .../test_layer2.py::TestLayer2Routes -q`: 12 passed
- `python3 -m pytest .../test_layer2.py::TestLayer2Routes::test_trigger_session_budget_exceeded -q`: 1 passed
- `cargo check -p openclaw_engine --bin openclaw-engine`: PASS with pre-existing unused warnings
- `cargo test -p openclaw_engine --lib database::lease_transition_writer -q`: 6 passed
- `git diff --check`: PASS

Residual: full `test_layer2.py` still has 5 Layer2Engine failures from local
Anthropic/local-LLM availability and an older `_model_upgrade_triage` signature
expectation. The W-AUDIT-2 route-auth failure in that file is fixed by the
route-class and targeted trigger tests above.

## Next

- `W-AUDIT-3` is next. Its F-15 lease flip -> writer -> DB row e2e regression
  is now unblocked by W-AUDIT-2 F-03.
- F-01 Executor fake-live lambda removal still depends on
  `P0-DECISION-AUDIT-2` operator decision.
