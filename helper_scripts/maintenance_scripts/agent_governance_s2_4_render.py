#!/usr/bin/env python3
"""S2.4(WP4·W2c)渲染與 manifest-builder 治理葉模組。

自 agent_governance_s2_4_install 依 2000 行治理拆分抽出的 W2c 面(install 模組逐名
re-export,ABI 經其不變):

- §8.3/§10.5 #22:engine-scanner system-unit 的 code-owned 渲染器與逐設定再驗謂詞
  (`render_engine_scanner_unit` / `derive_rendered_unit_status`);任何被移除/弱化/
  夾帶的設定都是 typed 拒絕。checked-in template
  (helper_scripts/deploy/arcane-equilibrium-aiml-engine-scanner.service.template)
  的 bytes 必須等於 `unit_template_text()`——渲染「不」讀該檔,故 template 漂移絕不
  影響渲染輸出,只會被 W2 exported-ABI 投影與 focused 測試抓紅。
- WP3_INVOCATION_FINGERPRINT_ALIGNMENT_REQUIRED 的 argv 半邊:
  `engine_scanner_rendered_invocation_contract` 匯出渲染後 ExecStart 的逐 token argv
  與完整 Environment 鍵集,供之後 WP3 側 C1 fingerprint/env-hash 修正案「消費」對齊
  (本葉「不」動 WP3-owned 的 agent_governance_alr_quiesce_inventory.py)。
- §2 候選學習組態列/§10.5 #21:`render_candidate_policy` /
  `derive_candidate_policy_status`(placeholder/null/hash-mismatch 於任何輸出前 typed
  拒絕;canonical bytes 決定 stable sha256)與私有空 evidence-directory 謂詞。
- §8.1 #2/#4:`build_base_runtime_tree_manifest` / `build_launch_bundle_manifest`
  只走「caller 提供」的 staging/launch 樹(tmp-dir 測試;絕不觸生產路徑),
  symlink/device/group-other-writable/路徑逃逸一律 typed 拒絕。

硬邊界:source-only、零 effect、零網路、零生產路徑接觸;九 authority 恆 false。
facade 依 2000 行治理拆分規約「只」經 schema_core.resolve_facade() 取得。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from aiml_gate_receipt_schema_core import resolve_facade  # noqa: E402
from ml_training import alr_candidate_policy as _policy  # noqa: E402

# ── §8.3 契約常量(canonical unit name 依 §8 reconciliation note/PR#134 釘死)──────
UNIT_NAME = "arcane-equilibrium-aiml-engine-scanner.service"
UNIT_TEMPLATE_REL = (
    "helper_scripts/deploy/arcane-equilibrium-aiml-engine-scanner.service.template"
)
_INSTALL_ROOT = "/opt/arcane-equilibrium/aiml"
_APPS_ROOT = _INSTALL_ROOT + "/apps"
_LAUNCHES_ROOT = _INSTALL_ROOT + "/launches"
_ETC_ROOT = "/etc/arcane-equilibrium/aiml/engine-scanner"
_STATE_ROOT = "/var/lib/arcane-equilibrium/aiml/engine-scanner"
_RECEIPT_V1_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v1.json"
)
_RECEIPT_V2_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v2.json"
)
# §8.3 的十個 Environment 鍵(次序 = unit 內次序;WP3 fingerprint 對齊消費此集合)。
ENGINE_SCANNER_ENV_KEYS = (
    "ALR_SOURCE_HEAD",
    "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST",
    "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST_V2",
    "ALR_EXPECTED_COMPATIBILITY_RECEIPT",
    "ALR_EXPECTED_COMPATIBILITY_RECEIPT_V2",
    "ALR_APPLICATION_BUNDLE_DIGEST",
    "ALR_LAUNCH_BUNDLE_DIGEST",
    "ALR_CANDIDATE_EVIDENCE_DIR",
    "ALR_CANDIDATE_POLICY_FILE",
    "ALR_TOPOLOGY_GUARD_FILE",
)
# §8.3 UnsetEnvironment 的確切載荷(次序即 bytes;弱化 = typed 拒絕)。
_UNSET_ENVIRONMENT_VALUE = (
    "PGPASSWORD PGPASSFILE PGSERVICE PGSERVICEFILE PGHOST PGHOSTADDR PGPORT "
    "PGDATABASE PGUSER PGOPTIONS PGAPPNAME PGCONNECT_TIMEOUT PGCLIENTENCODING "
    "PGTARGETSESSIONATTRS PGCHANNELBINDING PGGSSENCMODE PGKRBSRVNAME PGGSSLIB "
    "PGREQUIREPEER PGSSLMODE PGREQUIRESSL PGSSLCERT PGSSLKEY PGSSLROOTCERT "
    "PGSSLCRL PGSSLCRLDIR PGSSLSNI PGLOADBALANCEHOSTS LD_PRELOAD LD_LIBRARY_PATH "
    "PYTHONHOME PYTHONPATH PYTHONUSERBASE"
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_PLATFORM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_TREE_NAME_RE = re.compile(r"^[A-Za-z0-9_.+\-]+$")
_UNIT_MAX_BYTES = 65_536
_POLICY_MAX_BYTES = 65_536

# 渲染欄位契約:「只」接受這五個 digest/head 欄位——任何多餘鍵(caller 自帶 unit 文本、
# 任意 environment 鍵)一律 typed 拒絕;缺欄/None/格式不符亦然(§8.3:renderer accepts
# digests and fixed contract fields only)。
_UNIT_FIELD_PATTERNS = {
    "source_head": _HEAD_RE,
    "learning_runtime_digest": _DIGEST_RE,
    "learning_runtime_digest_v2": _DIGEST_RE,
    "application_bundle_digest": _DIGEST_RE,
    "launch_bundle_digest": _DIGEST_RE,
}
# template 佔位 token(值域為 hex/sha256,不可能含 '@',故「殘留 '@' = 未填佔位」成立)。
_TEMPLATE_TOKENS = {
    "source_head": "@ALR_SOURCE_HEAD@",
    "learning_runtime_digest": "@LEARNING_RUNTIME_DIGEST@",
    "learning_runtime_digest_v2": "@LEARNING_RUNTIME_DIGEST_V2@",
    "application_bundle_digest": "@APPLICATION_BUNDLE_DIGEST@",
    "application_bundle_leaf": "@APPLICATION_BUNDLE_LEAF@",
    "launch_bundle_digest": "@LAUNCH_BUNDLE_DIGEST@",
    "launch_bundle_leaf": "@LAUNCH_BUNDLE_LEAF@",
}


class EngineScannerUnitRenderError(ValueError):
    """typed 的 unit 渲染拒絕(caller 文本/任意鍵/未填佔位/格式不符)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _validate_unit_fields(fields: Any) -> dict[str, str]:
    """封閉欄位面驗證:非物件/未知鍵/缺欄/None/非字串/格式不符一律 typed 拒絕。"""
    if not isinstance(fields, Mapping):
        raise EngineScannerUnitRenderError("unit_fields_not_object")
    unknown = sorted(set(fields) - set(_UNIT_FIELD_PATTERNS))
    if unknown:
        # caller-provided unit text / arbitrary environment key 的唯一入口即多餘鍵——封死。
        raise EngineScannerUnitRenderError(
            "unit_fields_unknown_key:" + ",".join(unknown)
        )
    validated: dict[str, str] = {}
    for name, pattern in _UNIT_FIELD_PATTERNS.items():
        value = fields.get(name)
        if value is None:
            raise EngineScannerUnitRenderError(f"unit_field_missing:{name}")
        if not isinstance(value, str) or pattern.fullmatch(value) is None:
            raise EngineScannerUnitRenderError(f"unit_field_invalid:{name}")
        validated[name] = value
    return validated


