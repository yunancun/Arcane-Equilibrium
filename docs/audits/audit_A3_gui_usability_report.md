# A3 UX 审计报告 — OpenClaw Trading Console GUI

**审计员：** A3 (UX Auditor)
**日期：** 2026-04-05
**范围：** 11-Tab 控制台（console.html）+ 所有子 Tab + 旧版 index.html + 登录页
**严重程度定义：** P0=阻断功能/安全 | P1=重要体验缺陷 | P2=可改善 | P3=建议

---

## 一、死按钮 / 失效控件（Dead Buttons / Dead Controls）

### 1.1 P0 — 功能性死按钮

| # | 文件 | 控件 | 问题 | 严重 |
|---|------|------|------|------|
| D-01 | `tab-risk.html:351` | **"采纳建议 / Apply" 按钮** (`btn-apply-ai`) | `applyAIAdvice()` 函数体只是弹一个 toast 提示"请手动调整"，**没有任何实际功能**。用户看到"采纳建议"会以为点击后自动填入 AI 推荐值，但实际什么都没发生。 | **P1** |
| D-02 | `tab-system.html:83` | **"行情流 Feed" 快捷按钮** | 点击后弹出确认弹窗，但 `executeConfirmed()` 中 feed 分支只是 `ocToast('行情流由 Rust 引擎管理')` — **按钮完全无法控制行情流**，因为行情流已由 Rust 引擎自动管理（RC-12）。按钮仍显示 ON/OFF 状态点，误导用户以为可以手动控制。 | **P1** |
| D-03 | `tab-system.html:85` | **"Bybit Demo" 快捷按钮** | 点击确认后只弹 toast "请前往 Bybit Demo 页面查看连接状态" — **无实际操作**。 | **P1** |
| D-04 | `tab-system.html:86` | **"自动扫描 Scanner" 快捷按钮** | 点击确认后只弹 toast "请前往策略中心查看" — **无实际操作**。 | **P1** |
| D-05 | `tab-risk.html:351` | **"采纳建议" 按钮** `style="display:none"` + 外层 div 也有 `style="display:none"` | **双重 display:none**，`id="ai-advice-actions"` 的父 div 始终隐藏，即使 JS 设置 `btn-apply-ai.style.display=''`，父 div 的 `display:none` 仍生效，按钮**永远不可见**。 | **P0** |

### 1.2 P1 — 旧版页面残留

| # | 文件 | 问题 | 严重 |
|---|------|------|------|
| D-06 | `index.html` | **整个旧版控制面板仍然存在且可访问**（`/gui` 路由）。包含完整的 Paper Trading 交互、Quick Actions 按钮、Token 输入框。与新版 console.html 功能大量重叠，且使用旧版 `app.js`（2602 行）。可能导致用户在旧版页面操作而不知道新版存在。 | **P2** |
| D-07 | `index.html:36-39` | **Bearer Token 输入面板** — 旧版页面仍显示 Token 输入框和 "连接" 按钮，但认证已迁移到 HttpOnly cookie。输入 Token 无实际作用。 | **P1** |
| D-08 | `trading.html` | **独立 K 线图表页面** — 通过 "K线图表" Tab 以 iframe 方式加载 `/trading`。该页面有独立的 header、sidebar、认证逻辑，**但缺少 common.js 的共享工具（ocApi/ocToast 等）**，使用自己的 `getToken()` + `fetch` 模式。 | **P2** |

### 1.3 P2 — 潜在问题

| # | 文件 | 问题 | 严重 |
|---|------|------|------|
| D-09 | `tab-strategy.html:208` | **"Delete" 按钮没有确认弹窗** — 直接调用 `deleteStrategy()` DELETE 端点，无二次确认。删除策略是不可逆操作。 | **P1** |
| D-10 | `tab-ai.html:413-430` | **saveProviderKey() API Key 保存** — 调用 `/api/v1/paper/layer2/config` 传 `provider_keys` 字段，但 layer2_routes.py 的 config 端点**可能不处理 provider_keys 字段**（没有找到 provider_keys 相关后端处理代码）。保存大概率静默失败。 | **P1** |
| D-11 | `tab-ai.html:693-719` | **runEvolution() 手动进化** — 调用 `/api/v1/evolution/run` 以 `ocApi()` + `method: 'POST'` + `body` 方式，但 `ocApi()` 通常不支持 body 参数（它是 GET 封装）。应使用 `ocPost()`。 | **P1** |

