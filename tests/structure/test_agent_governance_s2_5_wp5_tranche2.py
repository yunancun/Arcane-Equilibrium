"""S2.5(WP5 tranche 2)攜帶 P2 的紅→綠測試——P2-2 consume→persist 交易互斥。

修前紅證據:pristine clone(base ``dab875882``)上本檔全紅——`S2_5FlockProbe` 只有
probe-only 面(`flock_probe` 探測即釋放),anchor-check→consume→persist→journal 的
交易窗沒有任何互斥;第二個 applier 可在窗內交錯而雙消費同一張 permit。

修後(hold-style acquire/release,鏡 ``agent_governance_s2_4_lock`` 公開形制):

- 窗內第二個 applier ⇒ typed 拒(零消費、零 driver 接觸、零 journal);
- persist 當下 flock 真的被持有(probe-only 面到不了這個斷言);
- release 在 finally——成功與拒絕路徑之後鎖都自由;
- probe-only 介面(無 acquire 面)fail-closed。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import s2_5_testkit as kit  # noqa: E402


# ── P2-2:hold-style 面本體(真 flock)────────────────────────────────────────────
def test_hold_style_acquire_release_semantics_on_a_real_flock(tmp_path):
    lock_path = tmp_path / "life.lock"
    holder = lifecycle.S2_5FlockProbe(lock_path)
    verdict = holder.acquire()
    assert verdict["status"] == "S2_5_LIFECYCLE_LOCK_ACQUIRED"
    # 持有期間:同 path 的另一個 probe 面觀測 held、acquire 得 typed HELD、不可重入。
    other = lifecycle.S2_5FlockProbe(lock_path)
    assert other.flock_probe()["held"] is True
    assert other.acquire()["status"] == "S2_5_LIFECYCLE_LOCK_HELD"
    assert holder.acquire()["status"] == "S2_5_LIFECYCLE_LOCK_HELD"  # 不可重入。
    # release:鎖自由、lock 檔仍在(永不 unlink)、重複 release=typed NOT_HELD。
    assert holder.release()["status"] == "S2_5_LIFECYCLE_LOCK_RELEASED"
    assert other.flock_probe()["held"] is False
    assert lock_path.exists()
    assert holder.release()["status"] == "S2_5_LIFECYCLE_LOCK_NOT_HELD"
    # symlink 替身:O_NOFOLLOW 拒(typed PRECHECK_FAILED,零變更)。
    real = tmp_path / "real.lock"
    real.touch()
    link = tmp_path / "link.lock"
    link.symlink_to(real)
    assert lifecycle.S2_5FlockProbe(link).acquire()["status"] == (
        "S2_5_LIFECYCLE_LOCK_PRECHECK_FAILED"
    )


def test_probe_only_interface_cannot_open_the_consume_window():
    # 無 hold 面的介面(舊 probe-only 形狀)fail-closed——窗永不打開。
    class ProbeOnly:
        def flock_probe(self):
            return {"held": False, "exists": True, "lock_path": "<probe-only>"}

    ok, reasons = lifecycle.acquire_s2_5_lifecycle_hold(ProbeOnly())
    assert ok is False
    assert any("probe-only" in reason for reason in reasons)
    # 取鎖逸出=unproven fail-closed。
    class Exploding:
        def acquire(self):
            raise RuntimeError("lock backend lost")

    ok2, reasons2 = lifecycle.acquire_s2_5_lifecycle_hold(Exploding())
    assert ok2 is False and any("raised" in reason for reason in reasons2)


# ── P2-2:第二個 applier 在鎖窗內 ⇒ typed 拒非雙消費 ────────────────────────────────
def test_second_applier_inside_the_window_is_rejected_without_double_consumption(
    tmp_path, monkeypatch
):
    lock_path = tmp_path / "life.lock"
    # applier 1 站在鎖窗內(hold-style acquire 未釋放)。
    in_window = lifecycle.S2_5FlockProbe(lock_path)
    assert in_window.acquire()["status"] == "S2_5_LIFECYCLE_LOCK_ACQUIRED"
    try:
        _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
        unit = kit.SimulatedUnit()
        ledger = kit.empty_ledger()
        verdict = lifecycle.apply_s2_5_start(
            intent, permit, unit,
            **kit.apply_kwargs(
                tmp_path=tmp_path, unit=unit, replay_ledger=ledger,
                lock_probe=lifecycle.S2_5FlockProbe(lock_path),
            ),
        )
        # typed 拒、零消費、零 driver 接觸、零 journal/ledger 落盤。
        assert verdict["status"] == "REQUEST_REJECTED", verdict
        assert ledger["entries"] == []
        assert unit.calls == []
        assert not (tmp_path / "state").exists()
    finally:
        in_window.release()
    # 窗釋放後,同一張 permit 由同一 probe 面正常消費(鎖窗只擋交錯,不擋合法流)。
    unit2 = kit.SimulatedUnit()
    verdict2 = lifecycle.apply_s2_5_start(
        intent, permit, unit2,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit2,
            lock_probe=lifecycle.S2_5FlockProbe(lock_path),
        ),
    )
    assert verdict2["status"] == "SOURCE_SIMULATION_PASS", verdict2["reasons"]


def test_consume_persist_journal_window_really_holds_the_flock_and_releases(
    tmp_path, monkeypatch
):
    lock_path = tmp_path / "life.lock"
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    observed: dict[str, bool] = {}
    real_persist = lifecycle._persist_s2_5_replay_ledger

    def _spy(ledger_path, replay_ledger):
        # persist 當下,獨立 probe 必須觀測到鎖被持有(probe-only 面到不了這裡)。
        observed["held_during_persist"] = (
            lifecycle.S2_5FlockProbe(lock_path).flock_probe()["held"]
        )
        return real_persist(ledger_path, replay_ledger)

    monkeypatch.setattr(lifecycle, "_persist_s2_5_replay_ledger", _spy)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit,
            lock_probe=lifecycle.S2_5FlockProbe(lock_path),
        ),
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert observed["held_during_persist"] is True
    # release 在 finally:apply 之後鎖自由。
    assert lifecycle.S2_5FlockProbe(lock_path).flock_probe()["held"] is False


def test_final_window_holds_the_flock_too(tmp_path, monkeypatch):
    lock_path = tmp_path / "life.lock"
    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    observed: dict[str, bool] = {}
    real_persist = lifecycle._persist_s2_5_replay_ledger

    def _spy(ledger_path, replay_ledger):
        observed["held_during_persist"] = (
            lifecycle.S2_5FlockProbe(lock_path).flock_probe()["held"]
        )
        return real_persist(ledger_path, replay_ledger)

    monkeypatch.setattr(lifecycle, "_persist_s2_5_replay_ledger", _spy)
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, unit,
        **kit.final_apply_kwargs(
            tmp_path=tmp_path, unit=unit,
            lock_probe=lifecycle.S2_5FlockProbe(lock_path),
        ),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert observed["held_during_persist"] is True
    assert lifecycle.S2_5FlockProbe(lock_path).flock_probe()["held"] is False


def test_window_rejection_paths_release_in_finally(tmp_path, monkeypatch):
    # 窗內拒絕(前態不符)之後鎖必須自由——release 在 finally,不在 happy path 尾巴。
    lock_path = tmp_path / "life.lock"
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    unit.enable_now()  # 前態已 active ⇒ 窗內 REQUEST_REJECTED。
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit,
            lock_probe=lifecycle.S2_5FlockProbe(lock_path),
        ),
    )
    assert verdict["status"] == "REQUEST_REJECTED"
    assert lifecycle.S2_5FlockProbe(lock_path).flock_probe()["held"] is False


def test_simulated_probe_release_is_invoked_exactly_once_per_window(
    tmp_path, monkeypatch
):
    # 注入模擬面:成功路徑 acquire/release 各恰一次(finally 不重複、不遺漏)。
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    probe = kit.SimulatedLockProbe()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, lock_probe=probe),
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS"
    assert (probe.acquires, probe.releases) == (1, 1)
    assert probe.holding is False


def test_consume_refused_under_the_lock_is_typed_not_an_escape(tmp_path, monkeypatch):
    """鎖下 consume 的 ValueError 臂:窗內重導出裁決失敗=typed AUTHORIZATION_REJECTED。

    構造:step-4 預檢之後、窗內 consume 之前,ledger 被塞入同 authorization 的消費紀錄
    (以 monkeypatch 在 anchor-check 時機注入,模擬「另一路已消費」的交錯)。
    """

    import agent_governance_s2_5_attestation as attestation

    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    ledger = kit.empty_ledger()
    real_anchor = lifecycle._replay_ledger_anchor_reasons

    def _race(journal_path, ledger_path, replay_ledger):
        # 在鎖窗內、consume 之前,把同一張 permit 標記為已消費(模擬交錯者)。
        if not replay_ledger["entries"]:
            attestation.consume_s2_5_authorization(
                replay_ledger, permit, start_id=intent["start_id"], consumed_at=kit.NOW
            )
        return real_anchor(journal_path, ledger_path, replay_ledger)

    monkeypatch.setattr(lifecycle, "_replay_ledger_anchor_reasons", _race)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, replay_ledger=ledger),
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED", verdict
    assert any("under the lifecycle lock" in r for r in verdict["reasons"])
    assert len(ledger["entries"]) == 1  # 只有交錯者那一筆;本 applier 零重複消費。
    assert unit.calls[:1] != ["enable_now"]  # effect 未發生。
    # durable ledger 未被本 applier 落盤(consume 拒絕在 persist 之前)。
    assert not lifecycle.s2_5_replay_ledger_path(tmp_path / "state").exists()


def test_journal_pin_still_binds_after_the_window(tmp_path, monkeypatch):
    # 窗閉合後 journal 的 APPLYING 已釘 ledger head(P1-3 anchor 與 P2-2 疊加不互斥)。
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS"
    journal_path = lifecycle.s2_5_journal_path(tmp_path / "state", intent["start_id"])
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["replay_ledger_head"]["entry_count"] == 1
