import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "helper_scripts"
SCRIPT = HELPER / "restart_all.sh"


def test_keep_auth_warns_when_live_auth_is_absent() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "warn_keep_auth_missing_authorization()" in text
    assert "--keep-auth requested but signed live authorization is missing" in text
    assert "restart will preserve auth absence" in text
    assert "/api/v1/live/auth/renew" in text
    assert 'BYBIT_SECRETS_DIR="${OPENCLAW_SECRETS_DIR:-$SECRETS_ROOT/secret_files/bybit}"' in text
    assert 'local auth_path="$live_dir/authorization.json"' in text
    assert '[[ ! -s "$api_key" || ! -s "$api_secret" ]]' in text


def test_keep_auth_preflight_runs_after_secret_preparation_before_restart() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    prepare_index = text.index("prepare_runtime_secret_files\n")
    preflight_index = text.index("warn_keep_auth_missing_authorization\n")
    case_index = text.index('case "$SCOPE" in')
    assert prepare_index < preflight_index < case_index


def test_engine_socket_gate_uses_same_ipc_socket_as_engine_and_api() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'ENGINE_SOCKET="${OPENCLAW_IPC_SOCKET:-$DATA_DIR/engine.sock}"' in text
    # 灰度逐-tick 捕捉現預設關閉（避免 engine_results.jsonl ~300GB/天 NVMe 寫入），改為
    # env-overridable `${OPENCLAW_CANARY_MODE:-0}`；斷言對齊新 engine 啟動行字面值。
    assert (
        'OPENCLAW_IPC_SOCKET="$ENGINE_SOCKET" OPENCLAW_CANARY_MODE="${OPENCLAW_CANARY_MODE:-0}"'
        in text
    )
    assert 'OPENCLAW_IPC_SOCKET="$ENGINE_SOCKET" \\' in text
    assert 'local sock="$ENGINE_SOCKET"' in text
    assert 'engine.sock ready at ${ENGINE_SOCKET}' in text


def test_canary_mode_is_default_off_across_all_deploy_surfaces() -> None:
    """灰度逐-tick 捕捉須在所有部署面預設關閉，不得任一處硬寫 =1。

    捕捉 ~300GB/天 NVMe churn 的回歸：穩態無消費者，三 shell 啟動行須 env-overridable
    `${OPENCLAW_CANARY_MODE:-0}`，systemd/plist 須 =0。任何重新硬寫 =1 即回歸。
    """
    # 三 shell 啟動腳本：必須 env-overridable 預設 0，且不得殘留硬寫 =1。
    for name in ("restart_all.sh", "fresh_start.sh", "clean_restart.sh"):
        text = (HELPER / name).read_text(encoding="utf-8")
        assert (
            'OPENCLAW_CANARY_MODE="${OPENCLAW_CANARY_MODE:-0}"' in text
        ), f"{name} canary 啟動 env 非 default-off overridable"
        # 註解可提到 `OPENCLAW_CANARY_MODE=1 ./...` 作為 on-demand 用法，但實際指派行
        # （行首非 # 的 `OPENCLAW_CANARY_MODE=1`）不得存在。
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            assert not re.search(r"\bOPENCLAW_CANARY_MODE=1\b", stripped), (
                f"{name} 殘留硬寫 OPENCLAW_CANARY_MODE=1: {line!r}"
            )

    svc = (HELPER / "systemd" / "openclaw-engine.service").read_text(encoding="utf-8")
    assert 'Environment="OPENCLAW_CANARY_MODE=0"' in svc
    assert 'Environment="OPENCLAW_CANARY_MODE=1"' not in svc

    plist = (HELPER / "deploy" / "com.openclaw.engine.plist").read_text(encoding="utf-8")
    # plist 內 key/value 分行：定位 OPENCLAW_CANARY_MODE key 後的 <string> 值須為 0。
    m = re.search(
        r"<key>OPENCLAW_CANARY_MODE</key>\s*<string>(?P<val>[^<]*)</string>", plist
    )
    assert m is not None, "plist 缺 OPENCLAW_CANARY_MODE key/value"
    assert m.group("val").strip() == "0", "plist OPENCLAW_CANARY_MODE 非 0"


