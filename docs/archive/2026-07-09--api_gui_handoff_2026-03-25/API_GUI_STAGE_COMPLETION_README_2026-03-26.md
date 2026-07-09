# OpenClaw / Bybit Control API & GUI 阶段性完工 README

日期：2026-03-26
分支：`feature/openclaw-bybit-control-api-gui-v1-rc2`

---

## 1. 本文件目的

本文件用于记录当前 OpenClaw / Bybit Control API 与 GUI 章节的阶段性完工状态，明确：

- 已经完成了什么
- 还需要继续做什么
- 哪些内容适合现在提前预留
- 哪些内容不适合现在提前开放
- 后续回到主线前，应把哪些收尾工作先做扎实

本文件是后续继续推进 GUI/API 与回归主线之间的桥接说明。

---

## 2. 当前阶段总体判断

### 2.1 API 进度判断

当前 API 进度约为：**80% - 85%**

当前 API 已经进入：

- 可用
- 可联调
- 可继续扩展

但尚未进入：

- 最终冻结
- 最终部署封板
- 与主线 runtime / OpenClaw 全量深度集成完成

### 2.2 GUI 进度判断

当前 GUI 进度约为：**65% - 75%**

当前 GUI 已经进入：

- 可打开
- 可连接
- 可查看核心状态
- 可执行受保护动作
- 可进行阶段性联调

但尚未进入：

- 最终成品化
- 完整配置台
- OpenClaw 一体化入口
- 长期正式运行形态

### 2.3 当前阶段目标

当前章节的合理目标不是“绝对意义上的全部做完”，而是：

- 把 API 和 GUI 尽量做到**阶段性完工**
- 把该预留的结构和入口预留出来
- 把后续继续开展工作的准备工作先布好
- 在不误开高权限能力的前提下，把控制台收口到“可继续长期演进”的状态

---

## 3. 当前已经完成的主要工作

### 3.1 Control API 主骨架

已完成：

- 统一响应 envelope
- 认证 token 接入
- 主要 GET 路由
- 关键控制 POST 路由
- 基础 config-change / manual-note / demo validate / demo arm
- runtime snapshot bridge
- source-context / product-families / overview / health / audit-summary 等核心接口

### 3.2 Runtime / Source Context 联动

已完成：

- runtime snapshot 文件桥接
- source context 基础编译
- product family facts 接入与展示
- pinned runtime snapshot 关联

### 3.3 API 合同与测试

已完成：

- 多轮 pytest 通过
- runtime snapshot validator 修正
- snapshot-stable 相关测试修正
- runtime bridge overview mode mapping 修正

### 3.4 GUI 主界面

已完成：

- 基础仪表盘
- source context 区
- health summary 区
- product family facts 区
- quick actions 区
- raw json 调试区
- 运行模式控制区
- business / income summary 区

### 3.5 GUI 交互与 UX

已完成：

- 关键动作二次确认弹窗
- 双语表达初步优化
- 关键概念提示折叠
- 文案逐步改为更易懂的人话
- 产品族配置独立卡片骨架

### 3.6 文档与 handoff 链

已完成：

- `WORKLOG_2026-03-25.md`
- `SOURCE_DOCS_INDEX.md`
- `SOURCE_DOCS_MANIFEST_2026-03-26.md`
- `UPLOADED_SOURCE_FILES_LOCATOR_2026-03-26.md`
- `GUI_PORTAL_AND_OPENCLAW_INTEGRATION_TASK.md`
- `GUI_TEXT_REWRITE_AND_PRODUCT_CONFIG_NOTE_2026-03-26.md`
- 部分 source docs 镜像

---

## 4. 当前还没有完全完成的工作

### 4.1 API 还需要继续补强

1. 产品族配置写接口边界进一步明确
2. learning / hypotheses 页面与接口真实化
3. business / income summary 更深的数据来源对接
4. 更完整的 bundle / guarded flow 收口
5. 与主线 runtime / OpenClaw 的更深层对接
6. 最终部署方式收口

### 4.2 GUI 还需要继续补强

