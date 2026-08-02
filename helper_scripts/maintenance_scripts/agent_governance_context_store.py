"""
MODULE_NOTE
模塊用途:context_artifact_v1 的 content-addressed 落盤儲存層(dehydrate/resolve/verify)。
主要類/函數:dehydrate_context_artifact、resolve_context_artifact、verify_round_trip、CLI main。
依賴:agent_governance_context_validation.ARTIFACT_FIELDS(artifact 欄位集唯一正本)。
硬邊界:本模塊只是儲存表示層,不是 admission gate——所有消費面
(validate_context_artifact / CONTEXT_ADMISSION_V1 / capture-command / closure)
仍只接受 resolve 後的全量 context_artifact_v1。
為什麼採純位元組重組而非語義重算:歷史 artifact 屬舊 plan 世代
(如 2026-07-30 世代無 registry_digest/execution_dag_binding),以現行
materialize_semantic_context 重算會產出不同位元組;儲存層必須對任何世代
可逐位還原,故小欄位一律 verbatim 保留,只對兩個大負載
(canonical_plan、shared_task_context_canonical)抽出 source content 落
content-addressed blob,resolve 時反向填回並以 digest 端到端驗證。
shared 投影的 dehydrated 文本另做 payload 級定址:同輪同 shared 投影對
所有 role 逐位相同(實測 39 份真實 artifact 僅 7 個唯一值),整份文本落
單一 blob 讓 N 份儲存體共用;plan_dehydrated 實測 39/39 唯一,payload 級
引用零收益徒增間接層,故維持內嵌。
為什麼 fail-closed:任何會破壞 resolve∘dehydrate=identity 的輸入
(非 canonical 位元組、content 本身撞 ref 形狀、blob 位元組不符)一律拒絕,
寧可不去重也不可產生無法逐位還原的儲存體。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from agent_governance_context_validation import ARTIFACT_FIELDS


STORE_SCHEMA_VERSION = "context_artifact_store_v1"
STORE_FIELDS = {
    "schema_version",
    "artifact_digest",
    "task_contract_digest",
    "budget_authority_digest",
    "budget_authority_canonical",
    "plan_dehydrated",
    "shared_task_context_digest",
    "shared_dehydrated",
    "role_context_delta_digest",
    "role_context_delta_canonical",
    "semantic_input_tokens",
    "shared_refs",
}
# 儲存體=verbatim 小欄位 + 兩個 dehydrated 大負載;此對照表定義兩者的來源欄位
# 與驗證錨(digest 欄位),resolve 據此重組後逐位驗證。
# 第四欄=是否對整份 dehydrated 文本做 payload 級 content-addressed 去重:
# 只有 shared 開啟——同輪同 shared 投影對所有 role 逐位相同;plan 逐 role 唯一,
# payload 級引用零收益。
DEHYDRATED_PAYLOADS = (
    ("canonical_plan", "plan_dehydrated", "artifact_digest", False),
    (
        "shared_task_context_canonical", "shared_dehydrated",
        "shared_task_context_digest", True,
    ),
)
VERBATIM_FIELDS = (
    "artifact_digest",
    "task_contract_digest",
    "budget_authority_digest",
    "budget_authority_canonical",
    "shared_task_context_digest",
    "role_context_delta_digest",
    "role_context_delta_canonical",
    "semantic_input_tokens",
)
REF_KEY = "$context_shared_ref"
REF_FIELDS = {"path", "sha256"}
BLOB_NAME_RE = re.compile(r"^context-shared-[0-9a-f]{64}\.json$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# 為什麼設下限:小 content 內嵌成本低於一次 blob 間接層;閾值只影響壓縮率,不影響正確性。
MIN_EXTRACT_BYTES = 1024


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _strict_loads(raw: str | bytes) -> Any:
    return json.loads(
        raw, object_pairs_hook=_strict_object, parse_constant=_reject_constant
    )


def _is_shared_ref(value: Any) -> bool:
    """判定一個 content 槽位是否為 blob 引用形狀(exact-shape,無寬鬆匹配)。"""

    return (
        isinstance(value, dict)
        and set(value) == {REF_KEY}
        and isinstance(value[REF_KEY], dict)
        and set(value[REF_KEY]) == REF_FIELDS
        and isinstance(value[REF_KEY]["path"], str)
        and isinstance(value[REF_KEY]["sha256"], str)
    )


def _content_slots(document: Any) -> list[dict[str, Any]]:
    """列出文件裡可抽取的 source content 槽位;結構不符時回空(存 verbatim 仍正確)。

    canonical_plan 與 shared_task_context_canonical 兩代以上世代都以
    ``sources`` 列表攜帶 content,槽位定義穩定;找不到就不抽取,可逆性不受影響。
    """

    if not isinstance(document, dict):
        return []
    sources = document.get("sources")
    if not isinstance(sources, list):
        return []
    return [
        source for source in sources
        if isinstance(source, dict) and "content" in source
    ]


def _write_blob(
    raw: bytes, store_dir: Path, refs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """把一段位元組落 content-addressed blob 並登記 manifest,回傳 ref 結構。"""

    digest = _digest(raw)
    blob_name = f"context-shared-{digest.removeprefix('sha256:')}.json"
    blob_path = store_dir / blob_name
    if blob_path.exists():
        if blob_path.read_bytes() != raw:
            raise ValueError(f"existing blob {blob_name} bytes differ from content")
    else:
        # 為什麼原子安裝:並行 dehydrate 或中斷/ENOSPC 不得留下半截 blob 汙染
        # content-addressed 池——先寫同目錄暫存檔再 os.replace 原子換入;
        # 同名即同內容,競態下後到者換入的位元組必然相同。
        tmp_path = store_dir / f".{blob_name}.tmp.{os.getpid()}"
        try:
            tmp_path.write_bytes(raw)
            os.replace(tmp_path, blob_path)
        finally:
            tmp_path.unlink(missing_ok=True)
    refs[blob_name] = {"path": blob_name, "sha256": digest, "bytes": len(raw)}
    return {REF_KEY: {"path": blob_name, "sha256": digest}}


def _dehydrate_payload(
    canonical_text: str, store_dir: Path, refs: dict[str, dict[str, Any]],
) -> str:
    """抽出單一 canonical JSON 負載中的大 content 落 blob,回傳 dehydrated 字串。"""

    document = _strict_loads(canonical_text)
    if _canonical(document) != canonical_text:
        # 為什麼拒絕:resolve 靠 parse→再序列化重組位元組,非 canonical 輸入無法逐位還原。
        raise ValueError("payload bytes are not canonical JSON")
    for source in _content_slots(document):
        content = source["content"]
        # 為什麼拒絕 ref 形狀的原生 content:resolve 以形狀判定槽位是否需要
        # 還原,原生 content 撞形會被誤解引用,破壞可逆性,必須 fail-closed。
        if _is_shared_ref(content):
            raise ValueError(
                "source content collides with shared-ref shape and cannot be stored"
            )
        raw = _canonical(content).encode("utf-8")
        if len(raw) < MIN_EXTRACT_BYTES:
            continue
        source["content"] = _write_blob(raw, store_dir, refs)
    return _canonical(document)


def _rehydrate_payload(
    dehydrated_text: str, store_dir: Path, used: set[str],
) -> str:
    """反向填回 blob content,回傳重組後的 canonical 字串。"""

    document = _strict_loads(dehydrated_text)
    for source in _content_slots(document):
        content = source["content"]
        if not _is_shared_ref(content):
            continue
        ref = content[REF_KEY]
        source["content"] = _load_blob(ref, store_dir)
        used.add(ref["path"])
    return _canonical(document)


def dehydrate_context_artifact(
    artifact: dict[str, Any], store_dir: Path,
) -> dict[str, Any]:
    """把一份全量 context_artifact_v1 壓成引用式儲存體,共享 content 落 blob。

    同一 store_dir 內跨 role、跨 delta 輪的相同 content(以 canonical bytes
    的 sha256 定址)只落一份 ``context-shared-<digest>.json``;
    canonical_plan 與 shared_task_context_canonical 內的相同 content 亦共用同一 blob。
    shared 投影的整份 dehydrated 文本達閾值時亦落 payload 級 blob,
    同輪 N 個 role 的儲存體共用同一份文本。
    """

    if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_FIELDS:
        raise ValueError("artifact fields are not exact context_artifact_v1")
    if artifact.get("schema_version") != "context_artifact_v1":
        raise ValueError("artifact schema_version is not context_artifact_v1")
    for source_field, _, anchor_field, _ in DEHYDRATED_PAYLOADS:
        if not isinstance(artifact.get(source_field), str):
            raise ValueError(f"artifact {source_field} must be a string")
        if _digest(artifact[source_field].encode("utf-8")) != artifact.get(anchor_field):
            raise ValueError(f"artifact {source_field} does not match {anchor_field}")
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    refs: dict[str, dict[str, Any]] = {}
    stored: dict[str, Any] = {"schema_version": STORE_SCHEMA_VERSION}
    for field in VERBATIM_FIELDS:
        stored[field] = artifact[field]
    for source_field, stored_field, _, payload_dedup in DEHYDRATED_PAYLOADS:
        try:
            dehydrated = _dehydrate_payload(artifact[source_field], store_dir, refs)
        except ValueError as error:
            raise ValueError(f"{source_field}: {error}") from error
        raw = dehydrated.encode("utf-8")
        if payload_dedup and len(raw) >= MIN_EXTRACT_BYTES:
            # 為什麼整份文本再定址:同輪同 shared 投影的 dehydrated 文本對所有
            # role 逐位相同,payload 級 blob 讓 N 份儲存體共用同一份文本;
            # 內嵌字串與 ref 物件型別互斥,resolve 以形狀分流,無撞形空間。
            stored[stored_field] = _write_blob(raw, store_dir, refs)
        else:
            stored[stored_field] = dehydrated
    stored["shared_refs"] = [refs[name] for name in sorted(refs)]
    return stored


def _read_blob_bytes(ref: dict[str, Any], store_dir: Path) -> bytes:
    """讀取並驗證單一 blob 位元組:檔名/摘要/位元組三方一致才接受。"""

    name = ref["path"]
    digest = ref["sha256"]
    if not BLOB_NAME_RE.fullmatch(name):
        raise ValueError(f"shared ref path is not a safe blob name: {name!r}")
    if not DIGEST_RE.fullmatch(digest):
        raise ValueError(f"shared ref sha256 is invalid: {digest!r}")
    if name != f"context-shared-{digest.removeprefix('sha256:')}.json":
        raise ValueError(f"shared ref path does not match its sha256: {name}")
    blob_path = Path(store_dir) / name
    if not blob_path.is_file():
        raise ValueError(f"shared blob is missing: {name}")
    raw = blob_path.read_bytes()
    if _digest(raw) != digest:
        raise ValueError(f"shared blob bytes do not match sha256: {name}")
    return raw


def _load_blob(ref: dict[str, Any], store_dir: Path) -> Any:
    """讀取並驗證單一 blob 後解析為 JSON 值(content 槽位還原用)。"""

    return _strict_loads(_read_blob_bytes(ref, store_dir))


def resolve_context_artifact(
    stored: dict[str, Any], store_dir: Path,
) -> dict[str, Any]:
    """把儲存體物化回全量 context_artifact_v1;舊格式(全內嵌)原樣通過。

    重組後以 artifact_digest 與 shared_task_context_digest 做端到端逐位驗證;
    任何 blob 缺失、竄改或 manifest 漂移都 fail-closed。
    """

    if isinstance(stored, dict) and stored.get("schema_version") == "context_artifact_v1":
        # 向後相容:全內嵌舊格式已是消費面的原生輸入,不再二次加工。
        return stored
    if not isinstance(stored, dict) or set(stored) != STORE_FIELDS:
        raise ValueError("stored fields are not exact context_artifact_store_v1")
    if stored.get("schema_version") != STORE_SCHEMA_VERSION:
        raise ValueError("stored schema_version is invalid")
    manifest = stored.get("shared_refs")
    if not isinstance(manifest, list) or any(
        not isinstance(item, dict) for item in manifest
    ):
        raise ValueError("stored shared_refs must be a list of objects")
    artifact: dict[str, Any] = {"schema_version": "context_artifact_v1"}
    for field in VERBATIM_FIELDS:
        artifact[field] = stored[field]
    used: set[str] = set()
    for source_field, stored_field, anchor_field, _ in DEHYDRATED_PAYLOADS:
        payload = stored.get(stored_field)
        if _is_shared_ref(payload):
            # payload 級引用:blob 位元組即整份 dehydrated 文本,sha256 驗證後採用;
            # 兩種形式(內嵌字串/ref 物件)型別互斥,不需旗標即可無歧義分流。
            ref = payload[REF_KEY]
            dehydrated_text = _read_blob_bytes(ref, Path(store_dir)).decode("utf-8")
            used.add(ref["path"])
        elif isinstance(payload, str):
            dehydrated_text = payload
        else:
            raise ValueError(f"stored {stored_field} must be a string or a shared ref")
        rehydrated = _rehydrate_payload(dehydrated_text, Path(store_dir), used)
        # 為什麼以 digest 錨驗證:blob 逐一校驗只證明單塊完整,端到端逐位
        # 等價必須由原 artifact 自帶的負載摘要收口。
        if _digest(rehydrated.encode("utf-8")) != stored.get(anchor_field):
            raise ValueError(f"rehydrated {source_field} does not match {anchor_field}")
        artifact[source_field] = rehydrated
    declared = {str(item.get("path")) for item in manifest}
    # 為什麼比對 manifest:防產消不對齊——宣告與實際引用漂移即代表儲存體被
    # 部分改寫或用錯 store_dir,寧可拒絕也不可還原出貌似完整的 artifact。
    if used != declared:
        raise ValueError("stored shared_refs manifest does not match payload references")
    if set(artifact) != ARTIFACT_FIELDS:
        raise ValueError("resolved artifact fields are not exact context_artifact_v1")
    return artifact


def verify_round_trip(
    artifact: dict[str, Any], stored: dict[str, Any], store_dir: Path,
) -> None:
    """驗證 resolve(stored) 與原全量 artifact canonical 位元組等價。"""

    resolved = resolve_context_artifact(stored, store_dir)
    if _canonical(resolved) != _canonical(artifact):
        raise ValueError("resolved artifact bytes differ from the original artifact")


def _read_json(path: str) -> Any:
    return _strict_loads(Path(path).read_text(encoding="utf-8"))


def _stored_name(input_path: Path) -> str:
    return input_path.name.removesuffix(".json") + ".store.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="context_artifact_v1 content-addressed 儲存工具"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    dehydrate = subparsers.add_parser(
        "dehydrate", help="把全量 artifact 壓成引用式儲存體+共享 blob"
    )
    dehydrate.add_argument("--store-dir", required=True)
    dehydrate.add_argument("artifacts", nargs="+")
    resolve = subparsers.add_parser(
        "resolve", help="把儲存體物化回全量 context_artifact_v1"
    )
    resolve.add_argument("--store-dir", required=True)
    resolve.add_argument("--output", default=None)
    resolve.add_argument("stored")
    verify = subparsers.add_parser(
        "verify", help="離線 round-trip:resolve 後與原全量 artifact 位元組比對"
    )
    verify.add_argument("--store-dir", required=True)
    verify.add_argument("--original", required=True)
    verify.add_argument("stored")
    args = parser.parse_args(argv)
    try:
        if args.command == "dehydrate":
            store_dir = Path(args.store_dir)
            written: list[dict[str, Any]] = []
            seen_outputs: dict[Path, str] = {}
            for raw_path in args.artifacts:
                input_path = Path(raw_path)
                artifact = _read_json(raw_path)
                stored = dehydrate_context_artifact(artifact, store_dir)
                # 為什麼入庫即回驗:dehydrate 寫盤與 verify 同一事務,任何
                # 不可逆輸入在產生儲存體的當下就暴露,而非消費時才發現。
                verify_round_trip(artifact, stored, store_dir)
                output_path = store_dir / _stored_name(input_path)
                # 為什麼拒絕撞名:不同目錄同 basename 會映射同一儲存檔,
                # 後者靜默覆蓋令前者失去可解析儲存體——同批次內 fail-loud。
                if output_path in seen_outputs:
                    raise ValueError(
                        f"stored name collision: {output_path.name} from "
                        f"{seen_outputs[output_path]} and {raw_path}"
                    )
                seen_outputs[output_path] = raw_path
                output_path.write_text(_canonical(stored) + "\n", encoding="utf-8")
                written.append({
                    "input": str(input_path),
                    "stored": str(output_path),
                    "shared_refs": len(stored["shared_refs"]),
                })
            print(_canonical({"status": "OK", "stored": written}))
        elif args.command == "resolve":
            artifact = resolve_context_artifact(
                _read_json(args.stored), Path(args.store_dir)
            )
            rendered = _canonical(artifact) + "\n"
            if args.output:
                Path(args.output).write_text(rendered, encoding="utf-8")
                print(_canonical({"status": "OK", "output": args.output}))
            else:
                sys.stdout.write(rendered)
        else:
            verify_round_trip(
                _read_json(args.original), _read_json(args.stored),
                Path(args.store_dir),
            )
            print(_canonical({"status": "OK", "round_trip": "byte_equivalent"}))
    except (OSError, TypeError, ValueError) as error:
        print(_canonical({"status": "FAIL", "error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
