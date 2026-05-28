# GUI 10-Tab 全面重构

**日期：** 2026-03-27
**范围：** 前端 GUI 从 4-Tab 散乱布局升级为 10-Tab 专业控制台
**结果：** 10 个新/重写文件 + 1 共享工具库 + 646 测试全通过

---

## 一、背景

原 GUI 存在以下问题：
1. Paper Trading 嵌入主仪表盘，信息过载
2. 没有 Bybit Demo 独立面板
3. Grafana 没有失败回退
4. 缺少策略管理、风控、AI 引擎、学习系统等面板
5. 控制开关分散，没有统一解释说明

---

## 二、新增/重写文件清单

| 文件 | 大小 | 说明 |
|------|------|------|
| `common.js` | 15.7 KB | 共享工具库：认证、API、格式化、解释模式、组件样式 |
| `console.html` | 重写 | 10-Tab 主容器 + 侧栏概览 + 懒加载 iframe |
| `tab-system.html` | 10.5 KB | G1 系统总览：运行态、业务概览、来源上下文、健康、产品族 |
| `tab-paper.html` | 17.8 KB | G2 模拟交易：会话控制、行情、PnL 6指标、持仓、订单、下单表单、成交历史、影子决策 |
| `tab-demo.html` | 9.9 KB | G3 Bybit Demo：连接状态、余额、持仓、Paper vs Demo 对比、未配置引导 |
| `tab-strategy.html` | 11.8 KB | G4 策略中心：编排器状态、策略卡片+生命周期控制、扫描器机会、自动部署、交易意图 |
| `tab-risk.html` | 14.3 KB | G6 风控止损：3层风控(P0/P1/P2)、止损管理器、AI 风控建议、危险操作区 |
| `tab-ai.html` | 12.3 KB | G7 AI 引擎：成本仪表盘、自适应预算、咨询状态、会话历史、定价表 |
| `tab-learning.html` | 13.8 KB | G8 学习系统：概览、审核队列+操作、学习动态、Net PnL、自动扫描、实验、假设 |
| `tab-monitoring.html` | 11.3 KB | G9 监控：Grafana 嵌入+失败引导、Pipeline Bridge、Telegram、OpenClaw Gateway |
| `tab-settings.html` | 13.6 KB | G10 设置：Demo 控制面板、快捷操作、产品族配置、成本/PnL 录入、调试 JSON、系统信息 |
| `login.html` | 修改 | 默认重定向 /trading → /console |

---

## 三、设计原则

### 信息密度策略（三层渐进展示）
- **Level 0 — 一览**：每个 Tab 顶部状态栏，3-6 个关键指标，无需滚动
- **Level 1 — 工作视图**：持仓表格、策略卡片、风控仪表，日常使用
- **Level 2 — 深度**：折叠区域（成交历史、调试 JSON、实验列表），按需展开

### 双层解释模式
每个重要区域都有两段说明：
1. **简单说明**（始终可见）：通俗易懂，零经验用户也能理解
2. **深入说明**（默认折叠）：技术细节，避免程序化语言

### 控制开关三态
- **Active**：已连接后端，正常操作
- **Placeholder**：后端存在但未配置（如 Demo 未设 API key），显示引导
- **Future**：虚线边框，Coming Soon，预留扩展

---

## 四、Tab 结构

```
Tab Bar（可水平滚动）：
 📊 系统总览  💰 模拟交易  🏦 Bybit Demo  ⚙ 策略中心  📈 K线图表
 🛡 风控止损  🤖 AI 引擎  📖 学习系统  🔍 监控  ⚙ 设置
```

侧栏始终显示：Paper PnL、Session 状态、AI 成本、系统健康、快速导航

---

## 五、API 覆盖

| Tab | 使用的 API 端点数 |
|-----|-------------------|
| System | 5 (overview, source-context, health, product-families, session/status) |
| Paper | 7 (session/*, positions, orders, fills, metrics, market-feed, shadow) |
| Demo | 3 (demo/status, demo/balance, demo/positions) |
| Strategy | 5 (list, status, scanner/*, intents) |
| Charts | 保持现有 trading.html |
| Risk | 3 (risk/config, risk/status, risk/ai-context) |
| AI | 6 (layer2/*, ai/status) |
| Learning | 6 (overview, hypotheses, feed, experiments, review-queue, net-pnl) |
| Monitoring | 3 (strategy/status, telegram/status, openclaw/health) |
| Settings | 5 (control-plane, product-families, overview, audit-summary, demo/*) |

---

## 六、技术实现

- **架构**：console.html 为主容器，每个 Tab 通过 iframe 加载独立 HTML 文件
- **懒加载**：Tab 首次切换时才加载对应 iframe，避免初始化卡顿
- **共享认证**：通过 localStorage 的 `oc_trading_token` 跨 iframe 共享认证
- **自动刷新**：核心 Tab 每 15 秒，次要 Tab 每 30 秒
- **样式统一**：common.js 注入标准化 CSS，所有 Tab 视觉一致

---

## 七、测试结果

```
全量测试：646 passed, 0 failed, 2 warnings
前端更改无 Python 逻辑变更，零回归风险
```
