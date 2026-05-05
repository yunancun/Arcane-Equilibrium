---
status: accepted
date: 2026-04-07
---

# Rust openclaw_engine is the sole trading authority; Python is a bridge

All trading decisions, risk control, strategy execution, and live order submission live in `rust/openclaw_engine` (the paper / demo / live three-mode binary). Python is restricted to API/GUI bridging, IPC read-only state proxying, and learning-plane analysis — it must not hold writable trading state or invoke `update_*` IPCs except as a thin GUI forwarder. We chose this in 2026-04-07 to end a dual-system divergence between Python risk and Rust risk that was producing race conditions, audit ambiguity, and silent semantic drift; finalized by DEAD-PY-2 (2026-04-11) which removed ~4500 lines of Python trading logic.
