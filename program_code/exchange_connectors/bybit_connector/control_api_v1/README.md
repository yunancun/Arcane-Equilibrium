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

## 后续对接 / Next integration step

下一步应当把当前 demo/state 层继续对接到真实 OpenClaw runtime facts，而不是继续扩展本地 demo 假状态。
The next step should connect the current demo/state layer to real OpenClaw runtime facts instead of further expanding local demo-only mocked state.
