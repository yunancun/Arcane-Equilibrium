# GUI 统一入口与 OpenClaw 集成任务

## 任务级别

- 阶段：后期正式任务 / later formal task
- 优先级：中高
- 状态：已登记，待后续实现

## 任务目标

解决当前 Control API GUI 需要记忆单独地址、单独端口、单独入口的问题。

## 目标形态

### 方案 A：OpenClaw 内部入口按钮

在 OpenClaw 主界面中增加固定入口，例如：

- `控制中心 / Control Center`
- `进入 Bybit 控制台 / Open Bybit GUI`

要求：

- 用户不再手工记忆 `127.0.0.1:8711/gui`
- 从 OpenClaw 主界面一跳进入

### 方案 B：GUI 作为 OpenClaw 内置页面

把当前 Control API GUI 正式并入 OpenClaw 页面体系，例如：

- `/control-center`
- `/ops/bybit`
- `/admin/control`

要求：

- 不再作为独立小站维护
- 统一菜单、统一导航、统一鉴权、统一视觉体系

### 方案 C：统一入口反向代理

通过反向代理或固定主域名路径，把 GUI 暴露为稳定入口，例如：

- `/control-center`
- `/gui/bybit`

要求：

- 隐藏端口号
- 提供稳定地址

## 推荐顺序

1. 先做方案 A：在 OpenClaw 中增加入口按钮
2. 再做方案 C：统一固定路径
3. 最后视前端架构决定是否做方案 B：正式并入 OpenClaw 内页

## 与当前 GUI 主线的关系

本任务不阻塞当前 GUI 成品化，但应在以下三项完成后尽快进入：

1. GUI 全量双语优化
2. 运行模式控制区成品化
3. business / income summary 区成品化

## 备注

当前临时访问方式仍为：

- 通过 SSH 本地转发后打开 `http://127.0.0.1:8711/gui`

该方式只作为开发阶段入口，不应作为长期正式使用方式。
