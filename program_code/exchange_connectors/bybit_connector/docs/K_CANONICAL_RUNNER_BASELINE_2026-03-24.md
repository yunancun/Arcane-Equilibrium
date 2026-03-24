# K Canonical Runner Baseline (2026-03-24)

## Purpose / 用途

This document defines the current canonical runner baseline for the K chapter.
本文定义当前 K 章节的规范 runner 基线。

K chapter meaning:
- `K. Paper / Demo Gate`
- current accepted closure shape = **design-only gate closed**

K 章节当前含义：
- `K. Paper / Demo Gate`
- 当前接受的闭环形态 = **设计层闭环且 gate 关闭**

## Canonical runner / 规范 runner

- `run_k10_canonical_demo_gate_recheck.sh`

## Current authoritative coverage / 当前权威覆盖范围

The K10 canonical recheck should read and summarize these latest artifacts:
K10 规范复查应读取并汇总以下 latest 产物：

- demo gate contract
- demo gate readiness
- demo paper adapter skeleton
- paper order lifecycle skeleton
- paper position / balance projection skeleton
- pretrade risk integration skeleton
- demo gate summary
- demo gate handoff
- demo gate final audit
- demo gate chapter consistency
- main runtime safety state

## Rule / 规则

The canonical K runner should:
规范 K runner 应：

1. use repo-local `ROOT`
2. read runtime artifacts from `docker_projects/trading_services/runtime/bybit/demo_gate/`
3. treat K closure as **design-only closed**, not execution-ready
4. preserve current runtime safety interpretation:
   - `system_mode = read_only`
   - `execution_state = disabled`

## Accepted semantics / 当前接受语义

K closed means:
K 闭环代表：

- design layers are defined coherently
- summary / handoff / final audit / chapter consistency align
- gate remains closed by design
- runtime remains protected

K closed does **not** mean:
K 闭环 **不** 代表：

- paper trading enabled
- operator may open execution now
- live execution approved
- any real-order authority granted

## Compatibility caution / 兼容性注意

Current runtime JSON still preserves many historical `G5.x` stage markers.
当前 runtime JSON 仍保留大量历史 `G5.x` stage 标记。

Do not mass-rename those stage fields during closure confirmation work.
在当前闭环确认工作中，不要贸然批量改这些 stage 字段。

Stage canonicalization should be treated as a later compatibility topic.
stage 规范化应视为后续兼容性专题。