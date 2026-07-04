"""P0-1c boot/repo SHA 可觀測面測試（control API 側）。

覆蓋：
  - boot 紀錄 schema（欄位齊備 / 型別正確 / boot_ts 為 ISO UTC）
  - append-only 語意（兩次 append = 兩行獨立可解析 JSON；自動建目錄）
  - git 缺席 fallback "unknown" 不拋出（跨平台 / 降級環境約束）
  - boot_identity 凍結不變量（boot_sha 進程壽命內不變）
  - /api/v1/healthz 回應攜帶 boot_sha / repo_head 欄位
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import boot_observability as boot  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_module_state():
    """每條測試前重置模組級緩存，避免凍結值 / TTL 緩存跨測試污染。"""
    with boot._lock:
        boot._state["boot_sha"] = None
        boot._state["repo_head"] = "unknown"
        boot._state["repo_head_expires_at"] = 0.0
    yield
    with boot._lock:
        boot._state["boot_sha"] = None
        boot._state["repo_head"] = "unknown"
        boot._state["repo_head_expires_at"] = 0.0


def _assert_sha_shape(sha: str) -> None:
    """SHA 只允許 40 位 hex 或 fallback 'unknown' 兩種形狀。"""
    assert isinstance(sha, str) and sha
    is_full_hex = len(sha) == 40 and all(c in "0123456789abcdef" for c in sha.lower())
    assert is_full_hex or sha == "unknown", f"非法 SHA 形狀：{sha}"


def test_boot_record_schema_has_required_fields():
    """P0-1c 驗收要求的 boot 紀錄格式 schema 測試。"""
    record = boot.build_boot_record()
    assert record["component"] == "control_api"
    # boot_ts 必須是可解析的 ISO 8601（帶 UTC offset）
    parsed = datetime.fromisoformat(record["boot_ts"])
    assert parsed.tzinfo is not None, "boot_ts 必須帶時區（UTC）"
    _assert_sha_shape(record["repo_head"])
    assert record["pid"] == os.getpid()
    assert record["workers"] is None or (
        isinstance(record["workers"], int) and record["workers"] > 0
    )


def test_append_boot_record_appends_parseable_lines(tmp_path: Path):
    """append-only 語意：兩次 boot 寫兩行，每行獨立可解析（不覆寫）。"""
    path = boot.append_boot_record(tmp_path)
    assert path == tmp_path / boot.BOOT_HISTORY_FILENAME
    boot.append_boot_record(tmp_path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, "兩次 boot 必須是兩行（append 不覆寫）"
    for line in lines:
        parsed = json.loads(line)
        assert parsed["component"] == "control_api"
        assert parsed["pid"] == os.getpid()


def test_append_boot_record_creates_missing_data_dir(tmp_path: Path):
    """data_dir 不存在時自動建立（全新 OPENCLAW_DATA_DIR 場景）。"""
    nested = tmp_path / "nested" / "data_dir"
    path = boot.append_boot_record(nested)
    assert path.exists()


def test_append_boot_record_respects_env_data_dir(tmp_path: Path, monkeypatch):
    """未顯式給 data_dir 時走 OPENCLAW_DATA_DIR env（現行默認慣例）。"""
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    path = boot.append_boot_record()
    assert path == tmp_path / boot.BOOT_HISTORY_FILENAME
    assert path.exists()


def test_git_absent_falls_back_to_unknown_without_raising(monkeypatch):
    """git 不在 PATH（FileNotFoundError）時不拋出，boot_sha/repo_head = "unknown"。"""

    def _raise_file_not_found(*_args, **_kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(boot.subprocess, "run", _raise_file_not_found)
    ident = boot.boot_identity()
    assert ident["boot_sha"] == "unknown"
    assert ident["repo_head"] == "unknown"
    # 紀錄組裝路徑同樣不得拋出
    record = boot.build_boot_record()
    assert record["repo_head"] == "unknown"


def test_boot_identity_freezes_boot_sha(monkeypatch):
    """凍結不變量：boot_sha 首次解析後在進程壽命內不變（repo_head 可變）。"""
    first = boot.boot_identity()["boot_sha"]

    # 之後 git 改口（模擬 checkout 前進）也不能改變凍結的 boot_sha
    def _raise_file_not_found(*_args, **_kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(boot.subprocess, "run", _raise_file_not_found)
    # 令 repo_head TTL 過期，強迫重新解析
    with boot._lock:
        boot._state["repo_head_expires_at"] = 0.0
    second = boot.boot_identity()
    assert second["boot_sha"] == first, "boot_sha 凍結後不得改變"
    assert second["repo_head"] == "unknown", "repo_head 必須反映當下解析結果"


def test_healthz_exposes_boot_sha_and_repo_head():
    """/api/v1/healthz 回應必須攜帶 boot_sha / repo_head（P0-1c 可觀測面）。"""
    from fastapi.testclient import TestClient

    from app import main_legacy as _base

    client = TestClient(_base.app)
    resp = client.get("/api/v1/healthz")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    _assert_sha_shape(payload["boot_sha"])
    _assert_sha_shape(payload["repo_head"])
