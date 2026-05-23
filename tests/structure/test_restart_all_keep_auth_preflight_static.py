from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "helper_scripts" / "restart_all.sh"


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
    assert 'OPENCLAW_IPC_SOCKET="$ENGINE_SOCKET" OPENCLAW_CANARY_MODE=1' in text
    assert 'OPENCLAW_IPC_SOCKET="$ENGINE_SOCKET" \\' in text
    assert 'local sock="$ENGINE_SOCKET"' in text
    assert 'engine.sock ready at ${ENGINE_SOCKET}' in text
