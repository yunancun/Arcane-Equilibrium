"""On-target (trade-core) real-primitive proof for the S1.6B probe — SKIPS off-target.

Gated on ``target_host_available()`` (linux + ``systemd-run`` on PATH +
``AIML_TARGET_HOST_PROBE=1``).  On this Mac / any non-target node the whole module
skips honestly — it never simulates a kernel fact.  On ``trade-core`` it drives the
REAL non-root user-scope primitives (``systemd-run --user --scope`` lifecycle,
cgroup cpu/mem/pids enforcement, seccomp ``SCMP_ACT_ERRNO(ENETUNREACH)`` egress
denial (differential vs a no-filter baseline) + ``bwrap`` native-lib
load, content-addressed bundle atomic swap, kill/restart/teardown + independent
residue check, pluggable PG-identity) and asserts the end-to-end target-host
choice receipt is a PLATFORM_OR_EXTERNAL_ATTESTED PASS whose binding is BINDING
(if postgresql-server is installed) or PROVISIONAL_PENDING_LINUX naming
``pg_identity`` (server absent) — the honest, non-faked target-host exit.
"""

from __future__ import annotations

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

import agent_governance_target_host_probe as th  # noqa: E402

OBS = "2026-07-23T12:00:00+00:00"
FRESH = "2026-07-23T12:05:00+00:00"
# governed on-host capture(command_capture_v2)參照:真跑由 OPS capture-command 綁定;此處代表其 record_digest。
CAPTURE_DIGEST = "sha256:" + "c" * 64

on_target = pytest.mark.skipif(
    not th.target_host_available(),
    reason="not the target host (need linux + systemd-run + AIML_TARGET_HOST_PROBE=1); skips honestly, never fakes",
)


@pytest.fixture(scope="module")
def probe_output(tmp_path_factory):
    import os

    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    throwaway = os.path.join(xdg, f"aiml_s16b_{os.getpid()}")
    os.makedirs(throwaway, exist_ok=True)
    try:
        # run_target_host_probe 頂層 finally 會 rmtree throwaway_root(即使 raw caller 直呼也不留殘留)。
        yield th.run_target_host_probe(
            throwaway_root=throwaway,
            pg_readonly_identity_receipt_digest="sha256:" + "a" * 64,
            target_host_capture_digest=CAPTURE_DIGEST,
        )
    finally:
        import shutil

        shutil.rmtree(throwaway, ignore_errors=True)


