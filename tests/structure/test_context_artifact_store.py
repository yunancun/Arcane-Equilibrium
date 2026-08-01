"""
MODULE_NOTE
模塊用途:context_artifact_store_v1 儲存層(dehydrate/resolve)可逆性與 fail-closed 邊界測試。
主要類/函數:合成 artifact 構造器 + round-trip/竄改/相容性測例。
依賴:agent_governance_context_store;測試自建合成 artifact,不依賴 Registry/git,
     可在 Mac plain pytest 下執行。
硬邊界:本檔測的是儲存表示層,不是 admission gate;admission 行為由
     test_agent_governance_context_adversarial.py 家族覆蓋,此處不得重複。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_context_store import (  # noqa: E402
    MIN_EXTRACT_BYTES,
    REF_KEY,
    dehydrate_context_artifact,
    main,
    resolve_context_artifact,
    verify_round_trip,
)


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _make_artifact(
    *, large_shared: str = "S" * (MIN_EXTRACT_BYTES * 2), wide_shared: int = 0,
) -> dict:
    """構造最小合成 artifact:plan 與 shared 投影共享同一大 content。

    為什麼合成:真實 artifact 需 Registry+git 世代,結構測試必須離線可跑;
    儲存層只依賴 canonical 位元組與 sources/content 槽位,合成件即可覆蓋。
    wide_shared>0 時追加 N 個小 content 的 shared source:單個 content 低於
    抽取閾值維持內嵌,但 dehydrated 後的 shared 投影文本仍夠大,
    用來覆蓋 payload 級去重(真實 artifact 的 shared 投影即此形態)。
    """

    shared_source = {
        "source": "docs/big.md",
        "content_encoding": "utf-8",
        "content": large_shared,
        "content_digest": _digest(large_shared.encode("utf-8")),
        "context_scope": "shared",
    }
    wide_sources = [
        {
            "source": f"docs/wide-{index:03d}.md",
            "content_encoding": "utf-8",
            "content": f"wide-{index:03d} " * 8,
            "content_digest": _digest((f"wide-{index:03d} " * 8).encode("utf-8")),
            "context_scope": "shared",
        }
        for index in range(wide_shared)
    ]
    role_source = {
        "source": "docs/small.md",
        "content_encoding": "utf-8",
        "content": "tiny",
        "content_digest": _digest(b"tiny"),
        "context_scope": "role",
    }
    plan = {
        "schema_version": "context_plan_v1",
        "role": "E1",
        "sources": [shared_source, *wide_sources, role_source],
        "task_contract": {"objective": "synthetic"},
        "task_contract_digest": _digest(b"contract"),
        "budget": {
            "authority_canonical": "{}",
            "authority_digest": _digest(b"{}"),
        },
    }
    shared_projection = {
        "schema_version": "shared_task_context_v1",
        "sources": [dict(shared_source), *[dict(s) for s in wide_sources]],
    }
    delta_projection = {
        "schema_version": "role_context_delta_v1",
        "sources": [dict(role_source)],
    }
    canonical_plan = _canonical(plan)
    shared_canonical = _canonical(shared_projection)
    delta_canonical = _canonical(delta_projection)
    return {
        "schema_version": "context_artifact_v1",
        "artifact_digest": _digest(canonical_plan.encode("utf-8")),
        "task_contract_digest": plan["task_contract_digest"],
        "budget_authority_digest": plan["budget"]["authority_digest"],
        "budget_authority_canonical": plan["budget"]["authority_canonical"],
        "canonical_plan": canonical_plan,
        "shared_task_context_digest": _digest(shared_canonical.encode("utf-8")),
        "shared_task_context_canonical": shared_canonical,
        "role_context_delta_digest": _digest(delta_canonical.encode("utf-8")),
        "role_context_delta_canonical": delta_canonical,
        "semantic_input_tokens": 123,
    }


def test_round_trip_is_byte_exact(tmp_path):
    artifact = _make_artifact()
    stored = dehydrate_context_artifact(artifact, tmp_path)
    verify_round_trip(artifact, stored, tmp_path)
    resolved = resolve_context_artifact(stored, tmp_path)
    assert resolved == artifact
    assert _canonical(resolved) == _canonical(artifact)


def test_shared_content_is_extracted_once_across_payloads_and_roles(tmp_path):
    # plan 與 shared 投影共享同一大 content;第二個 role 再存一次也不新增 blob。
    first = dehydrate_context_artifact(_make_artifact(), tmp_path)
    blobs_after_first = sorted(p.name for p in tmp_path.glob("context-shared-*.json"))
    assert len(blobs_after_first) == 1
    assert len(first["shared_refs"]) == 1
    second = dehydrate_context_artifact(_make_artifact(), tmp_path)
    blobs_after_second = sorted(p.name for p in tmp_path.glob("context-shared-*.json"))
    assert blobs_after_second == blobs_after_first
    assert second["shared_refs"] == first["shared_refs"]
    # 小 content 不抽取,維持內嵌。
    plan = json.loads(first["plan_dehydrated"])
    assert plan["sources"][1]["content"] == "tiny"
    assert REF_KEY in _canonical(plan["sources"][0]["content"])


def test_full_inline_v1_artifact_passes_through(tmp_path):
    # 向後相容:全內嵌舊格式必須原樣可讀。
    artifact = _make_artifact()
    assert resolve_context_artifact(artifact, tmp_path) is artifact


def test_tampered_blob_fails_closed(tmp_path):
    artifact = _make_artifact()
    stored = dehydrate_context_artifact(artifact, tmp_path)
    blob = next(tmp_path.glob("context-shared-*.json"))
    blob.write_bytes(blob.read_bytes().replace(b"S", b"X", 1))
    with pytest.raises(ValueError, match="do not match sha256"):
        resolve_context_artifact(stored, tmp_path)


def test_missing_blob_fails_closed(tmp_path):
    artifact = _make_artifact()
    stored = dehydrate_context_artifact(artifact, tmp_path)
    next(tmp_path.glob("context-shared-*.json")).unlink()
    with pytest.raises(ValueError, match="missing"):
        resolve_context_artifact(stored, tmp_path)


def test_manifest_drift_fails_closed(tmp_path):
    artifact = _make_artifact()
    stored = dehydrate_context_artifact(artifact, tmp_path)
    stored["shared_refs"] = []
    with pytest.raises(ValueError, match="manifest"):
        resolve_context_artifact(stored, tmp_path)


def test_ref_shaped_native_content_is_rejected(tmp_path):
    # content 原生撞 ref 形狀會破壞可逆性,必須在入庫時 fail-closed。
    collision = {REF_KEY: {"path": "context-shared-" + "0" * 64 + ".json",
                           "sha256": "sha256:" + "0" * 64}}
    artifact = _make_artifact()
    plan = json.loads(artifact["canonical_plan"])
    plan["sources"][1]["content"] = collision
    canonical_plan = _canonical(plan)
    artifact["canonical_plan"] = canonical_plan
    artifact["artifact_digest"] = _digest(canonical_plan.encode("utf-8"))
    with pytest.raises(ValueError, match="shared-ref shape"):
        dehydrate_context_artifact(artifact, tmp_path)


def test_non_canonical_payload_is_rejected(tmp_path):
    artifact = _make_artifact()
    padded = "  " + artifact["canonical_plan"]
    artifact["canonical_plan"] = padded
    artifact["artifact_digest"] = _digest(padded.encode("utf-8"))
    with pytest.raises(ValueError, match="not canonical"):
        dehydrate_context_artifact(artifact, tmp_path)


def test_digest_mismatch_on_input_is_rejected(tmp_path):
    artifact = _make_artifact()
    artifact["artifact_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="does not match artifact_digest"):
        dehydrate_context_artifact(artifact, tmp_path)


def test_shared_payload_text_is_deduped_across_roles(tmp_path):
    # 同輪同 shared 投影:整份 dehydrated 文本落 payload 級 blob,N 個 role 共用;
    # plan 逐 role 唯一,payload 級引用零收益,維持內嵌字串。
    first = dehydrate_context_artifact(_make_artifact(wide_shared=30), tmp_path)
    assert isinstance(first["shared_dehydrated"], dict)
    assert REF_KEY in first["shared_dehydrated"]
    assert isinstance(first["plan_dehydrated"], str)
    blobs_after_first = sorted(p.name for p in tmp_path.glob("context-shared-*.json"))
    second = dehydrate_context_artifact(_make_artifact(wide_shared=30), tmp_path)
    blobs_after_second = sorted(p.name for p in tmp_path.glob("context-shared-*.json"))
    assert blobs_after_second == blobs_after_first
    assert second["shared_dehydrated"] == first["shared_dehydrated"]
    verify_round_trip(_make_artifact(wide_shared=30), second, tmp_path)


def test_inline_shared_payload_form_still_resolves(tmp_path):
    # 向前相容:payload 級去重前的儲存體形態(shared_dehydrated=內嵌字串)仍可還原。
    artifact = _make_artifact(wide_shared=30)
    stored = dehydrate_context_artifact(artifact, tmp_path)
    ref = stored["shared_dehydrated"][REF_KEY]
    inline_text = (tmp_path / ref["path"]).read_text(encoding="utf-8")
    legacy = dict(stored)
    legacy["shared_dehydrated"] = inline_text
    legacy["shared_refs"] = [
        item for item in stored["shared_refs"] if item["path"] != ref["path"]
    ]
    assert resolve_context_artifact(legacy, tmp_path) == artifact


def test_tampered_payload_blob_fails_closed(tmp_path):
    artifact = _make_artifact(wide_shared=30)
    stored = dehydrate_context_artifact(artifact, tmp_path)
    blob = tmp_path / stored["shared_dehydrated"][REF_KEY]["path"]
    blob.write_bytes(blob.read_bytes().replace(b"wide", b"Wide", 1))
    with pytest.raises(ValueError, match="do not match sha256"):
        resolve_context_artifact(stored, tmp_path)


def test_rehydrated_payload_digest_anchor_fails_closed(tmp_path):
    # blob 個別完整但錨摘要不符(儲存體被改寫指向另一合法 blob)必須拒絕。
    artifact = _make_artifact()
    other = _make_artifact(large_shared="T" * (MIN_EXTRACT_BYTES * 2))
    stored = dehydrate_context_artifact(artifact, tmp_path)
    stored_other = dehydrate_context_artifact(other, tmp_path)
    swapped = dict(stored)
    swapped["plan_dehydrated"] = stored_other["plan_dehydrated"]
    swapped["shared_refs"] = stored_other["shared_refs"]
    with pytest.raises(ValueError, match="canonical_plan does not match"):
        resolve_context_artifact(swapped, tmp_path)


def test_dehydrate_cli_rejects_basename_collision(tmp_path, capsys):
    # 不同目錄同 basename 必須 fail-loud,不得靜默覆蓋先前輸入的儲存體。
    store = tmp_path / "store"
    store.mkdir()
    for sub in ("a", "b"):
        d = tmp_path / sub
        d.mkdir()
        (d / "context.json").write_text(
            _canonical(_make_artifact()) + "\n", encoding="utf-8"
        )
    rc = main([
        "dehydrate", "--store-dir", str(store),
        str(tmp_path / "a" / "context.json"), str(tmp_path / "b" / "context.json"),
    ])
    out = capsys.readouterr().out
    assert rc != 0
    assert "stored name collision" in out


def test_write_blob_installs_atomically_no_tmp_residue(tmp_path):
    # blob 落盤走同目錄暫存檔+os.replace;完成後不得殘留 .tmp 檔。
    dehydrate_context_artifact(_make_artifact(wide_shared=30), tmp_path)
    residues = [p.name for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert residues == []
