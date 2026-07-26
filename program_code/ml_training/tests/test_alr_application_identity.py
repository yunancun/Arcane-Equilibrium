"""S2.4 §8.1/§8.3(W2b)runtime application-identity 葉 + consumer production ABI 測試。

覆蓋(§10.5 #17 runtime 側):
* 物化 app tree 的整樹重算 == builder digest;缺檔/多檔/改檔/symlink/mode 漂移 →
  typed AlrApplicationIdentityError;
* production preflight:全期望硬比對 PASS;缺期望/receipt 逃出 root/pin 不符/launch
  prefix 不符/topology guard 竄改 → typed 拒絕(絕不回退 ambient/Git 來源);
* consumer main 佈線:--application-root 進 production 模式;preflight 失敗與
  permanent pre-DB 失敗 exit 78(EX_CONFIG);run_kwargs(唯一根/pinned head/
  engine-scanner DSN 身分)正確下傳;dev/test 路徑不變。

builder(committed-blob 溯源)測試屬 sibling
``tests/structure/test_agent_governance_s2_4_install_application_bundle.py``。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ml_training import alr_application_identity as app_identity
from ml_training import alr_event_consumer as consumer
from ml_training.aiml_gate_receipt_validator import artifact_self_digest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HELPERS = _REPO_ROOT / "helper_scripts/maintenance_scripts"
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))

import agent_governance_s2_4_install as install  # noqa: E402

_LAUNCH_HEX = "e" * 64
_LAUNCH_DIGEST = "sha256:" + _LAUNCH_HEX
_LAUNCH_PREFIX = f"/opt/arcane-equilibrium/aiml/launches/{_LAUNCH_HEX}"


@pytest.fixture(autouse=True)
def _simulate_guard_host_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    """P2-4:在無 root 的 checkout 上模擬 guard 的真實 host 佈署身分(唯一縫)。

    mode(恰 0440)照真檔驗;只有「讀 owner uid / group 名」這條縫被替換,判定邏輯
    不動——本 fixture 因此不可能放行 group-writable 或非 root 所有的 guard。
    """
    monkeypatch.setattr(
        app_identity,
        "guard_host_identity",
        lambda st: (
            app_identity.TOPOLOGY_GUARD_REQUIRED_OWNER_UID,
            app_identity.TOPOLOGY_GUARD_REQUIRED_GROUP,
        ),
    )


def _write_topology_guard(path: Path) -> dict:
    guard = {
        "schema_version": "pg_topology_runtime_guard_v1",
        "guard_path": (
            "/etc/arcane-equilibrium/aiml/engine-scanner/topology-runtime-guard.json"
        ),
        "cluster_identity_row_digest": "sha256:" + "1" * 64,
        "plan_topology_digest": "sha256:" + "2" * 64,
        "runtime_endpoint": {"host": "127.0.0.1", "port": 5432, "dbname": "trading_ai"},
        "system_identifier": "7357224466880011223",
        "database_oid": 16384,
        "server_major_version": 16,
        "binding_nonce": "host-nonce-1",
        "expected_topology_values_digest": "sha256:" + "3" * 64,
    }
    guard["self_digest"] = artifact_self_digest(guard)
    path.write_text(
        json.dumps(guard, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o440)
    return guard


@pytest.fixture(scope="module")
def bundle(tmp_path_factory) -> dict:
    """committed snapshot → builder → 物化 immutable app tree(§8.1 apps/<digest> 形)。"""
    snapshot = tmp_path_factory.mktemp("w2b-snapshot")
    closure = app_identity.load_runtime_closure(
        _REPO_ROOT / app_identity.RUNTIME_CLOSURE_REL
    )
    for rel in app_identity.closure_declared_paths(closure):
        destination = snapshot / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPO_ROOT / rel, destination)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "w2b@test"),
        ("config", "user.name", "w2b"),
        ("add", "-A"),
        ("commit", "-q", "-m", "bundle snapshot"),
    ):
        subprocess.run(["git", "-C", str(snapshot), *args], check=True)
    head = subprocess.run(
        ["git", "-C", str(snapshot), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    built = install.build_application_bundle_manifest(snapshot, head)
    assert built["status"] == "BUILT", built
    apps_root = tmp_path_factory.mktemp("w2b-apps") / "bundle"
    for entry in built["manifest"]["entries"]:
        destination = apps_root / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(snapshot / entry["path"], destination)
        os.chmod(destination, int(entry["mode"], 8))
    receipt = json.loads(
        (apps_root / app_identity.COMPATIBILITY_RECEIPT_V2_REL).read_text(
            encoding="utf-8"
        )
    )
    return {
        "root": apps_root,
        "head": head,
        "digest": built["application_bundle_digest"],
        "manifest": built["manifest"],
        "v2_pin": receipt["learning_runtime_digest"],
    }


def _mutable_copy(bundle: dict, tmp_path: Path) -> Path:
    target = tmp_path / "bundle-copy"
    shutil.copytree(bundle["root"], target)
    return target


def _preflight_kwargs(bundle: dict, guard_path: Path, **overrides) -> dict:
    kwargs = {
        "application_root": bundle["root"],
        "source_head": bundle["head"],
        "expected_compatibility_receipt_v2": (
            bundle["root"] / app_identity.COMPATIBILITY_RECEIPT_V2_REL
        ),
        "expected_application_bundle_digest": bundle["digest"],
        "expected_launch_bundle_digest": _LAUNCH_DIGEST,
        "topology_guard_file": guard_path,
        "expected_learning_runtime_digest_v2": bundle["v2_pin"],
        "interpreter_prefix": _LAUNCH_PREFIX,
    }
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------- #
# 整樹重算:PASS 與 typed 負例(缺檔/多檔/改檔/symlink/mode)
# --------------------------------------------------------------------------- #
def test_recompute_matches_builder_digest_and_verify_passes(bundle) -> None:
    digest, document = app_identity.recompute_application_bundle_digest(
        bundle["root"], source_head=bundle["head"]
    )
    assert digest == bundle["digest"]
    assert document == bundle["manifest"]
    verified = app_identity.verify_application_root(
        bundle["root"],
        source_head=bundle["head"],
        expected_application_bundle_digest=bundle["digest"],
    )
    assert verified["self_digest"] == bundle["digest"]


@pytest.mark.parametrize(
    "mutate,expected_code",
    [
        ("missing", "bundle_entry_missing"),
        ("extra", "bundle_undeclared_paths"),
        ("changed", "application_bundle_digest_mismatch"),
        ("symlink", "bundle_undeclared_paths"),
        ("mode", "bundle_entry_mode_invalid"),
    ],
)
def test_tree_drift_is_typed_fail_closed(
    bundle, tmp_path: Path, mutate: str, expected_code: str
) -> None:
    root = _mutable_copy(bundle, tmp_path)
    victim = root / "program_code/ml_training/alr_safe_file.py"
    if mutate == "missing":
        victim.unlink()
    elif mutate == "extra":
        (root / "program_code/ml_training/undeclared_extra.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
    elif mutate == "changed":
        os.chmod(victim, 0o644)
        victim.write_bytes(victim.read_bytes() + b"# drift\n")
        os.chmod(victim, 0o444)
    elif mutate == "symlink":
        moved = victim.with_suffix(".real")
        victim.rename(moved)
        victim.symlink_to(moved.name)
    elif mutate == "mode":
        os.chmod(victim, 0o644)
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.verify_application_root(
            root,
            source_head=bundle["head"],
            expected_application_bundle_digest=bundle["digest"],
        )
    assert str(error.value).startswith(expected_code), str(error.value)


# --------------------------------------------------------------------------- #
# production preflight:PASS + typed 負例(期望缺失/逃出 root/pin 不符/guard/launch)
# --------------------------------------------------------------------------- #
def test_production_preflight_passes_with_exact_expectations(
    bundle, tmp_path: Path
) -> None:
    guard = _write_topology_guard(tmp_path / "topology-runtime-guard.json")
    result = app_identity.run_production_preflight(
        **_preflight_kwargs(bundle, tmp_path / "topology-runtime-guard.json")
    )
    assert result["status"] == "PASS"
    assert result["application_bundle_digest"] == bundle["digest"]
    assert result["topology_guard_digest"] == guard["self_digest"]
    assert result["source_value_guard"] == {
        "schema_version": "source_value_guard_v1",
        "status": "PASS",
        "learning_runtime_digest_v2": bundle["v2_pin"],
    }
    run_kwargs = result["run_kwargs"]
    assert run_kwargs["repo_root"] == bundle["root"]
    assert run_kwargs["pinned_repo_source_head"] == bundle["head"]
    # §8.3:production DSN 綁 S2.3 身分 aiml_engine_scanner(非 alr_shadow)。
    assert run_kwargs["dsn_required_identity"]["user"] == "aiml_engine_scanner"
    assert str(run_kwargs["expected_compatibility_receipt"]).startswith(
        str(bundle["root"])
    )


@pytest.mark.parametrize(
    "missing",
    [
        "expected_compatibility_receipt_v2",
        "expected_application_bundle_digest",
        "expected_launch_bundle_digest",
        "topology_guard_file",
        "expected_learning_runtime_digest_v2",
    ],
)
def test_missing_expectation_never_falls_back(
    bundle, tmp_path: Path, missing: str
) -> None:
    _write_topology_guard(tmp_path / "guard.json")
    kwargs = _preflight_kwargs(bundle, tmp_path / "guard.json", **{missing: None})
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.run_production_preflight(**kwargs)
    assert str(error.value) == f"expectation_missing:{missing}"


def test_receipt_outside_application_root_is_refused(bundle, tmp_path: Path) -> None:
    _write_topology_guard(tmp_path / "guard.json")
    outside = tmp_path / "outside-receipt-v2.json"
    shutil.copyfile(
        bundle["root"] / app_identity.COMPATIBILITY_RECEIPT_V2_REL, outside
    )
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.run_production_preflight(
            **_preflight_kwargs(
                bundle,
                tmp_path / "guard.json",
                expected_compatibility_receipt_v2=outside,
            )
        )
    assert str(error.value) == "compatibility_receipt_v2_outside_application_root"


def test_bundle_digest_and_v2_pin_mismatches_are_refused(
    bundle, tmp_path: Path
) -> None:
    _write_topology_guard(tmp_path / "guard.json")
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.run_production_preflight(
            **_preflight_kwargs(
                bundle,
                tmp_path / "guard.json",
                expected_application_bundle_digest="sha256:" + "0" * 64,
            )
        )
    assert str(error.value) == "application_bundle_digest_mismatch"
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.run_production_preflight(
            **_preflight_kwargs(
                bundle,
                tmp_path / "guard.json",
                expected_learning_runtime_digest_v2="sha256:" + "0" * 64,
            )
        )
    assert str(error.value) == "learning_runtime_digest_v2_pin_mismatch"


def test_launch_prefix_and_guard_tamper_are_refused(bundle, tmp_path: Path) -> None:
    guard_path = tmp_path / "guard.json"
    guard = _write_topology_guard(guard_path)
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.run_production_preflight(
            **_preflight_kwargs(
                bundle, guard_path, interpreter_prefix="/usr/local/other-venv"
            )
        )
    assert str(error.value) == "launch_prefix_mismatch"
    # guard 竄改(不重簽 self_digest)→ typed 拒絕。
    guard["binding_nonce"] = "tampered"
    os.chmod(guard_path, 0o640)
    guard_path.write_text(
        json.dumps(guard, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(guard_path, 0o440)
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.run_production_preflight(**_preflight_kwargs(bundle, guard_path))
    assert str(error.value) == "topology_guard_self_digest_mismatch"


@pytest.mark.parametrize(
    "posture,expected",
    [
        ("group_writable", "topology_guard_mode_invalid:0660"),
        ("world_readable", "topology_guard_mode_invalid:0444"),
        ("non_root_owner", "topology_guard_owner_invalid:1000"),
        ("wrong_group", "topology_guard_group_invalid:staff"),
        ("unresolved_group", "topology_guard_group_invalid:unresolved"),
    ],
)
def test_guard_host_posture_drift_is_refused_before_the_guard_is_trusted(
    bundle, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, posture: str, expected: str
) -> None:
    """P2-4:契約要求 root 所有、scanner 群組、mode 恰 0440——三者都必須在信任前驗過。

    修前只拒 world-write 位元,於是 **group-writable(0660)** 的 guard 每次重連都通過:
    scanner 群組內的另一個行程可以改寫 guard 值再重算其 self_digest(self_digest 只證
    完整性,不證作者),身分閘就被對齊到攻擊者選定的叢集。
    """
    guard_path = tmp_path / "guard.json"
    _write_topology_guard(guard_path)
    if posture == "group_writable":
        os.chmod(guard_path, 0o660)
    elif posture == "world_readable":
        os.chmod(guard_path, 0o444)
    elif posture == "non_root_owner":
        monkeypatch.setattr(
            app_identity, "guard_host_identity", lambda st: (1000, "aiml-engine-scanner")
        )
    elif posture == "wrong_group":
        monkeypatch.setattr(app_identity, "guard_host_identity", lambda st: (0, "staff"))
    else:
        monkeypatch.setattr(app_identity, "guard_host_identity", lambda st: (0, None))
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.verify_topology_guard(guard_path)
    assert str(error.value) == expected
    # 同一姿態經 production 前置也必須被拒(重連路徑走同一個謂詞)。
    with pytest.raises(app_identity.AlrApplicationIdentityError) as preflight_error:
        app_identity.run_production_preflight(**_preflight_kwargs(bundle, guard_path))
    assert str(preflight_error.value) == expected


def test_guard_group_name_resolution_is_the_only_host_identity_seam() -> None:
    """P2-4:host 身分只從 stat 讀,判定邏輯不可被縫替換(縫只回事實)。"""
    fake = os.stat_result((0o100440, 1, 1, 1, 0, 0, 0, 0, 0, 0))
    assert app_identity.guard_host_identity(fake)[0] == 0
    assert app_identity.TOPOLOGY_GUARD_REQUIRED_MODE == 0o440
    assert app_identity.TOPOLOGY_GUARD_REQUIRED_OWNER_UID == 0
    assert app_identity.TOPOLOGY_GUARD_REQUIRED_GROUP == "aiml-engine-scanner"


# --------------------------------------------------------------------------- #
# P1-7:application root 自身的別名/重指防護
# --------------------------------------------------------------------------- #
def test_symlinked_application_root_is_refused(bundle, tmp_path: Path) -> None:
    """P1-7:digest 名下的 leaf 自身是 symlink 時,``Path.is_dir()`` 會跟隨它。

    修前:walk 只拒 root **以下**的 symlink,故別名指向的樹整棵通過 digest 前置,而
    ``run_kwargs.repo_root`` 拿到的仍是那個未解析的別名——preflight 之後把別名重指到
    另一棵樹,unit 路徑與 digest 都沒變,receipts 與 runtime 輸入卻已換人。
    """
    guard_path = tmp_path / "guard.json"
    _write_topology_guard(guard_path)
    alias = tmp_path / ("alias-" + bundle["digest"].split(":", 1)[1])
    alias.symlink_to(bundle["root"], target_is_directory=True)
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.run_production_preflight(
            **_preflight_kwargs(bundle, guard_path, application_root=alias)
        )
    assert str(error.value) == "application_root_not_a_real_directory"


def test_application_root_retargeted_during_the_walk_is_refused(
    bundle, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-7:走訪期間 root 被換成另一個 inode → (dev,ino) 再驗必須 typed 失敗。"""
    guard_path = tmp_path / "guard.json"
    _write_topology_guard(guard_path)
    root = _mutable_copy(bundle, tmp_path)
    decoy = tmp_path / "decoy"
    shutil.copytree(bundle["root"], decoy)
    real_verify = app_identity.verify_application_root

    def _verify_then_retarget(*args, **kwargs):
        document = real_verify(*args, **kwargs)
        # 走訪已完成、身分再驗之前:同名路徑換成另一個 inode(rename 交換)
        shutil.rmtree(root)
        os.rename(decoy, root)
        return document

    monkeypatch.setattr(app_identity, "verify_application_root", _verify_then_retarget)
    with pytest.raises(app_identity.AlrApplicationIdentityError) as error:
        app_identity.run_production_preflight(
            **_preflight_kwargs(bundle, guard_path, application_root=root)
        )
    assert str(error.value) == "application_root_identity_changed"