def _digest_leaf(digest: str) -> str:
    """§8.1/W2b 葉名契約:content digest 的 64-hex 作不可變樹葉目錄名(':' 不入路徑)。

    launches/<64-hex> 由 W2b 的 alr_application_identity.verify_launch_prefix 釘死;
    apps/<64-hex> 鏡射同一契約(§8.1 apps/<application_bundle_digest> 的路徑投影)。
    """
    return digest.split(":", 1)[1]


def _invocation_argv(
    *, app_leaf: str, app_digest: str, launch_leaf: str, launch_digest: str
) -> list[str]:
    """§8.3 ExecStart 的逐 token argv(唯一構造點;渲染與 invocation contract 共用)。"""
    app_root = f"{_APPS_ROOT}/{app_leaf}"
    return [
        f"{_LAUNCHES_ROOT}/{launch_leaf}/bin/python3",
        "-I",
        "-B",
        "-m",
        "ml_training.alr_event_consumer",
        "--dsn-file",
        "%d/pg-dsn",
        "--application-root",
        app_root,
        "--expected-compatibility-receipt-v2",
        f"{app_root}/{_RECEIPT_V2_REL}",
        "--expected-application-bundle-digest",
        app_digest,
        "--expected-launch-bundle-digest",
        launch_digest,
        "--topology-guard-file",
        f"{_ETC_ROOT}/topology-runtime-guard.json",
        "--lock-file",
        "%t/arcane-equilibrium/aiml/engine-scanner/consumer.lock",
        "--max-batch",
        "32",
    ]


