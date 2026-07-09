from __future__ import annotations

from pathlib import Path


def test_user_service_template_is_listener_only_and_has_no_activation_action() -> None:
    root = Path(__file__).resolve().parents[3]
    template = root / "helper_scripts/deploy/openclaw-alr-shadow.service.template"
    text = template.read_text(encoding="utf-8")

    assert "Type=exec" in text
    assert "-m ml_training.alr_event_consumer" in text
    assert "--dsn-file %h/.config/openclaw/alr-shadow.dsn" in text
    assert "--lock-file %t/alr-shadow/consumer.lock" in text
    assert "Environment=ALR_SOURCE_HEAD=__ALR_SOURCE_HEAD__" in text
    assert "RuntimeDirectory=alr-shadow" in text
    assert "Restart=on-failure" in text
    assert "NoNewPrivileges=true" in text
    assert "OnCalendar=" not in text
    assert "[Timer]" not in text
    assert "systemctl" not in text
    assert "enable " not in text
    assert "postgres://" not in text
    assert "password=" not in text
    assert "ALR_RECONCILE_AFTER" not in text
    assert "reconcile-after" not in text
