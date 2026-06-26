from __future__ import annotations

import json
from pathlib import Path

import pytest

from helper_scripts.operator import control_api_csrf_post as target


def _token_file(tmp_path: Path) -> Path:
    path = tmp_path / "api_token"
    path.write_text("test-token", encoding="utf-8")
    return path


def test_config_uses_cookie_engine_not_raw_cookie_header() -> None:
    config = target.build_curl_config(
        api_base="http://127.0.0.1:8000",
        path="/api/v1/__csrf_probe_no_route",
        token="test-token",
        csrf_token="csrf-token",
        connect_timeout=10,
        max_time=30,
        data=None,
    )

    assert 'cookie = "oc_csrf=csrf-token"' in config
    assert 'header = "X-CSRF-Token: csrf-token"' in config
    assert 'header = "Cookie:' not in config


def test_rejects_sensitive_path_without_reviewed_mutation(tmp_path, capsys) -> None:
    rc = target.run(
        [
            "--path",
            "/api/v1/strategy/demo/session/stop",
            "--token-file",
            str(_token_file(tmp_path)),
            "--output",
            str(tmp_path / "response.json"),
            "--dry-run",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert "control API POST requires" in payload["error"]


def test_allows_sensitive_path_with_exact_review_binding(tmp_path, capsys) -> None:
    path = "/api/v1/strategy/demo/session/stop"
    rc = target.run(
        [
            "--path",
            path,
            "--token-file",
            str(_token_file(tmp_path)),
            "--output",
            str(tmp_path / "response.json"),
            "--dry-run",
            "--allow-reviewed-write",
            target.REVIEWED_WRITE_TOKEN,
            "--allow-reviewed-mutation",
            target.REVIEWED_MUTATION_TOKEN,
            "--reviewed-path",
            path,
            "--reviewed-change-id",
            "pm-e3-bb-20260626",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["sensitive_path"] is True
    assert payload["uses_curl_cookie_engine"] is True
    assert payload["uses_raw_cookie_header"] is False


def test_rejects_reviewed_binding_for_different_path(tmp_path, capsys) -> None:
    rc = target.run(
        [
            "--path",
            "/api/v1/strategy/demo/session/stop",
            "--token-file",
            str(_token_file(tmp_path)),
            "--output",
            str(tmp_path / "response.json"),
            "--dry-run",
            "--allow-reviewed-write",
            target.REVIEWED_WRITE_TOKEN,
            "--allow-reviewed-mutation",
            target.REVIEWED_MUTATION_TOKEN,
            "--reviewed-path",
            "/api/v1/strategy/demo/session/start",
            "--reviewed-change-id",
            "pm-e3-bb-20260626",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False


def test_rejects_real_non_probe_path_without_reviewed_write(tmp_path, capsys) -> None:
    rc = target.run(
        [
            "--path",
            "/api/v1/auth/logout",
            "--token-file",
            str(_token_file(tmp_path)),
            "--output",
            str(tmp_path / "response.json"),
            "--dry-run",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert "reviewed_pm_control_api_write" in payload["error"]


def test_rejects_non_api_path(tmp_path, capsys) -> None:
    rc = target.run(
        [
            "--path",
            "http://127.0.0.1:8000/api/v1/auth/logout",
            "--token-file",
            str(_token_file(tmp_path)),
            "--output",
            str(tmp_path / "response.json"),
            "--dry-run",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert "/api/v1/" in payload["error"]


def test_rejects_query_string_path_bypass(tmp_path, capsys) -> None:
    rc = target.run(
        [
            "--path",
            "/api/v1/strategy/demo/session/stop?x=1",
            "--token-file",
            str(_token_file(tmp_path)),
            "--output",
            str(tmp_path / "response.json"),
            "--dry-run",
            "--allow-reviewed-write",
            target.REVIEWED_WRITE_TOKEN,
            "--allow-reviewed-mutation",
            target.REVIEWED_MUTATION_TOKEN,
            "--reviewed-path",
            "/api/v1/strategy/demo/session/stop?x=1",
            "--reviewed-change-id",
            "pm-e3-bb-20260626",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert "query strings or fragments" in payload["error"]


@pytest.mark.parametrize(
    "path,error_text",
    [
        ("/api/v1/__csrf_probe_/../strategy/demo/session/stop", "dot segments"),
        ("/api/v1/__csrf_probe_%2f..%2fstrategy/demo/session/stop", "percent"),
        ("/api/v1/__csrf_probe_//strategy/demo/session/stop", "empty path segments"),
        ("/api/v1/__csrf_probe_\\..\\strategy\\demo\\session\\stop", "backslash"),
    ],
)
def test_rejects_probe_path_normalization_bypasses(
    path: str, error_text: str, tmp_path, capsys
) -> None:
    rc = target.run(
        [
            "--path",
            path,
            "--token-file",
            str(_token_file(tmp_path)),
            "--output",
            str(tmp_path / "response.json"),
            "--dry-run",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert error_text in payload["error"]


def test_rejects_unapproved_api_base_before_reading_token(tmp_path, capsys) -> None:
    missing_token_file = tmp_path / "missing-token"
    rc = target.run(
        [
            "--api-base",
            "https://example.test",
            "--path",
            "/api/v1/__csrf_probe_no_route",
            "--token-file",
            str(missing_token_file),
            "--output",
            str(tmp_path / "response.json"),
            "--expect-http",
            "404",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert "not approved" in payload["error"]
    assert str(missing_token_file) not in payload["error"]


def test_rejects_api_base_with_embedded_path(tmp_path, capsys) -> None:
    rc = target.run(
        [
            "--api-base",
            "http://100.91.109.86:8000/api/v1",
            "--path",
            "/api/v1/__csrf_probe_no_route",
            "--token-file",
            str(_token_file(tmp_path)),
            "--output",
            str(tmp_path / "response.json"),
            "--dry-run",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert "path, query, or fragment" in payload["error"]


def test_http_status_ok_defaults_to_2xx() -> None:
    assert target.http_status_ok("200", set()) is True
    assert target.http_status_ok("204", set()) is True
    assert target.http_status_ok("404", set()) is False
    assert target.http_status_ok("403", set()) is False


def test_http_status_ok_honors_exact_expected_codes() -> None:
    expected = target.parse_expected_http(["404,409"])
    assert target.http_status_ok("404", expected) is True
    assert target.http_status_ok("409", expected) is True
    assert target.http_status_ok("200", expected) is False


def test_api_token_argv_option_is_not_supported() -> None:
    with pytest.raises(SystemExit):
        target.build_parser().parse_args(
            [
                "--path",
                "/api/v1/__csrf_probe_no_route",
                "--api-token",
                "token-in-argv",
                "--output",
                "/tmp/response.json",
            ]
        )
