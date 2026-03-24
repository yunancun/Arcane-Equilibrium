# OpenClaw / Bybit Top-Level Index (2026-03-25)

## Purpose / 用途

This document is the top-level navigation index for the current OpenClaw / Bybit engineering state after the concentrated J/K closeout completed on 2026-03-25.
本文是 OpenClaw / Bybit 项目在 2026-03-25 完成 J/K 集中收口后的顶层导航索引。

Its goals are:
它的目标是：

1. provide one accurate entry point for future handoffs
2. reduce confusion between old reports and current verified truth
3. show exactly which documents, scripts, builders, and runtime artifacts matter now
4. prevent future readers from misreading “chapter closed” as “execution authority granted”

1. 为后续接手提供一个准确入口
2. 减少旧报告与当前真相混淆
3. 明确指出当前真正重要的文档、脚本、builder 与 runtime 产物
4. 防止后续读者把“章节收口完成”误读成“执行权限已授予”

---

## Highest-priority truth order / 最高优先级真相顺序

When documents conflict, use this order:
当文档冲突时，应按以下顺序判断：

### Priority 1 / 第一优先级
- shell outputs verified in the 2026-03-24 night → 2026-03-25 early-morning round
- the latest runtime closeout artifacts produced in that round
- current `git status` / `git log` on `main`
- the 2026-03-25 work report and functional closeout baselines

- 2026-03-24 晚至 2026-03-25 凌晨本轮 shell 实测输出
- 本轮实际生成的 runtime closeout latest 产物
- `main` 分支当前 `git status` / `git log`
- 2026-03-25 的 work report 与 functional closeout baseline

### Priority 2 / 第二优先级
- 2026-03-24 canonical runner baselines and chapter closure baselines
- repo-local runner scripts and builder scripts already committed on main

- 2026-03-24 的 canonical runner baseline 与 chapter closure baseline
- 已进入 main 的 repo 内 runner / builder 程序

### Priority 3 / 第三优先级
- older total reports / older handoff summaries / older broad historical notes

- 更早的总报告 / 接手摘要 / 历史背景文件

Important note:
重要说明：

Older files still have background value, but they must not override the verified J/K closeout results from 2026-03-25.
旧文件仍有背景价值，但不得覆盖 2026-03-25 已验证通过的 J/K 收口结果。

---

## Current authoritative chapter status / 当前权威章节状态

### H chapter / H 章
- already closed earlier in the project
- legal no-call semantics are accepted
- not execution authority

- 已在更早阶段闭环
- legal no-call 语义已被接受
- 不是 execution authority

### I chapter / I 章
- **canonical closed**
- correct interpretation = **shadow-only decision-lease control plane closed**
- **not** live-execution ready
- I5 legal no-call misclassification bug had already been fixed before this round

- **canonical closed**
- 正确解释 = **shadow-only decision-lease control plane closed**
- **不是** live-execution ready
- I5 legal no-call 误判 bug 在本轮前已经修复

### J chapter / J 章
- **functionally closed for this round**
- strict interpretation = **functional_closeout_ready_shadow_only**
- still **shadow / skeleton-only**
- execution remains closed

- **本轮已完成功能收口**
- 严格解释 = **functional_closeout_ready_shadow_only**
- 仍然是 **shadow / skeleton-only**
- execution 仍关闭

### K chapter / K 章
- **functionally closed for this round**
- strict interpretation = **functional_closeout_ready_design_only_gate_closed**
- still **design-only gate closed**
- paper/live execution remain closed

- **本轮已完成功能收口**
- 严格解释 = **functional_closeout_ready_design_only_gate_closed**
- 仍然是 **design-only gate closed**
- paper/live execution 仍关闭

---

## Global runtime boundary / 全局 runtime 边界

At the current stage, the main runtime must still be interpreted as:
当前阶段主 runtime 必须仍解释为：

- `system_mode = read_only`
- `execution_state = disabled`

Therefore, the following are still forbidden interpretations:
因此，以下解释仍然是禁止的：

- “J is done, so execution is open”
- “K is done, so demo gate may open now”
- “K capability chains are green, so paper execution is ready”
- “closeout_ready = true means authority granted”

- “J 做完了，所以 execution 打开了”
- “K 做完了，所以 demo gate 现在可以开了”
- “K capability 链都绿了，所以 paper execution ready 了”
- “closeout_ready = true 就等于 authority granted”

---

## Fastest recommended reading order / 最快推荐阅读顺序

If a new maintainer only has limited time, read in this order:
如果新的维护者时间有限，建议按以下顺序阅读：

### Step 1 / 第一步：最新总口径
- `program_code/exchange_connectors/bybit_connector/docs/WORK_REPORT_2026-03-25_JK_FUNCTIONAL_CLOSEOUT.md`

Why:
因为：
- this is the newest integrated engineering report for the J/K closeout round
- it explains what happened, what changed, and what the final meaning is

