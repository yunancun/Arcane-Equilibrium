# OpenClaw / Bybit API + GUI 下一阶段推进清单（2026-03-26）

## 1. 当前状态

当前 GUI / API 章节已经从原始调试页推进到 **runtime-aware 控制台骨架**。

已经具备：

- 默认入口统一到 `app.main:app`
- snapshot identity 稳定性
- guarded demo 控制链路
- runtime snapshot bridge
- runtime snapshot generator / validator / provider
- GUI 摘要卡、产品族表格、动作摘要、折叠调试区

## 2. 目前仍明显缺失的内容

### 2.1 GUI 仍未全量双语

当前仍存在大量仅英文显示的字段和状态，例如：

- summary label
- table header
- raw debug section label
- action result hint
- runtime / capability / execution state 值

下一阶段要求：

- 所有可见文本统一为 **中英双语**
- 不是只改标题，而是字段名、按钮结果、错误摘要、模式提示都双语

### 2.2 运行模式控制区仍不完整

当前只有：

- `set-demo-mode`
- `validate`
- `arm-demo`
- `enable-spot`

但还缺：

- observe / shadow / demo / live 的统一模式区
- 当前允许切换什么、禁止切换什么的明确提示
- live mode 的锁定说明与保护边界
- mode control 与 canonical gate 的一一对应

### 2.3 business / income summary 尚未进入 GUI 主体

虽然 overview 已经有 `daily_business_summary` 骨架，但 GUI 还没有正式 business 面板。

需要补的内容：

- realized pnl
- unrealized pnl
- gross pnl
- total cost
- net operating pnl
- business event count
- reporting currency / valuation basis / fx rate source

### 2.4 learning 区仍为空缺

后续需决定：

- learning summary 是否先做只读展示
- 是否需要单独的 learning / audit / observation 区块

## 3. 下一阶段推荐顺序

### 第一优先级

1. 全量双语化 GUI
2. 补“运行模式控制区”正式面板
3. 补 business / income summary 面板

### 第二优先级

4. 继续压缩 raw JSON 在主界面的存在感
5. 增加 GUI 与 runtime snapshot 联调测试
6. 把 mode control 与 canonical gate 的映射写成固定规则

### 第三优先级

7. 接真实 OpenClaw runtime exporter
8. 做 learning 区
9. 最终工程审计与 GUI/API/runtime 一致性收口

## 4. 开发原则

1. 先验证，后开发
2. 所有高风险动作保持 protected boundary
3. GUI 不得自行推导未经确认的控制状态
4. 所有按钮可点条件必须能追溯到 canonical field 或 runtime snapshot field
5. live 相关动作在没有完整审计链前不得开放

## 5. 明确结论

当前这套 GUI：

- 已经可以视为“控制台底座”
- 但还不能视为“最终成品控制台”

后续继续时，应优先推进 **双语化 + 模式区 + business 区**，而不是继续扩 raw JSON。
