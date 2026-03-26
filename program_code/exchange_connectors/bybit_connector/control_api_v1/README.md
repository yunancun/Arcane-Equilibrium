# OpenClaw / Bybit Control API + GUI V1 RC2

这是当前分支上的 **FastAPI + 内嵌静态 GUI** 默认入口版本。
This is the **FastAPI + embedded static GUI** default-entrypoint version on the current branch.

## 当前状态 / Current status

本版本已经完成以下收口：
This version has already completed the following closeout items:

- 默认启动入口统一为 `app.main:app`
- 默认入口已通过 snapshot identity 稳定性验证
- 旧实现保留为 `app.main_legacy:app`
- 兼容别名保留为 `app.main_snapshot_stable:app`
- 可选接入 `OPENCLAW_RUNTIME_SNAPSHOT_FILE`，从外部 runtime JSON 快照读取真实事实
- 默认保持 protected boundary，不会打开真实执行权限

## 路径 / Location

- 后端代码 / backend  
  `program_code/exchange_connectors/bybit_connector/control_api_v1/app`
- GUI 静态资源 / GUI static files  
  `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static`
- Docker 部署目录 / Docker deployment directory  
  `docker_projects/trading_services/openclaw_bybit_control_api_v1`

## 默认入口 / Default entrypoint

- 默认入口 / default: `app.main:app`
- 旧实现回滚入口 / rollback: `app.main_legacy:app`
- 兼容别名 / compatibility alias: `app.main_snapshot_stable:app`

## Runtime snapshot bridge / Runtime 快照桥接

可选环境变量：
Optional environment variable:

- `OPENCLAW_RUNTIME_SNAPSHOT_FILE=/path/to/runtime_snapshot.json`

当该文件存在时：
When this file exists:

- `source_context` 将优先读取外部 runtime 快照中的连接状态与完整性字段
- `global_runtime.facts` 将优先读取外部 runtime 快照中的归一化事实
- `product_family_status.*.facts` 将优先读取外部 runtime 快照中的产品族事实
- 响应 `snapshot_id` 将绑定 `state snapshot + runtime snapshot`，避免 GUI 混屏

推荐 JSON 结构：
Recommended JSON shape:

```json
{
  "runtime_snapshot_id": "runtime:file:001",
  "runtime_snapshot_ts_ms": 0,
  "readonly_connector_name": "bybit_prod_readonly_main",
  "execution_connector_name": null,
  "rest_private_connection_state": "ready",
  "ws_private_connection_state": "ready",
  "runtime_connection_state": "healthy",
  "account_fact_completeness_state": "complete",
  "source_snapshot_completeness_state": "complete",
  "global_runtime_facts": {
    "system_mode_fact": "shadow_only",
    "execution_state_fact": "execution_disabled",
    "runtime_last_refresh_ts_ms": 0,
    "runtime_data_freshness_state": "fresh"
  },
  "product_family_facts": {
    "spot": {
      "exchange_permission_fact": "readonly_visible",
      "account_permission_fact": "readonly_visible"
    }
  },
  "health_telemetry": {
    "gates": {
      "health_gates_overall_state": "passed"
    }
  }
}
```

## 默认保护边界 / Default protected boundary

默认情况下：
By default:

- `global_execution_mode_switch = disabled`
- `demo_state_switch = closed`
- `runtime_still_protected = true`

它不会直接赋予真实交易执行权限。
It does not directly grant real trading execution authority.

## 本地启动 / Local startup

```bash
cd program_code/exchange_connectors/bybit_connector/control_api_v1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENCLAW_API_TOKEN='change-me'
uvicorn app.main:app --host 0.0.0.0 --port 8710 --reload
```

若要接 runtime 快照：
If you want to connect a runtime snapshot:

```bash
export OPENCLAW_RUNTIME_SNAPSHOT_FILE='/tmp/runtime_snapshot.json'
```

打开：
Open:

- API docs: `http://127.0.0.1:8710/docs`
- GUI: `http://127.0.0.1:8710/gui`

## 测试 / Tests

```bash
cd program_code/exchange_connectors/bybit_connector/control_api_v1
pytest -q
```

## Docker 启动 / Docker startup

```bash
cd docker_projects/trading_services/openclaw_bybit_control_api_v1
docker compose up --build
```

## 审计稳定性 / Audit stability

当前默认入口已经验证通过：
The current default entrypoint has been validated for:

- 连续两次 GET overview 时，`snapshot_id` 不变
- 连续两次 GET overview 时，`snapshot_ts_ms` 不变
- `config-change -> demo_validate -> demo_arm` 能推进到 `armed_but_closed`
- 系统仍保持 protected / guarded 状态，不进入 `demo_enabled`
- runtime snapshot 变更时，响应 `snapshot_id` 会变化，防止 GUI 混屏

## 后续对接 / Next integration step

下一步应当让 OpenClaw runtime 周期性产出标准 JSON 快照文件，并把控制 API 的 GET / POST 判断逐步改为依赖这些真实事实。
The next step should make the OpenClaw runtime periodically emit a normalized JSON snapshot file, then gradually move GET / POST decisions in the control API onto those real facts.