---

## 二、设计问题（Design Issues / UX Anti-Patterns）

### 2.1 P0 — 缺失确认弹窗

| # | 位置 | 问题 |
|---|------|------|
| UX-01 | `tab-strategy.html` — Delete 按钮 | 删除策略无确认。其他危险操作（Stop 引擎、Demo Enable）都有确认弹窗，唯独 Delete 没有。 |
| UX-02 | `tab-risk.html` — Danger Zone | "Reset Loss Cooldown" 和 "Unhalt Session" 两个危险操作按钮**没有确认弹窗**，直接执行 POST。 |
| UX-03 | `tab-risk.html` — "保存设置" 按钮 | 存在**三个** "保存设置" 按钮分散在不同区域（止损设置、仓位控制、冷却保护），但三个按钮**调用同一个 `saveRiskConfig()` 函数**，每次保存都发送所有字段。用户可能只改了止损就点保存，但实际上仓位和冷却的当前输入框值也被覆盖。 |

### 2.2 P1 — 缺失加载状态

| # | 位置 | 问题 |
|---|------|------|
| UX-04 | 全局 | **所有 "Save" 按钮缺少加载状态**。点击保存后，按钮没有 disabled/loading 反馈。用户可能重复点击。成功/失败仅靠 toast 提示。 |
| UX-05 | `tab-strategy.html` — createStrategy() | 创建策略后没有禁用提交按钮。用户快速双击可能创建重复策略。 |
| UX-06 | `tab-ai.html` — saveProviderKey() | API Key 保存后没有 loading 状态，也没有验证 key 格式的客户端校验。 |

### 2.3 P1 — 术语不一致

| # | 问题描述 |
|---|---------|
| UX-07 | Tab 标题混合使用中英文：`系统总览` `实盘交易` `测试交易` `K线图表` `策略中心` `风控止损` `AI 引擎` `学习系统` `治理控制` `监控` `设置`。部分用中文（监控），部分用双语（AI 引擎）。建议统一。 |
| UX-08 | "Demo" vs "测试" vs "执行引擎" — Tab 叫"测试交易"，Sub-tab 叫"执行引擎 / Demo (Primary)"，侧栏叫 "Live / 实盘"。三个不同名称指代同一个 Bybit Demo 概念，用户可能困惑。 |
| UX-09 | "Paper" 在不同地方叫：模拟交易 / 纸上交易 / 模拟引擎 / 测试引擎 / Paper Trading。建议统一为一个名称。 |
| UX-10 | "Session" 同时指 Paper Trading Session、AI 推理 Session、Auth Session，三者概念完全不同但共用同一术语。 |

### 2.4 P2 — 状态反馈不足

| # | 位置 | 问题 |
|---|------|------|
| UX-11 | `tab-risk.html` — 三层风控（P0/P1/P2） | P0 Category Limits 卡片仅展示原始数据，当 category_overrides 为空时显示 "Allowed Categories: --"，用户无法理解含义。 |
| UX-12 | `tab-system.html` — 全局模式控制 | 降级模式警告文字说"不会自动停止已运行的服务"，但没有显示**当前有哪些服务正在运行**，用户无法判断降级的实际影响。 |
| UX-13 | `console.html` — 侧栏刷新 | 15 秒自动刷新间隔内没有任何视觉提示表明数据正在更新。用户不知道数据是否最新。 |

---

## 三、优化机会（Optimization Opportunities）

### 3.1 信息密度

| # | 建议 | 优先 |
|---|------|------|
| O-01 | **tab-system.html 信息过载** — 一个 Tab 包含：Runtime Summary + Mode Control + Governance Status + Business Summary + Source Context + Health + Product Families + Confirm Modal。建议拆分为 Dashboard（简要）和 System Details（完整）。 | P2 |
| O-02 | **tab-ai.html 内容过多** — 单页包含：Cost Dashboard + Adaptive Budget + 6 个 Provider 管理卡 + Engine Settings + Consultation Status + Session History + Pricing Table + Experiment Status + Kelly Allocation + Strategy Evolution。建议按功能分组到 sub-tab。 | P2 |
| O-03 | **tab-risk.html 纵向过长** — 用户需要大量滚动才能看到 Danger Zone。止损设置、仓位控制、冷却保护三个区块结构相似但各自独立，可合并为一个可折叠表单。 | P3 |

