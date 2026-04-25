# OpenClaw / Bybit 交易 Agent

# Implementation Bridge 实施桥梁 V1

# AI 计算架构 / Bybit V5 映射 / 部署规范


## 0. 文档定位 Document Positioning

本文件是治理设计与工程实现之间的桥梁文件。它回答以下问题：

- AI 计算分几层？每层用什么模型？成本多少？何时触发？

- 本地 Ollama 怎么部署？如何确保不影响交易系统？

- Bybit V5 API 的 6 产品族、订单类型、保证金模式如何映射到治理对象？

- AI 预算怎么管？自适应逻辑是什么？

- 手续费怎么优化？时段意识怎么落地？

- Paper → Live 的闸门条件是什么？

如与《项目宪法》冲突，以宪法为最高约束。


## 1. 四层计算路径 Four-Tier Compute Path

每一层可独立开关。系统从 L0+L1 起步（零外部成本），根据验证后的表现逐步开启更高层。


| **层级** | **引擎** | **成本** | **延迟** | **触发条件** |
|---|---|---|---|---|
| L0 | 本地确定性计算（H0 门控、止损检查、健康判断） | 零 | <1ms | 每次 tick，始终运行 |
| L1 | 本地 Ollama 7B（regime 分类、机会筛选、情绪打分） | 零 API，本地算力 | 1-3s | 每 5 分钟 + 事件触发 |
| L1.5 | 低成本云端（Haiku ~$0.001 + Perplexity ~$0.005） | ~$0.01-0.05/次 | 2-5s | L1 不确定 + 新闻扫描 |
| L2 | 完整云端（Sonnet $0.15 / Opus $0.50-4.00） | $0.15-4.00/次 | 5-30s | 高价值机会深度分析 |

**降级规则：**

- L2 不可用或预算耗尽 → 回退到 L1.5

- L1.5 不可用或当日云端预算耗尽 → 回退到 L1

- L1（Ollama）崩溃或超时 → 回退到 L0（纯本地确定性）

- 交易系统永远不等 AI，AI 是增强层不是依赖层

## 2. 本地 AI 部署规范 Local AI Deployment

### 2.1 硬件环境

- CPU: AMD AI MAX 395

- 内存: 128GB 统一内存（CPU + iGPU 共享）

- 操作系统: Linux


### 2.2 推荐模型

| **方案** | **模型** | **占用内存** | **推理速度** | **适用** |
|---|---|---|---|---|
| 推荐 | Qwen2.5 7B-Instruct Q4_K_M | ~5GB | ~30 tok/s | Regime 分类、机会筛选、情绪打分 |
| 备选升级 | Qwen2.5 14B-Instruct Q4_K_M | ~10GB | ~15 tok/s | 更精确的策略选择和参数建议 |
| 不推荐 | 32B+ | 20GB+ | <8 tok/s | 太慢且抢资源 |


### 2.3 资源隔离（确保不影响交易系统）

- systemd 服务设置 MemoryMax=12G，留 116GB 给交易系统

- CPUQuota=150%，最多用 1.5 个核心

- OOMPolicy=stop，超内存停 Ollama 不杀交易进程

- 调用超时 3 秒，超时则跳过本次 AI 判断走纯 L0

- 每分钟健康检查，连续 3 次失败自动重启

- 核心原则：Ollama 崩溃 = 退化到 L0 模式，不是停止交易


## 3. 模型路由规则 Model Routing Rules

每个任务类型有默认的模型映射，可通过配置调整：


| **任务** | **默认层级** | **默认模型** | **备注** |
|---|---|---|---|
| 止损检查、健康判断、H0 门控 | L0 | 本地确定性 | 永远不用 AI |
| Regime 分类、机会筛选 | L1 | Ollama Qwen2.5 7B | 每 5 分钟 |
| 新闻情绪打分 | L1 | Ollama Qwen2.5 7B | 解析搜索结果 |
| 策略参数优化 | L1 | Ollama Qwen2.5 7B | 基于历史数据 |
| 新闻搜索（主搜索） | L1.5 | Perplexity API | 每 30 分钟 |
| L1 结果二次确认 | L1.5 | Haiku | 抽样验证 |
| 高价值机会深度分析 | L2 | Sonnet | 每天 3-5 次 |
| 复杂多因子交叉、新策略孵化 | L2 | Opus | 罕见，预算允许时 |
| 模型升级判断（Sonnet→Opus） | L1.5 | Haiku | ~$0.005 快速分诊 |

## 4. AI 预算管理 AI Budget Management

### 4.1 三层预算控制

| **层级** | **默认值** | **说明** |
|---|---|---|
| Session 预算 | $1.50 (Sonnet) / $4.00 (Opus) | 单次推理 session 上限，可被自适应倍率调整 |
| 每日硬上限 | $2.00（保守模式） | 绝对上限，自适应无论如何不超过 |
| 自适应浮动 | 基础 $2/天 × 倍率 | 根据近 7 天 AI ROI 动态调整 |


