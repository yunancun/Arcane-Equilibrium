# Session 日志：GUI Tab 重构 + Ollama 优化 + 后台市场流
<!-- 日期：2026-03-31（用户称"3月30日"）-->

## 本次工作概述

本 Session 完成了 6 项主要工作：

1. **Paper/Demo 账户余额卡片对齐** — 统一布局（上：账户余额，下：盈亏概览）
2. **Tab 合并与重排** — Paper+Demo 合并成"测试交易"子 Tab，新增"实盘交易（锁定）"占位 Tab
3. **子 Tab 样式修复** — 将半椭圆 pill 样式改为与外层一致的下划线样式
4. **设置 Tab Modal CSS 修复** — "计划重启"对话框常驻问题根治
5. **Ollama 模型分配 + think 参数优化** — 9B 快速路径 / 27B 复杂任务，关闭 thinking 模式后延迟大幅降低
6. **后台市场流常驻** — MarketDataDispatcher 改为服务启动即运行，不依赖 Paper/Demo 会话状态

---

## 1. Paper/Demo 账户余额对齐

### 背景
Paper Tab 顶部是盈亏概览，Demo Tab 顶部是账户余额，两者布局不一致。

### 修改内容

**`tab-paper.html`**：在 PnL Overview 卡片前插入 Account Balance 卡片，字段：
- `p-bal-initial`（初始余额，来自 session.initial_balance）
- `p-bal-current`（当前余额，来自 dm.current_balance）
- `p-bal-peak`（峰值余额，来自 dm.peak_balance）
- `p-bal-drawdown`（最大回撤，来自 dm.max_drawdown_pct）

`loadSession()` 计算 initial_balance 显示值；`loadMetrics()` 获取实时余额（authoritative 来源）。

**`tab-demo.html`**：把 unrealized/realized PnL 从账户余额卡片中移出，放到新的"盈亏概览"卡片（紧跟账户余额下方）。

最终两个 Tab 上下布局完全一致。

---

## 2. Tab 合并与重排

### 问题
随着功能增加，顶层 Tab 数量已 10+，Paper 和 Demo 都是独立 Tab 让界面碎片化。

### 方案 A（采用）：iframe 嵌套包装器

创建 `tab-trading.html`（新文件），作为"测试交易"Tab：
- 自带一条子 Tab 栏（纸面交易 / Bybit Demo）
- 每个子 Tab 加载独立 iframe，分别指向 `/static/tab-paper.html` 和 `/static/tab-demo.html`
- Demo iframe 懒加载（首次切换到 Demo 子 Tab 时才创建）

### `console.html` Tab 数组更新

旧：含 `paper`、`demo` 两个独立顶层 Tab
新：

```javascript
const TABS = [
  { id: 'system',     label: '系统总览',  labelEn: 'Overview',   icon: '📊', src: '/static/tab-system.html' },
  { id: 'live',       label: '实盘交易',  labelEn: 'Live 🔒',    icon: '🔒', src: '/static/tab-live.html' },
  { id: 'trading',    label: '测试交易',  labelEn: 'Test',       icon: '🧪', src: '/static/tab-trading.html' },
  { id: 'charts',     label: 'K线图表',   labelEn: 'Charts',     icon: '📈', src: '/trading' },
  { id: 'strategy',   label: '策略中心',  labelEn: 'Strategy',   icon: '⚙',  src: '/static/tab-strategy.html' },
  { id: 'risk',       label: '风控止损',  labelEn: 'Risk',       icon: '🛡',  src: '/static/tab-risk.html' },
  { id: 'ai',         label: 'AI 引擎',   labelEn: 'AI',         icon: '🤖', src: '/static/tab-ai.html' },
  { id: 'learning',   label: '学习系统',  labelEn: 'Learning',   icon: '📖', src: '/static/tab-learning.html' },
  { id: 'governance', label: '治理控制',  labelEn: 'Governance', icon: '⚖',  src: '/static/tab-governance.html' },
  { id: 'monitoring', label: '监控',      labelEn: 'Monitor',    icon: '🔍', src: '/static/tab-monitoring.html' },
  { id: 'settings',   label: '设置',      labelEn: 'Settings',   icon: '⚙',  src: '/static/tab-settings.html' },
];
```

