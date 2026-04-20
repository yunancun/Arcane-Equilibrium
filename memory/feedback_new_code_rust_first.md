---
name: New code should be Rust-first
description: New independent modules in Rust+PyO3, existing file modifications stay Python — confirmed 2026-04-03
type: feedback
---

New independent modules must be written in Rust+PyO3. Modifications to existing Python files stay in Python.

**Why:** The project has a planned Rust migration (Phase R, 14 weeks). Writing new Python modules creates more migration debt. User confirmed Option C on 2026-04-03: existing strategy upgrades (modifying existing files) stay Python, but new standalone modules use Rust.

**How to apply:**
- New standalone modules (computation, distillers, engines) → Rust+PyO3 (e.g. ContextDistiller was rewritten from Python to Rust)
- Modifications to existing Python strategy files → Python (e.g. MA_Crossover V2 stays Python)
- Rust workspace already set up: `Cargo.toml` at repo root, `rust/openclaw_core/` crate with maturin
- Build: `cd rust/openclaw_core && maturin develop --release`
- Import: `import openclaw_core` from Python
- Only write Python for: (1) thin wrappers, (2) modifications to existing files, (3) GUI/API routes

**Confirmed by:** User chose Option C on 2026-04-03 session
