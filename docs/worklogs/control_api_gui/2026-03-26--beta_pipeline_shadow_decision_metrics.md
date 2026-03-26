# Beta 管线完善：影子决策管线 + 性能指标 + 实时行情 + 自动桥接

**日期：** 2026-03-26
**分支：** feature/openclaw-bybit-control-api-gui-v1-rc2
**状态：** 248 测试全通过（从 200 → 248），零回归

---

## 完成内容总览

本轮工作完成了 Paper Trading Beta 的四个关键基础设施模块，使系统从"手动输入价格的纸上交易"升级为"可接入实时行情 + AI 决策 + 自动桥接 + 性能评估"的完整 beta 管线。

---

## 一、实时行情系统（Real-Time Market Data）

### 新增文件
- `app/bybit_public_ws_listener.py` — Bybit V5 公共 WebSocket 监听器
  - 连接 `wss://stream.bybit.com/v5/public/linear`，无需认证
  - 支持动态 subscribe/unsubscribe，价格缓存，回调分发
  - 线程安全，后台守护线程运行

- `app/market_data_dispatcher.py` — 事件驱动行情分发器
  - 自适应注意力过滤器：5 级（DORMANT/LOW/MEDIUM/HIGH/CRITICAL）
  - 根据交易上下文自动调节 tick 频率（60s → 0s）
  - 波动率检测（60 秒滑窗，1% 阈值）
  - 限价单接近度计算

### 新增路由（5 条）
| 方法 | 路由 | 功能 |
|------|------|------|
| POST | `/paper/market-feed/start` | 启动行情流 |
| POST | `/paper/market-feed/stop` | 停止行情流 |
| GET | `/paper/market-feed/status` | 行情流状态 |
| POST | `/paper/market-feed/add-symbol` | 动态添加交易对 |
| POST | `/paper/market-feed/remove-symbol` | 动态移除交易对 |

### GUI 集成
- `index.html` 新增行情控制区（Start/Stop 按钮 + 状态徽章 + 价格显示）
- `app.js` 新增行情状态自动刷新（3 秒间隔）
- `styles.css` 新增行情区样式

---

## 二、Observer 自动桥接（Auto-Bridge）

### 新增文件
- `scripts/auto_bridge_observer_to_runtime_snapshot.py` — Observer → Runtime Snapshot 自动桥接
  - 读取 3 个 observer 输出文件（system_snapshot / ws_facts / verdict）
  - 按 `runtime_snapshot_contract.py` 合同生成 runtime snapshot
  - 支持 one-shot 和 loop 模式（`--loop --interval 30`）
  - 已通过真实 observer 数据验证

- `scripts/beta_quickstart.sh` — 一键启动脚本
  - 运行 auto-bridge → 设置环境变量 → 启动 uvicorn

### 测试
- `tests/test_auto_bridge.py` — 26 个测试
  - 连接状态提取、新鲜度判断、完整性检查
  - 产品族事实推导、健康遥测计算
  - 完整快照生成 + 合同验证
  - 文件 I/O + 权限检查
  - 真实 observer 数据集成测试

---

## 三、影子决策管线（Shadow Decision Pipeline）

### 新增文件
- `app/shadow_decision_builder.py` — 影子决策构建器
  - `build_shadow_decision()` — 从 H 链输出构建影子决策
    - 支持 governed observation（AI 判断）和 verdict-only（降级模式）
    - 交易信号判断：confidence ≥ 0.5 && edge ≥ 5bps && mode ≠ observation_only
    - 安全标记：`is_simulated=True`, `lease_mode="shadow_only"`, `execution_authority="not_granted"`
  - `ShadowDecisionConsumer` — 消费影子决策，满足阈值时创建纸上订单
    - 仓位大小：余额 × position_size_fraction（默认 2%）
    - 历史记录上限 200 条
  - `ShadowDecisionFileFeeder` — 文件馈送器
    - 读取 H 链输出文件，按 verdict 时间戳去重
    - 支持 verdict + governed observation 双文件

### 新增路由（4 条）
| 方法 | 路由 | 功能 |
|------|------|------|
| POST | `/paper/shadow/feed` | 手动触发影子决策馈送 |
| GET | `/paper/shadow/history` | 影子决策消费历史 |
| GET | `/paper/shadow/decisions` | 存储在纸上状态中的影子决策 |
| GET | `/paper/metrics` | 综合性能指标 |

### 测试
- `tests/test_shadow_decision.py` — 26 个测试
  - build_shadow_decision：12 个（信号判断、安全标记、边界条件）
  - ShadowDecisionConsumer：8 个（hold/trade/rejected/history）
  - ShadowDecisionFileFeeder：6 个（文件加载、去重、错误处理）

