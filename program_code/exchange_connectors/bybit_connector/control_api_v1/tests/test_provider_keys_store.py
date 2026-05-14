from __future__ import annotations

import os
import sys
import urllib.error
from pathlib import Path

import pytest
from fastapi import HTTPException


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app import provider_keys_store, provider_model_catalog, provider_pricing_catalog  # noqa: E402
from app.layer2_cost_tracker import Layer2CostTracker  # noqa: E402
from app.layer2_routes import _validate_layer2_model_config  # noqa: E402
from app.layer2_types import Layer2Config  # noqa: E402


class _OkResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _n: int = -1) -> bytes:
        return b'{"data":[]}'


class _ModelsResponse:
    status = 200

    def __init__(self, model_ids: list[str]) -> None:
        self._model_ids = model_ids

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _n: int = -1) -> bytes:
        rows = ",".join('{"id":"' + mid + '"}' for mid in self._model_ids)
        return ('{"data":[' + rows + "]}").encode("utf-8")


@pytest.fixture(autouse=True)
def _clear_model_catalog_cache(monkeypatch) -> None:  # noqa: ANN001
    provider_model_catalog.invalidate_provider()
    monkeypatch.setattr(provider_model_catalog, "_read_local_model_ids", lambda **_kw: {
        "refresh_status": "local_unavailable",
        "refresh_error": "",
        "endpoint": None,
        "http_status": None,
        "provider_model_ids": [],
        "available": False,
    })
    yield
    provider_model_catalog.invalidate_provider()


