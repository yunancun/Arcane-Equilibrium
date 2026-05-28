# Session 4：GUI 10-Tab 专业控制台全面重构

**日期：** 2026-03-27
**范围：** 前端 GUI 从 4-Tab 散乱布局升级为 10-Tab 专业控制台 + 多供应商 AI 引擎 + 可编辑风控
**结果：** 6 commits, 17 files changed, +3964/-243 lines, 646 tests 全通过, 0 回归

---

## 一、背景

Session 3 完成后系统全部审核问题已修复（214/214），但 GUI 存在以下问题：
1. Paper Trading 嵌入主仪表盘，信息过载
2. 没有 Bybit Demo 独立面板
3. 缺少策略管理、风控、AI 引擎、学习系统等专属面板
4. 所有状态显示原始程序名（如 `design_only`），不直观
5. 按钮无法使用（body 格式不匹配 API）
6. AI 引擎仅支持 Claude，无法管理多供应商

---

## 二、提交记录（6 commits: 60bc63e → d0e250d）

| Commit | 说明 |
|--------|------|
| `60bc63e` | GUI 10-Tab 主架构：8 新 Tab + common.js + 双层解释 |
| `2dc1394` | 修复字段映射：Demo/Strategy/Risk/AI 匹配实际 API 响应 |
| `93fa0be` | Round 2：显示 bug + 可编辑风控/AI 设置 + AI 止损咨询 |
| `471e581` | 策略创建/删除 API + K 线页清理 + 策略管理 UI |
| `b892caf` | 系统总览：中文标签 + 悬停提示 + 来源上下文/健康 + 快速按钮 |
| `d0e250d` | 修复按钮 + 多供应商 AI 引擎 + Trigger 确认弹窗 |

---

## 三、新增/重写文件清单

### 新增（12 个文件）

| 文件 | 大小 | 说明 |
|------|------|------|
| `common.js` | 15.7 KB | 共享工具库：认证、API、格式化、组件样式 |
| `tab-system.html` | 25.0 KB | G1 系统总览：中文状态 + 悬停提示 + 快速按钮 + 确认弹窗 |
| `tab-paper.html` | 18.6 KB | G2 模拟交易：会话控制 + 行情 + PnL + 持仓 + 订单 + 下单 + 历史 |
| `tab-demo.html` | 11.3 KB | G3 Bybit Demo：Bybit V5 格式解析 + Paper vs Demo 对比 |
| `tab-strategy.html` | 15.3 KB | G4 策略中心：中文名 + 创建/删除 + Hard Stop + 扫描器 |
| `tab-risk.html` | 26.5 KB | G6 风控：可编辑止损 + AI 止损咨询 + 模型选择 + 危险操作区 |
| `tab-ai.html` | 28.9 KB | G7 AI 引擎：6 供应商管理 + API Key + 确认弹窗 + 扩展设置 |
| `tab-learning.html` | 13.8 KB | G8 学习系统：审核队列 + 自动扫描 + Net PnL |
| `tab-monitoring.html` | 11.3 KB | G9 监控：Grafana + Pipeline + Telegram + OpenClaw |
| `tab-settings.html` | 13.6 KB | G10 设置：Demo 控制 + 产品族 + 成本录入 + 调试 JSON |
| `gui_10tab_restructure.md` | 工作日志（首版） |
| 本文件 | 本次完整工作日志 |

### 重写（3 个文件）

| 文件 | 说明 |
|------|------|
| `console.html` | 10-Tab 主容器 + 侧栏概览 + 懒加载 iframe |
| `trading.html` | 移除 shadow_only/Console/GUI/token 输入框 + 动态币种 |
| `login.html` | 默认重定向 /trading → /console |

### 修改（2 个后端文件）

| 文件 | 说明 |
|------|------|
| `phase2_strategy_routes.py` | +2 API：POST /strategy/create + DELETE /strategy/{name} + Demo positions settleCoin 修复 |
| `CLAUDE.md` | 章节树 + 状态行 + 参考指针更新 |

---

## 四、设计原则

### 三层信息密度
- **Level 0 — 一览**：每 Tab 顶部状态栏，3-6 个关键指标
- **Level 1 — 工作视图**：持仓表格、策略卡片、风控仪表
- **Level 2 — 深度**：折叠区域（成交历史、调试 JSON、实验列表）

### 双层解释模式
每个重要区域有两段说明：
1. **简单说明**（始终可见）：通俗易懂，零经验用户也能理解
2. **深入说明**（默认折叠）：技术细节，避免程序化语言

### 中文状态标签 + 悬停提示
- 所有程序名翻译为直观中文（`design_only` → `仅设计模式`）
- 鼠标悬停显示原始值 + 详细说明

