---
status: accepted
---

# Paper / demo / live engines coexist, each with its own TOML risk config

The Rust engine spawns three pipelines (`PipelineKind::Paper`, `Demo`, `Live`) with three deliberately divergent risk-control TOML files (`risk_config_{paper,live,demo}.toml`). Numerical disagreement between them (e.g. `trailing_activation_pct` paper=0.5 / demo=0.8 / live=0.5) is intentional and reflects three different risk philosophies — paper for synthetic-fill exploration coverage, demo for live-equivalent behavior validation against Bybit demo API, live mainnet for maximum conservatism.

## Consequences

Any "hygiene" PR that unifies the three to a common default must be rejected; keep the three files independent even when values incidentally agree.
