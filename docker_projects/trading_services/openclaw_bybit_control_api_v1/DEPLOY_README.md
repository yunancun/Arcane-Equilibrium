# OpenClaw / Bybit Control API V1 部署说明

## 目的 / Purpose

这份说明用于部署当前默认入口版本：
This document is for deploying the current default-entrypoint version:

- 默认入口 / default entrypoint: `app.main:app`
- 回滚入口 / rollback entrypoint: `app.main_legacy:app`
- 兼容别名 / compatibility alias: `app.main_snapshot_stable:app`

## 代码位置 / Code location

- API + GUI 代码：`program_code/exchange_connectors/bybit_connector/control_api_v1`
- Compose 部署目录：`docker_projects/trading_services/openclaw_bybit_control_api_v1`

## 本地 Python 启动 / Local Python startup

```bash
cd ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENCLAW_API_TOKEN='change-me'
uvicorn app.main:app --host 0.0.0.0 --port 8710
```

## Docker Compose 启动 / Docker Compose startup

```bash
cd ~/BybitOpenClaw/srv/docker_projects/trading_services/openclaw_bybit_control_api_v1
mkdir -p runtime
docker compose up --build -d
```

## 停止 / Stop

```bash
cd ~/BybitOpenClaw/srv/docker_projects/trading_services/openclaw_bybit_control_api_v1
docker compose down
```

## 访问地址 / Endpoints

- API Docs: `http://127.0.0.1:8710/docs`
- GUI: `http://127.0.0.1:8710/gui`
- Overview API: `http://127.0.0.1:8710/api/v1/system/overview`

## 推荐环境变量 / Recommended environment variables

```bash
export OPENCLAW_API_TOKEN='change-me'
export OPENCLAW_READONLY_CONNECTOR_NAME='bybit_prod_readonly_main'
export OPENCLAW_EXECUTION_CONNECTOR_NAME=''
export OPENCLAW_REST_PRIVATE_CONNECTION_STATE='ready'
export OPENCLAW_WS_PRIVATE_CONNECTION_STATE='ready'
export OPENCLAW_RUNTIME_CONNECTION_STATE='healthy'
export OPENCLAW_ACCOUNT_FACT_COMPLETENESS_STATE='complete'
export OPENCLAW_SOURCE_SNAPSHOT_COMPLETENESS_STATE='complete'
```

## 已验证行为 / Validated behavior

当前默认入口已经验证通过：
The current default entrypoint has already been validated for:

- 纯读取不会刷新 `snapshot_id`
- 纯读取不会刷新 `snapshot_ts_ms`
- `config-change -> demo_validate -> demo_arm` 可以推进到 `armed_but_closed`
- 系统仍保持 guarded / protected，不进入 `demo_enabled`

## 排错 / Troubleshooting

### 1. 端口占用 / Port already in use

```bash
fuser -k 8710/tcp 2>/dev/null || true
```

### 2. 想做干净验证 / Need a clean verification state file

```bash
export OPENCLAW_STATE_FILE='/tmp/openclaw_control_api_final_verify.json'
rm -f "$OPENCLAW_STATE_FILE"
```

### 3. 需要回滚旧入口 / Need rollback

```bash
uvicorn app.main_legacy:app --host 0.0.0.0 --port 8710
```