- 这是最新的 J/K 收口整合工程记录
- 它解释了本轮做了什么、改了什么、最终该怎么解释

### Step 2 / 第二步：章节级功能收口基线
- `program_code/exchange_connectors/bybit_connector/docs/J_FUNCTIONAL_CLOSEOUT_BASELINE_2026-03-25.md`
- `program_code/exchange_connectors/bybit_connector/docs/K_FUNCTIONAL_CLOSEOUT_BASELINE_2026-03-25.md`

Why:
因为：
- these two files define the authoritative closeout meaning for each chapter
- they are the best place to check “what does done mean here?”

- 这两份文件定义了每个章节当前权威的收口含义
- 它们是检查“这里的做完到底是什么意思”的最佳入口

### Step 3 / 第三步：阶段总基线
- `program_code/exchange_connectors/bybit_connector/docs/JK_STAGE_STATUS_BASELINE_2026-03-25.md`

Why:
因为：
- this file compresses J/K into one stage-level view
- it is ideal when the question is “where exactly are we now?”

- 这份文件把 J/K 压缩成一个阶段总视图
- 当问题是“我们现在到底在哪一阶段”时，它最合适

### Step 4 / 第四步：旧 canonical baseline
- `program_code/exchange_connectors/bybit_connector/docs/J_CANONICAL_RUNNER_BASELINE_2026-03-24.md`
- `program_code/exchange_connectors/bybit_connector/docs/J_CHAPTER_CLOSURE_BASELINE_2026-03-24.md`
- `program_code/exchange_connectors/bybit_connector/docs/K_CANONICAL_RUNNER_BASELINE_2026-03-24.md`
- `program_code/exchange_connectors/bybit_connector/docs/K_CHAPTER_CLOSURE_BASELINE_2026-03-24.md`

Why:
因为：
- these explain the earlier canonical baseline before the functional closeout extension
- they still matter for compatibility and historical interpretation

- 这些文件解释的是 functional closeout 扩展前的 canonical baseline
- 它们对兼容性与历史解释仍然重要

---

## Most important repo-local documents / 当前最重要的 repo 内文档

### Round-end work report / 本轮总工程记录
- `program_code/exchange_connectors/bybit_connector/docs/WORK_REPORT_2026-03-25_JK_FUNCTIONAL_CLOSEOUT.md`

### J closeout baseline / J 收口基线
- `program_code/exchange_connectors/bybit_connector/docs/J_FUNCTIONAL_CLOSEOUT_BASELINE_2026-03-25.md`

### K closeout baseline / K 收口基线
- `program_code/exchange_connectors/bybit_connector/docs/K_FUNCTIONAL_CLOSEOUT_BASELINE_2026-03-25.md`

### J/K stage baseline / J/K 阶段基线
- `program_code/exchange_connectors/bybit_connector/docs/JK_STAGE_STATUS_BASELINE_2026-03-25.md`

### Earlier canonical baselines / 更早 canonical 基线
- `program_code/exchange_connectors/bybit_connector/docs/J_CANONICAL_RUNNER_BASELINE_2026-03-24.md`
- `program_code/exchange_connectors/bybit_connector/docs/J_CHAPTER_CLOSURE_BASELINE_2026-03-24.md`
- `program_code/exchange_connectors/bybit_connector/docs/K_CANONICAL_RUNNER_BASELINE_2026-03-24.md`
- `program_code/exchange_connectors/bybit_connector/docs/K_CHAPTER_CLOSURE_BASELINE_2026-03-24.md`

---

## Most important runner / builder files / 当前最重要的 runner / builder 文件

### J canonical recheck / J canonical 复查
- `helper_scripts/maintenance_scripts/bybit_connector/run_j10_canonical_transition_engine_recheck.sh`

### K canonical recheck / K canonical 复查
- `helper_scripts/maintenance_scripts/bybit_connector/run_k10_canonical_demo_gate_recheck.sh`

### J functional closeout builder / J 功能收口 builder
- `program_code/trading_strategy/bybit_event_driven/bybit_transition_engine_functional_closure_builder.py`

### K functional closeout builder / K 功能收口 builder
- `program_code/exchange_connectors/bybit_connector/misc_tools/bybit_demo_gate_functional_closure_builder.py`

### J unified decision chain / J unified decision 链
- `program_code/trading_strategy/bybit_event_driven/bybit_transition_engine_decision_builder.py`
- `program_code/trading_strategy/bybit_event_driven/bybit_transition_engine_decision_contract_check.py`

### K unified decision / intake chain / K 顶层决策与 intake 链
- `program_code/exchange_connectors/bybit_connector/misc_tools/bybit_demo_gate_transition_intake_builder.py`
- `program_code/exchange_connectors/bybit_connector/misc_tools/bybit_demo_gate_transition_intake_contract_check.py`
- `program_code/exchange_connectors/bybit_connector/misc_tools/bybit_demo_gate_decision_builder.py`
- `program_code/exchange_connectors/bybit_connector/misc_tools/bybit_demo_gate_decision_contract_check.py`

