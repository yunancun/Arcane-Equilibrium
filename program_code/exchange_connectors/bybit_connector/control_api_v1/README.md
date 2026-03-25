# OpenClaw / Bybit Control API + GUI V1 RC2

这是一个可直接落地的 **FastAPI + 内嵌静态 GUI** MVP 实现。
This is a deployable **FastAPI + embedded static GUI** MVP implementation.

## 目标 / Goal

本模块用于把你已经冻结的状态字典、Control API RC2 和 GUI 一致性规则，落成一个：
This module turns the frozen state dictionary, Control API RC2, and GUI consistency rules into a practical service that is:

- 可启动 / bootable
- 可本地验证 / locally verifiable
- 可继续对接 OpenClaw runtime / easy to connect to the OpenClaw runtime later
- 默认保持 **execution disabled / protected** / protected by default

## 路径 / Location

- 后端代码 / backend:
  `program_code/exchange_connectors/bybit_connector/control_api_v1/app`
- GUI 静态页 / GUI static files:
  `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static`
- Docker 部署 / Docker deployment:
  `docker_projects/trading_services/openclaw_bybit_control_api_v1`

## 主要能力 / Main capabilities

1. 冻结 `/api/v1` 路由骨架并给出可运行实现  
   Freeze the `/api/v1` route family with a runnable implementation.

2. 提供统一 envelope、`snapshot_id`、`state_revision`、`source_context`  
   Provide the unified envelope, `snapshot_id`, `state_revision`, and `source_context`.

3. 提供 demo 状态机的最小可运行实现  
   Provide a minimal runnable implementation for the demo state machine.

4. 提供 `config-change / cost / event / manual-note` 的受控写入  
   Provide controlled writes for `config-change / cost / event / manual-note`.

5. 提供一个不依赖前端框架的 GUI  
   Provide a GUI that does not require a separate frontend framework.

## 默认边界 / Default boundary

本实现默认：
By default, this implementation keeps:

- `global_execution_mode_switch = disabled`
- `demo_state_switch = closed`
- `runtime_still_protected = true`

它不会打开真实执行权限。
It does not open real execution authority.

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

## 需要你本地帮我验证的命令 / Commands I want you to run locally

```bash
cd ~/srv/program_code/exchange_connectors/bybit_connector/control_api_v1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENCLAW_API_TOKEN='change-me'
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8710
```

然后把以下结果贴给我：
Then paste back:

1. `pytest -q`
2. `curl -s http://127.0.0.1:8710/api/v1/system/overview | jq`
3. 打开 `/gui` 后首页截图或核心错误
   a screenshot of `/gui` or any important errors
