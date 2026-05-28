# Layer 2 AI 推理引擎设计工作记录

**日期：** 2026-03-27
**分支：** main
**状态：** 设计完成，尚未编码

---

## 本次工作内容

本轮对话完成了 Layer 2 AI 推理引擎的完整架构设计和实现计划，涵盖以下关键决策和设计产出。

---

## 一、搜索 Provider 方案调研与决策

### 调研范围

对以下搜索方案进行了可行性评估：

| 方案 | 结论 | 原因 |
|------|------|------|
| Perplexity Search API | **采用（Primary）** | 带引用+日期标注，信息时效性最佳，用户已获取 API key |
| web-pilot DuckDuckGo | **采用（Backtunnel）** | 零成本，已安装，作为终极后备 |
| 本地 LLM (Ollama) + web-pilot | **采用（Tier 1 降级）** | Perplexity 不可用时使用 |
| 本地 LLM 纯分析 | **采用（Conservative）** | 零 API 成本，频繁搜索或辅助判断 |
| Perplexity 浏览器自动化 | **放弃** | ToS 明确禁止自动化访问网页版 |
| Slack 桥接 | **放弃** | 需付费 Slack 工作区（$7.25/月+） |
| Discord 桥接 | **放弃** | 底层仍用 API |
| ChatGPT API | **不需要** | Claude 推理 + Perplexity 搜索已覆盖所有需求 |
| OpenClaw 内建 Perplexity 插件 | **确认为 API 封装** | 非免费通道，仍需 pplx- 或 sk-or- key |

### Perplexity Pro 福利调研

- 官方 API 定价页面**无**任何 Pro 用户免费额度说明
- 第三方来源（2026年）仍提及 $5/月 API credit
- 结论：大概率还在，但**不能作为长期依赖**

### 最终架构（Operator 确认）

> Perplexity+Claude 方案 A 第一优先 → 本地 LLM 联网+Claude 一阶降级 → 本地 LLM 搜索+分析保守方案 → web-pilot backtunnel

核心原则：**Claude = 大脑（推理），Perplexity = 眼睛（搜索+引用+时效性）**

---

## 二、Agentic Loop 设计

确定了完整的 Agent 循环架构：

1. Anthropic Messages API 的 tool-use 能力驱动循环
2. 8 个工具（4 数据读取 + 2 外部信息 + 2 输出）
3. `submit_recommendation` 作为 tool（强制结构化输出）
4. 同步 client + `asyncio.to_thread()` 避免阻塞
5. `threading.Lock()` 并发控制（同一时间仅一个 session）
6. 默认模型 Sonnet，可动态升级到 Opus

---

## 三、搜索后模型升级判断层

新增设计：搜索完成后插入 Haiku triage（~$0.005），判断是否需要升级到 Opus：

- 升级条件：重大宏观事件 / 搜索结果矛盾 / 多因子交叉 / 大仓位
- 升级时自动提升 session 预算上限（$1.50 → $4.00）
- 不升级条件：结果明确 / 已在 Opus / 预算不足 / 自适应倍率低

---

## 四、自适应预算系统

核心设计：Agent 根据近期 AI 花费 vs 交易收益自动调整每日预算。

- **每日硬上限：$15.00**（GUI 可调，自适应不可突破）
- **基础每日预算：$8.00**（留出扩张空间）
- **自适应倍率：** 基于近 7 天 AI ROI 计算（0.3x ~ 2.0x）
- **PnL 归因回填：** 每个 session 推荐执行后追踪实际 PnL → 计算 ROI → 喂回倍率

分级映射：
- ROI ≥ 3.0 → 2.0x（花 $1 赚 $3+）
- ROI ≥ 1.5 → 1.5x
- ROI ≥ 0.5 → 1.0x
- ROI ≥ 0 → 0.7x
- ROI < 0 → 0.3x（收紧但不停止）

---

## 五、API 定价定期核实

- 定价表存 `runtime/layer2_pricing.json`，记录核实日期
- 30 天未核实标记 `pricing_stale`（不阻断，显示警告）
- 可选与 OpenClaw `gateway usage-cost` 交叉验证（差异>10%标记）

---

## 六、路由规划

新增 9 条路由（系统总路由 75 → 84），覆盖：trigger / sessions / cost / pricing / adaptive / config。

---

## 七、GUI 集成规划

Paper Trading Dashboard 新增 AI Budget 控制卡片：
- 每日硬上限 / 基础 session 预算 / 自适应开关 / 扩张倍率（均可编辑）
- 今日花费进度 / 当前倍率 / 近 7 天 ROI / 划算率（实时展示）

---

## 产出文件

| 文件 | 位置 | 说明 |
|------|------|------|
| Layer 2 实现计划 | `docs/references/2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` | 完整实现计划存档 |
| 本工作记录 | `docs/worklogs/control_api_gui/2026-03-27--layer2_ai_engine_design_session.md` | 本文件 |
| Brainstorm 留档 | `docs/worklogs/control_api_gui/2026-03-26--brainstorm_layer2_ai_reasoning_engine.md` | 前一轮初步设计（已有） |

---

## Git 状态

- 当前在 `main` 分支，与 `origin/main` 一致
- 有大量未暂存修改和未跟踪文件（来自前几轮 Beta 管线开发）
- 无远端新提交需要 pull
- 本地有未提交的工作需要 commit + push

---

## 安全不变量确认

```
system_mode             = read_only        不变
execution_state         = disabled         不变
execution_authority     = not_granted      不变
全程未写任何代码        ✅ 仅设计和文档
```

---

## 下一步

1. 将本地未提交的工作整理 commit + push
2. 按实现计划编码 Layer 2（5 模块 + 1 测试 + 1 行 main.py 修改）
3. 依赖安装：`anthropic` / `duckduckgo-search` / `beautifulsoup4` / `httpx`