---

## K capability-chain index / K 能力链索引

The following seven families were added and validated as part of the K closeout basis:
以下七条能力族已作为 K 收口基础新增并验证通过：

### 1. Adapter family / Adapter 能力族
- `bybit_demo_paper_adapter_transition_intent_builder.py`
- `bybit_demo_paper_adapter_transition_intent_contract_check.py`
- `bybit_demo_paper_adapter_capability_builder.py`
- `bybit_demo_paper_adapter_capability_contract_check.py`

Meaning:
含义：
- internal adapter intent can be formed
- no paper order submission authority is opened

- 已可形成内部 adapter intent
- 未打开 paper order submission authority

### 2. Lifecycle family / Lifecycle 能力族
- `bybit_paper_order_lifecycle_capability_builder.py`
- `bybit_paper_order_lifecycle_capability_contract_check.py`

Meaning:
含义：
- lifecycle state machine skeleton is defined
- submission path remains closed

- lifecycle 状态机骨架已定义
- submission path 仍关闭

### 3. Projection family / Projection 能力族
- `bybit_paper_position_balance_projection_capability_builder.py`
- `bybit_paper_position_balance_projection_capability_contract_check.py`

Meaning:
含义：
- position/balance/projection model surface is defined
- paper ledger path remains closed

- position/balance/projection 模型面已定义
- paper ledger path 仍关闭

### 4. Risk family / Risk 能力族
- `bybit_pretrade_risk_gate_capability_builder.py`
- `bybit_pretrade_risk_gate_capability_contract_check.py`

Meaning:
含义：
- risk model surface is defined
- risk gate remains closed

- risk 模型面已定义
- risk gate 仍关闭

### 5. Audit family / Audit 能力族
- `bybit_paper_audit_trail_capability_builder.py`
- `bybit_paper_audit_trail_capability_contract_check.py`

Meaning:
含义：
- audit model surface is defined
- audit path remains closed

- audit 模型面已定义
- audit path 仍关闭

### 6. Explicit operator switch family / 显式 operator 开关能力族
- `bybit_explicit_operator_enable_switch_capability_builder.py`
- `bybit_explicit_operator_enable_switch_capability_contract_check.py`

Meaning:
含义：
- operator-switch model surface is defined
- operator enable remains unavailable

- operator-switch 模型面已定义
- operator enable 仍不可用

### 7. Acceptance family / Acceptance 能力族
- `bybit_demo_gate_acceptance_capability_builder.py`
- `bybit_demo_gate_acceptance_capability_contract_check.py`

Meaning:
含义：
- acceptance model surface is defined
- demo gate remains closed

- acceptance 模型面已定义
- demo gate 仍关闭

---

## Most important runtime artifacts / 当前最重要的 runtime 产物

### J functional closeout runtime artifact / J 功能收口 runtime 产物
- `docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_functional_closure_latest.json`

This is the single most important machine-readable round-end truth for J.
这是 J 当前最重要的 machine-readable 收口真相。

### K functional closeout runtime artifact / K 功能收口 runtime 产物
- `docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_functional_closure_latest.json`

This is the single most important machine-readable round-end truth for K.
这是 K 当前最重要的 machine-readable 收口真相。

---

## One-sentence interpretation for future handoffs / 给未来接手的一句话解释

If a future maintainer asks “where are we now?”, the shortest correct answer is:
如果未来维护者问“我们现在到底在哪一步？”，最短且正确的回答是：

- J is functionally closed for this round, but still shadow/skeleton only.
- K is functionally closed for this round, but still design-only gate closed.
- Runtime remains read_only / execution disabled.

- J 本轮已完成功能收口，但仍然只是 shadow/skeleton only。
- K 本轮已完成功能收口，但仍然只是 design-only gate closed。
- Runtime 仍是 read_only / execution disabled。

---

## Recommended next step after this index / 这份索引之后的建议下一步

After this index is in place, the next sensible order is:
有了这份索引后，最合理的下一步顺序是：

1. keep this index as the primary navigation entry
2. use the 2026-03-25 work report plus the J/K closeout baselines as the default handoff package
3. only then discuss whether to enter the next chapter or first refresh broader total docs

1. 把这份索引作为主要导航入口
2. 以 2026-03-25 的 work report 与 J/K closeout baseline 作为默认接手资料包
3. 之后再讨论是进入下一章节，还是先刷新更大的总文档

---

## Final warning / 最终警示

The most dangerous future mistake is this:
未来最危险的误读是：

> “J/K are done, therefore execution can now be opened.”

That interpretation is still wrong.
这个解释仍然是错误的。

The correct interpretation remains:
正确解释仍然是：

> J/K are done **for their current protected engineering scope**, not for execution authority release.

> J/K 是在 **当前受保护工程范围内** 做完了，不是 execution authority release 做完了。
