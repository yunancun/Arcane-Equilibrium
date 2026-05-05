---
status: accepted
---

# LiveDemo runs the Live pipeline against Bybit demo endpoint with Live-grade gating

When the Bybit endpoint slot points at `api-demo.bybit.com`, the engine runs `BybitEnvironment::LiveDemo` — the full Live pipeline (SM-01 Authorization, EarnedTrust TTL, signed `authorization.json` HMAC verification, every risk gate) — against play-money. The only LiveDemo-vs-Mainnet difference is the `OPENCLAW_ALLOW_MAINNET=1` env requirement; all other gates are byte-identical.

## Considered alternatives

A "relaxed LiveDemo" tier (skip TTL, skip signing, looser cost gate) was rejected: LiveDemo is the only online surface to exercise live code paths before real capital flows; degrading it would leave Mainnet promotion as the first time those gates ever execute.
