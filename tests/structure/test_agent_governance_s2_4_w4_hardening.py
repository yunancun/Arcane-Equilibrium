"""S2.4(WP4·W4)五腿對抗審查(E2/E3/E4/CC/OPS @ 677a12df9)findings 的 focused 迴歸。

每一條測試都對應一個被實證過的缺陷,且都會在 677a12df9 上**失敗**:

- **A2** install lock 的證明曾是**未認證的 caller 字典**:``{"status": "INSTALL_LOCK_ACQUIRED"}``
  就能拿到 ``AUTHORIZATION_CONSUMPTION_APPENDED``(ledger 真的被改寫)與
  ``STARTUP_RECONCILE_CLEAN``;``release`` 又從不動 verdict,故一份已釋放的證明永遠有效;
- **A3** ``derive_replay_consumption_decision`` 的 genesis 分支把 ``now=None`` 原樣轉發,
  而下游在 ``now is None`` 時**整段跳過**新鮮窗——系統一生中燒掉的第一張 permit 因此 fail-open;
- **A4/A5** 啟動 reconcile 的 lane 是 plan-scoped 且靠 caller 指名,於是**上一個 plan** 留下
  的半途交易看不見,沒被指名的 probe/prepare lane 也看不見;
- **A8** probe / PREPARE 進入點從不 reconcile,且 recovery 閂是 in-process 的;
- **A10** lane 路徑接受任意絕對字串(``/etc/shadow`` 亦然),與 docstring 的宣稱不符;
- **A12** 非 ACQUIRED 的每一條出路都洩漏 lock fd;
- **A13** 封好的 ledger 記的是被讀回物件自報的位置,而不是它真的被寫進去的那個。

另有兩條**接手項**(H1 / H2),它們建在上述修復所引入、**尚未提交**的 diff 之上,故 677a12df9
對它們不是有意義的 baseline:那個 commit 上既沒有 ``entry_source`` / ``component_effect_class``
這兩個判別欄,也沒有 ``INSTALL_LOCK_REQUIRED`` 這條 typed 出路。它們的「修改前失敗」是對
**本輪修改前的工作樹**成立(以 scratchpad 的丟棄式副本逐項回退驗證):

- **H1** 啟動 reconcile 的 lock 閘曾排在 ``driver is None`` 之後,於是 ``driver=None ∧ 無 lock``
  回報 ``EXTERNAL_VERIFICATION_PENDING``,而 §5.2 的准入前提(持有互斥 install lock)根本沒滿足;
- **H2** ``_Journal``(五 row 唯一的 entry producer)只寫得出 ``entry_source``,寫不出
  ``component_effect_class``,因此兩欄只能在三本 journal 的 schema 裡留成 optional——一個選配的
  digest 空間判別等於沒有判別。

時間全部錨在凍結常量上(無 wall clock,故無日期腐化)。所有 driver 皆為 in-memory fake,
``evidence_class`` 恆 ``STRUCTURAL_ONLY``——它們只證契約層行為,絕不認證任何 runtime。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_install_driver as runner_module  # noqa: E402
import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_lock as lock  # noqa: E402
import agent_governance_s2_4_reconcile as reconcile_leaf  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
import s2_4_w4b_testkit as w4b  # noqa: E402
from test_agent_governance_s2_4_journal import FakeDurableFs  # noqa: E402
from test_agent_governance_s2_4_lock import FakeLockDriver  # noqa: E402

_FORGED_LOCK = {"status": "INSTALL_LOCK_ACQUIRED"}
_OTHER_PLAN_ID = journal.PLAN_ID_PREFIX + "c" * 64
_STRANDED_PROBE_ID = journal.PROBE_ID_PREFIX + "d" * 64


@pytest.fixture()
def fx(tmp_path, monkeypatch):
    return w4b.Fixture(tmp_path, monkeypatch)


def _held() -> dict:
    """一份**真的**取得過的 lock verdict(token 由 acquire 產生,不可偽造)。"""

    return lock.acquire_s2_4_install_lock(FakeLockDriver())


def _install_paths(plan_id: str) -> dict[str, str]:
    return {"install": journal.install_journal_path(plan_id)}


def _stranded_install_journal(plan_id: str) -> bytes:
    built = journal.build_install_journal(
        plan_id=plan_id, plan_core_digest="sha256:" + "1" * 64, idempotency_key=plan_id,
        expected_pre_state_digest="sha256:" + "2" * 64,
        aggregate_rollback_digest="sha256:" + "3" * 64,
        entries=[{
            "seq": 0, "step_index": 0, "state": "APPLYING",
            "pre_state_digest": "sha256:" + "2" * 64,
            "post_state_digest": "sha256:" + "4" * 64,
            "fsynced": True, "recorded_at": kit.ISSUED,
            "entry_source": "aggregate_transaction",
            "component_effect_class": "HOST_IDENTITY_INSTALL",
        }],
        terminal=False,
    )
    return validator._canonical_bytes(built)


def _stranded_probe_journal(probe_id: str) -> bytes:
    built = journal.build_probe_journal(
        probe_id=probe_id,
        derived_unit_name=f"arcane-aiml-s2-4-probe-{probe_id[len(journal.PROBE_ID_PREFIX):]}"
                          ".service",
        scope="PREPARE_SANDBOX", transient_unit_property_digest="sha256:" + "1" * 64,
        expected_invocation_id_pattern="^[0-9a-f]{32}$",
        cleanup_rollback_digest="sha256:" + "2" * 64,
        entries=[{
            "seq": 0, "state": "APPLYING", "pre_state_digest": "sha256:" + "3" * 64,
            "post_state_digest": "sha256:" + "4" * 64, "fsynced": True,
            "recorded_at": kit.ISSUED,
            "entry_source": "capability_probe",
            "component_effect_class": "HOST_CAPABILITY_PROBE",
        }],
        terminal=False,
    )
    return validator._canonical_bytes(built)


# ══════════════════════ A2 —— lock 證明不再是 caller 字典 ═══════════════════════
def test_a2_a_forged_lock_verdict_can_no_longer_append_a_consumption(fx) -> None:
    """677a12df9:``{"status": "INSTALL_LOCK_ACQUIRED"}`` 直達
    ``AUTHORIZATION_CONSUMPTION_APPENDED`` 且 ledger 真的被改寫在磁碟上。"""

    before = bytes(fx.fs.files[w4b.LEDGER_BASENAME])
    bindings = {
        "apply_aggregate": w4b.runner.aggregate_permit_payload_binding(
            fx.plan, installed_unit_probe_receipt=fx.probe_receipts["INSTALLED_UNIT"],
            issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
        ),
        "pg_migration": w4b.runner.pg_permit_payload_binding(
            fx.plan, component_intents=fx.component_intents,
            installed_unit_probe_receipt=fx.probe_receipts["INSTALLED_UNIT"],
            issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
        ),
    }
    outcome = lock.consume_authorizations_under_lock(
        fx.fs, authorizations=fx.authorization_set, expected_payload_bindings=bindings,
        lock_verdict=dict(_FORGED_LOCK), now=kit.NOW,
    )
    assert outcome["status"] == "INSTALL_LOCK_REQUIRED"
    assert outcome["mutation_performed"] is False
    assert outcome["appended_authorization_ids"] == []
    assert any("carries no install-lock token" in reason for reason in outcome["reasons"])
    assert fx.fs.files[w4b.LEDGER_BASENAME] == before


def test_a2_a_forged_lock_verdict_can_no_longer_declare_the_journals_clean(fx) -> None:
    """677a12df9:同一個偽造字典拿到 ``STARTUP_RECONCILE_CLEAN`` 且 ``admits_new_work=True``。"""

    outcome = reconcile_leaf.reconcile_startup_journals(
        fx.fs, journal_paths=_install_paths(fx.plan["plan_id"]),
        lock_verdict=dict(_FORGED_LOCK),
    )
    assert outcome["status"] == "INSTALL_LOCK_REQUIRED"
    assert outcome["admits_new_work"] is False
    assert outcome["mutation_performed"] is False


def test_a2_a_released_lock_proof_never_re_authorizes_anything(fx) -> None:
    """677a12df9:``release_s2_4_install_lock`` 只關 fd、從不動 verdict,故一份已釋放的
    證明永遠通得過每一道閘。"""

    driver = FakeLockDriver()
    held = lock.acquire_s2_4_install_lock(driver)
    assert reconcile_leaf.reconcile_startup_journals(
        fx.fs, journal_paths=_install_paths(fx.plan["plan_id"]), lock_verdict=held,
    )["status"] != "INSTALL_LOCK_REQUIRED"
    released = lock.release_s2_4_install_lock(driver, held)
    assert released["status"] == "INSTALL_LOCK_RELEASED"
    assert released["lock_unlinked"] is False
    # verdict 自身現在記著「已釋放」,而且 token 已從 live 集合移出。
    assert held["status"] == "INSTALL_LOCK_RELEASED"
    assert lock.install_lock_is_held(held) is False
    blocked = reconcile_leaf.reconcile_startup_journals(
        fx.fs, journal_paths=_install_paths(fx.plan["plan_id"]), lock_verdict=held,
    )
    assert blocked["status"] == "INSTALL_LOCK_REQUIRED"
    assert blocked["admits_new_work"] is False
    # 二次 release 不再宣稱成功。
    assert lock.release_s2_4_install_lock(driver, held)["status"] == "NOT_HELD"


def test_a2_the_journal_routed_driver_refuses_a_forged_lock_proof() -> None:
    fs = FakeDurableFs()
    plan_id = journal.PLAN_ID_PREFIX + "a" * 64
    routed = reconcile_leaf.JournalRoutedDriver(
        object(),
        store=journal.JournalStore(fs, journal_path=journal.install_journal_path(plan_id)),
        build_journal=lambda entries, terminal: journal.build_install_journal(
            plan_id=plan_id, plan_core_digest="sha256:" + "1" * 64, idempotency_key=plan_id,
            expected_pre_state_digest="sha256:" + "2" * 64,
            aggregate_rollback_digest="sha256:" + "3" * 64, entries=entries,
            terminal=terminal,
        ),
        lock_verdict=dict(_FORGED_LOCK), clock=kit.frozen_clock(), step_index=0,
    )
    with pytest.raises(reconcile_leaf.InstallDriverContractError) as excinfo:
        routed.journal_transition(entry={
            "state": "APPLYING", "pre_state_digest": "sha256:" + "2" * 64,
            "post_state_digest": "sha256:" + "4" * 64,
        })
    assert excinfo.value.code == "journal_transition_requires_the_install_lock"
    assert fs.files == {}


# ══════════════ A3 —— genesis 消費分支不得跳過 permit 新鮮窗 ═══════════════════
def test_a3_the_genesis_consumption_branch_applies_the_freshness_window(
    tmp_path, monkeypatch
) -> None:
    """677a12df9:空 ledger + ``now=None`` → 一張 2030 年才生效的 permit 被判
    ``CONSUME_ADMITTED``(``_s2_4_operator_authorization_errors`` 在 ``now is None``
    時整段跳過新鮮度)。姊妹函式 ``derive_authorization_replay_binding`` 早就預設牆鐘。"""

    private_key, public_key, fingerprint = kit.mint_key(tmp_path, name="a3-operator")
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    binding = kit.filler_payload_binding("prepare")
    # 凍結的 fixture 窗就在 2030 年——對 2026 年的牆鐘而言,它「還沒生效」。
    future = kit.authorization(
        private_key, profile_key="prepare", payload_binding=binding,
    )
    empty = lock.empty_replay_ledger()
    assert empty["entries"] == []
    admitted = lock.derive_replay_consumption_decision(
        future, empty, expected_payload_binding=binding, profile_key="prepare",
        now=kit.NOW,
    )
    assert admitted["status"] == "CONSUME_ADMITTED", admitted["reasons"]
    implicit = lock.derive_replay_consumption_decision(
        future, empty, expected_payload_binding=binding, profile_key="prepare", now=None,
    )
    assert implicit["status"] == "AUTHORIZATION_REJECTED", implicit["reasons"]
    assert implicit["status"] != "CONSUME_ADMITTED"
    # 非空 ledger 的分支本來就會拒(它走 derive_authorization_replay_binding,那支
    # 早就預設牆鐘);修好之後兩條分支的結論一致。
    seeded = kit.replay_ledger()
    assert lock.derive_replay_consumption_decision(
        future, seeded, expected_payload_binding=binding, profile_key="prepare", now=None,
    )["status"] == "AUTHORIZATION_REJECTED"


def test_a3_a_permit_whose_window_contains_the_wall_clock_is_still_admitted(
    tmp_path, monkeypatch
) -> None:
    """A3 的修法是**對齊姊妹函式的預設**,不是把閘關死:窗涵蓋當下牆鐘的 permit 仍可
    在空 ledger 上被消費。"""

    private_key, public_key, fingerprint = kit.mint_key(tmp_path, name="a3-live-operator")
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    issued = (now - timedelta(minutes=1)).isoformat()
    expires = (now + timedelta(minutes=9)).isoformat()
    binding = kit.filler_payload_binding("prepare", issued_at=issued, expires_at=expires)
    profile = validator.S2_4_AUTHORIZATION_PROFILES["prepare"]
    artifact = {
        "schema_version": "s2_4_operator_authorization_v1",
        "profile_identity": profile["profile_identity"],
        "signature_namespace": profile["signature_namespace"],
        "authorization_id": "",
        "payload_fields": list(profile["payload_fields"]),
        "payload_binding": dict(binding),
        "issued_at": issued,
        "expires_at": expires,
        "sshsig_armored": "-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----\n",
        "self_digest": "sha256:" + "0" * 64,
    }
    artifact["authorization_id"] = validator.derive_authorization_id(artifact)
    live = kit.sign(private_key, artifact, namespace=profile["signature_namespace"])
    assert lock.derive_replay_consumption_decision(
        live, lock.empty_replay_ledger(), expected_payload_binding=binding,
        profile_key="prepare", now=None,
    )["status"] == "CONSUME_ADMITTED"


# ═════ A4/A5 —— 「任何」非終端 journal(不只被指名的、不只本 plan 的) ═════════
def test_a4_a_previous_plans_stranded_transaction_blocks_a_newly_signed_plan(fx) -> None:
    """677a12df9:plan A 崩在半途留下 10 筆 ``terminal=False`` 的 journal;operator 簽了
    plan B(只差一個欄位)→ ``STARTUP_RECONCILE_CLEAN`` / ``admits_new_work=True`` /
    ``SOURCE_SIMULATION_PASS`` / ``mutation_performed=True``。"""

    other_basename = journal.install_journal_path(_OTHER_PLAN_ID).rsplit("/", 1)[-1]
    fx.fs.files[other_basename] = _stranded_install_journal(_OTHER_PLAN_ID)
    verdict = fx.apply()
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict["reasons"]
    assert verdict["reconcile"]["admits_new_work"] is False
    assert verdict["mutation_performed"] is False
    lane_key = f"install:{_OTHER_PLAN_ID}"
    assert verdict["reconcile"]["lanes"][lane_key]["status"] == "RECOVERY_REQUIRED"
    # 本 plan 自己的 lane 仍然乾淨——被擋住的是**別的** plan 的殘留。
    assert verdict["reconcile"]["lanes"]["install"]["status"] == "STARTUP_RECONCILE_CLEAN"
    assert all(row.calls == [] for row in fx.row_drivers.values())
    # 那本 journal 既未被改名也未被覆寫(§5.2)。
    assert fx.fs.files[other_basename] == _stranded_install_journal(_OTHER_PLAN_ID)


def test_a5_an_unnamed_probe_lane_can_no_longer_be_clean_by_omission(fx) -> None:
    """677a12df9:磁碟上有一本非終端的 probe journal,但 caller 沒指名 probe lane →
    ``admits_new_work=True``,APPLY 一路跑到終端成功 receipt。"""

    basename = journal.probe_journal_path(_STRANDED_PROBE_ID).rsplit("/", 1)[-1]
    fx.fs.files[basename] = _stranded_probe_journal(_STRANDED_PROBE_ID)
    verdict = fx.apply()  # 刻意**不**傳 startup_journal_paths
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict["reasons"]
    assert verdict["reconcile"]["admits_new_work"] is False
    assert verdict["reconcile"]["lanes"][f"probe:{_STRANDED_PROBE_ID}"]["status"] == (
        "RECOVERY_REQUIRED"
    )
    assert all(row.calls == [] for row in fx.row_drivers.values())


def test_a4_a_driver_without_an_enumeration_surface_is_fail_closed(fx) -> None:
    """「我沒辦法知道那個目錄裡還躺著什麼」不得被讀成「那個目錄是乾淨的」。"""

    class _NoEnumeration:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            if name == "list_journal_basenames":
                raise AttributeError(name)
            return getattr(self._inner, name)

    outcome = reconcile_leaf.reconcile_startup_journals(
        _NoEnumeration(fx.fs), journal_paths=_install_paths(fx.plan["plan_id"]),
        lock_verdict=_held(),
    )
    assert outcome["status"] == "RECOVERY_REQUIRED"
    assert outcome["admits_new_work"] is False
    assert any("cannot enumerate" in reason for reason in outcome["reasons"])


def test_a7_one_ownership_key_no_longer_opens_all_three_lanes(fx) -> None:
    """677a12df9:同一個 ``ownership_evidence`` 物件被餵給 install / prepare / probe 三條
    lane,於是一把鑰匙同時授權三條 lane 上的破壞性補償。"""

    lanes = reconcile_leaf._lane_ownership_evidence({
        "journal_subject": {
            "journal_digest": "sha256:" + "b" * 64,
            "s2_4_receipt_digest": "sha256:" + "a" * 64,
        }
    })
    assert set(lanes) == {"install"}
    per_lane = reconcile_leaf._lane_ownership_evidence({
        "install": {"journal_subject": {}}, "probe": {"journal_subject": {}},
    })
    assert set(per_lane) == {"install", "probe"}
    assert "prepare" not in per_lane


# ═══════════ A8 —— probe / PREPARE 進入點在接受新 intent 之前先 reconcile ══════
def test_a8_the_probe_entrypoint_reconciles_before_accepting_a_new_probe(
    tmp_path, monkeypatch
) -> None:
    """677a12df9:``grep -c reconcile`` 在 probe.py / prepare.py 皆為 0,而 recovery 閂是
    in-process 的——救不了「行程消失」這件事(§10.5 #39 要的正是跨崩潰的證明)。"""

    import test_agent_governance_s2_4_probe as probe_tests
    from test_agent_governance_s2_4_probe import _FakeProbeDriver, _core, _intent
    import agent_governance_s2_4_probe as probe

    private_key, public_key, fingerprint = probe_tests._mint_key(tmp_path, name="a8-operator")
    probe_tests._install_pinned_key(monkeypatch, public_key, fingerprint)
    intent = _intent()
    host = _FakeProbeDriver(property_digest=_core()["transient_unit_property_digest"])
    fs = FakeDurableFs()
    # 上一次 probe 崩在半途:磁碟上留著一本非終端的 probe journal(durable 閂)。
    stranded_basename = journal.probe_journal_path(_STRANDED_PROBE_ID).rsplit("/", 1)[-1]
    fs.files[stranded_basename] = _stranded_probe_journal(_STRANDED_PROBE_ID)
    routed = reconcile_leaf.JournalRoutedDriver(
        host,
        store=journal.JournalStore(
            fs, journal_path=journal.probe_journal_path(intent["probe_id"])
        ),
        build_journal=lambda entries, terminal: journal.build_probe_journal(
            probe_id=intent["probe_id"],
            derived_unit_name=probe.derived_probe_unit_name(intent["probe_id"]),
            scope="PREPARE_SANDBOX",
            transient_unit_property_digest=_core()["transient_unit_property_digest"],
            expected_invocation_id_pattern="^[0-9a-f]{32}$",
            cleanup_rollback_digest="sha256:" + "2" * 64,
            entries=entries, terminal=terminal,
        ),
        lock_verdict=_held(), clock=kit.frozen_clock(),
    )
    # 這一組輸入在 677a12df9 上是**完全合法**的正例(它在那裡跑到終端成功 receipt);
    # 唯一的差別是:磁碟上還躺著一本未解的 probe journal。
    verdict = probe_tests._run(intent, probe_tests._authorization(private_key), routed)
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict["status"]
    # 零主機接觸:transient unit 從未被建立。
    assert host.calls == []
    assert verdict["mutation_performed"] is False
    assert any("no new probe may start" in reason for reason in verdict["reasons"])


def test_a8_a_driver_without_a_durable_journal_surface_is_recorded_not_assumed_clean(
) -> None:
    """沒有 durable journal 面的 driver:回 typed ``STARTUP_RECONCILE_SURFACE_ABSENT``
    且 ``admits_new_work`` 為 ``None``——「沒能建立」與「乾淨」是兩件事。"""

    outcome = reconcile_leaf.reconcile_before_new_intent(
        object(), lane="probe", lane_path=journal.probe_journal_path(_STRANDED_PROBE_ID)
    )
    assert outcome["status"] == "STARTUP_RECONCILE_SURFACE_ABSENT"
    assert outcome["admits_new_work"] is None
    assert outcome["mutation_performed"] is False


def test_a8_a_completed_probe_leaves_a_terminal_durable_journal() -> None:
    """durable 閂的另一半:成功結束的 probe 必須把 journal 標成終端,否則下一次啟動的
    §5.2 收斂會永遠把它讀成未解殘留(677a12df9 的 routed driver 恆傳 ``terminal=False``)。"""

    fs = FakeDurableFs()
    plan_id = journal.PLAN_ID_PREFIX + "a" * 64
    routed = reconcile_leaf.JournalRoutedDriver(
        object(),
        store=journal.JournalStore(fs, journal_path=journal.install_journal_path(plan_id)),
        build_journal=lambda entries, terminal: journal.build_install_journal(
            plan_id=plan_id, plan_core_digest="sha256:" + "1" * 64, idempotency_key=plan_id,
            expected_pre_state_digest="sha256:" + "2" * 64,
            aggregate_rollback_digest="sha256:" + "3" * 64, entries=entries,
            terminal=terminal,
        ),
        lock_verdict=_held(), clock=kit.frozen_clock(), step_index=0,
    )
    routed.journal_transition(entry={
        "state": "VERIFIED", "pre_state_digest": "sha256:" + "4" * 64,
        "post_state_digest": "sha256:" + "4" * 64, "terminal": True,
        "entry_source": "component_row_driver",
        "component_effect_class": "HOST_IDENTITY_INSTALL",
    })
    basename = journal.install_journal_path(plan_id).rsplit("/", 1)[-1]
    persisted = journal.verify_journal_bytes(
        fs.files[basename], journal_path=basename
    )["journal"]
    assert persisted["terminal"] is True
    # ``terminal`` 是 journal 級欄位,絕不滲進 entry 本體(closed schema)。
    assert "terminal" not in persisted["entries"][0]
    assert journal.reconcile_journal(
        persisted, observed_state_digest="sha256:" + "4" * 64
    )["status"] == "TERMINAL_NOTHING_TO_RECONCILE"


# ══════════════ A10 —— lane 路徑必須由 journal 葉的導出函式重算 ════════════════
@pytest.mark.parametrize("hostile", [
    "/etc/shadow", "//etc//passwd", "/\n/x", "/var/lib/x", "..", "",
    "/var/lib/arcane-equilibrium/aiml/install/s2_4/probes/evil.probe.journal.json",
])
def test_a10_a_lane_path_that_is_not_rederivable_is_typed_refused(hostile) -> None:
    """677a12df9:``isinstance(value, str) and value`` 是唯一檢查,於是 ``/etc/shadow``
    被當成合法 lane 路徑收下(讀取仍卡在 root-owned-0700 前置,故無洩漏,但 docstring
    宣稱的「路徑仍由導出函式產生」在結構上並不成立)。"""

    plan_id = journal.PLAN_ID_PREFIX + "a" * 64
    with pytest.raises(reconcile_leaf.InstallDriverContractError):
        reconcile_leaf.startup_journal_paths(plan_id, {"probe": hostile})


def test_a10_a_rederivable_lane_value_is_accepted_as_either_id_or_path() -> None:
    plan_id = journal.PLAN_ID_PREFIX + "a" * 64
    expected = journal.probe_journal_path(_STRANDED_PROBE_ID)
    assert reconcile_leaf.startup_journal_paths(
        plan_id, {"probe": expected}
    )["probe"] == expected
    assert reconcile_leaf.startup_journal_paths(
        plan_id, {"probe": _STRANDED_PROBE_ID}
    )["probe"] == expected


# ══════════════════════ A12 —— 非 ACQUIRED 出路不得洩漏 fd ════════════════════
def test_a12_a_contended_acquisition_closes_the_lock_fd() -> None:
    """677a12df9:``finally`` 只關 parent_fd,於是 50 次競爭洩 50 個 fd——一個重試迴圈
    會用盡 RLIMIT_NOFILE。"""

    for kwargs, expected in (
        ({"flock_succeeds": False}, "INSTALL_LOCK_HELD"),
        ({"lock_nlink": 2}, "PRECHECK_FAILED"),
        ({"replace_parent_on_fstat": True}, "PRECHECK_FAILED"),
    ):
        driver = FakeLockDriver(**kwargs)
        verdict = lock.acquire_s2_4_install_lock(driver)
        assert verdict["status"] == expected, verdict["reasons"]
        assert 11 in driver.closed, (kwargs, driver.closed)
    # 50 次連續競爭:每一次的 lock fd 都被關掉(fd 11 共出現 50 次)。
    driver = FakeLockDriver(flock_succeeds=False)
    for _ in range(50):
        lock.acquire_s2_4_install_lock(driver)
    assert driver.closed.count(11) == 50


def test_a12_a_successful_acquisition_hands_the_fd_to_the_caller() -> None:
    driver = FakeLockDriver()
    verdict = lock.acquire_s2_4_install_lock(driver)
    assert verdict["status"] == "INSTALL_LOCK_ACQUIRED"
    # 取得成功時 lock fd **不**在 acquire 內被關(呼叫端持有它直到 release)。
    assert 11 not in driver.closed
    lock.release_s2_4_install_lock(driver, verdict)
    assert driver.closed.count(11) == 1


# ═══════════ A13 —— 封好的 ledger 記的必須是它真的被寫進去的位置 ══════════════
def test_a13_the_sealed_ledger_records_the_path_it_was_written_to() -> None:
    """677a12df9:``ledger_path`` 取自被讀回的物件自報值,而不是實際寫入用的參數。"""

    moved = dict(lock.empty_replay_ledger(), ledger_path="/tmp/somewhere-else.json")
    appended = lock.append_replay_entries(
        moved,
        [{
            "authorization_id": "sha256:" + "1" * 64,
            "self_digest": "sha256:" + "2" * 64,
            "profile_identity": "aiml-s2-capability-probe-operator-v1",
        }],
        consumed_at=kit.ISSUED, ledger_path=lock.REPLAY_LEDGER_PATH,
    )
    assert appended["ledger_path"] == lock.REPLAY_LEDGER_PATH


def test_a13_a_ledger_self_reporting_a_foreign_path_is_typed_corrupt() -> None:
    fs = FakeDurableFs()
    basename = lock.REPLAY_LEDGER_PATH.rsplit("/", 1)[-1]
    foreign = lock.append_replay_entries(
        lock.empty_replay_ledger(),
        [{
            "authorization_id": "sha256:" + "1" * 64,
            "self_digest": "sha256:" + "2" * 64,
            "profile_identity": "aiml-s2-capability-probe-operator-v1",
        }],
        consumed_at=kit.ISSUED, ledger_path="/tmp/somewhere-else.json",
    )
    fs.files[basename] = validator._canonical_bytes(foreign)
    store = journal.JournalStore(fs, journal_path=lock.REPLAY_LEDGER_PATH)
    read = lock._read_durable_ledger(store, ledger_path=lock.REPLAY_LEDGER_PATH)
    assert read["status"] == "LEDGER_CORRUPT_RECOVERY_REQUIRED"
    assert any("was read from" in reason for reason in read["reasons"])
    assert read["ledger"] is None
    # 壞掉的 ledger 既未被改名也未被覆寫。
    assert fs.files[basename] == validator._canonical_bytes(foreign)


# ═════ H1 —— §5.2 的閘序:lock 在 driver 之前(重啟的 runner 先要有那把 lock)═════
def test_h1_the_lock_gate_precedes_the_driver_gate_in_startup_reconcile() -> None:
    """§5.2:重啟的 runner **只在持有**互斥 install lock 時巡查並收斂 journal,所以「有沒有
    那把 lock」是這個進入點的第一個問題。閘序倒過來時,``driver=None ∧ 無 lock`` 會回
    ``EXTERNAL_VERIFICATION_PENDING``——那句話讀起來像「只差一個主機面就成」,實際上連 §5.2
    的准入前提都不成立。

    (此迴歸建在本輪未提交的 diff 之上:``INSTALL_LOCK_REQUIRED`` 這條 typed 出路與
    ``install_lock_is_held`` 的 token 判準在 677a12df9 上都還不存在,故該 baseline 對它無意義;
    「修改前失敗」是對**本輪修改前的工作樹**成立。)
    """

    paths = {"install": journal.install_journal_path(_OTHER_PLAN_ID)}
    held = _held()
    released = _held()
    lock.release_s2_4_install_lock(FakeLockDriver(), released)
    # 沒有一把**真的**持有的 lock:無論有沒有 host file driver,先擋在 lock 閘。
    for verdict in (None, _FORGED_LOCK, {}, released):
        for driver in (None, object()):
            outcome = reconcile_leaf.reconcile_startup_journals(
                driver, journal_paths=paths, lock_verdict=verdict
            )
            assert outcome["status"] == "INSTALL_LOCK_REQUIRED", (verdict, driver)
            assert outcome["admits_new_work"] is False
            assert outcome["mutation_performed"] is False
    # 已持有 lock 但沒有 host file driver:此時、且只有此時,才是 typed PENDING。
    pending = reconcile_leaf.reconcile_startup_journals(
        None, journal_paths=paths, lock_verdict=held
    )
    assert pending["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert pending["admits_new_work"] is False and pending["mutation_performed"] is False
    # 路徑前置仍在兩道閘之前(缺 journal_paths 與 lock/driver 無關)。
    assert reconcile_leaf.reconcile_startup_journals(
        None, journal_paths={}, lock_verdict=None
    )["status"] == "RECOVERY_REQUIRED"


# ═════ H2 —— producer 判別欄是必填的(選配的判別欄等於沒有判別欄)═══════════════
def test_h2_the_component_row_producer_stamps_its_own_effect_class() -> None:
    """``_Journal`` 是 row driver 那三筆 entry 的唯一 producer。它過去只寫得出
    ``entry_source``(「是 row driver 寫的」),寫不出**哪一** row 的 subject digest 空間,
    於是三本 journal 的 schema 只能把 ``component_effect_class`` 留成 optional。"""

    import agent_governance_s2_4_component as component

    class _Recorder:
        def __init__(self) -> None:
            self.entries: list[dict] = []

        def journal_transition(self, *, entry):
            self.entries.append(dict(entry))

    recorder = _Recorder()
    row_journal = component._Journal(recorder, kit.frozen_clock(), "ENGINE_SCANNER")
    row_journal.write("APPLYING", "sha256:" + "2" * 64, "sha256:" + "2" * 64)
    assert recorder.entries == row_journal.entries
    assert recorder.entries[0]["entry_source"] == journal.ENTRY_SOURCE_COMPONENT_ROW
    assert recorder.entries[0]["component_effect_class"] == "ENGINE_SCANNER"
    # 判別欄是契約的一部分,不是自由字串:不屬於五 row 的值 typed 拒。
    for bogus in (None, "", "HOST_CAPABILITY_PROBE", "NOT_A_ROW"):
        with pytest.raises(component.ComponentContractError):
            component._Journal(recorder, kit.frozen_clock(), bogus)


def test_h2_every_entry_on_the_shared_apply_wal_names_its_digest_space(
    fx, monkeypatch
) -> None:
    """共用 WAL 上每個 row 六筆 entry 中有三筆由 row driver 以自己的 subject 空間寫入,
    另三筆由 aggregate 以 row-observation 空間寫入。兩者的 ``post_state_digest`` 在同一個
    ``step_index`` 下並不相等,所以「這一筆屬於哪個空間」不可留給 caller 猜。

    判別必須由 **producer** 給出:在 ``journal_transition`` 的入口攔下五 row 遞交的原始 entry,
    每一筆都必須已經自帶兩欄。只驗落盤後的結果並不足夠——``_append_and_commit`` 可以從
    ``step_index`` 推出 class,於是一個什麼都沒填的 producer 也能讓 WAL 看起來完整。
    """

    handed: list[dict] = []
    original = reconcile_leaf.JournalRoutedDriver.journal_transition

    def _recording(self, *, entry):
        handed.append(dict(entry))
        return original(self, entry=entry)

    monkeypatch.setattr(
        reconcile_leaf.JournalRoutedDriver, "journal_transition", _recording
    )
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    # 五 row × 三筆:每一筆遞交進來的 entry 都已自帶完整判別。
    assert len(handed) == 3 * len(runner_module.APPLY_ROW_ORDER)
    for entry in handed:
        assert entry["entry_source"] == journal.ENTRY_SOURCE_COMPONENT_ROW, entry
        assert entry["component_effect_class"] in runner_module.APPLY_ROW_ORDER, entry
    assert {entry["component_effect_class"] for entry in handed} == set(
        runner_module.APPLY_ROW_ORDER
    )
    persisted = fx.persisted_install_journal()
    for entry in persisted["entries"]:
        assert entry["entry_source"] in journal.ENTRY_SOURCES, entry
        if entry["component_effect_class"] == journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION:
            # E12:交易級 entry(終端 VERIFIED / COMPENSATING / COMPENSATED / FAILED)的
            # subject 是 plan 級前態,不屬於任何一 row 的 digest 空間;它只能由 aggregate
            # producer 宣告,且**不得**由 step_index 推出一個冒名的 row。
            assert entry["entry_source"] == journal.ENTRY_SOURCE_AGGREGATE, entry
            assert entry["state"] in {
                "VERIFIED", "COMPENSATING", "COMPENSATED", "FAILED"
            }, entry
            assert entry["pre_state_digest"] == entry["post_state_digest"], entry
        else:
            assert entry["component_effect_class"] == (
                journal.APPLY_STEP_INDEX_COMPONENT_CLASS[entry["step_index"]]
            ), entry
    sources = {entry["entry_source"] for entry in persisted["entries"]}
    assert sources == {
        journal.ENTRY_SOURCE_AGGREGATE, journal.ENTRY_SOURCE_COMPONENT_ROW
    }
    # 最後一筆的兩欄被 reconcile 原樣攤在 verdict 上:重啟的 runner 才分得出 digest 空間。
    reconciled = journal.reconcile_journal(
        persisted, observed_state_digest=persisted["entries"][-1]["post_state_digest"]
    )
    assert reconciled["terminal_entry_source"] in journal.ENTRY_SOURCES
    assert reconciled["terminal_component_effect_class"] in (
        set(journal.APPLY_STEP_INDEX_COMPONENT_CLASS.values())
        | {journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION}
    )


@pytest.mark.parametrize("missing", ["entry_source", "component_effect_class"])
def test_h2_an_entry_without_both_discriminators_is_refused_by_all_three_wals(
    missing,
) -> None:
    """三本 §5.2 journal 的 entry 契約與 ``journal_entry_sequence_errors`` 同時要求兩欄。
    少了任一欄,``JournalStore.commit`` 也不會把它落盤(而不是落盤後才發現無法收斂)。"""

    complete = {
        "install": {
            "seq": 0, "step_index": 0, "state": "APPLYING",
            "pre_state_digest": "sha256:" + "2" * 64,
            "post_state_digest": "sha256:" + "4" * 64,
            "fsynced": True, "recorded_at": kit.ISSUED,
            "entry_source": journal.ENTRY_SOURCE_AGGREGATE,
            "component_effect_class": "HOST_IDENTITY_INSTALL",
        },
        "probe": {
            "seq": 0, "state": "APPLYING", "pre_state_digest": "sha256:" + "2" * 64,
            "post_state_digest": "sha256:" + "4" * 64,
            "fsynced": True, "recorded_at": kit.ISSUED,
            "entry_source": journal.ENTRY_SOURCE_PROBE,
            "component_effect_class": "HOST_CAPABILITY_PROBE",
        },
        "prepare": {
            "seq": 0, "state": "PREPARING", "pre_state_digest": "sha256:" + "2" * 64,
            "post_state_digest": "sha256:" + "2" * 64,
            "fsynced": True, "recorded_at": kit.ISSUED,
            "entry_source": journal.ENTRY_SOURCE_PREPARE,
            "component_effect_class": "LEARNING_RUNTIME_PREPARE",
        },
    }
    probe_id = journal.PROBE_ID_PREFIX + "a" * 64
    prepare_id = journal.PREPARE_ID_PREFIX + "b" * 64
    builders = {
        "install": lambda entry: journal.build_install_journal(
            plan_id=_OTHER_PLAN_ID, plan_core_digest="sha256:" + "1" * 64,
            idempotency_key=_OTHER_PLAN_ID,
            expected_pre_state_digest="sha256:" + "2" * 64,
            aggregate_rollback_digest="sha256:" + "3" * 64, entries=[entry],
            terminal=False,
        ),
        "probe": lambda entry: journal.build_probe_journal(
            probe_id=probe_id,
            derived_unit_name=f"arcane-aiml-s2-4-probe-{'a' * 64}.service",
            scope="PREPARE_SANDBOX",
            transient_unit_property_digest="sha256:" + "1" * 64,
            expected_invocation_id_pattern="^[0-9a-f]{32}$",
            cleanup_rollback_digest="sha256:" + "2" * 64, entries=[entry],
            terminal=False,
        ),
        "prepare": lambda entry: journal.build_prepare_journal(
            prepare_id=prepare_id,
            staging_root=(
                "/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared/" + prepare_id
            ),
            entries=[entry], terminal=False,
        ),
    }
    paths = {
        "install": journal.install_journal_path(_OTHER_PLAN_ID),
        "probe": journal.probe_journal_path(probe_id),
        "prepare": journal.prepare_journal_path(prepare_id),
    }
    for lane, build in builders.items():
        assert journal.journal_entry_sequence_errors(build(complete[lane])) == []
        stripped = {k: v for k, v in complete[lane].items() if k != missing}
        broken = build(stripped)
        reasons = journal.journal_entry_sequence_errors(broken)
        assert reasons, (lane, missing)
        # 中央 validator 也擋(schema 的 entry required 現在含這兩欄)。
        assert any(
            missing in reason for reason in validator.validate_aiml_artifact(broken)
        ), (lane, missing)
        # 落盤層在 rename 之前就 typed 拒:壞 entry 從不成為 durable 的 write-ahead 證據。
        fs = FakeDurableFs()
        store = journal.JournalStore(fs, journal_path=paths[lane])
        assert store.commit(broken)["status"] == "PRECHECK_FAILED"
        assert fs.files == {}


# ═════════ E-series —— 對「上一輪修復」本身的對抗審查(E2/E3 @ 未提交工作樹)═════════
#
# 這一節每一條都對應一個由**修復本身**引入或留下的缺陷。它們的 baseline 不是 677a12df9,而是
# 本輪修改**之前**的工作樹;每一條都以 scratchpad 的丟棄式副本逐項回退驗證過(見交付報告)。


def _crash_after_consume(fx) -> None:
    """讓行程在「兩張 permit 已 durable 消費、第一筆 APPLY journal 尚未落盤」之後消失。"""

    crash = w4b.CrashingClock("post_consume")
    with pytest.raises(journal.JournalCrash):
        fx.apply(fault=crash)


def test_e1_a_burnt_permit_without_any_apply_journal_is_recovery_required(fx) -> None:
    """E1(a):consume 之後、第一筆 journal 之前崩潰 → 重跑**不得**回 ALREADY_APPLIED。

    修復前:``ALREADY_APPLIED_IDEMPOTENT`` 只看 replay 的狀態,``_load_terminal_journal``
    只檢查 ``read["status"] == JOURNAL_LOADED`` 而完全不看 ``terminal``/state,且回
    ``journal=None`` 時分支也不改——於是一台**沒有任何 row 被碰過、也沒有第一次 receipt**
    的主機收到「durable APPLY journal 與第一次執行的 receipt 仍是權威 … 沒有任何主機狀態是
    未知的,也不需要操作員介入」。兩張 permit 都已燒掉,所以這份 plan 自此永遠無法被施作。
    """

    _crash_after_consume(fx)
    assert fx.persisted_install_journal() is None
    consumed = [
        entry["profile_identity"] for entry in fx.persisted_replay_ledger()["entries"]
    ]
    assert "aiml-s2-install-operator-v1" in consumed
    assert "aiml-s2-pg-migration-operator-v1" in consumed

    verdict = fx.apply()
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict["status"]
    assert verdict["receipt"] is None
    assert verdict["journal"] is None
    # 讀不到的 typed 原因必須出現(N08:把 load-status 檢查整個刪掉時,這句話會消失)。
    assert any(journal.JOURNAL_STATUS_ABSENT in reason for reason in verdict["reasons"])
    assert any(
        "the host state is UNPROVEN" in reason for reason in verdict["reasons"]
    )
    assert any(
        "mint a NEW signed plan with fresh permits" in reason
        for reason in verdict["reasons"]
    )
    assert not any(
        "no operator action is required" in reason for reason in verdict["reasons"]
    )


def test_e1_a_mid_row_crash_replay_is_recovery_required_not_already_applied(fx) -> None:
    """E1(b):HOST_IDENTITY + PG 已施作、CREDENTIAL 崩在 pre_effect → 重跑仍不得是「已完成」。

    §5.2 的啟動收斂看的是 ``entries[-1]``,所以「觀測 == 最後一步的 pre-state」會收斂成
    ``STEP_NOT_APPLIED`` 並**准入新工作**——那對第三列是對的,對前兩列已經落在主機上的
    uid/gid、目錄與 PG role/ACL/HBA delta 卻不是。接著 replay 判 idempotent,修復前就回
    「不需操作員介入」,而那些 delta 沒有 rollback artifact、沒有證據集、沒有殘留觀測。
    """

    crash = w4b.CrashingClock("CREDENTIAL_INSTALL:pre_effect")
    with pytest.raises(journal.JournalCrash):
        fx.apply(fault=crash)
    persisted = fx.persisted_install_journal()
    assert persisted is not None and persisted["terminal"] is False
    last = persisted["entries"][-1]
    assert last["state"] == "APPLYING"

    verdict = fx.apply(
        startup_observed_state_digests={"install": last["pre_state_digest"]},
    )
    assert verdict["reconcile"]["status"] == "STARTUP_RECONCILE_STEP_NOT_APPLIED"
    assert verdict["reconcile"]["admits_new_work"] is True
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict["status"]
    assert verdict["receipt"] is None
    assert any(
        "is NOT terminal" in reason for reason in verdict["reasons"]
    ), verdict["reasons"]
    assert not any(
        "no operator action is required" in reason for reason in verdict["reasons"]
    )


def test_e1_a_terminal_verified_journal_is_the_only_idempotent_replay(fx) -> None:
    """E1 正例:第一次真的跑完(終端 VERIFIED)才是 ALREADY_APPLIED_IDEMPOTENT。"""

    first = fx.apply()
    assert first["status"] == "SOURCE_SIMULATION_PASS", first["reasons"]
    persisted = fx.persisted_install_journal()
    assert persisted["terminal"] is True
    assert journal.journal_terminal_state(persisted) == "VERIFIED"

    replay = fx.apply()
    assert replay["status"] == "ALREADY_APPLIED_IDEMPOTENT", replay["reasons"]
    assert replay["journal"]["self_digest"] == persisted["self_digest"]
    assert replay["mutation_performed"] is False
    # E9:誠實界線必須寫在原因裡——重跑**不會**補簽那份 receipt。
    assert any(
        "this replay cannot" in reason and "reconstruct it" in reason
        for reason in replay["reasons"]
    )


@pytest.mark.parametrize("terminal_state", ["COMPENSATED", "FAILED"])
def test_e1_a_terminal_compensated_journal_is_never_already_applied(
    fx, terminal_state
) -> None:
    """E1 的顯式裁決:終端 ``COMPENSATED``/``FAILED`` 都不是「已安裝」。

    ``COMPENSATED`` 代表 task-owned delta 已被逆序移除——安裝**沒有**發生,而兩張 permit 已
    燒掉;``FAILED`` 代表補償無法被證明為 exact,記的是確切殘留。把任一個讀成
    ``ALREADY_APPLIED_IDEMPOTENT``(「不需操作員介入」)都是對 on-call 謊報。
    """

    _crash_after_consume(fx)
    plan_id = fx.plan["plan_id"]
    built = journal.build_install_journal(
        plan_id=plan_id, plan_core_digest=fx.plan["core_digest"], idempotency_key=plan_id,
        expected_pre_state_digest=fx.plan["core"]["pre_state_digest"],
        aggregate_rollback_digest=runner_module.aggregate_rollback_digest(plan_id=plan_id),
        entries=[{
            "seq": 0, "step_index": 0, "state": terminal_state,
            "pre_state_digest": fx.plan["core"]["pre_state_digest"],
            "post_state_digest": fx.plan["core"]["pre_state_digest"],
            "fsynced": True, "recorded_at": kit.ISSUED,
            "entry_source": journal.ENTRY_SOURCE_AGGREGATE,
            "component_effect_class": journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION,
        }],
        terminal=True,
    )
    basename = journal.install_journal_path(plan_id).rsplit("/", 1)[-1]
    fx.fs.files[basename] = validator._canonical_bytes(built)

    verdict = fx.apply(
        startup_observed_state_digests={"install": fx.plan["core"]["pre_state_digest"]},
    )
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict["status"]
    assert verdict["receipt"] is None
    if terminal_state == "FAILED":
        # ``FAILED`` 更早就被 §5.2 的啟動收斂擋住(它記的是確切殘留)。
        assert verdict["reconcile"]["admits_new_work"] is False
        return
    # ``COMPENSATED`` 在啟動收斂上是「無需收斂」,所以擋住它的只能是 idempotent-replay
    # 分支自己的終端 state 裁決。
    assert verdict["reconcile"]["status"] == "STARTUP_RECONCILE_CLEAN"
    assert verdict["reconcile"]["admits_new_work"] is True
    assert any(
        f"terminal state is {terminal_state!r}, not 'VERIFIED'" in reason
        for reason in verdict["reasons"]
    ), verdict["reasons"]


# ── E5:主機時鐘 ↔ permit 窗 ────────────────────────────────────────────────────
def test_e5_a_host_clock_outside_the_permit_window_blocks_the_receipt(fx) -> None:
    """E5:M25(``if not issued <= host_moment < expires:`` → ``if False:``)必須被殺。

    既有的 ``test_c18_*`` 只覆蓋 ±60s 的 skew 上限,而讓 permit 新鮮度成為**主機**性質而非
    caller 性質的正是這一段窗檢查:主機說「這張 permit 現在不在有效期內」時,交易不得簽出
    receipt。此處把 trusted host time 放在 anchor−30s(仍在 skew 內,故 skew 那道不會觸發),
    而 permit 窗自 anchor 起算。
    """

    host_time = (kit.ANCHOR - timedelta(seconds=30)).isoformat()
    observed = (kit.ANCHOR + timedelta(seconds=30)).isoformat()
    fx.driver.trusted_time = host_time
    verdict = fx.apply(now=observed)
    assert verdict["status"] == "RECEIPT_EMISSION_PENDING", verdict["status"]
    assert verdict["receipt"] is None
    assert any(
        "outside the apply_aggregate permit window" in reason
        for reason in verdict["reasons"]
    ), verdict["reasons"]
    # skew 那道**不**觸發(60s 恰好等於上限),所以這條紅只可能來自窗檢查。
    assert not any("clock skew ceiling" in reason for reason in verdict["reasons"])


# ── E8:probe-core 綁定的可見性 ────────────────────────────────────────────────
def test_e8_the_probe_core_binding_status_is_visible_on_every_verdict(fx) -> None:
    """E8:``expected_installed_unit_probe_core_digest`` 是選配的,所以「有沒有被檢查」
    必須是 verdict 上的 typed 事實——否則下游讀者分不出「檢查過」與「跳過」。"""

    skipped = fx.apply()
    assert skipped["probe_core_binding"] == "UNVERIFIED_NO_EXPECTED_VALUE_SUPPLIED"
    supplied = fx.apply(
        expected_installed_unit_probe_core_digest=(
            fx.probe_receipts["INSTALLED_UNIT"]["probe_core_digest"]
        ),
    )
    assert supplied["probe_core_binding"] == "VERIFIED_AGAINST_SUPPLIED_EXPECTED_DIGEST"
    # 零變更的早期拒絕也帶著同一個 typed 事實。
    pending = fx.apply(driver=None)
    assert pending["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert pending["probe_core_binding"] == "UNVERIFIED_NO_EXPECTED_VALUE_SUPPLIED"


# ── E10:每個 §9 bound term 都必須有導出來源 ───────────────────────────────────
def test_e10_a_bound_term_with_no_derived_source_is_refused_with_zero_mutation(fx) -> None:
    """E10:省略 ``topology_attestation`` 並自報 ``10**9`` 過去讓預算不等式在**捏造**的界上
    通過——而 ``PG_ROLE_ACL_MIGRATION`` 直到 ``HOST_IDENTITY_INSTALL`` 動過主機之後才會失敗。"""

    payloads = fx.row_payloads()
    payloads["PG_ROLE_ACL_MIGRATION"].pop("topology_attestation")
    verdict = fx.apply(
        row_payloads=payloads,
        remaining_ttls={
            **w4b.REMAINING_TTLS, "topology_attestation_remaining_ttl": 10 ** 9,
        },
    )
    assert verdict["status"] == "PRECHECK_FAILED", verdict["status"]
    assert verdict["mutation_performed"] is False
    assert verdict["driver_engaged"] is False
    assert fx.driver.calls == []
    assert fx.persisted_install_journal() is None
    assert any(
        "'topology_attestation_remaining_ttl' has no derived source" in reason
        for reason in verdict["reasons"]
    ), verdict["reasons"]


# ── E11:證據集落盤失敗必須留痕 ───────────────────────────────────────────────
def test_e11_a_failed_evidence_set_write_is_named_in_the_verdict(fx, monkeypatch) -> None:
    """E11:``EFFECT_RECEIPT_RECONCILE_BINDING`` 宣稱的那份綁定 artifact 沒寫成時,終端狀態
    與 receipt 完全不變——修復前那件事在 verdict 上完全靜默。"""

    monkeypatch.setattr(
        runner_module._evidence, "commit_install_evidence_set",
        lambda file_driver, evidence: {
            "status": "INSTALL_EVIDENCE_SET_UNAVAILABLE",
            "reasons": ["injected durable evidence-set write failure"],
        },
    )
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert verdict["evidence_set"]["status"] == "INSTALL_EVIDENCE_SET_UNAVAILABLE"
    assert any(
        "EFFECT_RECEIPT_RECONCILE_BINDING" in reason for reason in verdict["reasons"]
    ), verdict["reasons"]
    assert any(
        "injected durable evidence-set write failure" in reason
        for reason in verdict["reasons"]
    )


# ── E12:交易級 entry 不得冒名一列 ─────────────────────────────────────────────
def test_e12_an_aggregate_teardown_entry_does_not_impersonate_the_first_row(fx) -> None:
    """E12:``failing_row is None`` 時 ``step_index`` 退回 0,journal 葉於是把五列全數拆除的
    COMPENSATING/終端 entry 推導成 ``HOST_IDENTITY_INSTALL``——必填判別欄被一個**事實上錯誤**
    的推導值滿足,而衝突檢查只在顯式不一致時才會開火。"""

    fx.driver.postcheck_flags["plan_lineage_verified"] = False
    verdict = fx.apply()
    assert verdict["status"] in {"RECOVERY_REQUIRED", "POSTCHECK_FAILED_ROLLED_BACK"}
    persisted = fx.persisted_install_journal()
    scoped = [
        entry for entry in persisted["entries"]
        if entry["state"] in {"COMPENSATING", "COMPENSATED", "FAILED"}
    ]
    assert scoped, [entry["state"] for entry in persisted["entries"]]
    for entry in scoped:
        assert entry["component_effect_class"] == (
            journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION
        ), entry
        assert entry["entry_source"] == journal.ENTRY_SOURCE_AGGREGATE, entry
    reconciled = journal.reconcile_journal(
        persisted, observed_state_digest=persisted["entries"][-1]["post_state_digest"]
    )
    assert reconciled["terminal_component_effect_class"] == (
        journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION
    )


def test_e12_a_row_producer_can_never_claim_the_aggregate_scope() -> None:
    """交易級 scope 只有 aggregate producer 能宣告(否則它就成了繞過判別的萬用鍵)。"""

    fs = FakeDurableFs()
    store = journal.JournalStore(fs, journal_path=journal.install_journal_path(_OTHER_PLAN_ID))
    transaction = _wal(store)
    with pytest.raises(journal.JournalContractError) as excinfo:
        transaction.record(
            state="APPLYING", pre_state_digest="sha256:" + "2" * 64,
            post_state_digest="sha256:" + "4" * 64, step_index=0,
            entry_source=journal.ENTRY_SOURCE_COMPONENT_ROW,
            component_effect_class=journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION,
        )
    assert excinfo.value.code == (
        "journal_entry_aggregate_scope_requires_the_aggregate_producer"
    )
    assert fs.files == {}


def _wal(store):
    def _build(entries, terminal):
        return journal.build_install_journal(
            plan_id=_OTHER_PLAN_ID, plan_core_digest="sha256:" + "1" * 64,
            idempotency_key=_OTHER_PLAN_ID,
            expected_pre_state_digest="sha256:" + "2" * 64,
            aggregate_rollback_digest="sha256:" + "3" * 64, entries=entries,
            terminal=terminal,
        )

    return journal.WriteAheadTransaction(store, build_journal=_build, clock=kit.frozen_clock())


# ── E13:兩個 typed 契約錯必須真的經 _append_and_commit 被證明 ────────────────
def test_e13_an_entry_with_no_resolvable_effect_class_is_a_typed_contract_error() -> None:
    """M09(刪掉 ``journal_entry_component_effect_class_required`` 那個 raise)必須被殺。"""

    fs = FakeDurableFs()
    store = journal.JournalStore(fs, journal_path=journal.install_journal_path(_OTHER_PLAN_ID))
    transaction = _wal(store)
    with pytest.raises(journal.JournalContractError) as excinfo:
        transaction.record(
            state="APPLYING", pre_state_digest="sha256:" + "2" * 64,
            post_state_digest="sha256:" + "4" * 64, step_index=None,
        )
    assert excinfo.value.code == "journal_entry_component_effect_class_required"
    assert fs.files == {}


def test_e13_a_producer_declared_class_conflicting_with_the_step_is_a_contract_error() -> None:
    """M10(刪掉 ``..._conflicts_step`` 那個 raise)必須被殺。"""

    fs = FakeDurableFs()
    store = journal.JournalStore(fs, journal_path=journal.install_journal_path(_OTHER_PLAN_ID))
    transaction = _wal(store)
    with pytest.raises(journal.JournalContractError) as excinfo:
        transaction.record(
            state="APPLYING", pre_state_digest="sha256:" + "2" * 64,
            post_state_digest="sha256:" + "4" * 64, step_index=0,
            component_effect_class="ENGINE_SCANNER",
        )
    assert excinfo.value.code == "journal_entry_component_effect_class_conflicts_step"
    assert fs.files == {}


# ── E14:一次瞬時讀取失敗不得拆掉一筆正確的安裝 ───────────────────────────────
def test_e14_a_transient_observation_failure_is_retried_not_fatal() -> None:
    """N06(``RESIDUE_OBSERVATION_ATTEMPTS`` 3→1)必須被殺:既有測試斷言的是
    ``len(calls) == RESIDUE_OBSERVATION_ATTEMPTS``,那對任何常量都成立。"""

    import agent_governance_s2_4_install_evidence as evidence_leaf

    class _FlakyDriver:
        def __init__(self) -> None:
            self.calls = 0

        def observe_installed_unit_state(self):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("transient")
            return {"loaded": True, "disabled": True, "inactive": True}

    driver = _FlakyDriver()
    residue = evidence_leaf.observe_install_residue(driver, {})
    assert residue["observation_status"] == "INSTALLED_UNIT_OBSERVED_INACTIVE"
    assert residue["installed_unit_inactive"] is True
    assert driver.calls == 2
    assert evidence_leaf.RESIDUE_OBSERVATION_ATTEMPTS > 1
    # 界限在 1 時,同一個瞬時失敗就會把一筆已完整驗證的安裝判成 UNOBSERVABLE。
    once = evidence_leaf.observe_install_residue(_FlakyDriver(), {}, attempts=1)
    assert once["observation_status"] == "INSTALLED_UNIT_OBSERVATION_UNAVAILABLE"


# ── E16:擱淺的 WAL 暫存檔必須被看見 ──────────────────────────────────────────
def test_e16_stranded_wal_temp_files_are_enumerated_and_reported(fx) -> None:
    """E16:跨行程唯一的暫存名讓 ``O_EXCL`` 再也撞不到殘留,於是它只能靠列舉被看見。"""

    basename = journal.install_journal_path(_OTHER_PLAN_ID).rsplit("/", 1)[-1]
    stranded = journal.journal_temp_basename(basename, attempt=0)
    fs = FakeDurableFs(temp_residue=(stranded,))
    verdict = reconcile_leaf.reconcile_startup_journals(
        fs, journal_paths=_install_paths(fx.plan["plan_id"]), lock_verdict=_held(),
    )
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict["status"]
    assert verdict["admits_new_work"] is False
    assert verdict["mutation_performed"] is False
    assert stranded in verdict["enumerated_parents"]["install"]["temp_residue"]
    assert any(
        "stranded write-ahead temp files" in reason for reason in verdict["reasons"]
    ), verdict["reasons"]
    assert any(
        journal.JOURNAL_STATUS_TEMP_COLLISION in reason for reason in verdict["reasons"]
    )


# ── E18:live-token 集合不得以 CPython 的位址為鍵 ──────────────────────────────
def test_e18_a_dropped_lock_token_cannot_be_satisfied_by_address_reuse() -> None:
    """E18:``_LIVE_LOCK_TOKENS`` 記 ``id(token)`` 時,一個 acquire 之後把 verdict 丟掉而
    未 release 的呼叫端會留下一個永久 live 的位址;CPython 把該位址配給下一個同型物件之後,
    那個**從未被發出**的 token 就通得過 ``install_lock_is_held``,卻沒有持有任何 flock。"""

    held = _held()
    token = held["lock_token"]
    assert lock.install_lock_is_held(held) is True
    stale_id = id(token)
    stale_nonce = token.nonce
    del held, token  # acquire 過但沒有 release:登記留在 live-set 裡
    try:
        replacement = None
        parked = []
        for _ in range(4096):
            candidate = lock._InstallLockToken(lock_fd=999)
            if id(candidate) == stale_id:
                replacement = candidate
                break
            parked.append(candidate)
        assert replacement is not None, (
            "CPython did not reuse the freed token address in 4096 allocations; this test "
            "cannot demonstrate the id-reuse property on this interpreter"
        )
        forged = {"status": lock.LOCK_STATUS_ACQUIRED, "lock_token": replacement}
        assert lock.install_lock_is_held(forged) is False
    finally:
        lock._LIVE_LOCK_TOKENS.discard(stale_nonce)


# ── E19:hoist 的 pre-lock 簽章閘必須用**已解析**的觀測時刻 ────────────────────
def test_e19_a_permit_outside_its_freshness_window_never_reaches_the_install_lock(
    fx,
) -> None:
    """E19:``now`` 的 ABI 預設是 ``None``,而 ``_s2_4_operator_authorization_errors`` 在
    ``now is None`` 時**整段跳過**新鮮度檢查——於是那個「先驗簽再取 lock」的 hoist 對一張窗外
    的合法簽章完全無效:它照樣 flock install lock、跑啟動 reconcile、讀 ledger 與 journal。

    此處以 fixture 的凍結 permit 窗(2030-01-01 起算)配上 ``now=None``(= 真實牆鐘)重現它:
    permit 落在窗外,而每一份證據的 ``expires_at`` 仍在牆鐘之後,故 §9 的預算閘抓不到它。
    """

    verdict = fx.apply(now=None)
    assert verdict["status"] == "AUTHORIZATION_REJECTED", verdict["status"]
    assert verdict["driver_engaged"] is False
    assert verdict["mutation_performed"] is False
    assert fx.driver.calls == []
    assert fx.lock_fake.calls == []
    assert fx.persisted_install_journal() is None
    # ledger 只剩 fixture 種下的三筆前導 lineage:沒有任何 permit 被消費。
    assert len(fx.persisted_replay_ledger()["entries"]) == 3
    assert any(
        "not currently within its freshness window" in reason
        for reason in verdict["reasons"]
    ), verdict["reasons"]
    assert any(
        "before the install lock is created or flocked" in reason
        for reason in verdict["reasons"]
    )


# ── E20:敵意 driver 的 attestation 不得讓例外逸出凍結 ABI ────────────────────
@pytest.mark.parametrize("poison", [float("nan"), float("inf"), {"a", "b"}])
def test_e20_a_non_serializable_attestation_is_typed_rejected(fx, poison) -> None:
    """E20:``apply_attestation_digest`` 在任何 try 之外,故 18 個正確鍵配上一個 ``NaN`` /
    ``inf`` / ``set`` 就能讓 ``json.dumps(allow_nan=False)`` 的例外從 §10.2 的凍結 ABI 逸出
    ——而且是在主機已完整變更、終端 journal 已 commit **之後**。"""

    import agent_governance_s2_4_install_evidence as evidence_leaf

    attestation = {field: "x" for field in evidence_leaf.APPLY_ATTESTATION_FIELDS}
    attestation["evidence_class"] = poison

    outcome = evidence_leaf.derive_apply_attestation_status(
        attestation, b"not-a-signature", plan=fx.plan,
        applier_node=runner_module.AGGREGATE_APPLIER_NODE, verifier_node="verifier",
        row_results={}, installed_unit_state={}, authorizations=fx.authorization_set,
    )
    assert outcome["status"] == "APPLY_ATTESTATION_REJECTED"
    assert any("not canonically serializable" in reason for reason in outcome["reasons"])

    # 端到端:同一份 attestation 經真交易也只能收在 SOURCE_SIMULATION_PASS,絕不 raise。
    fx.driver.apply_attestation = lambda: {
        "attestation": dict(attestation), "signature": b"not-a-signature",
    }
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert verdict["attestation"]["status"] == "APPLY_ATTESTATION_REJECTED"
