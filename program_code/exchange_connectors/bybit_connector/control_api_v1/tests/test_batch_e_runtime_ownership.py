"""Batch E operator/runtime ownership static regression tests.
Batch E 運維/服務所有權靜態回歸測試。

These checks pin file-level guardrails introduced for Batch E so future edits
cannot silently re-open unsafe restart/cron/scheduler/script behaviors.
這些檢查固定 Batch E 的檔案層防護，避免日後改動悄悄回退到不安全行為。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)


def _repo_root() -> Path:
    return Path(_control_api_dir).parents[3]


def _read(rel_path: str) -> str:
    return (_repo_root() / rel_path).read_text(encoding="utf-8")


def test_dapi_007_scheduled_restart_route_is_disabled() -> None:
    """Scheduled restart endpoint is hard-disabled and no longer self-restarts uvicorn."""
    text = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py"
    )
    assert '_base.require_scope_and_operator(actor, "system:restart")' in text
    assert "status_code=410" in text
    assert "scheduled restart endpoint is disabled" in text
    assert "_run_restart_in_background" not in text


def test_multi_worker_leader_locks_are_present() -> None:
    """Evolution/reconciler/grafana background jobs must enforce single leader worker."""
    evo = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py"
    )
    reconciler = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py"
    )
    grafana = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py"
    )
    main = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py"
    )
    wiring = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py"
    )

    assert "fcntl.flock" in evo
    assert "evolution_scheduler.leader.lock" in evo
    assert "-> Optional[EvolutionScheduler]" in evo
    assert "if not _acquire_leader_lock():" in evo

    assert "_acquire_reconciler_alert_lock" in reconciler
    assert "reconciler_alert_monitor.leader.lock" in reconciler

    assert "grafana_writer.leader.lock" in grafana
    assert "def start(self) -> bool" in grafana
    assert "if not _acquire_leader_lock():" in grafana

    assert "EvolutionScheduler skipped (non-leader worker)" in main
    assert "Grafana data writer skipped (non-leader worker)" in wiring


def test_sw_004_experiment_expiry_is_persisted() -> None:
    """Expiry transitions must schedule a save so EXPIRED state survives restart."""
    text = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_ledger.py"
    )
    section = text.partition("def expire_stale_hypotheses")[2].partition("return expired_count")[0]
    assert "if expired_count > 0:" in section
    assert "self._schedule_debounced_save()" in section


def test_sw_006_cron_wrappers_have_overlap_locks() -> None:
    """Cron wrappers use lock-dir + EXIT/INT/TERM trap to prevent overlap."""
    scripts = [
        "helper_scripts/cron_daily_report.sh",
        "helper_scripts/cron_observer_cycle.sh",
        "helper_scripts/db/counterfactual_daily_cron.sh",
        "helper_scripts/db/passive_wait_healthcheck_cron.sh",
    ]
    for script in scripts:
        body = _read(script)
        assert "LOCK_DIR" in body, script
        assert "mkdir \"$LOCK_DIR\"" in body, script
        assert "EXIT INT TERM" in body, script


def test_sw_001_os_004_maintenance_flag_and_safe_pid_checks() -> None:
    """clean/fresh restart maintain maintenance-flag lifecycle and safe API stop."""
    clean = _read("helper_scripts/clean_restart.sh")
    fresh = _read("helper_scripts/fresh_start.sh")

    for body in (clean, fresh):
        assert "cleanup_maintenance_flag()" in body
        assert "trap cleanup_maintenance_flag EXIT INT TERM" in body
        assert "is_openclaw_api_pid()" in body
        assert "stop_api_safe()" in body

    assert "--db-reset-confirm=CODE" in fresh
    assert "if [[ -z \"$DB_RESET_CONFIRM\" ]]; then" in fresh
    assert "CONFIRM_CODE=" not in fresh


def test_os_002_db_reset_uses_dsn_fingerprint_confirmation() -> None:
    """DB reset execute confirm code is fingerprinted to DSN/environment."""
    body = _read("helper_scripts/db/fresh_start_reset.py")
    assert "def _build_confirmation_code(dsn: str)" in body
    assert "urlparse(dsn)" in body
    assert "FRESH_START_{today_str}_{fp}" in body
    assert "if args.confirm != expected:" in body


def test_os_003_process_kill_scope_is_narrowed() -> None:
    """Lifecycle stop/restart scripts avoid broad :8000 and process-name kills."""
    restart_all = _read("helper_scripts/restart_all.sh")
    stop_all = _read("helper_scripts/stop_all.sh")
    clean = _read("helper_scripts/clean_restart.sh")
    fresh = _read("helper_scripts/fresh_start.sh")

    for body in (restart_all, stop_all, clean, fresh):
        assert "is_openclaw_engine_pid()" in body
        assert "process_cwd()" in body
        assert "signal_engine_pids" in body
        assert "pkill -f" not in body
        assert "pkill -TERM -f" not in body
        assert "pkill -KILL -f" not in body

    for body in (restart_all, stop_all):
        assert "is_openclaw_api_pid()" in body
        assert "API_WORKDIR" in body
        assert 'readlink "/proc/$pid/cwd"' in body
        assert "multiprocessing-fork" in body
        assert "lsof -ti :8000 | xargs kill -TERM" not in body
        assert "lsof -ti :8000 | xargs kill -9" not in body


def test_os_005_launchd_preflight_is_present_and_fail_closed() -> None:
    """Launchd preflight validates placeholder/template and secret readiness."""
    preflight_path = _repo_root() / "helper_scripts/deploy/launchd_preflight.sh"
    assert preflight_path.exists()
    body = preflight_path.read_text(encoding="utf-8")

    assert "plutil -lint" in body
    assert "__BASE__|__HOME__" in body
    assert "DB_URL_FILE" in body
    assert "IPC_SECRET_FILE" in body
    assert "fail \"unreplaced placeholder" in body
    assert "trading API plist must not bind all interfaces" in body


def test_os_006_mac_bootstrap_db_is_least_privilege() -> None:
    """Bootstrap role must be non-superuser and password must use safe binding."""
    body = _read("helper_scripts/mac_bootstrap_db.sh")
    assert "NOSUPERUSER" in body
    assert "NOCREATEDB" in body
    assert "NOCREATEROLE" in body
    assert "NOREPLICATION" in body
    assert "PASSWORD :'role_password'" in body
    assert "-v role_password=\"$PG_PASS\"" in body
    assert 'cat >> "$TMP_SQL"' not in body
    assert "SQL_TEMPLATE" in body


def test_os_007_telegram_report_uses_json_encoder_and_no_tokenized_argv() -> None:
    """Daily report should avoid shell JSON interpolation and tokenized curl URL argv."""
    body = _read("helper_scripts/cron_daily_report.sh")
    assert "jq -n" in body
    assert "--data-binary \"@$TELEGRAM_PAYLOAD\"" in body
    assert "--config \"$TELEGRAM_CONFIG\"" in body
    assert "TELEGRAM_API=" not in body
    assert "bot${BOT_TOKEN}" not in body
    assert "-d \"{\\\"chat_id\\\"" not in body


def test_w_audit_2_mutating_learning_routes_require_operator_scopes() -> None:
    """Weekly review and scout writes must require operator role plus explicit scopes."""
    phase4 = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/phase4_routes.py"
    )
    scout = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_routes.py"
    )
    layer2 = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_routes.py"
    )

    assert phase4.count('base.require_scope_and_operator(actor, "learning:manage")') >= 2
    assert "base.audit_actor_id(actor)" in phase4
    assert scout.count('base.require_scope_and_operator(actor, "learning:write")') >= 2
    assert 'base.require_scope_and_operator(actor, "ai_budget:write")' in layer2


def test_w_audit_2_api_launches_default_to_tailnet_or_loopback_bind() -> None:
    """Lifecycle scripts and deploy docs must not default uvicorn to all interfaces."""
    helper = _read("helper_scripts/lib/api_bind_host.sh")
    assert "OPENCLAW_BIND_HOST:-auto" in helper
    assert '"0.0.0.0"|"::"' in helper
    assert "tailscale ip -4" in helper

    scripts = [
        "helper_scripts/restart_all.sh",
        "helper_scripts/clean_restart.sh",
        "helper_scripts/fresh_start.sh",
    ]
    for script in scripts:
        body = _read(script)
        assert "resolve_openclaw_api_bind_host" in body, script
        assert "--host 0.0.0.0" not in body, script

    deploy_readme = _read("helper_scripts/deploy/README.md")
    assert "OPENCLAW_BIND_HOST=tailscale" in deploy_readme
    assert "--host 0.0.0.0" not in deploy_readme
    assert "Tailscale Serve" in deploy_readme

    launchd_api = _read("helper_scripts/deploy/com.openclaw.trading-api.plist")
    assert "<string>--host</string>" in launchd_api
    assert "<string>127.0.0.1</string>" in launchd_api
    assert "<string>0.0.0.0</string>" not in launchd_api


def test_api_bind_host_helper_resolves_tailscale_and_rejects_all_interfaces(tmp_path: Path) -> None:
    """The non-interactive SSH path should get tailnet access without 0.0.0.0."""
    helper = _repo_root() / "helper_scripts/lib/api_bind_host.sh"
    fake_tailscale = tmp_path / "tailscale"
    fake_tailscale.write_text("#!/bin/sh\n[ \"$1\" = \"ip\" ] && [ \"$2\" = \"-4\" ] && echo 100.91.109.86\n", encoding="utf-8")
    fake_tailscale.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env.get('PATH', '')}"

    auto = subprocess.run(
        ["bash", "-c", f"source '{helper}'; unset OPENCLAW_BIND_HOST; resolve_openclaw_api_bind_host"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert auto.stdout.strip() == "100.91.109.86"

    rejected = subprocess.run(
        ["bash", "-c", f"source '{helper}'; OPENCLAW_BIND_HOST=0.0.0.0 resolve_openclaw_api_bind_host"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "all interfaces" in rejected.stderr


def test_w_audit_2_ai_service_listener_chmods_unix_socket() -> None:
    """AI service Unix socket should be owner-only after bind."""
    body = _read(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service_listener.py"
    )
    assert "os.chmod(self._socket_path, 0o600)" in body
    assert "await self._server.wait_closed()" in body


def test_w_audit_2_lease_transition_writer_is_wired_into_pipelines() -> None:
    """Governance lease transitions must reach the DB writer from all active pipelines."""
    main = _read("rust/openclaw_engine/src/main.rs")
    pipelines = _read("rust/openclaw_engine/src/main_pipelines.rs")
    deps = _read("rust/openclaw_engine/src/event_consumer/types.rs")
    bootstrap = _read("rust/openclaw_engine/src/event_consumer/bootstrap.rs")

    assert "spawn_lease_transition_pipeline" in main
    assert "lease_transition_tx: lease_transition_tx.clone()" in main
    assert "pub lease_transition_tx: Option<LeaseTransitionSender>" in pipelines
    assert "lease_transition_tx: writers.lease_transition_tx.clone()" in pipelines
    assert "pub lease_transition_tx: Option<LeaseTransitionSender>" in deps
    assert "pipeline.governance.set_lease_transition_tx(tx)" in bootstrap
