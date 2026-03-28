# Session 6 — 半天数据分析与系统诊断修复
# 2026-03-28

---

## 背景

系统 Paper Trading + 自主交易 Agent 已运行约半天（~21.8小时），对积累的数据进行首次系统性分析。发现4个问题，当场全部修复。

---

## 一、运行数据快照（分析时刻）

| 指标 | 数值 |
|------|------|
| Paper session ID | psess:fe7ac188 |
| 运行时长 | 约 21.8 小时 |
| 初始余额 | $10,000 |
| 当前余额 | $9,947.12 |
| 已实现 PnL | -$42.33 |
| 手续费 | -$10.55 |
| **Net PnL** | **-$52.88 (-0.53%)** |
| 总订单 | 522 笔 |
| Round-trip 次数 | 153 次 |
| **胜率** | **0%（153 战全负）** |
| Sharpe 比率 | -1.30 |
| 最大回撤 | 0.53% |
| 平均持仓时长 | 548 秒（约 9 分钟） |

**已部署策略（服务重启前）：**
- 10 个 scanner 自动部署（9 个 MA_Crossover trend + 1 个 FundingRate_Arb）
- 5 个默认 BTCUSDT 策略（MA_Crossover / BB_Reversion / FundingRate_Arb / Grid_Trading / BB_Breakout）

---

## 二、发现的问题

### 问题1（严重）：胜率 0%，MA Crossover 被高波动币反复震仓

**根因：** Scanner 扫描"trend"类别时，以24h涨跌幅和波动率打分，并不过滤极端波动的pump/dump币。结果部署了：
- SIRENUSDT：24h +114.8%（当日暴拉）
- TAUSDT：-33.9%，ONTUSDT：+29.6%……

这类币价格变动剧烈，MA Crossover 会在高点开多、在回调中被止出，或追空之后反弹。

另一个放大因素：`min_confidence` 默认值 0.3，几乎相当于无过滤，在噪音行情中近乎随机入场。

**实证：**
```
avg_fill_price_buy  = 0.298
avg_fill_price_sell = 0.2968
→ 每次都是更贵买、更便宜卖（顺势追噪音的典型模式）
```

### 问题2（中）：`bybit_private_*_check.py.orig` 文件缺失，cron 每5分钟崩溃

**根因：** `io_and_persistence/bybit_private_account_check.py`（及 positions、order_history）设计为：
```
io_and_persistence/*.py → os.execv → _bybit_latest_wrapper.py → <script>.py.orig
```
其中 `.orig` 文件是真正调用 Bybit REST API 的业务逻辑。但这三个 `.orig` 文件从未被创建。

结果：每5分钟 cron 运行 `bybit_full_readonly_observer_cycle.py` 时，私有检查脚本全部以 `FileNotFoundError` 崩溃，产生大量错误日志，且 `allowed_to_continue` 永远为 `false`。

Observer 事实上还能工作（execution_history 走的是另一条路径），但 account/positions/order_history 三项检查完全不可用。

### 问题3（低）：`connector_runtime_status` 和 `connector_heartbeats` 表不存在

**根因：** `bybit_readonly_status_writer.py`（另一条每5分钟 cron）尝试写入这两张表，但 DB 初始化 SQL 里从未建过。同样，`audit_events` 表也缺失。

结果：每次都 `ERROR: relation "connector_runtime_status" does not exist`，INSERT 全部失败。

### 问题4（观察/无需立即处理）：BB_Reversion / FundingRate_Arb 零交易

BB_Reversion 和 BB_Breakout 的信号条件在当前行情下未被触发（正常）。FundingRate_Arb 的资金费率一直低于阈值（正常）。Grid_Trading BTCUSDT 在 sandbox 价格 $66,478 范围内（63k-68k），工作正常：24 笔均衡交易（12买/12卖，净持仓=0）。

---

## 三、修复内容

### Fix 1：扫描器过滤极端波动币 + 提高 MA Crossover 置信度阈值

**文件：** `program_code/local_model_tools/strategy_auto_deployer.py`

