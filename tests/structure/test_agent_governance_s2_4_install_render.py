"""S2.4(WP4·W2c)渲染與 manifest-builder 葉的 focused 測試。

覆蓋(§10.5 #21/#22 + §8.1 #2/#4):
* §8.3 渲染:checked-in template bytes == code-owned 形狀;渲染輸出含每一 normative
  設定(byte-exact 抽測);derive_rendered_unit_status 對移除/弱化/夾帶/token 竄改
  的代表性矩陣逐一 typed 拒絕;渲染欄位面封閉(caller 文本/任意鍵/缺欄/null 拒);
* invocation contract == 渲染輸出 ExecStart/Environment 的重 parse(WP3 C1 對齊消費面);
* candidate policy:render → derive PASS;佔位/null/hash 竄改於任何輸出前 typed 拒絕;
  bytes deterministic;私有空 evidence-directory 謂詞;
* base/launch manifest builders:tmp 樹 BUILT + 中央閘全綠 + digest 穩定;symlink/
  world-writable/fifo/缺 interpreter 的 typed 拒絕;launch_tree_digest 隨樹變。
全部 SOURCE 靜態執法;無任何 runtime/production 宣稱。
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_install as install  # noqa: E402
import agent_governance_s2_4_render as render  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

POLICY_TEMPLATE = ROOT / "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json"
UNIT_TEMPLATE = ROOT / render.UNIT_TEMPLATE_REL

_FIELDS = {
    "source_head": "0" * 40,
    "learning_runtime_digest": "sha256:" + "a" * 64,
    "learning_runtime_digest_v2": "sha256:" + "b" * 64,
    "application_bundle_digest": "sha256:" + "c" * 64,
    "launch_bundle_digest": "sha256:" + "d" * 64,
}
_BUDGETS = {
    "row_budget": 100,
    "byte_budget": 1_000_000,
    "collection_window_days": 14,
    "max_new_entries_per_window": 5,
}


# ═════════════════════════ §8.3 unit renderer(#22)═════════════════════════════
def test_checked_in_template_bytes_equal_code_owned_shape() -> None:
    # template 檔是部署 artifact;code-owned `_unit_lines` 是唯一權威——兩者逐位元組相等,
    # 任何 template 漂移在此紅、亦令 W2 exported-ABI 投影變值。
    assert UNIT_TEMPLATE.read_bytes() == render.unit_template_text().encode("utf-8")
    # 佔位 slot 僅限五個契約欄位的投影 token(source head/lrd v1/v2/app/launch)。
    tokens = {token for token in render._TEMPLATE_TOKENS.values()}
    text = UNIT_TEMPLATE.read_text(encoding="utf-8")
    import re as _re

    assert set(_re.findall(r"@[A-Z0-9_]+@", text)) == tokens


def test_rendered_unit_contains_every_normative_setting_and_derives_pass() -> None:
    rendered = render.render_engine_scanner_unit(dict(_FIELDS))
    # §8.3 逐設定 byte-exact 抽測(全文相等性由 derive 的 canonical byte-check 執法)。
    for needle in (
        "[Unit]\nDescription=Arcane Equilibrium ALR scanner event consumer\n",
        "After=network.target\nStartLimitIntervalSec=300s\nStartLimitBurst=3\n",
        "Type=exec\nUser=aiml-engine-scanner\nGroup=aiml-engine-scanner\n",
        "WorkingDirectory=/var/lib/arcane-equilibrium/aiml/engine-scanner\n",
        "LoadCredentialEncrypted=pg-dsn:/etc/credstore.encrypted/aiml-engine-scanner-pg-dsn\n",
        "RuntimeDirectory=arcane-equilibrium/aiml/engine-scanner\nRuntimeDirectoryMode=0700\n",
        "StateDirectory=arcane-equilibrium/aiml/engine-scanner\nStateDirectoryMode=0700\n",
        "Restart=on-failure\nRestartSec=30s\nRestartPreventExitStatus=78\n",
        "TimeoutStopSec=30s\nKillMode=control-group\n",
        "NoNewPrivileges=true\nLimitCORE=0\nUMask=0077\n",
        "PrivateTmp=true\nPrivateDevices=true\nProtectSystem=strict\nProtectHome=true\n",
        "ProtectKernelTunables=true\nProtectKernelModules=true\nProtectControlGroups=true\n",
        "ProtectClock=true\nRestrictRealtime=true\nRestrictSUIDSGID=true\nLockPersonality=true\n",
        "CapabilityBoundingSet=\nAmbientCapabilities=\nSystemCallArchitectures=native\n",
        "RestrictAddressFamilies=AF_UNIX AF_INET\nIPAddressDeny=any\nIPAddressAllow=127.0.0.1/32\n",
        "MemoryMax=512M\nTasksMax=64\n",
        "[Install]\nWantedBy=multi-user.target\n",
    ):
        assert needle in rendered, needle
    # 十個 Environment 行 + PG*/LD*/PYTHON* 全量 UnsetEnvironment。
    assert rendered.count("Environment=ALR_") == 10
    for env_key in render.ENGINE_SCANNER_ENV_KEYS:
        assert f"Environment={env_key}=" in rendered
    assert "UnsetEnvironment=PGPASSWORD " in rendered
    for scrubbed in ("LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH", "PYTHONUSERBASE"):
        assert scrubbed in rendered
    verdict = render.derive_rendered_unit_status(rendered)
    assert verdict["status"] == "PASS"
    assert verdict["reasons"] == []
    assert verdict["unit_name"] == "arcane-equilibrium-aiml-engine-scanner.service"
    assert verdict["fields"] == _FIELDS


@pytest.mark.parametrize(
    "mutation,needle",
    [
        # 移除 sandbox 設定
        (lambda text: text.replace("NoNewPrivileges=true\n", ""), "NoNewPrivileges"),
        # 放寬網路 allowlist
        (
            lambda text: text.replace("IPAddressAllow=127.0.0.1/32", "IPAddressAllow=any"),
            "IPAddressAllow",
        ),
        # 放寬資源上限
        (lambda text: text.replace("MemoryMax=512M", "MemoryMax=4G"), "MemoryMax"),
        # 夾帶 drop-in 式額外設定
        (
            lambda text: text.replace("[Install]", "ExecStartPre=/bin/true\n\n[Install]"),
            "ExecStartPre",
        ),
        # ExecStart token 竄改
        (lambda text: text.replace("--max-batch 32", "--max-batch 9999"), "ExecStart"),
        # 憑證機制弱化(LoadCredentialEncrypted → LoadCredential)
        (
            lambda text: text.replace("LoadCredentialEncrypted=", "LoadCredential="),
            "LoadCredential",
        ),
        # UnsetEnvironment 弱化(移除 PYTHONPATH scrub)
        (lambda text: text.replace(" PYTHONPATH", ""), "UnsetEnvironment"),
    ],
)
def test_removed_or_weakened_setting_is_typed_rejection(mutation, needle) -> None:
    rendered = render.render_engine_scanner_unit(dict(_FIELDS))
    verdict = render.derive_rendered_unit_status(mutation(rendered))
    assert verdict["status"] == "ENGINE_SCANNER_UNIT_INVALID"
    assert any(needle in reason for reason in verdict["reasons"]), verdict["reasons"]


@pytest.mark.parametrize(
    "fields,code_prefix",
    [
        ("not-a-mapping", "unit_fields_not_object"),
        ({**_FIELDS, "unit_text": "[Service]\nExecStart=/bin/sh"}, "unit_fields_unknown_key"),
        ({**_FIELDS, "ALR_EXTRA_ENV": "1"}, "unit_fields_unknown_key"),
        ({k: v for k, v in _FIELDS.items() if k != "launch_bundle_digest"}, "unit_field_missing"),
        ({**_FIELDS, "source_head": None}, "unit_field_missing"),
        ({**_FIELDS, "application_bundle_digest": "sha256:xyz"}, "unit_field_invalid"),
        ({**_FIELDS, "source_head": "0" * 39}, "unit_field_invalid"),
    ],
)
def test_renderer_rejects_caller_text_arbitrary_keys_and_unfilled_fields(
    fields, code_prefix
) -> None:
    with pytest.raises(render.EngineScannerUnitRenderError) as excinfo:
        render.render_engine_scanner_unit(fields)
    assert excinfo.value.code.startswith(code_prefix)


def test_invocation_contract_equals_reparse_of_rendered_unit() -> None:
    """WP3_INVOCATION_FINGERPRINT_ALIGNMENT_REQUIRED 的 argv 半邊釘死:契約 == 重 parse。"""
    rendered = render.render_engine_scanner_unit(dict(_FIELDS))
    contract = render.engine_scanner_rendered_invocation_contract(dict(_FIELDS))
    entries, reasons = render._parse_unit_entries(rendered)
    assert reasons == []
    exec_values = [value for (_s, key, value) in entries if key == "ExecStart"]
    assert len(exec_values) == 1
    assert exec_values[0].split() == contract["argv"]
    env_keys = [
        value.partition("=")[0] for (_s, key, value) in entries if key == "Environment"
    ]
    assert env_keys == contract["env_keys"] == list(render.ENGINE_SCANNER_ENV_KEYS)
    # exec_prefix = launches/<64-hex launch leaf>/bin/python3(W2b 葉名契約)。
    launch_leaf = _FIELDS["launch_bundle_digest"].split(":", 1)[1]
    assert contract["exec_prefix"] == (
        f"/opt/arcane-equilibrium/aiml/launches/{launch_leaf}/bin/python3"
    )
    assert contract["argv"][0] == contract["exec_prefix"]
    assert contract["unit_name"] == "arcane-equilibrium-aiml-engine-scanner.service"
    # derive PASS 時契約隨 verdict 匯出且與獨立構造相等。
    verdict = render.derive_rendered_unit_status(rendered)
    assert verdict["invocation_contract"] == contract
    # install 模組 re-export 同一 ABI(消費端唯一匯入面不變)。
    assert install.engine_scanner_rendered_invocation_contract is (
        render.engine_scanner_rendered_invocation_contract
    )


# ═════════════════════ candidate policy(§2 列/#21)═══════════════════════════
def test_candidate_policy_render_then_derive_pass_and_deterministic() -> None:
    policy_bytes, policy_hash = render.render_candidate_policy(POLICY_TEMPLATE, dict(_BUDGETS))
    verdict = render.derive_candidate_policy_status(policy_bytes, policy_hash)
    assert verdict["status"] == "PASS"
    assert verdict["reasons"] == []
    assert verdict["policy_config_hash"] == policy_hash
    # deterministic bytes → stable hash(重渲染逐位元組相等)。
    again_bytes, again_hash = render.render_candidate_policy(POLICY_TEMPLATE, dict(_BUDGETS))
    assert again_bytes == policy_bytes and again_hash == policy_hash


def test_candidate_policy_placeholder_null_and_hash_mismatch_fail_before_output(
    tmp_path,
) -> None:
    from ml_training.alr_candidate_policy import CandidatePolicyError

    template = json.loads(POLICY_TEMPLATE.read_text(encoding="utf-8"))
    # (a) 佔位 budget 被預填(template 不得帶 production default)→ 於任何輸出前 typed 拒。
    poisoned = copy.deepcopy(template)
    poisoned["row_budget"] = 999
    bad_template = tmp_path / "poisoned.json"
    bad_template.write_text(json.dumps(poisoned), encoding="utf-8")
    with pytest.raises(CandidatePolicyError):
        render.render_candidate_policy(bad_template, dict(_BUDGETS))
    # (b) 佔位 hash 被預填 → 同樣拒。
    poisoned_hash = copy.deepcopy(template)
    poisoned_hash["policy_config_hash"] = "0" * 64
    bad_hash = tmp_path / "poisoned-hash.json"
    bad_hash.write_text(json.dumps(poisoned_hash), encoding="utf-8")
    with pytest.raises(CandidatePolicyError):
        render.render_candidate_policy(bad_hash, dict(_BUDGETS))
    # (c) budget null / 欄位面不完整 → typed 拒。
    with pytest.raises(CandidatePolicyError):
        render.render_candidate_policy(POLICY_TEMPLATE, {**_BUDGETS, "row_budget": None})
    with pytest.raises(CandidatePolicyError):
        render.render_candidate_policy(POLICY_TEMPLATE, {"row_budget": 1})
    # (d) derive:hash mismatch / bytes 竄改 → CANDIDATE_POLICY_CONFIGURATION_REQUIRED。
    policy_bytes, policy_hash = render.render_candidate_policy(POLICY_TEMPLATE, dict(_BUDGETS))
    assert (
        render.derive_candidate_policy_status(policy_bytes, "0" * 64)["status"]
        == "CANDIDATE_POLICY_CONFIGURATION_REQUIRED"
    )
    tampered = policy_bytes.replace(b'"row_budget": 100', b'"row_budget": 999999')
    assert (
        render.derive_candidate_policy_status(tampered, policy_hash)["status"]
        == "CANDIDATE_POLICY_CONFIGURATION_REQUIRED"
    )


def test_private_empty_evidence_directory_predicate(tmp_path) -> None:
    target = tmp_path / "candidate-evidence"
    target.mkdir(mode=0o700)
    os.chmod(target, 0o700)
    assert render.derive_candidate_evidence_directory_status(target)["status"] == "PASS"
    # 過寬 mode → typed 拒。
    os.chmod(target, 0o755)
    wide = render.derive_candidate_evidence_directory_status(target)
    assert wide["status"] == "CANDIDATE_POLICY_CONFIGURATION_REQUIRED"
    os.chmod(target, 0o700)
    # 非空(legacy 看板不得搬遷)→ typed 拒。
    (target / "legacy.json").write_text("{}", encoding="utf-8")
    assert (
        render.derive_candidate_evidence_directory_status(target)["status"]
        == "CANDIDATE_POLICY_CONFIGURATION_REQUIRED"
    )
    # 缺失 → typed 拒。
    assert (
        render.derive_candidate_evidence_directory_status(tmp_path / "absent")["status"]
        == "CANDIDATE_POLICY_CONFIGURATION_REQUIRED"
    )


# ══════════════ base/launch manifest builders(§8.1 #2/#4)═════════════════════
def _make_staging_tree(root: Path) -> None:
    (root / "bin").mkdir(mode=0o755)
    python3 = root / "bin/python3"
    python3.write_bytes(b"#!/fake-interpreter\n")
    os.chmod(python3, 0o555)
    lib = root / "lib"
    lib.mkdir(mode=0o755)
    so_file = lib / "libssl.so.3"
    so_file.write_bytes(b"native-bytes")
    os.chmod(so_file, 0o555)
    data = lib / "python312.txt"
    data.write_bytes(b"stdlib-data")
    os.chmod(data, 0o444)


_BASE_KWARGS = {
    "runtime_content_digest": "sha256:" + "e" * 64,
    "platform": "x86_64-unknown-linux-gnu",
    "build_tool_versions": {"python3": "3.12.3", "uv": "0.5.0"},
}


def test_base_runtime_tree_manifest_builds_and_validates(tmp_path) -> None:
    _make_staging_tree(tmp_path)
    result = render.build_base_runtime_tree_manifest(tmp_path, **_BASE_KWARGS)
    assert result["status"] == "BUILT", result
    manifest = result["manifest"]
    assert validator.validate_aiml_artifact(manifest) == []
    assert result["base_runtime_tree_digest"] == manifest["self_digest"]
    assert manifest["interpreter_target"] == "bin/python3"
    assert [item["path"] for item in manifest["native_libraries"]] == ["lib/libssl.so.3"]
    assert [entry["path"] for entry in manifest["entries"]] == sorted(
        entry["path"] for entry in manifest["entries"]
    )
    # 同一樹重建 → digest 穩定(deterministic)。
    again = render.build_base_runtime_tree_manifest(tmp_path, **_BASE_KWARGS)
    assert again["base_runtime_tree_digest"] == result["base_runtime_tree_digest"]
    # dirs null sha256 / files digest(中央閘 file↔digest 一致驗的正面)。
    for entry in manifest["entries"]:
        assert (entry["type"] == "file") == (entry["sha256"] is not None)


@pytest.mark.parametrize(
    "poison,needle",
    [
        ("symlink", "symlink"),
        ("world_writable", "writable"),
        ("fifo", "regular file"),
        ("no_interpreter", "bin/python3"),
        ("bad_mode", "mode is not immutable"),
    ],
)
def test_base_runtime_tree_builder_rejects_hostile_trees(tmp_path, poison, needle) -> None:
    _make_staging_tree(tmp_path)
    if poison == "symlink":
        (tmp_path / "lib/evil-link").symlink_to(tmp_path / "bin/python3")
    elif poison == "world_writable":
        os.chmod(tmp_path / "lib/python312.txt", 0o666)
    elif poison == "fifo":
        os.mkfifo(tmp_path / "lib/evil-fifo")
        os.chmod(tmp_path / "lib/evil-fifo", 0o444)
    elif poison == "no_interpreter":
        (tmp_path / "bin/python3").unlink()
    elif poison == "bad_mode":
        os.chmod(tmp_path / "lib/python312.txt", 0o640)
    result = render.build_base_runtime_tree_manifest(tmp_path, **_BASE_KWARGS)
    assert result["status"] == "BASE_RUNTIME_TREE_INVALID"
    assert any(needle in reason for reason in result["reasons"]), result["reasons"]
    assert "manifest" not in result


def test_base_runtime_tree_builder_rejects_malformed_inputs(tmp_path) -> None:
    _make_staging_tree(tmp_path)
    bad = render.build_base_runtime_tree_manifest(
        tmp_path,
        runtime_content_digest="not-a-digest",
        platform="x86_64-unknown-linux-gnu",
        build_tool_versions={},
    )
    assert bad["status"] == "BASE_RUNTIME_TREE_INVALID"
    assert any("runtime_content_digest" in r for r in bad["reasons"])
    assert any("build_tool_versions" in r for r in bad["reasons"])


_LAUNCH_KWARGS = {
    "runtime_content_digest": "sha256:" + "e" * 64,
    "base_runtime_tree_digest": "sha256:" + "f" * 64,
    "application_bundle_digest": "sha256:" + "c" * 64,
    "launcher_config_digest": "sha256:" + "1" * 64,
    "target_platform": "x86_64-unknown-linux-gnu",
}


def test_launch_bundle_manifest_builds_and_binds_independent_tree_digest(tmp_path) -> None:
    _make_staging_tree(tmp_path)
    result = render.build_launch_bundle_manifest(tmp_path, **_LAUNCH_KWARGS)
    assert result["status"] == "BUILT", result
    manifest = result["manifest"]
    assert validator.validate_aiml_artifact(manifest) == []
    assert result["launch_bundle_digest"] == manifest["self_digest"]
    # launch 葉名 = digest 的 64-hex(W2b verify_launch_prefix 契約)。
    assert result["launch_leaf_name"] == manifest["self_digest"].split(":", 1)[1]
    # 提供樹改變 → launch_tree_digest / launch_bundle_digest 都變(獨立 hash 綁樹)。
    extra = tmp_path / "lib/site.txt"
    extra.write_bytes(b"more")
    os.chmod(extra, 0o444)
    changed = render.build_launch_bundle_manifest(tmp_path, **_LAUNCH_KWARGS)
    assert changed["launch_tree_digest"] != result["launch_tree_digest"]
    assert changed["launch_bundle_digest"] != result["launch_bundle_digest"]


def test_launch_bundle_builder_rejects_bad_digests_and_hostile_tree(tmp_path) -> None:
    _make_staging_tree(tmp_path)
    bad = render.build_launch_bundle_manifest(
        tmp_path, **{**_LAUNCH_KWARGS, "base_runtime_tree_digest": "nope"}
    )
    assert bad["status"] == "LAUNCH_BUNDLE_INVALID"
    assert any("base_runtime_tree_digest" in r for r in bad["reasons"])
    (tmp_path / "bin/python3").unlink()
    no_interp = render.build_launch_bundle_manifest(tmp_path, **_LAUNCH_KWARGS)
    assert no_interp["status"] == "LAUNCH_BUNDLE_INVALID"
    assert any("bin/python3" in r for r in no_interp["reasons"])


def test_manifest_tamper_is_rejected_by_the_central_gate(tmp_path) -> None:
    _make_staging_tree(tmp_path)
    base = render.build_base_runtime_tree_manifest(tmp_path, **_BASE_KWARGS)["manifest"]
    launch = render.build_launch_bundle_manifest(tmp_path, **_LAUNCH_KWARGS)["manifest"]
    for manifest, field, value in (
        (base, "runtime_content_digest", "sha256:" + "0" * 64),
        (launch, "application_bundle_digest", "sha256:" + "0" * 64),
    ):
        tampered = copy.deepcopy(manifest)
        tampered[field] = value  # 改 byte 不重封 self_digest → 中央閘抓
        assert any(
            "self_digest" in error
            for error in validator.validate_aiml_artifact(tampered)
        )
    # 排序竄改(entries 亂序 + 重封)→ canonical 排序驗抓。
    shuffled = copy.deepcopy(base)
    shuffled["entries"] = list(reversed(shuffled["entries"]))
    shuffled["self_digest"] = validator.artifact_self_digest(shuffled)
    assert any(
        "sorted" in error for error in validator.validate_aiml_artifact(shuffled)
    )
