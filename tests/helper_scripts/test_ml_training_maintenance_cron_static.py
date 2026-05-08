from __future__ import annotations

import importlib.util
import sys
import subprocess
import textwrap
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
WRAPPER = _SRV_ROOT / "helper_scripts" / "cron" / "ml_training_maintenance_cron.sh"
RUNNER = _SRV_ROOT / "helper_scripts" / "cron" / "ml_training_maintenance.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("ml_training_maintenance", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_f08_wrapper_and_runner_static_syntax() -> None:
    assert WRAPPER.exists(), f"missing wrapper: {WRAPPER}"
    assert RUNNER.exists(), f"missing runner: {RUNNER}"

    bash_rc = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert bash_rc.returncode == 0, bash_rc.stderr

    py_rc = subprocess.run(
        ["python3", "-m", "py_compile", str(RUNNER)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert py_rc.returncode == 0, py_rc.stderr


def test_f08_runner_pins_the_five_audit_jobs() -> None:
    runner = _load_runner()

    assert runner.VALID_JOBS == (
        "linucb_trainer",
        "mlde_shadow_advisor",
        "mlde_demo_applier",
        "scorer_trainer",
        "quantile_trainer",
    )
    assert runner._expected_training_skip("insufficient samples: 10 < 200")
    assert not runner._expected_training_skip("lightgbm not installed")


def test_f08_wrapper_sources_pg_env_and_uses_lock_status_and_logs() -> None:
    body = WRAPPER.read_text(encoding="utf-8")

    assert "basic_system_services.env" in body
    assert "POSTGRES_PASSWORD" in body
    assert "OPENCLAW_DATABASE_URL" in body
    assert "PYTHONPATH" in body
    assert "ml_training_maintenance_cron.lock.d" in body
    assert "ml_training_maintenance_cron.log" in body
    assert "ml_training_maintenance_status.json" in body
    assert "mkdir \"$LOCK_DIR\"" in body


def test_f08_wrapper_invokes_runner_with_all_jobs(tmp_path: Path) -> None:
    secrets_root = tmp_path / "secrets"
    env_file_dir = secrets_root / "environment_files"
    env_file_dir.mkdir(parents=True)
    (env_file_dir / "basic_system_services.env").write_text(
        textwrap.dedent(
            """\
            POSTGRES_PASSWORD=secret_pw
            POSTGRES_USER=tradebot
            POSTGRES_DB=trading_ai
            POSTGRES_PORT=15432
            """
        ),
        encoding="utf-8",
    )

    mock_bin = tmp_path / "mock_bin"
    mock_bin.mkdir()
    mock_python = mock_bin / "python3"
    mock_python.write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            echo "MOCK_ML_DSN=${OPENCLAW_DATABASE_URL:-UNSET}"
            echo "MOCK_ML_ARGS=$*"
            exit 0
            """
        ),
        encoding="utf-8",
    )
    mock_python.chmod(0o755)

    env = {
        "HOME": str(tmp_path),
        "PATH": f"{mock_bin}:/usr/bin:/bin",
        "OPENCLAW_BASE_DIR": str(_SRV_ROOT),
        "OPENCLAW_DATA_DIR": str(tmp_path / "data"),
        "OPENCLAW_SECRETS_ROOT": str(secrets_root),
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0, proc.stderr
    log_text = (
        tmp_path
        / "data"
        / "logs"
        / "ml_training_maintenance_cron.log"
    ).read_text(encoding="utf-8")
    assert (
        "MOCK_ML_DSN=postgresql://tradebot:secret_pw@127.0.0.1:15432/trading_ai"
        in log_text
    ), f"wrapper log did not include mocked python output:\n{log_text}"
    for token in (
        "linucb_trainer",
        "mlde_shadow_advisor",
        "mlde_demo_applier",
        "scorer_trainer",
        "quantile_trainer",
    ):
        assert token in log_text
