# GUI 统一入口预埋布局（OpenClaw Portal Prelayout）

日期：2026-03-26
分支：`feature/openclaw-bybit-control-api-gui-v1-rc2`

---

## 1. 目的

本文件用于提前固定 GUI 未来并入 OpenClaw 时的入口与导航结构，避免后续临时命名、临时挂菜单、临时改路径。

本文件只做：

- 入口预埋
- 命名预埋
- 导航层级预埋

本文件不代表当前已经完成 OpenClaw 一体化接入。

---

## 2. 推荐统一入口命名

### 主入口名称

- 中文：`控制中心`
- 英文：`Control Center`

### 入口说明

该入口应作为 OpenClaw 内部导航的一部分，而不是长期依赖手输：

- `127.0.0.1:8711/gui`

---

## 3. 推荐导航分组

未来并入 OpenClaw 后，建议在左侧或顶部导航预留如下结构：

### A. 控制中心 / Control Center

用于进入当前 Control API GUI 主页面。

### B. 产品配置 / Product Configuration

用于承接：

- spot / 现货产品配置
- margin / 保证金配置
- perp_linear / 线性永续配置
- perp_inverse / 反向永续配置
- options / 期权配置
- other_derivatives_reserved / 其他衍生品（预留）

### C. 经营与收益 / Business & Income

用于承接：

- daily business summary
- 周 / 月切片
- 收益与成本拆分
- 业务事件统计

### D. 审计 / Audit

用于承接：

- latest control action
- latest write action
- raw response / audit refs
- 手工输入与配置变更轨迹

---

## 4. 推荐路径预留

当前先做路径预留约定，后续择一落地。

### 推荐候选路径

- `/control-center`
- `/product-configuration`
- `/business-income`
- `/audit`

如果后续要更贴近运维风格，也可考虑：

- `/ops/control-center`
- `/ops/products`
- `/ops/business`
- `/ops/audit`

---

## 5. 当前阶段与未来阶段的区别

### 当前阶段

当前仍允许：

- 独立运行 GUI
- 通过本地转发访问 `/gui`

### 未来阶段

未来应收口到：

- 从 OpenClaw 主界面一跳进入
- 用户不再手记端口与路径
- 统一鉴权
- 统一导航
- 统一视觉

---

## 6. 当前建议

在当前 API / GUI 章节收口期间，建议先完成：

1. 统一入口命名冻结
2. 导航位命名冻结
3. 产品配置 / 经营收益 / 审计 三个二级入口命名冻结

待主线条件成熟后，再做真正接入。

---

## 7. 一句话结论

当前阶段先把 GUI 做成“能独立使用的控制台”，同时把它未来并入 OpenClaw 所需的入口、路径、导航名字全部预埋好。