顺序逻辑：总览 → 实盘（锁） → 测试 → K线 → 策略/风控 → AI/学习/治理 → 监控/设置

### `tab-live.html`（新文件）
实盘交易占位 Tab，显示：
- 当前 runtime 状态（从 `/api/v1/governance/status` 读取）
- 8 项 Live 前置条件（颜色码：绿/黄/灰）
- Phase 路线图（Phase 1-4 进度）
- 说明：本 Tab 在 Phase 4 Paper Trading 观察完成后开放

---

## 3. 子 Tab 样式修复（关键视觉 bug）

### 问题
初版 `tab-trading.html` 子 Tab 使用 `border-radius: 20px 20px 0 0` + 三边 border，渲染成半椭圆，与外层 Tab 栏完全不同风格，且因 body 未设 `height: 100%` 导致子 Tab 栏只显示上半段。

### 根本原因（两个）
1. **布局塌陷**：`body` height 为 `auto`，`.inner-wrap` 使用 `position: absolute; top: 41px` 依赖父高度，但父无固定高度
2. **样式不统一**：pill 样式与外层控制台 Tab 风格完全不同

### 修复方案
完全复制外层控制台 Tab 栏的 CSS 逻辑：

```css
html, body {
  height: 100%;
  margin: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.sub-tab-bar {
  display: flex;
  background: var(--card-bg);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sub-tab {
  padding: 7px 16px;
  font-size: 12px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  white-space: nowrap;
  transition: color .2s, border-color .2s;
}
.sub-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.inner-wrap {
  flex: 1;
  position: relative;
  overflow: hidden;
}
.inner-wrap iframe {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  border: none;
}
```

`flex-direction: column` + `flex: 1` 让内容区填满剩余高度，彻底解决截断问题。

---

## 4. 设置 Tab Modal CSS 修复

### 问题
"计划重启"警告内容（⚠ 倒计时 + 确认框）一直常驻在设置 Tab 中，未点击任何按钮就可见。

### 根本原因
`tab-settings.html` 完全没有定义 `.hidden`、`.confirm-modal`、`.confirm-modal-backdrop` 等 CSS 类，导致：
- `.hidden` = `display: none` 从未生效（undefined class）
- Modal 容器默认 block 显示，页面加载即可见

### 修复
在 `tab-settings.html` `<style>` 块中补全完整 Modal CSS：

```css
.hidden { display: none !important; }
.confirm-modal {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.confirm-modal-backdrop {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0.6); backdrop-filter: blur(2px);
}
.confirm-modal-dialog {
  position: relative; z-index: 1;
  background: #161b22; border: 1px solid #30363d; border-radius: 12px;
  padding: 24px; min-width: 360px; max-width: 480px;
}
/* + confirm-modal-header/body/footer, confirm-block, confirm-label, button-muted */
```

---

## 5. Ollama 模型分配 + think 参数优化

### 背景
系统有两个本地 Ollama 模型：`qwen3.5:9b-q4_K_M` 和 `qwen3.5:27b-q4_K_M`。
启用 thinking 模式时 9B = 8.7s，27B = 21s，对交易时效不可接受。

### 关键发现：`think` 参数位置错误
Ollama 0.19.0 处理 Qwen3.5 的 `think` 开关时，**必须放在 JSON payload 顶层**，而非 `options: {}` 内部。
初版代码将其放在 `options` 中，被 Ollama 静默忽略，thinking 始终开启。

```python
# 错误（放在 options 里，被忽略）
"options": {"temperature": 0.1, "num_predict": 256, "think": False}

# 正确（顶层）
payload = {
    "model": model,
    "prompt": prompt,
    "stream": False,
    "think": think,          # ← 必须在顶层
    "options": {"temperature": 0.1, "num_predict": 256},
}
```

### 修复后延迟对比
| 模型 | thinking=on | thinking=off (修复后) |
|------|-------------|----------------------|
| 9B   | ~8.7s       | **~1.9s**            |
| 27B  | ~21s        | **~9.9s**            |

