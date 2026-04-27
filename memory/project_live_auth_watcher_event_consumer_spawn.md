---
name: LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN fix (2026-04-27)
description: Live engine 8天 snapshot 停寫 RCA + fix — watcher respawn path 漏接 event_consumer spawn
type: project
originSessionId: b734f2c9-48f0-4c0f-a396-b5c00a0425a6
---
2026-04-27 P0 silent regression 修復完成，merge commit `1fac9b1`，engineering log `docs/worklogs/2026-04-27--live_auth_watcher_event_consumer_spawn_fix.md`。

**Why:** manual restart 清除 authorization.json（安全設計）→ boot 走 `(None,None)→None` → `spawn_live_pipeline` 未被呼叫 → `event_consumer` 不存在 → snapshot/state/ML writers 8 天靜默 dead。watcher respawn 只跑 `build_exchange_pipeline` 3 task，從未呼叫 `spawn_live_pipeline`。

**How to apply:** 修復後 operator 每次 `POST /api/v1/live/auth/renew` → watcher respawn path 正確呼叫 `spawn_live_pipeline`（`has_pipeline_spawner=true` 可驗）→ event_consumer 正常 spawn。

**Open TODO:**
- [P1] LIVE-RECONCILER-STALE-CMD-TX：watcher teardown+respawn 後 reconciler/scheduler stale cmd_tx，Live 5min 縮倉輪詢失效
- [WARN] main.rs 1194 行，§九 6 行 margin，下次 touch 必拆
- 8 天 Live ML 資料空白無法回填
