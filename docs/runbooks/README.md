# Runbooks

> **REFERENCE ONLY**
>
> 本目录保存操作手册和故障处置 SOP。它不是 active approval，也不是当前
> operator action 清单。执行任何运行态操作前，先读根目录 `TODO.md` §6
> Operator actions，并确认最新 PM/role report。

## 入口

| 场景 | 先读 |
|---|---|
| 凭证 / key rotation | `credential_rotation.md`, `replay_signing_key_rotation.md` |
| DB restore / 演练 | `pg_restore_drill_sop.md` |
| Replay / REF-21 操作 | `ref21_replay_operator_runbook.md`, `2026-05-21--counterfactual_quality_report_runbook.md` |
| Cost Gate demo-learning lane activation | `2026-06-21--cost_gate_learning_lane_runtime_activation.md`（installer apply path now enforces read-only expected-head activation preflight by default） |
| Earn / 资金移动 | `2026-05-21--earn_governance_runbook.md` |
| M-series 运维 | `2026-05-21--m*_runbook.md` |
| OPS / trust first use | `2026-05-28--ops_1_cert_trust_first_use.md` |
| LG-1 H0 flip 回滾 | `2026-05-11--lg1_h0_flip_rollback.md` |
| LG-2 pricing assertion 失敗 | `2026-05-11--lg2_pricing_assertion_failure.md` |

## 使用规则

- Runbook 可以告诉你怎么做，不能单独授权你现在就做。
- 涉及 deploy、auth、DB、risk、trading、live/demo 操作时，必须回到 `TODO.md`
  和最新 PM/Operator 报告确认 gate。
- 旧 runbook 保留历史上下文；若和 `CLAUDE.md` / `.codex/MEMORY.md` / `TODO.md`
  冲突，以当前权威文件为准。