1. 产品族配置卡片从“摘要”升级为“可配置区”
2. 更多产品族专属设置入口
3. business / income 区更丰富的时间维度
4. 页面组织进一步成品化
5. 与 OpenClaw 主界面的统一入口
6. 更长期正式使用路径

---

## 5. 现在适合提前预留的内容

以下内容建议在当前章节里**尽早预埋结构**，但不必马上全部开放。

### 5.1 GUI 统一入口预埋

应提前预留：

- OpenClaw 主界面入口按钮位
- GUI 固定路径命名位
- 控制中心页面命名位

建议目标：

- `控制中心 / Control Center`
- `产品配置 / Product Configuration`
- `经营与收益 / Business & Income`
- `审计 / Audit`

### 5.2 产品族配置位预埋

应提前预留以下产品族配置槽位：

- spot / 现货
- margin / 保证金
- perp_linear / 线性永续
- perp_inverse / 反向永续
- options / 期权
- other_derivatives_reserved / 其他衍生品（预留）

### 5.3 模式权限结构预埋

应提前保留展示与结构位：

- observe only
- demo reserved
- demo enabled
- live locked

即使暂时不开放，也应在结构上留位。

### 5.4 产品族专属设置入口预埋

后续每个产品族建议逐步具备：

- enabled / disabled
- visible / hidden
- mode
- risk profile
- per-family guard
- settings button

当前阶段不必全部开放，但适合保留“设置入口占位”。

---

## 6. 当前不适合提前开放的内容

以下内容当前不建议提前做成真正可用能力：

### 6.1 live 相关真实开关

原因：

- 会把当前章节从“受保护控制面”拉向“真实执行面”
- 主线 runtime 与安全收口尚未完成

### 6.2 更复杂的自动化执行开关

原因：

- 当前 GUI/API 章节重点仍然是控制面与验证面
- 自动化执行属于主线后续更高风险内容

### 6.3 过细的风险参数编辑器

原因：

- 当前阶段先做结构预埋更合理
- 过早细化会分散当前章节收尾精力

### 6.4 大规模视觉工程

原因：

- 当前最重要的是可读性、正确性、结构完整性
- 不是花大量时间做纯视觉抛光

---

## 7. 当前阶段推荐继续推进的顺序

### 第一优先级：章节收口

1. 把 GUI 当前结构收口到稳定可演示状态
2. 把产品族配置卡片骨架做稳
3. 把关键文案继续修到足够清楚
4. 把 API / GUI 当前状态补齐到“阶段性完工”

### 第二优先级：预埋而不误开

1. 预留 GUI 统一入口位
2. 预留产品族设置入口位
3. 预留更多模式层级展示位
4. 预留 OpenClaw 一体化命名与导航位

### 第三优先级：回归主线

待本章节达到“阶段性完工 + 预埋齐备”后，再回归推进主线。

---

## 8. 当前阶段的建议结论

### 建议 1

本章节当前目标应定义为：

- **阶段性完工**
- **结构预留完成**
- **后续继续开展工作的准备就绪**

而不是追求此刻就把所有未来能力一次性做完。

### 建议 2

现在最值得做的是：

- 把控制台结构做稳
- 把产品族配置区做成真正的后续承接点
- 把 GUI 和 OpenClaw 的一体化入口预埋下来

### 建议 3

现在最不该做的是：

- 提前开放 live
- 提前开放自动化真实执行
- 在主线未封板前做过高权限控制入口

---

## 9. 后续接手时先看什么

建议后续接手顺序：

1. 本文件
2. `WORKLOG_2026-03-25.md`
3. `API_GUI_NEXT_STEPS_2026-03-26.md`
4. `GUI_PORTAL_AND_OPENCLAW_INTEGRATION_TASK.md`
5. `GUI_TEXT_REWRITE_AND_PRODUCT_CONFIG_NOTE_2026-03-26.md`
6. `source_docs/README.md`
7. 当前分支下最新 GUI / API 代码

---

## 10. 本文件结论一句话版

当前 OpenClaw / Bybit Control API 与 GUI 章节已经不再是“起步阶段”，而是进入了：

**可用、可联调、可阶段性完工、适合做结构预埋并准备回归主线** 的阶段。