def test_record_l1_events_env_is_durable_across_plain_restart() -> None:
    """recorder-v2 enablement must survive watchdog/plain restart_all calls.

    The runtime bug this guards: a one-shot
    `OPENCLAW_RECORD_L1_EVENTS=1 bash restart_all.sh ...` enables market.l1_events,
    but the next restart without that parent env silently turns the producer OFF.
    """
    text = SCRIPT.read_text(encoding="utf-8")

    assert "local record_l1_events l1_max_events_per_sec_per_symbol" in text
    assert re.search(
        r'record_l1_events="\$\{OPENCLAW_RECORD_L1_EVENTS:-\$\(grep '
        r"'\^OPENCLAW_RECORD_L1_EVENTS=' "
        r'"\$SECRETS_ROOT/environment_files/basic_system_services\.env"',
        text,
    )
    assert re.search(
        r'l1_max_events_per_sec_per_symbol="\$\{OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL:-\$\(grep '
        r"'\^OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL=' "
        r'"\$SECRETS_ROOT/environment_files/basic_system_services\.env"',
        text,
    )
    assert 'OPENCLAW_RECORD_L1_EVENTS="${record_l1_events}"' in text
    assert (
        'OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL="${l1_max_events_per_sec_per_symbol}"'
        in text
    )
    assert 'OPENCLAW_RECORD_L1_EVENTS="${OPENCLAW_RECORD_L1_EVENTS:-}"' not in text
    assert (
        'OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL="${OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL:-}"'
        not in text
    )

    resolve_index = text.index("record_l1_events=")
    launch_index = text.index('OPENCLAW_RECORD_L1_EVENTS="${record_l1_events}"')
    assert resolve_index < launch_index


def test_demo_learning_lane_writer_and_probe_adapter_env_are_durable_across_plain_restart() -> None:
    """Cost-gate learning writer/adapter env-file settings must reach the engine."""
    text = SCRIPT.read_text(encoding="utf-8")

    assert (
        "local demo_learning_lane_writer demo_learning_lane_plan "
        "demo_learning_lane_ledger bounded_probe_adapter_enabled"
        in text
    )
    for env_name, shell_name in (
        ("OPENCLAW_DEMO_LEARNING_LANE_WRITER", "demo_learning_lane_writer"),
        ("OPENCLAW_DEMO_LEARNING_LANE_PLAN", "demo_learning_lane_plan"),
        ("OPENCLAW_DEMO_LEARNING_LANE_LEDGER", "demo_learning_lane_ledger"),
        ("OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED", "bounded_probe_adapter_enabled"),
    ):
        assert re.search(
            rf'{shell_name}="\$\{{{env_name}:-\$\(grep '
            rf"'\^{env_name}=' "
            r'"\$SECRETS_ROOT/environment_files/basic_system_services\.env"',
            text,
        )
        assert f'{env_name}="${{{shell_name}}}"' in text
        assert f'{env_name}="${{{env_name}:-}}"' not in text

    resolve_index = text.index("demo_learning_lane_writer=")
    launch_index = text.index(
        'OPENCLAW_DEMO_LEARNING_LANE_WRITER="${demo_learning_lane_writer}"'
    )
    assert resolve_index < launch_index


def test_bybit_demo_connector_mode_env_reaches_api_process() -> None:
    """Reviewed Demo connector mode must be visible to the settings API after restart."""
    text = SCRIPT.read_text(encoding="utf-8")

    assert "local bybit_mode_api bybit_connector_write_enabled_api" in text
    assert re.search(
        r'bybit_mode_api="\$\{BYBIT_MODE:-\$\(grep '
        r"'\^BYBIT_MODE=' "
        r'"\$SECRETS_ROOT/environment_files/trading_services\.env"',
        text,
    )
    assert re.search(
        r'bybit_connector_write_enabled_api="\$\{BYBIT_CONNECTOR_WRITE_ENABLED:-\$\(grep '
        r"'\^BYBIT_CONNECTOR_WRITE_ENABLED=' "
        r'"\$SECRETS_ROOT/environment_files/trading_services\.env"',
        text,
    )
    assert 'BYBIT_MODE="${bybit_mode_api}"' in text
    assert 'BYBIT_CONNECTOR_WRITE_ENABLED="${bybit_connector_write_enabled_api}"' in text

    resolve_index = text.index("bybit_mode_api=")
    launch_index = text.index('BYBIT_MODE="${bybit_mode_api}"')
    assert resolve_index < launch_index
