# Brainstorm: Layer 2 AI 推理引擎设计

**日期：** 2026-03-26
**状态：** 设计讨论中，尚未实现
**关联：** project_layer2_agent_design.md（memory）

---

## 背景

Paper Trading Beta 已完成（248 测试，75 路由）。现有 H0-H5 是固定管线，无法做开放式推理。
Operator 要求 Agent 具备"像真人一样思考"的能力：自主搜新闻、理解宏观事件、判断预期差。

---

## 三层架构（已确定方向）

```
Layer 0（确定性监控，零成本，持续运行）
  = 现有 H0 + Observer + WS listener + 日历感知 + 基础设施监控
  输出：事件流 → 触发升级

Layer 1（情境评估，轻量 AI，~$0.01/次，~20 次/天）
  = 升级版 H1 thought_gate
  判断："这个异常值不值得深入？"
  输出：升级/不升级

Layer 2（深度推理，全能力 AI Agent 循环，$0.50-2.00/次，1-10 次/天）
  = 新架构，核心待实现
  能力：自主搜新闻、查链上数据、综合推理、形成交易观点
  工具箱：web_search / fetch_url / get_market_state / get_experience / submit_recommendation
  预估日成本：普通日 $1-2，大事件日 $3-6
```

---

## 核心设计思路

### Agentic Loop（Agent 循环）

使用 Anthropic Messages API 的 tool-use 能力。AI 不是一次性调用，而是循环：

```
1. 构建 system prompt（角色 + 约束 + 可用工具）
2. 构建 initial message（触发原因 + 市场概览）
3. 调用 API → AI 返回 tool_use blocks
4. 执行工具 → 返回结果给 AI
5. AI 继续推理 → 可能再调工具 → 可能直接输出结论
6. 循环直到 AI 调用 submit_recommendation 或达到限制
```

### 工具清单（8 个）

**数据读取类（零外部调用）：**
- `get_market_state` — 读取 verdict + microstructure + 最新价格
- `get_account_state` — 读取 paper trading 持仓/余额/PnL
- `get_recent_decisions` — 读取影子决策历史
- `get_experience` — 读取学习系统记录

**外部信息类（需网络）：**
- `web_search` — 搜索新闻/分析（AI 自主决定搜什么、怎么搜）
- `fetch_url` — 抓取网页内容

**输出类：**
- `submit_recommendation` — 提交结构化交易推荐
- `record_insight` — 记录市场洞察到学习系统

### 成本控制

- 每 session 预算：默认 $2.00
- 每日预算：默认 $20.00
- AI 成本计入 paper PnL

### 集成方式

Layer 2 推荐 → 映射为 governed_observation → build_shadow_decision() → consumer → paper order
无需修改现有管线。

---

## 新增文件预案

| 文件 | 职责 |
|------|------|
| `app/layer2_types.py` | 数据结构、常量、配置 |
| `app/layer2_cost_tracker.py` | 成本追踪与预算控制 |
| `app/layer2_tools.py` | 工具定义 + 执行调度 |
| `app/layer2_engine.py` | 核心 Agent 循环 |
| `app/layer2_routes.py` | FastAPI 路由 |
| `tests/test_layer2.py` | 测试（mock API） |

---

## 待讨论的关键问题

1. **web_search 实现方式** — 用什么搜索引擎？duckduckgo-search 库还是其他方案？
2. **Agent 循环实现** — 自己写 vs 用框架（如 LangChain、Claude Agent SDK）
3. **升级触发条件** — L0 → L1 → L2 的具体规则
4. **推理链记录格式** — 供复盘和学习系统消费
5. **模型选择** — L1 用 Haiku，L2 用 Sonnet 还是 Opus？
6. **并发控制** — 同一时间只允许一个 L2 session？

---

## 安全不变量

```
system_mode             = read_only        不变
execution_state         = disabled         不变
execution_authority     = not_granted      不变
所有推荐                = is_simulated: true
所有决策                = lease_mode: shadow_only
```
