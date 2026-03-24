# I Canonical Runner Baseline (2026-03-24)

## Purpose / 用途

This document defines the current canonical runner baseline for the decision-lease I chapter.
本文定义当前 decision-lease I 章节的规范 runner 基线。

## Canonical runners / 规范 runner

- `run_i1_decision_lease_full_closure.sh`
- `run_i2_decision_lease_shadow_closure.sh`
- `run_i3_decision_lease_consume_closure.sh`
- `run_i4_decision_lease_replay_closure.sh`
- `run_i5_decision_lease_friction_closure.sh`
- `run_i10_canonical_decision_lease_recheck.sh`

## Rule / 规则

These runners should use:
这些 runner 应统一使用：

1. repo-local `ROOT`
2. canonical `PYTHONPATH`
3. canonical implementation under:
   `program_code/trade_executor/bybit_decision_lease/`

Legacy absolute-path entry styles should not be used for new runner maintenance.
后续不应继续把旧式 absolute-path 入口当作新维护基线。

## Current accepted semantics / 当前接受语义

The I chapter is closed as a shadow-only control plane.
I 章节目前是以 shadow-only control plane 闭环。

This does **not** mean:
这 **不** 代表：

- live execution approved
- execution authority granted
- decision lease emitted

It means only:
它只代表：

- I1-I10 close coherently
- runtime remains protected
- future live design may use this chapter as a safe baseline
