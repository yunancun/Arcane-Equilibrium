"""S2E.2a:S2.0 受信主機 runner 的**拋棄式 rehearsal**(T1)+ production 拒絕矩陣(T0)。

T0(恆跑,含 Mac):production/unknown 全路徑 typed 拒且 **driver 未被構造**(以
``ObserverBootstrapHostDriver.constructions`` 計數器斷言);``--allow-production`` 單獨不足;
rehearsal 恆拒在 production target class 上執行;rehearsal driver 永不宣稱 PLATFORM_ATTESTED。

T1(需 ``initdb``/``pg_ctl``/``psycopg2``,缺任一則**整個模組誠實 SKIP**):對一個真的
``initdb`` 拋棄式叢集,以 runner 的 ``ObserverBootstrapHostDriver`` 走 **S2.0 adapter 的 production
gate**(§6 step 2→9),證明三段:

  apply(真 CREATE ROLE + GRANT)→ 獨立 verifier 的 postcheck **FAIL** → 補償
  → catalog digest **逐位元組**回前態、observer 角色真的消失。

另證:evidence_class 第一道 filter(LOCAL_REPRODUCIBLE 一律補償後 PENDING)、
``signed_apply_attestation`` 永遠 raise(絕不偽造 platform 背書)、補償失敗 → RECOVERY_REQUIRED、
以及 receipt 的 ``production_apply_performed`` 恆 false。

**誠實界線**:所有 rehearsal 頂點都是 ``EXTERNAL_VERIFICATION_PENDING`` / ``RECOVERY_REQUIRED``
——那是**預期**行為。rehearsal 綠不是 closure PASS,也不是 EFFECT 進展;九 authority 恆 false,
runtime 恆 inactive,生產 PG 從未被接觸。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_pg_observer_bootstrap as obs  # noqa: E402
import agent_governance_pg_observer_bootstrap_attestation as obs_att  # noqa: E402
import agent_governance_s2_0_host_runner as runner  # noqa: E402
import agent_governance_s2_host_kernel as kernel  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")

DB = "postgres"
SCHEMA = "learning"
TABLE = "alr_consumer_events"
OBSERVER = "aiml_s2e2_observer"
WRITER = "aiml_s2e2_writer"
ASSUME = "aiml_s2e2_assume"
ASSUME_PW = "aiml-s2e2-assume-cred-v0"
WRONG_PW = "aiml-s2e2-assume-cred-WRONG"

HEAD = "0123456789abcdef0123456789abcdef01234567"
CREATED = "2026-07-28T12:00:00+00:00"
NOW = "2026-07-28T12:01:00+00:00"
CAP = "sha256:" + "e" * 64

CLEAN_SUBPROCESS_ENV = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}


# --------------------------------------------------------------------------- #
# T0 — production refusal matrix (always runs, including on Mac)
# --------------------------------------------------------------------------- #
def _intent(target_class="production", sock="/var/run/postgresql"):
    return obs.build_pg_observer_bootstrap_intent(
        target_class=target_class, target_host="trade-core", database=DB,
        observer_role=OBSERVER, observed_schema=SCHEMA, observed_relations=[TABLE],
        socket_dir=sock, auth_mapping="pg_hba_ident_local",
        applier_node_id="s2_0_apply_actor", postcheck_node_id="s2_0_ops_postcheck",
        created_at=CREATED, ttl_seconds=900, source_head=HEAD,
    )


def _exploding_factory():
    def _factory():  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("the driver factory must never be reached when admission refuses")

    return _factory


PRODUCTION_VIEWS = [
    {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x", "facts": {}},
    {"target_class": kernel.TARGET_CLASS_UNKNOWN, "reason": "x", "facts": {}},
]


@pytest.mark.parametrize("view", PRODUCTION_VIEWS)
@pytest.mark.parametrize("kwargs", [
    {},
    {"allow_production": True},
    {"allow_production": True, "operator_authorization_verified": True},
    {"allow_production": True, "production_confirm": "sha256:" + "9" * 64},
    {"operator_authorization_verified": True, "production_confirm": "match"},
])
def test_production_refusal_never_constructs_a_driver(view, kwargs):
    intent = _intent()
    if kwargs.get("production_confirm") == "match":
        kwargs["production_confirm"] = intent["self_digest"]
    before = runner.ObserverBootstrapHostDriver.constructions
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.run_observer_bootstrap_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            driver_factory=_exploding_factory(), target_view=view, **kwargs,
        )
    assert runner.ObserverBootstrapHostDriver.constructions == before


@pytest.mark.parametrize("view", PRODUCTION_VIEWS)
def test_all_three_conditions_reach_the_driver_factory(view):
    intent = _intent()
    reached = {"count": 0}

    class _Placeholder:
        """一個沒有任何寫能力面的佔位 driver(adapter 因缺 SSHSIG 根本不會呼叫它)。"""

        evidence_class = runner.LOCAL_REPRODUCIBLE_EVIDENCE_CLASS
        calls: list = []

    def _factory():
        reached["count"] += 1
        return _Placeholder()

    # driver 被構造了,但 adapter 的 L2 閘(缺 operator SSHSIG)仍讓它停在 PENDING —— L1 只決定
    # 「今天要不要碰這台主機」,證據完整性仍由 L2 把關。
    result = runner.run_observer_bootstrap_on_host(
        intent, None, None, now=NOW, source_head=HEAD, driver_factory=_factory,
        target_view=view, allow_production=True, production_confirm=intent["self_digest"],
        operator_authorization_verified=True,
    )
    assert reached["count"] == 1
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["production_apply_performed"] is False
    assert result["closure_pass_blocked"] is True


def test_non_target_host_is_refused_outright():
    intent = _intent()
    before = runner.ObserverBootstrapHostDriver.constructions
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.run_observer_bootstrap_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            driver_factory=_exploding_factory(),
            target_view={"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"},
            allow_production=True, production_confirm=intent["self_digest"],
            operator_authorization_verified=True,
        )
    assert runner.ObserverBootstrapHostDriver.constructions == before


def test_this_machine_refuses_the_production_lane_with_no_target_view_supplied():
    intent = _intent()
    if sys.platform == "linux":  # pragma: no cover - 開發機為 Mac
        pytest.skip("only asserts the non-target refusal on a non-target host")
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.run_observer_bootstrap_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            driver_factory=_exploding_factory(), allow_production=True,
            production_confirm=intent["self_digest"], operator_authorization_verified=True,
        )


def test_rehearsal_refuses_on_a_production_target_class():
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=lambda: None, verifier_connect=lambda: None,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.rehearse_observer_bootstrap(
            _intent(), None, None, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=lambda: "sha256:" + "0" * 64, role_probe=lambda: False,
            target_view={"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x"},
        )


def test_rehearsal_driver_may_never_claim_platform_attested():
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=lambda: None, verifier_connect=lambda: None,
        evidence_class=obs.PRODUCTION_APPLIED_EVIDENCE_CLASS,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.rehearse_observer_bootstrap(
            _intent(), None, None, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=lambda: "sha256:" + "0" * 64, role_probe=lambda: False,
            target_view={"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"},
        )


def test_signed_apply_attestation_always_raises():
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=lambda: None, verifier_connect=lambda: None,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        driver.signed_apply_attestation(
            intent={}, applied_grant_set_digest="sha256:" + "0" * 64,
            reobserved_digest="sha256:" + "0" * 64,
        )


def test_independent_proof_refuses_to_fabricate_without_the_capability():
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=lambda: None, verifier_connect=lambda: None,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        driver.independent_read_only_proof(grant_set={
            "role": OBSERVER, "schema": SCHEMA, "relations": [TABLE],
        })


def test_ops_postcheck_uses_the_s2e1_builder_and_records_its_typed_refusal():
    # §H R4:runner 不得產出自己的 receipt schema。S2E.1 的建構子對 S2.0 typed 拒絕,
    # runner 忠實記錄該理由而非另造一份。
    receipt = obs.apply_observer_bootstrap(
        _intent(), None, None, now=NOW, source_head=HEAD,
    )
    projection = runner._ops_postcheck_projection(
        receipt, verifier_node="s2_0_ops_postcheck", observed_at=NOW
    )
    assert projection["evidence"] is None
    assert "not representable today" in projection["refusal"]


# --------------------------------------------------------------------------- #
# T1 — real disposable cluster rehearsal
# --------------------------------------------------------------------------- #
psycopg2 = pytest.importorskip(
    "psycopg2", reason="psycopg2 driver is required for the S2.0 host runner rehearsal"
)

disposable = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; the S2.0 host runner rehearsal cannot run",
)


def _run(cmd, *, logfile, timeout):
    result = subprocess.run(
        cmd, env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=timeout,
    )
    if result.returncode != 0:
        detail = ""
        try:
            detail = Path(logfile).read_text(encoding="utf-8")[-800:]
        except OSError:
            pass
        raise RuntimeError(f"command failed rc={result.returncode}: {cmd[0]}\n{detail}")


@pytest.fixture(scope="module")
def cluster():
    if not (INITDB and PG_CTL):
        pytest.skip("initdb/pg_ctl are absent")
    tmp = tempfile.mkdtemp(prefix="aiml_s2e2_s20_")
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    started = False
    try:
        _run([INITDB, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
             logfile=logfile, timeout=90)
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
            handle.write("password_encryption = 'scram-sha-256'\n")
            handle.write("lc_messages = 'C'\n")
            handle.write("log_statement = 'none'\n")
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   postgres   trust\n")
            handle.write("local   all   all        scram-sha-256\n")
        _run([PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
             logfile=logfile, timeout=60)
        started = True
        _bootstrap(sock_dir)
        yield {"socket_dir": sock_dir}
    finally:
        if started or os.path.exists(os.path.join(data_dir, "postmaster.pid")):
            try:
                subprocess.run([PG_CTL, "-D", data_dir, "-m", "immediate", "stop"],
                               env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _admin(sock):
    connection = psycopg2.connect(host=sock, dbname=DB, user="postgres", connect_timeout=10)
    connection.autocommit = True
    return connection


def _bootstrap(sock):
    connection = _admin(sock)
    try:
        cursor = connection.cursor()
        cursor.execute(f"CREATE SCHEMA {SCHEMA}")
        cursor.execute(f"CREATE TABLE {SCHEMA}.{TABLE}(event_id integer PRIMARY KEY, note text)")
        cursor.execute(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (1, 'seed')")
        cursor.execute(f"CREATE ROLE {WRITER} NOLOGIN")
        cursor.execute(f"CREATE ROLE {ASSUME} LOGIN NOSUPERUSER PASSWORD %s", (ASSUME_PW,))
        cursor.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ASSUME}")
    finally:
        connection.close()


def _install_operator_profile(tmp_path, monkeypatch):
    private_key = tmp_path / "operator"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True)
    public_key = " ".join(private_key.with_suffix(".pub").read_text(encoding="ascii").split()[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(obs_att, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(obs_att, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


_SIGN_SEQ = [0]


def _sign(private_key, intent, source_head):
    authorization = obs.build_operator_authorization(intent=intent, source_head=source_head)
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"s2e2-observer-permit-{_SIGN_SEQ[0]}.json"
    message.write_bytes(obs.canonical_bytes(authorization))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n",
         obs.OPERATOR_SIGNATURE_NAMESPACE, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return authorization, message.with_suffix(".json.sig").read_bytes()


def _catalog_probe(sock):
    def _probe():
        connection = _admin(sock)
        try:
            return obs.observer_role_acl_state_digest(
                connection.cursor(), role=OBSERVER, schema=SCHEMA, relations=[TABLE]
            )
        finally:
            connection.close()

    return _probe


def _role_probe(sock):
    def _probe():
        connection = _admin(sock)
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (OBSERVER,))
            return cursor.fetchone() is not None
        finally:
            connection.close()

    return _probe


def _driver(sock, **overrides):
    applier = _admin(sock)
    verifier = _admin(sock)
    opened = [applier, verifier]

    def _observer_session():
        session = psycopg2.connect(
            host=sock, dbname=DB, user=ASSUME, password=ASSUME_PW, connect_timeout=10
        )
        session.autocommit = True
        return session

    def _wrong_credential():
        return psycopg2.connect(
            host=sock, dbname=DB, user=ASSUME, password=WRONG_PW, connect_timeout=10
        )

    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=lambda: applier,
        verifier_connect=lambda: verifier,
        observer_session_connect=_observer_session,
        credential_escalation_connect=_wrong_credential,
        set_role_target=WRITER,
        observer_session_role=ASSUME,
        verifier_capture_digest=CAP,
        **overrides,
    )
    return driver, opened


@disposable
def test_rehearsal_apply_then_failing_postcheck_then_compensation_restores_exactly(
    cluster, tmp_path, monkeypatch
):
    """三段:apply → 獨立 postcheck FAIL(T2)→ 補償 → catalog digest 逐位元組回前態。"""

    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)

    def _disagree(proof):
        # 獨立 verifier 不同意 applier 的觀測(T2 gate 的真實失敗形)。
        return {**proof, "reobserved_digest": "sha256:" + "1" * 64}

    driver, opened = _driver(sock, proof_fault=_disagree)
    try:
        result = runner.rehearse_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=_catalog_probe(sock), role_probe=_role_probe(sock),
        )
    finally:
        for connection in opened:
            connection.close()

    assert result["rehearsal"] is True
    assert result["lane"] == "disposable_rehearsal"
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "reobserved digest != applied (T2)" in result["receipt"]["failure_reason"]
    # 真的走完 apply → proof → compensate 三段(不是在前檢就退場)。
    assert driver.calls.count("create_read_only_observer") == 1
    assert driver.calls.count("independent_read_only_proof") == 1
    assert driver.calls.count("compensate") == 1
    # 逐位元組還原 + observer 角色真的消失。
    assert result["catalog_restored_exact"] is True
    assert result["pre_state_digest"] == result["post_state_digest"]
    assert result["observer_present_after"] is False
    # 誠實邊界:absolutely never a closure PASS / EFFECT 進展。
    assert result["production_apply_performed"] is False
    assert result["closure_pass_blocked"] is True
    assert result["ops_postcheck_evidence"] is None
    assert "not representable today" in result["ops_postcheck_refusal"]
    assert result["receipt"]["boundary"]["nine_authorities_false"] is True


@disposable
def test_rehearsal_real_denial_proofs_then_evidence_class_filter_compensates(
    cluster, tmp_path, monkeypatch
):
    """不注入任何 fault:真 42501 / 28P01 被觀測到,但 evidence_class 第一道 filter 仍補償。"""

    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)
    observed: dict = {}

    def _record(proof):
        observed.update(proof["read_only_proof"])
        return proof

    driver, opened = _driver(sock, proof_fault=_record)
    try:
        result = runner.rehearse_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=_catalog_probe(sock), role_probe=_role_probe(sock),
        )
    finally:
        for connection in opened:
            connection.close()

    # 真 SQLSTATE(nothing mocked):真 postgres 行程發出的拒絕碼。
    assert observed["write_denied"]["observed_sqlstate"] == "42501"
    assert observed["set_role_denied"]["observed_sqlstate"] == "42501"
    assert observed["credential_escalation_denied"]["observed_sqlstate"] in (
        obs.CREDENTIAL_DENIAL_SQLSTATES
    )
    assert observed["search_path_reset_harmless"]["harmless"] is True
    # T2 通過(verifier 的 reobserved == applied),但 evidence_class 不是 PLATFORM_ATTESTED。
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "not PLATFORM_ATTESTED" in result["receipt"]["failure_reason"]
    assert "signed_apply_attestation" not in driver.calls   # 連 attestation 都沒被請求
    assert result["catalog_restored_exact"] is True
    assert result["observer_present_after"] is False
    assert result["production_apply_performed"] is False


@disposable
def test_rehearsal_unconfirmed_compensation_is_recovery_required(cluster, tmp_path, monkeypatch):
    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)

    def _explode():
        raise RuntimeError("injected compensation failure")

    driver, opened = _driver(sock, compensate_fault=_explode)
    try:
        result = runner.rehearse_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=_catalog_probe(sock), role_probe=_role_probe(sock),
        )
        assert result["status"] == "RECOVERY_REQUIRED"
        # 誠實回報:角色其實還在(絕不冒充「已補償」)。
        assert result["observer_present_after"] is True
        assert result["catalog_restored_exact"] is False
    finally:
        cleanup = _admin(sock)
        try:
            cleanup.cursor().execute(
                f"REVOKE ALL ON {SCHEMA}.{TABLE} FROM {OBSERVER}"
            )
            cleanup.cursor().execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM {OBSERVER}")
            cleanup.cursor().execute(f'DROP ROLE IF EXISTS "{OBSERVER}"')
        finally:
            cleanup.close()
        for connection in opened:
            connection.close()


@disposable
def test_rehearsal_without_an_operator_signature_never_touches_the_cluster(cluster):
    sock = cluster["socket_dir"]
    intent = _intent(sock=sock)
    driver, opened = _driver(sock)
    try:
        result = runner.rehearse_observer_bootstrap(
            intent, None, None, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=_catalog_probe(sock), role_probe=_role_probe(sock),
        )
    finally:
        for connection in opened:
            connection.close()
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "AUTHORIZATION_REJECTED" in result["receipt"]["failure_reason"]
    assert driver.calls == []               # driver 一次都沒被呼叫
    assert result["observer_present_after"] is False
    assert result["catalog_restored_exact"] is True