---

## 四、高级性能指标（Advanced Metrics）

### 新增文件
- `app/paper_trading_metrics.py` — 性能指标计算模块
  - `compute_trade_metrics()` — 胜率、平均盈亏、盈亏比、最大盈亏
  - `compute_drawdown_metrics()` — 最大回撤（百分比 + 绝对值）、峰值/谷值余额
  - `compute_holding_period_metrics()` — 平均/最小/最大持仓时长
  - `compute_sharpe_ratio()` — 简化 Sharpe 比率（年化）
  - `compute_shadow_decision_metrics()` — 影子决策效率（交易率、平均置信度、regime 分布）
  - `compute_full_metrics()` — 一站式完整指标报告

### 测试
- `tests/test_paper_metrics.py` — 22 个测试
  - 交易指标、余额序列、回撤计算
  - 持仓时长、Sharpe 比率
  - 影子决策指标、完整报告

---

## 数据汇总

| 指标 | 数值 |
|------|------|
| 新增文件 | 7 个（3 模块 + 4 测试） |
| 修改文件 | 3 个（routes + index.html + app.js + styles.css） |
| 新增路由 | 10 条（73 总路由） |
| 新增测试 | 48 个（248 总测试） |
| 测试通过 | 248/248（100%） |
| 纸上交易路由 | 23 条 |

---

## 安全不变量确认

```
system_mode             = read_only        ✅ 未变
execution_state         = disabled         ✅ 未变
execution_authority     = not_granted      ✅ 未变
decision_lease_emitted  = false            ✅ 未变
所有新模块              = is_simulated: true ✅
影子决策                = lease_mode: shadow_only ✅
```

---

## 五、OpenClaw 融合（Canvas 仪表盘 + AI 成本追踪）

### 统一控制台 — `http://localhost:8000/console`
- 左侧边栏：AI 成本实时显示、Paper PnL、Session 状态、系统健康
- 主区域：Tab 切换 Trading Dashboard / OpenClaw Control
- 15 秒自动刷新，零 AI 成本
- OpenClaw Canvas (`~/.openclaw/canvas/index.html`) 通过 iframe 指向统一控制台

### AI 成本追踪 — `GET /api/v1/paper/ai-cost`
- 调用 `openclaw gateway usage-cost --json` 读取 OpenClaw 内建的 token/成本追踪
- 返回：今日成本、30 天累计、token 用量、成本分解（input/output/cache）、每日明细
- 零额外开发成本 — 复用 OpenClaw 已有能力
- 侧边栏实时展示 AI 花费，与 Paper PnL 并列显示

### 新增路由（2 条）
| 方法 | 路由 | 功能 |
|------|------|------|
| GET | `/console` | 统一控制台入口 |
| GET | `/api/v1/paper/ai-cost` | AI 成本追踪（via OpenClaw） |

### 访问方式
- **最简单：** `http://localhost:8000/console` — 一个页面看到所有东西
- **原有 GUI：** `http://localhost:8000/static/index.html` — 不变
- **OpenClaw Canvas：** `http://localhost:18789/canvas/index.html` — 指向统一控制台

---

## 最终数据汇总

| 指标 | 数值 |
|------|------|
| 总路由 | **75 条** |
| 纸上交易路由 | **24 条** |
| 总测试 | **248 个，全部通过** |
| 新增文件（本轮） | 9 个 |

---

## 六、基础设施完善

### systemd 服务化
- `~/.config/systemd/user/openclaw-trading-api.service` — API 服务器开机自启 + 崩溃重启
- 绑定 `127.0.0.1:8000`，仅本地访问
- 管理：`systemctl --user {status|restart|stop} openclaw-trading-api`

### 统一控制台 iframe 修复
- OpenClaw 设置 X-Frame-Options 阻止 iframe 嵌入
- 解决：OpenClaw tab 改为"新窗口打开"按钮 + Gateway 状态面板

---

## 下一步

1. **远程安全访问方案** — SSH 隧道 / Tailscale / Cloudflare Tunnel（详见独立工程日志）
2. **Layer 2 AI 推理循环设计** — 三层 Agent 架构（L0确定性/L1轻量评估/L2深度推理），支持自主搜新闻、智能化交易判断
3. **Telegram 告警通道** — 接 OpenClaw channels，推送交易告警
4. **自动循环 cron** — observer cycle → shadow decision → paper order → fill tick
5. **Beta 运行数据积累** — 运行数周积累足够数据后进入 M 章
