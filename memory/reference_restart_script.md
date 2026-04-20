---
name: Restart Script Location
description: helper_scripts/restart_all.sh — one-command restart for Rust engine + API server, use this instead of writing restart commands manually
type: reference
---

Engine + API restart script: `bash helper_scripts/restart_all.sh`

Options:
- `bash helper_scripts/restart_all.sh` — restart both engine + API (4 workers)
- `bash helper_scripts/restart_all.sh --engine-only` — only Rust engine
- `bash helper_scripts/restart_all.sh --api-only` — only API server

Auto-verifies: engine health + ticks + paused state after startup.
