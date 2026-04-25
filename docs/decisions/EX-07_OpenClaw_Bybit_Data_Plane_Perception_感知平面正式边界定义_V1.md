# OpenClaw / Bybit 交易 Agent

# Data Plane / Perception

# 感知平面正式边界定义 V1


## 0. 文档定位

本文件定义系统的数据感知平面——所有流入系统的外部数据源及其治理规则。

- 交易所市场数据（价格、K 线、Order Book、Funding Rate）如何接入和校验？

- 外部信息（新闻、公告、事件、情绪）如何接入和标记质量？

- 数据鲜度如何评估？过时数据如何处理？

- 4 层搜索降级体系如何运作？

- Crypto 事件日历覆盖哪些事件？如何触发系统响应？

如与《项目宪法》冲突，以宪法为最高约束。


## 1. 数据源分类 Data Source Taxonomy

| **数据源** | **认知级别** | **刷新频率** | **主要消费者** |
|---|---|---|---|
| Bybit REST API（账户/持仓/订单） | fact | 按需 + 定时 | H0 / Guardian / Executor |
| Bybit WebSocket（ticker/trade/kline） | fact | 实时推送 | H0 / Strategist / Executor |
| Bybit WebSocket（orderbook） | fact | 实时推送 | Executor（流动性感知） |
| Bybit REST（funding rate / OI） | fact | 每 8 小时 + 按需 | Strategist / Guardian |
| Perplexity 搜索（新闻） | inference | 每 30 分钟 | Scout |
| web-pilot DuckDuckGo（免费搜索） | inference | 降级备选 | Scout |
| 本地 Ollama 情绪打分 | inference | 解析搜索结果时 | Scout |
| Crypto 事件日历（Token Unlock 等） | fact+inference | 每日更新 | Scout |
| 本地技术指标（MA/RSI/BB/MACD/ATR） | fact（计算结果） | 每根 K 线 | Strategist |
| 学习系统历史模式 | inference | Analyst 产出时 | Strategist / Guardian |

**核心原则：交易所 API 返回的数据是 fact，所有经过 AI 处理或外部搜索获取的数据默认是 inference。任何 inference 不得在未标记的情况下进入决策链。**

## 2. 数据质量评估 Data Quality Assessment

### 2.1 鲜度标记

| **鲜度级别** | **时间范围** | **处理方式** |
|---|---|---|
| FRESH | < 5 分钟 | 正常使用 |
| RECENT | 5-30 分钟 | 可使用，降低权重 |
| STALE | 30 分钟-2 小时 | 仅作参考，不作为主要决策依据 |
| EXPIRED | > 2 小时 | 丢弃，不进入决策链 |


### 2.2 质量维度

- completeness：数据是否完整（如 K 线缺失、Order Book 深度不足）

- consistency：多个数据源之间是否一致（REST vs WebSocket 价格偏差）

- latency：从交易所到系统的延迟是否在可接受范围内

- source_reliability：数据源是否可靠（Bybit API > 第三方聚合 > 新闻网站）


### 2.3 数据质量不足时的行为

- 价格数据 STALE → 不开新仓，已有仓位照常管理

- 价格数据 EXPIRED → 进入 CAUTIOUS 模式

- WebSocket 断连 > 30 秒 → 切换到 REST 轮询

- WebSocket 断连 > 5 分钟 → 进入 REDUCED 模式

- REST API 连续 3 次失败 → 进入 DEFENSIVE 模式


## 3. 交易所数据接入 Exchange Data Ingestion

### 3.1 WebSocket 频道

| **频道** | **推送频率** | **用途** |
|---|---|---|
| tickers.* | 实时 | 最新价格、24h 涨跌幅、成交量 |
| trade.* | 实时 | 逐笔成交（流动性感知、大单检测） |
| kline.*.{interval} | K 线收盘时 | 技术指标计算 |
| orderbook.{depth}.{symbol} | 实时增量 | 流动性深度、滑点预估 |


### 3.2 REST 端点

- /v5/market/tickers：批量获取 650+ 符号快照

- /v5/market/kline：历史 K 线（回测 + 冷启动）

- /v5/market/funding/history：Funding rate 历史

- /v5/market/open-interest：持仓量

- /v5/account/wallet-balance：账户余额

- /v5/position/list：持仓列表

- /v5/order/realtime：活跃订单


### 3.3 Rate Limit 约束