### 模型分配策略（`ollama_client.py`）

| 用途 | 模型 | think | 原因 |
|------|------|-------|------|
| L1 edge filter (pre-trade) | 9B | False | 交易路径，延迟敏感，1.9s 可接受 |
| L1 triage (`layer2_engine`) | 9B | False | 快速分流，速度优先 |
| `classify()` | 9B | False | 分类任务，无需推理链 |
| AnalystAgent 周报 (Wednesday) | 27B | True | 复杂模式分析，时效宽松 |
| Layer2Engine weekly session (Sunday) | Claude L2 | — | 深度季度回顾，外部 AI |

### `ollama_client.py` 改动
- `DEFAULT_MODEL` 改为 `qwen3.5:9b-q4_K_M`
- `generate()` 新增 `think: bool = False` 参数（顶层 payload 注入）
- `judge_edge()`：max_tokens 256→100，timeout 20→8，think=False
- `classify()`：timeout 15→8，think=False
- 新增 `get_ollama_client_27b()` 单例（`_heavy_client` 全局变量，双重检查锁）
- `reset_ollama_client()` 同时重置 `_heavy_client`

### AnalystAgent 使用 27B
`phase2_strategy_routes.py` 中 AnalystAgent 初始化改用 `get_ollama_client_27b()`：
```python
from .ollama_client import get_ollama_client_27b
ANALYST_AGENT = AnalystAgent(ollama_client=get_ollama_client_27b(), ...)
```
周报 AI 分析调用时加 `think=True`（`analyst_agent.py` 中 `_ai_pattern_analysis`）。

---

## 6. PipelineBridge L1 Edge Filter 修复（原代码死路）

### 问题
`PipelineBridge.set_ollama_client()` 方法存在，`_check_edge_filter()` 也判断 `if self._ollama_client`，但**从未在启动代码中被调用**，导致 `_ollama_client` 永远是 `None`，边缘过滤器静默跳过。

### 修复
在 `phase2_strategy_routes.py` Batch 7 注入块中添加：
```python
PIPELINE_BRIDGE.set_ollama_client(OLLAMA_CLIENT)
```

现在 L1 edge filter 正式接入，每次生成 Trade Intent 前会调用 `judge_edge()` 进行过滤。

---

## 7. 后台市场流常驻

### 问题
MarketDataDispatcher 启动逻辑：原来条件判断 `if _sess_state in ("active", "paused")`，关闭 Paper/Demo 会话后市场数据停止积累，再次开启需等待数据重新建立。

### 修改
`phase2_strategy_routes.py` 服务启动代码改为**无条件启动**：

```python
# 旧逻辑：if _sess_state in ("active", "paused"):
# 新逻辑：始终启动
if _paper_ptr.DISPATCHER is None and PIPELINE_BRIDGE is not None:
    _auto_symbols = ["BTCUSDT", "ETHUSDT"]
    _paper_ptr.DISPATCHER = MarketDataDispatcher(engine=_paper_ptr.ENGINE, symbols=_auto_symbols)
    _paper_ptr.DISPATCHER.start()
    _paper_ptr.DISPATCHER.register_tick_consumer(PIPELINE_BRIDGE)
    PIPELINE_BRIDGE.activate()
    logger.info("Background market feed started (always-on, paper_state=%s)", _sess_state)
```

**交易安全不受影响**：PaperTradingEngine 内部有会话状态检查，无活跃会话时拒绝订单，trade 路径安全边界不变。

当前后台流覆盖 BTCUSDT + ETHUSDT（扫描器的 650 对由扫描周期独立运行）。

---

## 8. 周报时间表调整

### 需求
原来：仅周日 UTC 0:00 触发一次 Claude L2 深度分析
新：
- **周三 UTC 0:00**：简报（27B Ollama，`AnalystAgent.analyze_patterns(force=True)`）
- **周日 UTC 0:00**：详报（Claude L2，`Layer2Engine.run_session()`）

### 实现
扩展 `PipelineBridge._try_l2_cron_trigger()`，使用独立去重键防止互相干扰：

