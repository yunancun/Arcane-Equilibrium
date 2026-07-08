---
name: new-code-should-be-rust-first
description: "New independent modules in Rust (standalone engine binary reached over IPC), existing file modifications stay Python — confirmed 2026-04-03"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b8f94432-3891-440a-ba13-f17896dd26d5
---

New independent modules must be written in Rust. Modifications to existing Python files stay in Python.

**Why:** The project has a planned Rust migration. Writing new Python modules creates more migration debt. User confirmed Option C on 2026-04-03: existing strategy upgrades (modifying existing files) stay Python, but new standalone modules use Rust. (Matches CLAUDE.md Rust-first rule.)

**How to apply:**
- New standalone modules (computation, distillers, engines, risk) → Rust (e.g. ContextDistiller was rewritten from Python to Rust)
- Modifications to existing Python strategy files → Python (e.g. MA_Crossover V2 stays Python)
- Rust workspace: `Cargo.toml` at repo root, `rust/openclaw_engine/` crate
- The Rust engine is a **standalone binary** — Python reaches it over IPC (Unix socket), NOT as a Python extension module (no in-process import)
- Only write Python for: (1) thin wrappers / IPC bridges, (2) modifications to existing files, (3) GUI/API routes

**Confirmed by:** User chose Option C on 2026-04-03 session

> 2026-07-09 校正：PyO3 已於 2026-04-20（PYO3-ELIMINATE-1 Phase 3, `9b691a0`）全數移除；不再有 `maturin develop --release` 或 `import openclaw_core`；Rust engine 是 standalone binary，Python 經 IPC（Unix socket）連接。
