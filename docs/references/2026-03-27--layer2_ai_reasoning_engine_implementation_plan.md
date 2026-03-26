# Layer 2 AI 推理引擎实现计划 (Layer 2 AI Reasoning Engine Implementation Plan)

**日期：** 2026-03-27
**状态：** 设计完成，待实现
**分支：** main（实现时将在 feature 分支进行）

---

## 背景

Paper Trading Beta 已完成（248 测试，75 路由）。现有 H0-H5 是固定管线（数据→筛选→结构化 AI 调用→输出），无法做到自主信息收集和开放式推理。Layer 2 是一个**真正的 agentic loop**：AI 可以调用工具、处理结果、决定下一步调查方向、迭代直到形成结论。

**关键架构决策（Operator 已确认）：** 搜索能力采用 4 层降级体系，Perplexity（带引用+时间戳）作为主搜索，Claude 作为推理大脑。信息时效性是交易场景的核心需求——过时信息被当作最新信息比没有信息更危险。

---

## 一、三层 Agent 架构

```
Layer 0（已有）→ 事件触发（零成本，持续运行）
  ↓
Layer 1（轻量 Haiku ~$0.01）→ "值得深入吗？"
  ↓ 值得
Layer 2（Sonnet Agent 循环 $0.50-2.00，可升级 Opus）
  → 调用工具（市场数据 / 持仓 / 新闻搜索 / 经验库）
  → 搜索：4 层 SearchProvider 降级体系
  → 搜索后模型升级判断（Haiku triage → Sonnet 或 Opus）
  → 迭代推理 → submit_recommendation
  ↓
build_shadow_decision() → ShadowDecisionConsumer → Paper Order
  ↓
PnL 归因回填 → 自适应预算调整（学习 AI 花费是否划算）
```

---

## 二、4 层 SearchProvider 降级体系

| 优先级 | Provider | 实现 | 成本 | 依赖 |
|--------|----------|------|------|------|
| 1 Primary | Perplexity Search API + Claude 推理 | `PerplexitySearchProvider` | ~$0.005/次搜索 | `PERPLEXITY_API_KEY` (pplx-) |
| 2 Degradation | 本地 LLM (Ollama) + web-pilot | `LocalLLMWebSearchProvider` | 零 API | Ollama + web-pilot |
| 3 Conservative | 本地 LLM 搜索 + 分析 | `LocalLLMSearchProvider` | 零 API | Ollama |
| 4 Backtunnel | web-pilot DuckDuckGo | `WebPilotSearchProvider` | 零 | web-pilot scripts |

自动降级：上层失败自动尝试下层，返回结果标注来源 provider。

---

## 三、新增文件（5 模块 + 1 测试）

| 文件 | 职责 |
|------|------|
| `app/layer2_types.py` | 数据结构、SearchProvider ABC、配置类、常量 |
| `app/layer2_cost_tracker.py` | 成本追踪（Claude + Perplexity）+ 自适应预算 + 定价核实 |
| `app/layer2_tools.py` | 8 个工具 Anthropic schema + 执行器 + 4 个 SearchProvider 实现 |
| `app/layer2_engine.py` | 核心 Agent 循环 + 模型升级判断 + Shadow Decision 集成 |
| `app/layer2_routes.py` | 9 条 FastAPI 路由（trigger/sessions/cost/pricing/adaptive/config） |
| `tests/test_layer2.py` | 全量测试（mock Anthropic + Perplexity，不做真实 API 调用） |

修改 1 个文件：`app/main.py`（注册 `layer2_router`，2 行）

---

## 四、8 个 Agent 工具

**数据读取（零外部调用）：**
- `get_market_state` — verdict + microstructure + 最新价格
- `get_account_state` — paper trading 持仓/余额/PnL
- `get_recent_decisions` — 影子决策历史
- `get_experience` — 学习系统记录

**外部信息（SearchProvider 抽象）：**
- `web_search` — 通过 4 层 Provider 搜索新闻（自动降级）
- `fetch_url` — 抓取网页提取文本

**输出：**
- `submit_recommendation` — 结构化交易推荐（action/confidence/edge/reasoning/freshness）
- `record_insight` — 记录市场洞察到学习系统

---

## 五、成本控制体系

### 5.1 预算控制（三层）

