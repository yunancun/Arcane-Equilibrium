"""S2.4 §8.1/§10.5 #17(W2b)application closure allowlist + bundle-manifest builder 測試。

覆蓋:
* 真 repo 樹上 derive_application_runtime_closure_status 導出 PASS 且 deterministic;
  checked-in allowlist 過中央閘,self_digest 偽造被拒;
* 合成違規樹:undeclared runtime import(escape)、effect-capable deploy/broker 模組
  被匯入或被宣告 → typed APPLICATION_BUNDLE_CLOSURE_INVALID;
* builder(committed-blob 溯源):同一 head 重建 → 同一 application_bundle_digest
  (determinism);dirty 宣告路徑 / 非當前 HEAD / committed symlink → typed 拒絕;
* 產出 manifest 過中央閘;runtime 葉(alr_application_identity)整樹重算與 builder
  digest 逐位元組相等(同一構造點,§8.1 #3)。

runtime 側(production preflight / consumer ABI)測試屬 sibling
``program_code/ml_training/tests/test_alr_application_identity.py``。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_install as install  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import alr_application_identity as app_identity  # noqa: E402

CLOSURE_PATH = ROOT / app_identity.RUNTIME_CLOSURE_REL


def _load_closure() -> dict:
    return json.loads(CLOSURE_PATH.read_text(encoding="utf-8"))


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _snapshot_tree(target: Path) -> Path:
    """把全部宣告路徑複製為獨立樹(供合成違規/committed-blob 溯源測試)。"""
    closure = app_identity.load_runtime_closure(CLOSURE_PATH)
    for rel in app_identity.closure_declared_paths(closure):
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, destination)
    return target


def _commit_snapshot(target: Path) -> str:
    _git(target, "init", "-q")
    _git(target, "config", "user.email", "w2b@test")
    _git(target, "config", "user.name", "w2b")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "bundle snapshot")
    return _git(target, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def committed_snapshot(tmp_path_factory) -> tuple[Path, str]:
    tree = _snapshot_tree(tmp_path_factory.mktemp("bundle-snapshot"))
    return tree, _commit_snapshot(tree)


# --------------------------------------------------------------------------- #
# 真 repo 樹:closure 裁決 PASS 與其證據面
# --------------------------------------------------------------------------- #
def test_real_tree_closure_verdict_derives_pass_and_is_deterministic() -> None:
    first = install.derive_application_runtime_closure_status()
    second = install.derive_application_runtime_closure_status()
    assert first["status"] == "PASS"
    assert first["reasons"] == []
    assert first == second
    assert first["closure_digest"] == _load_closure()["self_digest"]
    # 新 runtime 葉必須被宣告且 runtime-import 可達(雙向 exact-match 的活證)。
    closure = _load_closure()
    assert (
        "program_code/ml_training/alr_application_identity.py"
        in closure["python_modules"]
    )
    assert {
        "program_code/ml_training/aiml_gate_receipt_s2e_launch.py",
        "program_code/ml_training/aiml_gate_receipt_source_compatibility.py",
    }.issubset(closure["python_modules"])
    assert (
        "helper_scripts/maintenance_scripts/"
        "agent_governance_s2e_launch_receipts.py"
    ) not in closure["python_modules"]
    assert {
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_launch_genesis_receipt_v1.schema.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_launch_wave_receipt_v1.schema.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "receipt_carrier_attestation_v1.schema.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_launch_acceptance_review_bundle_v1.schema.json",
    }.issubset(closure["schema_resources"])
    assert first["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_checked_in_closure_passes_central_gate_and_forgery_is_rejected() -> None:
    closure = _load_closure()
    assert validator.validate_aiml_artifact(closure) == []
    forged = copy.deepcopy(closure)
    forged["python_modules"] = forged["python_modules"][:-1]
    # 不重簽 self_digest → 中央閘拒。
    assert any(
        "self_digest" in error for error in validator.validate_aiml_artifact(forged)
    )


def test_closure_never_admits_retention_or_effect_driver_modules() -> None:
    # §2.1 retention split + §8.1 effect-capable deny 的宣告面回歸。
    closure = _load_closure()
    for rel in closure["python_modules"]:
        name = rel.rsplit("/", 1)[-1]
        assert "retention" not in name, rel
        assert install._bundle_path_deny_reasons(rel) == [], rel


def test_closure_excludes_the_ambient_dsn_parquet_etl_import_but_keeps_its_identity_bytes() -> None:
    """W2 P1-C(E3 P1-2):parquet_etl 退出 *import* 閉包,但仍是 v2 身分的內容輸入。

    它真的會連 PG(duckdb ``ATTACH ... TYPE postgres`` + ambient ``OPENCLAW_DATABASE_URL``
    等 env 回退),故不得留在 runtime import 面;其**檔案內容**必須續留 bundle,否則
    runtime 端以 application root 重算 learning_runtime_digest_v2 會缺輸入而失敗。
    """
    closure = _load_closure()
    parquet = "program_code/ml_training/parquet_etl.py"
    assert parquet not in closure["python_modules"]
    assert parquet in closure["learning_runtime_inputs"]
    assert parquet in app_identity.closure_declared_paths(closure)
    # 取代它的 PG-surface-free 葉必須被宣告且 runtime-import 可達。
    for rel in (
        "program_code/ml_training/edge_feature_schema_contract.py",
        "program_code/ml_training/alr_consumer_resilience.py",
        "program_code/ml_training/alr_consumer_write_metrics.py",
    ):
        assert rel in closure["python_modules"], rel
    derived = install.build_engine_scanner_runtime_import_closure(
        ROOT,
        lazy_helper_roots=tuple(
            entry["module"] for entry in closure["runtime_lazy_helper_roots"]
        ),
    )
    assert parquet not in set(derived.values())
    assert install.derive_application_runtime_closure_status()["status"] == "PASS"


# --------------------------------------------------------------------------- #
# 合成違規樹:undeclared import escape / effect-capable inclusion
# --------------------------------------------------------------------------- #
def test_undeclared_runtime_import_is_refused(tmp_path: Path) -> None:
    tree = _snapshot_tree(tmp_path)
    smuggled = tree / "program_code/ml_training/alr_smuggled_helper.py"
    smuggled.write_text("VALUE = 1\n", encoding="utf-8")
    consumer = tree / "program_code/ml_training/alr_event_consumer.py"
    consumer.write_text(
        "from ml_training.alr_smuggled_helper import VALUE  # noqa\n"
        + consumer.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    verdict = install.derive_application_runtime_closure_status(tree)
    assert verdict["status"] == "APPLICATION_BUNDLE_CLOSURE_INVALID"
    assert any(
        "runtime import escapes the declared closure" in reason
        and "alr_smuggled_helper" in reason
        for reason in verdict["reasons"]
    )


def test_effect_capable_import_into_temp_copy_is_refused(tmp_path: Path) -> None:
    # §10.5 #17:合成把 deploy/broker 模組 import 進 consumer 副本 → typed 拒絕。
    tree = _snapshot_tree(tmp_path)
    driver = tree / "helper_scripts/maintenance_scripts/agent_governance_effects.py"
    driver.write_text("def apply_effect():\n    return 'boom'\n", encoding="utf-8")
    consumer = tree / "program_code/ml_training/alr_event_consumer.py"
    consumer.write_text(
        "import agent_governance_effects  # noqa\n"
        + consumer.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    verdict = install.derive_application_runtime_closure_status(tree)
    assert verdict["status"] == "APPLICATION_BUNDLE_CLOSURE_INVALID"
    assert any(
        "runtime import escapes the declared closure" in reason
        and "agent_governance_effects" in reason
        for reason in verdict["reasons"]
    )


def test_declared_effect_capable_or_broker_module_is_refused(tmp_path: Path) -> None:
    # 宣告面 deny:把 effect driver / broker 模組寫進 allowlist 亦拒(不靠 import 縫)。
    tree = _snapshot_tree(tmp_path)
    closure = _load_closure()
    for smuggled in (
        "helper_scripts/maintenance_scripts/agent_governance_effects.py",
        "program_code/ml_training/bybit_order_router.py",
    ):
        (tree / smuggled).parent.mkdir(parents=True, exist_ok=True)
        (tree / smuggled).write_text("VALUE = 1\n", encoding="utf-8")
        forged = copy.deepcopy(closure)
        forged["python_modules"] = sorted(forged["python_modules"] + [smuggled])
        forged["self_digest"] = validator.artifact_self_digest(
            {k: v for k, v in forged.items() if k != "self_digest"}
        )
        target = tree / app_identity.RUNTIME_CLOSURE_REL
        target.write_text(
            json.dumps(forged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verdict = install.derive_application_runtime_closure_status(tree)
        assert verdict["status"] == "APPLICATION_BUNDLE_CLOSURE_INVALID"
        assert any(
            ("effect-capable" in reason or "broker/order" in reason)
            and smuggled in reason
            for reason in verdict["reasons"]
        ), verdict["reasons"]


def test_forbidden_path_families_are_denied() -> None:
    # deny 謂詞單元面:tests/caches/pyc/git/credential/deploy-driver/escape 全拒。
    for rel, needle in (
        ("program_code/ml_training/tests/test_x.py", "forbidden path family"),
        ("program_code/ml_training/__pycache__/x.pyc", "forbidden path family"),
        (".git/config", "forbidden mutable/effect path prefix"),
        ("program_code/ml_training/x.pyc", "forbidden cache/credential"),
        ("secrets/operator.pem", "forbidden cache/credential"),
        ("helper_scripts/deploy/install_engine.py", "effect-capable deployment driver"),
        ("helper_scripts/deploy/rollout.sh", "effect-capable deployment driver"),
        ("docs/../secrets.py", "path escapes the bundle root"),
    ):
        reasons = install._bundle_path_deny_reasons(rel)
        assert any(needle in reason for reason in reasons), (rel, reasons)


# --------------------------------------------------------------------------- #
# builder:committed-blob 溯源 + determinism + typed 拒絕
# --------------------------------------------------------------------------- #
def test_builder_builds_deterministically_from_committed_snapshot(
    committed_snapshot,
) -> None:
    tree, head = committed_snapshot
    first = install.build_application_bundle_manifest(tree, head)
    second = install.build_application_bundle_manifest(tree, head)
    assert first["status"] == "BUILT"
    assert first["source_head"] == head
    # §10.5 #17:同一 head → 同一 digest(determinism)。
    assert (
        first["application_bundle_digest"] == second["application_bundle_digest"]
    )
    manifest = first["manifest"]
    assert validator.validate_aiml_artifact(manifest) == []
    assert manifest["self_digest"] == first["application_bundle_digest"]
    assert manifest["entrypoint"] == "ml_training.alr_event_consumer"
    assert manifest["source_head"] == head
    entry_paths = [entry["path"] for entry in manifest["entries"]]
    assert entry_paths == sorted(entry_paths)
    assert app_identity.RUNTIME_CLOSURE_REL in entry_paths
    assert all(entry["mode"] in {"0444", "0555"} for entry in manifest["entries"])


def test_runtime_tree_recompute_matches_builder_digest(
    committed_snapshot, tmp_path: Path
) -> None:
    # §8.1 #3:builder(committed blobs)與 runtime(整樹重算)同一構造點 → 同一 digest。
    tree, head = committed_snapshot
    built = install.build_application_bundle_manifest(tree, head)
    assert built["status"] == "BUILT"
    apps_root = tmp_path / "apps"
    for entry in built["manifest"]["entries"]:
        destination = apps_root / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tree / entry["path"], destination)
        os.chmod(destination, int(entry["mode"], 8))
    digest, document = app_identity.recompute_application_bundle_digest(
        apps_root, source_head=head
    )
    assert digest == built["application_bundle_digest"]
    assert document["entries"] == built["manifest"]["entries"]


def test_builder_refuses_dirty_declared_path(tmp_path: Path) -> None:
    tree = _snapshot_tree(tmp_path)
    head = _commit_snapshot(tree)
    victim = tree / "requirements-ml.txt"
    victim.write_text(victim.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
    result = install.build_application_bundle_manifest(tree, head)
    assert result["status"] == "APPLICATION_BUNDLE_SOURCE_DIRTY"
    assert any("requirements-ml.txt" in reason for reason in result["reasons"])


def test_builder_refuses_non_checkout_head_and_malformed_head(
    committed_snapshot,
) -> None:
    tree, _head = committed_snapshot
    result = install.build_application_bundle_manifest(tree, "f" * 40)
    assert result["status"] == "APPLICATION_BUNDLE_SOURCE_HEAD_MISMATCH"
    result = install.build_application_bundle_manifest(tree, "not-a-head")
    assert result["status"] == "APPLICATION_BUNDLE_SOURCE_HEAD_MISMATCH"


def test_builder_refuses_committed_symlink(tmp_path: Path) -> None:
    tree = _snapshot_tree(tmp_path)
    victim = tree / "requirements-ml.lock"
    real = tree / "requirements-ml.lock.real"
    victim.rename(real)
    victim.symlink_to(real.name)
    # symlink 需連同 target 一起提交;closure 裁決在 builder 之前即以 typed 拒絕。
    _commit_snapshot(tree)
    head = _git(tree, "rev-parse", "HEAD")
    result = install.build_application_bundle_manifest(tree, head)
    assert result["status"] == "APPLICATION_BUNDLE_CLOSURE_INVALID"
    assert any(
        "symlink" in reason and "requirements-ml.lock" in reason
        for reason in result["reasons"]
    )
