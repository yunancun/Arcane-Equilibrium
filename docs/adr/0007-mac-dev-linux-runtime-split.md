---
status: accepted
---

# macOS is the development environment; Linux is the only runtime

Engine binary, Python uvicorn, PostgreSQL, and watchdog only run on the Linux trade-core box (128 GB unified-memory AMD/AI-MAX-class hardware). Macs are restricted to read/write code, RCA, design, and unit tests that do not touch DB / socket. On Mac, `engine_alive=false` and a missing `pipeline_snapshot.json` are expected — never a bug; Mac CC must SSH into trade-core to inspect runtime state.

## Consequences

Apple Silicon Mac (M5 Ultra/Max class) remains a long-term deployment target, so cross-platform discipline is enforced now: no `/home/ncyu` or `/Users/<name>` literals in code; `aarch64-apple-darwin` must remain in CI tuple choices; LLM model paths must be abstracted, not hard-coded.