def test_save_key_probes_provider_before_persisting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_KEYS_DIR", str(tmp_path))
    calls: list[str] = []

    def fake_urlopen(req, timeout):  # noqa: ANN001
        calls.append(req.full_url)
        assert timeout == 12.0
        assert req.headers["Authorization"].startswith("Bearer ")
        return _OkResponse()

    monkeypatch.setattr(provider_keys_store.urllib.request, "urlopen", fake_urlopen)

    result = provider_keys_store.save_key("openai", "sk-" + "x" * 30)

    assert result["validated"] is True
    assert result["validation_status"] == "auth_ok"
    assert calls == ["https://api.openai.com/v1/models"]
    stored = (tmp_path / "openai.env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-" in stored
    assert "# validation_status=auth_ok" in stored
    assert provider_keys_store.status()["providers"]["openai"]["validated"] is True


def test_save_key_rejects_failed_live_probe_without_writing(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_KEYS_DIR", str(tmp_path))

    def fake_urlopen(req, timeout):  # noqa: ANN001
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(provider_keys_store.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="live validation failed"):
        provider_keys_store.save_key("deepseek", "sk-" + "x" * 30)

    assert not (tmp_path / "deepseek.env").exists()


def test_status_marks_legacy_saved_key_as_unverified(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_KEYS_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "anthropic.env").write_text(
        "# anthropic API key - old file\nANTHROPIC_API_KEY=sk-ant-" + "x" * 30 + "\n",
        encoding="utf-8",
    )

    info = provider_keys_store.status()["providers"]["anthropic"]

    assert info["configured"] is True
    assert info["validated"] is False
    assert info["validation_status"] is None
    assert info["source"] == "provider_store"
    assert info["source_clearable"] is True


def test_status_loads_legacy_secret_file_when_provider_store_missing(
    tmp_path: Path, monkeypatch,
) -> None:
    secrets_root = tmp_path / "secrets"
    legacy_dir = secrets_root / "secret_files" / "ai"
    legacy_dir.mkdir(parents=True)
    legacy_key = "sk-ant-" + "l" * 40
    (legacy_dir / "anthropic_api_key").write_text(legacy_key + "\n", encoding="utf-8")

    monkeypatch.delenv("OPENCLAW_PROVIDER_KEYS_DIR", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENCLAW_SECRETS_ROOT", str(secrets_root))

    info = provider_keys_store.status()["providers"]["anthropic"]

    assert info["configured"] is True
    assert info["source"] == "legacy_secret_file"
    assert info["source_clearable"] is False
    assert info["masked"] == "sk-a…" + "l" * 4
    assert provider_keys_store.load_into_environ()["anthropic"] is True
    assert os.environ["ANTHROPIC_API_KEY"] == legacy_key


def test_provider_store_takes_precedence_over_legacy_secret_file(
    tmp_path: Path, monkeypatch,
) -> None:
    keys_dir = tmp_path / "providers"
    secrets_root = tmp_path / "secrets"
    legacy_dir = secrets_root / "secret_files" / "ai"
    keys_dir.mkdir(parents=True)
    legacy_dir.mkdir(parents=True)
    store_key = "sk-ant-" + "s" * 40
    legacy_key = "sk-ant-" + "l" * 40
    (keys_dir / "anthropic.env").write_text(
        "# validation_status=auth_ok\nANTHROPIC_API_KEY=" + store_key + "\n",
        encoding="utf-8",
    )
    (legacy_dir / "anthropic_api_key").write_text(legacy_key + "\n", encoding="utf-8")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENCLAW_PROVIDER_KEYS_DIR", str(keys_dir))
    monkeypatch.setenv("OPENCLAW_SECRETS_ROOT", str(secrets_root))

    info = provider_keys_store.status()["providers"]["anthropic"]

    assert info["configured"] is True
    assert info["source"] == "provider_store"
    assert info["source_clearable"] is True
    assert info["validated"] is True
    assert provider_keys_store.load_into_environ()["anthropic"] is True
    assert os.environ["ANTHROPIC_API_KEY"] == store_key


def test_delete_key_leaves_legacy_secret_as_readonly_source(
    tmp_path: Path, monkeypatch,
) -> None:
    keys_dir = tmp_path / "providers"
    secrets_root = tmp_path / "secrets"
    legacy_dir = secrets_root / "secret_files" / "ai"
    keys_dir.mkdir(parents=True)
    legacy_dir.mkdir(parents=True)
    store_key = "sk-ant-" + "s" * 40
    legacy_key = "sk-ant-" + "l" * 40
    provider_file = keys_dir / "anthropic.env"
    provider_file.write_text("ANTHROPIC_API_KEY=" + store_key + "\n", encoding="utf-8")
    legacy_file = legacy_dir / "anthropic_api_key"
    legacy_file.write_text(legacy_key + "\n", encoding="utf-8")

    monkeypatch.setenv("OPENCLAW_PROVIDER_KEYS_DIR", str(keys_dir))
    monkeypatch.setenv("OPENCLAW_SECRETS_ROOT", str(secrets_root))
    monkeypatch.setenv("ANTHROPIC_API_KEY", store_key)

    result = provider_keys_store.delete_key("anthropic")

    assert result["deleted"] is True
    assert result["configured"] is True
    assert result["source"] == "legacy_secret_file"
    assert result["source_clearable"] is False
    assert not provider_file.exists()
    assert legacy_file.exists()
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_layer2_model_config_rejects_provider_model_mismatch() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_layer2_model_config(
            {"default_provider": "openai", "default_model": "sonnet"},
            Layer2Config(),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["reason_codes"] == ["model_not_supported_by_provider"]


def test_layer2_model_config_accepts_matching_pairs() -> None:
    _validate_layer2_model_config(
        {
            "default_provider": "openai",
            "default_model": "gpt-4o-mini",
            "fallback_tier2_provider": "deepseek",
            "fallback_tier2_model": "deepseek-v4-flash",
            "fallback_tier3_provider": "anthropic",
            "fallback_tier3_model": "haiku",
        },
        Layer2Config(),
    )


def test_deepseek_model_catalog_fetches_v4_and_marks_legacy_aliases(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_KEYS_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "deepseek.env").write_text(
        "# validation_status=auth_ok\nDEEPSEEK_API_KEY=sk-" + "x" * 30 + "\n",
        encoding="utf-8",
    )

    def fake_urlopen(req, timeout):  # noqa: ANN001
        assert req.full_url == "https://api.deepseek.com/models"
        assert timeout == 12.0
        return _ModelsResponse(["deepseek-v4-flash", "deepseek-v4-pro"])

    monkeypatch.setattr(provider_model_catalog.urllib.request, "urlopen", fake_urlopen)

    catalog = provider_model_catalog.get_model_catalog(force_refresh=True)
    deepseek = catalog["providers"]["deepseek"]
    models = {m["value"]: m for m in deepseek["models"]}

    assert deepseek["refresh_status"] == "ok"
    assert deepseek["provider_model_ids"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert models["deepseek-v4-flash"]["provider_listed"] is True
    assert models["deepseek-v4-pro"]["provider_listed"] is True
    assert models["deepseek-chat"]["deprecated"] is True
    assert models["deepseek-chat"]["deprecation_date"] == "2026-07-24"
    assert models["deepseek-chat"]["availability_source"] == "documented_alias"


def test_model_catalog_uses_cache_until_forced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_PROVIDER_KEYS_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "anthropic.env").write_text(
        "# validation_status=auth_ok\nANTHROPIC_API_KEY=sk-ant-" + "x" * 30 + "\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_urlopen(req, timeout):  # noqa: ANN001
        calls.append(req.full_url)
        return _ModelsResponse(["claude-sonnet-4-6"])

    monkeypatch.setattr(provider_model_catalog.urllib.request, "urlopen", fake_urlopen)

    provider_model_catalog.get_model_catalog(force_refresh=True)
    cached = provider_model_catalog.get_model_catalog(force_refresh=False)

    assert calls.count("https://api.anthropic.com/v1/models") == 1
    assert cached["providers"]["anthropic"]["cache_hit"] is True


def test_local_model_catalog_uses_queried_local_models(monkeypatch) -> None:
    monkeypatch.setattr(provider_model_catalog, "_read_local_model_ids", lambda **_kw: {
        "refresh_status": "ok",
        "refresh_error": "",
        "endpoint": "http://127.0.0.1:11434/api/tags",
        "http_status": 200,
        "provider_model_ids": ["qwen3.5:27b-q4_K_M", "llama3.2:latest"],
        "local_provider": "ollama",
        "available": True,
    })

    catalog = provider_model_catalog.get_model_catalog(force_refresh=True)
    local = catalog["providers"]["local_llm"]
    models = {m["value"]: m for m in local["models"]}

    assert local["refresh_status"] == "ok"
    assert "local:qwen3.5:27b-q4_K_M" in models
    assert models["local:qwen3.5:27b-q4_K_M"]["zero_cost"] is True
    assert models["local:qwen3.5:27b-q4_K_M"]["supports_tools"] is False


def test_pricing_refresh_updates_mismatched_prices(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_LAYER2_COST_FILE", str(tmp_path / "layer2_cost.json"))

    class _PricingSourceResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _n: int = -1) -> bytes:
            return b"official pricing source"

    monkeypatch.setattr(
        provider_pricing_catalog.urllib.request,
        "urlopen",
        lambda req, timeout: _PricingSourceResponse(),  # noqa: ARG005
    )
    tracker = Layer2CostTracker()
    tracker.update_pricing({
        "models": {
            "deepseek-v4-pro": {
                "input_per_mtok": 1.74,
                "output_per_mtok": 3.48,
                "last_verified_date": "2026-05-08",
            },
        },
    })

    payload = provider_pricing_catalog.refresh_pricing_if_needed(
        tracker,
        current_date="2026-05-10",
    )

    assert payload["refresh_status"] == "refreshed"
    assert "pricing_mismatch" in payload["refresh_reasons"]
    assert payload["models"]["deepseek-v4-pro"]["input_per_mtok"] == 0.435
    assert payload["models"]["deepseek-v4-pro"]["output_per_mtok"] == 0.87
    assert payload["source_meta"]["refresh_interval_days"] == 30