- REST：按端点不同 10-120 次/秒，需要 rate limiter 保护

- WebSocket：每账户最多 5 个连接，每连接最多 500 个订阅

- 系统必须有 rate limit aware 的请求调度器

## 4. 外部信息接入 External Information Ingestion

### 4.1 搜索降级体系（复述 DOC-08 §6，此处为 Scout 视角）

Scout Agent 通过 4 层搜索降级体系获取外部信息。搜索失败不得阻塞交易系统——降级到缓存数据或无新闻模式继续运行。


### 4.2 搜索结果标准化

所有搜索结果必须标准化为 intel_object，至少包含：

- source：来源 URL 或 API

- fetched_at：获取时间戳

- freshness：鲜度评估（FRESH / RECENT / STALE / EXPIRED）

- cognitive_level：fact / inference / hypothesis

- sentiment_score：-1.0（极度负面）到 +1.0（极度正面）

- relevance_score：0.0（无关）到 1.0（高度相关）

- summary：一句话摘要

- symbols_mentioned：涉及的交易符号列表


### 4.3 搜索内容安全

- 不访问需要登录的网站

- 不模拟浏览器登录

- 仅使用公开 API 和公开网页

- 遵守各搜索引擎的 ToS


## 5. Crypto 事件日历 Crypto Event Calendar

Scout Agent 维护一个结构化的 crypto 事件日历，覆盖以下事件类型：


| **事件类型** | **数据来源** | **系统响应** |
|---|---|---|
| Token Unlock | TokenUnlocks / 项目公告 | 提前 24h 通知 Guardian 收紧对应币种风控 |
| 交易所上币 | Bybit 公告 / 搜索 | 新币种加入扫描池，首日观察不交易 |
| 协议升级 | 项目公告 / 搜索 | 提前 48h 提高波动率预期 |
| FOMC / CPI | 经济日历 | 提前 2h 通知 Guardian 全面收紧风控 |
| 监管新闻 | 搜索 | 实时评估影响，必要时收紧风控 |
| 大额清算事件 | Bybit API（OI 突变） | 实时检测，Guardian 评估连锁风险 |
| Funding Rate 异常 | Bybit API | 极端 FR → Strategist 评估反向机会 |

**事件响应原则：**

- 事件的存在是 fact，事件的影响评估是 inference

- 重大事件（FOMC / 大额清算）触发 Guardian 自动收紧风控，不需要等 Strategist 评估

- 事件日历每日更新，但突发事件（监管新闻、清算事件）实时响应

## 6. 数据隔离与 Agent 访问权限 Data Isolation

| **数据类型** | **Scout** | **Strategist** | **Guardian** | **Analyst** | **Executor** |
|---|---|---|---|---|---|
| 交易所价格/K线 | 读 | 读 | 读 | 读 | 读 |
| 交易所账户/持仓 | - | 读 | 读 | 读 | 读 |
| 搜索结果/新闻 | 读写 | 读 | 读 | 读 | - |
| 交易意图 | - | 读写 | 读 | 读 | 读 |
| 风控参数 P2 | - | 读 | 读写 | 读 | 读 |
| 风控参数 P0/P1 | - | 读 | 读 | 读 | 读 |
| 学习记录 | - | 读 | 读 | 读写 | - |
| 订单/成交 | - | 读 | 读 | 读 | 读写 |

- Scout 不能访问账户和持仓信息（防止情报收集受持仓偏见影响）

- Executor 不能访问搜索结果（它只负责执行，不参与判断）

- P0/P1 硬上限所有 Agent 只读，只有 Operator 可修改

## 7. 漂移防护声明 Drift Protection

以下倾向应视为 Data Plane 边界漂移风险：

- 将 inference 级别的搜索结果不加标记地当作 fact 使用

- 搜索结果直接触发交易（必须经 Strategist 评估 + Guardian 审查）

- 数据质量评估被简化为"有数据就用"

- 事件日历只记录不触发响应

- Rate limit 被忽略导致 API 封禁

- WebSocket 断连后不降级，继续使用过时数据

一旦出现上述趋势，应优先修正数据治理边界。

## 8. 一句话总纲 One-Line Summary

*Data Plane 的职责是确保所有流入系统的数据都有明确的来源、鲜度、认知级别标记和质量评估，交易所数据是 fact、AI 处理和搜索获取的数据是 inference、未经标记的数据不得进入决策链。*