### 4.2 自适应预算倍率

| **近 7 天 AI ROI** | **倍率** | **含义** |
|---|---|---|
| ≥ 3.0 | 2.0x | 大力花（AI 赚钱赚得多） |
| ≥ 1.5 | 1.5x | 适度扩张 |
| ≥ 0.5 | 1.0x | 维持 |
| ≥ 0 | 0.7x | 收紧 |
| < 0 | 0.3x | 大幅收紧但不停止 |
| 数据不足 3 天 | 1.0x | 不判断 |


### 4.3 ROI 计算方法

AI ROI = (AI 推荐产生的 Net PnL + AI 帮助规避的估算亏损) / AI 总花费

- 攻击价值：AI 推荐的交易的 paper PnL

- 防御价值：AI 建议不做的机会之后的市场表现（如果跌了 = AI 帮你躲了）

- 每个 session 的 PnL 回填形成闭环


### 4.4 保守模式日常成本估算

| **用途** | **频率** | **单次成本** | **日成本** |
|---|---|---|---|
| L1 Ollama regime 扫描 | 288次/天 | $0 | $0 |
| L1 Ollama 新闻解析 | 48次/天 | $0 | $0 |
| L1.5 Perplexity 新闻搜索 | 20次/天 | ~$0.005 | $0.10 |
| L1.5 Haiku 二次确认 | 10次/天 | ~$0.001 | $0.01 |
| L2 Sonnet 深度分析 | 3次/天 | ~$0.15 | $0.45 |
| 日合计 |  |  | ~$0.56 |
| 月合计 |  |  | ~$17 |


## 5. AI 注意力税工程规范 AI Attention Tax Engineering

### 5.1 注意力等级与税率

| **等级** | **tick 间隔** | **AI 成本/小时** | **场景** |
|---|---|---|---|
| dormant | 60s | $0.000 | 无仓位 |
| low | 10s | $0.003 | 有仓但安全 |
| medium | 3s | $0.010 | 有持仓 |
| high | 500ms | $0.050 | 接近触发 |
| critical | 实时 | $0.100 | 高波动 |


### 5.2 cost_edge_ratio 等级

| **等级** | **cost_edge_ratio** | **含义** |
|---|---|---|
| A | < 0.2 | 成本可忽略 |
| B | < 0.4 | 健康 |
| C | < 0.6 | 需要关注 |
| D | < 0.8 | 建议减仓或平仓 |
| F | ≥ 0.8 | 持有已不划算，应平仓 |


### 5.3 参数校准规则

- 免税期：新开仓位前 30 分钟不计注意力税，给仓位建立利润的时间窗

- 策略差异化：Grid 策略默认 dormant/low 注意力，Trend 策略默认 medium/high

- 平仓成本门槛：注意力税触发平仓的条件是 remaining_edge > close_cost + min_profit_threshold，而不是 remaining_edge > 0

- 开仓前成本预估：预估 AI 成本 = 预估持仓时间 × 每小时 AI 税率，预估净边际 ≤ 0 则不开仓

## 6. 四层搜索降级体系 Search Provider Fallback

| **优先** | **Provider** | **实现** | **成本** | **依赖** |
|---|---|---|---|---|
| 1 | Perplexity Search API + Claude 推理 | PerplexitySearchProvider | ~$0.005/次 | PERPLEXITY_API_KEY |
| 2 | 本地 Ollama + web-pilot | LocalLLMWebSearchProvider | 零 API | Ollama + web-pilot |
| 3 | 本地 Ollama 独立分析 | LocalLLMSearchProvider | 零 API | Ollama |
| 4 | web-pilot DuckDuckGo | WebPilotSearchProvider | 零 | web-pilot scripts |

- 自动降级：上层失败自动尝试下层，返回结果标注来源 provider

- 搜索结果必须带鲜度标记（5分钟前 vs 2小时前，权重不同）

- 搜索失败 → 降级到缓存数据 → 降级到无新闻决策（而不是阻塞）


## 7. Bybit V5 API 约束映射 Bybit V5 Constraint Mapping

### 7.1 六大产品族

| **品类** | **API category** | **杠杆** | **Funding** | **爆仓** | **风控特殊性** |
|---|---|---|---|---|---|
| Spot 现货 | spot | 无 | 无 | 无 | 最安全，亏损有限于本金 |
| Spot Margin | spot | 有 | 无 | 有 | 有借贷利息 |
| Linear Perp | linear | 1-125x | 每8h | 有 | 主战场，流动性最好 |
| Inverse Perp | inverse | 有 | 每8h | 有 | 以币结算，双重风险 |
| Futures | linear/inverse | 有 | 无 | 有 | 有到期日 |
| Options | option | N/A | 无 | N/A | 买方亏损有限，卖方无限 |


### 7.2 订单类型（10+）

