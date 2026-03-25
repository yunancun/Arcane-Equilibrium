# Snapshot-Stable Local Validation (2026-03-26)

## Purpose

这份说明用于验证新的 `app.main_snapshot_stable:app` 入口是否修复了：

- 相同 `state_revision` 下 `snapshot_id` 漂移
- 纯读取 GET 导致 snapshot identity 刷新

## Local commands

```bash
cd ~/BybitOpenClaw/srv
git fetch origin
git checkout feature/openclaw-bybit-control-api-gui-v1-rc2
git pull origin feature/openclaw-bybit-control-api-gui-v1-rc2

cd ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1
source .venv/bin/activate
export OPENCLAW_API_TOKEN='change-me'
pytest -q tests/test_snapshot_stable_entrypoint.py
uvicorn app.main_snapshot_stable:app --host 0.0.0.0 --port 8710
```

## New terminal checks

```bash
BASE=http://127.0.0.1:8710
TOKEN=change-me

curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/system/overview" | python3 -m json.tool
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/system/overview" | python3 -m json.tool
```

预期：

- 两次返回的 `state_revision` 相同
- 两次返回的 `snapshot_id` 相同
- 两次返回的 `snapshot_ts_ms` 相同

## Guarded control-flow check

```bash
get_rev() {
  curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/system/overview" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["state_revision"])'
}

REV=$(get_rev)
cat <<EOF >/tmp/openclaw_cfg_demo_reserved.json
{
  "request_id": "cfg-demo-reserved-stable",
  "idempotency_key": "cfg-demo-reserved-stable",
  "operator_id": "demo-operator",
  "reason": "set demo reserved for guarded validation",
  "client_ts_ms": 1,
  "expected_state_revision": $REV,
  "expected_previous_state": null,
  "payload": {
    "changes": [
      {
        "path": "global_runtime.controls.global_execution_mode_switch",
        "value": "demo_reserved"
      }
    ]
  }
}
EOF
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$BASE/api/v1/input/config-change" --data @/tmp/openclaw_cfg_demo_reserved.json | python3 -m json.tool

REV=$(get_rev)
cat <<EOF >/tmp/openclaw_validate.json
{
  "request_id": "demo-validate-stable",
  "idempotency_key": "demo-validate-stable",
  "operator_id": "demo-operator",
  "reason": "validate after demo reserved",
  "client_ts_ms": 1,
  "expected_state_revision": $REV,
  "expected_previous_state": null,
  "payload": {}
}
EOF
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$BASE/api/v1/control/demo/validate" --data @/tmp/openclaw_validate.json | python3 -m json.tool

REV=$(get_rev)
cat <<EOF >/tmp/openclaw_arm.json
{
  "request_id": "demo-arm-stable",
  "idempotency_key": "demo-arm-stable",
  "operator_id": "demo-operator",
  "reason": "guarded arm only",
  "client_ts_ms": 1,
  "expected_state_revision": $REV,
  "expected_previous_state": "closed",
  "payload": {
    "acknowledged": true
  }
}
EOF
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$BASE/api/v1/control/demo/arm" --data @/tmp/openclaw_arm.json | python3 -m json.tool
```

预期：

- `config-change` 成功
- `demo_validate` 成功
- `demo_arm` 成功
- `demo_state_switch = armed_but_closed`
- 仍未进入 `demo_enabled`
