# Brainstorm 留档：OpenClaw 定位 + Agent 架构讨论

**日期：** 2026-03-26
**参与者：** Operator (ncyu) + Claude Code
**性质：** 架构讨论 brainstorm，非最终决策

---

## 一、讨论起因

Operator 提出问题："我们的 agent 究竟是通过 OpenClaw 实现还是实际上是一个本地 agent？"

经过调研 OpenClaw（https://openclaw.ai/）— 一个本地运行的 AI Agent 运行时 + 消息网关（port 18789），发现需要明确分工。

---

## 二、OpenClaw 能力调研结果

OpenClaw v2026.3.24，已安装运行，但处于出厂状态（BOOTSTRAP.md 还在，无自定义技能/通道）。

**核心能力：**
- AI Agent 运行时（Claude/OpenAI API 后端）
- 50+ 内建技能（weather, github, coding-agent 等）
- 30+ 消息通道（Telegram, Discord, Slack 等）
- Cron 定时任务 + Heartbeat 定期检查
- Canvas 可编程页面
- 内建 AI 成本追踪（gateway usage-cost）
- 持久记忆（workspace 文件 + SQLite）
- 命令审计日志

**当前实例状态：**
- 版本：2026.3.24
- 模型：claude-opus-4-6（200k context）
- 通道：无
- 技能：6/50 ready（coding-agent, weather 等通用技能）
- Cron：无
- 累计消耗：$0.10 / 15k tokens

---

## 三、核心结论：OpenClaw 不适合当交易 Agent 大脑

### 四个要求 vs OpenClaw

| 要求 | OpenClaw 能否满足 | 原因 |
|------|-------------------|------|
| 1. 感知成本和收益 | ❌ | 每步推理都调 LLM，无法精细控制 AI 花费；不知道"这次思考值不值得" |
| 2. 最佳运用 AI | ❌ | 没有 thought_gate / query_budget / model_router；每条消息都触发 AI |
| 3. 长期自我进化 | ⚠️ | 通用 markdown 记忆，无法做量化交易学习（胜率/归因/假设验证） |
| 4. 硬件/基础设施感知 | ❌ | Heartbeat 30 分钟一次；交易需要秒级实时监控 |

### 架构决定

```
本地 Python Agent = 大脑（决策 + 感知 + 执行 + 学习）
OpenClaw = 嘴巴和耳朵（通信 + 运维 + Operator 交互）
```

---

## 四、OpenClaw 融合方案（零/低 AI 成本）

### 优先级 1：Canvas 仪表盘入口
- 在 OpenClaw Canvas (port 18790) 嵌入我们的 GUI
- 解决"打开 GUI 麻烦"的问题

### 优先级 2：AI 成本追踪整合
- `openclaw gateway usage-cost --json` → 读取 AI 花费
- Feed 进我们的 Net PnL 计算
- 省去自己写 token 计费程序的时间

### 优先级 3：Telegram 告警通道
- `openclaw channels add --channel telegram`
- 我们的 Agent 通过 `openclaw message send` 推送告警
- 纯消息转发，零 AI 成本

### 优先级 4：自定义 Skill
- 在 workspace 创建 bybit-trading skill
- 让 Operator 通过自然语言控制交易系统
- 后续详细设计

### 不用 OpenClaw 做的
- 市场数据处理、交易决策循环、实时风控
- H0-H5 判断链、Decision Lease
- 结构化交易学习

---

## 五、未解决的严肃问题（待后续讨论）

**Operator 提出：** "我希望 agent 能够自己决定是否搜索相关新闻，并且能够执行一些机械化交易以外的智能化判断（就像真人一样，但是更好）。我不确定我们现有的本地架构足够支撑这个想法。"

这个问题涉及 H 链架构的根本设计 — 当前 H0-H5 是固定管线（确定性判断 → 结构化 AI 调用），但真正的智能交易决策需要开放式推理能力（自主搜索新闻、联系宏观事件、适应性策略调整）。

**核心矛盾：**
- 固定管线 = 可控、可预测、低成本 → 但不够"智能"
- 开放式 AI 推理 = 智能、灵活 → 但成本高、不可预测

**确定的解决方向：三层 Agent 架构**

```
Layer 0（确定性监控，零成本，持续运行）
  = 现有 H0 + Observer + WebSocket + 日历感知 + 基础设施监控
  输出：事件流 → 触发升级

Layer 1（情境评估，轻量AI，$0.01/次，~20次/天）
  = 升级版 H1 thought_gate
  判断："这个异常值不值得深入？"

Layer 2（深度推理，全能力AI Agent循环，$0.50-2.00/次，1-10次/天）
  = 新架构，核心待设计
  能力：自主搜新闻、查链上数据、综合推理、形成交易观点
  工具箱：web_search / fetch_url / query_onchain / check_derivatives
         / read_experience / submit_paper_order / record_reasoning

日均成本估算：正常日 $1-2，重大事件日 $3-6
```

**Layer 2 待设计的关键问题：**
1. Agent 循环实现方式
2. 工具箱定义（新闻、链上、衍生品、日历）
3. 升级触发条件
4. 推理链记录格式
5. 成本控制策略
6. 与现有代码整合点

**时间线：** 完成仪表盘 + AI 成本追踪后启动 Layer 2 设计

---

## 六、保留的代码资产

所有已完成的代码（73 路由、248 测试）不白费：
- Control API 的 73 条路由 → OpenClaw 的工具/技能后端
- Paper Trading Engine → 保留作为执行引擎
- Observer Pipeline → 保留作为数据采集
- H0 本地判断 → 保留作为快速预筛
- H1-H5 → 保留但可能需要扩展以支持开放式推理
- Learning System → 保留作为结构化经验存储
- GUI → 保留，通过 Canvas 提供统一入口
