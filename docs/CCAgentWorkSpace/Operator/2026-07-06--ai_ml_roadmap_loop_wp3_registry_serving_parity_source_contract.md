# 2026-07-06 AI/ML Roadmap Loop - WP3 Registry Serving Parity Source Contract

This continuous-loop round selected
`WP3-REGISTRY-SERVING-PARITY-SOURCE-CONTRACT`.

Reason: WP2 PIT dataset manifest was green, and registry/advisory serving
metadata needed a machine-checkable source contract before advisory DreamEngine
or serving-parity work can proceed.

Completed:

- Added `registry_serving_contract_v1`.
- Contract requires advisory-only mode, `not_authority=true`,
  `symlink_authority=false`, and `promotion_serving_ready=false`.
- Contract binds PIT dataset, feature/label/split/leakage/serving hashes,
  policies, q10/q50/q90 artifact hashes, and q10/q50/q90 registry trio fields.
- Python registry verifies local ONNX artifact sha256 values before DB
  registration is attempted.
- Rust registry rejects row artifact hashes that do not match the resolved
  quantile contract hash.
- Rust and FastAPI capabilities keep direct `reload_edge_predictor=false` until
  registry-authorized serving integration exists.

Dispatch result:

- PA design: ready with concerns.
- E1/E1a implementation: PASS after remediation.
- E2 final: PASS.
- E4 final: PASS.
- QA final: ACCEPT_WITH_CONCERNS.

Verification:

- py_compile PASS.
- focused Python tests: `58 passed`.
- expanded ML source-contract tests: `106 passed, 13 skipped`.
- Rust registry tests: `25 passed`.
- Rust reload tests: `4 passed`.
- Rust capability test: `1 passed`.
- rustfmt check PASS.
- `git diff --check` PASS.

State:

- `ADVANCED_WITH_CONCERNS`
- next work: `WP4-ADVISORY-DREAMENGINE-ROLE-HARDENING`

Machine-readable artifacts:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.work_item.json`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.effect_review.json`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.state_packet.json`

PM report:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.md`

Boundary: no runtime mutation, DB read/write, exchange/private read, MCP server,
secret access, order/probe, Cost Gate change, deploy, live, or mainnet action.

Residuals: no promotion-serving readiness; no authorized runtime reload; no
transactional rollback for partial trio persistence; stale nearby comments can
be cleaned later.
