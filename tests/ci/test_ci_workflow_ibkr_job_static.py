"""無條件 workflow static test：機器釘鎖 ci.yml 的 IBKR 守衛鏈(W5-S0;R8 審計洞②)。

病根同 PR#42 修過的 guard-drift:`rust-ibkr-tests` job(五 cargo scope + 五審計步)
過去無任何機器斷言釘住——整 job 或任一審計步被刪,CI 仍全綠靜默過。本測試跑在
ci.yml 的無條件 `git-workflow-policy` job(deliberately independent of the classifier),
故 workflow 自身被改的 PR 必然執行本檔;job/步驟被刪即紅。

風格沿 `test_github_ci_workflow_static.py`:純文字解析(stdlib,不引 PyYAML——
無條件 job 只裝 pytest,依賴最小化)。
"""

from __future__ import annotations

from pathlib import Path
import re


WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
).read_text(encoding="utf-8")


def _strip_comment_lines(text: str) -> str:
    """剝除純注釋行（YAML `#` 與 run block 內 shell `#`;E2 LOW-2）——防注釋文字使
    「命令存在」斷言空洞化（步驟被刪但注釋殘留仍綠）。只剝整行注釋,不動行內內容。"""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _job(name: str) -> str:
    marker = f"\n  {name}:\n"
    assert marker in WORKFLOW, f"ci.yml 缺 job: {name}"
    body = WORKFLOW.split(marker, 1)[1]
    next_job = re.search(r"\n  [a-z0-9][a-z0-9-]*:\n", body)
    scoped = body if next_job is None else body[: next_job.start()]
    return _strip_comment_lines(scoped)


def test_rust_ibkr_tests_job_exists_and_is_gated_on_rust_or_stock_etf() -> None:
    job = _job("rust-ibkr-tests")
    assert "needs: changes" in job
    # 觸發條件:PR-only(成本紀律)+ rust 或 stock_etf 任一 gate 點亮。
    assert "github.event_name == 'pull_request'" in job
    assert "needs.changes.outputs.rust == 'true'" in job
    assert "needs.changes.outputs.stock_etf == 'true'" in job
    assert "runs-on: ubuntu-latest" in job


def test_rust_ibkr_tests_job_keeps_all_cargo_test_scopes() -> None:
    job = _job("rust-ibkr-tests")
    # 六 cargo scope(W-CI 五 scope + W5-S0 ④ fake crate 單元測試)。
    for command in (
        "cargo test -p openclaw_types --test 'ibkr_*'",
        "cargo test -p openclaw_types --test 'stock_etf_*'",
        "cargo test -p openclaw_engine --lib ibkr",
        "cargo test -p openclaw_engine --lib stock_etf",
        "cargo test -p openclaw_engine --bin ibkr_phase2_seal",
        "cargo test -p openclaw_fake_tws",
    ):
        assert command in job, f"rust-ibkr-tests 缺 cargo scope: {command}"


def test_rust_ibkr_tests_job_keeps_all_five_audit_steps() -> None:
    job = _job("rust-ibkr-tests")
    # 五審計步(g4 symbol / permit-stub / fake dev-dep-only / fake 缺席 nm /
    # driver 缺席 nm)——任一被刪即紅。
    for command in (
        "bash helper_scripts/ci/ibkr_g4_symbol_audit.sh",
        "python3 tests/structure/test_ibkr_tws_permit_stub_source_static.py",
        "python3 tests/structure/test_ibkr_fake_tws_devdep_only.py",
        "bash helper_scripts/ci/ibkr_fake_tws_absence_audit.sh",
        "bash helper_scripts/ci/ibkr_driver_absence_audit.sh",
    ):
        assert command in job, f"rust-ibkr-tests 缺審計步: {command}"


def test_stock_etf_guards_job_runs_w4_connection_health_lockstep_suite() -> None:
    # W5-S0 ③(c)(R8 審計洞③):W4 lockstep/parity/tripwire pytest 必在 hosted CI——
    # 單改 Rust emitter 的 PR 由 stock_etf gate 觸發本 job,破 lockstep 即紅。
    job = _job("stock-etf-static-guards")
    # 逐檔字面釘鎖(E2 MEDIUM-1:共享前綴斷言一次可被「移除單檔」繞過)——兩檔各須
    # 出現 ≥2 次(collect-count 段 + 實跑段各一)。
    for suite_file in (
        "test_stock_etf_connection_health_routes.py",
        "test_stock_etf_connection_health_cross_surface_parity.py",
    ):
        assert job.count(suite_file) >= 2, (
            f"stock-etf-static-guards 缺 lockstep 套件檔（需 collect+run 兩段）: "
            f"{suite_file}"
        )
    # 執行計數證明接線(R1 教訓:字面 filter 空轉——收集數必須被斷言非零)。
    assert "--collect-only" in job
    assert 'test "$collected" -ge' in job


def test_this_static_guard_is_wired_into_unconditional_policy_job() -> None:
    # 自釘:本檔必須掛在無條件 git-workflow-policy job——否則守衛自身可被靜默摘除。
    policy = _job("git-workflow-policy")
    assert "needs: changes" not in policy
    assert "tests/ci/test_ci_workflow_ibkr_job_static.py" in policy


def test_rust_check_macos_skips_draft_pull_requests() -> None:
    # W5-S0 ⑤(loop v2 S4 draft 閘):draft PR 不燒 macOS 10x;schedule 事件無
    # pull_request payload,必須以 event_name 守衛保住週一 smoke。
    job = _job("rust-check-macos")
    assert (
        "(github.event_name != 'pull_request' "
        "|| github.event.pull_request.draft == false)"
    ) in job
    assert "needs.changes.outputs.rust == 'true'" in job