### 确认弹窗
关键操作（Paper 启停、Feed 启停、AI Trigger）弹出确认对话框：
- 说明即将发生什么
- 提示可能的后果
- 显示预估成本（AI Trigger）
- 要求二次确认

---

## 五、Tab 结构（10 个）

```
📊 系统总览  💰 模拟交易  🏦 Bybit Demo  ⚙ 策略中心  📈 K线图表
🛡 风控止损  🤖 AI 引擎  📖 学习系统  🔍 监控  ⚙ 设置
```

---

## 六、核心功能清单

### G1 系统总览
- 6 个运行态指标（中文 + 悬停提示）
- 来源上下文 6 指标（REST/WS/运行连接/账户/快照/角色分离）
- 健康评分仪表 5 项 + 门禁徽章 5 项
- 业务概览 6 指标
- 快速按钮 4 个（Paper/Demo/Feed/Scanner）+ 确认弹窗

### G2 模拟交易
- Session 控制栏（Start/Pause/Resume/Stop）— 按钮实际工作
- 行情流控制 + 实时价格显示
- PnL 6 指标 + 持仓表 + 活跃订单表 + 下单表单
- 性能指标（12 项：Fill 数/Round Trips/胜率/回撤/余额...）

### G3 Bybit Demo
- 通过 balance API 自动检测连接（retCode=0）
- Bybit V5 格式解析（totalEquity/availableBalance/...）
- 持仓表 + Paper vs Demo 对比
- 未配置时显示引导说明

### G4 策略中心
- 策略卡片：中文名（均线交叉/布林回归/...）+ Hard Stop + Delete
- 创建策略表单（Type + Symbol + Qty）
- API：POST /strategy/create + DELETE /strategy/{name}
- 扫描器机会 + 自动部署列表 + 交易意图历史
- AI 自主决定启停（上限 100），人类只做硬关闭

### G5 K 线图表
- 移除过时元素（shadow_only/Console/GUI/token 输入）
- 动态币种：自动从策略/持仓/Demo 拉取交易中的币种

### G6 风控止损
- 可编辑设置：硬止损/跟踪止损/时间止损/回撤/杠杆/日亏损
- AI 止损咨询：选择模型 + 风格 → 自动生成 prompt → AI 建议
- 3 层风控展示（P0/P1/P2）
- 危险操作区（Reset Cooldown / Unhalt Session）

### G7 AI 引擎
- 6 AI 供应商管理：Anthropic/OpenAI/DeepSeek/Perplexity/Local LLM/Google
- 每个供应商可输入 API Key 并保存
- Trigger Session 确认弹窗 + 各模型预估成本
- 扩展设置：供应商/模型/硬上限/弹性预算/自动提交/最大迭代

### G8-G10
- G8 学习系统：审核队列 + 自动扫描 + 实验/假设 + Net PnL
- G9 监控：Grafana + Pipeline Bridge + Telegram + OpenClaw
- G10 设置：Demo 控制面板 + 产品族配置 + 成本录入 + 调试 JSON

---

## 七、修复的 Bug

| Bug | 原因 | 修复 |
|-----|------|------|
| Paper Session 按钮无反应 | `ocEnvelope` 包装，Paper 路由期望简单 body | 改为直接 `{initial_balance: 100000}` |
| Feed 按钮无反应 | 同上 | 改为 `{symbols: [...]}` |
| Runtime Summary 全 "--" | 数据在 `global_runtime.global_mode_state` 下 | 解析嵌套结构 |
| 性能指标 `[object Object]` | `trade_metrics`/`drawdown_metrics` 嵌套对象 | 展开嵌套字段 |
| Demo "未连接" | status 返回 `{}` 但 balance 有数据 | 改用 balance API 检测 |
| 策略无名字 | API 字段是 `strategy` 不是 `name` | 修正字段名 + 添加中文翻译 |
| 风控全空 | 键名 `global_config` 不是 `global` | 修正映射 |
| Demo positions 报错 | Bybit V5 要求 `settleCoin` 参数 | 传 `settleCoin=USDT` |
| 来源上下文空白 | 字段名不匹配（`rest_private_connection_state`） | 逐字段对应 |
| 健康摘要空白 | 嵌套结构 `scores`/`gates` | 分别渲染评分 + 门禁 |

---

## 八、测试结果

```
全量测试：646 passed, 0 failed, 2 warnings
  - control_api_v1/tests/: 428 passed
  - local_model_tools/tests/: 218 passed
前端+后端修改零回归
```

---

## 九、文件体量统计

```
前端总计：~230 KB（12 HTML + 2 JS + 1 CSS）
后端修改：phase2_strategy_routes.py (+105 lines)
工作日志：2 文件
主日志更新：CLAUDE.md + docs/README.md
```
