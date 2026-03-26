# 2026-03-25 API / GUI 章节重要源文件索引

本索引用于让下一次对话快速找到本章节最关键的源文件、约束文档和设计前置文件。

## 建议归档目录

- `docs/handoffs/2026-03-25_api_gui_handoff/`
- `docs/handoffs/2026-03-25_api_gui_handoff/source_docs/`

## 本章节最重要的源文件

1. `OpenClaw_Bybit_Control_API_V1_RC2_最终候选版.md`
   - 用途：Control API 合同、请求/响应 envelope、HTTP 状态码、reason code、source_context 合同

2. `OpenClaw_Bybit_状态字典_数据字典_V1_最终版.md`
   - 用途：状态字典 canonical 路径、枚举注册表、CFG/ACT/DRV/AUD 边界、产品族与控制平面数据字典

3. `OpenClaw_Bybit_状态字典_V1_RC2_伴随补丁.md`
   - 用途：RC2 对齐补丁，补足 risk_envelope、audit_context、GUI snapshot_id 兼容要求、config-change 白名单边界

4. `OpenClaw_Bybit_后端实现清单_V1_RC2.md`
   - 用途：后端工程执行顺序、验收矩阵、适配器骨架、状态编译器与路由完成清单

5. `OpenClaw_Bybit_FastAPI_OpenAPI_V1_RC2_路由草案.md`
   - 用途：FastAPI / OpenAPI 路由、鉴权依赖、GUI 对接约束、OpenClawRuntimeAdapter 接入原则

6. `分支 · OpenClaw Trading Bot Design.txt`
   - 用途：更早期的 Bybit key 规划、只读链 / 执行链角色分离、execution 保守规划思路

## 当前仓库中必须优先查看的位置

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/runtime_bridge.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/index.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/styles.css`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/scripts/runtime_snapshot_contract.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/scripts/validate_runtime_snapshot.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/scripts/generate_runtime_snapshot.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/scripts/generate_runtime_snapshot_from_directory.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/scripts/runtime_snapshot_providers.py`

## 接手建议

下一次继续时，优先顺序：

1. 先读 `WORKLOG_2026-03-25.md`
2. 再读本索引
3. 再读 Control API 合同 / 状态字典 / 路由草案
4. 最后再看当前代码与最近提交