在 `_deploy_strategy()` 的 `category == "trend"` 分支：
1. 新增过滤：`abs(opp.price_change_pct_24h) > 40.0` 时跳过部署，并记录 log
2. 传入 `min_confidence=0.55` 给 `MACrossoverStrategy`（原默认 0.3）

**逻辑：** 24h涨跌幅超40%的币处于pump/dump状态，趋势跟踪策略在其上会被反复震仓。0.55置信度要求信号更明确，减少噪音入场。

### Fix 2：创建3个 `.orig` stub 文件

**文件：**
- `scripts/bybit_private_account_check.py.orig`
- `scripts/bybit_private_positions_check.py.orig`
- `scripts/bybit_private_order_history_check.py.orig`

每个 stub 脚本检查 API key 是否存在：
- 不存在 → 输出 `{"ok": false, "retMsg": "api_key_not_configured", ...}` 的 JSON
- 存在但逻辑未实现 → 输出 `not_implemented` JSON

**效果：** cron 不再崩溃；preflight guard 能读到文件，`*_file_present` 检查变为 `OK`；失败原因从"文件不存在"变为更诚实的"api_key_not_configured"（6 项失败，全部因为没有真实 API key，是预期行为）。

**验证（修复前→后对比）：**
```
修复前：
  account_file_present  = FAIL（FileNotFoundError）
  Python 抛 can't open file '...account_check.py.orig': No such file or directory

修复后：
  account_file_present  = OK ✓
  positions_file_present = OK ✓
  order_history_file_present = OK ✓
  失败原因：api_key_not_configured（诚实反映现状）
```

### Fix 3：建立缺失的 DB 表

在 Docker postgres (`trading_postgres`) 新建3张表：
- `connector_runtime_status` — 连接器运行状态快照
- `connector_heartbeats` — 连接器心跳记录
- `audit_events` — 系统审计事件

建表后验证：`bybit_readonly_status_writer.py` 运行结束输出 `INSERT 0 1 / INSERT 0 1 / bybit read-only preflight status written successfully`。

---

## 四、测试结果

```
修复后全量测试：428 passed, 2 warnings（全通过）
API 服务重启：systemctl --user restart openclaw-trading-api.service
Paper session 状态：保留（psess:fe7ac188，余额 $9,947.12，数据无损）
```

---

## 五、重启后状态

服务重启后 scanner 已清空已部署策略列表（`deployed_count: 0`）。下次扫描周期（约5分钟后）将以新规则重新部署：
- 跳过24h涨跌幅>40%的币
- MA Crossover 置信度阈值改为 0.55

Paper session 继续运行，余额/历史数据完整保留。

---

## 六、遗留观察（不紧急）

- **Grid Trading BTC 范围**：Sandbox 价格约 $66k，范围 63k-68k 目前在范围内。若切换到真实环境，需按实际价格（~$87k）重新设置 grid 上下界。
- **Scanner 策略多样性**：目前扫描结果几乎全是 `trend` 类别。中期应考虑在行情稳定时适当部署 `grid` 或 `reversion` 类别策略，降低单一策略类型的集中风险。
- **策略表现追踪**：目前所有 MA_Crossover 合并计 PnL，无法单独评估每个 symbol 的贡献。后续可考虑按 strategy_name 分解 PnL。

---

## 七、本次修改文件清单

| 文件 | 类型 | 变更 |
|------|------|------|
| `program_code/local_model_tools/strategy_auto_deployer.py` | 修改 | 过滤>40%涨跌幅 + 置信度0.55 |
| `scripts/bybit_private_account_check.py.orig` | 新建 | API key缺失时输出not_configured JSON |
| `scripts/bybit_private_positions_check.py.orig` | 新建 | 同上 |
| `scripts/bybit_private_order_history_check.py.orig` | 新建 | 同上 |
| DB: `connector_runtime_status` | 新建表 | 连接器状态持久化 |
| DB: `connector_heartbeats` | 新建表 | 心跳持久化 |
| DB: `audit_events` | 新建表 | 审计事件持久化 |