def engine_scanner_rendered_invocation_contract(fields: Any) -> dict[str, Any]:
    """渲染後 ExecStart 的確切 argv token 列 + 完整 Environment 鍵集(exported 契約)。

    供之後 WP3 側 C1 fingerprint/env-hash 修正案消費,以卸除
    WP3_INVOCATION_FINGERPRINT_ALIGNMENT_REQUIRED 的 argv 半邊;渲染輸出的 ExecStart
    重新 parse 後必須逐 token 等於本契約(focused 測試釘死)。
    """
    validated = _validate_unit_fields(fields)
    launch_leaf = _digest_leaf(validated["launch_bundle_digest"])
    argv = _invocation_argv(
        app_leaf=_digest_leaf(validated["application_bundle_digest"]),
        app_digest=validated["application_bundle_digest"],
        launch_leaf=launch_leaf,
        launch_digest=validated["launch_bundle_digest"],
    )
    return {
        "schema_version": "engine_scanner_invocation_contract_v1",
        "unit_name": UNIT_NAME,
        "exec_prefix": f"{_LAUNCHES_ROOT}/{launch_leaf}/bin/python3",
        "argv": argv,
        "env_keys": list(ENGINE_SCANNER_ENV_KEYS),
    }


# §8.3 ExecStart 的續行分組(token 切片;斷言逐片覆蓋 argv 全長,分組絕不能吞/漏 token)。
_EXEC_GROUP_SLICES = (
    (0, 3), (3, 7), (7, 9), (9, 11), (11, 13), (13, 15), (15, 17), (17, 21),
)


def _exec_start_lines(argv: list[str]) -> list[str]:
    """把 argv 按 §8.3 的續行版式渲染為多行 ExecStart(bytes 即契約)。"""
    covered = [token for start, end in _EXEC_GROUP_SLICES for token in argv[start:end]]
    if covered != argv:
        raise EngineScannerUnitRenderError("exec_start_group_slices_do_not_cover_argv")
    lines: list[str] = []
    for index, (start, end) in enumerate(_EXEC_GROUP_SLICES):
        text = " ".join(argv[start:end])
        prefix = "ExecStart=" if index == 0 else "  "
        suffix = " \\" if index < len(_EXEC_GROUP_SLICES) - 1 else ""
        lines.append(prefix + text + suffix)
    return lines


def _unit_lines(values: Mapping[str, str]) -> list[str]:
    """§8.3 normative shape 的唯一構造點(template 與渲染共用;逐行即逐 byte)。"""
    app_leaf = values["application_bundle_leaf"]
    exec_lines = _exec_start_lines(
        _invocation_argv(
            app_leaf=app_leaf,
            app_digest=values["application_bundle_digest"],
            launch_leaf=values["launch_bundle_leaf"],
            launch_digest=values["launch_bundle_digest"],
        )
    )
    app_root = f"{_APPS_ROOT}/{app_leaf}"
    return [
        "[Unit]",
        "Description=Arcane Equilibrium ALR scanner event consumer",
        "After=network.target",
        "StartLimitIntervalSec=300s",
        "StartLimitBurst=3",
        "",
        "[Service]",
        "Type=exec",
        "User=aiml-engine-scanner",
        "Group=aiml-engine-scanner",
        f"WorkingDirectory={_STATE_ROOT}",
        "LoadCredentialEncrypted=pg-dsn:/etc/credstore.encrypted/aiml-engine-scanner-pg-dsn",
        f"Environment=ALR_SOURCE_HEAD={values['source_head']}",
        f"Environment=ALR_EXPECTED_LEARNING_RUNTIME_DIGEST={values['learning_runtime_digest']}",
        f"Environment=ALR_EXPECTED_LEARNING_RUNTIME_DIGEST_V2={values['learning_runtime_digest_v2']}",
        f"Environment=ALR_EXPECTED_COMPATIBILITY_RECEIPT={app_root}/{_RECEIPT_V1_REL}",
        f"Environment=ALR_EXPECTED_COMPATIBILITY_RECEIPT_V2={app_root}/{_RECEIPT_V2_REL}",
        f"Environment=ALR_APPLICATION_BUNDLE_DIGEST={values['application_bundle_digest']}",
        f"Environment=ALR_LAUNCH_BUNDLE_DIGEST={values['launch_bundle_digest']}",
        f"Environment=ALR_CANDIDATE_EVIDENCE_DIR={_STATE_ROOT}/candidate-evidence",
        f"Environment=ALR_CANDIDATE_POLICY_FILE={_ETC_ROOT}/candidate-policy.json",
        f"Environment=ALR_TOPOLOGY_GUARD_FILE={_ETC_ROOT}/topology-runtime-guard.json",
        *exec_lines,
        "RuntimeDirectory=arcane-equilibrium/aiml/engine-scanner",
        "RuntimeDirectoryMode=0700",
        "StateDirectory=arcane-equilibrium/aiml/engine-scanner",
        "StateDirectoryMode=0700",
        "Restart=on-failure",
        "RestartSec=30s",
        "RestartPreventExitStatus=78",
        "TimeoutStopSec=30s",
        "KillMode=control-group",
        "NoNewPrivileges=true",
        "LimitCORE=0",
        "UMask=0077",
        f"UnsetEnvironment={_UNSET_ENVIRONMENT_VALUE}",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "ProtectKernelTunables=true",
        "ProtectKernelModules=true",
        "ProtectControlGroups=true",
        "ProtectClock=true",
        "RestrictRealtime=true",
        "RestrictSUIDSGID=true",
        "LockPersonality=true",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "SystemCallArchitectures=native",
        "RestrictAddressFamilies=AF_UNIX AF_INET",
        "IPAddressDeny=any",
        "IPAddressAllow=127.0.0.1/32",
        "MemoryMax=512M",
        "TasksMax=64",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ]


