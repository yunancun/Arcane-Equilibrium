# Domain Docs

This repo is single-context.

Before using `diagnose`, `tdd`, `improve-codebase-architecture`, `to-prd`, `to-issues`, or `triage`, read:

- `CONTEXT.md`
- relevant accepted ADRs in `docs/adr/`
- `CLAUDE.md`
- `TODO.md`

## Use the glossary's vocabulary

When output names a domain concept, use the term defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.

Current durable examples:

- Use `Arcane Equilibrium` in English-only contexts, and `玄衡 · Arcane Equilibrium` where the full product name is appropriate.
- Use `OpenClaw` only for the control-plane service family, such as OpenClaw Control Console or OpenClaw Gateway.
- Use `Bybit` only for the exchange venue and connector context.
- Treat `LiveDemo` as live-grade control flow against the Bybit demo endpoint, not as a relaxed live mode.
- Treat Rust `openclaw_engine` as the trading, risk, config, and execution authority.

## Check ADRs

Read the ADRs relevant to the area being changed. At minimum, keep these recent project-wide ADRs in mind:

- `docs/adr/0013-openclaw-gateway-not-trading-conductor.md`
- `docs/adr/0014-arcane-equilibrium-soft-rename.md`

If output contradicts an accepted ADR, surface the conflict explicitly instead of silently overriding it.