### 3.2 数据可视化

| # | 建议 | 优先 |
|---|------|------|
| O-04 | **PnL 缺少图表** — Paper 和 Demo 的盈亏只有数字，没有趋势图。trading.html 有 K 线图（TradingView Lightweight Charts），但 PnL 没有等效的可视化。 | P2 |
| O-05 | **Risk Pressure 缺少进度条** — 当前只显示百分比数字。加一个彩色进度条（绿→黄→红）可以大幅提升风险感知度。 | P3 |
| O-06 | **AI Cost 缺少预算使用进度条** — 今日成本/日预算的比例关系不直观。 | P3 |

### 3.3 工作流优化

| # | 建议 | 优先 |
|---|------|------|
| O-07 | **引擎启动流程太长** — 启动双引擎需要：console → 测试交易 Tab → 点"启动引擎" → 弹窗等待余额读取 → 确认启动。可在 System Overview 的快捷按钮区直接提供一键启动。 | P2 |
| O-08 | **风控配置修改后无 diff 确认** — 改了 5 个参数点保存，没有"确认修改内容"的 diff 视图。用户不知道自己实际改了什么。 | P2 |
| O-09 | **策略创建后需手动刷新** — 创建策略后调用了 `loadStrategies()` 但用户可能已经切走。建议创建成功后自动滚动到新策略卡片。 | P3 |

### 3.4 响应式/移动端

| # | 问题 | 优先 |
|---|------|------|
| O-10 | `console.html` 在 860px 以下隐藏侧栏（`@media max-width:860px`），但 Tab 横向滚动条无明显指示。用户可能不知道右侧还有更多 Tab。 | P2 |
| O-11 | `tab-risk.html` 的 `oc-grid-3` 三栏布局在窄屏下没有 media query，P0/P1/P2 三个卡片会水平溢出。 | P2 |
| O-12 | `tab-ai.html` Provider 卡片使用 `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))` 这在手机上可能只显示一列但 API Key 输入框太窄。 | P3 |

---

## 四、反人类设计（Anti-Human Design Issues）

### 4.1 P1 — 隐藏重要控件

| # | 位置 | 问题 |
|---|------|------|
| AH-01 | `tab-risk.html` — Danger Zone | "Reset Loss Cooldown" 和 "Unhalt Session" 是**紧急恢复按钮**，但被放在页面最底部，用户需要向下滚动很久才能找到。当系统因连续亏损冷却或回撤熔断时，用户急需这些按钮但很难快速定位。 |
| AH-02 | `tab-system.html` — Governance Status | 治理状态区块嵌在页面中间，没有视觉突出。当 Auth State 为 FROZEN 或 Risk Level >= 4 时，应该有醒目的全页面警告。 |
| AH-03 | `tab-learning.html` — Auto-Scan Controls | 三个扫描按钮藏在 `<details>` 折叠区中，用户不容易发现。 |

### 4.2 P1 — 误导性标签

| # | 位置 | 问题 |
|---|------|------|
| AH-04 | `tab-system.html` — Feed/Demo/Scanner 快捷按钮 | 这三个按钮看起来是可操作的开关（有 ON/OFF 状态点），但**点击后实际不做任何切换操作**，只弹 toast 提示。状态点的颜色变化基于后台检测，不受点击影响。用户会反复点击试图改变状态。 |
| AH-05 | `tab-risk.html` — "AI 止损建议" | "采纳建议 / Apply" 按钮暗示点击后会自动应用 AI 推荐的参数，但实际只弹提示让用户手动调整。严重违反用户预期。 |
| AH-06 | `tab-risk.html` — 输入框每 15 秒被覆盖 | `loadRiskConfig()` 每 15 秒执行一次，会**用服务端值覆盖用户正在编辑的输入框**。用户可能正在输入新值，结果被自动刷新覆盖。这是非常反直觉的行为。 |

### 4.3 P1 — 危险操作太容易触发