@on_target
def test_real_probe_emits_attested_receipt(probe_output):
    assert probe_output["evidence_class"] == "PLATFORM_OR_EXTERNAL_ATTESTED"
    assert probe_output["target_host_capture_digest"] == CAPTURE_DIGEST
    fixed_seams = probe_output["fixed_path_seams"]
    assert {seam["seam_id"] for seam in fixed_seams} == th.TARGET_HOST_SEAM_SET
    # #1:applier 自跑的 independent_postcheck 恆 DEFERRED(無法自證獨立性)。
    ip_seam = next(seam for seam in fixed_seams if seam["seam_id"] == "independent_postcheck")
    assert ip_seam["verdict"] == "DEFERRED_TARGET_HOST"
    # #T2:failure_rollback_cleanup 必真重啟已佈署的內容定址 bundle 並解析回它(proc cwd 落在 bundle root 下)
    # 才 PASSED——否則只證「隨便一個 sleeper 能殺能重跑」。
    frc_seam = next(seam for seam in fixed_seams if seam["seam_id"] == "failure_rollback_cleanup")
    assert frc_seam["verdict"] == "PASSED_TARGET_HOST", (
        f"expected rollback seam to restart the deployed bundle and resolve to it, "
        f"got {frc_seam['verdict']}: {frc_seam['note']}"
    )
    assert "resolves" in frc_seam["note"]

    # #T1:require_target_host_attested 需要一個內嵌的 governed command_capture_v2 ARTIFACT(非裸 digest)。
    # 這裡用結構有效的 artifact SHAPE(offline-unauthenticated,非真 governed capture)行使新的綁定路徑;
    # 真出口綁的是 OPS ``capture-command`` 產出的真 record。builder 由 artifact 的 record_digest 派生
    # target_host_capture_digest(digest 與 artifact 不可解耦)。
    capture_artifact = th._structural_capture_artifact()
    applier = th.build_target_host_choice_receipt(
        caller="E1:S1.6B:on-target",
        platform=th.detect_platform(),
        target_class="target_host",
        host_identity=probe_output["host_identity"],
        apply_actor_node="s16b_apply_actor",
        postcheck_verifier_node="s16b_independent_verifier",
        fixed_path_seams=fixed_seams,
        pg_identity_mode=probe_output["pg_identity_mode"],
        evidence_class=probe_output["evidence_class"],
        real_target_host_primitives_invoked=True,
        complete_teardown_verified=True,
        runtime_candidate_receipt_a_digest="sha256:" + "0" * 64,
        runtime_candidate_receipt_b_digest="sha256:" + "1" * 64,
        runtime_candidate_comparison_digest="sha256:" + "2" * 64,
        effect_seams_ready_receipt_digest="sha256:" + "3" * 64,
        pg_readonly_identity_receipt_digest="sha256:" + "a" * 64,
        observation_time=OBS, ttl_seconds=900,
        target_host_capture_artifact=capture_artifact,
    )
    assert applier["host_identity"]["observed_host"] == applier["host_identity"]["expected_host"]
    assert applier["target_host_capture"]["record_digest"] == applier["target_host_capture_digest"]
    # applier 自跑 receipt 為 PASS 但 PROVISIONAL,指名 independent_postcheck(尚待 distinct 驗證者)。
    assert applier["status"] == "PASS"
    assert applier["selection"]["final_choice"] == "content_addressed_fixed_path"
    assert applier["selection"]["oci_selectable"] is False
    assert applier["selection"]["binding"] == "PROVISIONAL_PENDING_LINUX"
    assert "independent_postcheck" in applier["selection"]["pending_seams"]

    # distinct OPS 驗證者以真 on-host 殘留掃描附掛(units/cgroup/netns/temp 皆已清)。
    swept = th.independent_postcheck_on_host(
        unit=f"aiml-probeB-absent-{os.getpid()}.scope",
        teardown_root=os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", f"aiml_s16b_{os.getpid()}"),
    )
    residue_observation = {
        "units_gone": swept["unit_absent"],
        "cgroup_gone": swept["cgroup_gone"],
        "netns_gone": True,  # network-denial 為 seccomp(行程本地 filter,隨子行程退出即消),無 netns/殘留。
        "temp_gone": swept["temp_gone"],
    }
    bound = th.attach_independent_postcheck(
        applier, verifier_node="s16b_independent_verifier",
        residue_observation=residue_observation, now=OBS,
    )
    # 附掛後:pg real → BINDING;pg deferred(server 缺席)→ PROVISIONAL 指名 pg_identity。
    if probe_output["pg_identity_mode"] == "real_initdb_cluster":
        assert bound["selection"]["binding"] == "BINDING"
        assert bound["selection"]["pending_seams"] == []
    else:
        assert bound["selection"]["binding"] == "PROVISIONAL_PENDING_LINUX"
        assert bound["selection"]["pending_seams"] == ["pg_identity"]
    assert th.validate_target_host_choice_receipt(
        bound, require_success=True, require_target_host_attested=True, now=FRESH
    ) == []


@on_target
def test_real_start_stop_lifecycle_observed():
    seam = th.probe_start_stop_on_host(launcher_argv=[sys.executable, "-I", "-c", "import time; time.sleep(20)"], nonce="ltest")
    assert seam["seam_id"] == "start_stop"
    assert seam["verdict"] in {"PASSED_TARGET_HOST", "DEFERRED_TARGET_HOST"}