| 层级 | 默认值 | 说明 |
|------|--------|------|
| Session 预算 | $1.50 (Sonnet) / $4.00 (Opus) | 单次推理 session 上限，可被自适应倍率调整 |
| 每日硬上限 | **$15.00** | 绝对上限，自适应无论如何不超过，GUI 可调 |
| 自适应浮动 | 基础 $8/天 × 倍率 | 根据近 7 天 AI ROI 动态调整 |

**默认 $15/天分配：** L1 triage ~$0.50 + L2 搜索 ~$1.50 + Sonnet 推理 ~$3.00 + Opus 升级 ~$5.00 + 判断 ~$0.10 + 预留 ~$4.90

### 5.2 搜索后模型升级判断

搜索工具返回结果后，用 Haiku（~$0.005）快速判断是否从 Sonnet 升级到 Opus：
- 升级条件：重大宏观事件 / 结果矛盾 / 多因子交叉 / 大仓位
- 升级时自动提升 session 预算（$1.50 → $4.00）

### 5.3 自适应预算（根据盈利浮动）

```
近 7 天 AI ROI ≥ 3.0  → 倍率 2.0x（大力花）
近 7 天 AI ROI ≥ 1.5  → 倍率 1.5x（适度扩张）
近 7 天 AI ROI ≥ 0.5  → 倍率 1.0x（维持）
近 7 天 AI ROI ≥ 0    → 倍率 0.7x（收紧）
近 7 天 AI ROI < 0     → 倍率 0.3x（大幅收紧但不停止）
数据不足 3 天          → 倍率 1.0x（不判断）
```

**花费划算度学习：** 每个 session 推荐执行后追踪 paper PnL → 回填 `pnl_attribution`（ROI、是否划算）→ 倍率重算 → 形成闭环。

### 5.4 定价定期核实

- 定价表存 `runtime/layer2_pricing.json`，记录 `last_verified_date`
- 超过 30 天未核实：标记 `pricing_stale`（不阻断运行，成本报告中显示警告）
- 可选与 OpenClaw `gateway usage-cost` 交叉验证

---

## 六、9 条新增路由

| 方法 | 路由 | 功能 |
|------|------|------|
| POST | `/paper/layer2/trigger` | 手动触发 L2 推理 session |
| GET | `/paper/layer2/sessions` | session 列表 |
| GET | `/paper/layer2/sessions/{id}` | session 详情（推理链 + 模型升级 + PnL 归因） |
| GET | `/paper/layer2/cost` | 成本汇总（今日/累计/预算/自适应倍率/定价警告） |
| GET | `/paper/layer2/cost/pricing` | 定价表 + 核实状态 |
| POST | `/paper/layer2/cost/pricing` | 更新定价表 |
| GET | `/paper/layer2/cost/adaptive` | 自适应预算状态（倍率 + ROI + 历史） |
| GET | `/paper/layer2/config` | L2 全量配置 |
| POST | `/paper/layer2/config` | 更新配置（预算/模型/自适应/provider） |

系统总路由 75 → 84。

---

## 七、GUI 集成

Paper Trading Dashboard 新增 **AI Budget 控制卡片**：
- 每日硬上限 / 基础 session 预算（可编辑）
- 自适应开关 / 最大扩张倍率（可编辑）
- 今日花费进度条 / 当前倍率 / 近 7 天 ROI
- 花费划算度统计（AI 花费 vs Paper PnL / ROI / 划算率）
- 触发 L2 推理 / 查看历史 / 重置默认

---

## 八、集成方式（无需修改现有代码）

Layer 2 推荐 → 映射为 `governed_observation`（`analysis_mode: "layer2_agentic"`）→ 走现有 `build_shadow_decision()` → `ShadowDecisionConsumer.consume()` → paper order

---

## 九、依赖

```bash
.venv/bin/pip install anthropic duckduckgo-search beautifulsoup4 httpx
```

---

## 十、安全不变量

```
system_mode             = read_only        不变
execution_state         = disabled         不变
execution_authority     = not_granted      不变
所有推荐                = is_simulated: true
所有决策                = lease_mode: shadow_only
AI 成本                 = 计入 paper PnL
并发控制                = 同一时间仅一个 L2 session
搜索 ToS               = 仅用 API（不模拟浏览器登录）
daily_hard_cap          = 绝对上限，自适应不可突破
```