```python
week_key = utc_now.strftime("%Y-W%W")

# 周三 - 简报
if weekday == 2 and utc_now.hour == 0:
    brief_key = "brief_" + week_key
    if getattr(self, "_last_l2_brief_week", None) != brief_key:
        self._last_l2_brief_week = brief_key
        self._analyst_agent.analyze_patterns(force=True)

# 周日 - 详报
elif weekday == 6 and utc_now.hour == 0:
    detail_key = "detail_" + week_key
    if getattr(self, "_last_l2_detail_week", None) != detail_key:
        self._last_l2_detail_week = detail_key
        asyncio.ensure_future(engine.run_session(trigger="weekly_cron_sunday", ...))
```

---

## 新增文件清单

| 文件 | 说明 |
|------|------|
| `app/static/tab-trading.html` | 新 Tab：iframe 包装器（子 Tab 切换 Paper/Demo） |
| `app/static/tab-live.html` | 新 Tab：实盘交易锁定占位（前置条件 + 路线图） |

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `app/static/tab-paper.html` | 新增 Account Balance 卡片（排在 PnL 前） |
| `app/static/tab-demo.html` | 新增 PnL Overview 卡片（排在 Account Balance 后） |
| `app/static/tab-settings.html` | 补全 Modal CSS（修复常驻 bug） |
| `app/static/console.html` | Tab 数组重排：移除 paper/demo，加入 trading/live |
| `app/ollama_client.py` | DEFAULT_MODEL 改 9B；think 参数；27B 单例；超时优化 |
| `app/pipeline_bridge.py` | `_try_l2_cron_trigger` 扩展为周三+周日双触发 |
| `app/phase2_strategy_routes.py` | 后台流常驻；注入 ollama_client；AnalystAgent 用 27B |
| `app/analyst_agent.py` | `_ai_pattern_analysis` 加 `think=True` |
| `app/layer2_engine.py` | `_l1_triage_local` max_tokens→100，think=False，timeout→12 |

---

## 已知问题与待后续处理

### 问题（非紧急）
1. **Demo 余额无法通过 API 重置** — Bybit Demo 账户余额须在 Bybit 官网手动补充/重置，无程序化接口
2. **后台流仅覆盖 2 对** — BTCUSDT + ETHUSDT，非全 650 对；全对扫描由 5min 扫描器独立负责，两者并行不冲突
3. **asyncio.ensure_future 同步上下文风险** — `_try_l2_cron_trigger` 是同步函数，在 uvicorn 事件循环运行时 `ensure_future` 正常工作，但若在测试或脱离异步上下文中调用可能报错，后续可改为 `asyncio.get_event_loop().call_soon_threadsafe`
4. **27B 关思考模式仍 ~9.9s** — 对于时效不高的周报可接受，但不应用于同步路径
5. **AnalystAgent 非强制调用仍需 obs ≥ 200** — cron 触发使用 `force=True` 规避，正常情况下观察数不足会跳过
6. **双 iframe 独立轮询** — tab-trading.html 中 Paper iframe 和 Demo iframe 各自独立 API 轮询，无共享状态问题，但产生双倍请求量
7. **无会话时 PipelineBridge.activate() 产生日志噪音** — activate 后 PipelineBridge 可能生成 Trade Intent，Paper Engine 拒绝并记录 INFO 日志，无功能影响但略显嘈杂

### 未做的工作（本 Session 范围外）
- H0 Gate 确定性门控（Phase 1 Batch 1A，最高优先级）
- Learning Cockpit 数据展示（依赖 Analyst 数据积累）
- 全 650 对后台流（资源消耗大，非必须）
- Demo 余额自动补充 API（Bybit 不开放）

---

## 测试状态

本 Session 工作主要在 GUI 层（纯前端 HTML/JS）和少量 Python 逻辑改动，未引入新业务逻辑分支。
原有 2,227 tests passed / 0 failed 基准线维持不变。
Ollama 相关测试（ollama_client.py）修复了 Phase 0 Round 2.5 审计中发现的 3 个 Ollama 测试 bug（大小写不符 + 错误消息 + 逻辑修复）。