def unit_template_text() -> str:
    """code-owned template 全文(checked-in template 檔 bytes 必須逐位元組相等)。"""
    return "\n".join(_unit_lines(_TEMPLATE_TOKENS)) + "\n"


def render_engine_scanner_unit(fields: Any) -> str:
    """§8.3:由驗過的 digest/head 欄位渲染完整 system unit(bytes 即最終安裝身分)。

    渲染「不」讀 template 檔——形狀是 code-owned 的 `_unit_lines`;任何殘留 '@'
    佔位(template 常量新增 token 而欄位面未覆蓋)一律 typed fail-closed。
    """
    validated = _validate_unit_fields(fields)
    rendered = "\n".join(_unit_lines({
        "source_head": validated["source_head"],
        "learning_runtime_digest": validated["learning_runtime_digest"],
        "learning_runtime_digest_v2": validated["learning_runtime_digest_v2"],
        "application_bundle_digest": validated["application_bundle_digest"],
        "application_bundle_leaf": _digest_leaf(validated["application_bundle_digest"]),
        "launch_bundle_digest": validated["launch_bundle_digest"],
        "launch_bundle_leaf": _digest_leaf(validated["launch_bundle_digest"]),
    })) + "\n"
    if "@" in rendered:
        raise EngineScannerUnitRenderError("unit_template_placeholder_unfilled")
    return rendered