def test_verified_real_root_is_what_runtime_receives(bundle, tmp_path: Path) -> None:
    """P1-7:run_kwargs 交給 runtime 的是**已驗身分**的實體路徑(中間段別名已解析)。"""
    guard_path = tmp_path / "guard.json"
    _write_topology_guard(guard_path)
    result = app_identity.run_production_preflight(**_preflight_kwargs(bundle, guard_path))
    assert result["run_kwargs"]["repo_root"] == Path(os.path.realpath(bundle["root"]))
    assert result["application_root_realpath"] == str(Path(os.path.realpath(bundle["root"])))
    identity = os.stat(bundle["root"])
    assert result["application_root_identity"] == f"{identity.st_dev}:{identity.st_ino}"


# --------------------------------------------------------------------------- #
# consumer main 佈線:production 模式 / exit 78 / run_kwargs 下傳 / DSN 身分
# --------------------------------------------------------------------------- #
def _main_args(*extra: str) -> list[str]:
    return [
        "--dsn-file", "/tmp/alr.dsn",
        "--lock-file", "/tmp/alr.lock",
        "--source-head", "a" * 40,
        *extra,
    ]


def _clear_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ALR_EXPECTED_COMPATIBILITY_RECEIPT_V2",
        "ALR_APPLICATION_BUNDLE_DIGEST",
        "ALR_LAUNCH_BUNDLE_DIGEST",
        "ALR_TOPOLOGY_GUARD_FILE",
        "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST_V2",
        "ALR_EXPECTED_COMPATIBILITY_RECEIPT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_ex_config_exit_code_is_sysexits_config() -> None:
    assert consumer.EX_CONFIG_EXIT_CODE == 78
    assert app_identity.EX_CONFIG_EXIT_CODE == 78