- Market / Limit / Conditional(Stop) / TP_SL(order-level) / TP_SL(position-level) / Trailing Stop / Reduce Only / Post Only / Iceberg / TWAP / Batch


### 7.3 保证金模式

- Cross（共享全账户余额）/ Isolated（每仓独立）/ Portfolio（组合保证金）

### 7.4 持仓模式

- One-way（单向）/ Hedge（双向对冲）


### 7.5 手续费结构与优化

| **角色** | **费率** | **Executor 策略** |
|---|---|---|
| Taker | 0.055% | 只在止损和紧急平仓时使用 |
| Maker | 0.02% | 非紧急入场优先 Post-Only 限价单 |
| 往返成本底线 | ~21 bps (taker) | maker 优先可降至 ~12 bps |

- Executor Agent 必须默认 maker 优先：非紧急入场用 Post-Only，止盈用限价单，只有止损和紧急平仓才用市价

- VIP 等级意识：交易量达标后 taker fee 可降至 0.04% 以下，应纳入成本模型

## 8. 延迟预算 Latency Budget

| **环节** | **统计目标** | **说明** |
|---|---|---|
| H0 门控 | <1ms | 纯本地确定性 |
| L1 Ollama 推理 | <3s | 超时则跳过 |
| L1.5 云端搜索+确认 | <5s | 超时则降级到 L1 |
| L2 深度分析 | <30s | 非实时，不阻塞交易 |
| Bybit REST 下单 | <500ms p95 | 含网络 |
| Bybit WS 行情 | <100ms p95 | 含解码 |
| 端到端（信号→下单） | <5s (不含 L2) | 包含 H0+L1+风控+执行 |

## 9. 时段意识 Session Awareness

| **时段 (UTC)** | **特征** | **Strategist / Guardian 调整** |
|---|---|---|
| 亚洲 00:00-08:00 | 相对低波动 | Grid/FundingArb 权重上升 |
| 欧洲开盘 07:00-08:00 | 波动率上升 | 趋势策略准备 |
| 美国开盘 13:00-14:00 | 波动率最高 | 趋势策略权重上升，注意力税升级 |
| 周末 | 流动性差、假突破多 | 自动收紧风控 + 放宽软止损（防猎杀） |
| Session 交接期 | 组合波动 | 软止损阈值放宽 |


## 10. 部署架构 Deployment Architecture

- systemd 用户服务：openclaw-trading-api.service（开机自启 + 崩溃重启）

- 绑定 127.0.0.1:8000（仅本地），远程访问通过 SSH 隧道或 Tailscale

- OpenClaw Gateway：端口 18789

- Ollama 服务：独立 systemd，资源隔离，崩溃不影响交易

- Postgres：本地实例，存储 K 线、指标、交易记录、学习数据

- 运行时状态文件：chmod 0o600，不进 Git

**预留扩展点：**

- Venue Adapter 抽象层：当前只有 Bybit，但接口设计预留多交易所支持（如 Binance）

- Docker 化：当前裸机部署，后续可迁移到 Docker Compose

## 11. Paper → Live 闸门条件 Paper-to-Live Gate

以下条件全部满足后，方可由 Operator 批准首次进入 Supervised Live：

**Paper Trading 数据条件：**

- Paper trading 连续运行至少 4 周

- Round trips 至少 500 笔

- Net PnL 为正（含全部成本）

- 胜率 > 30%（含手续费后）

- Max drawdown 未触发熔断

- Sharpe ratio > 0.5

**系统健康条件：**

- 风控框架实测验证通过

- Freshness 闭合正常

- H0 门控全部 passed

- 审计链完整性率 > 99%

- 对账链 mismatch 率 < 0.1%

**治理条件：**

- Authority grant contract 已签署

- Execution adapter contract 已验证

- Provider pricing table 已绑定

- 灭灾保护单已在交易所端预挂

- Operator 明确批准

## 12. 安全不变量 Safety Invariants

以下不变量在任何情况下不得被违反：

- P0/P1 硬风控上限不可突破（Agent 只能在内收紧）

- 所有交易必须通过 H0 门控

- 所有写操作必须通过统一执行入口

- AI 每日硬上限不可突破

- Ollama 崩溃 → 退化到 L0，不停止交易

- 云端 API 不可用 → 退化到 L1，不停止交易

- 审计链不可被静默绕过

- 火灾保护单必须始终在交易所端存在

- Paper 阶段：system_mode=read_only, execution_state=disabled, execution_authority=not_granted

## 13. 一句话总纲 One-Line Summary

*Implementation Bridge 的目标，是把治理设计的每一个原则映射到可执行的工程约束：四层计算路径确保 AI 成本可控且零外部成本可运行；Bybit V5 全量映射确保 Agent 拥有完整操作空间；资源隔离确保本地 AI 不影响交易稳定性；Paper→Live 闸门确保只有已验证的能力才能进入实盘。*