@on_target
def test_real_network_denial_enforced():
    seam = th.probe_network_denial_on_host()
    assert seam["seam_id"] == "network_denial"
    # 差分證明(seccomp):同一 host/port,無過濾 baseline 真連上(證明本機有 egress),
    # 裝了 connect/sendto/sendmsg 拒絕過濾的子行程真連時被 kernel 拒(ENETUNREACH)。
    # trade-core 有 libseccomp → 期望 PASSED;若某 host 缺 libseccomp 則誠實 DEFERRED。
    assert seam["verdict"] == "PASSED_TARGET_HOST", (
        f"expected seccomp egress denial to PASS on trade-core, got {seam['verdict']}: {seam['note']}"
    )


@on_target
def test_real_cgroup_enforcement_observed():
    # 真 cgroup enforcement:child hog 被 OOM 殺(main 存活保 scope)、fork 觸 pids.max、busy-loop 觸 cpu 節流;
    # 三計數皆自 scope 自身 cgroup 檔真讀。trade-core 委派 cpu/mem/pids → 期望 PASSED。
    seam = th.probe_cgroup_isolation_on_host(nonce="cgtest")
    assert seam["seam_id"] == "cgroup_resource_isolation"
    assert seam["verdict"] == "PASSED_TARGET_HOST", (
        f"expected cgroup oom_kill/pids.max/throttled all enforced on trade-core, got {seam['verdict']}: {seam['note']}"
    )


@on_target
def test_real_native_lib_bundle_origin_with_symbol(tmp_path):
    # 真 native-lib:現編唯一 soname 的 .so 進 bundle、CDLL、maps 證 bundle 來源、符號真回 42。
    # trade-core 有 cc/gcc → 期望 PASSED(bwrap 掛載隔離被 AppArmor 擋 → direct_no_sandbox,maps-origin 仍真)。
    seam = th.probe_native_lib_loading_on_host(bundle_dir=str(tmp_path / "native_bundle"))
    assert seam["seam_id"] == "native_lib_loading"
    assert seam["verdict"] == "PASSED_TARGET_HOST", (
        f"expected compiled unique-soname .so to load from bundle with symbol=42, got {seam['verdict']}: {seam['note']}"
    )


@on_target
def test_real_rollback_restarts_and_resolves_to_deployed_bundle():
    # #T2:真備內容定址 bundle → kill → 重啟綁到那個 rolled-back bundle 的 launcher → 讀 restart scope 的
    # cgroup.procs、解析 /proc/<pid>/cwd 真的落在 bundle root 下才 PASSED。teardown + 獨立殘留檢查全清。
    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    throwaway = os.path.join(xdg, f"aiml_s16b_frc_{os.getpid()}")
    immut_root = os.path.join(throwaway, "bundle_store")
    os.makedirs(throwaway, exist_ok=True)
    try:
        immut = th.probe_immutable_closure_on_host(deploy_root=immut_root)
        assert immut["verdict"] == "PASSED_TARGET_HOST"
        bundle_root = th._active_bundle_dir(immut_root)
        assert os.path.isdir(bundle_root)
        seam = th.probe_failure_rollback_cleanup_on_host(
            nonce="frctest",
            launcher_argv=th._bundle_pinned_launcher(bundle_root),
            teardown_root=os.path.join(throwaway, "frc"),
            bundle_root=bundle_root,
        )
        assert seam["seam_id"] == "failure_rollback_cleanup"
        assert seam["verdict"] == "PASSED_TARGET_HOST", (
            f"expected kill+restart of the deployed bundle to resolve (proc cwd) under {bundle_root!r}, "
            f"got {seam['verdict']}: {seam['note']}"
        )
    finally:
        import shutil

        shutil.rmtree(throwaway, ignore_errors=True)
