# Uploaded Source Files Locator（2026-03-26）

本文件记录本章节关键源文件在当前工作环境中的**已上传原件**定位信息，方便后续对话或接手者快速核对、查找、比对哈希，并继续完成原文镜像。

## 说明

- 本文件记录的是当前对话工作环境内可取得的上传原件信息
- `source_docs/` 目录中的镜像文件用于 GitHub 内部 handoff 与长期留档
- 若某份原文镜像尚未完整写入仓库，可优先按本定位文件回找上传原件

## 文件清单

### 1. OpenClaw_Bybit_状态字典_数据字典_V1_最终版.md
- 环境路径：`/mnt/data/OpenClaw_Bybit_状态字典_数据字典_V1_最终版.md`
- 大小：`45883` bytes
- SHA256：`ac21f4b365a2b0d483d8e5424552b12bfc5d7e507aad83346c8e3b06a90f121b`
- 用途：冻结顶层块、canonical ownership matrix、枚举注册表、CFG / ACT / DRV / AUD 边界

### 2. OpenClaw_Bybit_Control_API_V1_最终定稿.md
- 环境路径：`/mnt/data/OpenClaw_Bybit_Control_API_V1_最终定稿.md`
- 大小：`23990` bytes
- SHA256：`955f8ed586e7e5aba482aea29df9981b07073b7a918fffcb819c9bcc5e18fd26`
- 用途：Control API V1 最终定稿合同、统一 envelope、状态码、并发与幂等要求

### 3. OpenClaw_Bybit_Control_API_V1_RC2_最终候选版.md
- 环境路径：`/mnt/data/OpenClaw_Bybit_Control_API_V1_RC2_最终候选版.md`
- 大小：`26278` bytes
- SHA256：`9c563947aadf72290b0f872bb5a8432be640f830e1e26641abb3975af265128a`
- 用途：RC2 候选版合同、`snapshot_id`、`source_context`、guarded bundle 一致性规则

### 4. OpenClaw_Bybit_FastAPI_OpenAPI_V1_RC2_路由草案.md
- 环境路径：`/mnt/data/OpenClaw_Bybit_FastAPI_OpenAPI_V1_RC2_路由草案.md`
- 大小：`11568` bytes
- SHA256：`076d15585e79aaa559308497e253c70e3760ff2fb1372ef404c74079c5673889`
- 用途：FastAPI / OpenAPI 路由清单、依赖注入、GUI 对接约束、OpenClawRuntimeAdapter 原则

### 5. OpenClaw_Bybit_后端实现清单_V1_RC2.md
- 环境路径：`/mnt/data/OpenClaw_Bybit_后端实现清单_V1_RC2.md`
- 大小：`7285` bytes
- SHA256：`6cba0dd116ead9636018fb10c5a50648b2e0761d301a6261eb6db4b5e0a8b113`
- 用途：后端工程执行顺序、验收矩阵、状态编译器、路由与 GUI 联调门槛

### 6. OpenClaw_Bybit_状态字典_V1_RC2_伴随补丁.md
- 环境路径：`/mnt/data/OpenClaw_Bybit_状态字典_V1_RC2_伴随补丁.md`
- 大小：`6450` bytes
- SHA256：`bd675a1d70778d954b9b06600604e4bd5af76726a36ff19144674ea94c55fe39`
- 用途：补足 `risk_envelope`、`audit_context`、来源枚举、GUI snapshot 兼容要求

### 7. 分支 · OpenClaw Trading Bot Design.txt
- 环境路径：`/mnt/data/分支 · OpenClaw Trading Bot Design.txt`
- 大小：`4423` bytes
- SHA256：`c549379197296e4ba24a9392952dd8ca38c2e98f30cc7a1055931a43248eac64`
- 用途：早期 Bybit key 规划、只读链 / 执行链角色分离、execution 保守策略

## 当前镜像状态

- 已镜像到仓库：
  - `OpenClaw_Bybit_状态字典_V1_RC2_伴随补丁.md`
- 已建立 README / INDEX / MANIFEST / LOCATOR：
  - `README.md`
  - `SOURCE_DOCS_MANIFEST_2026-03-26.md`
  - `UPLOADED_SOURCE_FILES_LOCATOR_2026-03-26.md`
- 其余原件：
  - 当前可通过本文件先定位并核对
  - 后续继续逐份写入仓库镜像

## 建议接手顺序

1. 先读 `WORKLOG_2026-03-25.md`
2. 再读 `SOURCE_DOCS_INDEX.md`
3. 再读本 locator
4. 然后逐份把尚未镜像的原件继续写入 `source_docs/`
