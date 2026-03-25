# OpenClaw / Bybit Control API V1 - Known Issues and Next Fixes

## 2026-03-26 local validation finding

在本地验证中，已经确认 API 与 GUI 可以启动、鉴权、返回 overview，并能完成 `demo_validate` 与 `manual-note` 写入。

但是同时发现一个需要优先修复的审计一致性问题：

- 当前 `snapshot_ts_ms` 与 `snapshot_id` 在纯读取路径上会发生变化。
- 这意味着相同 `state_revision` 下，不同 GET 读取可能返回不同 `snapshot_id`。
- 对于严格审计与幂等追踪，这个行为不合格，必须修正。

## Why this matters

对于 OpenClaw / Bybit 这种高审计要求场景：

- 纯读取不应改变状态文件
- 同一 revision 的 snapshot identity 应稳定
- snapshot identity 只能在真实写入后变化

## Required fix direction

1. `compile_state()` 需要区分：
   - read-only compile
   - write-time compile

2. `JsonStateStore.read()` 不得刷新 `snapshot_ts_ms`

3. `JsonStateStore.mutate()` 应只在真实写入成功后生成新的 snapshot

4. 新增测试：
   - 连续两次 GET overview，`state_revision` 相同且 `snapshot_id` 不变
   - config-change 后 `state_revision` 增加且 `snapshot_id` 变化

## Current deployment status

当前版本可作为：

- GUI / API 路由骨架验证
- 鉴权验证
- 本地交互 MVP

但在完成 snapshot 稳定性修复前，**不应视为审计严格可接受版本**。