def _parse_unit_entries(text: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """把 unit 文本解析為有序 (section, key, value) 列(systemd 續行語義;fail-closed)。"""
    reasons: list[str] = []
    logical: list[str] = []
    pending: str | None = None
    for raw in text.split("\n"):
        line = raw if pending is None else pending + raw
        if line.endswith("\\"):
            pending = line[:-1]
            continue
        pending = None
        logical.append(line)
    if pending is not None:
        reasons.append("unit text ends inside a line continuation")
    section: str | None = None
    entries: list[tuple[str, str, str]] = []
    for line in logical:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            if stripped:
                # §8.3 canonical 渲染無註釋;夾帶註釋亦屬 drop-in 式偏移。
                reasons.append(f"unexpected comment line in rendered unit: {stripped[:60]}")
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        if "=" not in stripped or section is None:
            reasons.append(f"unit line is not a sectioned key=value setting: {stripped[:60]}")
            continue
        key, _, value = stripped.partition("=")
        entries.append((section, key.strip(), value.strip()))
    return entries, reasons


def _extract_unit_fields(
    entries: list[tuple[str, str, str]]
) -> tuple[dict[str, str] | None, list[str]]:
    """從 [Service] Environment 行抽回五個渲染欄位(缺/重複/格式不符 → typed reasons)。"""
    reasons: list[str] = []
    env: dict[str, list[str]] = {}
    for section, key, value in entries:
        if section == "Service" and key == "Environment":
            name, _, payload = value.partition("=")
            env.setdefault(name, []).append(payload)
    wanted = {
        "source_head": "ALR_SOURCE_HEAD",
        "learning_runtime_digest": "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST",
        "learning_runtime_digest_v2": "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST_V2",
        "application_bundle_digest": "ALR_APPLICATION_BUNDLE_DIGEST",
        "launch_bundle_digest": "ALR_LAUNCH_BUNDLE_DIGEST",
    }
    fields: dict[str, str] = {}
    for field, env_key in wanted.items():
        values = env.get(env_key, [])
        if len(values) != 1:
            reasons.append(
                f"unit environment {env_key} must appear exactly once (found {len(values)})"
            )
            continue
        if _UNIT_FIELD_PATTERNS[field].fullmatch(values[0]) is None:
            reasons.append(f"unit environment {env_key} value is malformed")
            continue
        fields[field] = values[0]
    if len(fields) != len(wanted):
        return None, reasons
    return fields, reasons


def derive_rendered_unit_status(rendered: Any) -> dict[str, Any]:
    """§10.5 #22:重 parse 渲染文本並逐設定再驗——移除/弱化/夾帶皆 typed 拒絕。

    機制:自渲染文本抽回五個 digest/head 欄位 → 以同一 code-owned 構造點重建 canonical
    unit → (a) 逐 (section, key) 比對(移除=removed、值變=weakened/changed、多出=
    drop-in-style extra),(b) 全文 bytes 相等(版式/排序漂移亦拒)。caller 不可自證;
    PASS 只證 SOURCE 渲染形狀,「不」認證任何 runtime/install 狀態。
    """
    reasons: list[str] = []
    if not isinstance(rendered, str):
        return _unit_verdict("ENGINE_SCANNER_UNIT_INVALID", ["rendered unit must be a string"], None)
    if len(rendered.encode("utf-8")) > _UNIT_MAX_BYTES:
        return _unit_verdict(
            "ENGINE_SCANNER_UNIT_INVALID", ["rendered unit exceeds the size bound"], None
        )
    entries, parse_reasons = _parse_unit_entries(rendered)
    reasons.extend(parse_reasons)
    fields, field_reasons = _extract_unit_fields(entries)
    reasons.extend(field_reasons)
    if fields is None:
        return _unit_verdict("ENGINE_SCANNER_UNIT_INVALID", reasons, None)
    try:
        canonical = render_engine_scanner_unit(fields)
    except EngineScannerUnitRenderError as error:
        reasons.append(f"canonical §8.3 rendering is unbuildable: {error.code}")
        return _unit_verdict("ENGINE_SCANNER_UNIT_INVALID", reasons, None)
    expected_entries, _ = _parse_unit_entries(canonical)
    expected_map: dict[tuple[str, str], list[str]] = {}
    for section, key, value in expected_entries:
        expected_map.setdefault((section, key), []).append(value)
    actual_map: dict[tuple[str, str], list[str]] = {}
    for section, key, value in entries:
        actual_map.setdefault((section, key), []).append(value)
    for (section, key), values in expected_map.items():
        actual_values = actual_map.get((section, key))
        if actual_values is None:
            reasons.append(f"required unit setting removed: [{section}] {key}")
        elif actual_values != values:
            reasons.append(
                f"required unit setting weakened or changed: [{section}] {key}"
            )
    for (section, key) in actual_map:
        if (section, key) not in expected_map:
            reasons.append(f"unexpected drop-in-style unit setting: [{section}] {key}")
    if not reasons and rendered != canonical:
        reasons.append("rendered unit bytes do not equal the canonical §8.3 rendering")
    status = "PASS" if not reasons else "ENGINE_SCANNER_UNIT_INVALID"
    return _unit_verdict(status, reasons, fields, rendered=rendered)


def _unit_verdict(
    status: str,
    reasons: list[str],
    fields: dict[str, str] | None,
    *,
    rendered: str | None = None,
) -> dict[str, Any]:
    verdict: dict[str, Any] = {
        "schema_version": "engine_scanner_rendered_unit_verdict_v1",
        "status": status,
        "reasons": sorted(set(reasons)),
        "unit_name": UNIT_NAME,
        "fields": dict(fields) if fields is not None else None,
        "rendered_unit_sha256": (
            "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()
            if isinstance(rendered, str)
            else None
        ),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }
    if status == "PASS" and fields is not None:
        verdict["invocation_contract"] = engine_scanner_rendered_invocation_contract(fields)
    return verdict


# --------------------------------------------------------------------------- #
# §2 候選學習組態列(§10.5 #21):candidate-policy 渲染 + 私有 evidence-directory 謂詞。
# SSOT 是 ml_training.alr_candidate_policy(frozen gates/hash 語義都在那裡);本葉只補
# deterministic bytes 出口與 typed derive 謂詞,「不」複製任何策略語義。
# --------------------------------------------------------------------------- #
_POLICY_BUDGET_FIELDS = (
    "row_budget",
    "byte_budget",
    "collection_window_days",
    "max_new_entries_per_window",
)


def _canonical_policy_bytes(policy: Mapping[str, Any]) -> bytes:
    """provision 落盤位元組的鏡像(alr_candidate_policy._write_private_policy 同構)。"""
    return (
        json.dumps(dict(policy), ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def render_candidate_policy(
    template_path: str | Path, fields: Any
) -> tuple[bytes, str]:
    """§10.5 #21:自 reviewed template 渲染 candidate policy → (canonical bytes, hash)。

    typed 拒絕(全部發生在「任何輸出之前」):template 缺失/佔位(budget 非 null)/
    schema 或 fixed-semantics 漂移/hash 欄位偽造(SSOT `load_candidate_policy_template`
    + `render_candidate_policy_configuration` 執法);fields 非物件/鍵集不等於四個
    budget 鍵/非正整數。bytes deterministic → sha256(policy_config_hash)stable。
    """
    if not isinstance(fields, Mapping):
        raise _policy.CandidatePolicyError("policy_render_fields_invalid")
    if set(fields) != set(_POLICY_BUDGET_FIELDS):
        raise _policy.CandidatePolicyError("policy_render_fields_invalid")
    template = _policy.load_candidate_policy_template(template_path)
    policy = _policy.render_candidate_policy_configuration(
        template,
        row_budget=fields["row_budget"],
        byte_budget=fields["byte_budget"],
        collection_window_days=fields["collection_window_days"],
        max_new_entries_per_window=fields["max_new_entries_per_window"],
    )
    return _canonical_policy_bytes(policy), policy["policy_config_hash"]


def derive_candidate_policy_status(policy_bytes: Any, expected_hash: Any) -> dict[str, Any]:
    """rendered policy bytes 的 typed 再驗謂詞(caller 不可自證)。

    PASS ⇔ bytes 是 canonical 序列化 ∧ 內容過 SSOT
    `validate_candidate_policy_configuration`(frozen gates/budget/hash 全驗)∧
    policy_config_hash == expected_hash。否則 §10.2 typed
    CANDIDATE_POLICY_CONFIGURATION_REQUIRED + 逐項 reasons。
    """
    reasons: list[str] = []
    policy_hash: str | None = None
    if not isinstance(policy_bytes, (bytes, bytearray)):
        reasons.append("policy bytes must be bytes")
    elif len(policy_bytes) > _POLICY_MAX_BYTES:
        reasons.append("policy bytes exceed the size bound")
    else:
        try:
            loaded = json.loads(bytes(policy_bytes).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            loaded = None
            reasons.append("policy bytes are not valid JSON")
        if isinstance(loaded, dict):
            try:
                normalized = _policy.validate_candidate_policy_configuration(loaded)
                policy_hash = normalized["policy_config_hash"]
            except _policy.CandidatePolicyError as error:
                reasons.append(f"policy configuration rejected: {error}")
            else:
                if _canonical_policy_bytes(normalized) != bytes(policy_bytes):
                    reasons.append("policy bytes are not the canonical serialization")
        elif loaded is not None:
            reasons.append("policy bytes must decode to an object")
    if not isinstance(expected_hash, str) or re.fullmatch(
        r"[0-9a-f]{64}", expected_hash
    ) is None:
        reasons.append("expected policy_config_hash must be a 64-hex sha256")
    elif policy_hash is not None and policy_hash != expected_hash:
        reasons.append("policy_config_hash does not match the expected hash")
    return {
        "schema_version": "candidate_policy_render_verdict_v1",
        "status": "PASS" if not reasons else "CANDIDATE_POLICY_CONFIGURATION_REQUIRED",
        "reasons": reasons,
        "policy_config_hash": policy_hash,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }


def derive_candidate_evidence_directory_status(path: str | Path) -> dict[str, Any]:
    """§8.3/§10.5 #21:私有空 evidence rendezvous 的 typed 謂詞(caller 提供路徑)。

    PASS ⇔ 真目錄(非 symlink)∧ mode 恰為 0700 ∧ 空。首次 S2.4 install 必須為空
    (不得搬遷 legacy user-home 看板);owner/uid 屬 host 面(W3+ postcheck),源碼
    謂詞不冒充。
    """
    reasons: list[str] = []
    target = Path(path)
    try:
        meta = target.lstat()
    except OSError:
        reasons.append("evidence directory is missing")
        meta = None
    if meta is not None:
        if stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode):
            reasons.append("evidence directory must be a real directory (not a symlink)")
        elif stat.S_IMODE(meta.st_mode) != 0o700:
            reasons.append("evidence directory mode must be exactly 0700")
        elif sorted(entry.name for entry in target.iterdir()):
            reasons.append("evidence directory must be empty on first install")
    return {
        "schema_version": "candidate_evidence_directory_verdict_v1",
        "status": "PASS" if not reasons else "CANDIDATE_POLICY_CONFIGURATION_REQUIRED",
        "reasons": reasons,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }


# --------------------------------------------------------------------------- #
# §8.1 #2/#4:base_runtime_tree / launch_bundle manifest builders。
# 兩者都只走「caller 提供」的樹(tmp-dir 測試;絕不觸生產路徑),不可變樹謂詞
# fail-closed:symlink/device/fifo/group-other-writable/非法名/非法 mode 全拒。
# --------------------------------------------------------------------------- #
_FILE_MODES = ("0444", "0555")
_DIR_MODES = ("0555", "0755")
_INTERPRETER_TARGET = "bin/python3"
_NATIVE_LIBRARY_MARKERS = (".so", ".dylib")


def _is_native_library(name: str) -> bool:
    return name.endswith(_NATIVE_LIBRARY_MARKERS) or ".so." in name


def _walk_immutable_tree(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """caller 提供樹的不可變走訪 → sorted {path, type, mode, sha256} + typed reasons。"""
    reasons: list[str] = []
    if root.is_symlink() or not root.is_dir():
        return [], ["tree root must be an existing real directory (not a symlink)"]
    entries: list[dict[str, Any]] = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in sorted(dirnames) + sorted(filenames):
            child = current_path / name
            rel = os.path.relpath(child, root).replace(os.sep, "/")
            if _TREE_NAME_RE.fullmatch(name) is None:
                reasons.append(f"tree entry name is not allowlisted: {rel}")
                continue
            if ".." in rel.split("/"):
                reasons.append(f"tree entry escapes the tree root: {rel}")
                continue
            meta = os.lstat(child)
            mode_bits = stat.S_IMODE(meta.st_mode)
            mode = format(mode_bits, "04o")
            if stat.S_ISLNK(meta.st_mode):
                reasons.append(f"tree entry is a symlink: {rel}")
                continue
            if mode_bits & 0o022:
                reasons.append(f"tree entry is group/other writable: {rel}")
                continue
            if stat.S_ISDIR(meta.st_mode):
                if mode not in _DIR_MODES:
                    reasons.append(f"tree directory mode is not immutable: {rel}:{mode}")
                    continue
                entries.append({"path": rel, "type": "dir", "mode": mode, "sha256": None})
            elif stat.S_ISREG(meta.st_mode):
                if mode not in _FILE_MODES:
                    reasons.append(f"tree file mode is not immutable: {rel}:{mode}")
                    continue
                digest = hashlib.sha256(child.read_bytes()).hexdigest()
                entries.append({
                    "path": rel,
                    "type": "file",
                    "mode": mode,
                    "sha256": "sha256:" + digest,
                })
            else:
                # device/fifo/socket 等一律拒(§8.1 rejects devices)。
                reasons.append(f"tree entry is not a regular file or directory: {rel}")
    entries.sort(key=lambda entry: entry["path"])
    return entries, reasons


def build_base_runtime_tree_manifest(
    staging_root: str | Path,
    *,
    runtime_content_digest: str,
    platform: str,
    build_tool_versions: Mapping[str, str],
) -> dict[str, Any]:
    """§8.1 #2:自「提供的」staging 樹產出 base_runtime_tree_manifest_v1(typed)。

    綁定:sorted {path, type, mode, sha256} + interpreter target(bin/python3 必須
    在樹內)+ native-library inventory + S2.3 runtime_content_digest + platform +
    build-tool versions。self_digest 即 base_runtime_tree_digest(§8.1 #2 身分)。
    成功回 {status: "BUILT", ...};任一不可變謂詞不成立回 typed
    BASE_RUNTIME_TREE_INVALID + 逐項 reasons(絕不部分輸出)。
    """
    reasons: list[str] = []
    if not isinstance(runtime_content_digest, str) or _DIGEST_RE.fullmatch(
        runtime_content_digest
    ) is None:
        reasons.append("runtime_content_digest must be a sha256 digest")
    if not isinstance(platform, str) or _PLATFORM_RE.fullmatch(platform) is None:
        reasons.append("platform must be a target-platform token")
    tools: list[dict[str, str]] = []
    if not isinstance(build_tool_versions, Mapping) or not build_tool_versions:
        reasons.append("build_tool_versions must be a non-empty mapping")
    else:
        for tool in sorted(build_tool_versions):
            version = build_tool_versions[tool]
            if (
                not isinstance(tool, str)
                or _TREE_NAME_RE.fullmatch(tool) is None
                or not isinstance(version, str)
                or not version
            ):
                reasons.append(f"build tool version entry is malformed: {tool!r}")
                continue
            tools.append({"tool": tool, "version": version})
    entries, walk_reasons = _walk_immutable_tree(Path(staging_root))
    reasons.extend(walk_reasons)
    interpreter = next(
        (entry for entry in entries if entry["path"] == _INTERPRETER_TARGET), None
    )
    if interpreter is None or interpreter["type"] != "file":
        reasons.append("interpreter target bin/python3 is absent from the staging tree")
    elif interpreter["mode"] != "0555":
        reasons.append("interpreter target bin/python3 must be an executable 0555 file")
    if reasons:
        return {"status": "BASE_RUNTIME_TREE_INVALID", "reasons": sorted(set(reasons))}
    facade = resolve_facade()
    manifest: dict[str, Any] = {
        "schema_version": "base_runtime_tree_manifest_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "component": "engine_scanner",
        "runtime_content_digest": runtime_content_digest,
        "target_platform": platform,
        "build_tool_versions": tools,
        "interpreter_target": _INTERPRETER_TARGET,
        "native_libraries": [
            {"path": entry["path"], "sha256": entry["sha256"]}
            for entry in entries
            if entry["type"] == "file" and _is_native_library(entry["path"].rsplit("/", 1)[-1])
        ],
        "entries": entries,
    }
    manifest["self_digest"] = facade.artifact_self_digest(manifest)
    central_errors = facade.validate_aiml_artifact(manifest)
    if central_errors:
        return {"status": "BASE_RUNTIME_TREE_INVALID", "reasons": central_errors}
    return {
        "status": "BUILT",
        "base_runtime_tree_digest": manifest["self_digest"],
        "entry_count": len(entries),
        "native_library_count": len(manifest["native_libraries"]),
        "manifest": manifest,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }


def launch_tree_walk_digest(launch_tree_root: str | Path) -> tuple[str | None, list[str]]:
    """§8.1 #4:對「提供的」materialized launch 樹獨立走訪並 hash(typed)。"""
    entries, reasons = _walk_immutable_tree(Path(launch_tree_root))
    if not any(
        entry["path"] == _INTERPRETER_TARGET and entry["type"] == "file"
        for entry in entries
    ):
        reasons.append("launch tree interpreter bin/python3 is absent")
    if reasons:
        return None, sorted(set(reasons))
    facade = resolve_facade()
    return (
        facade.canonical_digest({
            "schema_version": "launch_tree_walk_v1",
            "entries": entries,
        }),
        [],
    )


def build_launch_bundle_manifest(
    launch_tree_root: str | Path,
    *,
    runtime_content_digest: str,
    base_runtime_tree_digest: str,
    application_bundle_digest: str,
    launcher_config_digest: str,
    target_platform: str,
) -> dict[str, Any]:
    """§8.1 #4:launch_bundle_manifest_v1 builder(self_digest == launch_bundle_digest)。

    綁定 {runtime_content_digest, base_runtime_tree_digest, application_bundle_digest,
    launcher_config_digest, launch_tree_digest, target_platform};launch_tree_digest
    由「提供的」materialized launch-tree 走訪獨立 hash。launch 葉名契約:digest 的
    64-hex(launches/<64-hex>,W2b verify_launch_prefix 消費)。
    """
    reasons: list[str] = []
    digests = {
        "runtime_content_digest": runtime_content_digest,
        "base_runtime_tree_digest": base_runtime_tree_digest,
        "application_bundle_digest": application_bundle_digest,
        "launcher_config_digest": launcher_config_digest,
    }
    for name, value in digests.items():
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            reasons.append(f"{name} must be a sha256 digest")
    if not isinstance(target_platform, str) or _PLATFORM_RE.fullmatch(target_platform) is None:
        reasons.append("target_platform must be a target-platform token")
    tree_digest, tree_reasons = launch_tree_walk_digest(launch_tree_root)
    reasons.extend(tree_reasons)
    if reasons or tree_digest is None:
        return {"status": "LAUNCH_BUNDLE_INVALID", "reasons": sorted(set(reasons))}
    facade = resolve_facade()
    manifest: dict[str, Any] = {
        "schema_version": "launch_bundle_manifest_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "component": "engine_scanner",
        **digests,
        "launch_tree_digest": tree_digest,
        "target_platform": target_platform,
    }
    manifest["self_digest"] = facade.artifact_self_digest(manifest)
    central_errors = facade.validate_aiml_artifact(manifest)
    if central_errors:
        return {"status": "LAUNCH_BUNDLE_INVALID", "reasons": central_errors}
    return {
        "status": "BUILT",
        "launch_bundle_digest": manifest["self_digest"],
        "launch_leaf_name": _digest_leaf(manifest["self_digest"]),
        "launch_tree_digest": tree_digest,
        "manifest": manifest,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }
