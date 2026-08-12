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
# W5 對抗審計第四輪 P1(PM path-scope ruling,延伸至本 W2-owned 葉):本葉不在 import 期把
# ``program_code`` 放進 sys.path。它是 facade 的 top-level import,於是「載入 facade 的每一個
# 進程」的 top-level namespace 都會多出 broker_connectors / exchange_connectors / dashboard /
# ai_agents——那必須是決策而非 import 副作用(§10.1.1 #4)。這是第三輪掃過但漏數的**第五處**
# (前四處:contracts 葉、W5 葉、W3 葉、W4 葉)。唯一需要 ``ml_training.*`` package 形匯入的
# 地方在函式內,改用 ``program_code_on_path`` 就地開窗、離開時只收回自己放的那一筆;本變更
# **縮小**能力,故與 §10.1.1 條件 4 同向而非相悖。
from aiml_gate_receipt_schema_core import (  # noqa: E402
    canonical_digest,
    owned_path_blob_projection_digest,
    owned_scope_worktree_delta,
    program_code_on_path,
    resolve_facade,
)

# §10.1/§10.3:W2a+W2b+W2c 三片的 owned-path 投影(wave-exit owned_path_manifest_digest
# 與 owned_path_diff_digest 綁定;每一路徑必須真實存在,診斷測試釘死)。
_W2_OWNED_PATHS = tuple(sorted((
    "helper_scripts/deploy/arcane-equilibrium-aiml-engine-scanner.service.template",
    "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_emit_sink.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_render.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_sql_scan.py",
    # 2026-08-08 拆分波:`schema_core` 的下層 view 葉(信任邊界獨立成檔)。它進入
    # engine-scanner 的 runtime import 閉包,不列入 owned scope 的話,對它的削弱性
    # 修改不會改變 owned_path_diff_digest ⇒ 治理不變量覆蓋面靜默收窄。
    "program_code/ml_training/aiml_gate_receipt_git_view.py",
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
    "tests/structure/test_agent_governance_s2_4_consumer_resilience_disposable.py",
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
    "application_bundle_builder": (
        "agent_governance_s2_4_install.build_application_bundle_manifest"
    ),
    "launch_leaf_contract": "launches/<64-hex launch_bundle_digest leaf>",
    # D1/D2:§8.3 consumer 側兩個 code-owned 契約的**名稱**面(值面在 live 折入)。
    "cluster_identity_relation": (
        "ml_training.alr_consumer_resilience.CLUSTER_IDENTITY_RELATION"
    ),
    "consumer_liveness_contract": (
        "ml_training.alr_consumer_resilience.derive_consumer_liveness_contract"
    ),
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


# --------------------------------------------------------------------------- #
# P1-6(W2 review)builder 活探針:舊 ABI 只以**硬編字串**代表 base/launch builder、
# 完全漏掉 application-bundle builder,而 w2_structural_errors 一個都沒執行過。後果:
# 把三個 builder 改壞或整個刪掉,只會改變 owned-byte digest——重發一份新 receipt 之後
# 照樣再導出 PASS。此處對三者各跑一次 deterministic 的真呼叫,並要求輸出**互相自洽**:
#   * base:code-owned hermetic 探針樹 → BUILT,self_digest == base_runtime_tree_digest;
#   * application:bound commit blob → BUILT,self_digest == application_bundle_digest,
#     並物化成一棵真的 application 樹;
#   * launch:同一棵探針樹 + 上面那棵**已物化**的 application 樹 → BUILT,且其綁定的
#     application digest 必須等於 application builder 給出的那一個;
#   * 反向:同一次呼叫換成一個語法正確但**無關**的 application digest 必須被拒
#     (P1-1 的綁定是活的,不是宣告)。
# 任一例外一律 fail-closed 記 None/非 BUILT → 投影變值 + 結構層顯式 reason。
# --------------------------------------------------------------------------- #
_PROBE_RUNTIME_CONTENT_DIGEST = "sha256:" + "4" * 64
_PROBE_LAUNCHER_CONFIG_DIGEST = "sha256:" + "5" * 64
_PROBE_FOREIGN_APPLICATION_DIGEST = "sha256:" + "6" * 64
_PROBE_TARGET_PLATFORM = "x86_64-unknown-linux-gnu"
_PROBE_BUILD_TOOL_VERSIONS = {"python3": "3.12.3", "uv": "0.5.0"}


def _application_bundle_probe_identity(manifest: dict[str, Any]) -> str:
    """Application builder 的 head-independent 語義投影身分。

    entries 已逐 byte 綁定全部 declared application 路徑;source_head 與由它再封出的
    learning_runtime_digest_v2/self_digest 只是這次 builder instance 的 carrier 身分。
    """
    semantic = {
        key: value
        for key, value in manifest.items()
        if key not in {"source_head", "learning_runtime_digest_v2", "self_digest"}
    }
    return canonical_digest({
        "schema_version": "application_bundle_probe_projection_v1",
        "semantic_manifest": semantic,
    })


def _launch_bundle_probe_identity(
    manifest: dict[str, Any], *, application_probe_identity: str
) -> str:
    """Launch builder 的 head-independent 語義投影,仍綁同一 application 語義。"""
    semantic = {
        key: value
        for key, value in manifest.items()
        if key
        not in {
            "application_bundle_digest",
            "application_source_head",
            "self_digest",
        }
    }
    semantic["application_bundle_probe_identity"] = application_probe_identity
    return canonical_digest({
        "schema_version": "launch_bundle_probe_projection_v1",
        "semantic_manifest": semantic,
    })


def _builder_probe(repo_root: Path) -> dict[str, Any]:
    """三個 §8.1 builder 的活再導出(全部在 tmp 目錄;零生產路徑、零網路)。"""
    import tempfile

    import agent_governance_s2_4_install as _install
    import agent_governance_s2_4_render as _render

    probe: dict[str, Any] = {
        "base_runtime_tree_status": None,
        "base_runtime_tree_probe_digest": None,
        "application_bundle_status": None,
        "application_bundle_probe_digest": None,
        "application_bundle_worktree_delta": None,
        "launch_bundle_status": None,
        "launch_bundle_probe_digest": None,
        "launch_binds_probed_application": None,
        "launch_foreign_application_digest_status": None,
    }
    with tempfile.TemporaryDirectory(prefix="aiml-w2-builder-probe-") as scratch:
        staging = Path(scratch) / "staging"
        application_root = Path(scratch) / "apps" / "probe"
        _render.materialize_probe_runtime_tree(staging)
        base = _render.build_base_runtime_tree_manifest(
            staging,
            runtime_content_digest=_PROBE_RUNTIME_CONTENT_DIGEST,
            platform=_PROBE_TARGET_PLATFORM,
            build_tool_versions=dict(_PROBE_BUILD_TOOL_VERSIONS),
        )
        probe["base_runtime_tree_status"] = base["status"]
        if base["status"] != "BUILT" or base["manifest"]["self_digest"] != base.get(
            "base_runtime_tree_digest"
        ):
            return probe
        probe["base_runtime_tree_probe_digest"] = base["base_runtime_tree_digest"]

        bundle = _install.build_application_bundle_manifest(
            repo_root,
            materialize_root=application_root,
            require_clean_declared_paths=False,
        )
        probe["application_bundle_status"] = bundle["status"]
        if bundle["status"] != "BUILT" or bundle["manifest"]["self_digest"] != bundle.get(
            "application_bundle_digest"
        ):
            return probe
        application_probe_identity = _application_bundle_probe_identity(
            bundle["manifest"]
        )
        probe["application_bundle_probe_digest"] = application_probe_identity
        probe["application_bundle_worktree_delta"] = list(
            bundle["declared_paths_worktree_delta"]
        )

        launch = _render.build_launch_bundle_manifest(
            staging,
            runtime_content_digest=_PROBE_RUNTIME_CONTENT_DIGEST,
            base_runtime_tree_digest=base["base_runtime_tree_digest"],
            application_bundle_digest=bundle["application_bundle_digest"],
            launcher_config_digest=_PROBE_LAUNCHER_CONFIG_DIGEST,
            target_platform=_PROBE_TARGET_PLATFORM,
            application_root=application_root,
            application_source_head=bundle["source_head"],
        )
        probe["launch_bundle_status"] = launch["status"]
        if (
            launch["status"] == "BUILT"
            and launch["manifest"]["self_digest"] == launch.get("launch_bundle_digest")
        ):
            probe["launch_bundle_probe_digest"] = _launch_bundle_probe_identity(
                launch["manifest"],
                application_probe_identity=application_probe_identity,
            )
            probe["launch_binds_probed_application"] = bool(
                launch["manifest"]["application_bundle_digest"]
                == bundle["application_bundle_digest"]
                and launch["verified_application_bundle_digest"]
                == bundle["application_bundle_digest"]
                and launch["manifest"]["base_runtime_tree_digest"]
                == base["base_runtime_tree_digest"]
            )
        foreign = _render.build_launch_bundle_manifest(
            staging,
            runtime_content_digest=_PROBE_RUNTIME_CONTENT_DIGEST,
            base_runtime_tree_digest=base["base_runtime_tree_digest"],
            application_bundle_digest=_PROBE_FOREIGN_APPLICATION_DIGEST,
            launcher_config_digest=_PROBE_LAUNCHER_CONFIG_DIGEST,
            target_platform=_PROBE_TARGET_PLATFORM,
            application_root=application_root,
            application_source_head=bundle["source_head"],
        )
        probe["launch_foreign_application_digest_status"] = foreign["status"]
    return probe


def w2_exported_abi_projection(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """W2 exported-ABI 投影:code-owned 骨架 + 六個「活」再導出(fail-closed 記 None)。

    折入的活面(§10.5 #3/#23/#27):
      * engine-scanner privilege-split 裁決 status(§2.1;非 PASS → 導出失敗);
      * application runtime-closure 裁決 status(§8.1;非 PASS → 導出失敗);
      * pg_acl_manifest_v1.json 的 self_digest(split 裁決附帶;中央閘拒即 None);
      * §8.3 invocation contract 於固定探針欄位下的 canonical digest(argv/env drift
        即變值)+ 渲染探針裁決 status;
      * policy/unit template 的檔案 sha256,且 unit template bytes 必須等於 code-owned
        `unit_template_text()`(template 檔漂移 → False → 導出失敗);
      * D1 §8.2/§8.3 叢集身分列的**封閉欄位契約** digest:該關聯的 migration 由 W6B 擁有,
        W2 只綁名稱與欄位序;不折入的話 W6B 改名/換序不會弄破任何 W2 receipt,卻會讓每次
        重連的 row-digest 比對永久失敗(exit 78)——drift 必須在 receipt 面就可見;
      * D2 常駐 liveness/staleness 契約 digest:讓 S2.5A 的 running-evidence postcheck
        有一個 receipt-bound 的輸入,不能退回「ActiveState=active」。
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
    try:
        with program_code_on_path():
            from ml_training import alr_consumer_resilience as _resilience

        identity_columns_digest = canonical_digest(
            list(_resilience.CLUSTER_IDENTITY_COLUMNS)
        )
        identity_relation_name = _resilience.CLUSTER_IDENTITY_RELATION
        liveness_contract_digest = canonical_digest(
            _resilience.derive_consumer_liveness_contract()
        )
        # P1-4:連線期錯誤分類的 locale 契約(值面折入 → 設定/名單漂移即 receipt 可見)。
        connect_locale_contract_digest = canonical_digest(
            _resilience.derive_connect_error_locale_contract()
        )
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        identity_columns_digest = None
        identity_relation_name = None
        liveness_contract_digest = None
        connect_locale_contract_digest = None
    try:
        builder_probe = _builder_probe(repo_root)
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        builder_probe = {
            "base_runtime_tree_status": None,
            "base_runtime_tree_probe_digest": None,
            "application_bundle_status": None,
            "application_bundle_probe_digest": None,
            "application_bundle_worktree_delta": None,
            "launch_bundle_status": None,
            "launch_bundle_probe_digest": None,
            "launch_binds_probed_application": None,
            "launch_foreign_application_digest_status": None,
        }
    return {
        **_W2_EXPORTED_ABI,
        **builder_probe,
        "connect_error_locale_contract_digest": connect_locale_contract_digest,
        # P1-5 可見性:owned 投影已改綁 commit blob(髒工作樹不再污染任何 digest),
        # 但「這份 receipt 是從一棵髒 owned scope 發射的」本身是事實 → 折入投影,受
        # exported_abi_digest 綁定,乾淨 checkout 重驗時一眼可見,而不是靜默。
        "owned_scope_worktree_delta": owned_scope_worktree_delta(
            repo_root, _W2_OWNED_PATHS
        ),
        "cluster_identity_relation_name": identity_relation_name,
        "cluster_identity_columns_digest": identity_columns_digest,
        "consumer_liveness_contract_digest": liveness_contract_digest,
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


def w2_owned_path_diff_digest(
    repo_root: Path = REPO_ROOT, *, source_head: str | None = None
) -> str:
    """W2 owned-path 內容投影 digest(同 W0/W1 機制,綁 W2 面)。

    P1-5(W2 review):讀的是**被綁定 commit 的 blob**,不是工作樹位元組——髒 checkout
    再也無法讓一份「宣稱乾淨 HEAD」的 receipt 在驗證時自我對上(缺檔/非 blob 記 None)。
    """
    return owned_path_blob_projection_digest(
        repo_root, _W2_OWNED_PATHS, source_head=source_head
    )


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
    if projection["cluster_identity_columns_digest"] is None:
        reasons.append(
            "W2 cluster-identity column contract cannot be re-derived (W6B-owned relation)"
        )
    if projection["consumer_liveness_contract_digest"] is None:
        reasons.append("W2 consumer liveness/staleness contract cannot be re-derived")
    if projection["connect_error_locale_contract_digest"] is None:
        reasons.append("W2 connect-error locale contract cannot be re-derived")
    # P1-6:三個 §8.1 builder 必須在當前 checkout 上真的跑出自洽輸出(硬編字串不算)。
    for field, label in (
        ("base_runtime_tree_status", "base runtime tree builder"),
        ("application_bundle_status", "application bundle builder"),
        ("launch_bundle_status", "launch bundle builder"),
    ):
        if projection[field] != "BUILT":
            reasons.append(
                f"W2 {label} does not re-derive BUILT on the current checkout "
                f"(status={projection[field]})"
            )
    for field, label in (
        ("base_runtime_tree_probe_digest", "base runtime tree"),
        ("application_bundle_probe_digest", "application bundle"),
        ("launch_bundle_probe_digest", "launch bundle"),
    ):
        if projection[field] is None:
            reasons.append(f"W2 {label} builder probe digest cannot be re-derived")
    if projection["launch_binds_probed_application"] is not True:
        reasons.append(
            "W2 launch bundle manifest does not bind the probed application/base "
            "identities (application bytes are not bound to the launch identity)"
        )
    if projection["launch_foreign_application_digest_status"] != "LAUNCH_BUNDLE_INVALID":
        reasons.append(
            "W2 launch bundle builder accepts an unrelated application_bundle_digest "
            "(the materialized application package is not verified before the launch "
            "identity is emitted)"
        )
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
        # P1-2:loader 閉包必須排序唯一、綁到樹內既有檔案,且 interpreter 本身在閉包內。
        closure = artifact["loader_closure"]
        binary_paths = [record["path"] for record in closure["binaries"]]
        if binary_paths != sorted(binary_paths) or len(binary_paths) != len(
            set(binary_paths)
        ):
            errors.append("base runtime tree loader_closure binaries must be sorted and unique")
        entry_paths = {
            entry["path"] for entry in artifact["entries"] if entry["type"] == "file"
        }
        if not set(binary_paths) <= entry_paths:
            errors.append("base runtime tree loader_closure binds a path outside the entries")
        if artifact["interpreter_target"] not in set(binary_paths):
            errors.append(
                "base runtime tree loader_closure does not cover the interpreter target"
            )
        provided = set()
        for record in closure["binaries"]:
            provided.add(record["path"].rsplit("/", 1)[-1])
            if record["soname"]:
                provided.add(record["soname"])
        for record in closure["binaries"]:
            if not set(record["needed"]) <= provided:
                errors.append(
                    "base runtime tree loader_closure has unresolved DT_NEEDED entries"
                )
                break
    return errors
