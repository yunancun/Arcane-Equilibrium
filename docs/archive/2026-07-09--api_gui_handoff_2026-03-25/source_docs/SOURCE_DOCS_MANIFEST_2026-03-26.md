# Source Docs Manifest（2026-03-26）

本清单记录本章节开发最重要的起始依赖文件，确认这些文件已经在当前工作环境中可取得，并标记后续应继续镜像到仓库内 `source_docs/`。

## 已确认可取得的源文件

1. `OpenClaw_Bybit_Control_API_V1_RC2_最终候选版.md`
2. `OpenClaw_Bybit_状态字典_数据字典_V1_最终版.md`
3. `OpenClaw_Bybit_状态字典_V1_RC2_伴随补丁.md`
4. `OpenClaw_Bybit_后端实现清单_V1_RC2.md`
5. `OpenClaw_Bybit_FastAPI_OpenAPI_V1_RC2_路由草案.md`
6. `分支 · OpenClaw Trading Bot Design.txt`

## 文件用途

- Control API 合同：定义统一 envelope、状态码、reason code、source_context 合同
- 状态字典 / 数据字典：定义 canonical 路径、枚举注册表、CFG/ACT/DRV/AUD 边界
- RC2 伴随补丁：补充 risk_envelope、audit_context、GUI snapshot 兼容要求
- 后端实现清单：定义后端工程实现顺序与验收矩阵
- FastAPI / OpenAPI 路由草案：定义路由、鉴权依赖、GUI 对接约束、adapter 原则
- Trading Bot Design：记录早期 key 规划、只读链 / 执行链角色分离、execution 保守策略

## 当前归档状态

- handoff 工作报告：已归档
- source docs 索引：已归档
- source_docs 目录与 README：已建立
- 本 manifest：已归档
- 源文件原文本体：下一步继续逐份镜像进本目录

## 后续镜像要求

1. 优先保持原始文件名
2. 优先保留原文，不要只保留摘要
3. 如需区分多个版本，在文件名中补版本或日期
4. 如暂时无法写入原文，至少保留索引、用途、来源、和接手说明

## 与当前代码最直接相关的关系

- `OpenClaw_Bybit_Control_API_V1_RC2_最终候选版.md`：直接约束 Control API 响应 envelope、POST 行为、source_context
- `OpenClaw_Bybit_状态字典_数据字典_V1_最终版.md`：直接约束 canonical 状态结构与 GUI 所读取的字段
- `OpenClaw_Bybit_FastAPI_OpenAPI_V1_RC2_路由草案.md`：直接约束 GUI 拉取顺序、按钮 gating、以及 OpenClawRuntimeAdapter 原则
- `OpenClaw_Bybit_后端实现清单_V1_RC2.md`：直接定义尚未完成的接口与 GUI 联调门槛
