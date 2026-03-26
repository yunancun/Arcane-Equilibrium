# 长期开关预留方案（Long-Term Switches Preset）

日期：2026-03-26
分支：`feature/openclaw-bybit-control-api-gui-v1-rc2`

---

## 1. 目的

本文件用于定义：

- 哪些长期开关应在当前章节提前预埋
- 哪些开关当前只能做显示或禁用占位
- 哪些开关绝不能在当前章节提前开放

本文件服务于 API / GUI 阶段性收口，不代表这些能力现在已经可用。

---

## 2. 当前建议预埋的长期开关

### 2.1 全局模式层

建议预留显示位 / 锁定位：

- Observe Only / 仅观察
- Demo Reserved
- Demo Enabled
- Live Locked

当前要求：

- 允许显示
- 允许解释含义
- 不允许在当前章节做成真正 live 开关

### 2.2 安全控制层

建议预留显示位 / 锁定位：

- Emergency Relock / 紧急回锁
- Readonly Maintenance / 只读维护模式
- Automation Locked / 自动化锁定
- Audit Enhanced / 审计增强（只读）

当前要求：

- 可以先做成禁用按钮或状态芯片
- 不在当前章节开放真实自动化执行能力

### 2.3 产品族层

建议预留：

- spot / 现货
- margin / 保证金
- perp_linear / 线性永续
- perp_inverse / 反向永续
- options / 期权
- other_derivatives_reserved / 其他衍生品（预留）

当前要求：

- 允许展示配置摘要
- 允许展示未来设置入口占位
- 不要求当前章节提供全部可修改能力

---

## 3. 当前明确不应提前开放的内容

### 3.1 Live 真正开放

当前禁止：

- 真实 live execute 开关
- 容易被误解为“已经可真实执行”的按钮

### 3.2 自动化真实执行

当前禁止：

- 自动化策略真实放权
- 自动化真实交易开关

### 3.3 高风险参数编辑器

当前禁止：

- 复杂风险参数直接编辑
- 过深的执行参数控制入口

---

## 4. GUI 推荐表现形式

当前阶段建议采用：

1. 状态芯片
2. 锁定按钮
3. 占位说明文案
4. 二次确认预留结构

不建议采用：

1. 可立即生效的高权限按钮
2. 一点即改的真实执行型设置

---

## 5. 推荐在 GUI 中的预留项

建议后续 GUI 出现一个“长期控制预留 / Long-Term Control Preset”或类似区块，用于展示：

- Observe Only
- Demo Reserved
- Demo Enabled
- Live Locked
- Emergency Relock
- Automation Locked
- Readonly Maintenance
- Audit Enhanced

当前它们都应表现为：

- 状态说明
- 禁用按钮
- 未来开放提示

---

## 6. 一句话结论

当前章节正确的做法不是“把长期开关做活”，而是“把长期开关的位置、名字、层级和风险边界全部预埋好”。