def test_main_production_missing_expectation_exits_78(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_production_env(monkeypatch)
    calls: list[bool] = []
    monkeypatch.setattr(consumer, "run_event_consumer", lambda **k: calls.append(True))
    code = consumer.main(_main_args("--application-root", str(tmp_path)))
    assert code == 78
    output = json.loads(capsys.readouterr().out)
    assert output["result"] is None
    assert output["production_identity"]["status"] == "FAIL_CLOSED"
    assert output["production_identity"]["code"].startswith("expectation_missing:")
    assert calls == []  # 絕不回退進 consumer


def test_main_production_threads_root_scoped_run_kwargs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_production_env(monkeypatch)
    seen: dict = {}

    def _stub_preflight(arguments) -> dict:
        return {
            "summary": {"status": "PASS", "application_bundle_digest": "sha256:" + "a" * 64},
            "source_value_guard": {
                "schema_version": "source_value_guard_v1",
                "status": "PASS",
                "learning_runtime_digest_v2": "sha256:" + "b" * 64,
            },
            "run_kwargs": {
                "repo_root": tmp_path,
                "pinned_repo_source_head": "a" * 40,
                "dsn_required_identity": dict(app_identity.PRODUCTION_DSN_IDENTITY),
                "expected_compatibility_receipt": tmp_path / "v1.json",
            },
        }

    def _stub_run(**kwargs):
        seen.update(kwargs)
        return {"drains": 0}

    monkeypatch.setattr(consumer, "run_production_preflight_from_args", _stub_preflight)
    monkeypatch.setattr(consumer, "run_event_consumer", _stub_run)
    code = consumer.main(_main_args("--application-root", str(tmp_path)))
    assert code == 0
    assert seen["repo_root"] == tmp_path
    assert seen["pinned_repo_source_head"] == "a" * 40
    assert seen["dsn_required_identity"]["user"] == "aiml_engine_scanner"
    assert seen["expected_compatibility_receipt"] == tmp_path / "v1.json"
    output = json.loads(capsys.readouterr().out)
    assert output["production_identity"]["status"] == "PASS"
    assert output["source_value_guard"]["status"] == "PASS"


def test_main_production_permanent_pre_db_error_exits_78(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_production_env(monkeypatch)
    monkeypatch.setattr(
        consumer,
        "run_production_preflight_from_args",
        lambda arguments: {
            "summary": {"status": "PASS"},
            "source_value_guard": {
                "schema_version": "source_value_guard_v1",
                "status": "PASS",
                "learning_runtime_digest_v2": "sha256:" + "b" * 64,
            },
            "run_kwargs": {},
        },
    )

    def _raise_dsn(**kwargs):
        raise consumer.AlrEventConsumerError("dsn_not_local_trading_ai")

    monkeypatch.setattr(consumer, "run_event_consumer", _raise_dsn)
    code = consumer.main(_main_args("--application-root", str(tmp_path)))
    assert code == 78
    output = json.loads(capsys.readouterr().out)
    assert output["production_identity"]["code"] == "dsn_not_local_trading_ai"

    # transient 類(lock busy)不吃 78:照舊向上拋(start-limit 保護真 crash loop)。
    def _raise_lock(**kwargs):
        raise consumer.AlrEventConsumerError("single_instance_lock_busy")

    monkeypatch.setattr(consumer, "run_event_consumer", _raise_lock)
    with pytest.raises(consumer.AlrEventConsumerError, match="lock_busy"):
        consumer.main(_main_args("--application-root", str(tmp_path)))


def test_dev_path_unchanged_without_application_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 非 production:無 preflight、production_identity=None、exit 0(舊行為)。
    monkeypatch.setattr(consumer, "run_event_consumer", lambda **k: {"drains": 0})
    assert consumer.main(_main_args()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["production_identity"] is None


def test_production_dsn_identity_replaces_alr_shadow(bundle) -> None:
    shadow_dsn = "host=127.0.0.1 port=5432 dbname=trading_ai user=alr_shadow"
    scanner_dsn = (
        "host=127.0.0.1 port=5432 dbname=trading_ai user=aiml_engine_scanner"
    )
    # dev 預設:仍是 legacy alr_shadow。
    consumer._validate_local_dsn(shadow_dsn)
    with pytest.raises(consumer.AlrEventConsumerError):
        consumer._validate_local_dsn(scanner_dsn)
    # production 身分表:aiml_engine_scanner;alr_shadow 被拒(§8.3 identity 修正)。
    consumer._validate_local_dsn(
        scanner_dsn, app_identity.PRODUCTION_DSN_IDENTITY
    )
    with pytest.raises(consumer.AlrEventConsumerError):
        consumer._validate_local_dsn(
            shadow_dsn, app_identity.PRODUCTION_DSN_IDENTITY
        )