| # | 位置 | 问题 |
|---|------|------|
| AH-07 | `tab-strategy.html` — Delete 按钮 | Delete 按钮紧挨 Stop 和 Pause 按钮，且**没有确认弹窗**。误点直接删除策略。 |
| AH-08 | `tab-settings.html` — Demo Enable | "Enable Demo" 按钮在视觉上与其他按钮无明显区分，但操作影响远大于 Validate/Arm。建议加上颜色区分和确认。 |

### 4.4 P2 — 信息层级缺失

| # | 位置 | 问题 |
|---|------|------|
| AH-09 | `console.html` — 侧栏 | Live 面板默认显示但 opacity 为 0.5（因为 LOCKED），给人"系统有问题"的感觉。实际上这是正常状态（Live 尚未解锁）。建议直接显示 "Live: LOCKED" 文字而不是半透明的占位数据。 |
| AH-10 | `tab-ai.html` — 6 个 Provider 卡片 | 所有 Provider 等权重展示，但大部分是 "未配置" 状态。已配置的 Provider 没有视觉突出。用户需要逐个扫描才能找到已配置的。 |
| AH-11 | `tab-live.html` — 整个 Tab | 该 Tab 展示 8 个前置条件卡片，但**没有任何可交互元素**（除了 governance status 的自动加载）。用户点进来后发现无法做任何操作，只能看。建议加一个明确的 CTA 指向下一步行动。 |

---

## 五、Tab 逐一评估

### Tab 1: 系统总览（tab-system.html）
- **功能性：** 8/10 — 核心指标齐全，模式控制可用
- **问题：** Feed/Demo/Scanner 三个快捷按钮形同虚设（D-02/03/04）；信息过载（O-01）；输入框被自动刷新覆盖问题也存在于此
- **亮点：** Tooltip 悬停说明、模式切换确认弹窗、双语解释区块设计优秀

### Tab 2: 实盘交易（tab-live.html）
- **功能性：** 5/10 — 纯信息展示，无交互
- **问题：** 无 CTA（AH-11）；前置条件状态是硬编码的 dot-done/dot-todo，没有动态检测
- **用途合理：** 作为 Live 未解锁的占位页面，设计意图正确

### Tab 3: 测试交易（tab-trading.html）
- **功能性：** 9/10 — 双引擎控制完整，Sub-tab 切换流畅
- **问题：** 术语不一致（UX-08）
- **亮点：** 启动/停止都有确认弹窗，余额预读显示在弹窗中

### Tab 4: K线图表（trading.html）
- **功能性：** 7/10 — TradingView 图表可用
- **问题：** 独立页面架构，不共享 common.js（D-08）；有独立的认证逻辑
- **亮点：** 专业的图表展示

### Tab 5: 策略中心（tab-strategy.html）
- **功能性：** 9/10 — CRUD 完整，Scanner/Deployed/Intents 信息全面
- **问题：** Delete 无确认（D-09/UX-01/AH-07）
- **亮点：** V2 参数渲染、解释器模式、策略类型中文映射

### Tab 6: 风控止损（tab-risk.html）
- **功能性：** 8/10 — P0/P1/P2 三层展示清晰，编辑功能完整
- **问题：** 输入框被自动刷新覆盖（AH-06）；Apply AI 按钮永远不可见（D-05）；Danger Zone 无确认（UX-02）；三个保存按钮语义不清（UX-03）
- **亮点：** Risk Governor 可视化、H0 Shadow 开关、Dynamic Risk 开关、解释器非常详尽

### Tab 7: AI 引擎（tab-ai.html）
- **功能性：** 8/10 — 成本追踪、Provider 管理、进化引擎、Kelly 资本配置
- **问题：** Provider Key 保存可能失效（D-10）；runEvolution 调用方式错误（D-11）；单页内容过多（O-02）
- **亮点：** Ollama 状态自动检测、预估成本显示

### Tab 8: 学习系统（tab-learning.html）
- **功能性：** 7/10 — Review Queue 可操作，Feed 展示清晰
- **问题：** Auto-Scan 藏太深（AH-03）
- **亮点：** 科学方法论的学习循环设计

### Tab 9: 治理控制（tab-governance.html）
- **功能性：** 9/10 — 4 张卡片覆盖 SM-01/SM-04/SM-02/EX-04
- **问题：** 使用独立的 governance.js，需确保函数定义存在
- **亮点：** Auth Scope 可视化、Risk De-escalate 有原因输入

