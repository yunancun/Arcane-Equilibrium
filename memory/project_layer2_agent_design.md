---
name: Layer 2 开放式 AI 推理循环设计
description: 交易Agent需要"像人一样思考"的能力——自主搜新闻、理解宏观事件、判断预期差。三层架构 L0/L1/L2 已确定，Layer 2 设计工作在 W22（G-1 AI Agent）展开。
type: project
originSessionId: 189878ce-df95-4b97-a566-ea1b4e395fe9
---
## 背景

Operator 明确要求：Agent 要能自己决定是否搜索新闻，能做机械化交易以外的智能化判断。

现有 H0-H5 是固定管线（数据→筛选→结构化AI调用→输出），无法做到：
- 自主信息收集（"好奇心"机制）
- 宏观事件理解（Fed会议、ETF flow、监管新闻）
- 预期差判断（需要常识推理）
- 自主决定下一步做什么

## 确定的三层架构

```
Layer 0（确定性监控，零成本，持续运行）
  = 现有 H0 + Observer + WebSocket + 日历感知 + 基础设施监控
  输出：事件流 → 触发升级

Layer 1（情境评估，轻量AI，$0.01/次）
  = 升级版 H1 thought_gate
  判断："这个异常值不值得深入？"
  输出：升级/不升级

Layer 2（深度推理，全能力AI Agent循环，$0.50-2.00/次）
  = 新架构，核心待设计
  能力：自主搜新闻、查链上数据、综合推理、形成交易观点
  工具箱：web_search / fetch_url / query_onchain / check_derivatives / read_experience / submit_paper_order / record_reasoning
  每日触发 1-10 次，成本 $1-6/天
```

## 当前状态（2026-04-12）

原阻断条件 "完成仪表盘 + 成本追踪" **已解除**（Live GUI Phase 4-6 ✅，AI 成本追踪 ✅）。

Layer 2 设计工作纳入 W22（G-1 AI Agent / Strategist+Guardian）路线图，当前 H1-H5 全为 stub。现有设计见 `docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md`。

## Layer 2 待设计的关键问题

1. Agent 循环怎么实现（自己写 vs 用框架 vs 借用OpenClaw部分能力）
2. 工具箱有哪些（新闻搜索、链上数据API、衍生品数据、经济日历）
3. 升级条件定义（Layer 0 → 1 → 2 的触发规则）
4. 推理链记录格式（供复盘和学习系统消费）
5. 成本控制（Layer 2 的预算上限、模型选择策略）
6. 与现有代码的整合点（H1扩展、Paper Engine作为工具、Learning System作为经验库）

## 现有代码资产对照

保留不变：H0, Paper Engine, Control API, Learning System, Observer  
需要扩展：H1 thought_gate → Layer 0→1→2 升级决策器  
需要新增：Layer 2 Agent 循环 + 工具箱 + 推理链记录

**Why:** Operator 的终极目标是"超越脚本的交易Agent"，不是更好的下单机器人。
**How to apply:** W22+ G-1 AI Agent 设计工作展开时，以此三层架构为基础；H1-H5 stub 替换为真实实现。
