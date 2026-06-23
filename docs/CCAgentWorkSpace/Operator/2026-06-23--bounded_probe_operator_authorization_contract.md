# Operator Note: Bounded Probe Operator Authorization Contract

日期：2026-06-23
Checkpoint：`545564d7`

已完成 source/test/docs + Mac/origin/Linux 三端同步。這輪沒有授權或提交任何 demo 訂單。

核心變更：

- future `DEMO_LEARNING_PROBE_GRANTED` 不能再單獨放行。
- admission 必須同時看到 `bounded_demo_probe_operator_authorization_v1`。
- 該 authorization 必須匹配 side-cell、未過期、含 operator/authorization id、probe-order budget、authority-path readiness、`main_cost_gate_adjustment=NONE`、`promotion_evidence=false`。
- 缺失或不匹配時返回 `OPERATOR_AUTHORIZATION_INVALID`。

這使下一步 operator 可以審核一個非常窄的 bounded Demo probe authorization，而不是全局 lower Cost Gate。

已驗證：

- Mac policy suite：71 passed
- Mac Rust `demo_learning_lane`：23 passed
- Mac Rust `bounded_probe_near_touch`：9 passed
- Linux policy suite：71 passed
- Linux Rust `demo_learning_lane`：23 passed

盈利路徑仍是：side-cell/horizon alpha candidate -> bounded Demo probe authorization -> near-touch-or-skip fill-backed data -> matched blocked controls -> result/execution-realism review -> 再決定是否調整 Cost Gate。

邊界：no CI, no PG, no Bybit, no deploy/restart, no cron/env/auth/risk/order mutation, no active probe/order authority, no Cost Gate lowering, no promotion proof.