### Tab 10: 监控（tab-monitoring.html）
- **功能性：** 6/10 — Grafana 嵌入 + 组件状态
- **问题：** Grafana URL 硬编码为 `http://trade-core:3000`，在外部网络不可达；组件状态卡片数据可能缺失
- **亮点：** Fallback UI 在 Grafana 不可用时清晰展示

### Tab 11: 设置（tab-settings.html）
- **功能性：** 8/10 — Demo Control Plane、Product Family Config、Config Change、Scheduled Restart
- **问题：** 有多步确认的重启流程设计良好，但 "Enable Demo" 按钮区分度不够（AH-08）
- **亮点：** 重启确认的多步流程

---

## 六、汇总与优先级排序

### 必须修复（P0/P1 — 影响功能或安全）

| 编号 | 问题 | 建议修复 |
|------|------|---------|
| D-05 | AI 建议 Apply 按钮双重 display:none 永远不可见 | 移除父 div 的 `style="display:none"`，改由 JS 控制 |
| AH-06 | 输入框被 15 秒自动刷新覆盖 | 只在首次加载时填入 input 值，后续刷新只更新"当前生效值"显示区。或检测 input 是否 focused，focused 时跳过覆盖 |
| D-09/UX-01 | Delete 策略无确认弹窗 | 添加确认弹窗，至少需要用户确认策略名称 |
| UX-02 | Danger Zone 操作无确认 | 添加确认弹窗，显示当前状态和操作后果 |
| D-02/03/04 | Feed/Demo/Scanner 快捷按钮无功能 | 要么移除这三个按钮的"开关"外观（改为只读状态指示器），要么实现实际的控制逻辑 |
| D-10 | Provider Key 保存可能静默失败 | 验证后端是否处理 provider_keys；若不支持，给出明确的错误提示而非静默失败 |
| D-11 | runEvolution() 使用 ocApi + body | 改用 `ocPost('/api/v1/evolution/run', {...})` |
| UX-03 | 三个保存按钮调用同一函数 | 拆分为三个独立的保存函数，或在保存前显示 diff |

### 建议改善（P2 — 提升体验）

| 编号 | 问题 | 建议 |
|------|------|------|
| AH-04 | 快捷按钮误导性 ON/OFF 外观 | 改为不可点击的状态指示器，移除 onclick |
| AH-09 | Live 面板半透明误导 | 改为明确的 "LOCKED" 文字说明 |
| D-06/D-07 | 旧版 index.html 残留 | 考虑移除或将 `/gui` 重定向到 `/console` |
| O-01/O-02 | 信息过载 | 考虑 sub-tab 分组 |
| O-04 | PnL 缺少趋势图 | 添加简单的折线图 |
| UX-04 | Save 按钮缺少 loading 状态 | 添加 disabled + spinner |

---

## 七、亮点（正面评价）

1. **解释器模式（Explainer Pattern）** — 每个区块都有"新手/专家"双层解释，降低了专业交易系统的学习门槛
2. **确认弹窗体系** — 引擎启动/停止、模式切换等关键操作都有详尽的确认弹窗，包含影响说明和警告
3. **双语支持** — 中英文标签贯穿全站，适合双语用户
4. **Currency Toggle** — 全局货币切换（USDT/USD/EUR）配合 `occurrencychange` 事件广播，所有 Tab 同步更新
5. **Lazy Loading Iframes** — 只在切换到对应 Tab 时才加载 iframe，节省初始加载时间
6. **HttpOnly Cookie 认证** — 已完成从 localStorage Token 到 HttpOnly Cookie 的迁移，安全性良好
7. **Server-ready Polling** — `waitForServerUp()` 替代固定 2s 延迟，服务重启后体验更好
8. **Risk Governor 可视化** — 6 级风险等级 + 颜色编码 + 降级审批流程，设计合理
9. **Toast 通知系统** — 全局 toast 提供一致的操作反馈

---

*报告结束。建议优先处理 P0/P1 问题，特别是 AH-06（输入框覆盖）和 D-05（Apply 按钮不可见），这两个直接影响用户日常操作。*
