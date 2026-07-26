"""S2.4(WP4·W2)wave-exit 綁定的 code-owned 投影葉模組(§10.3 W2 row)。

自 facade(aiml_gate_receipt_validator)依 2000 行治理拆分抽出的 W2 面;facade 逐名
re-export,derive_wave_exit_status 的 W2 分支委派本葉。與 W0/W1 同一機制:

- `_W2_OWNED_PATHS`:W2a(retention split + pg_acl)/ W2b(application closure +
  bundle builder)/ W2c(unit·policy 渲染 + base/launch builders)三片的 owned-path
  集合,「路徑集合」digest 與「內容」投影 digest 全由 repo 當前 checkout 再導出;
- `w2_exported_abi_projection`:§10.2/§10.3 W2 exit 的 exported-ABI 投影,折入
  「活」再導出——engine-scanner privilege-split 裁決與 application runtime-closure
  裁決的 status 直接入投影(任一非 PASS → 投影變值且結構層另有顯式 reason)、
  invocation-contract 的 canonical digest、渲染探針裁決、pg_acl manifest digest、
  policy/unit template digest——ABI-surface drift 必然破壞 W2 導出(§10.5 #27);
- W2 的 PASS 另需前導 W1 wave-exit「連同其 W0/admission 鏈」一起再導出 PASS
  (predecessor 物件鏈驗在 facade 的 derive_wave_exit_status)。

receipt 只帶 evidence,PASS 恆由中央 validator 導出;通過「不」認證任何 runtime——
九 authority / production_apply_performed / running_attested 恆 false。
facade 依 2000 行治理拆分規約「只」經 schema_core.resolve_facade() 取得;governed
helper 模組(install/render)於函式內延遲匯入(保 monkeypatch 縫、避免 import 循環)。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from aiml_gate_receipt_schema_core import canonical_digest, resolve_facade  # noqa: E402

# §10.1/§10.3:W2a+W2b+W2c 三片的 owned-path 投影(wave-exit owned_path_manifest_digest
# 與 owned_path_diff_digest 綁定;每一路徑必須真實存在,診斷測試釘死)。
_W2_OWNED_PATHS = tuple(sorted((
    "helper_scripts/deploy/arcane-equilibrium-aiml-engine-scanner.service.template",
    "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_emit_sink.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_render.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_sql_scan.py",
    "program_code/ml_training/aiml_gate_receipt_schema_core.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    "program_code/ml_training/aiml_gate_receipt_wave_w2.py",
    "program_code/ml_training/alr_application_identity.py",
    "program_code/ml_training/alr_candidate_board_events.py",
    "program_code/ml_training/alr_consumer_resilience.py",
    "program_code/ml_training/alr_consumer_write_metrics.py",
    "program_code/ml_training/alr_event_consumer.py",
    "program_code/ml_training/alr_retention_runner.py",
    "program_code/ml_training/application_bundle_runtime_closure_v1.json",
    "program_code/ml_training/edge_feature_schema_contract.py",
    "program_code/ml_training/learning_runtime_manifest.py",
    "program_code/ml_training/pg_acl_manifest_v1.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/application_bundle_manifest_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/application_bundle_runtime_closure_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/base_runtime_tree_manifest_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/launch_bundle_manifest_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/pg_acl_manifest_v1.schema.json",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    "program_code/ml_training/tests/test_alr_application_identity.py",
    "program_code/ml_training/tests/test_alr_candidate_board_events.py",
    "program_code/ml_training/tests/test_alr_consumer_resilience.py",
    "program_code/ml_training/tests/test_alr_candidate_full_chain.py",
    "program_code/ml_training/tests/test_alr_event_consumer.py",
    "program_code/ml_training/tests/test_alr_retention_runner.py",
    "tests/structure/test_agent_governance_s2_4_install.py",
    "tests/structure/test_agent_governance_s2_4_install_application_bundle.py",
    "tests/structure/test_agent_governance_s2_4_install_engine_scanner.py",
    "tests/structure/test_agent_governance_s2_4_install_engine_scanner_disposable.py",
    "tests/structure/test_agent_governance_s2_4_install_integration.py",
    "tests/structure/test_agent_governance_s2_4_install_render.py",
    "tests/structure/test_learning_runtime_manifest_source_static.py",
)))
# §10.2/§10.3 W2 exported-ABI 的 code-owned 骨架(live 部分見 w2_exported_abi_projection)。
_W2_EXPORTED_ABI = {
    "engine_scanner_split_predicate": (
        "agent_governance_s2_4_install.derive_engine_scanner_privilege_split(status=PASS)"
    ),
    "application_closure_predicate": (
        "agent_governance_s2_4_install.derive_application_runtime_closure_status(status=PASS)"
    ),
    "unit_renderer": "agent_governance_s2_4_render.render_engine_scanner_unit",
    "rendered_unit_predicate": (
        "agent_governance_s2_4_render.derive_rendered_unit_status(status=PASS)"
    ),
    "invocation_contract": (
        "agent_governance_s2_4_render.engine_scanner_rendered_invocation_contract"
    ),
    "unit_name": "arcane-equilibrium-aiml-engine-scanner.service",
    "candidate_policy_renderer": "agent_governance_s2_4_render.render_candidate_policy",
    "candidate_policy_predicate": (
        "agent_governance_s2_4_render.derive_candidate_policy_status(status=PASS)"
    ),
    "base_runtime_tree_builder": (
        "agent_governance_s2_4_render.build_base_runtime_tree_manifest"
    ),
    "launch_bundle_builder": "agent_governance_s2_4_render.build_launch_bundle_manifest",
    "launch_leaf_contract": "launches/<64-hex launch_bundle_digest leaf>",
    "schema_ids": [
        "application_bundle_manifest_v1",
        "application_bundle_runtime_closure_v1",
        "base_runtime_tree_manifest_v1",
        "launch_bundle_manifest_v1",
    ],
}
# invocation-contract 投影的固定探針欄位(code-owned 合成 digest;與真 repo/runtime 無關,
# 只為把 argv/env 契約的「形狀」折成 deterministic digest——token 漂移即投影變值)。
_W2_ABI_PROBE_FIELDS = {
    "source_head": "0" * 40,
    "learning_runtime_digest": "sha256:" + "0" * 64,
    "learning_runtime_digest_v2": "sha256:" + "1" * 64,
    "application_bundle_digest": "sha256:" + "2" * 64,
    "launch_bundle_digest": "sha256:" + "3" * 64,
}
_PG_ACL_MANIFEST_REL = "program_code/ml_training/pg_acl_manifest_v1.json"
_POLICY_TEMPLATE_REL = "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json"
_UNIT_TEMPLATE_REL = (
    "helper_scripts/deploy/arcane-equilibrium-aiml-engine-scanner.service.template"
)


def _file_sha256(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def w2_exported_abi_projection(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """W2 exported-ABI 投影:code-owned 骨架 + 六個「活」再導出(fail-closed 記 None)。

    折入的活面(§10.5 #3/#23/#27):
      * engine-scanner privilege-split 裁決 status(§2.1;非 PASS → 導出失敗);
      * application runtime-closure 裁決 status(§8.1;非 PASS → 導出失敗);
      * pg_acl_manifest_v1.json 的 self_digest(split 裁決附帶;中央閘拒即 None);
      * §8.3 invocation contract 於固定探針欄位下的 canonical digest(argv/env drift
        即變值)+ 渲染探針裁決 status;
      * policy/unit template 的檔案 sha256,且 unit template bytes 必須等於 code-owned
        `unit_template_text()`(template 檔漂移 → False → 導出失敗)。
    任何例外一律 fail-closed 記 None(投影仍變值 → 導出失敗)。
    """
    import agent_governance_s2_4_install as _install
    import agent_governance_s2_4_render as _render

    try:
        split = _install.derive_engine_scanner_privilege_split(repo_root)
        split_status, pg_acl_digest = split["status"], split["manifest_digest"]
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        split_status, pg_acl_digest = None, None
    try:
        closure_status = _install.derive_application_runtime_closure_status(repo_root)["status"]
    except Exception:  # noqa: BLE001
        closure_status = None
    try:
        contract_digest = canonical_digest(
            _render.engine_scanner_rendered_invocation_contract(dict(_W2_ABI_PROBE_FIELDS))
        )
    except Exception:  # noqa: BLE001
        contract_digest = None
    try:
        unit_probe_status = _render.derive_rendered_unit_status(
            _render.render_engine_scanner_unit(dict(_W2_ABI_PROBE_FIELDS))
        )["status"]
    except Exception:  # noqa: BLE001
        unit_probe_status = None
    unit_template_bytes: bytes | None
    try:
        unit_template_bytes = (repo_root / _UNIT_TEMPLATE_REL).read_bytes()
    except OSError:
        unit_template_bytes = None
    try:
        template_matches = unit_template_bytes == _render.unit_template_text().encode("utf-8")
    except Exception:  # noqa: BLE001
        template_matches = False
    return {
        **_W2_EXPORTED_ABI,
        "engine_scanner_split_status": split_status,
        "application_closure_status": closure_status,
        "pg_acl_manifest_digest": pg_acl_digest,
        "invocation_contract_digest": contract_digest,
        "rendered_unit_probe_status": unit_probe_status,
        "policy_template_digest": _file_sha256(repo_root / _POLICY_TEMPLATE_REL),
        "unit_template_digest": (
            "sha256:" + hashlib.sha256(unit_template_bytes).hexdigest()
            if unit_template_bytes is not None
            else None
        ),
        "unit_template_matches_renderer": bool(template_matches),
    }


def w2_owned_path_diff_digest(repo_root: Path = REPO_ROOT) -> str:
    """W2 owned-path 內容投影 digest(同 W0/W1 機制,綁 W2 面;缺檔記 None)。"""
    projection: dict[str, str | None] = {}
    for rel in sorted(_W2_OWNED_PATHS):
        projection[rel] = _file_sha256(repo_root / rel)
    return canonical_digest(projection)


def w2_structural_errors(receipt: dict[str, Any], repo_root: Path = REPO_ROOT) -> list[str]:
    """wave=W2 的自足結構再導出(facade `_wave_exit_structural_errors` 委派)。

    除 digest 恆等外,把兩個 W2 exit 謂詞「顯式」折活:privilege-split 與
    application-closure 於當前 checkout 必須真的再導出 PASS(§10.3 W2 row exit——
    traced scanner 零 retention mutation/DELETE、application 只讀宣告檔),連同
    渲染探針/template 一致性;任一不成立即列 typed reason。
    """
    reasons: list[str] = []
    if receipt.get("predecessor_wave_receipt_digest") is None:
        reasons.append(
            "W2 wave-exit requires a non-null predecessor_wave_receipt_digest "
            "(the W1 wave-exit self_digest)"
        )
    projection = w2_exported_abi_projection(repo_root)
    if receipt.get("exported_abi_digest") != canonical_digest(projection):
        reasons.append(
            "wave-exit exported_abi_digest does not re-derive the W2 exported-ABI projection"
        )
    if projection["engine_scanner_split_status"] != "PASS":
        reasons.append(
            "W2 engine-scanner privilege-split does not re-derive PASS on the current checkout"
        )
    if projection["application_closure_status"] != "PASS":
        reasons.append(
            "W2 application runtime-closure does not re-derive PASS on the current checkout"
        )
    if projection["rendered_unit_probe_status"] != "PASS":
        reasons.append("W2 rendered-unit probe does not re-derive PASS")
    if projection["invocation_contract_digest"] is None:
        reasons.append("W2 invocation contract cannot be re-derived")
    if projection["unit_template_matches_renderer"] is not True:
        reasons.append(
            "W2 checked-in unit template does not byte-match the code-owned renderer shape"
        )
    if projection["pg_acl_manifest_digest"] is None:
        reasons.append("W2 pg_acl manifest digest cannot be re-derived")
    if projection["policy_template_digest"] is None:
        reasons.append("W2 candidate-policy template digest cannot be re-derived")
    if receipt.get("owned_path_manifest_digest") != canonical_digest(sorted(_W2_OWNED_PATHS)):
        reasons.append("wave-exit owned_path_manifest_digest is not the exact W2 owned-path set")
    if receipt.get("owned_path_diff_digest") != w2_owned_path_diff_digest(repo_root):
        reasons.append(
            "wave-exit owned_path_diff_digest does not re-derive the W2 owned-path content projection"
        )
    return reasons


def w2_chain_binding_errors(
    receipt: dict[str, Any],
    source_admission_receipt: dict[str, Any],
    predecessor_wave_receipt: dict[str, Any],
    head: str | None,
) -> list[str]:
    """W2 predecessor/admission/HEAD 綁定檢查(facade 於 W1 鏈已導 PASS 後呼叫)。"""
    reasons: list[str] = []
    if predecessor_wave_receipt.get("wave") != "W1":
        reasons.append("W2 wave-exit predecessor must be the W1 wave-exit receipt")
    if predecessor_wave_receipt.get("self_digest") != receipt.get(
        "predecessor_wave_receipt_digest"
    ):
        reasons.append(
            "W2 predecessor_wave_receipt_digest does not bind the derived W1 wave-exit receipt"
        )
    if source_admission_receipt.get("self_digest") != receipt.get(
        "source_admission_receipt_digest"
    ):
        reasons.append(
            "wave-exit source_admission_receipt_digest does not bind the derived admission receipt"
        )
    # source_head 四方一致 + 等於目前 checkout HEAD(同 W1 的 T2 姿態)。
    if head is None:
        reasons.append(
            "W2 wave-exit source_head cannot be bound: repo HEAD is unreadable (fail-closed)"
        )
    elif receipt.get("source_head") != head:
        reasons.append("W2 wave-exit source_head is not the current checkout HEAD")
    if receipt.get("source_head") != predecessor_wave_receipt.get("source_head"):
        reasons.append("W2 wave-exit source_head differs from the bound W1 wave-exit receipt")
    if receipt.get("source_head") != source_admission_receipt.get("source_head"):
        reasons.append("W2 wave-exit source_head differs from the bound admission receipt")
    return reasons


def w2_manifest_artifact_errors(schema_version: str, artifact: dict[str, Any]) -> list[str]:
    """base/launch manifest 的中央閘補充驗(self_digest 反偽造 + canonical 排序/一致)。

    ⚠ 乾淨的 [] 只證結構/完整性,「不」證 manifest 與某棵真樹相符——樹走訪/builder
    溯源屬 agent_governance_s2_4_render(caller 提供樹)。
    """
    facade = resolve_facade()
    errors: list[str] = []
    if artifact["self_digest"] != facade.artifact_self_digest(artifact):
        errors.append(f"{schema_version} self_digest is invalid")
    if schema_version == "base_runtime_tree_manifest_v1":
        paths = [entry["path"] for entry in artifact["entries"]]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            errors.append("base runtime tree entries must be sorted by path and unique")
        for entry in artifact["entries"]:
            if (entry["type"] == "file") != (entry["sha256"] is not None):
                errors.append(
                    "base runtime tree entry sha256 must be present for files and null for dirs"
                )
                break
        native = [item["path"] for item in artifact["native_libraries"]]
        if native != sorted(native) or len(native) != len(set(native)):
            errors.append("base runtime tree native_libraries must be sorted by path and unique")
        tools = [item["tool"] for item in artifact["build_tool_versions"]]
        if tools != sorted(tools) or len(tools) != len(set(tools)):
            errors.append("base runtime tree build_tool_versions must be sorted by tool and unique")
        if not any(
            entry["path"] == artifact["interpreter_target"] and entry["type"] == "file"
            for entry in artifact["entries"]
        ):
            errors.append("base runtime tree interpreter_target is absent from the entries")
    return errors
