# V083 halt_session entry_context_id Fix

**Date**: 2026-05-12
**Role**: PM local source/test fix
**Verdict**: SOURCE/TEST CLOSED; RUNTIME DEPLOY PENDING

## Task Summary

接手 TODO 後按 repo boot / runtime 三連核查，發現 Linux `trade-core` runtime 與 TODO/CLAUDE 狀態 drift：
- Mac / origin / Linux repo HEAD 均為 `0fb661d3`。
- Mac worktree 既有 46 個 Rust dirty files，與本修復無關，未吸收。
- Linux watchdog：`demo` fresh；`paper/live` stale；`live` pipeline boot 被拒，原因為 signed authorization file missing。
- Linux `engine.log`：`risk_close:halt_session` close fill 缺 `entry_context_id`，`trading.fills` 每 2s 撞 `chk_fills_close_has_entry_context_id_v083` 並保留 buffer 重試。

## Root Cause

5/11 的 V083 producer-side fix 已在 `commands.rs` close paths 引入 `resolve_close_entry_context_id()`，但 `step_6_risk_checks.rs` HaltSession loop 仍直接使用：

```rust
paper_state.get_entry_context_id(sym).unwrap_or("").to_string()
```

重啟後或 orphan-adopted positions 沒有 in-memory entry id，該路徑會產生空 `entry_context_id`，被 V083 CHECK 拒絕。

## Changes

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`
  - HaltSession close loop 改走 `resolve_close_entry_context_id(sym, event.ts_ms)`。
- `rust/openclaw_engine/src/tick_pipeline/tests/per_symbol_price_pnl.rs`
  - 既有 halt-session price regression 新增 close fill `entry_context_id` 非空斷言，允許真 `ctx-*` 或 synthetic `orphan_recovery_ctx:*`。
- `TODO.md`
  - 新增 `P1-V083-HALT-SESSION-CTX`，標記 source/test closed、runtime deploy pending。
- `docs/CLAUDE_CHANGELOG.md` / PM memory
  - 記錄 runtime evidence、source fix、verification、未 deploy 邊界。

## Verification

- `cargo test -q -p openclaw_engine test_halt_session_uses_per_symbol_price_not_triggering_tick` PASS。
- `rg 'get_entry_context_id\([^)]*\).*unwrap_or\("")' rust/openclaw_engine/src/tick_pipeline` 0 hit。
- `git diff --check -- rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs rust/openclaw_engine/src/tick_pipeline/tests/per_symbol_price_pnl.rs` PASS。

## Boundaries

- No rebuild / restart / deploy.
- No live auth mutation.
- No risk / strategy parameter change.
- Existing Mac dirty Rust WIP was left intact.

## Runtime Follow-up

After operator-approved rebuild/restart:
- verify `engine.log` has no new `chk_fills_close_has_entry_context_id_v083`;
- verify watchdog stays fresh beyond 30 minutes;
- renew LiveDemo auth only if operator wants LiveDemo pipeline active again.
